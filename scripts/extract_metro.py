#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OpenStreetMap（Overpass API）抽取上海地铁核心区的线路与车站，生成两个「基建数据」文件：

    data/map/metro/lines.json       裸顶层数组，每条线一条记录（id/name/color/path/stations）
    data/map/metro/stations.json    裸顶层数组，每个物理站一条记录（id/name/coords）

形状与 data/map/roads.json 同构。这是**维护脚本**：render.sh / build.py 都不会调用它，
只在「地铁数据需要更新」（新线开通、站名更名）时手动运行一次，然后提交生成的两个 JSON。

用法
----
    python3 scripts/extract_metro.py                  # 查询 Overpass 并写盘
    python3 scripts/extract_metro.py --cache raw.json # 同时把 Overpass 原始响应存下来
    python3 scripts/extract_metro.py --raw raw.json   # 用已存响应离线重跑（同一快照结果一致）
    python3 scripts/extract_metro.py --check          # 只校验已生成的两个 JSON，不联网

数据 provenance —— Overpass 查询语句原文
----------------------------------------
    [out:json][timeout:600];
    rel[type=route][route=subway](30.60,120.80,31.90,122.20)->.r;
    .r out body;
    node(r.r)->.s;
    .s out body;

    POST https://overpass-api.de/api/interpreter
    User-Agent: shanghai-map-pages/1.0 (metro data extraction)

查询范围是「大上海」（与 validate_data.py 的上海范围一致），最后再按本项目的核心区 bbox
裁剪，保证脚本将来还能复用到更大的范围。

口径（改这几条等于改数据，改前先想清楚）
----------------------------------------
1. **覆盖范围**：与 data/map/roads.json 完全一致的 bbox（下称「核心区」）。范围外的站一律不收。
2. **选 relation**：同一线号在 OSM 里通常有两条（上下行）甚至更多（小交路、苏州 11 号线同名）。
   只保留 `network` 为上海地铁的 relation，取 stop 成员最多的那条作主；并列时取 relation id 最小的。
   结果对同一份 OSM 快照完全确定（见 --cache / --raw）。
3. **站序**：直接用主 relation 里 role 以 stop 开头的成员的先后顺序。这是唯一的真相源。
4. **裁剪**：两端落在核心区外的站直接丢掉，保留边界内最后一个真实站作端点，不做插值。
   - 环线（4 号线，首尾同一站）会先把首尾重复站合并，再旋转站序，让核心区内的站连成一段不跨断点。
   - 个别线路会「出核心区再回来」（如 7 号线在云台路一带），此时按原顺序保留全部区内站，
     相邻保留站之间用直线连接（与全线一律「相邻站直连」的口径一致），报告里会列出这类情况。
5. **折线几何**：不抄 OSM route=subway 里 way 成员的原始几何（无序、有方向翻转/断链/环线问题），
   一律用「站序 + 相邻站直连」生成。渲染时 lineJoin:'round' 足够掩盖直连折角。
6. **换乘合并**：同一物理站在不同 relation 里是不同 node（上海地铁各线的 stop_position 节点不共享），
   所以只能按**站名**合并成 stations.json 的同一记录。合并后的唯一坐标取该站所有真实节点里
   「到同组其它节点最大距离最小」的那个（medoid，并列取先出现的），只挑真实坐标、不做平均，
   避免造出不在站台上的点。lines.json 的 path 顶点一律用这个合并坐标，
   保证「线严格穿过站点、不会从站旁边几十米掠过」；代价是换乘站在各线上的平台偏移
   （实测最大 485 m，见曹杨路）被折线吸收。两条线同名但相距过远时会打印告警供人工复核。
   station 记录刻意不含 lines / 换乘标记：lines 可由 lines.json 反查，换乘 = 被引用线路数 > 1。
7. **id**：`s_` + 站名逐字全拼小写、无声调、以 `_` 连接（如 上海火车站 → s_shang_hai_huo_che_zhan）。
   pypinyin 的短语/多音字判定会随版本变化，所以最终 id 表固化在下面的 STATION_IDS 里，
   脚本运行时不依赖任何第三方库：换 id 表 = 换 id，绝不可能「因为装了新版拼音库就全体漂移」。
   新增车站时脚本会报错并提示怎么补这一行。
