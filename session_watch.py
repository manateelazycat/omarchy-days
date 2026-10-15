#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe Omarchy lock, display standby and login1 sleep without network I/O."""
import json
import selectors
import signal
import subprocess
import time


def read_command(command):
    return subprocess.check_output(command, text=True, timeout=2, stderr=subprocess.DEVNULL).strip()


def session_available():
    try:
        unlocked = read_command(['omarchy-shell', 'lock', 'isLocked']) == 'false'
        monitors = json.loads(read_command(['hyprctl', '-j', 'monitors']))
        return unlocked and any(m.get('dpmsStatus', False) for m in monitors)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False  # Unknown session state must not start network requests.


def main():
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    monitor = subprocess.Popen(['dbus-monitor', '--system',
        "type='signal',interface='org.freedesktop.login1.Manager',member='PrepareForSleep'"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(monitor.stdout, selectors.EVENT_READ)
    sleeping, previous, pending = False, None, b''
    last_clock = time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()
    try:
        while True:
            wake = False
            for key, _ in selector.select(timeout=1):
                chunk = key.fileobj.read(4096)
                if not chunk:
                    return  # QML restarts the observer if the system bus drops.
                pending += chunk
                lines = pending.split(b'\n')
                pending = lines.pop()
                for line in lines:
                    if b'boolean true' in line:
                        sleeping = True
                    elif b'boolean false' in line:
                        sleeping, wake = False, True
            clock = time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()
            wake = wake or clock - last_clock > 0.5
            last_clock = clock
            available = not sleeping and session_available()
            if available != previous or wake:
                print(json.dumps({'available': available, 'wake': wake}), flush=True)
                previous = available
    finally:
        selector.close()
        monitor.terminate()
        monitor.wait(timeout=2)


if __name__ == '__main__':
    main()
