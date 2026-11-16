#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 data/*.json 的结构与取值，让错误在写数据时暴露而不是在页面里。

被 build.py 作为前置检查调用，也可单独运行：
    python3 scripts/validate_data.py
"""
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import date
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 三页各自的 schema
SCHEMAS = {
    "data/venues/bars.json": {
        "label": "酒吧 / Livehouse / 夜店",
        "required": [
            "key", "name", "coords", "district", "addr", "type", "genre", "avg", "close",
            "open_days", "live", "capacity", "booking", "id_check", "ticket", "status",
            "metro", "vibe", "note", "src_tier", "src_url", "updated",
        ],
        "enums": {
            "type": ["精酿", "鸡尾酒", "威士忌", "爵士现场", "Livehouse", "音乐剧场",
                     "电音俱乐部", "大型夜店"],
            "booking": ["免预约", "建议预约", "必须预约", "不接受预约"],
            "id_check": ["none", "实名一证一票", "身份证强实名(人脸核验)"],
            "status": ["active", "suspended", "closed"],
        },
        "bool": ["live"],
        "list_enum": {"src_tier": ["A", "B", "C", "D", "🗂"]},
    },
    "data/venues/bichi.json": {
        "label": "必吃榜 × 扫街榜",
        "required": [
            "key", "name", "bichi", "saojie", "michelin", "avg", "coords", "cuisine",
            "address", "price", "desc", "mnemonic", "icon", "note", "isNew",
        ],
        "int_enums": {"michelin": [-1, 0, 1, 2, 3]},
        "bool": ["bichi", "saojie", "isNew"],
    },
    "data/venues/michelin.json": {
        "label": "米其林指南 2026",
        "required": [
            "key", "name", "category", "coords", "desc", "mnemonic", "icon", "stars",
            "bib", "cuisine", "address", "price", "note", "isNew",
        ],
        "enums": {"category": ["michelin3", "michelin2", "michelin1", "bib"]},
        "int_enums": {"stars": [0, 1, 2, 3]},
        "bool": ["bib", "isNew"],
    },
}

ROADS_JSON = "data/map/roads.json"
AREA_FILES = ["data/map/areas/downtown.json", "data/map/areas/greater.json"]
LANDMARK_FILES = ["data/map/landmarks/downtown.json", "data/map/landmarks/greater.json"]

AREA_KINDS = ["origin", "zone"]
LANDMARK_KINDS = ["tower", "venue", "mall", "park", "transit"]

METRO_LINES = "data/map/metro/lines.json"
METRO_STATIONS = "data/map/metro/stations.json"

# 地铁线色必须是 #RRGGBB（Leaflet 直接把它喂给 SVG stroke）
COLOR_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# bars.json 的 metro 是自然语言，从中抠出「8/12号线」这类线号
METRO_REF = re.compile(r"([0-9]+(?:\s*/\s*[0-9]+)*)\s*号线")

# 已知偏差白名单：bars.json 的 metro 里提到、但 lines.json 故意不收录的线路。
# 6 号线在核心区 bbox 内 0 站（最近的高科西路距东边界约 400 m），按「范围外不收录 /
# 严禁编造坐标」的铁律跳过 —— 用户已知并接受，见 README「地铁线路」与阶段一报告。
# 关键：白名单只对下面列出的线号生效，其余任何「bars 提到却查无此线」都要报错，
# 这条断言的未来价值就是抓住「新开了一条线却忘了收录」。
MISSING_LINES = {
    6: "核心区 bbox 内 0 站（最近的高科西路距东边界约 400 m），按不编造坐标的铁律跳过；见 README / 阶段一报告",
}

# 「规划中未启用」的站允许不被任何线路引用。目前一个都没有 —— 保持空集合而不是关掉整条检查。
PLANNED_STATIONS = set()

# 上海大致范围（含崇明/金山等外围），坐标超出必然是填错了
LAT_RANGE = (30.60, 31.90)
LNG_RANGE = (120.80, 122.20)

HHMM = re.compile(r"^\d{1,2}:\d{2}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 百度 POI 的 uid（如 09185c56d24f7e44f1193763 / GaC7fyEEg0CDu3Je）。形态不对外承诺，
# 所以只做「像 id 的字符串」这一层校验；数据里手填的 uid 与短链由人工保证正确。
BAIDU_UID = re.compile(r"^[0-9A-Za-z_-]{8,64}$")

SEOUL_JSON = "data/venues/seoul-michelin.json"
GUIDE_METADATA = "data/guide-metadata.json"
MICHELIN_AWARDS = {
    "3": "THREE_STARS", "2": "TWO_STARS", "1": "ONE_STAR", "bib": "BIB_GOURMAND",
}
ATLAS_PAGES = "data/atlas-pages.json"
OFFICIAL_GUIDE_HOSTS = {"www.michelin.com", "guide.michelin.com", "www.michelin.com.cn"}
# 宽松的城市行政范围用于拦截错城/经纬倒置；不把边界框当作精确行政区划。
CITY_GUIDES = {
    "seoul": {"label": "首尔", "lat": (37.4, 37.75), "lng": (126.75, 127.2), "currency": "₩"},
    "beijing": {"label": "北京", "lat": (39.4, 41.1), "lng": (115.4, 117.6), "currency": "¥"},
    "suzhou": {"label": "苏州", "lat": (30.75, 32.1), "lng": (119.9, 121.5), "currency": "¥"},
    "nanjing": {"label": "南京", "lat": (31.2, 32.7), "lng": (118.3, 119.3), "currency": "¥"},
    "hangzhou": {"label": "杭州", "lat": (29.1, 30.6), "lng": (118.3, 120.8), "currency": "¥"},
    "hong-kong": {"label": "香港", "lat": (22.1, 22.6), "lng": (113.8, 114.5), "currency": "$"},
}
for _city, _cfg in CITY_GUIDES.items():
    _cfg["data"] = "data/venues/{}-michelin.json".format(_city)


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def check_city_michelin(errors, city):
    """验证首尔及新增城市；各城市使用自己的地理边界和货币符号。"""
    cfg = CITY_GUIDES[city]
    rel = cfg["data"]
    records = load(rel)
    if not isinstance(records, list) or not records:
        errors.append(rel + ": 必须是非空数组")
        return
    seen = {field: set() for field in ("id", "key", "url")}
    required_strings = ("id", "key", "name", "url", "award", "year", "category")
    for i, record in enumerate(records):
        where = "{}[{}]".format(rel, i)
        if not isinstance(record, dict):
            errors.append(where + ": 必须是对象")
            continue
        where += " ({})".format(record.get("name", "?"))
        for field in required_strings:
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append("{}: {} 必须是非空字符串".format(where, field))
        for field in seen:
            value = record.get(field)
            if isinstance(value, str):
                if value in seen[field]:
                    errors.append("{}: {} 重复".format(where, field))
                seen[field].add(value)
        rid = record.get("id")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", rid):
            errors.append(where + ": id 必须是数字或稳定的字母数字slug")
        if city == "seoul" and isinstance(rid, str) and not rid.isdecimal():
            errors.append(where + ": 首尔官方id必须是数字字符串")
        if record.get("key") != "{}_{}".format(city, rid):
            errors.append(where + ": key 必须使用城市前缀并与 id 对应")

        unverified = record.get("locationStatus") == "unverified"
        if unverified:
            if "lat" not in record or "lng" not in record or record["lat"] is not None or record["lng"] is not None:
                errors.append(where + ": 未核实定位必须显式使用 lat:null / lng:null，不能填占位坐标")
            if record.get("directoryStatus") != "not-listed":
                errors.append(where + ": 未定位档案必须显式标记 directoryStatus=not-listed")
            if not isinstance(record.get("directoryNote"), str) or not record["directoryNote"].strip():
                errors.append(where + ": 未定位档案必须说明 directoryNote")
        else:
            for field, bounds in (("lat", cfg["lat"]), ("lng", cfg["lng"])):
                value = record.get(field)
                if (type(value) not in (int, float) or not math.isfinite(value)
                        or not bounds[0] <= value <= bounds[1]):
                    errors.append("{}: {} 必须是{}范围内的有限坐标".format(where, field, cfg["label"]))
        for field in ("price", "cuisine", "address", "district"):
            value = record.get(field)
            if not isinstance(value, str) or (not unverified and field != "district" and not value.strip()):
                errors.append("{}: {} 必须是{}字符串".format(where, field, "" if unverified or field == "district" else "非空"))
        category = record.get("category")
        if not isinstance(category, str) or category not in MICHELIN_AWARDS:
            errors.append(where + ": category 不是已收录的米其林奖项")
        elif record.get("award") != MICHELIN_AWARDS[category]:
            errors.append(where + ": category 与 award 不一致")
        price = record.get("price")
        if not (unverified and price == "") and (not isinstance(price, str) or not re.fullmatch(re.escape(cfg["currency"]) + r"{1,4}", price)):
            errors.append(where + ": price 必须是1至4个本币价位符号")
        if not isinstance(record.get("year"), str) or not re.fullmatch(r"20[0-9]{2}", record["year"]):
            errors.append(where + ": year 必须为四位指南年度")
        if record.get("phone") is not None and not isinstance(record["phone"], str):
            errors.append(where + ": phone 必须是字符串或null")
        if "greenStar" in record and not isinstance(record["greenStar"], bool):
            errors.append(where + ": greenStar 必须是布尔值；未核实请省略")
        if "distinctionChange" in record and record["distinctionChange"] not in ("new", "promoted", "retained"):
            errors.append(where + ": distinctionChange 必须为 new / promoted / retained；未核实请省略")
        if city == "seoul":
            for field in ("koreanName", "koreanAddress", "district"):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    errors.append("{}: {} 必须是非空字符串".format(where, field))
            if "greenStar" not in record or "distinctionChange" not in record:
                errors.append(where + ": 首尔已核验的绿星和年度奖项字段不可缺失")
        url = record.get("url")
        if isinstance(url, str):
            parsed = urlparse(url)
            if (parsed.scheme != "https" or parsed.netloc != "guide.michelin.com"
                    or "/restaurant/" not in parsed.path):
                errors.append(where + ": url 必须指向米其林官方餐厅页")
    mapped = sum(isinstance(r, dict) and r.get("locationStatus") != "unverified" for r in records)
    print("  {:<34} {:>3} 条  {}米其林（地图定位 {}）".format(rel, len(records), cfg["label"], mapped))


def check_seoul(errors):
    check_city_michelin(errors, "seoul")


def check_city_guides(errors):
    for city in CITY_GUIDES:
        try:
            check_city_michelin(errors, city)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append("{}: 资料读取失败 {}".format(city, exc))


def check_guide_metadata(errors):
    """官方年度数量含未定位档案；零家分类与地图定位数分别核对。"""
    metadata = load(GUIDE_METADATA)
    if not isinstance(metadata, dict):
        errors.append(GUIDE_METADATA + ": 必须是对象")
        return
    guides = {city: cfg["data"] for city, cfg in CITY_GUIDES.items()}
    guides["shanghai"] = "data/venues/michelin.json"
    for city, rel in guides.items():
        guide = metadata.get(city)
        if not isinstance(guide, dict):
            errors.append(GUIDE_METADATA + ": 缺少 " + city)
            continue
        if city not in ("seoul", "shanghai"):
            try:
                standalone = load("data/guides/{}.json".format(city))
                if standalone != guide:
                    errors.append("{}: {} 与独立指南元数据不一致".format(GUIDE_METADATA, city))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append("{}: 独立指南资料读取失败 {}".format(city, exc))
        edition = guide.get("edition")
        if not isinstance(edition, str) or not re.fullmatch(r"20[0-9]{2}", edition):
            errors.append("{}: {}.edition 必须为四位指南年度".format(GUIDE_METADATA, city))
        for field in ("announcedAt", "verifiedAt"):
            try:
                value = guide[field]
                if not isinstance(value, str) or not DATE.fullmatch(value):
                    raise ValueError("invalid date")
                date.fromisoformat(value)
            except (KeyError, TypeError, ValueError):
                errors.append("{}: {}.{} 必须为有效日期".format(GUIDE_METADATA, city, field))
        sources = guide.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append("{}: {} 缺少核验来源".format(GUIDE_METADATA, city))
        else:
            has_official_source = False
            for source in sources:
                url = source.get("url", "") if isinstance(source, dict) else ""
                parsed = urlparse(url) if isinstance(url, str) else urlparse("")
                if parsed.scheme != "https" or not parsed.netloc or not isinstance(source, dict) or not source.get("label"):
                    errors.append("{}: {} 核验来源必须有说明和有效HTTPS链接".format(GUIDE_METADATA, city))
                has_official_source |= parsed.netloc in OFFICIAL_GUIDE_HOSTS
            if not has_official_source:
                errors.append("{}: {} 必须至少引用一项米其林官方核验来源".format(GUIDE_METADATA, city))
        try:
            records = load(rel)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append("{}: 资料读取失败 {}".format(rel, exc))
            continue
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            continue
        allowed = {"michelin3", "michelin2", "michelin1", "bib"} if city == "shanghai" else set(MICHELIN_AWARDS)
        counts = guide.get("counts")
        counts_valid = (isinstance(counts, dict) and set(counts) <= allowed
                        and all(type(value) is int and value >= 0 for value in counts.values()))
        if not counts_valid:
            errors.append("{}: {}.counts 必须是合法奖项到非负整数的映射".format(GUIDE_METADATA, city))
        categories = [r.get("category") for r in records]
        if counts_valid and all(isinstance(category, str) for category in categories):
            actual = Counter(categories)
            if set(actual) - allowed or any(actual[category] != counts.get(category, 0) for category in allowed):
                errors.append("{}: 分类数量与 {} 的官方年度统计不一致".format(rel, GUIDE_METADATA))
        if city != "shanghai" and any(r.get("year") != edition for r in records):
            errors.append(rel + ": year 与指南版本不一致")
        if "greenStarCount" in guide:
            if type(guide["greenStarCount"]) is not int or sum(r.get("greenStar") is True for r in records) != guide["greenStarCount"]:
                errors.append(rel + ": 绿星数量与官方统计不一致")
        if "distinctionChanges" in guide:
            changes = [r.get("distinctionChange") for r in records]
            if not all(isinstance(value, str) for value in changes) or dict(Counter(changes)) != guide["distinctionChanges"]:
                errors.append(rel + ": 年度奖项变动数量与官方统计不一致")
        unmapped = [r for r in records if r.get("locationStatus") == "unverified"]
        if unmapped or "mappedCount" in guide or "unmappedEntries" in guide:
            mapped_count = guide.get("mappedCount")
            if type(mapped_count) is not int or mapped_count != len(records) - len(unmapped):
                errors.append(rel + ": mappedCount 与已定位门店数不一致")
            entries = guide.get("unmappedEntries")
            declared = []
            if isinstance(entries, list):
                for entry in entries:
                    identifier = entry if isinstance(entry, str) else entry.get("id", entry.get("key")) if isinstance(entry, dict) else None
                    match = next((r for r in unmapped if identifier in (r.get("id"), r.get("key"))), None)
                    if match is None:
                        errors.append(rel + ": unmappedEntries 必须逐项引用未定位档案的id或key")
                    else:
                        declared.append(match.get("key"))
            if not isinstance(entries, list) or len(declared) != len(unmapped) or set(declared) != {r.get("key") for r in unmapped}:
                errors.append(rel + ": unmappedEntries 与未定位档案不一致")


def check_atlas_pages(errors):
    """页面数量、数据源与指南版本一起校验，防止目录与构建配置漂移。"""
    import merge_venues

    pages = load(ATLAS_PAGES)
    metadata = load(GUIDE_METADATA)
    if not isinstance(pages, list) or not pages:
        errors.append(ATLAS_PAGES + ": 必须是非空页面数组")
        return
    if not isinstance(metadata, dict):
        return
    seen = {field: set() for field in ("id", "file")}
    known_cities = set(CITY_GUIDES) | {"shanghai"}
    for i, page in enumerate(pages):
        where = "{}[{}]".format(ATLAS_PAGES, i)
        if not isinstance(page, dict):
            errors.append(where + ": 必须是对象")
            continue
        for field in seen:
            value = page.get(field)
            if not isinstance(value, str) or not value:
                errors.append("{}: {} 必须是非空字符串".format(where, field))
            elif value in seen[field]:
                errors.append("{}: {} 重复".format(where, field))
            else:
                seen[field].add(value)
        filename = page.get("file")
        if not isinstance(filename, str) or not re.fullmatch(r"[a-z0-9_-]+[.]html", filename):
            errors.append(where + ": file 必须是安全的HTML输出文件名")
        city, kind = page.get("city"), page.get("kind")
        if not isinstance(city, str) or city not in known_cities:
            errors.append(where + ": city 未配置地理范围")
            continue
        country = page.get("country")
        expected_country = "KR" if city == "seoul" else "CN"
        if country not in ("CN", "KR"):
            errors.append(where + ": country 必须为 CN / KR")
        elif country != expected_country:
            errors.append(where + ": country 与城市所属国家不一致（香港属于CN，首尔属于KR）")
        if page.get("countryName") != {"CN": "中国", "KR": "韩国"}[expected_country]:
            errors.append(where + ": countryName 与城市所属国家不一致")
        expected_currency = CITY_GUIDES[city]["currency"] if city != "shanghai" else "¥"
        if ("currency" in page or city == "hong-kong") and page.get("currency") != expected_currency:
            errors.append(where + ": currency 与城市货币不一致（香港使用港币$档位）")
        if kind not in ("michelin", "eat", "bichi", "bars") or (city != "shanghai" and kind != "michelin"):
            errors.append(where + ": kind 不是当前城市支持的地图类型")
            continue
        edition = page.get("edition")
        if not isinstance(edition, str) or not re.fullmatch(r"20[0-9]{2}", edition):
            errors.append(where + ": edition 必须为四位年度")
        if kind in ("michelin", "eat"):
            guide = metadata.get(city, {})
            if not isinstance(guide, dict) or edition != guide.get("edition"):
                errors.append(where + ": 页面edition与城市指南版本不一致")
        if city != "shanghai":
            expected_sources = [CITY_GUIDES[city]["data"]]
        elif kind == "eat":
            expected_sources = ["data/venues/bichi.json", "data/venues/michelin.json"]
        else:
            expected_sources = ["data/venues/{}.json".format(kind)]
        if page.get("data") != expected_sources:
            errors.append(where + ": data 必须与城市和地图类型的数据源对应")
            continue
        try:
            inputs = [load(rel) for rel in expected_sources]
            if any(not isinstance(records, list) for records in inputs):
                continue
            count = len(merge_venues.merge_sources(list(zip(("bichi", "michelin"), inputs)))) if kind == "eat" else len(inputs[0])
            if type(page.get("expectedCount")) is not int or page["expectedCount"] != count:
                errors.append("{}: expectedCount 与数据条数 {} 不一致".format(where, count))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append("{}: 无法读取/合并页面资料 {}".format(where, exc))
    print("  {:<34} {:>3} 张  城市地图配置".format(ATLAS_PAGES, len(pages)))


def check_coords(errors, where, coords):
    if not (isinstance(coords, list) and len(coords) == 2):
        errors.append("{}: coords 必须是 [lat, lng]，实际 {}".format(where, coords))
        return
    lat, lng = coords
    if not all(isinstance(x, (int, float)) for x in coords):
        errors.append("{}: coords 必须是数字，实际 {}".format(where, coords))
        return
    if not LAT_RANGE[0] <= lat <= LAT_RANGE[1]:
        errors.append("{}: 纬度 {} 超出上海范围 {}".format(where, lat, LAT_RANGE))
    if not LNG_RANGE[0] <= lng <= LNG_RANGE[1]:
        errors.append("{}: 经度 {} 超出上海范围 {}".format(where, lng, LNG_RANGE))


def check_records(errors, rel, cfg):
    recs = load(rel)
    if not isinstance(recs, list):
        errors.append("{}: 顶层必须是数组".format(rel))
        return
    seen = set()
    for i, r in enumerate(recs):
        where = "{}[{}]".format(rel, i)
        if not isinstance(r, dict):
            errors.append("{}: 必须是对象".format(where))
            continue
        label = r.get("name") or r.get("key") or "?"
        where = "{} ({})".format(where, label)

        for f in cfg["required"]:
            if f not in r:
                errors.append("{}: 缺字段 {}（缺字段会让页面渲染出 undefined）".format(where, f))

        key = r.get("key")
        if not key:
            errors.append("{}: key 为空".format(where))
        elif key in seen:
            errors.append("{}: key 重复".format(where))
        else:
            seen.add(key)

        if "coords" in r:
            check_coords(errors, where, r["coords"])

        for f, allowed in cfg.get("enums", {}).items():
            if f in r and r[f] not in allowed:
                errors.append("{}: {} = {!r} 不在允许值 {}".format(where, f, r[f], allowed))
        for f, allowed in cfg.get("int_enums", {}).items():
            if f in r and r[f] not in allowed:
                errors.append("{}: {} = {!r} 不在允许值 {}".format(where, f, r[f], allowed))
        for f in cfg.get("bool", []):
            if f in r and not isinstance(r[f], bool):
                errors.append("{}: {} 必须是布尔，实际 {!r}".format(where, f, r[f]))
        for f, allowed in cfg.get("list_enum", {}).items():
            if f in r:
                if not isinstance(r[f], list) or not r[f]:
                    errors.append("{}: {} 必须是非空数组".format(where, f))
                else:
                    bad = [x for x in r[f] if x not in allowed]
                    if bad:
                        errors.append("{}: {} 含非法值 {}".format(where, f, bad))

        # avg：要么是正整数，要么是 None（页面渲染「人均待核实」）
        if "avg" in r and r["avg"] is not None:
            if not isinstance(r["avg"], int) or r["avg"] <= 0:
                errors.append("{}: avg 必须是正整数或 null，实际 {!r}".format(where, r["avg"]))
        # close：要么是 HH:MM，要么是 None
        if "close" in r and r["close"] is not None:
            if not (isinstance(r["close"], str) and HHMM.match(r["close"])):
                errors.append("{}: close 必须是 HH:MM 或 null，实际 {!r}".format(where, r["close"]))
        if "updated" in r and not (isinstance(r["updated"], str) and DATE.match(r["updated"])):
            errors.append("{}: updated 必须是 YYYY-MM-DD，实际 {!r}".format(where, r["updated"]))
        if "src_url" in r:
            if not isinstance(r["src_url"], list) or not r["src_url"]:
                errors.append("{}: src_url 必须是非空数组".format(where))
            elif not all(isinstance(u, str) and u.startswith("http") for u in r["src_url"]):
                errors.append("{}: src_url 必须都是 http(s) 链接".format(where))

        # 百度 POI 身份：三个字段都是**可选**的，缺省时页面退化为关键词检索，
        # 不算数据错误（见 src/static/venue-links.js 的三档降级）。
        if r.get("baidu_uid") is not None:
            if not (isinstance(r["baidu_uid"], str) and BAIDU_UID.match(r["baidu_uid"])):
                errors.append("{}: baidu_uid 必须是百度 POI 的 uid 字符串或 null，实际 {!r}".format(
                    where, r["baidu_uid"]))
        if r.get("baidu_url") is not None:
            u = r["baidu_url"]
            if not (isinstance(u, str) and u.startswith("http")):
                errors.append("{}: baidu_url 必须是 http(s) 链接或 null，实际 {!r}".format(where, u))
        if r.get("baidu_uid_at") is not None:
            if not (isinstance(r["baidu_uid_at"], str) and DATE.match(r["baidu_uid_at"])):
                errors.append("{}: baidu_uid_at 必须是 YYYY-MM-DD，实际 {!r}".format(
                    where, r["baidu_uid_at"]))

    # 米其林的 category 与 stars / bib 必须自洽
    if rel.endswith("michelin.json"):
        for r in recs:
            cat, stars, bib = r.get("category"), r.get("stars"), r.get("bib")
            if cat == "bib" and (stars != 0 or bib is not True):
                errors.append("michelin: {} 的 category=bib 但 stars={} / bib={}".format(
                    r.get("name"), stars, bib))
            if cat in ("michelin1", "michelin2", "michelin3"):
                want = int(cat[-1])
                if stars != want or bib is not False:
                    errors.append("michelin: {} 的 category={} 但 stars={} / bib={}".format(
                        r.get("name"), cat, stars, bib))

    n_uid = sum(1 for r in recs if isinstance(r, dict) and r.get("baidu_uid"))
    extra = "（已补百度 uid {}/{}）".format(n_uid, len(recs)) if n_uid else ""
    print("  {:<34} {:>3} 条  {}{}".format(rel, len(recs), cfg["label"], extra))


def check_merged(errors, verbose=True):
    """校验 bichi + michelin 的合并结果（eat 页数据）。

    合并靠「坐标完全一致」去重，所以这里把该规则的成立条件也一并断言，
    避免以后数据更新后悄悄产生漏合并/错合并。
    """
    import merge_venues

    bichi = load("data/venues/bichi.json")
    michelin = load("data/venues/michelin.json")

    # 去重要求同源内坐标不重复，否则「坐标 -> 单条」的索引会有歧义
    for rel, recs in (("data/venues/bichi.json", bichi), ("data/venues/michelin.json", michelin)):
        seen = {}
        for r in recs:
            c = tuple(r.get("coords") or [])
            if c in seen:
                errors.append("{}: 坐标重复（{} 与 {}），合并去重会产生歧义".format(
                    rel, seen[c], r.get("name")))
            seen[c] = r.get("name")

    # 不变量：bichi 侧 michelin != 0 的每条，都恰好对应一条坐标完全一致的米其林记录，
    # 且星级一致 —— 实测正是这 13 对，这也是坐标去重规则可靠的原因。
    by_coords = {tuple(m["coords"]): m for m in michelin}
    pairs = 0
    for b in bichi:
        level = b.get("michelin", 0)
        twin = by_coords.get(tuple(b["coords"]))
        if not level:
            if twin is not None:
                errors.append("bichi: {} 与米其林 {} 坐标完全相同（{}）但 michelin=0，"
                              "请确认是否漏标".format(b.get("name"), twin.get("name"), twin["category"]))
            continue
        if twin is None:
            errors.append("bichi: {} 标了 michelin={} 但在米其林数据里找不到同坐标记录".format(
                b.get("name"), level))
            continue
        want = "bib" if level == -1 else "michelin{}".format(level)
        if twin["category"] != want:
            errors.append("bichi: {} 的 michelin={} 与米其林 category={} 不一致".format(
                b.get("name"), level, twin["category"]))
        pairs += 1

    recs = merge_venues.merge_sources([("bichi", bichi), ("michelin", michelin)])

    expect_n = len(bichi) + len(michelin) - pairs
    if len(recs) != expect_n:
        errors.append("merge: 合并后 {} 条，预期 {} + {} - {} = {}".format(
            len(recs), len(bichi), len(michelin), pairs, expect_n))

    seen_keys, seen_coords = set(), set()
    for r in recs:
        name = r.get("name", "?")
        if r["key"] in seen_keys:
            errors.append("merge: key 重复 {}".format(r["key"]))
        seen_keys.add(r["key"])
        c = tuple(r["coords"])
        if c in seen_coords:
            errors.append("merge: 坐标重复（{}）".format(name))
        seen_coords.add(c)

        if not r["tags"]:
            errors.append("merge: {} 没有任何标签".format(name))
            continue
        bad = [t for t in r["tags"] if t not in merge_venues.PRIMARY_ORDER]
        if bad:
            errors.append("merge: {} 含非法标签 {}".format(name, bad))
        if r["primary"] not in r["tags"]:
            errors.append("merge: {} 的 primary={} 不在 tags {}".format(name, r["primary"], r["tags"]))
        elif r["primary"] != merge_venues._primary_of(r["tags"]):
            errors.append("merge: {} 的 primary={} 不符合优先级顺序 {}".format(
                name, r["primary"], merge_venues.PRIMARY_ORDER))
        if r["michelin"] != merge_venues._level_of(r["tags"]):
            errors.append("merge: {} 的 michelin={} 与 tags {} 不符".format(
                name, r["michelin"], r["tags"]))
        if "avg" in r and r["avg"] is not None and not isinstance(r["avg"], int):
            errors.append("merge: {} 的 avg 必须是整数或 null".format(name))
        if not r["sources"]:
            errors.append("merge: {} 缺少 sources".format(name))

    # 米其林标签条数必须与米其林数据条数一致（既不漏也不重）
    with_michelin = sum(1 for r in recs if r["michelin"] != 0)
    if with_michelin != len(michelin):
        errors.append("merge: 带米其林标签的 {} 条，米其林数据 {} 条，对不上".format(
            with_michelin, len(michelin)))

    if verbose:
        print("  {:<34} {:>3} 条  bichi + michelin 合并（去重 {} 对）".format(
            "data/venues/eat.json（构建期生成）", len(recs), pairs))


def check_roads(errors):
    roads = load(ROADS_JSON)
    if not isinstance(roads, list) or not roads:
        errors.append("{}: 必须是非空数组".format(ROADS_JSON))
        return
    seen = set()
    for i, r in enumerate(roads):
        where = "{}[{}]".format(ROADS_JSON, i)
        for f in ["id", "name", "tier", "vertical", "path"]:
            if f not in r:
                errors.append("{}: 缺字段 {}".format(where, f))
        if r.get("id") in seen:
            errors.append("{}: id 重复 {}".format(where, r.get("id")))
        seen.add(r.get("id"))
        if r.get("tier") not in (1, 2, 3):
            errors.append("{}: tier 必须是 1/2/3，实际 {!r}".format(where, r.get("tier")))
        if not isinstance(r.get("vertical"), bool):
            errors.append("{}: vertical 必须是布尔".format(where))
        path = r.get("path")
        if not (isinstance(path, list) and len(path) >= 2):
            errors.append("{}: path 至少要有 2 个点，实际 {}".format(
                where, len(path) if isinstance(path, list) else path))
        else:
            for p in path:
                check_coords(errors, where + " path", p)
    print("  {:<34} {:>3} 条  道路骨架".format(ROADS_JSON, len(roads)))


def check_points(errors, rel, allowed_kinds):
    pts = load(rel)
    if not isinstance(pts, list) or not pts:
        errors.append("{}: 必须是非空数组".format(rel))
        return
    for i, p in enumerate(pts):
        where = "{}[{}] ({})".format(rel, i, p.get("name") if isinstance(p, dict) else "?")
        if not isinstance(p, dict):
            errors.append("{}: 必须是对象".format(where))
            continue
        for f in ["name", "coords", "kind"]:
            if f not in p:
                errors.append("{}: 缺字段 {}".format(where, f))
        if p.get("kind") not in allowed_kinds:
            errors.append("{}: kind = {!r} 不在 {}".format(where, p.get("kind"), allowed_kinds))
        if "coords" in p:
            check_coords(errors, where, p["coords"])
    print("  {:<34} {:>3} 条  注记点".format(rel, len(pts)))


def check_metro(errors):
    """校验 data/map/metro/ 的线路与站点，并和 bars.json 的 metro 文本交叉核对。

    stations.json 故意不带 lines 字段（所属线路由 lines.json 反查派生），所以这里
    只能顺着 lines.json 的 stations 引用去查，孤儿站另行报错。
    """
    lines = load(METRO_LINES)
    stations = load(METRO_STATIONS)
    if not isinstance(lines, list) or not lines:
        errors.append("{}: 必须是非空裸数组".format(METRO_LINES))
        return
    if not isinstance(stations, list) or not stations:
        errors.append("{}: 必须是非空裸数组".format(METRO_STATIONS))
        return

    # bbox 从 roads.json 实时算，绝不硬编码 —— 以后路网扩边，这里会跟着变
    roads = load(ROADS_JSON)
    if not isinstance(roads, list) or not roads:
        errors.append("{}: 无法从路网计算 bbox（顶层不是非空数组）".format(ROADS_JSON))
        return
    pts = [p for r in roads if isinstance(r, dict) for p in (r.get("path") or [])]
    if not pts:
        errors.append("{}: 无法取到路网顶点，不能计算 bbox".format(ROADS_JSON))
        return
    lat0, lat1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lng0, lng1 = min(p[1] for p in pts), max(p[1] for p in pts)

    def in_bbox(where, coord):
        if not (isinstance(coord, list) and len(coord) == 2
                and all(isinstance(x, (int, float)) for x in coord)):
            errors.append("{}: 坐标必须是 [lat, lng] 数字对，实际 {!r}".format(where, coord))
            return
        if not (lat0 <= coord[0] <= lat1 and lng0 <= coord[1] <= lng1):
            errors.append("{}: 坐标 {} 超出 roads.json bbox（lat {}~{} / lng {}~{}）".format(
                where, coord, lat0, lat1, lng0, lng1))

    # ---------- 站点：id 唯一、形状、坐标在 bbox 内 ----------
    st_ids = set()
    for i, s in enumerate(stations):
        where = "{}[{}]".format(METRO_STATIONS, i)
        if not isinstance(s, dict):
            errors.append("{}: 必须是对象".format(where))
            continue
        where = "{} ({})".format(where, s.get("name") or s.get("id") or "?")
        for f in ["id", "name", "coords"]:
            if f not in s:
                errors.append("{}: 缺字段 {}".format(where, f))
        sid = s.get("id")
        if not sid:
            errors.append("{}: id 为空".format(where))
        elif sid in st_ids:
            errors.append("{}: id 重复 {}".format(where, sid))
        else:
            st_ids.add(sid)
        if "coords" in s:
            in_bbox(where + " coords", s["coords"])

    # ---------- 线路：id 唯一、color 合法、path 与 stations 引用 ----------
    line_ids = set()
    for i, l in enumerate(lines):
        where = "{}[{}]".format(METRO_LINES, i)
        if not isinstance(l, dict):
            errors.append("{}: 必须是对象".format(where))
            continue
        where = "{} ({})".format(where, l.get("name") or l.get("id") or "?")
        for f in ["id", "name", "color", "path", "stations"]:
            if f not in l:
                errors.append("{}: 缺字段 {}".format(where, f))
        lid = l.get("id")
        if not lid:
            errors.append("{}: id 为空".format(where))
        elif lid in line_ids:
            errors.append("{}: id 重复 {}".format(where, lid))
        else:
            line_ids.add(lid)

        if "color" in l and not (isinstance(l["color"], str) and COLOR_HEX.match(l["color"])):
            errors.append("{}: color 必须是 #RRGGBB，实际 {!r}".format(where, l["color"]))

        path = l.get("path")
        if not (isinstance(path, list) and len(path) >= 2):
            errors.append("{}: path 至少要有 2 个点，实际 {}".format(
                where, len(path) if isinstance(path, list) else path))
        else:
            for p in path:
                in_bbox(where + " path", p)

        refs = l.get("stations")
        if not (isinstance(refs, list) and len(refs) >= 2):
            errors.append("{}: stations 至少引用 2 个站，实际 {}".format(
                where, len(refs) if isinstance(refs, list) else refs))
        else:
            for sid in refs:
                if sid not in st_ids:
                    errors.append("{}: 引用了不存在的站 {!r}（悬空引用）".format(where, sid))

    # ---------- 孤儿站：每个站至少被一条线引用 ----------
    used = Counter(x for l in lines if isinstance(l, dict) for x in (l.get("stations") or []))
    for s in stations:
        sid = s.get("id") if isinstance(s, dict) else None
        if sid and sid not in used and sid not in PLANNED_STATIONS:
            errors.append("{}: 孤儿站 {}（不被任何线路引用，也不在 PLANNED_STATIONS 白名单里）".format(
                METRO_STATIONS, sid))
    transfers = sum(1 for n in used.values() if n > 1)

    # ---------- 交叉校验：bars.json 的 metro 里提到的线号都必须有对应线路 ----------
    known = set()
    for l in lines:
        m = re.match(r"^m_(\d+)$", (l.get("id") if isinstance(l, dict) else "") or "")
        if m:
            known.add(int(m.group(1)))
    referenced = set()
    for r in load("data/venues/bars.json"):
        for m in METRO_REF.finditer(r.get("metro") or ""):
            referenced.update(int(n.strip()) for n in m.group(1).split("/"))
    for n in sorted(referenced - known):
        if n in MISSING_LINES:
            print("  ⚠ SKIP 地铁交叉校验：bars.json 提到 {} 号线，但 lines.json 故意不收录 —— {}".format(
                n, MISSING_LINES[n]))
        else:
            errors.append("bars.json 的 metro 提到 {} 号线，但 lines.json 里没有对应线路，"
                          "且不在 MISSING_LINES 白名单里 —— 请补数据，或显式加白名单并写明理由".format(n))

    print("  {:<34} {:>3} 条  地铁线路".format(METRO_LINES, len(lines)))
    print("  {:<34} {:>3} 条  地铁站点（换乘 {} / 引用 {} 次）".format(
        METRO_STATIONS, len(stations), transfers, sum(used.values())))


def validate_all(verbose=True):
    """返回错误列表；空列表表示通过。"""
    errors = []
    if verbose:
        print("校验数据源：")
    for rel, cfg in SCHEMAS.items():
        if not os.path.exists(os.path.join(ROOT, rel)):
            errors.append("缺少数据文件: " + rel)
            continue
        try:
            check_records(errors, rel, cfg)
        except json.JSONDecodeError as e:
            errors.append("{}: JSON 解析失败 {}".format(rel, e))
    for checker in (check_city_guides, check_guide_metadata, check_atlas_pages):
        try:
            checker(errors)
        except (OSError, json.JSONDecodeError) as e:
            errors.append("指南资料读取失败: {}".format(e))
    try:
        check_roads(errors)
    except json.JSONDecodeError as e:
        errors.append("{}: JSON 解析失败 {}".format(ROADS_JSON, e))
    try:
        check_metro(errors)
    except json.JSONDecodeError as e:
        errors.append("{}: JSON 解析失败 {}".format(METRO_LINES, e))
    try:
        check_merged(errors, verbose=verbose)
    except (json.JSONDecodeError, ValueError) as e:
        errors.append("合并 bichi/michelin 失败: {}".format(e))
    for rel in AREA_FILES:
        if os.path.exists(os.path.join(ROOT, rel)):
            check_points(errors, rel, AREA_KINDS)
    for rel in LANDMARK_FILES:
        if os.path.exists(os.path.join(ROOT, rel)):
            check_points(errors, rel, LANDMARK_KINDS)
    return errors


def main():
    errors = validate_all()
    if errors:
        print("\n发现 {} 个问题：".format(len(errors)))
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print("\n数据校验通过。")


if __name__ == "__main__":
    main()
