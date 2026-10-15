# SPDX-License-Identifier: GPL-3.0-only
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import backend


class LocationSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = dict(api_host='example.re.qweatherapi.com', project_id='project', credential_id='credential')
        for name, value in [('CACHE', Path(self.temp.name)), ('weather_settings', None), ('validate_qweather', None), ('qweather_token', None)]:
            kwargs = {} if name == 'CACHE' else {'return_value': {'provider': 'qweather', 'qweather': self.config} if name == 'weather_settings' else self.config if name == 'validate_qweather' else 'test-token'}
            p = patch.object(backend, name, value) if name == 'CACHE' else patch.object(backend, name, **kwargs)
            p.start(); self.addCleanup(p.stop)

    def test_other_source_and_offline_do_not_call_poi(self):
        with patch.object(backend, 'weather_settings', return_value={'provider': 'open-meteo'}), patch.object(backend, 'search_cities', return_value={'results': []}) as cities, patch.object(backend, 'fetch_json') as fetch:
            backend.search_locations('上海')
            backend.search_locations('上海', offline=True)
            self.assertEqual(cities.call_count, 2)
            fetch.assert_not_called()

    def test_poi_city_and_precise_coordinates_survive_validation_and_cache(self):
        def response(url, params, headers):
            self.assertEqual(headers, {'Authorization': 'Bearer test-token'})
            if params.get('type') != 'scenic':
                raise backend.LocationNotFound('no match')
            return {'code': '200', 'poi': [{'id': 'poi-1', 'name': '岳麓山', 'adm2': '长沙', 'adm1': '湖南',
                'country': '中国', 'lat': '28.18001', 'lon': '112.93002', 'tz': 'Asia/Shanghai'}]}
        with patch.object(backend, 'fetch_json', side_effect=response) as fetch:
            result = backend.search_locations('岳麓山')
            self.assertEqual(fetch.call_count, 3)
            again = backend.search_locations('岳麓山')
            self.assertEqual(fetch.call_count, 3)
        place = backend.validate_city(result['results'][0])
        self.assertEqual(place['cityName'], '长沙')
        self.assertEqual(place['kind'], 'poi')
        self.assertEqual(place['latitude'], 28.18001)
        self.assertEqual(place['longitude'], 112.93002)
        self.assertEqual(result['results'], again['results'])

    def test_no_matching_residential_location_is_not_a_service_error(self):
        with patch.object(backend, 'fetch_json', side_effect=backend.LocationNotFound('no match')):
            self.assertEqual(backend.search_locations('未收录的小区')['results'], [])

    def test_auth_failure_is_not_reported_as_no_results(self):
        with patch.object(backend, 'fetch_json', side_effect=backend.DataError('HTTP 401')):
            result = backend.search_locations('岳麓山')
            self.assertFalse(result['ok'])
            self.assertIn('401', result['error'])

    def test_structured_http_no_such_location(self):
        body = json.dumps({'error': {'type': 'https://dev.qweather.com/docs/resource/error-code/#no-such-location'}}).encode()
        error = urllib.error.HTTPError('https://example.test', 400, 'Bad Request', {}, io.BytesIO(body))
        self.addCleanup(error.close)
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(backend.LocationNotFound):
                backend.fetch_json('https://example.test')
