# SPDX-License-Identifier: GPL-3.0-only
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import backend


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.city = {'name': '天津', 'latitude': 39.14, 'longitude': 117.18, 'timezone': 'Asia/Shanghai'}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, kwargs in [('CACHE', {'new': Path(self.temp.name)}),
            ('weather_settings', {'return_value': {'provider': 'qweather', 'qweather': {}}}),
            ('validate_qweather', {'return_value': {'api_host': 'example.re.qweatherapi.com'}}),
            ('qweather_token', {'return_value': 'test-token'})]:
            p = patch.object(backend, name, **kwargs); p.start(); self.addCleanup(p.stop)

    def alert(self, id='a', **changes):
        return dict(id=id, effectiveTime=(self.now-timedelta(minutes=1)).isoformat(),
                    expireTime=(self.now+timedelta(hours=1)).isoformat(), issuedTime=self.now.isoformat(),
                    headline='大风预警', description='预警详情', severity='minor',
                    messageType={'code': 'alert'}, color={'code': 'blue'}, icon='1023', eventType={'name': '海上大风'}, **changes)

    def test_updated_cancelled_expired_and_future_alerts(self):
        old = self.alert('old')
        updated = self.alert('new'); updated['messageType'] = {'code': 'update', 'supersedes': ['old']}
        cancelled = self.alert('cancelled')
        cancellation = self.alert('cancel'); cancellation['messageType'] = {'code': 'cancel', 'supersedes': ['cancelled']}
        expired = self.alert('expired'); expired['expireTime'] = self.now.isoformat()
        future = self.alert('future'); future['effectiveTime'] = (self.now+timedelta(hours=1)).isoformat()
        rows, attr = backend.normalize_alerts({'alerts': [old,updated,cancelled,cancellation,expired,future], 'metadata': {'attributions': ['发布机构']}}, self.now)
        self.assertEqual([a['id'] for a in rows], ['new'])
        self.assertEqual(attr, ['发布机构'])
        self.assertEqual(rows[0]['eventName'], '海上大风')
        self.assertEqual(rows[0]['icon'], '1023')

    def test_zero_results_and_malformed_response_are_distinct(self):
        self.assertEqual(backend.normalize_alerts({'metadata': {'zeroResult': True}})[0], [])
        with self.assertRaises(backend.DataError): backend.normalize_alerts({})
        with self.assertRaises(backend.DataError): backend.normalize_alerts({'alerts': [{}]})

    def test_15_minute_cache_and_forced_resume_deduplication(self):
        stamp = self.now.timestamp()
        with patch.object(backend.time, 'time', return_value=stamp) as clock, patch.object(backend, 'fetch_json', return_value={'alerts': [self.alert()]}) as fetch:
            backend.get_alerts(self.city)
            self.assertEqual(fetch.call_count, 1)
            self.assertIn('/weatheralert/v1/current/39.14/117.18', fetch.call_args.args[0])
            clock.return_value = stamp+899
            self.assertLessEqual(backend.get_alerts(self.city)['nextRefresh'], 1)
            self.assertEqual(fetch.call_count, 1)
            clock.return_value = stamp+900
            backend.get_alerts(self.city)
            self.assertEqual(fetch.call_count, 2)
            clock.return_value = stamp+910
            backend.get_alerts(self.city, force=True)
            backend.get_alerts(self.city, force=True)
            self.assertEqual(fetch.call_count, 3)

    def test_failure_preserves_valid_alerts_and_retries_on_schedule(self):
        stamp = self.now.timestamp()
        with patch.object(backend.time, 'time', return_value=stamp) as clock, patch.object(backend, 'fetch_json', return_value={'alerts': [self.alert()]}) as fetch:
            backend.get_alerts(self.city)
            clock.return_value = stamp+900
            fetch.side_effect = backend.DataError('HTTP 503')
            result = backend.get_alerts(self.city)
            self.assertFalse(result['ok']); self.assertTrue(result['stale'])
            self.assertEqual(result['alerts'][0]['id'], 'a')
            clock.return_value = stamp+1000
            backend.get_alerts(self.city)
            self.assertEqual(fetch.call_count, 2)
            other = dict(self.city, longitude=120)
            result = backend.get_alerts(other)
            self.assertEqual(result['alerts'], [])
            self.assertFalse(result['ok'])

    def test_other_provider_does_not_request_or_locate(self):
        with patch.object(backend, 'weather_settings', return_value={'provider': 'open-meteo'}), patch.object(backend, 'fetch_json') as fetch, patch.object(backend, 'locate_city') as locate:
            self.assertFalse(backend.get_alerts()['enabled'])
            fetch.assert_not_called(); locate.assert_not_called()
