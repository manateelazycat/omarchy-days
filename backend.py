#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

"""JSON bridge for the Omarchy Days widget; networking never runs on the UI thread."""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import os
from pathlib import Path
import re
import site
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "omarchy-days"
RUNTIME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "omarchy-days/venv"
# Keep the virtual environment outside the plugin: Omarchy rejects symlinks
# anywhere inside a plugin directory, including the python symlink in a venv.
runtime_site = RUNTIME / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
if runtime_site.is_dir():
    site.addsitedir(str(runtime_site))


class DataError(Exception):
    pass


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".days-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fetch_json(url: str, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "Omarchy-Days/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise DataError("服务返回的数据过大")
        result = json.loads(content)
        if not isinstance(result, dict) or result.get("error"):
            raise DataError("服务返回无效数据")
        return result
    except urllib.error.HTTPError as exc:
        raise DataError(f"数据服务暂不可用（HTTP {exc.code}）") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DataError("网络连接失败，请稍后重试") from exc
    except (ValueError, UnicodeError) as exc:
        raise DataError("数据服务返回格式错误") from exc


def normalize_query(value: str):
    value = str(value).casefold().replace("ü", "v")
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if c.isalnum() and not unicodedata.combining(c))


def city_catalog():
    data = read_json(ROOT / "data/cities.json")
    return data["cities"] if isinstance(data, dict) else []


def public_city(item):
    return {key: item[key] for key in ("id", "name", "englishName", "admin1", "country", "country_code", "latitude", "longitude", "timezone") if key in item}


