#!/usr/bin/env python3
"""Import the 2026 Hangzhou starred/Bib selection from official public pages.

Uses Python's standard library and curl. The optional HTML cache makes the import
repeatable without network requests. Fail closed if the live counts, edition,
awards or listing/detail coordinates no longer agree; review changes explicitly.

Example:
    python3 scripts/import_hangzhou_michelin.py --cache-dir /tmp/hangzhou-michelin-cache --verified-at 2026-11-16

One published Bib restaurant no longer has an official detail page. Keep its
identity in the directory with null coordinates, rather than inventing a pin.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin

BASE = 'https://guide.michelin.com'
CITY_PATH = '/zhe-jiang/hangzhou_1027184'
LISTING = BASE + '/sg/zh_CN' + CITY_PATH + '/restaurants'
EDITION = '2026'
AWARDS = {'THREE_STARS': '3', 'TWO_STARS': '2', 'ONE_STAR': '1', 'BIB_GOURMAND': 'bib'}
EXPECTED_LIVE = {'2': 2, '1': 11, 'bib': 33}
NEW_BIB_IDS = {'1245387', '1246153', '1245381', '1246056', '1246059', '1246161', '1245384', '1245386', '1246057'}
RELEASE = 'https://www.michelin.com.cn/news/2026/0409.html'
ANNUAL_LIST = 'https://www.restaurant-ranking.com/news-magazine/restaurant-guides/all-information-about-the-michelin-guide/guide-michelin-china/michelin-guide-shanghai-jiangsu-zhejiang/'
PREVIOUS_PDF = 'https://dgaddcosprod.blob.core.windows.net/cxf-corporate/attachments/i6nksyffjs1qw0ls4wekcdtq-20250509-pr-michelinguide-hangzhou-2025.pdf'
MISSING_ID = 'hao-shi-tang-1987-wensan-road'
MISSING_URL = BASE + '/sg/zh_CN' + CITY_PATH + '/restaurant/' + MISSING_ID
VIA_MICHELIN = 'https://www.viamichelin.com/maps/restaurants/poi/hangzhou-_-1f5a65e6'


class ListingParser(HTMLParser):
    """Read server-rendered restaurant cards; ignore unrelated recommendations."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.card = None
        self.heading = False
        self.items = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            self.depth += 1
        if (tag == 'div' and self.card is None and
                'js-restaurant__list_item' in attrs.get('class', '').split() and
                attrs.get('data-id', '').isdigit()):
            self.card = {'id': attrs['data-id'], 'depth': self.depth, 'nameParts': [],
                         'lat': float(attrs['data-lat']), 'lng': float(attrs['data-lng']),
                         'award': attrs.get('data-map-pin-name', '')}
        if self.card is not None:
            if tag == 'h3':
                self.heading = True
            if tag == 'a' and CITY_PATH + '/restaurant/' in attrs.get('href', ''):
                self.card['url'] = urljoin(BASE, attrs['href'])

    def handle_data(self, data):
        if self.card is not None and self.heading:
            self.card['nameParts'].append(data)

    def handle_endtag(self, tag):
        if tag == 'h3':
            self.heading = False
        if tag == 'div':
            if self.card is not None and self.card['depth'] == self.depth:
                if 'url' in self.card:
                    self.card['name'] = ' '.join(''.join(self.card.pop('nameParts')).split())
                    self.card.pop('depth')
                    self.items.append(self.card)
                self.card = None
            self.depth -= 1


def read_cards(html):
    parser = ListingParser()
    parser.feed(html)
    return parser.items


def fetch(url, path, refresh=False):
    if path.exists() and not refresh:
        return path.read_text(encoding='utf-8')
    response = subprocess.run(
        ['curl', '--compressed', '-fLsS', '--max-time', '30', '--retry', '1', url],
        check=True, capture_output=True, text=True, encoding='utf-8')
    if '<html' not in response.stdout.lower():
        raise ValueError('Expected a complete public HTML page: ' + url)
    path.write_text(response.stdout, encoding='utf-8')
    return response.stdout


