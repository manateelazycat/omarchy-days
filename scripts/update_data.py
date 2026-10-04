#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

"""Rebuild redistributable offline cities and holiday snapshots from their sources."""
import io
import json
from pathlib import Path
import re
import unicodedata
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def download(url):
    with urllib.request.urlopen(url, timeout=45) as response:
        return response.read()


def normalized(text):
    text = unicodedata.normalize("NFKD", text.casefold().replace("ü", "v"))
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def main():
    dest = ROOT / "data"
    (dest / "holidays").mkdir(parents=True, exist_ok=True)
    (ROOT / "licenses").mkdir(exist_ok=True)
    base = "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/"
    for year in (2024, 2025, 2026):
        data = json.loads(download(f"{base}{year}.json"))
        (dest / "holidays" / f"{year}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "licenses/holiday-cn-MIT.txt").write_bytes(download(base + "LICENSE"))
    url = "https://download.geonames.org/export/dump/cities15000.zip"
    rows = zipfile.ZipFile(io.BytesIO(download(url))).read("cities15000.txt").decode().splitlines()
    admins = {}
    translations = {"Anhui": "安徽省", "Beijing": "北京市", "Chongqing": "重庆市", "Fujian": "福建省", "Gansu": "甘肃省", "Guangdong": "广东省", "Guangxi": "广西", "Guizhou": "贵州省", "Hainan": "海南省", "Hebei": "河北省", "Heilongjiang": "黑龙江省", "Henan": "河南省", "Hubei": "湖北省", "Hunan": "湖南省", "Jiangsu": "江苏省", "Jiangxi": "江西省", "Jilin": "吉林省", "Liaoning": "辽宁省", "Nei Mongol": "内蒙古", "Inner Mongolia": "内蒙古", "Ningxia": "宁夏", "Qinghai": "青海省", "Shaanxi": "陕西省", "Shandong": "山东省", "Shanghai": "上海市", "Shanxi": "山西省", "Sichuan": "四川省", "Tianjin": "天津市", "Xinjiang": "新疆", "Xizang": "西藏", "Tibet": "西藏", "Yunnan": "云南省", "Zhejiang": "浙江省"}
    for row in download("https://download.geonames.org/export/dump/admin1CodesASCII.txt").decode().splitlines():
        fields = row.split("\t")
        admins[fields[0]] = next((zh for en, zh in translations.items() if en.casefold() in fields[1].casefold()), fields[1])
    preferred = {"Beijing": "北京", "Shanghai": "上海", "Chongqing": "重庆", "Tianjin": "天津", "Guangzhou": "广州", "Shenzhen": "深圳", "Hangzhou": "杭州", "Chengdu": "成都", "Wuhan": "武汉", "Nanjing": "南京", "Xi'an": "西安", "Xiamen": "厦门", "Fuzhou": "福州", "Qingdao": "青岛", "Harbin": "哈尔滨", "Changsha": "长沙", "Zhengzhou": "郑州", "Kunming": "昆明", "Hong Kong": "香港", "Taipei": "台北", "Macau": "澳门"}
    countries = {"CN": "中国", "HK": "香港", "MO": "澳门", "TW": "台湾"}
    cities = []
    for line in rows:
        f = line.split("\t")
        if f[8] not in countries:
            continue
        alt = f[3].split(",")
        chinese = [a for a in alt if re.fullmatch(r"[\u4e00-\u9fff]{2,12}", a)]
        name = preferred.get(f[2]) or (f[1] if re.fullmatch(r"[\u4e00-\u9fff]{2,12}", f[1]) else min(chinese, key=len) if chinese else f[1])
        aliases = {normalized(name), normalized(f[1]), normalized(f[2])}
        for a in alt:
            if re.fullmatch(r"[a-zA-Z\u00c0-\u024f '-]{2,40}", a):
                aliases.add(normalized(a))
        cities.append({"id": int(f[0]), "name": name, "englishName": f[2], "admin1": admins.get(f[8] + "." + f[10], ""), "country": countries[f[8]], "country_code": f[8], "latitude": float(f[4]), "longitude": float(f[5]), "timezone": "Asia/Shanghai" if f[8] == "CN" else f[17], "population": int(f[14]), "aliases": sorted(aliases)})
    cities.sort(key=lambda c: -c["population"])
    data = {"source": url, "license": "CC BY 4.0", "cities": cities}
    (dest / "cities.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Updated {len(cities)} offline cities and 2024–2026 holiday schedules.")


if __name__ == "__main__":
    main()
