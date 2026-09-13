#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 bichi / michelin 两份店铺数据合并成「上海餐饮总览」页（eat.html）用的单份记录。

合并规则（全部可校验，不做模糊猜测）：

1. 去重：两源坐标**完全一致**（距离 0）即视为同一家店。
   实测恰好 13 对，且与 bichi 侧 `michelin != 0` 的 13 条一一对应，星级也一致
   —— 见 validate_data.check_merged 的不变量断言。两者命名不同（bichi 带门店后缀，
   米其林用官方短名），所以不能靠店名匹配。
   注意：坐标接近但不等（如 4 m、8 m）的**不合并**，实测那是不同餐厅。

2. 字段取值：有 bichi 侧就用 bichi 侧（中文描述与菜系更细、有真实人均数值），
   仅米其林收录的用官方字段。`mnemonic`（认路落脚点）米其林侧存的是地址，
   属于历史字段，米其林独有记录一律留空，避免详情卡重复显示地址。

3. 标签模型：合并成一维可多选的 `tags`。
   - 榜单：`bichi` / `saojie`，两者都在则额外给 `both`
   - 米其林：`michelin3` / `michelin2` / `michelin1` / `bib`
   `primary` 是主色分类（图标边框/角标用），取 tags 里优先级最高的一项：
       双榜 > 必吃 > 扫街 > 三星 > 二星 > 一星 > 必比登
   即：上榜门店以榜单为主色、米其林走左下角金角标；仅米其林收录的以星级为主色。
   这与 bichi 页既有画法一致，不引入第二套配色。