def detail_record(card, html, english_names):
    blocks = re.findall(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.S | re.I)
    objects = [json.loads(block) for block in blocks]
    restaurant = next(obj for obj in objects if obj.get('@type') == 'Restaurant')
    assert restaurant['award']['dateAwarded'] == EDITION, (card['id'], 'edition changed')
    assert restaurant['address']['addressLocality'] == 'Hangzhou', card['id']
    assert restaurant['latitude'] == card['lat'] and restaurant['longitude'] == card['lng'], (card['id'], 'coordinates differ')
    assert 'data-pid="' + card['id'] + '"' in html, (card['id'], 'ID missing')
    award_label = restaurant['award']['awardFor']
    expected_label = {'THREE_STARS': '三星', 'TWO_STARS': '二星', 'ONE_STAR': '一星', 'BIB_GOURMAND': '必比登'}[card['award']]
    assert expected_label in award_label, (card['id'], 'award differs')
    price = re.search(r'>\s*(¥{1,4})\s*<', html)
    assert price, (card['id'], 'official price missing')
    address = restaurant['address']['streetAddress']
    district = re.search(r'(西湖区|上城区|拱墅区|滨江区|萧山区|余杭区|临平区|钱塘区|富阳区|临安区|桐庐县|淳安县|建德市)', address)
    record = {'id': card['id'], 'key': 'hangzhou_' + card['id'], 'name': restaurant['name'],
              'url': restaurant['url'], 'lat': restaurant['latitude'], 'lng': restaurant['longitude'],
              'award': card['award'], 'category': AWARDS[card['award']], 'price': price[1],
              'cuisine': restaurant['servesCuisine'], 'address': address,
              'district': district[1] if district else '', 'phone': restaurant.get('telephone', ''),
              'year': EDITION}
    if card['id'] in english_names:
        record['englishName'] = english_names[card['id']]
    # These changes are explicitly named in the 2026 official release, not inferred
    # from a page badge, a renamed branch, or the review's last modification date.
    if card['id'] in NEW_BIB_IDS:
        record['distinctionChange'] = 'new'
    elif card['id'] == '1199479':
        record['distinctionChange'] = 'promoted'
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--verified-at', required=True, help='Date on which the source pages were actually checked, YYYY-MM-DD')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.verified_at)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    cards, english_names = {}, {}
    for language in ('zh', 'en'):
        locale = 'zh_CN' if language == 'zh' else 'en'
        for page in (1, 2):
            url = LISTING.replace('/zh_CN/', '/' + locale + '/') + ('' if page == 1 else '/page/2')
            html = fetch(url, args.cache_dir / f'list-{language}-{page}.html', args.refresh)
            for card in read_cards(html):
                if language == 'en':
                    english_names[card['id']] = card['name']
                elif card['award'] in AWARDS:
                    cards[card['id']] = card
    assert dict(Counter(AWARDS[r['award']] for r in cards.values())) == EXPECTED_LIVE, 'Live selection changed; review the release and unresolved entry before importing.'

    def load(card):
        html = fetch(card['url'], args.cache_dir / (card['id'] + '.html'), args.refresh)
        return detail_record(card, html, english_names)
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(load, cards.values()))
    missing = {'id': MISSING_ID, 'key': 'hangzhou_' + MISSING_ID,
               'name': '好食堂1987（文三路）', 'englishName': 'Hao Shi Tang 1987 (Wensan Road)',
               'url': MISSING_URL, 'lat': None, 'lng': None, 'award': 'BIB_GOURMAND',
               'category': 'bib', 'price': '', 'cuisine': '杭州菜', 'address': '', 'district': '',
               'phone': '', 'year': EDITION, 'locationStatus': 'unverified', 'directoryStatus': 'not-listed',
               'directoryNote': '2026发布名单列入必比登推介；核对时原米其林详情页返回404，ViaMichelin页面返回410，当前杭州官方目录未列出。保留年度名单记录，不据此判定停业；地址、价位和官方坐标未能重新核实，因此不显示地图点位。'}
    records.append(missing)
    order = {'3': 0, '2': 1, '1': 2, 'bib': 3}
    records.sort(key=lambda r: (order[r['category']], r.get('englishName', r['name'])))
    metadata = {
        'edition': EDITION, 'announcedAt': '2026-04-09', 'verifiedAt': args.verified_at,
        'scope': '2026沪苏浙《米其林指南》杭州发布版全部13家星级餐厅与34家必比登推介；不含41家米其林入选餐厅。绿星为独立奖项，不另行重复计数。',
        'counts': {'3': 0, '2': 2, '1': 11, 'bib': 34}, 'mappedCount': 46,
        'sources': [
            {'label': '米其林官方：2026沪苏浙指南发布及杭州统计', 'url': RELEASE},
            {'label': '米其林官方：杭州当前中文目录', 'url': LISTING},
            {'label': '米其林官方：杭州当前中文目录第2页', 'url': LISTING + '/page/2'},
            {'label': '2026发布完整名单（Restaurant Ranking转载）', 'url': ANNUAL_LIST},
        ],
        'unmappedEntries': [{
            'id': MISSING_ID, 'name': missing['name'], 'url': MISSING_URL,
            'reason': missing['directoryNote'],
            'sources': [
                {'label': '2026发布完整名单（转载）：列好食堂1987（文三路）为必比登', 'url': ANNUAL_LIST},
                {'label': '2025米其林官方完整名单：核对店名、菜系及原收录身份', 'url': PREVIOUS_PDF},
                {'label': '米其林原餐厅详情（核对时404）', 'url': MISSING_URL},
                {'label': 'ViaMichelin原餐厅资料（核对时410）', 'url': VIA_MICHELIN},
            ],
        }],
        'verificationNote': '年度发布口径为47家（2家二星、11家一星、34家必比登）；当前官方目录仅46家。46条地图记录已逐店核对官方目录与详情页JSON-LD，2026版年份、评级、中文店名、地址、电话、菜系及WGS-84坐标相符；价位取官方页面的¥档位，区名直接提取中文地址。另保留发布名单中的好食堂1987（文三路）为未定位条目，详见unmappedEntries；缺失坐标不估算，官网缺页不等同于停业。仅标记官方发布公告明确列出的9家新必比登及解香楼晋升二星。未核实实时营业时间、临时停业或具体套餐价格。',
    }
    for relative, value in [('data/venues/hangzhou-michelin.json', records), ('data/guides/hangzhou.json', metadata)]:
        path = args.output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Hangzhou 2026: 47 records, 46 verified map positions; 2 two-star + 11 one-star + 34 Bib Gourmand.')


if __name__ == '__main__':
    main()
