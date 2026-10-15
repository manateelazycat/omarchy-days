from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import backend


class CustomLocationTests(unittest.TestCase):
    def setUp(self):
        self.location = dict(enabled=True, name='家', longitude='114.305123', latitude='30.592456')
        self.settings = dict(provider='qweather', qweather={}, customLocation=self.location)

    def test_coordinates_and_boundaries(self):
        result = backend.validate_custom_location(self.location)
        self.assertEqual(result['longitude'], 114.305123)
        self.assertEqual(result['latitude'], 30.592456)
        for lon, lat in [('180', '90'), ('-180', '-90'), ('0', '0')]:
            backend.validate_custom_location(dict(self.location, longitude=lon, latitude=lat))

    def test_invalid_input_is_rejected(self):
        for change in [dict(name=' '), dict(name='x\ny'), dict(latitude='90.01'), dict(longitude='-180.1'),
                       dict(latitude='nan'), dict(longitude='1e2'), dict(latitude='30,5'), dict(latitude=''), dict(longitude=True)]:
            with self.subTest(change=change), self.assertRaises(backend.DataError):
                backend.validate_custom_location(dict(self.location, **change))

    def test_weather_uses_fixed_coordinates_over_manual_and_ip(self):
        with patch.object(backend, 'weather_settings', return_value=self.settings), \
                patch.object(backend, 'get_qweather', return_value={'warning': ''}) as fetch, \
                patch.object(backend, 'locate_city') as locate:
            for selected in [None, dict(name='天津', latitude=39, longitude=117, timezone='Asia/Shanghai')]:
                backend._get_weather(selected)
                city = fetch.call_args.args[0]
                self.assertEqual(city['name'], '家')
                self.assertEqual(city['latitude'], 30.592456)
                self.assertEqual(city['longitude'], 114.305123)
            locate.assert_not_called()

    def test_alerts_use_same_fixed_coordinates(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(backend, 'CACHE', Path(directory)), \
                patch.object(backend, 'weather_settings', return_value=self.settings), \
                patch.object(backend, 'validate_qweather', return_value={'api_host': 'example.re.qweatherapi.com'}), \
                patch.object(backend, 'qweather_token', return_value='test'), \
                patch.object(backend, 'fetch_json', return_value={'alerts': []}) as fetch, \
                patch.object(backend, 'locate_city') as locate:
            result = backend.get_alerts(dict(name='天津', latitude=39, longitude=117, timezone='Asia/Shanghai'))
            self.assertEqual(result['city']['name'], '家')
            self.assertIn('/30.59/114.31', fetch.call_args.args[0])
            locate.assert_not_called()

    def test_provider_gating_and_disabled_location(self):
        self.assertIsNone(backend.custom_city(dict(self.settings, provider='open-meteo')))
        self.assertIsNone(backend.custom_city(dict(self.settings, customLocation={'enabled': False})))

    def test_save_validation_does_not_overwrite_previous(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, 'WEATHER_SETTINGS', Path(directory)/'weather.json'), \
                patch.object(backend, 'fetch_qweather') as fetch:
            backend.atomic_json(backend.WEATHER_SETTINGS, dict(provider='qweather', qweather={}))
            backend.configure_weather('save', self.settings)
            self.assertEqual(backend.weather_settings()['customLocation']['latitude'], 30.592456)
            with self.assertRaises(backend.DataError):
                backend.configure_weather('save', dict(self.settings, customLocation=dict(self.location, latitude='bad')))
            self.assertEqual(backend.weather_settings()['customLocation']['latitude'], 30.592456)
            fetch.assert_not_called()
