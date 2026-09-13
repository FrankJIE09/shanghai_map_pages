#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 src/pages/*.html 抽取内联数据字面量 → data/*.json，并把源文件的数据区
替换为 @@BUILD:json@@ 标记，供 build.py 在构建期内联回去。

这是**一次性迁移脚本**：跑完之后源数据以 data/*.json 为准，日常改数据直接改
JSON 再跑 build.py 即可，不需要再执行本脚本。

用法：
    python3 scripts/extract_data.py            # 抽取；已存在的数据文件不覆盖
    python3 scripts/extract_data.py --force    # 覆盖已存在的数据文件
    python3 scripts/extract_data.py --dry      # 只报告将要做什么，不写盘
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jslit  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 页面 -> 配置。records 是「店铺数据」字面量；areas/landmarks 指向各自数据文件。
PAGES = {
    "bars": {
        "html": "src/pages/bars.html",
        "record_name": "VENUES",
        "record_json": "data/venues/bars.json",
        "areas": "data/map/areas/downtown.json",
        "landmarks": "data/map/landmarks/downtown.json",
        "expect_records": 37,
    },
    "bichi": {
        "html": "src/pages/bichi.html",
        "record_name": "ALL_STORES",
        "record_json": "data/venues/bichi.json",
        "areas": "data/map/areas/greater.json",
        "landmarks": "data/map/landmarks/greater.json",
        "expect_records": 59,
        "shared_areas": True,
    },
    "michelin": {
        "html": "src/pages/michelin.html",
        "record_name": "RESTAURANTS",
        "record_json": "data/venues/michelin.json",
        "areas": "data/map/areas/greater.json",
        "landmarks": "data/map/landmarks/greater.json",
        "expect_records": 86,
        "shared_areas": True,
    },
}

ROADS_JSON = "data/map/roads.json"
EXPECT_ROADS = 227
MARKER_HEAD = "/* @@BUILD:"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def marker_block(name, indent, data_rel):
    """生成注入标记块。首行不留缩进（调用处已保留原缩进），后续行带缩进。"""
    return (
        "{head}json {rel} -> {name}@@ */\n"
        "{ind}const {name} = [ /* 构建生成：勿手改，改数据请改 {rel} */ ];\n"
        "{ind}/* @@BUILD:end@@ */"
    ).format(head=MARKER_HEAD, ind=indent, name=name, rel=data_rel)


