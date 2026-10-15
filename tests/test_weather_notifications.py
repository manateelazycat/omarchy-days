import copy
import io
import json
from pathlib import Path
import tempfile
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
import weather_notifications as notifications


class NotificationsTest(unittest.TestCase):
    def setUp(self):
        settings = patch.object(notifications, 'weather_settings', return_value={'notifications': True})
        settings.start()
        self.addCleanup(settings.stop)
        self.now = 1800000000
        self.city = dict(name='测试地点', latitude=30, longitude=114, timezone='Asia/Shanghai')

    def iso(self, offset):
        return datetime.fromtimestamp(self.now + offset, timezone.utc).isoformat()

    def weather(self, wet=False, snow=False, shift=0):
        return dict(ok=True, provider='qweather', city=self.city, nowcast=dict(points=[
            dict(time=self.iso(-60), amount=int(wet), type='snow' if snow else 'rain'),
            dict(time=self.iso(600 + shift), amount=int(not wet), type='snow' if snow else 'rain')]))

    def test_rain_and_snow_transitions(self):
        for wet in (False, True):
            for snow in (False, True):
                event = notifications.plan('weather', self.weather(wet, snow), {}, self.now)[0]
                self.assertEqual(event['title'], ('雪' if snow else '雨') + ('将停' if wet else '将至'))

    def test_dedup_and_material_time_change(self):
        state = {}
        self.assertEqual(len(notifications.plan('weather', self.weather(), state, self.now)), 1)
        self.assertEqual(notifications.plan('weather', self.weather(), state, self.now), [])
        self.assertEqual(notifications.plan('weather', self.weather(shift=300), state, self.now), [])
        self.assertEqual(len(notifications.plan('weather', self.weather(shift=900), state, self.now)), 1)
        self.assertEqual(len(notifications.plan('weather', self.weather(wet=True), state, self.now)), 1)

    def test_failure_fallback_and_expired_are_silent(self):
        for changes in (dict(ok=False), dict(stale=True), dict(provider='open-meteo')):
            data = self.weather(); data.update(changes)
            self.assertEqual(notifications.plan('weather', data, {}, self.now), [])
        self.assertEqual(notifications.plan('weather', self.weather(), {}, self.now + 8000), [])

    def alert(self, message='alert'):
        return dict(id=message, messageType=dict(code=message), eventType=dict(name='大风'),
                    icon='1006', effectiveTime=self.iso(-60), expireTime=self.iso(3600), headline='大风预警')

    def test_alert_lifecycle_and_restart_dedup(self):
        state = {}
        for message, action in [('alert', '发布'), ('update', '更新'), ('cancel', '取消')]:
            data = dict(ok=True, enabled=True, city=self.city, messages=[self.alert(message)])
            events = notifications.plan('alerts', data, state, self.now)
            self.assertEqual(events[0]['title'], '大风预警' + action)
            self.assertEqual(notifications.plan('alerts', data, copy.deepcopy(state), self.now), [])
        self.assertEqual(notifications.plan('alerts', dict(ok=True, enabled=True, messages=[]), state, self.now), [])
        self.assertEqual(notifications.plan('alerts', dict(ok=False, enabled=True, messages=[]), state, self.now), [])

    def test_replaced_alert_not_reannounced(self):
        old = self.alert(); new = self.alert('update')
        new['messageType']['supersedes'] = ['alert']
        events = notifications.plan('alerts', dict(ok=True, enabled=True, messages=[old, new]), {}, self.now)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['title'], '大风预警更新')

    def test_worker_persistence_and_locked_session(self):
        packet = json.dumps(dict(kind='weather', data=self.weather())) + '\n'
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(notifications, 'STATE', Path(directory)), \
                patch.object(notifications.time, 'time', return_value=self.now), \
                patch.object(notifications, 'send') as send:
            with patch.object(notifications, 'session_available', return_value=False), \
                    patch.object(notifications.sys, 'stdin', io.StringIO(packet)):
                notifications.main()
            send.assert_not_called()
            self.assertFalse((Path(directory) / 'notifications.json').exists())
            for _ in range(2):
                with patch.object(notifications, 'session_available', return_value=True), \
                        patch.object(notifications.sys, 'stdin', io.StringIO(packet)):
                    notifications.main()
            self.assertEqual(send.call_count, 1)

    def test_disabled_notifications_do_not_send_or_consume_events(self):
        packet = json.dumps(dict(kind='weather', data=self.weather())) + '\n'
        with patch.object(notifications, 'weather_settings', return_value={'notifications': False}), \
                patch.object(notifications, 'session_available', return_value=True), \
                patch.object(notifications.sys, 'stdin', io.StringIO(packet)), \
                patch.object(notifications, 'plan') as plan, \
                patch.object(notifications, 'send') as send:
            notifications.main()
            plan.assert_not_called()
            send.assert_not_called()

    def test_send_uses_argv_and_click_action(self):
        with patch.object(notifications.subprocess, 'run') as run:
            notifications.send(dict(title='雨将至', body='<b>地点</b>', icon='305', urgent=False))
        args = run.call_args.args[0]
        self.assertIn('&lt;b&gt;地点&lt;/b&gt;', args)
        self.assertEqual(args[-4:], ['--exec', 'omarchy-shell', 'andy.days', 'open'])


if __name__ == '__main__':
    unittest.main()
