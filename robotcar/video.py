"""Pull the latest JPEG after each write; never relay a queue of old frames."""
import asyncio
import math
import socket
import time

from aiohttp import ClientError, ClientTimeout, web
from .camera import Frame, MAX_FRAME_AGE, MAX_FRAME_BYTES, frame_part


async def snapshot(http, url):
    async with http.get(url, timeout=ClientTimeout(total=.8)) as response:
        if response.status != 200 or response.content_type != 'image/jpeg':
            raise ValueError('Camera unavailable')
        length = response.content_length
        if length is None or not 4 <= length <= MAX_FRAME_BYTES:
            raise ValueError('Invalid camera image length')
        when = float(response.headers['X-Frame-Monotonic'])
        seq = int(response.headers['X-Frame-Sequence'])
        jpeg = await response.content.readexactly(length)
    if not math.isfinite(when) or not 0 <= time.monotonic()-when <= MAX_FRAME_AGE:
        raise ValueError('Camera image is stale')
    if seq < 1 or not (jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9')):
        raise ValueError('Invalid camera image')
    return Frame(seq, when, jpeg)


async def relay_latest(fetch, send, first):
    """At most one fetched image; downstream pressure slows fetching, not capture."""
    frame, previous = first, None
    while True:
        started = time.monotonic()
        age = started-frame.when
        if not 0 <= age < MAX_FRAME_AGE:
            raise ValueError('Camera image became stale')
        identity = (frame.seq, frame.when)
        if identity != previous:
            await asyncio.wait_for(send(frame_part(frame)), min(.5, MAX_FRAME_AGE-age))
            previous = identity
        await asyncio.sleep(max(0, .05-(time.monotonic()-started)))
        frame = await fetch()


async def stream_latest(request, http, url):
    response = None
    try:
        first = await snapshot(http, url)
        response = web.StreamResponse(headers={
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
            'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
        transport = request.transport
        if transport:
            transport.set_write_buffer_limits(high=16384, low=4096)
            sock = transport.get_extra_info('socket')
            if sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        await response.prepare(request)
        await relay_latest(lambda: snapshot(http, url), response.write, first)
    except (ClientError, OSError, ValueError, KeyError, asyncio.IncompleteReadError, asyncio.TimeoutError):
        if response is None or not response.prepared:
            raise web.HTTPServiceUnavailable(text='Videostrøm er utilgjengelig.')
        # Discard pending transport data instead of flushing an old video tail.
        if request.transport:
            request.transport.abort()
        response.force_close()
        return response
