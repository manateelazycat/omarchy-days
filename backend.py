#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

"""JSON bridge for the Omarchy Days widget; networking never runs on the UI thread."""
from __future__ import annotations

import argparse
import base64
import gzip
import fcntl
from concurrent.futures import ThreadPoolExecutor
import calendar
from functools import partial
import hashlib
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import site
import socket
import sys
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "omarchy-days"
WEATHER_SETTINGS = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarchy-days/weather.json"
RUNTIME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "omarchy-days/venv"
NETWORK_IDLE_TIMEOUT = 8
NETWORK_TOTAL_TIMEOUT = 20
JSON_MAX_BYTES = 2_000_000
GZIP_MAX_BYTES = 4_000_000
TEXT_MAX_BYTES = 200_000
# Keep the virtual environment outside the plugin: Omarchy rejects symlinks
# anywhere inside a plugin directory, including the python symlink in a venv.
runtime_site = RUNTIME / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
if runtime_site.is_dir():
    site.addsitedir(str(runtime_site))


class DataError(Exception):
    pass


class LocationNotFound(DataError):
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


class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DataError("天气认证请求被重定向，请检查 API Host")


class RequestDeadline:
    """Interrupt socket reads, including HTTP headers and chunk framing.

    A timer shuts down the sockets rather than closing a buffered reader from
    another thread (which can wait for its read lock). DNS and connection setup
    are also covered by the outer QML process watchdog.
    """
    def __init__(self):
        self.expires = time.monotonic() + NETWORK_TOTAL_TIMEOUT
        self.sockets = []
        self.lock = threading.Lock()
        self.timer = threading.Timer(NETWORK_TOTAL_TIMEOUT, self.interrupt)
        self.timer.daemon = True

    def __enter__(self):
        self.timer.start()
        return self

    def __exit__(self, *args):
        self.timer.cancel()
        self.timer.join()

    def check(self):
        if time.monotonic() >= self.expires:
            raise DataError("网络请求超时，请稍后重试")

    def interrupt(self):
        with self.lock:
            for sock in self.sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # Completed responses may already have closed sockets.

    def response(self, sock, *args, **kwargs):
        with self.lock:
            self.check()
            self.sockets.append(sock)
        return http.client.HTTPResponse(sock, *args, **kwargs)

    def connection(self, connection_type, *args, **kwargs):
        self.check()
        connection = connection_type(*args, **kwargs)
        connection.response_class = self.response
        return connection


class DeadlineHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, deadline):
        super().__init__()
        self.deadline = deadline

    def http_open(self, request):
        return self.do_open(partial(self.deadline.connection, http.client.HTTPConnection), request)


class DeadlineHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, deadline):
        super().__init__()
        self.deadline = deadline

    def https_open(self, request):
        return self.do_open(partial(self.deadline.connection, http.client.HTTPSConnection), request,
                            context=self._context)


def response_opener(deadline, authenticated=False):
    handlers = [DeadlineHTTPHandler(deadline), DeadlineHTTPSHandler(deadline)]
    if authenticated:
        handlers.append(NoAuthRedirect())
    return urllib.request.build_opener(*handlers)


def read_response(response, deadline, limit):
    compressed = response.headers.get("Content-Encoding", "").strip().lower() == "gzip"
    input_limit = GZIP_MAX_BYTES if compressed else limit
    content = bytearray()
    read = getattr(response, "read1", response.read)
    try:
        while len(content) <= input_limit:
            deadline.check()
            chunk = read(min(65_536, input_limit + 1 - len(content)))
            deadline.check()
            if not chunk:
                break
            content.extend(chunk)
    except (OSError, http.client.HTTPException):
        deadline.check()
        raise
    if len(content) > input_limit:
        raise DataError("服务返回的数据过大")
    if compressed:
        # The decompressor only sees finite in-memory input. Empty gzip members
        # therefore consume the input budget even when they produce no output.
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                content = stream.read(limit + 1)
        except (OSError, EOFError, zlib.error) as exc:
            raise DataError("数据服务返回格式错误") from exc
    deadline.check()
    if len(content) > limit:
        raise DataError("服务返回的数据过大")
    return bytes(content)