8. **颜色**：优先取该 route relation 的 colour/color 标签（OSM 里 14 条线全部有，且带 colour:ref=PANTONE 号）；
   没有才回落到权威来源人工核对。归一化成 6 位大写十六进制。
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "map", "metro")
LINES_JSON = os.path.join(OUT_DIR, "lines.json")
STATIONS_JSON = os.path.join(OUT_DIR, "stations.json")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "shanghai-map-pages/1.0 (metro data extraction)"

# 与 data/map/roads.json 实测范围一致（lat_min, lat_max, lng_min, lng_max）
BBOX = (31.1824, 31.2812, 121.3907, 121.5011)
# 边界处允许的浮点容差（自检用）
TOL = 1e-9

# Overpass 查询原文（provenance，见模块 docstring）
QUERY = """[out:json][timeout:600];
rel[type=route][route=subway](30.60,120.80,31.90,122.20)->.r;
.r out body;
node(r.r)->.s;
.s out body;
"""

# 需要覆盖的线号（来自 data/venues/bars.json 的 metro 字段实测统计：1..15 去掉 5 号线）
LINE_ORDER = ["1", "2", "3", "4", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]

# 只认上海地铁自己的 relation：苏州轨道交通也有 ref=11 的线路，且 colour 完全不同
SHANGHAI_METRO = {"上海地铁", "Shanghai Metro"}

# 站名 -> station id。由 pypinyin 0.55.0 生成并逐条人工校对（含多音字，如 长风公园 = cháng 而非 zhǎng）。
# 固化在这里而不是运行时算：id 必须可复现、与 pypinyin 版本无关。
STATION_IDS = {
    "延长路": "s_yan_chang_lu",
    "中山北路": "s_zhong_shan_bei_lu",
    "上海火车站": "s_shang_hai_huo_che_zhan",
    "汉中路": "s_han_zhong_lu",
    "新闸路": "s_xin_zha_lu",
    "人民广场": "s_ren_min_guang_chang",
    "一大会址·黄陂南路": "s_yi_da_hui_zhi_huang_pi_nan_lu",
    "陕西南路": "s_shan_xi_nan_lu",
    "常熟路": "s_chang_shu_lu",
    "衡山路": "s_heng_shan_lu",
    "徐家汇": "s_xu_jia_hui",
    "上海体育馆": "s_shang_hai_ti_yu_guan",
    "陆家嘴": "s_lu_jia_zui",
    "南京东路": "s_nan_jing_dong_lu",
    "南京西路": "s_nan_jing_xi_lu",
    "静安寺": "s_jing_an_si",
    "江苏路": "s_jiang_su_lu",
    "中山公园": "s_zhong_shan_gong_yuan",
    "娄山关路": "s_lou_shan_guan_lu",
    "虹口足球场": "s_hong_kou_zu_qiu_chang",
    "东宝兴路": "s_dong_bao_xing_lu",
    "宝山路": "s_bao_shan_lu",
    "中潭路": "s_zhong_tan_lu",
    "镇坪路": "s_zhen_ping_lu",
    "曹杨路": "s_cao_yang_lu",
    "金沙江路": "s_jin_sha_jiang_lu",
    "延安西路": "s_yan_an_xi_lu",
    "虹桥路": "s_hong_qiao_lu",
    "宜山路": "s_yi_shan_lu",
    "临平路": "s_lin_ping_lu",
    "南浦大桥": "s_nan_pu_da_qiao",
    "西藏南路": "s_xi_zang_nan_lu",
    "鲁班路": "s_lu_ban_lu",
    "大木桥路": "s_da_mu_qiao_lu",
    "东安路": "s_dong_an_lu",
    "上海体育场": "s_shang_hai_ti_yu_chang",
    "海伦路": "s_hai_lun_lu",
    "大华三路": "s_da_hua_san_lu",
    "新村路": "s_xin_cun_lu",
    "岚皋路": "s_lan_gao_lu",
    "长寿路": "s_chang_shou_lu",
    "昌平路": "s_chang_ping_lu",
    "肇嘉浜路": "s_zhao_jia_bang_lu",
    "龙华中路": "s_long_hua_zhong_lu",
    "云台路": "s_yun_tai_lu",
    "中华艺术宫": "s_zhong_hua_yi_shu_gong",
    "陆家浜路": "s_lu_jia_bang_lu",
    "老西门": "s_lao_xi_men",
    "大世界": "s_da_shi_jie",
    "曲阜路": "s_qu_fu_lu",
    "中兴路": "s_zhong_xing_lu",
    "西藏北路": "s_xi_zang_bei_lu",
    "曲阳路": "s_qu_yang_lu",
    "四平路": "s_si_ping_lu",
    "嘉善路": "s_jia_shan_lu",
    "打浦桥": "s_da_pu_qiao",
    "马当路": "s_ma_dang_lu",
    "小南门": "s_xiao_nan_men",
    "伊犁路": "s_yi_li_lu",
    "宋园路": "s_song_yuan_lu",
    "交通大学": "s_jiao_tong_da_xue",
    "上海图书馆": "s_shang_hai_tu_shu_guan",
    "一大会址·新天地": "s_yi_da_hui_zhi_xin_tian_di",
    "豫园": "s_yu_yuan",
    "天潼路": "s_tian_tong_lu",
    "四川北路": "s_si_chuan_bei_lu",
    "邮电新村": "s_you_dian_xin_cun",
    "隆德路": "s_long_de_lu",
    "枫桥路": "s_feng_qiao_lu",
    "真如": "s_zhen_ru",
    "上海西站": "s_shang_hai_xi_zhan",
    "国际客运中心": "s_guo_ji_ke_yun_zhong_xin",
    "世博大道": "s_shi_bo_da_dao",
    "世博会博物馆": "s_shi_bo_hui_bo_wu_guan",
    "淮海中路": "s_huai_hai_zhong_lu",
    "自然博物馆": "s_zi_ran_bo_wu_guan",
    "江宁路": "s_jiang_ning_lu",
    "武宁路": "s_wu_ning_lu",
    "武定路": "s_wu_ding_lu",
    "中宁路": "s_zhong_ning_lu",
    "铜川路": "s_tong_chuan_lu",
    "吴中路": "s_wu_zhong_lu",
    "姚虹路": "s_yao_hong_lu",
    "红宝石路": "s_hong_bao_shi_lu",
    "长风公园": "s_chang_feng_gong_yuan",
    "大渡河路": "s_da_du_he_lu",
    "梅岭北路": "s_mei_ling_bei_lu",
}


