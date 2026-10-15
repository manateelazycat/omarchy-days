# SPDX-License-Identifier: GPL-3.0-only
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend


class WeatherSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / 'weather.json'
        self.key = self.directory / 'private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        self.config = dict(api_host='example.re.qweatherapi.com', developer_id='Q123456789',
                           project_id='P123456789', credential_id='K123456789', private_key_path=str(self.key))
        self.settings = dict(provider='qweather', qweather=self.config, notifications=True)
        self.patcher = patch.object(backend, 'WEATHER_SETTINGS', self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_default_still_uses_original_provider(self):
        self.assertEqual(backend.weather_settings()['provider'], 'open-meteo')

    def test_test_does_not_save_and_failed_save_keeps_previous(self):
        original = {'provider': 'open-meteo'}
        backend.atomic_json(self.path, original)
        with patch.object(backend, 'fetch_qweather', return_value={'ok': True}):
            self.assertTrue(backend.configure_weather('test', self.settings)['ok'])
        self.assertEqual(backend.read_json(self.path), original)
        with patch.object(backend, 'fetch_qweather', side_effect=backend.DataError('HTTP 401')):
            with self.assertRaises(backend.DataError):
                backend.configure_weather('save', self.settings)
        self.assertEqual(backend.read_json(self.path), original)

    def test_save_persists_and_can_switch_back_without_credentials(self):
        with patch.object(backend, 'fetch_qweather', return_value={'ok': True}):
            backend.configure_weather('save', self.settings)
        self.assertEqual(backend.weather_settings(), self.settings)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with patch.object(backend, 'fetch_qweather') as fetch:
            backend.configure_weather('save', {'provider': 'open-meteo', 'qweather': self.config})
            fetch.assert_not_called()
        self.assertEqual(backend.weather_settings()['provider'], 'open-meteo')

    def test_notification_default_and_save_without_network(self):
        self.assertTrue(backend.weather_settings()['notifications'])
        backend.atomic_json(self.path, {'provider': 'qweather', 'qweather': self.config})
        self.assertTrue(backend.weather_settings()['notifications'])
        with patch.object(backend, 'fetch_qweather') as fetch:
            backend.configure_weather('save', {**self.settings, 'notifications': False})
            self.assertFalse(backend.weather_settings()['notifications'])
            backend.configure_weather('save', self.settings)
            self.assertTrue(backend.weather_settings()['notifications'])
            fetch.assert_not_called()

    def test_rejects_untrusted_hosts_and_missing_keys(self):
        for host in ('example.com', 'example.qweatherapi.com.evil.com', 'example.qweatherapi.com/path', 'user@example.qweatherapi.com'):
            with self.subTest(host=host), self.assertRaises(backend.DataError):
                backend.validate_qweather({**self.config, 'api_host': host})
        with self.assertRaises(backend.DataError):
            backend.validate_qweather({**self.config, 'private_key_path': '/missing/key.pem'})

    def test_corrupt_settings_do_not_silently_switch_provider(self):
        self.path.write_text('{')
        with self.assertRaises(backend.DataError):
            backend.weather_settings()

    def test_jwt_claims_and_signature(self):
        token = backend.qweather_token(self.config)
        head, body, sig = token.split('.')
        decode = lambda part: base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))
        self.assertEqual(json.loads(decode(head)), {'alg': 'EdDSA', 'kid': self.config['credential_id']})
        claims = json.loads(decode(body))
        self.assertEqual(set(claims), {'iss', 'sub', 'iat', 'exp'})
        self.assertEqual(claims['exp'] - claims['iat'], 900)
        self.assertEqual(claims['sub'], self.config['project_id'])
        message, signature, public = [self.directory / name for name in ('message', 'signature', 'public.pem')]
        message.write_bytes((head + '.' + body).encode())
        signature.write_bytes(decode(sig))
        subprocess.run(['openssl', 'pkey', '-in', str(self.key), '-pubout', '-out', str(public)], check=True, capture_output=True)
        subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(public), '-rawin', '-in', str(message), '-sigfile', str(signature)], check=True, capture_output=True)

    def test_qweather_cache_never_uses_open_meteo_cache(self):
        city = {'name': '北京', 'latitude': 39.92, 'longitude': 116.41, 'timezone': 'Asia/Shanghai'}
        with patch.object(backend, 'weather_settings', return_value=self.settings), patch.object(backend, 'get_qweather', return_value={'warning': '', 'provider': 'qweather'}) as fetch:
            self.assertEqual(backend.get_weather(city)['provider'], 'qweather')
            fetch.assert_called_once()

    def test_units_and_missing_history_in_daily_forecast(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        period = {'forecastStartTime': today + 'T07:00+08:00', 'condition': {'text': '晴', 'code': '100'},
                  'wind': {'speed': {'value': 2}}, 'precipitation': {'amount': {'value': 1}, 'probability': 0.3}}
        current = {'temperature': {'value': 20}, 'humidity': 0.5, 'wind': {'speed': {'value': 2}}}
        daily = {'days': [{'daytime': period, 'nighttime': period, 'temperatureMin': {'value': 10}, 'temperatureMax': {'value': 22}}]}
        city = {'timezone': 'Asia/Shanghai'}
        result = backend.normalize_qweather(current, daily, city)
        self.assertEqual(result['current']['humidity'], 50)
        self.assertEqual(result['current']['wind'], 7.2)
        self.assertEqual(result['days'][0]['rainProbability'], 30)
        self.assertEqual(result['days'][0]['rain'], 2)
        self.assertEqual(result['days'][0]['kind'], 'today')
        self.assertEqual(result['days'][0]['icon'], 'sun')


if __name__ == '__main__':
    unittest.main()