def fetch_json(url: str, params=None, headers=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "Omarchy-Days/0.1", "Accept": "application/json", **(headers or {})})
    with RequestDeadline() as deadline:
        try:
            opener = response_opener(deadline, authenticated=bool(headers))
            with opener.open(request, timeout=NETWORK_IDLE_TIMEOUT) as response:
                content = read_response(response, deadline, JSON_MAX_BYTES)
            result = json.loads(content)
            if not isinstance(result, dict) or result.get("error"):
                raise DataError("服务返回无效数据")
            return result
        except urllib.error.HTTPError as exc:
            with exc:
                if exc.code == 400:
                    try:
                        detail = json.loads(read_response(exc, deadline, 16_384))
                        error = detail.get("error") if isinstance(detail, dict) else None
                        if isinstance(error, dict) and str(error.get("type", "")).endswith("#no-such-location"):
                            raise LocationNotFound("没有匹配的地点") from exc
                    except (ValueError, OSError, http.client.HTTPException):
                        deadline.check()
            raise DataError(f"数据服务暂不可用（HTTP {exc.code}）") from exc
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            deadline.check()
            raise DataError("网络连接失败，请稍后重试") from exc
        except (ValueError, UnicodeError) as exc:
            raise DataError("数据服务返回格式错误") from exc


def fetch_text(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Omarchy-Days/0.1", "Accept": "text/plain"})
    with RequestDeadline() as deadline:
        try:
            with response_opener(deadline).open(request, timeout=NETWORK_IDLE_TIMEOUT) as response:
                content = read_response(response, deadline, TEXT_MAX_BYTES)
            return content.decode("utf-8")
        except urllib.error.HTTPError as exc:
            exc.close()
            raise DataError(f"数据服务暂不可用（HTTP {exc.code}）") from exc
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            deadline.check()
            raise DataError("网络连接失败，请稍后重试") from exc
        except UnicodeError as exc:
            raise DataError("数据服务返回格式错误") from exc


def normalize_query(value: str):
    value = str(value).casefold().replace("ü", "v")
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if c.isalnum() and not unicodedata.combining(c))


def city_catalog():
    data = read_json(ROOT / "data/cities.json")
    return data["cities"] if isinstance(data, dict) else []


def public_city(item):
    return {key: item[key] for key in ("id", "name", "englishName", "admin1", "country", "country_code", "latitude", "longitude", "timezone", "cityName", "kind", "source") if key in item}


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


def search_locations(query, offline=False):
    if offline:
        return search_cities(query, True)
    settings = weather_settings()
    if settings["provider"] != "qweather":
        return search_cities(query)
    query = query.strip()[:120]
    if len(query) < 2:
        return {"ok": True, "query": query, "results": []}
    config = validate_qweather(settings["qweather"])
    identity = json.dumps([config["api_host"], config["project_id"], config["credential_id"], query], ensure_ascii=False)
    path = CACHE / ("poi-search-" + hashlib.sha256(identity.encode()).hexdigest()[:20] + ".json")
    cached = read_json(path)
    if cached and time.time() - cached.get("savedAt", 0) < 3600:
        return {"ok": True, "query": query, "results": cached["results"]}
    token = qweather_token(config)

    def lookup(product, kind=None):
        params = {"location": query, "lang": "zh", "number": 12}
        if kind:
            params["type"] = kind
        try:
            data = fetch_json(f"https://{config['api_host']}/geo/v2/{product}/lookup", params,
                              {"Authorization": "Bearer " + token})
        except LocationNotFound:
            return []
        if data.get("code") == "404":
            return []
        if data.get("code") != "200":
            raise DataError(f"和风地点搜索失败（{data.get('code', '无状态码')}）")
        results = []
        for item in data.get("poi" if product == "poi" else "location", []):
            try:
                results.append(validate_city({"id": item["id"], "name": item["name"],
                    "latitude": item["lat"], "longitude": item["lon"], "timezone": item["tz"],
                    "cityName": item.get("adm2", ""), "admin1": item.get("adm1", ""), "country": item.get("country", ""),
                    "kind": "poi" if product == "poi" else "city", "source": "qweather"}))
            except (KeyError, DataError):
                continue
        return results

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        requests = [pool.submit(lookup, "poi", "scenic"), pool.submit(lookup, "poi", "TSTA"), pool.submit(lookup, "city")]
        for request in requests:
            try:
                results.extend(request.result())
            except DataError as exc:
                errors.append(str(exc))
    unique = {item["id"]: item for item in results}
    results = list(unique.values())[:20]
    if errors:
        return {"ok": bool(results), "query": query, "results": results, "error": "；".join(dict.fromkeys(errors))}
    atomic_json(path, {"savedAt": time.time(), "results": results})
    return {"ok": True, "query": query, "results": results}


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


