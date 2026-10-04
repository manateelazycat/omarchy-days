# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend


class CalendarTests(unittest.TestCase):
    def day(self, year, month, day):
        return next(d for d in backend.month_data(year, month, today=date(year, month, day))["days"] if d["date"] == f"{year}-{month:02d}-{day:02d}")

    def test_chinese_new_year_and_leap_month(self):
        self.assertIn("正月初一", self.day(2026, 2, 17)["lunarFull"])
        self.assertIn("春节", self.day(2026, 2, 17)["festivals"])
        leap = self.day(2025, 7, 25)
        self.assertEqual(leap["lunar"], "闰六月")
        self.assertNotIn("闰闰", leap["lunarFull"])

    def test_holiday_makeup_work_overrides_weekend(self):
        self.assertEqual(self.day(2026, 10, 1)["status"], "off")
        work = self.day(2026, 10, 10)
        self.assertEqual(work["weekday"], "六")
        self.assertEqual(work["status"], "work")
        group = backend.month_data(2026, 10)["holidays"][0]
        self.assertEqual(len(group["off"]), 7)
        self.assertEqual(group["work"], ["2026-09-20", "2026-10-10"])

    def test_month_grid_covers_year_boundary(self):
        result = backend.month_data(2026, 12)
        self.assertEqual(len(result["days"]), 42)
        self.assertEqual(result["days"][0]["weekday"], "一")
        self.assertEqual(result["days"][-1]["date"], "2027-01-10")

    def test_unknown_schedule_is_not_guessed(self):
        result = backend.month_data(2099, 10)
        self.assertFalse(result["scheduleKnown"])
        self.assertEqual(result["holidays"], [])
        self.assertFalse(any(d["status"] in ("off", "work") for d in result["days"]))


class CityTests(unittest.TestCase):
    def test_english_pinyin_prefix_spaces_and_alias(self):
        for query, expected in [("shang", "上海"), ("SHANG HAI", "上海"), ("Peking", "北京"), ("Chongqing", "重庆"), ("xi'an", "西安")]:
            with self.subTest(query=query):
                self.assertEqual(backend.search_cities(query, offline=True)["results"][0]["name"], expected)

    def test_same_pinyin_keeps_distinct_names_and_provinces(self):
        results = backend.search_cities("suzhou", offline=True)["results"]
        self.assertTrue(any(c["name"] == "苏州" and c["admin1"] == "江苏省" for c in results))
        self.assertTrue(any("宿州" in c["name"] and c["admin1"] == "安徽省" for c in results))

    def test_invalid_coordinates_rejected(self):
        for value in [float("nan"), float("inf"), 200, None]:
            with self.assertRaises(backend.DataError):
                backend.validate_city({"name": "test", "latitude": value, "longitude": 0, "timezone": "UTC"})


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.city = backend.validate_city(backend.search_cities("Beijing", offline=True)["results"][0])
        self.temp = tempfile.TemporaryDirectory()
        self.cache_patch = patch.object(backend, "CACHE", Path(self.temp.name))
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        self.temp.cleanup()

    def fixture(self):
        today = datetime.now(ZoneInfo(self.city["timezone"])).date()
        from datetime import timedelta
        days = [(today + timedelta(days=i)).isoformat() for i in range(-1, 6)]
        return {"daily": {"time": days, "weather_code": [0] * 7, "temperature_2m_min": [10] * 7, "temperature_2m_max": [20] * 7}, "current": {"time": today.isoformat() + "T12:00", "temperature_2m": 18, "weather_code": 0}}

    def test_exactly_seven_days_around_city_local_today(self):
        data = {"daily": {"time": ["2026-12-31", "2027-01-01"], "weather_code": [61, 0], "temperature_2m_min": [None, 0]}}
        result = backend.normalize_weather(data, self.city, datetime(2026, 12, 31, 20, tzinfo=ZoneInfo("UTC")))
        self.assertEqual(result["today"], "2027-01-01")
        self.assertEqual([d["date"] for d in result["days"]], ["2026-12-31"] + [f"2027-01-{d:02d}" for d in range(1, 7)])
        self.assertEqual([d["kind"] for d in result["days"]], ["history", "today"] + ["forecast"] * 5)
        self.assertIsNone(result["days"][0]["min"])
        self.assertEqual(result["days"][1]["min"], 0)
        self.assertIsNone(result["days"][-1]["max"])

    def test_request_and_cache_and_stale_fallback(self):
        with patch.object(backend, "fetch_json", return_value=self.fixture()) as fetch:
            result = backend.get_weather(self.city)
            params = fetch.call_args.args[1]
            self.assertEqual(params["past_days"], 1)
            self.assertEqual(params["forecast_days"], 6)
            self.assertEqual(params["timezone"], "Asia/Shanghai")
            self.assertEqual(len(result["days"]), 7)
        with patch.object(backend, "fetch_json", side_effect=backend.DataError("offline")) as fetch:
            cached = backend.get_weather(self.city)
            fetch.assert_not_called()
            self.assertFalse(cached["stale"])
            stale = backend.get_weather(self.city, force=True)
            self.assertTrue(stale["stale"])
            self.assertIn("缓存", stale["warning"])

    def test_network_failure_never_shows_another_city(self):
        with patch.object(backend, "fetch_json", return_value=self.fixture()):
            backend.get_weather(self.city)
        other = backend.search_cities("Shanghai", offline=True)["results"][0]
        with patch.object(backend, "fetch_json", side_effect=backend.DataError("offline")):
            result = backend.get_weather(other)
            self.assertFalse(result["ok"])
            self.assertEqual(result["city"]["name"], "上海")
            self.assertNotIn("days", result)


if __name__ == "__main__":
    unittest.main()
