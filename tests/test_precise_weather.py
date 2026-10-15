# SPDX-License-Identifier: GPL-3.0-only
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import backend
import session_watch


class PreciseWeatherTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-10-15T15:00:00+08:00')
        self.city = {'name': '天津', 'latitude': 39.14, 'longitude': 117.18, 'timezone': 'Asia/Shanghai'}
        self.hours = {'hours': [{'forecastTime': (self.now + timedelta(hours=1)).isoformat(),
                                'temperature': {'value': 20}, 'condition': {'code': '100'}}]}

    def normalize(self, values, kind='rain'):
        minute = {'code': '200', 'minutely': [dict(fxTime=(self.now + timedelta(minutes=5*i)).isoformat(),
                  precip=str(value), type=kind) for i, value in enumerate(values)]}
        return backend.normalize_precise_weather(self.hours, minute, self.city, self.now)

    def test_rain_start_and_snow_end(self):
        start = self.normalize([0, 0, .2, .2])
        self.assertEqual(start['nowcast']['summary'], '预计 15:10 开始下雨')
        self.assertFalse(start['precipitating'])
        end = self.normalize([.1, .1, 0, 0], 'snow')
        self.assertTrue(end['precipitating'])
        self.assertEqual(end['nowcast']['summary'], '预计 15:10 雪停')
        self.assertFalse(self.normalize([0, 0])['precipitating'])

    def test_invalid_and_expired_data_rejected(self):
        with self.assertRaises(backend.DataError):
            backend.normalize_precise_weather(self.hours, {'code': '403'}, self.city, self.now)
        with self.assertRaises(backend.DataError):
            self.normalize([])
        with self.assertRaises(backend.DataError):
            self.normalize([-1, 0])

    def test_cache_intervals_and_no_stale_qweather(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, 'CACHE', Path(directory)), patch.object(backend, 'validate_qweather', return_value={}):
            for interval in (300, 600):
                result = {'hourly': [{}], 'refreshAfter': interval, 'today': datetime.now().date().isoformat()}
                with patch.object(backend, 'fetch_qweather', return_value=result) as fetch:
                    backend.get_qweather(self.city, True, {'qweather': {}})
                    fetch.assert_called_once()
                paths = list(Path(directory).glob('qweather-*.json'))
                cache = backend.read_json(paths[0]); cache['savedAt'] -= interval - 10
                backend.atomic_json(paths[0], cache)
                with patch.object(backend, 'fetch_qweather') as fetch:
                    got = backend.get_qweather(self.city, False, {'qweather': {}})
                    fetch.assert_not_called()
                    self.assertLessEqual(got['nextRefresh'], 10)
                cache['savedAt'] -= 20; backend.atomic_json(paths[0], cache)
                with patch.object(backend, 'fetch_qweather', side_effect=backend.DataError('offline')):
                    with self.assertRaises(backend.DataError):
                        backend.get_qweather(self.city, False, {'qweather': {}})
                paths[0].unlink()

    def test_fallback_does_not_change_selected_source(self):
        settings = {'provider': 'qweather', 'qweather': {}}
        today = datetime.now().date().isoformat()
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, 'CACHE', Path(directory)), patch.object(backend, 'weather_settings', return_value=settings), patch.object(backend, 'get_qweather', side_effect=backend.DataError('403')), patch.object(backend, 'fetch_json', return_value={'daily': {'time': [today]}}):
            result = backend.get_weather(self.city)
            self.assertEqual(result['provider'], 'open-meteo')
            self.assertNotIn('nowcast', result)
            self.assertIn('回退', result['warning'])
            self.assertIn('403', result['warning'])
            self.assertEqual(settings['provider'], 'qweather')

    def test_fallback_retries_only_when_due_and_can_recover(self):
        settings = {'provider': 'qweather', 'qweather': {}}
        fallback = {'ok': True, 'provider': 'open-meteo', 'refreshAfter': 600}
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, 'CACHE', Path(directory)), patch.object(backend, 'weather_settings', return_value=settings), patch.object(backend, '_get_weather', return_value=fallback) as request:
            backend.get_weather(self.city)
            backend.get_weather(self.city)
            self.assertEqual(request.call_count, 1)
            path = next(Path(directory).glob('weather-result-*.json'))
            cached = backend.read_json(path); cached['savedAt'] -= 601
            backend.atomic_json(path, cached)
            request.return_value = {'ok': True, 'provider': 'qweather'}
            self.assertEqual(backend.get_weather(self.city)['provider'], 'qweather')
            self.assertEqual(request.call_count, 2)

    def test_session_lock_and_display_standby_gate_network(self):
        for locked, monitors, expected in [('true', '[{"dpmsStatus":true}]', False), ('false', '[{"dpmsStatus":false}]', False), ('false', '[{"dpmsStatus":true}]', True)]:
            with patch.object(session_watch, 'read_command', side_effect=[locked, monitors]):
                self.assertEqual(session_watch.session_available(), expected)
        with patch.object(session_watch, 'read_command', side_effect=OSError()):
            self.assertFalse(session_watch.session_available())
