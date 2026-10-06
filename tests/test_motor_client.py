import asyncio
import json
import os
import unittest
from unittest.mock import patch

from robotcar.navigation import MotorClient


class MotorConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'ROBOTCAR_TOKEN':'test-only-token-with-no-hardware'})
        self.env.start()
        self.connections = 0
        self.received = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.behaviour = 'delay_first'
        self.tasks = set()
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.client = MotorClient('127.0.0.1', self.server.sockets[0].getsockname()[1])

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.connections += 1
        connection = self.connections
        try:
            while line := await reader.readline():
                msg = json.loads(line)
                if self.behaviour == 'delay_first' and connection == 1:
                    self.received.set()
                    # The request has reached the server, but its reply has not.
                    await reader.read()
                    self.disconnected.set()
                    return
                seq = msg['seq']-1 if self.behaviour == 'wrong_sequence' else msg['seq']
                writer.write((json.dumps({'ok':True, 'seq':seq, 'armed':False})+'\n').encode())
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            self.tasks.discard(task)

    async def asyncTearDown(self):
        self.client.disconnect()
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.env.stop()

    async def test_cancelled_command_disconnects_before_next_request(self):
        task = asyncio.create_task(self.client.request('arm'))
        await asyncio.wait_for(self.received.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(self.disconnected.wait(), 1)
        self.assertFalse(self.client.state['armed'])
        with self.assertRaisesRegex(ValueError, 'rearm'):
            await self.client.request('drive', left=.2, right=.2)
        await self.client.request('status')
        self.assertEqual(self.connections, 2)
        self.assertEqual(self.client.state['seq'], 2)

    async def test_wrong_reply_sequence_drops_connection(self):
        self.behaviour = 'wrong_sequence'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            await self.client.request('arm')
        self.assertFalse(self.client.state['connected'])
        self.assertFalse(self.client.state['armed'])
        self.assertIsNone(self.client.writer)


if __name__ == '__main__':
    unittest.main()
