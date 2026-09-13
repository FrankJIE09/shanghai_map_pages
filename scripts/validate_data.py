#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 data/*.json 的结构与取值，让错误在写数据时暴露而不是在页面里。

被 build.py 作为前置检查调用，也可单独运行：
    python3 scripts/validate_data.py
"""
import json
import os
import re
import sys

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

# 上海大致范围（含崇明/金山等外围），坐标超出必然是填错了
LAT_RANGE = (30.60, 31.90)
LNG_RANGE = (120.80, 122.20)

HHMM = re.compile(r"^\d{1,2}:\d{2}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


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

    print("  {:<34} {:>3} 条  {}".format(rel, len(recs), cfg["label"]))


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
    try:
        check_roads(errors)
    except json.JSONDecodeError as e:
        errors.append("{}: JSON 解析失败 {}".format(ROADS_JSON, e))
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