def parse_ipip_location(text: str):
    match = re.search(r"来自于[：:]\s*(.+?)\s*$", text.strip())
    if not match:
        raise DataError("IP 定位失败，请手动搜索城市")
    return [part for part in re.split(r"[\s\u3000]+", match.group(1)) if part]


def resolve_ipip_city(parts):
    # myip.ipip.net reports "中国 江苏 苏州 联通": walk backwards past the ISP
    # label to the first part that names a catalog city, preferring province hints.
    catalog = city_catalog()
    for index in range(len(parts) - 1, -1, -1):
        candidates = [item for item in catalog if item.get("name") == parts[index]]
        if not candidates:
            continue
        context = "".join(parts[:index])
        candidates.sort(key=lambda item: (0 if item.get("admin1", "")[:2] and item["admin1"][:2] in context else 1, -item.get("population", 0)))
        return validate_city(candidates[0])
    return None


def locate_via_ipip():
    # Return a catalog city from myip.ipip.net, or None when the service is
    # unreachable or reports a location outside mainland China.
    try:
        parts = parse_ipip_location(fetch_text("https://myip.ipip.net/"))
    except DataError:
        return None
    if not parts or parts[0] != "中国":
        return None
    return resolve_ipip_city(parts)


def nearest_catalog_city(latitude, longitude, tolerance=0.25):
    best = None
    for item in city_catalog():
        if abs(item["latitude"] - latitude) <= tolerance and abs(item["longitude"] - longitude) <= tolerance:
            if best is None or item.get("population", 0) > best.get("population", 0):
                best = item
    return best


def geocoding_timezone(name, latitude, longitude):
    data = fetch_json("https://geocoding-api.open-meteo.com/v1/search", {"name": name, "count": 10, "language": "en", "format": "json"})
    best = None
    for item in data.get("results", []):
        try:
            distance = max(abs(float(item["latitude"]) - latitude), abs(float(item["longitude"]) - longitude))
        except (KeyError, TypeError, ValueError):
            continue
        if distance <= 1 and (best is None or distance < best[0]):
            best = (distance, item)
    return best[1].get("timezone") if best else None


