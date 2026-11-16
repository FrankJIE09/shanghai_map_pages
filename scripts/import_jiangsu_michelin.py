#!/usr/bin/env python3
"""Import Suzhou/Nanjing's 2026 starred and Bib Gourmand restaurants.

Uses official MICHELIN directory cards and each restaurant's JSON-LD.
Requires curl, otherwise only the Python standard library. To repeat the
verified 2026 import: python3 scripts/import_jiangsu_michelin.py
Use --refresh to refetch cached pages. Counts and edition are deliberately
pinned to the official announcement: a new edition requires review.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://guide.michelin.com'
ANNOUNCEMENT = 'https://www.michelin.com.cn/news/2026/0409.html'
CEREMONY = BASE + '/en/article/michelin-guide-ceremony/michelin-guide-shanghai-jiangsu-zhejiang'
CITIES = {
    'suzhou': {'name': '苏州', 'slug': 'suzhou_1031079', 'total': 38, 'stars': 3, 'bib': 18,
               'new': {'喜鼎家宴', '姑苏楼上', '阿成饭店', '三星羊肉馆', '柳家有梦梅', '六宜楼 (南新路)', '塘园'}, 'promoted': set()},
    'nanjing': {'name': '南京', 'slug': 'nanjing_1029511', 'total': 41, 'stars': 4, 'bib': 21,
                'new': {'无名老卤面', '崔姐小吃', '富临轩 (集庆门大街)', '致和老鸭粉丝汤', '顾家包子', '正清牛肉锅贴店'}, 'promoted': {'品宁府', '梦都会'}},
}
CATEGORIES = {'THREE_STARS': '3', 'TWO_STARS': '2', 'ONE_STAR': '1', 'BIB_GOURMAND': 'bib'}


class ListingParser(HTMLParser):
    """Read only published restaurant card attributes and text."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards, self.card, self.depth, self.score_depth = [], None, 0, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div' and all(key in attrs for key in ('data-id', 'data-lat', 'data-lng')):
            if self.card is not None:
                raise ValueError('Unexpected nested restaurant cards')
            self.card = {'id': attrs['data-id'], 'lat': float(attrs['data-lat']), 'lng': float(attrs['data-lng']),
                         'award': attrs.get('data-map-pin-name', ''), 'scores': []}
            self.depth = 1
        elif self.card is not None and tag == 'div':
            self.depth += 1
        if self.card is None:
            return
        if attrs.get('data-restaurant-name'):
            self.card['name'] = attrs['data-restaurant-name']
        if attrs.get('data-distinction') in CATEGORIES:
            self.card['award'] = attrs['data-distinction']
        href = attrs.get('href', '')
        if tag == 'a' and '/restaurant/' in href:
            self.card['url'] = href if href.startswith('https://') else BASE + href
        if 'card__menu-footer--score' in attrs.get('class', '').split():
            self.score_depth = self.depth
            self.card['scores'].append('')

    def handle_data(self, data):
        if self.card is not None and self.score_depth is not None:
            self.card['scores'][-1] += data

    def handle_endtag(self, tag):
        if self.card is None or tag != 'div':
            return
        if self.score_depth == self.depth:
            self.score_depth = None
        self.depth -= 1
        if self.depth == 0:
            self.cards.append(self.card)
            self.card = None


def fetch(url, path, refresh=False):
    if path.exists() and path.stat().st_size and not refresh:
        return path.read_text()
    for attempt in range(3):
        result = subprocess.run(['curl', '-fLsS', '--max-time', '45', url], capture_output=True, text=True)
        if result.returncode == 0 and '<html' in result.stdout:
            path.write_text(result.stdout)
            return result.stdout
        if attempt < 2:
            time.sleep(1)
    raise RuntimeError(f'Official page unavailable or empty: {url}')