# --------------------------------------------------------------------------
# Overpass
# --------------------------------------------------------------------------

def fetch_overpass(query=QUERY):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data,
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)


def load_snapshot(elements):
    """把 Overpass 响应拆成 relation / node 索引。"""
    rels = {}
    nodes = {}
    for e in elements:
        if e.get("type") == "relation":
            rels[e["id"]] = e
        elif e.get("type") == "node":
            nodes[e["id"]] = e
    return rels, nodes


def pick_relation(rels, line):
    """同一线号选主 relation：上海地铁、stop 成员最多、并列取 id 最小。"""
    cands = []
    for r in rels.values():
        tags = r.get("tags", {})
        if str(tags.get("ref", "")).replace("号线", "") != line:
            continue
        if tags.get("network:zh") in SHANGHAI_METRO or tags.get("network:en") in SHANGHAI_METRO:
            cands.append(r)
    if not cands:
        return None
    def key(r):
        stops = sum(1 for m in r["members"] if m["role"].startswith("stop"))
        return (-stops, r["id"])
    return min(cands, key=key)


def stop_sequence(rel, nodes):
    """relation 里 role 以 stop 开头的 node 成员，按原始顺序 → [{name, coords, node, role}, ...]

    只认 node 成员：platform（way）与空 role 的 way 成员不参与站序，它们是无序的。
    """
    seq = []
    for m in rel["members"]:
        if m["type"] != "node" or not m["role"].startswith("stop"):
            continue
        n = nodes.get(m["ref"])
        if n is None:
            raise SystemExit("relation {} 的 stop 节点 {} 不在响应里".format(rel["id"], m["ref"]))
        name = n.get("tags", {}).get("name")
        if not name:
            raise SystemExit("节点 {} 没有 name，无法生成 station".format(n["id"]))
        seq.append({"name": name, "coords": [n["lat"], n["lon"]],
                    "node": n["id"], "role": m["role"]})
    return seq


def in_bbox(coords):
    return (BBOX[0] - TOL <= coords[0] <= BBOX[1] + TOL and
            BBOX[2] - TOL <= coords[1] <= BBOX[3] + TOL)


