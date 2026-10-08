"""Reversible service isolation on the camera Pi; never disables SSH/network.

Existing enablement and unit files are preserved. An additional condition
blocks each selected service/socket/timer, including D-Bus activation.
Only drop-ins created by this tool are removed by restore.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/var/lib/robotcar-camera-isolation')
GATES = Path('/etc/robotcar-camera-isolation/blocked')
DROPIN = '99-robotcar-camera-isolation.conf'
TESTS = ['robotcar-camera-test@front.service', 'robotcar-camera-test@rear.service']
FIXED = ['robotcar@camera.service']
PROTECTED = {'ssh.service', 'sshd.service', 'NetworkManager.service',
             'NetworkManager-dispatcher.service', 'NetworkManager-wait-online.service',
             'wpa_supplicant.service', 'dbus.service', 'dbus.socket',
             'systemd-logind.service', 'systemd-udevd.service', 'systemd-journald.service'}

SYSTEM_A = '''robotcar@vision.service robotcar@lidar.service robotcar@mapworker.service
robotcar@webapp.service hailort.service'''.split()
SYSTEM_B = '''accounts-daemon.service avahi-daemon.service avahi-daemon.socket
bluetooth.service hciuart.service cron.service cups-browsed.service cups.service
cups.socket cups.path glamor-test.service lightdm.service ModemManager.service
nmbd.service smbd.service samba-ad-dc.service rp1-test.service
rpi-display-backlight.service rpi-eeprom-update.service rtkit-daemon.service
triggerhappy.service triggerhappy.socket udisks2.service wayvnc-control.service
wayvnc.service wayvnc-generate-keys.service vncserver-virtuald.service
vncserver-x11-serviced.service packagekit.service packagekit-offline-update.service
apt-daily.service apt-daily.timer apt-daily-upgrade.service apt-daily-upgrade.timer
dpkg-db-backup.service dpkg-db-backup.timer e2scrub_all.service e2scrub_all.timer
e2scrub_reap.service fstrim.service fstrim.timer logrotate.service logrotate.timer
man-db.service man-db.timer pi-drive-backup.service pi-drive-backup.timer'''.split()
USER_A_PREFIXES = ('pipewire', 'pulseaudio', 'wireplumber', 'filter-chain',
                   'xdg-desktop-portal', 'xdg-document-portal', 'xdg-permission-store', 'gvfs-')


def command(scope, *args, check=True):
    prefix = ['systemctl']
    if scope == 'user':
        prefix = ['runuser', '-u', 'pi', '--', 'env', 'XDG_RUNTIME_DIR=/run/user/1000',
                  'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus', 'systemctl', '--user']
    result = subprocess.run(prefix+list(args), text=True, capture_output=True, timeout=35)
    if check and result.returncode:
        raise RuntimeError(' '.join(prefix+list(args))+': '+result.stderr.strip())
    return result.stdout.strip()


def properties(scope, name):
    text = command(scope, 'show', name, '-p', 'Id', '-p', 'LoadState', '-p', 'ActiveState',
                   '-p', 'SubState', '-p', 'UnitFileState', '-p', 'FragmentPath',
                   '-p', 'Description', '-p', 'ConditionResult')
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def write_json(path, value):
    temp = path.with_suffix('.next')
    with temp.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def dropin(scope, name):
    base = Path('/etc/systemd/system') if scope == 'system' else Path('/home/pi/.config/systemd/user')
    return base/(name+'.d')/DROPIN


def condition(scope, name):
    return '[Unit]\n# Managed by robotcar camera isolation\nConditionPathExists=!'+str(GATES/scope/name)+'\n'


def inventory():
    if (ROOT/'original.json').exists():
        return json.loads((ROOT/'original.json').read_text())
    if Path('/proc/device-tree/model').read_text().find('Raspberry Pi 5') < 0:
        raise RuntimeError('This setup is for the camera Pi 5 only')
    addresses = json.loads(subprocess.check_output(['ip', '-j', 'address'], text=True))
    if not any(a.get('local') == '192.168.4.44' for interface in addresses for a in interface.get('addr_info', [])):
        raise RuntimeError('Expected the camera Pi at 192.168.4.44')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    original = {'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'hostname': os.uname().nodename, 'default_target': command('system', 'get-default'),
                'units': [], 'groups': {'A': [], 'B': []}}
    system = [(x, 'A') for x in SYSTEM_A]+[(x, 'B') for x in SYSTEM_B]+[(x, 'fixed') for x in FIXED]
    user_files = json.loads(command('user', 'list-unit-files', '--output=json', '--no-pager'))
    user = []
    for item in user_files:
        name = item['unit_file']
        if name in PROTECTED or name.startswith('systemd-') or '@.' in name:
            continue
        if name.endswith(('.service', '.socket', '.timer', '.path')):
            user.append((name, 'A' if name.startswith(USER_A_PREFIXES) else 'B'))
    for scope, selected in (('system', system), ('user', user)):
        original[scope+'_unit_files'] = json.loads(command(scope, 'list-unit-files', '--output=json', '--no-pager'))
        original[scope+'_loaded_units'] = json.loads(command(scope, 'list-units', '--all', '--output=json', '--no-pager'))
        for name, group in selected:
            if name in PROTECTED or '/' in name:
                raise ValueError('Protected/invalid candidate: '+name)
            props = properties(scope, name)
            if props['LoadState'] == 'not-found':
                continue
            path = dropin(scope, name)
            if path.exists():
                raise RuntimeError('Refusing to overwrite pre-existing drop-in: '+str(path))
            entry = dict(scope=scope, name=name, group=group, original=props)
            original['units'].append(entry)
            if group != 'fixed':
                original['groups'][group].append(scope+':'+name)
    write_json(ROOT/'original.json', original)
    return original


def permitted(original, phase, custom=None):
    if phase == 'baseline':
        return set()
    if phase in ('A', 'B'):
        return set(original['groups'][phase])
    result = set(json.loads(Path(custom).read_text()))
    known = set(original['groups']['A']+original['groups']['B'])
    if not result <= known:
        raise ValueError('Allow-list contains an unknown or fixed-off unit')
    return result


def close_desktop_sessions():
    sessions = subprocess.check_output(['loginctl', 'list-sessions', '--no-legend'], text=True)
    for line in sessions.splitlines():
        sid = line.split()[0]
        result = subprocess.run(['loginctl', 'show-session', sid, '-p', 'Service', '-p', 'Type'], text=True, capture_output=True)
        if result.returncode:
            continue  # Display-manager shutdown can remove the session first.
        details = result.stdout
        if any(x in details.splitlines() for x in ('Type=wayland', 'Type=x11', 'Service=lightdm', 'Service=lightdm-autologin')):
            subprocess.run(['loginctl', 'terminate-session', sid], check=True, timeout=10)


def apply(original, phase, custom=None):
    allow = permitted(original, phase, custom)
    GATES.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    GATES.parent.chmod(0o755)
    GATES.mkdir(mode=0o755, exist_ok=True)
    GATES.chmod(0o755)
    for scope in ('system', 'user'):
        (GATES/scope).mkdir(mode=0o755, parents=True, exist_ok=True)
        (GATES/scope).chmod(0o755)
    for entry in original['units']:
        scope, name = entry['scope'], entry['name']
        path = dropin(scope, name)
        expected = condition(scope, name)
        if path.exists() and path.read_text() != expected:
            raise RuntimeError('Isolation drop-in changed externally: '+str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o755)
        path.write_text(expected)
        path.chmod(0o644)
        gate = GATES/scope/name
        if scope+':'+name in allow:
            gate.unlink(missing_ok=True)
        else:
            gate.touch(mode=0o644)
    command('system', 'daemon-reload')
    command('user', 'daemon-reload')
    for scope in ('user', 'system'):
        stopped = [e['name'] for e in original['units'] if e['scope'] == scope and scope+':'+e['name'] not in allow]
        if stopped:
            # D-Bus/socket activation can replace a queued stop job. Conditions
            # already block fresh starts; verify resulting states rather than
            # treating a canceled intermediate job as the final outcome.
            command(scope, 'stop', '--no-block', *stopped, check=False)
            deadline = time.monotonic()+120
            while True:
                remaining = [name for name in stopped
                             if properties(scope, name)['ActiveState'] not in ('inactive', 'failed')]
                if not remaining:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Units did not stop: '+', '.join(remaining))
                time.sleep(1)
    if 'system:lightdm.service' not in allow:
        close_desktop_sessions()
    command('system', 'enable', *TESTS)
    write_json(ROOT/'phase.json', {'phase': phase, 'allowed': sorted(allow), 'applied_at': time.time(),
                                 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                                 'note': 'Reboot before comparing phases; old sensor state can persist.'})
    # Only the initial baseline is started live. Later phase changes are applied
    # for the next user-coordinated reboot, not mixed into a running trial.
    if phase == 'baseline':
        command('system', 'start', '--no-block', *TESTS)


def restore(original):
    command('system', 'disable', '--now', *TESTS)
    for entry in original['units']:
        scope, name = entry['scope'], entry['name']
        path = dropin(scope, name)
        if path.exists():
            if path.read_text() != condition(scope, name):
                raise RuntimeError('Refusing to remove externally changed drop-in: '+str(path))
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        (GATES/scope/name).unlink(missing_ok=True)
    command('system', 'daemon-reload')
    command('user', 'daemon-reload')
    for scope in ('system', 'user'):
        live = [e['name'] for e in original['units'] if e['scope'] == scope
                and e['original']['ActiveState'] == 'active' and e['original']['SubState'] != 'exited']
        if live:
            command(scope, 'start', '--no-block', *live)
    write_json(ROOT/'phase.json', {'phase':'restored', 'restored_at':time.time()})


def status(original):
    phase = json.loads((ROOT/'phase.json').read_text()) if (ROOT/'phase.json').exists() else {}
    blocked, leaking = [], []
    for entry in original['units']:
        scope, name = entry['scope'], entry['name']
        if (GATES/scope/name).exists():
            blocked.append(scope+':'+name)
            props = properties(scope, name)
            if props['ActiveState'] in ('active', 'activating', 'reloading'):
                leaking.append(dict(unit=scope+':'+name, state=props['ActiveState']))
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    cameras = {}
    for name in ('front', 'rear'):
        path = Path('/run/robotcar-camera-test')/(name+'.json')
        data = json.loads(path.read_text()) if path.exists() else {}
        last = data.get('last_frame')
        age = time.monotonic()-last if last is not None else None
        data['frame_age_s'] = round(age, 2) if age is not None else None
        data['unit'] = properties('system', 'robotcar-camera-test@'+name+'.service')
        data['fresh'] = bool(data.get('boot_id') == boot and age is not None and age < 2
                             and not data.get('error') and data['unit']['ActiveState'] == 'active')
        cameras[name] = data
    return dict(phase=phase, blocked_count=len(blocked), unexpectedly_active=leaking, cameras=cameras)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'baseline', 'A', 'B', 'custom', 'restore', 'status'))
    parser.add_argument('--allow-file')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the camera Pi')
    if args.operation == 'prepare':
        original = inventory()
        print(json.dumps({'candidates': len(original['units']), 'groups': original['groups']}, indent=2))
        return
    original = json.loads((ROOT/'original.json').read_text())
    if args.operation == 'restore':
        restore(original)
    elif args.operation != 'status':
        apply(original, args.operation, args.allow_file)
    print(json.dumps(status(original), indent=2))


if __name__ == '__main__':
    main()
