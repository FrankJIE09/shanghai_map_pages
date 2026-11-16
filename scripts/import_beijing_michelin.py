#!/usr/bin/env python3
"""Import the official Beijing 2027 Starred + Bib Gourmand selection.

Maintenance-only command; not part of the offline site build. Requires curl and
beautifulsoup4. All coordinates, names, prices and addresses come from Michelin's
listing pages and Restaurant JSON-LD, never from geocoding guesses.

    python3 scripts/import_beijing_michelin.py --verified-at 2026-11-16

Responses are cached in a temporary directory. Use --cache-dir to reuse an
explicit cache; remove that cache when deliberately performing a fresh import.
The importer refuses to write partial data or a different guide edition.
"""
import argparse
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://guide.michelin.com"
LIST_ROOT = BASE + "/sg/zh_CN/beijing-municipality/beijing/restaurants/"
EXPECTED_COUNTS = {"3": 2, "2": 5, "1": 26, "bib": 32}
CATEGORIES = {"THREE_STARS": "3", "TWO_STARS": "2", "ONE_STAR": "1", "BIB_GOURMAND": "bib"}
CHINESE_AWARDS = {"三星": "THREE_STARS", "二星": "TWO_STARS", "一星": "ONE_STAR", "必比登": "BIB_GOURMAND"}
NEW_BIB_IDS = {"1253080", "1252071", "1248186", "1248181", "1247544", "1250497", "1252039"}


def fetch(url, cache_file):
    if cache_file.exists() and cache_file.stat().st_size:
        return BeautifulSoup(cache_file.read_text(encoding="utf-8"), "html.parser")
    for attempt in range(3):
        result = subprocess.run(
            ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "45", url],
            capture_output=True, check=False,
        )
        if result.returncode == 0 and len(result.stdout) > 1000:
            html = result.stdout.decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            if soup.select_one("[data-id][data-lat][data-lng], script[type='application/ld+json']"):
                cache_file.write_text(html, encoding="utf-8")
                return soup
        if attempt < 2:
            time.sleep(1 + attempt)
    raise RuntimeError("No usable official HTML received: " + url)


def listing(kind, cache):
    soup = fetch(LIST_ROOT + kind, cache / (kind + ".html"))
    rows = []
    for card in soup.select("[data-id][data-lat][data-lng]"):
        anchor = card.select_one("h3 a")
        if not anchor:
            continue
        url = urljoin(BASE, anchor.get("href", ""))
        # The page footer contains unrelated Singapore recommendations.
        if "/beijing-municipality/beijing/restaurant/" not in url:
            continue
        award = card.get("data-map-pin-name")
        if award not in CATEGORIES:
            raise ValueError("Missing official distinction: " + url)
        score = card.select(".card__menu-footer--score")[-1].get_text(" ", strip=True)
        price, cuisine = [part.strip() for part in score.split("·", 1)]
        if not re.fullmatch("¥{1,4}", price):
            raise ValueError("Unexpected official price band: " + score)
        rows.append({
            "id": card["data-id"], "key": "beijing_" + card["data-id"],
            "name": anchor.get_text(" ", strip=True), "url": url,
            "lat": float(card["data-lat"]), "lng": float(card["data-lng"]),
            "award": award, "category": CATEGORIES[award], "price": price,
            "cuisine": cuisine,
        })
    return rows


def detail(row, cache):
    soup = fetch(row["url"], cache / (row["id"] + ".html"))
    restaurant = None
    for script in soup.select('script[type="application/ld+json"]'):
        payload = json.loads(script.get_text())
        candidates = payload if isinstance(payload, list) else [payload]
        restaurant = next((item for item in candidates if item.get("@type") == "Restaurant"), restaurant)
    if not restaurant:
        raise ValueError("Missing Restaurant JSON-LD: " + row["url"])
    official_award = restaurant.get("award", {})
    if official_award.get("dateAwarded") != "2027":
        raise ValueError("Expected the 2027 guide: " + row["url"])
    label = official_award.get("awardFor", "")
    award = next((value for text, value in CHINESE_AWARDS.items() if text in label), None)
    if award != row["award"]:
        raise ValueError("Listing/detail award mismatch: " + row["url"])
    address = restaurant["address"]["streetAddress"]
    district = re.match(r"(?:北京市)?([^区市]{1,8}区)", address)
    lat, lng = float(restaurant["latitude"]), float(restaurant["longitude"])
    if not 39.4 <= lat <= 41.1 or not 115.4 <= lng <= 117.6:
        raise ValueError("Official coordinate outside Beijing: " + row["url"])
    row.update({"name": restaurant["name"], "address": address,
                "district": district.group(1) if district else "",
                "phone": restaurant.get("telephone", ""), "year": "2027",
                "lat": lat, "lng": lng})
    # These annual changes are explicitly documented in Michelin's release.
    if row["id"] == "1210036":
        row["distinctionChange"] = "promoted"
    elif row["id"] == "1247546" or row["id"] in NEW_BIB_IDS:
        row["distinctionChange"] = "new"
    print("  " + row["name"], flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-at", default=date.today().isoformat())
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    date.fromisoformat(args.verified_at)
    cache = args.cache_dir or Path(tempfile.mkdtemp(prefix="beijing-michelin-"))
    cache.mkdir(parents=True, exist_ok=True)
    print("Official HTML cache: " + str(cache), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        groups = list(pool.map(lambda kind: listing(kind, cache), ["all-starred", "bib-gourmand"]))
    rows = [row for group in groups for row in group]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate official restaurant IDs")
    if dict(Counter(row["category"] for row in rows)) != EXPECTED_COUNTS:
        raise ValueError("Incomplete or changed official annual list: " + str(Counter(row["category"] for row in rows)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda row: detail(row, cache), rows))
    rows.sort(key=lambda row: ({"3": 0, "2": 1, "1": 2, "bib": 3}[row["category"]], row["name"]))
    metadata = {
        "edition": "2027", "announcedAt": "2026-10-27", "verifiedAt": args.verified_at,
        "scope": "北京33家星级餐厅与32家必比登推介；不含42家米其林入选餐厅及天津餐厅",
        "counts": EXPECTED_COUNTS,
        "sources": [
            {"label": "米其林中国：2027北京天津指南正式发布", "url": "https://www.michelin.com.cn/news/2026/1027.html"},
            {"label": "米其林官方：2027北京天津指南分类统计", "url": "https://guide.michelin.com/en/article/michelin-guide-ceremony/michelin-guide-beijing-tianjin-2027"},
            {"label": "米其林官方：北京全部星级餐厅", "url": LIST_ROOT + "all-starred"},
            {"label": "米其林官方：北京必比登推介", "url": LIST_ROOT + "bib-gourmand"},
        ],
        "verificationNote": "逐店核对米其林官方目录与餐厅页：名称、奖项、2027年度、价位档位、菜系、中文地址、联系电话与官方经纬度。行政区从官方中文地址提取。仅为指南资料核验，不代表餐厅实时营业或有可订座位；未推算人均消费。绿星及未明确记载的年度奖项变化不作推断。",
    }
    missing_districts = [row["name"] for row in rows if not row["district"]]
    if missing_districts:
        metadata["verificationNote"] += " 以下门店官方地址未明确行政区，保留为空：" + "、".join(missing_districts) + "。"
    dest = ROOT / "data/venues/beijing-michelin.json"
    guide = ROOT / "data/guides/beijing.json"
    guide.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    guide.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote {} restaurants: {}".format(len(rows), dict(Counter(row["category"] for row in rows))), flush=True)


if __name__ == "__main__":
    main()