def locate_via_myip_la():
    # myip.la answers in English with string coordinates and no timezone.
    data = fetch_json("https://api.myip.la/en?json")
    location = data.get("location") or {}
    name = str(location.get("city") or "").strip()
    if not name:
        raise DataError("IP 定位失败，请手动搜索城市")
    try:
        lat, lon = float(location["latitude"]), float(location["longitude"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError("IP 定位失败，请手动搜索城市") from exc
    known = nearest_catalog_city(lat, lon)
    if known:
        # Coordinates inside the catalog give the localized name and timezone.
        return validate_city(known)
    item = {"name": name, "englishName": name, "admin1": location.get("province", ""), "country": location.get("country_name", ""),
            "country_code": location.get("country_code", ""), "latitude": lat, "longitude": lon}
    try:
        timezone = location.get("timezone") or geocoding_timezone(name, lat, lon)
    except DataError:
        timezone = None
    if timezone:
        item["timezone"] = timezone
    return validate_city(item)


def locate_city(force=False):
    path = CACHE / "ip-location.json"
    cached = read_json(path)
    if not force and cached and cached.get("source") == "ipip" and time.time() - cached.get("savedAt", 0) < 6 * 3600:
        return validate_city(cached["city"]), ""
    try:
        city = locate_via_ipip()
        if city is None:
            # ipip.net failed or reported an overseas location: recheck with myip.la.
            city = locate_via_myip_la()
        atomic_json(path, {"savedAt": time.time(), "source": "ipip", "city": city})
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


def weather_settings():
    saved = read_json(WEATHER_SETTINGS)
    if saved is None and WEATHER_SETTINGS.exists():
        raise DataError("无法读取天气配置，请检查配置文件")
    if saved is not None:
        if not isinstance(saved, dict) or saved.get("provider") not in ("open-meteo", "qweather"):
            raise DataError("天气配置无效，请重新配置")
        return {**saved, "notifications": saved.get("notifications", True) is not False}
    # Local development credentials are only suggestions, never auto-enabled.
    local = read_json(ROOT / "data/qweather/config.json") or {}
    return {"provider": "open-meteo", "notifications": True, "qweather": {
        **{key: local.get(key, "") for key in ("api_host", "developer_id", "project_id", "credential_id")},
        "private_key_path": local.get("private_key_path", str(ROOT / "data/qweather/ed25519-private.pem"))}}


def validate_qweather(config):
    if not isinstance(config, dict):
        raise DataError("请填写和风天气参数")
    result = {key: str(config.get(key, "")).strip() for key in
              ("api_host", "developer_id", "project_id", "credential_id", "private_key_path")}
    host = result["api_host"].removeprefix("https://").rstrip("/").lower()
    if not re.fullmatch(r"[a-z0-9-]+(?:\.re)?\.qweatherapi\.com", host):
        raise DataError("API Host 应为控制台中的 qweatherapi.com 域名，不包含路径")
    result["api_host"] = host
    for key, label in (("developer_id", "开发者 ID"), ("project_id", "项目 ID"), ("credential_id", "凭据 ID")):
        if not re.fullmatch(r"[A-Za-z0-9]{10}", result[key]):
            raise DataError(f"{label} 应为 10 位字母或数字")
    path = Path(result["private_key_path"]).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise DataError("请填写可读取的私钥文件绝对路径")
    result["private_key_path"] = str(path)
    return result


def qweather_token(config):
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
    now = int(time.time())
    parts = ({"alg": "EdDSA", "kid": config["credential_id"]},
             {"iss": config["developer_id"], "sub": config["project_id"], "iat": now - 30, "exp": now + 870})
    message = ".".join(encode(json.dumps(part, separators=(",", ":")).encode()) for part in parts)
    try:
        public = subprocess.run(["openssl", "pkey", "-in", config["private_key_path"], "-pubout", "-outform", "DER"],
                                capture_output=True, timeout=5, check=True)
        if len(public.stdout) != 44 or not public.stdout.startswith(bytes.fromhex("302a300506032b6570032100")):
            raise DataError("私钥必须使用 Ed25519 算法")
        # pkeyutl needs a regular input file for Ed25519 on OpenSSL 3.
        with tempfile.TemporaryDirectory(prefix="days-jwt-") as directory:
            source = Path(directory) / "message"
            source.write_bytes(message.encode("ascii"))
            signed = subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", config["private_key_path"],
                                     "-in", str(source)], capture_output=True, timeout=5, check=True)
        if len(signed.stdout) != 64:
            raise DataError("私钥必须使用 Ed25519 算法")
    except (OSError, subprocess.SubprocessError) as exc:
        raise DataError("JWT 签名失败，请检查 Ed25519 私钥文件和 OpenSSL 3 安装") from exc
    return message + "." + encode(signed.stdout)


def qweather_request(config, token, product, city, **params):
    coordinates = f"{city['latitude']:.2f}/{city['longitude']:.2f}"
    return fetch_json(f"https://{config['api_host']}/weather/v1/{product}/{coordinates}",
                      {"lang": "zh", "localTime": "true", **params}, {"Authorization": "Bearer " + token})


def qweather_icon(condition):
    code = int(condition.get("code", "999"))
    if code in (100, 150):
        return "sun"
    if code in (101, 102, 103, 151, 152, 153):
        return "partly"
    if code == 104:
        return "cloud"
    if code in (302, 303, 304):
        return "storm"
    if 300 <= code < 400:
        return "rain"
    if 400 <= code < 500:
        return "snow"
    if 500 <= code < 600:
        return "fog"
    return "unknown"


def qvalue(data, key):
    value = data.get(key) or {}
    return number(value.get("value")) if isinstance(value, dict) else None


