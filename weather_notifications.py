#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Desktop weather notifications with durable, cross-monitor deduplication."""
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from session_watch import session_available
from backend import weather_settings

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'omarchy-days'


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0


def plan(kind, data, state, now):
    """Return notifications and mutate only the supplied candidate state."""
    if not data.get('ok') or data.get('stale'):
        return []
    city = data.get('city') or {}
    place = ' · '.join(dict.fromkeys(filter(None, [city.get('name'), city.get('cityName')])))
    events = []
    if kind == 'weather':
        if data.get('provider') != 'qweather':
            return []
        points = [p for p in (data.get('nowcast') or {}).get('points', [])
                  if now - 300 < stamp(p.get('time')) <= now + 7200]
        if not points:
            return []
        wet = points[0]['amount'] > 0
        transition = next((p for p in points[1:] if (p['amount'] > 0) != wet), None)
        if not transition:
            if now - state.get('rain', {}).get('seen', 0) > 1800:
                state.pop('rain', None)
            return []
        snow = (points[0] if wet else transition).get('type') == 'snow'
        event = ('stop' if wet else 'start') + ('snow' if snow else 'rain')
        target = stamp(transition['time'])
        old = state.get('rain', {})
        changed = old.get('event') != event or now - old.get('seen', 0) > 1800
        shifted = abs(target - old.get('target', target)) >= 900
        state['rain'] = dict(old, seen=now)
        if changed or shifted:
            at = datetime.fromtimestamp(target, ZoneInfo(city.get('timezone', 'Asia/Shanghai'))).strftime('%H:%M')
            label = '雪' if snow else '雨'
            title = label + ('将停' if wet else '将至')
            if not wet and (data.get('current') or {}).get('icon') in ('rain', 'snow', 'storm'):
                title = '降水提醒'
            if shifted and not changed:
                title += ' · 时间更新'
            body = f'{place} · 预计 {at} ' + (label + '停' if wet else '起有降水')
            events.append(dict(title=title, body=body, icon='400' if snow else '305', urgent=False))
            state['rain'] = {'event': event, 'target': target, 'seen': now}
    elif kind == 'alerts' and data.get('enabled'):
        seen = {k: v for k, v in state.get('alerts', {}).items() if now - v < 7 * 86400}
        messages = data.get('messages', [])
        superseded = {i for a in messages for i in (a.get('messageType') or {}).get('supersedes', [])}
        for alert in messages:
            if alert.get('id') in superseded or not stamp(alert.get('effectiveTime')) <= now < stamp(alert.get('expireTime')):
                continue
            message = (alert.get('messageType') or {}).get('code', 'alert')
            if message not in ('alert', 'update', 'cancel'):
                continue
            signature = hashlib.sha256(json.dumps(alert, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if signature in seen:
                continue
            action = {'alert': '发布', 'update': '更新', 'cancel': '取消'}[message]
            category = (alert.get('eventType') or {}).get('name') or '天气'
            body = place + '\n' + (alert.get('headline') or alert.get('senderName') or category + '预警')
            body += '\n和风天气 · 以官方发布为准'
            events.append(dict(title=category + '预警' + action, body=body, icon=str(alert.get('icon') or '999'),
                               urgent=message != 'cancel' and alert.get('severity') in ('severe', 'extreme')))
            seen[signature] = now
        state['alerts'] = seen
    return events


def send(event):
    icon = ROOT / 'assets/qweather/notifications' / (event['icon'] + '.svg')
    if not icon.is_file() or icon.parent != ROOT / 'assets/qweather/notifications':
        icon = ROOT / 'assets/qweather/notifications/999.svg'
    subprocess.run(['omarchy', 'notification', 'send', '--app-name', '日历与天气',
                    '-u', 'critical' if event['urgent'] else 'normal', '-t', '12000', '-i', str(icon),
                    event['title'], html.escape(event['body']), '--exec', 'omarchy-shell', 'andy.days', 'open'],
                   check=True, timeout=8, stdout=subprocess.DEVNULL)


def main():
    packet = json.loads(sys.stdin.readline(1048577))
    if not session_available() or not weather_settings().get("notifications", True):
        return
    data = packet['data']
    city = data.get('city') or {}
    key = json.dumps([city.get('latitude'), city.get('longitude')])
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'notifications.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = STATE / 'notifications.json'
        try:
            states = json.loads(path.read_text())
        except (OSError, ValueError):
            states = {}
        now = time.time()
        states = {k: v for k, v in states.items() if now - v.get('touched', 0) < 7 * 86400}
        state = states.setdefault(key, {})
        events = plan(packet['kind'], data, state, now)
        for event in events:
            if not session_available() or not weather_settings().get("notifications", True):
                return
            send(event)
        state['touched'] = now
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(states, ensure_ascii=False))
        temporary.chmod(0o600)
        temporary.replace(path)


if __name__ == '__main__':
    main()