def validate_city(item):
    if not isinstance(item, dict) or not str(item.get("name", "")).strip():
        raise DataError("请选择有效的城市")
    try:
        lat, lon = float(item["latitude"]), float(item["longitude"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError
        tz = "Asia/Shanghai" if item.get("country_code") == "CN" else item.get("timezone", "UTC")
        ZoneInfo(tz)
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError("城市坐标或时区无效") from exc
    city = public_city(item)
    city.update(latitude=lat, longitude=lon, timezone=tz)
    return city


def search_cities(query: str, offline=False):
    needle = normalize_query(query)
    if len(needle) < 2:
        return {"ok": True, "results": [], "query": query}
    matches = []
    for item in city_catalog():
        aliases = item.get("aliases", [])
        primary = [normalize_query(item["name"]), normalize_query(item.get("englishName", ""))]
        if needle in primary:
            rank = 0
        elif any(alias.startswith(needle) for alias in primary):
            rank = 1
        elif needle in aliases:
            rank = 2
        elif any(alias.startswith(needle) for alias in aliases):
            rank = 3
        else:
            continue
        matches.append((rank, -item.get("population", 0), item))
    matches.sort(key=lambda match: match[:2])
    if matches or offline:
        return {"ok": True, "results": [public_city(m[2]) for m in matches[:12]], "query": query}
    path = CACHE / ("search-" + hashlib.sha256((query.casefold() + "|en-v1").encode()).hexdigest()[:20] + ".json")
    cached = read_json(path)
    if cached and time.time() - cached.get("savedAt", 0) < 7 * 86400:
        return {"ok": True, "results": cached["results"], "query": query}
    data = fetch_json("https://geocoding-api.open-meteo.com/v1/search", {"name": query.strip(), "count": 12, "language": "en", "format": "json"})
    results = []
    for item in data.get("results", []):
        try:
            item["englishName"] = item.get("name", "")
            results.append(validate_city(item))
        except DataError:
            continue
    atomic_json(path, {"savedAt": time.time(), "results": results})
    return {"ok": True, "results": results, "query": query}


def valid_holidays(data, year):
    if not isinstance(data, dict) or data.get("year") != year or not isinstance(data.get("days"), list) or not data["days"]:
        return False
    seen = set()
    for row in data["days"]:
        try:
            day = date.fromisoformat(row["date"])
            if day.year != year or day.isoformat() in seen or type(row["isOffDay"]) is not bool or not isinstance(row["name"], str):
                return False
            seen.add(day.isoformat())
        except (KeyError, TypeError, ValueError):
            return False
    return True


def holiday_data(year):
    for path in (CACHE / f"holidays-{year}.json", ROOT / f"data/holidays/{year}.json"):
        data = read_json(path)
        if valid_holidays(data, year):
            return data
    return None


def refresh_holidays(year):
    marker = CACHE / f"holidays-{year}-checked.json"
    checked = read_json(marker)
    if checked and time.time() - checked.get("savedAt", 0) < 86400:
        return {"ok": True, "known": holiday_data(year) is not None, "changed": False}
    try:
        data = fetch_json(f"https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json")
        if not valid_holidays(data, year):
            raise DataError("本年度放假调休安排尚未收录")
        changed = data != holiday_data(year)
        atomic_json(CACHE / f"holidays-{year}.json", data)
        atomic_json(marker, {"savedAt": time.time()})
        return {"ok": True, "known": True, "changed": changed}
    except DataError as exc:
        # Retry the next day rather than issuing a request on every click.
        atomic_json(marker, {"savedAt": time.time()})
        return {"ok": False, "known": holiday_data(year) is not None, "changed": False, "error": str(exc)}


def today_info(today=None):
    today = today or date.today()
    try:
        from lunar_python import Solar
    except ImportError as exc:
        raise DataError("农历依赖尚未安装，请运行 bash bootstrap.sh") from exc
    lunar = Solar.fromYmd(today.year, today.month, today.day).getLunar()
    groups = {}
    for year in (today.year, today.year + 1):
        data = holiday_data(year)
        if not data:
            continue
        for row in data["days"]:
            if row["isOffDay"]:
                groups.setdefault((year, row["name"]), {"name": row["name"], "off": []})["off"].append(date.fromisoformat(row["date"]))
    holiday = None
    for group in groups.values():
        group["off"].sort()
        if group["off"][0] <= today <= group["off"][-1]:
            holiday = {"name": group["name"], "state": "during", "days": (group["off"][-1] - today).days}
            break
    if holiday is None:
        upcoming = min((group for group in groups.values() if group["off"][0] > today), key=lambda group: group["off"][0], default=None)
        if upcoming:
            holiday = {"name": upcoming["name"], "state": "until", "days": (upcoming["off"][0] - today).days}
    return {"ok": True, "date": today.isoformat(), "lunar": f"{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
            "lunarYear": f"{lunar.getYearInGanZhi()}年·{lunar.getYearShengXiao()}",
            "weekday": "一二三四五六日"[today.weekday()], "holiday": holiday}


def month_data(year: int, month: int, today=None):
    if not 1901 <= year <= 2099 or not 1 <= month <= 12:
        raise DataError("日历支持 1901—2099 年")
    try:
        from lunar_python import Solar
    except ImportError as exc:
        raise DataError("农历依赖尚未安装，请运行 bash bootstrap.sh") from exc
    today = today or date.today()
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    years = {start.year, (start + timedelta(days=41)).year, year}
    datasets = {y: holiday_data(y) for y in years}
    lookup = {row["date"]: row for data in datasets.values() if data for row in data["days"]}
    cells = []
    for offset in range(42):
        day = start + timedelta(days=offset)
        solar = Solar.fromYmd(day.year, day.month, day.day)
        lunar = solar.getLunar()
        festivals = list(dict.fromkeys(solar.getFestivals() + lunar.getFestivals()))
        term = lunar.getJieQi()
        lunar_month = lunar.getMonthInChinese() + "月"
        lunar_day = lunar.getDayInChinese()
        holiday = lookup.get(day.isoformat())
        status = "off" if holiday and holiday["isOffDay"] else "work" if holiday else "weekend" if day.weekday() >= 5 else "normal"
        cells.append({"date": day.isoformat(), "day": day.day, "weekday": "一二三四五六日"[day.weekday()], "inMonth": day.month == month,
                      "today": day == today, "lunar": lunar_day if lunar.getDay() != 1 else lunar_month,
                      "lunarFull": f"{lunar.getYearInGanZhi()}年 · {lunar.getYearShengXiao()} · {lunar_month}{lunar_day}",
                      "festivals": festivals, "term": term, "label": (festivals[0] if festivals else term or (lunar_month if lunar.getDay() == 1 else lunar_day)),
                      "status": status, "holiday": holiday["name"] if holiday else "", "scheduleKnown": datasets[day.year] is not None})
    data = datasets[year]
    groups = {}
    for row in data["days"] if data else []:
        group = groups.setdefault(row["name"], {"name": row["name"], "off": [], "work": []})
        group["off" if row["isOffDay"] else "work"].append(row["date"])
    holidays = sorted((g for g in groups.values() if any(d.startswith(f"{year}-{month:02d}") for d in g["off"] + g["work"])), key=lambda g: min(g["off"] + g["work"]))
    for group in holidays:
        group["off"].sort()
        group["work"].sort()
    return {"ok": True, "year": year, "month": month, "today": today.isoformat(), "days": cells, "holidays": holidays,
            "scheduleKnown": data is not None, "sources": data.get("papers", []) if data else []}


def locate_city(force=False):
    path = CACHE / "ip-location.json"
    cached = read_json(path)
    if not force and cached and time.time() - cached.get("savedAt", 0) < 6 * 3600:
        return validate_city(cached["city"]), ""
    try:
        data = fetch_json("https://ipwho.is/")
        if data.get("success") is not True or not data.get("city"):
            raise DataError("IP 定位失败，请手动搜索城市")
        item = {"name": data["city"], "admin1": data.get("region", ""), "country": data.get("country", ""), "country_code": data.get("country_code", ""),
                "latitude": data.get("latitude"), "longitude": data.get("longitude"), "timezone": (data.get("timezone") or {}).get("id", "UTC")}
        city = validate_city(item)
        # Localize the IP service's English city label without another request.
        for known in city_catalog():
            if normalize_query(city["name"]) in known.get("aliases", []) and abs(city["latitude"] - known["latitude"]) < 1 and abs(city["longitude"] - known["longitude"]) < 1:
                city.update(name=known["name"], englishName=known.get("englishName", ""), admin1=known["admin1"], country=known["country"])
                break
        atomic_json(path, {"savedAt": time.time(), "city": city})
        return city, ""
    except DataError:
        if cached:
            return validate_city(cached["city"]), "IP 定位暂不可用，沿用上次定位"
        raise


WEATHER = {
    0: ("晴", "sun"), 1: ("晴间多云", "partly"), 2: ("多云", "partly"), 3: ("阴", "cloud"),
    45: ("雾", "fog"), 48: ("冻雾", "fog"), 51: ("小毛毛雨", "rain"), 53: ("毛毛雨", "rain"), 55: ("大毛毛雨", "rain"),
    56: ("冻毛毛雨", "rain"), 57: ("强冻毛毛雨", "rain"), 61: ("小雨", "rain"), 63: ("中雨", "rain"), 65: ("大雨", "rain"),
    66: ("冻雨", "rain"), 67: ("强冻雨", "rain"), 71: ("小雪", "snow"), 73: ("中雪", "snow"), 75: ("大雪", "snow"), 77: ("雪粒", "snow"),
    80: ("小阵雨", "rain"), 81: ("阵雨", "rain"), 82: ("强阵雨", "rain"), 85: ("小阵雪", "snow"), 86: ("强阵雪", "snow"),
    95: ("雷阵雨", "storm"), 96: ("雷雨伴冰雹", "storm"), 99: ("强雷雨伴冰雹", "storm")}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def weather_description(code):
    return WEATHER.get(code, ("暂无数据", "unknown"))


def normalize_weather(data, city, now=None):
    now = now or datetime.now(ZoneInfo(city["timezone"]))
    today = now.astimezone(ZoneInfo(city["timezone"])).date()
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    indexes = {key: i for i, key in enumerate(times)}

    def value(key, index):
        values = daily.get(key) or []
        return number(values[index]) if index is not None and index < len(values) else None

    rows = []
    for offset in range(-1, 6):
        day = today + timedelta(days=offset)
        index = indexes.get(day.isoformat())
        code = value("weather_code", index)
        description, icon = weather_description(code)
        rows.append({"date": day.isoformat(), "label": "昨天" if offset == -1 else "今天" if offset == 0 else "明天" if offset == 1 else "周" + "一二三四五六日"[day.weekday()],
                     "kind": "history" if offset == -1 else "today" if offset == 0 else "forecast", "description": description, "icon": icon,
                     "min": value("temperature_2m_min", index), "max": value("temperature_2m_max", index),
                     "rain": value("precipitation_sum", index), "rainProbability": value("precipitation_probability_max", index), "wind": value("wind_speed_10m_max", index)})
    current = data.get("current") or {}
    if not str(current.get("time", "")).startswith(today.isoformat()):
        current = {}
    description, icon = weather_description(current.get("weather_code"))
    return {"ok": True, "city": city, "today": today.isoformat(), "days": rows, "current": {
        "temperature": number(current.get("temperature_2m")), "feelsLike": number(current.get("apparent_temperature")),
        "humidity": number(current.get("relative_humidity_2m")), "wind": number(current.get("wind_speed_10m")), "description": description, "icon": icon},
        "timezone": city["timezone"]}


def get_weather(city=None, force=False):
    warning = ""
    if city is None:
        city, warning = locate_city(force)
    else:
        city = validate_city(city)
    key = hashlib.sha256(f"{city['latitude']:.5f},{city['longitude']:.5f},{city['timezone']}".encode()).hexdigest()[:20]
    path = CACHE / f"weather-{key}.json"
    cached = read_json(path)
    now = datetime.now(ZoneInfo(city["timezone"]))
    same_day = cached and cached.get("day") == now.date().isoformat()
    fresh = same_day and time.time() - cached.get("savedAt", 0) < 15 * 60
    stale = False
    if not force and fresh:
        data = cached["data"]
        saved_at = cached["savedAt"]
    else:
        try:
            data = fetch_json("https://api.open-meteo.com/v1/forecast", {
                "latitude": city["latitude"], "longitude": city["longitude"], "timezone": city["timezone"],
                "past_days": 1, "forecast_days": 6, "temperature_unit": "celsius", "wind_speed_unit": "kmh",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"})
            if not isinstance(data.get("daily", {}).get("time"), list) or not data["daily"]["time"]:
                raise DataError("天气服务返回了空数据")
            saved_at = time.time()
            atomic_json(path, {"savedAt": saved_at, "day": now.date().isoformat(), "data": data})
        except DataError as exc:
            if not cached or time.time() - cached.get("savedAt", 0) > 48 * 3600:
                return {"ok": False, "error": str(exc), "city": city}
            data, saved_at, stale = cached["data"], cached["savedAt"], True
            warning = "网络暂不可用，显示上次缓存的天气"
    result = normalize_weather(data, city, now)
    result.update(stale=stale, warning=warning, updatedAt=datetime.fromtimestamp(saved_at, ZoneInfo(city["timezone"])).isoformat(timespec="minutes"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    month = commands.add_parser("month")
    month.add_argument("--year", type=int, required=True)
    month.add_argument("--month", type=int, required=True)
    holiday = commands.add_parser("holidays")
    holiday.add_argument("--year", type=int, required=True)
    today_cmd = commands.add_parser("today")
    search = commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--offline", action="store_true")
    weather = commands.add_parser("weather")
    weather.add_argument("--city", help="JSON city selected from search results")
    weather.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "month":
            result = month_data(args.year, args.month)
        elif args.command == "holidays":
            if not 1901 <= args.year <= 2099:
                raise DataError("年份超出支持范围")
            result = refresh_holidays(args.year)
        elif args.command == "today":
            result = today_info()
        elif args.command == "search":
            result = search_cities(args.query[:120], args.offline)
        else:
            result = get_weather(json.loads(args.city) if args.city else None, args.force)
    except (DataError, ValueError, KeyError, TypeError, OSError) as exc:
        result = {"ok": False, "error": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