def normalize_qweather(current, daily, city):
    if qvalue(current, "temperature") is None or not isinstance(daily.get("days"), list) or not daily["days"]:
        raise DataError("和风天气返回了空数据或格式不正确")
    today = datetime.now(ZoneInfo(city["timezone"])).date()
    rows = []
    for item in daily["days"]:
        # Daily intervals start at 06:00 local time; daytime starts at 07:00.
        daytime = item.get("daytime") or {}
        day = datetime.fromisoformat(daytime["forecastStartTime"].replace("Z", "+00:00")).astimezone(ZoneInfo(city["timezone"])).date()
        if day < today:
            continue
        condition = daytime.get("condition") or {}
        night = item.get("nighttime") or {}
        amounts = [qvalue(period.get("precipitation") or {}, "amount") for period in (daytime, night)]
        probabilities = [number((period.get("precipitation") or {}).get("probability")) for period in (daytime, night)]
        winds = [qvalue(period.get("wind") or {}, "speed") for period in (daytime, night)]
        offset = (day - today).days
        rows.append({"date": day.isoformat(), "label": "今天" if offset == 0 else "明天" if offset == 1 else "周" + "一二三四五六日"[day.weekday()],
                     "kind": "today" if offset == 0 else "forecast", "description": condition.get("text", "暂无数据"), "icon": qweather_icon(condition),
                     "min": qvalue(item, "temperatureMin"), "max": qvalue(item, "temperatureMax"),
                     "rain": sum(amounts) if all(value is not None for value in amounts) else None,
                     "rainProbability": max(probabilities) * 100 if all(value is not None for value in probabilities) else None,
                     "wind": max(winds) * 3.6 if all(value is not None for value in winds) else None})
    if not rows:
        raise DataError("和风天气未返回当前日期的预报")
    condition = current.get("condition") or {}
    humidity = number(current.get("humidity"))
    wind = qvalue(current.get("wind") or {}, "speed")
    return {"ok": True, "provider": "qweather", "city": city, "today": today.isoformat(), "timezone": city["timezone"], "days": rows,
            "current": {"temperature": qvalue(current, "temperature"), "feelsLike": qvalue(current, "feelsLike"),
                        "humidity": humidity * 100 if humidity is not None else None, "wind": wind * 3.6 if wind is not None else None,
                        "description": condition.get("text", "暂无数据"), "icon": qweather_icon(condition)}}


def normalize_precise_weather(hourly, minutely, city, now=None):
    now = now or datetime.now(ZoneInfo(city["timezone"]))
    hours = []
    for item in hourly.get("hours", []):
        stamp = datetime.fromisoformat(item["forecastTime"].replace("Z", "+00:00"))
        if stamp < now:
            continue
        if qvalue(item, "temperature") is None:
            raise DataError("和风逐小时温度数据不完整")
        precipitation = item.get("precipitation") or {}
        condition = item.get("condition") or {}
        hours.append({"time": stamp.isoformat(), "label": stamp.astimezone(ZoneInfo(city["timezone"])).strftime("%H:%M"),
                      "temperature": qvalue(item, "temperature"), "icon": qweather_icon(condition),
                      "description": condition.get("text", ""), "rain": qvalue(precipitation, "amount"),
                      "probability": (number(precipitation.get("probability")) or 0) * 100})
    points = []
    if minutely.get("code") != "200":
        raise DataError("和风分钟降水预报不可用")
    for item in minutely.get("minutely", []):
        stamp = datetime.fromisoformat(item["fxTime"].replace("Z", "+00:00"))
        amount = number(float(item["precip"]))
        if amount is None or amount < 0:
            raise DataError("和风分钟降水数据不完整")
        if stamp + timedelta(minutes=5) > now:
            points.append({"time": stamp.isoformat(), "amount": amount, "type": item.get("type", "rain")})
    if not hours or len(points) < 2:
        raise DataError("和风分时或分钟降水预报已过期")
    wet = points[0]["amount"] > 0
    transition = next((point for point in points[1:] if (point["amount"] > 0) != wet), None)
    kind = "雪" if (points[0] if wet else transition or {}).get("type") == "snow" else "雨"
    if transition:
        at = datetime.fromisoformat(transition["time"]).astimezone(ZoneInfo(city["timezone"])).strftime("%H:%M")
        summary = f"预计 {at} {kind}停" if wet else f"预计 {at} 开始下{kind}"
    else:
        summary = "预报时段内降水持续" if wet else "预报时段内无雨雪"
    return {"hourly": hours, "nowcast": {"summary": summary, "points": points,
             "validUntil": (datetime.fromisoformat(points[-1]["time"]) + timedelta(minutes=5)).isoformat()}, "precipitating": wet}