def dump_json(rel, value):
    """写开发者可读的 JSON 源：indent=2，保留字段顺序，中文不转义。"""
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已存在的数据文件")
    ap.add_argument("--dry", action="store_true", help="只报告，不写盘")
    args = ap.parse_args()

    if not os.path.exists(jslit.JS_EVAL):
        sys.exit("缺少 Node 求值器: " + jslit.JS_EVAL)

    problems = []
    extracted = {}       # page -> {name: value}
    offsets = {}         # page -> {name: 偏移信息}
    roads_digests = {}   # md5 -> [页面]
    shared_digests = {}  # md5 -> [页面]

    # ---------- 1) 抽取 ----------
    for page, cfg in PAGES.items():
        src = read(cfg["html"])
        if MARKER_HEAD in src:
            print("[跳过] {}：已经是标记形式，无需再抽取".format(page))
            continue
        names = ["MAIN_ROADS", "AREAS", "LANDMARKS", cfg["record_name"]]
        values, offs = {}, {}
        for name in names:
            try:
                loc = jslit.find_literal(src, name)
                values[name] = jslit.eval_to_json(loc["raw"])
                offs[name] = loc
            except (LookupError, ValueError) as e:
                problems.append("{} / {}: {}".format(page, name, e))
        if len(values) != len(names):
            continue
        extracted[page] = values
        offsets[page] = offs

        n = len(values[cfg["record_name"]])
        if n != cfg["expect_records"]:
            problems.append("{}: {} 有 {} 条，预期 {}".format(
                page, cfg["record_name"], n, cfg["expect_records"]))

        roads_digests.setdefault(_digest(values["MAIN_ROADS"]), []).append(page)
        if cfg.get("shared_areas"):
            shared_digests.setdefault(
                _digest({"a": values["AREAS"], "l": values["LANDMARKS"]}), []).append(page)

    if problems:
        print("抽取失败：")
        for p in problems:
            print("  - " + p)
        sys.exit(1)

    # ---------- 2) 一致性校验 ----------
    if len(roads_digests) > 1:
        sys.exit("三页的 MAIN_ROADS 内容不一致，需人工确认：{}".format(roads_digests))
    if len(shared_digests) > 1:
        sys.exit("bichi 与 michelin 的 AREAS/LANDMARKS 不一致，需人工确认：{}".format(shared_digests))

    if not extracted:
        print("没有需要抽取的内容（可能已全部迁移）。")
        return

    roads = list(extracted.values())[0]["MAIN_ROADS"]
    if len(roads) != EXPECT_ROADS:
        sys.exit("MAIN_ROADS 有 {} 条，预期 {}".format(len(roads), EXPECT_ROADS))

    # ---------- 3) 写 JSON ----------
    writes = [(ROADS_JSON, roads, "{} 条道路（三页共用）".format(len(roads)))]
    donor = extracted.get("bichi") or extracted.get("michelin")
    if donor:
        writes.append(("data/map/areas/greater.json", donor["AREAS"], "bichi/michelin 共用"))
        writes.append(("data/map/landmarks/greater.json", donor["LANDMARKS"], "bichi/michelin 共用"))
    for page, cfg in PAGES.items():
        if page not in extracted:
            continue
        vals = extracted[page]
        writes.append((cfg["record_json"], vals[cfg["record_name"]],
                       "{} 条记录".format(len(vals[cfg["record_name"]]))))
        if not cfg.get("shared_areas"):
            writes.append((cfg["areas"], vals["AREAS"], "{} 专用".format(page)))
            writes.append((cfg["landmarks"], vals["LANDMARKS"], "{} 专用".format(page)))

    for rel, value, desc in writes:
        exists = os.path.exists(os.path.join(ROOT, rel))
        tag = "[dry] " if args.dry else ""
        if exists and not args.force:
            print("[跳过] {} 已存在（加 --force 覆盖）".format(rel))
            continue
        print("{}写入 {}  ({})".format(tag, rel, desc))
        if not args.dry:
            dump_json(rel, value)

    # ---------- 4) 源文件改为标记 ----------
    for page, cfg in PAGES.items():
        if page not in extracted:
            continue
        offs = offsets[page]
        items = [
            (offs[cfg["record_name"]]["stmt_start"], offs[cfg["record_name"]]["end"],
             marker_block(cfg["record_name"], offs[cfg["record_name"]]["indent"], cfg["record_json"])),
            (offs["MAIN_ROADS"]["stmt_start"], offs["MAIN_ROADS"]["end"],
             marker_block("MAIN_ROADS", offs["MAIN_ROADS"]["indent"], ROADS_JSON)),
            (offs["AREAS"]["stmt_start"], offs["AREAS"]["end"],
             marker_block("AREAS", offs["AREAS"]["indent"], cfg["areas"])),
            (offs["LANDMARKS"]["stmt_start"], offs["LANDMARKS"]["end"],
             marker_block("LANDMARKS", offs["LANDMARKS"]["indent"], cfg["landmarks"])),
        ]
        print("{}改写 {}：4 处字面量 → 标记".format("[dry] " if args.dry else "", cfg["html"]))
        if not args.dry:
            _rewrite(cfg["html"], items)

    print("\n完成。数据源已就位，请跑 python3 build.py --check 验证。")


def _digest(value):
    return hashlib.md5(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _rewrite(rel, replacements):
    """把源 HTML 里的字面量替换为标记块。从后往前替换，避免位移互相影响。"""
    src = read(rel)
    for start, end, text in sorted(replacements, key=lambda r: -r[0]):
        src = src[:start] + text + src[end:]
    with open(os.path.join(ROOT, rel), "w", encoding="utf-8") as f:
        f.write(src)


if __name__ == "__main__":
    main()