"""
import os

# 米其林等级 <-> 标签
LEVEL_TO_TAG = {1: "michelin1", 2: "michelin2", 3: "michelin3", -1: "bib"}
TAG_TO_LEVEL = {v: k for k, v in LEVEL_TO_TAG.items()}

# 主色分类的优先级（同时也是筛选按钮与名录分组的展示顺序）
PRIMARY_ORDER = ["both", "bichi", "saojie", "michelin3", "michelin2", "michelin1", "bib"]


def _merge_pair(b, m):
    """合并同一家店的 bichi 记录与 michelin 记录。"""
    rec = _from_bichi(b)
    rec["sources"] = ["bichi", "michelin"]
    # 米其林侧补齐榜单标签里没有的部分
    tags = set(rec["tags"]) | {m["category"]}
    rec["tags"] = [t for t in PRIMARY_ORDER if t in tags]
    rec["primary"] = _primary_of(rec["tags"])
    rec["michelin"] = _level_of(rec["tags"])
    # 米其林侧只在 bichi 侧缺内容时兜底
    if not rec["desc"]:
        rec["desc"] = m.get("desc", "")
    if not rec["cuisine"]:
        rec["cuisine"] = m.get("cuisine", "")
    if not rec["address"]:
        rec["address"] = m.get("address", "")
    if not rec["price"]:
        rec["price"] = m.get("price", "")
    if not rec["note"]:
        rec["note"] = m.get("note", "")
    rec["isNew"] = bool(rec["isNew"] or m.get("isNew"))
    # 百度 POI 身份（可选）：两边谁有就用谁，都没有则页面退化为关键词检索
    # （见 src/static/venue-links.js 的三档降级）
    for f in ("baidu_uid", "baidu_url", "baidu_uid_at"):
        if not rec.get(f) and m.get(f):
            rec[f] = m[f]
    return rec


def _from_bichi(b):
    """单条 bichi 记录 -> 合并记录。"""
    tags = []
    if b.get("bichi") and b.get("saojie"):
        tags.append("both")
    if b.get("bichi"):
        tags.append("bichi")
    if b.get("saojie"):
        tags.append("saojie")
    level = b.get("michelin", 0)
    if level:
        tags.append(LEVEL_TO_TAG[level])
    tags = [t for t in PRIMARY_ORDER if t in tags]
    return {
        "key": b["key"],
        "name": b["name"],
        "primary": _primary_of(tags),
        "tags": tags,
        "michelin": level,
        "coords": b["coords"],
        "cuisine": b.get("cuisine", ""),
        "address": b.get("address", ""),
        "price": b.get("price", ""),
        "avg": b.get("avg"),
        "desc": b.get("desc", ""),
        "mnemonic": b.get("mnemonic", ""),
        "icon": b.get("icon", "🍽️"),
        "note": b.get("note", ""),
        "isNew": bool(b.get("isNew")),
        "sources": ["bichi"],
        "baidu_uid": b.get("baidu_uid"),
        "baidu_url": b.get("baidu_url"),
        "baidu_uid_at": b.get("baidu_uid_at"),
    }


def _from_michelin(m):
    """单条 michelin 记录 -> 合并记录。"""
    tags = [t for t in PRIMARY_ORDER if t == m["category"]]
    # 米其林侧 mnemonic 存的是地址（历史字段），只有与 address 不同才是真的落脚点
    mnemonic = m.get("mnemonic", "")
    if mnemonic == m.get("address"):
        mnemonic = ""
    return {
        "key": m["key"],
        "name": m["name"],
        "primary": _primary_of(tags),
        "tags": tags,
        "michelin": _level_of(tags),
        "coords": m["coords"],
        "cuisine": m.get("cuisine", ""),
        "address": m.get("address", ""),
        "price": m.get("price", ""),
        "avg": None,                     # 米其林侧只有 ¥ 档位，没有具体人均
        "desc": m.get("desc", ""),
        "mnemonic": mnemonic,
        "icon": m.get("icon", "🍽️"),
        "note": m.get("note", ""),
        "isNew": bool(m.get("isNew")),
        "sources": ["michelin"],
        "baidu_uid": m.get("baidu_uid"),
        "baidu_url": m.get("baidu_url"),
        "baidu_uid_at": m.get("baidu_uid_at"),
    }


def _primary_of(tags):
    for t in PRIMARY_ORDER:
        if t in tags:
            return t
    raise ValueError("记录没有任何标签，无法决定主色分类: {}".format(tags))


def _level_of(tags):
    """标签 -> 米其林等级（0 表示不在米其林榜上）。"""
    for t in tags:
        if t in TAG_TO_LEVEL:
            return TAG_TO_LEVEL[t]
    return 0


def merge_sources(sources):
    """sources: [(来源名, 记录列表), ...]，来源名取 JSON 文件名（bichi / michelin）。

    返回合并后的记录列表，顺序：bichi 原有顺序优先，米其林独有记录追加在后。
    """
    data = {}
    for name, recs in sources:
        if name in data:
            raise ValueError("重复的数据源: {}".format(name))
        data[name] = recs
    unknown = set(data) - {"bichi", "michelin"}
    if unknown:
        raise ValueError("merge 只支持 bichi / michelin，收到: {}".format(sorted(unknown)))
    if "bichi" not in data or "michelin" not in data:
        raise ValueError("merge 需要同时提供 bichi 与 michelin 两份数据")

    # 按坐标完全一致建索引（浮点直接做 key；实测两源重合点逐位相同）
    # 校验器会保证同一份数据里坐标不重复，所以 coords -> 单条 即可
    by_coords = {}
    for m in data["michelin"]:
        by_coords.setdefault(tuple(m["coords"]), m)

    used = set()        # 已被合并掉的米其林记录
    out = []
    for b in data["bichi"]:
        m = by_coords.get(tuple(b["coords"]))
        if m is not None and id(m) not in used:
            used.add(id(m))
            out.append(_merge_pair(b, m))
        else:
            out.append(_from_bichi(b))

    # 剩余的米其林独有记录
    for m in data["michelin"]:
        if id(m) not in used:
            out.append(_from_michelin(m))

    return out


def load_merged(root="."):
    """从 data/venues/ 读两份源数据并合并（供校验脚本调用）。"""
    import json
    out = {}
    for name in ("bichi", "michelin"):
        path = os.path.join(root, "data", "venues", name + ".json")
        with open(path, encoding="utf-8") as f:
            out[name] = json.load(f)
    return merge_sources([("bichi", out["bichi"]), ("michelin", out["michelin"])])