def fetch_qweather(config, city):
    token = qweather_token(config)
    with ThreadPoolExecutor(max_workers=4) as pool:
        current = pool.submit(qweather_request, config, token, "current", city)
        daily = pool.submit(qweather_request, config, token, "daily", city, days=7)
        hourly = pool.submit(qweather_request, config, token, "hourly", city, hours=24)
        minutely = pool.submit(fetch_json, f"https://{config['api_host']}/v7/minutely/5m",
                               {"location": f"{city['longitude']:.2f},{city['latitude']:.2f}", "lang": "zh"},
                               {"Authorization": "Bearer " + token})
        def response(future, label):
            try:
                return future.result()
            except DataError as exc:
                raise DataError(f"{label}：{exc}") from exc
        try:
            result = normalize_qweather(response(current, "实时天气"), response(daily, "七日预报"), city)
            result.update(normalize_precise_weather(response(hourly, "逐小时预报"), response(minutely, "分钟降水"), city))
            result["precipitating"] = result["precipitating"] or result["current"]["icon"] in ("rain", "snow", "storm")
            result["refreshAfter"] = 300 if result["precipitating"] else 600
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DataError("和风天气返回格式不正确") from exc


def validate_custom_location(value):
    if not isinstance(value, dict) or not isinstance(value.get("enabled", False), bool):
        raise DataError("自定义位置设置无效")
    result = {"enabled": value.get("enabled", False),
              **{key: value.get(key, "") for key in ("name", "longitude", "latitude")}}
    if not result["enabled"]:
        return result
    if not isinstance(result["name"], str) or not result["name"].strip() or len(result["name"].strip()) > 80 or any(ord(c) < 32 for c in result["name"]):
        raise DataError("请输入位置名称（1–80 个字符）")
    result["name"] = result["name"].strip()
    for key, label, limit in (("longitude", "经度", 180), ("latitude", "纬度", 90)):
        text = str(result[key]).strip()
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", text):
            raise DataError(f"{label}请输入十进制数字")
        number = float(text)
        if not math.isfinite(number) or not -limit <= number <= limit:
            raise DataError(f"{label}应在 -{limit} 到 {limit} 之间")
        result[key] = number
    return result


def custom_city(settings):
    value = settings.get("customLocation") or {}
    if settings["provider"] != "qweather" or not value.get("enabled"):
        return None
    value = validate_custom_location(value)
    # Coordinates need no geocoding request; display times in the system zone.
    zone = str(Path("/etc/localtime").resolve()).partition("/zoneinfo/")[2] or "UTC"
    return {"name": value["name"], "latitude": value["latitude"], "longitude": value["longitude"],
            "timezone": zone, "kind": "custom", "source": "qweather"}


def configure_weather(action, draft=None):
    if action == "load":
        return {"ok": True, "settings": weather_settings()}
    if not isinstance(draft, dict) or draft.get("provider") not in ("open-meteo", "qweather"):
        raise DataError("请选择天气来源")
    if not isinstance(draft.get("notifications", True), bool):
        raise DataError("天气通知开关无效")
    settings = {"provider": draft["provider"], "qweather": draft.get("qweather", {}),
                "notifications": draft.get("notifications", True)}
    saved = weather_settings()
    if "customLocation" in draft or "customLocation" in saved:
        settings["customLocation"] = validate_custom_location(draft.get("customLocation", saved.get("customLocation")))
    notification_only = (action == "save" and settings["provider"] == saved["provider"]
                         and settings["qweather"] == saved.get("qweather", {}))
    if settings["provider"] == "qweather" and not notification_only:
        settings["qweather"] = validate_qweather(settings["qweather"])
        # Both test and save verify the exact draft, including forecast permissions.
        city = {"name": "北京", "latitude": 39.92, "longitude": 116.41, "timezone": "Asia/Shanghai"}
        fetch_qweather(settings["qweather"], city)
    if action == "save":
        atomic_json(WEATHER_SETTINGS, settings)
    return {"ok": True, "settings": settings, "message": "配置已保存" if action == "save" else "连接成功，实时、逐小时、分钟降水及七日预报均可用"}