def clip_and_order(seq):
    """把站序裁到核心区，返回 (区内站序, is_loop, 源序号)。

    - 非环线：按原顺序保留区内站（两端被裁掉；若线路进出核心区导致中间有空洞，
      也照样保留全部区内站，相邻保留站直连 —— 见模块 docstring 第 4 条）。
    - 环线（首尾同一 node）：先把首尾重复站合并，再旋转到「最大空洞之后」开始，
      使区内站连成一段，避免用一条横穿核心区的假直线去闭合环。
    """
    loop = len(seq) > 1 and seq[0]["node"] == seq[-1]["node"]
    core = seq[:-1] if loop else seq
    idx = [i for i, x in enumerate(core) if in_bbox(x["coords"])]
    if not idx:
        return [], loop, []
    if loop:
        n = len(core)
        # 最大的环形空洞出现在 idx[g] 与 idx[g+1] 之间；把这一段放到折线的「两端」，
        # 即从空洞之后那个站开始，这样区内站在折线上连续、不会凭空拉一条横穿核心区的线。
        _, g = max((((idx[(k + 1) % len(idx)] - idx[k]) % n), k)
                   for k in range(len(idx)))
        k = (g + 1) % len(idx)
        idx = idx[k:] + idx[:k]
    out, src = [], []
    for i in idx:
        if out and out[-1]["node"] == core[i]["node"]:
            continue  # 环线首尾合并后可能出现的重复
        out.append(core[i])
        src.append(i)
    return out, loop, src


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------

def normalize_color(raw):
    """colour 标签归一化成 #RRGGBB（6 位大写）。"""
    if not raw:
        return None
    c = raw.strip().lstrip("#").upper()
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6 or any(ch not in "0123456789ABCDEF" for ch in c):
        return None
    return "#" + c


def station_id(name):
    try:
        return STATION_IDS[name]
    except KeyError:
        raise SystemExit(
            "station id 表里没有站名 {!r} —— 这是新站或改名了。\n"
            "请把它加进 scripts/extract_metro.py 的 STATION_IDS（`s_` + 逐字全拼小写、"
            "以 `_` 连接，多音字人工核一下），再重跑。".format(name))


def build(rels, nodes, verbose=True):
    """返回 (lines, stations, station_occ, diag)。"""
    station_occ = {}   # name -> [{"line":..., "coords":..., "node":...}, ...]
    per_line = {}      # line -> kept 站序
    diag = {"picked": {}, "clipped": {}, "loop": {}, "no_station": []}

    for line in LINE_ORDER:
        rel = pick_relation(rels, line)
        if rel is None:
            raise SystemExit("Overpass 响应里找不到 {} 号线的上海地铁 relation".format(line))
        seq = stop_sequence(rel, nodes)
        kept, loop, src = clip_and_order(seq)
        diag["picked"][line] = {
            "rel": rel["id"],
            "name": rel["tags"].get("name"),
            "color": normalize_color(rel["tags"].get("colour") or rel["tags"].get("color")),
            "color_ref": rel["tags"].get("colour:ref"),
            "stop_count": len(seq),
        }
        diag["loop"][line] = loop
        if not kept:
            diag["no_station"].append(line)
            if verbose:
                print("  ! {} 号线在核心区内没有任何车站，已跳过".format(line))
            continue

        # 「跳站」诊断：相邻两个保留站在源 relation 里并不相邻（中间隔了被裁掉的站），
        # 折线会直接用一段直线跨过去，需要人工确认是否可以接受。环线按环形取差。
        n_core = len(seq) - 1 if loop else None
        jumps = []
        for (ia, xa), (ib, xb) in zip(zip(src, kept), zip(src[1:], kept[1:])):
            step = (ib - ia) % n_core if loop else ib - ia
            if step != 1:
                jumps.append({"from": xa["name"], "to": xb["name"],
                              "skipped": step - 1,
                              "dist_m": round(haversine(xa["coords"], xb["coords"]))})
        # 环线的最后一个成员是首站的人工副本（seq[0] == seq[-1]），不算被裁掉
        body = seq[:-1] if loop else seq
        diag["clipped"][line] = [x["name"] for i, x in enumerate(body)
                                 if i not in set(src)]
        diag.setdefault("jumps", {})[line] = jumps

        for x in kept:
            station_occ.setdefault(x["name"], []).append(
                {"line": line, "coords": x["coords"], "node": x["node"]})
        per_line[line] = kept

    # 合并后的唯一坐标：取「到同组其它真实节点最大距离最小」的那个真实节点（medoid），
    # 并列时取第一次出现。只用真实坐标、不做平均，避免造出不在站台上的点。
    canonical = {}
    for name, occ in station_occ.items():
        best = min(range(len(occ)),
                   key=lambda i: (max(haversine(occ[i]["coords"], o["coords"]) for o in occ), i))
        canonical[name] = list(occ[best]["coords"])

    stations = [{"id": station_id(name), "name": name, "coords": canonical[name]}
                for name in station_occ]
    stations.sort(key=lambda s: s["id"])

    lines = []
    for line in LINE_ORDER:
        kept = per_line.get(line)
        if not kept:
            continue
        lines.append({
            "id": "m_" + line,
            "name": line + "号线",
            "color": diag["picked"][line]["color"],
            # path 顶点一律用合并后的唯一坐标，保证「线严格穿过站点」；
            # 代价是换乘站在不同线路上的平台偏移（实测最大 485 m）被折线吸收。
            "path": [list(canonical[x["name"]]) for x in kept],
            "stations": [station_id(x["name"]) for x in kept],
        })
    return lines, stations, station_occ, diag