def detail(row, city, cache, refresh):
    text = fetch(row['url'], cache / (row['id'] + '.html'), refresh)
    blocks = re.findall(r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', text, re.S | re.I)
    data = next((value for block in blocks if isinstance(value := json.loads(block), dict) and value.get('@type') == 'Restaurant'), None)
    if not data:
        raise ValueError(f'Missing Restaurant JSON-LD: {row["url"]}')
    if str(data.get('award', {}).get('dateAwarded')) != '2026':
        raise ValueError(f'Unexpected award edition: {row["name"]}')
    expected_award = '必比登' if row['award'] == 'BIB_GOURMAND' else '一星'
    if expected_award not in data['award']['awardFor']:
        raise ValueError(f'Listing/detail award conflict: {row["name"]}')
    for field, key in [('lat', 'latitude'), ('lng', 'longitude')]:
        if abs(row[field] - float(data[key])) > 0.0000001:
            raise ValueError(f'Listing/detail coordinate conflict: {row["name"]} {field}')
    row['name'] = data['name']
    row['address'] = data['address']['streetAddress']
    row['cuisine'] = data['servesCuisine']
    row['year'] = '2026'
    row['phone'] = data.get('telephone', '')
    row['category'] = CATEGORIES[row['award']]
    row['key'] = city + '_' + row['id']
    address = row['address'].removeprefix(CITIES[city]['name'] + '市')
    district = re.match(r'^(.{1,8}?(?:工业园区|区|市))', address)
    row['district'] = district.group(1) if district else ''
    score = next((score.strip() for score in reversed(row.pop('scores')) if '¥' in score), '')
    price = score.split('·')[0].strip()
    if not re.fullmatch('¥{1,4}', price):
        raise ValueError(f'Unexpected official price category: {row["name"]}: {price}')
    row['price'] = price
    if row['name'] in CITIES[city]['new']:
        row['distinctionChange'] = 'new'
    elif row['name'] in CITIES[city]['promoted']:
        row['distinctionChange'] = 'promoted'
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path(tempfile.gettempdir()) / 'jiangsu-michelin')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for city, spec in CITIES.items():
        url = f'{BASE}/sg/zh_CN/jiang-su/{spec["slug"]}/restaurants'
        listing = ListingParser()
        listing.feed(fetch(url, args.cache_dir / f'{city}-listing.html', args.refresh))
        city_rows = [row for row in listing.cards if f'/{spec["slug"]}/restaurant/' in row.get('url', '')]
        if len(city_rows) != spec['total']:
            raise ValueError(f'{city}: directory changed, expected {spec["total"]}, got {len(city_rows)}; review pagination/edition')
        rows = [row for row in city_rows if row['award'] in CATEGORIES]
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(lambda row: detail(row, city, args.cache_dir, args.refresh), rows))
        counts = Counter(row['category'] for row in rows)
        if counts != {'1': spec['stars'], 'bib': spec['bib']}:
            raise ValueError(f'{city}: award counts disagree with official announcement: {counts}')
        if len({row['id'] for row in rows}) != len(rows):
            raise ValueError(f'{city}: duplicate official restaurant ids')
        if not (spec['new'] | spec['promoted']).issubset({row['name'] for row in rows}):
            raise ValueError(f'{city}: missing officially announced new/promoted restaurants')
        bounds = (30.7, 32.1, 119.8, 121.4) if city == 'suzhou' else (31.2, 32.7, 118.2, 119.3)
        if not all(bounds[0] <= row['lat'] <= bounds[1] and bounds[2] <= row['lng'] <= bounds[3] for row in rows):
            raise ValueError(f'{city}: coordinates outside expected city bounds')
        rows.sort(key=lambda row: ({'3': 0, '2': 1, '1': 2, 'bib': 3}[row['category']], row['name']))
        metadata = {
            'edition': '2026', 'announcedAt': '2026-04-09', 'verifiedAt': '2026-11-16',
            'scope': f'2026沪苏浙《米其林指南》{spec["name"]}星级餐厅与必比登推介；不含{spec["total"] - len(rows)}家米其林入选餐厅',
            'counts': {'3': 0, '2': 0, '1': spec['stars'], 'bib': spec['bib']},
            'sources': [{'label': '米其林官方：2026沪苏浙指南发布及分城市统计', 'url': ANNOUNCEMENT},
                        {'label': f'米其林官方：{spec["name"]}完整餐厅目录', 'url': url},
                        {'label': '米其林官方：2026新获奖及晋级餐厅', 'url': CEREMONY}],
            'verificationNote': '逐店核对官方目录与餐厅页JSON-LD：中文店名、星级/必比登、2026版年份、地址、菜系、电话、价位档和WGS-84坐标；详情页与目录坐标一致。区名直接提取官方中文地址，未使用第三方推算；未能提取时留空。仅标记发布公告明确列出的本年度新获奖及晋级，不等同于新开业。未核实实时营业时间、临时停业或具体套餐价格，出发前请向餐厅确认。',
        }
        if city == 'suzhou':
            metadata['verificationNote'] += '“工业园区”为官方地址所用片区名称，沿用为筛选项，不将其表述为法定行政区。'
        print(f'{city}: {len(rows)} records, {dict(counts)}, missing districts: {[row["name"] for row in rows if not row["district"]]}', flush=True)
        outputs.append((city, rows, metadata))
    # Write only after both complete selections pass validation.
    (ROOT / 'data/guides').mkdir(exist_ok=True)
    for city, rows, metadata in outputs:
        (ROOT / f'data/venues/{city}-michelin.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        (ROOT / f'data/guides/{city}.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