def get_qweather(city, force, settings):
    config = validate_qweather(settings["qweather"])
    identity = json.dumps([config, city], sort_keys=True)
    key = hashlib.sha256(identity.encode()).hexdigest()[:20]
    path = CACHE / f"qweather-{key}.json"
    cached = read_json(path)
    age = time.time() - cached.get("savedAt", 0) if cached else float("inf")
    today = datetime.now(ZoneInfo(city["timezone"])).date().isoformat()
    interval = cached.get("data", {}).get("refreshAfter", 600) if cached else 600
    if (not force or age < 3) and age < interval and cached["data"].get("hourly") and cached["data"].get("today") == today:
        result, saved_at = cached["data"], cached["savedAt"]
    else:
        result, saved_at = fetch_qweather(config, city), time.time()
        atomic_json(path, {"data": result, "savedAt": saved_at})
    result.update(stale=False, warning="", fetchedAt=saved_at, nextRefresh=max(1, result["refreshAfter"] - (time.time() - saved_at)),
                  updatedAt=datetime.fromtimestamp(saved_at, ZoneInfo(city["timezone"])).isoformat(timespec="minutes"))
    return result


def _get_weather(city=None, force=False):
    warning = ""
    settings = weather_settings()
    city = custom_city(settings) or city
    if city is None:
        city, warning = locate_city(force)
    else:
        city = validate_city(city)
    settings = weather_settings()
    if settings["provider"] == "qweather":
        try:
            result = get_qweather(city, force, settings)
            if warning:
                result["warning"] = "；".join(filter(None, (warning, result["warning"])))
            return result
        except DataError as exc:
            warning = "；".join(filter(None, (warning, f"和风天气暂不可用（{exc}），已回退 Open-Meteo")))
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
    result.update(provider="open-meteo", refreshAfter=(300 if result["current"]["icon"] in ("rain", "snow", "storm") else 600) if settings["provider"] == "qweather" else 900, fetchedAt=saved_at, stale=stale, warning=warning, updatedAt=datetime.fromtimestamp(saved_at, ZoneInfo(city["timezone"])).isoformat(timespec="minutes"))
    return result


def get_weather(city=None, force=False):
    # Serialize requests from multiple monitor instances, including wake refreshes.
    requested_at = time.time()
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / "weather.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        key = hashlib.sha256(json.dumps([city, weather_settings()], sort_keys=True).encode()).hexdigest()[:20]
        recent_path = CACHE / f"weather-result-{key}.json"
        recent = read_json(recent_path)
        if recent:
            previous = recent["data"]
            age = time.time() - recent.get("savedAt", 0)
            fallback_fresh = (not force and weather_settings()["provider"] == "qweather"
                              and previous.get("provider") == "open-meteo"
                              and age < previous.get("refreshAfter", 600))
            if recent.get("savedAt", 0) >= requested_at or fallback_fresh:
                if fallback_fresh:
                    previous["nextRefresh"] = max(1, previous.get("refreshAfter", 600) - age)
                return previous
        result = _get_weather(city, force)
        atomic_json(recent_path, {"savedAt": time.time(), "data": result})
        return result