# --------------------------------------------------------------------------
# 写盘 / 自检
# --------------------------------------------------------------------------

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(lines=None, stations=None, verbose=True):
    """验收口径：id 唯一、无悬空引用、无孤儿站、path >= 2 点、坐标全在 bbox 内。"""
    if lines is None:
        lines = load_json(LINES_JSON)
    if stations is None:
        stations = load_json(STATIONS_JSON)
    errors = []

    if not isinstance(lines, list) or not lines:
        errors.append("lines.json: 必须是非空裸顶层数组")
    if not isinstance(stations, list) or not stations:
        errors.append("stations.json: 必须是非空裸顶层数组")
    if errors:
        return errors, None

    sid = {}
    scoords = {}
    for i, s in enumerate(stations):
        where = "stations.json[{}]".format(i)
        for f in ("id", "name", "coords"):
            if f not in s:
                errors.append("{}: 缺字段 {}".format(where, f))
        if s.get("id") in sid:
            errors.append("{}: id 重复 {}".format(where, s.get("id")))
        sid[s.get("id")] = s.get("name")
        scoords[s.get("id")] = s.get("coords")
        c = s.get("coords")
        if not (isinstance(c, list) and len(c) == 2):
            errors.append("{}: coords 必须是 [lat, lng]".format(where))
        elif not in_bbox(c):
            errors.append("{} {}: coords {} 超出核心区 bbox {}".format(
                where, s.get("name"), c, BBOX))
        if not str(s.get("id", "")).startswith("s_"):
            errors.append("{}: id 必须 s_ 前缀".format(where))

    seen_line_ids = set()
    ref_count = {}
    for i, r in enumerate(lines):
        where = "lines.json[{}]".format(i)
        for f in ("id", "name", "color", "path", "stations"):
            if f not in r:
                errors.append("{}: 缺字段 {}".format(where, f))
        if r.get("id") in seen_line_ids:
            errors.append("{}: id 重复 {}".format(where, r.get("id")))
        seen_line_ids.add(r.get("id"))
        if not str(r.get("id", "")).startswith("m_"):
            errors.append("{}: id 必须 m_ 前缀".format(where))
        color = r.get("color") or ""
        if len(color) != 7 or not color.startswith("#") or \
                any(ch not in "0123456789ABCDEF" for ch in color[1:]):
            errors.append("{}: color 必须是 6 位十六进制，实际 {!r}".format(where, color))
        path = r.get("path")
        if not (isinstance(path, list) and len(path) >= 2):
            errors.append("{} {}: path 至少 2 个点".format(where, r.get("name")))
        else:
            for p in path:
                if not (isinstance(p, list) and len(p) == 2) or not in_bbox(p):
                    errors.append("{} {}: path 点 {} 非法或超出 bbox".format(
                        where, r.get("name"), p))
        st = r.get("stations")
        if not (isinstance(st, list) and st):
            errors.append("{} {}: stations 必须是非空数组".format(where, r.get("name")))
            continue
        for x in st:
            if x not in sid:
                errors.append("{} {}: 悬空引用 {}".format(where, r.get("name"), x))
                continue
            ref_count[x] = ref_count.get(x, 0) + 1
        # 站与线必须严格对齐：path 的第 i 个点就是第 i 个站在 stations.json 里的坐标
        if isinstance(path, list) and len(path) == len(st):
            for i, x in enumerate(st):
                if x in scoords and path[i] != scoords[x]:
                    errors.append("{} {}: path[{}] 与 {} 的坐标不一致".format(
                        where, r.get("name"), i, x))

    for s in stations:
        if ref_count.get(s["id"], 0) == 0:
            errors.append("孤儿站：{} {} 没有被任何线路引用".format(s["id"], s["name"]))

    stats = None
    if verbose:
        print("每线站数：")
        for r in sorted(lines, key=lambda r: int(r["id"][2:])):
            print("  {:<6} {:>2} 站  {:<9} {}".format(
                r["name"], len(r["stations"]), r["color"], r["id"]))
        trans = [s for s in stations if ref_count.get(s["id"], 0) > 1]
        stats = {
            "lines": len(lines),
            "stations": len(stations),
            "refs": sum(len(r["stations"]) for r in lines),
            "transfers": len(trans),
        }
        print("合计：{} 条线 / {} 个站 / {} 次引用 / {} 个换乘站".format(
            stats["lines"], stats["stations"], stats["refs"], stats["transfers"]))
    return errors, stats


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="抽取上海地铁核心区的 lines/stations JSON")
    ap.add_argument("--raw", metavar="FILE", help="改用已保存的 Overpass 响应，不联网")
    ap.add_argument("--cache", metavar="FILE", help="把 Overpass 原始响应另存一份")
    ap.add_argument("--check", action="store_true", help="只校验已生成的两个 JSON")
    args = ap.parse_args()

    if args.check:
        errors, _ = check()
        if errors:
            print("自检失败，{} 个问题：".format(len(errors)))
            for e in errors:
                print("  - " + e)
            return 1
        print("自检通过。")
        return 0

    if args.raw:
        with open(args.raw, encoding="utf-8") as f:
            payload = json.load(f)
    else:
        print("查询 Overpass（{}）…".format(OVERPASS_URL))
        payload = fetch_overpass()
    if args.cache:
        write_json(args.cache, payload)

    rels, nodes = load_snapshot(payload["elements"])
    print("Overpass 响应：{} 个 relation / {} 个 node".format(len(rels), len(nodes)))

    lines, stations, station_occ, diag = build(rels, nodes)

    print("\n采用的 relation：")
    for line in LINE_ORDER:
        p = diag["picked"][line]
        print("  {}号线  rel {:<9} {:<26} colour={:<9} ({}), stop {} 个{}".format(
            line, p["rel"], p["name"] or "", p["color"] or "?", p["color_ref"] or "无",
            p["stop_count"], "，环线" if diag["loop"][line] else ""))
    print("\n被核心区裁掉的端点/中间站：")
    for line in LINE_ORDER:
        dropped = diag["clipped"].get(line) or []
        if dropped:
            print("  {}号线: {}".format(line, "、".join(dropped)))
    for line in diag["no_station"]:
        print("  {}号线: 核心区内 0 站，无法生成，已跳过".format(line))

    print("\n跨站直连（相邻保留站在源 relation 里不相邻，折线会直线跨过被裁掉的站）：")
    any_jump = False
    for line in LINE_ORDER:
        for j in diag.get("jumps", {}).get(line, []):
            any_jump = True
            print("  {}号线: {} → {} 跨过 {} 站，直线 {} m".format(
                line, j["from"], j["to"], j["skipped"], j["dist_m"]))
    if not any_jump:
        print("  无")

    print("\n同名站坐标间距（>150 m 时列出，供人工复核是否该合并）：")
    for name, occ in sorted(station_occ.items()):
        spread = max(
            (haversine(a["coords"], b["coords"]) for a in occ for b in occ), default=0)
        if spread > 150:
            print("  {:<10} {:>4.0f} m  {}".format(
                name, spread, "、".join("{}号线 {}".format(o["line"], o["node"]) for o in occ)))

    write_json(LINES_JSON, lines)
    write_json(STATIONS_JSON, stations)
    print("\n已写入：\n  {}\n  {}".format(LINES_JSON, STATIONS_JSON))

    errors, _ = check(lines, stations)
    if errors:
        print("\n自检失败，{} 个问题：".format(len(errors)))
        for e in errors:
            print("  - " + e)
        return 1
    print("\n自检通过。")
    return 0


def haversine(a, b):
    import math
    R = 6371000.0
    dlat = math.radians(b[0] - a[0])
    dlng = math.radians(b[1] - a[1])
    h = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) *
         math.cos(math.radians(b[0])) * math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


if __name__ == "__main__":
    sys.exit(main())