def normalize_alerts(data, now=None):
    now = now or datetime.now(ZoneInfo("UTC"))
    items = data.get("alerts")
    if items is None and data.get("metadata", {}).get("zeroResult") is True:
        items = []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise DataError("预警服务返回格式错误")
    replaced = set()
    for item in items:
        message = item.get("messageType") or {}
        if message.get("code") in ("update", "cancel"):
            replaced.update(message.get("supersedes") or [])
    alerts = {}
    try:
        for item in items:
            if item["id"] in replaced or (item.get("messageType") or {}).get("code") == "cancel":
                continue
            effective = datetime.fromisoformat(item["effectiveTime"].replace("Z", "+00:00"))
            expires = datetime.fromisoformat(item["expireTime"].replace("Z", "+00:00"))
            if not effective.tzinfo or not expires.tzinfo:
                raise ValueError("Missing timezone")
            if not effective <= now < expires:
                continue
            alerts[item["id"]] = {key: item.get(key) or "" for key in
                ("id", "senderName", "issuedTime", "effectiveTime", "expireTime", "headline", "description", "instruction", "severity")}
            alerts[item["id"]]["eventName"] = (item.get("eventType") or {}).get("name", "天气预警")
            alerts[item["id"]]["icon"] = str(item.get("icon") or "999")
            alerts[item["id"]]["color"] = (item.get("color") or {}).get("code", "")
        rank = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3}
        return sorted(alerts.values(), key=lambda a: (rank.get(a["severity"], 4), a["issuedTime"])), data.get("metadata", {}).get("attributions", [])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DataError("预警服务返回格式错误") from exc


def get_alerts(city=None, force=False):
    settings = weather_settings()
    if settings["provider"] != "qweather":
        return {"ok": True, "enabled": False, "alerts": [], "nextRefresh": 900}
    config = validate_qweather(settings["qweather"])
    city = custom_city(settings) or (validate_city(city) if city is not None else locate_city(False)[0])
    key = hashlib.sha256(json.dumps([config, city], sort_keys=True).encode()).hexdigest()[:20]
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / "alerts.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = CACHE / f"alerts-{key}.json"
        cached = read_json(path) or {}
        age = time.time() - cached.get("checkedAt", 0)
        if age >= 900 or (force and age >= 3):
            try:
                token = qweather_token(config)
                data = fetch_json(f"https://{config['api_host']}/weatheralert/v1/current/{city['latitude']:.2f}/{city['longitude']:.2f}",
                                  {"lang": "zh", "localTime": "true"}, {"Authorization": "Bearer " + token})
                normalize_alerts(data)
                cached = {"data": data, "savedAt": time.time(), "error": ""}
            except DataError as exc:
                cached["error"] = str(exc)
            cached["checkedAt"] = time.time()
            atomic_json(path, cached)
        # Re-evaluate expiry even when returning a cached or failed response.
        alerts, attributions = normalize_alerts(cached["data"]) if cached.get("data") else ([], [])
        error = cached.get("error", "")
        return {"ok": not bool(error), "enabled": True, "city": city, "alerts": alerts,
                "messages": (cached.get("data") or {}).get("alerts", []),
                "attributions": attributions, "error": error, "stale": bool(error and alerts),
                "updatedAt": datetime.fromtimestamp(cached["savedAt"], ZoneInfo(city["timezone"])).isoformat(timespec="minutes") if cached.get("savedAt") else "",
                "nextRefresh": max(1, 900 - (time.time() - cached["checkedAt"]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    month = commands.add_parser("month")
    month.add_argument("--year", type=int, required=True)
    month.add_argument("--month", type=int, required=True)
    holiday = commands.add_parser("holidays")
    holiday.add_argument("--year", type=int, required=True)
    search = commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--offline", action="store_true")
    weather = commands.add_parser("weather")
    weather.add_argument("--city", help="JSON city selected from search results")
    weather.add_argument("--force", action="store_true")
    alerts = commands.add_parser("alerts")
    alerts.add_argument("--city")
    alerts.add_argument("--force", action="store_true")
    settings = commands.add_parser("weather-settings")
    settings.add_argument("action", choices=("load", "test", "save"))
    args = parser.parse_args()
    try:
        if args.command == "weather-settings":
            draft = json.loads(sys.stdin.readline(16385)) if args.action != "load" else None
            result = configure_weather(args.action, draft)
        elif args.command == "alerts":
            result = get_alerts(json.loads(args.city) if args.city else None, args.force)
        elif args.command == "month":
            result = month_data(args.year, args.month)
        elif args.command == "holidays":
            if not 1901 <= args.year <= 2099:
                raise DataError("年份超出支持范围")
            result = refresh_holidays(args.year)
        elif args.command == "search":
            result = search_locations(args.query[:120], args.offline)
        else:
            result = get_weather(json.loads(args.city) if args.city else None, args.force)
    except (DataError, ValueError, KeyError, TypeError, OSError) as exc:
        result = {"ok": False, "error": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
