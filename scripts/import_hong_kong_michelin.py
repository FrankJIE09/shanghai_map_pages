#!/usr/bin/env python3
"""Import the 2026 Hong Kong starred/Bib selection from official public pages.

Uses Python's standard library and curl. The optional HTML cache makes the import
repeatable without network requests. Fail closed if the live counts, edition,
awards or listing/detail coordinates no longer agree; review changes explicitly.

Example:
    python3 scripts/import_hong_kong_michelin.py --cache-dir /tmp/hong-kong-michelin-cache --verified-at 2026-11-16

One published Bib restaurant is absent from the current official directory and returns 404. Keep its
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
CITY_PATH = '/hong-kong-region/hong-kong'
LISTING = BASE + '/hk/zh_HK/hong-kong-region/restaurants/3-stars-michelin/2-stars-michelin/1-star-michelin/bib-gourmand'
EDITION = '2026'
AWARDS = {'THREE_STARS': '3', 'TWO_STARS': '2', 'ONE_STAR': '1', 'BIB_GOURMAND': 'bib'}
EXPECTED_LIVE = {'3': 7, '2': 13, '1': 57, 'bib': 69}
NEW_IDS = {'446675', '1219247', '1244244', '1244294', '1219139', '1245414', '1243604', '1243603'}
PROMOTED_IDS = {'1212171', '230806'}
GREEN_IDS = {'569032', '1210406', '1200897', '1185143'}
RELEASE = BASE + '/hk/en/article/michelin-guide-ceremony/hong-kong-and-macau-full-selection-release-2026'
ANNUAL_LIST = BASE + '/hk/zh_HK/article/michelin-guide-ceremony/hong-kong-macau-full-list'
ANNUAL_LIST_EN = BASE + '/hk/en/article/michelin-guide-ceremony/hong-kong-macau-full-list'
MISSING_ID = 'chiuchow-delicacies'
MISSING_URL = BASE + '/hk/zh_HK' + CITY_PATH + '/restaurant/' + MISSING_ID



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
    assert restaurant['address']['addressLocality'] == 'Hong Kong', card['id']
    assert restaurant['address']['addressCountry'] == 'HKG', (card['id'], 'not Hong Kong')
    assert restaurant['currenciesAccepted'] == 'HKD', (card['id'], 'not Hong Kong dollars')
    assert restaurant['latitude'] == card['lat'] and restaurant['longitude'] == card['lng'], (card['id'], 'coordinates differ')
    assert 'data-pid="' + card['id'] + '"' in html, (card['id'], 'ID missing')
    award_label = restaurant['award']['awardFor']
    expected_label = {'THREE_STARS': '三星', 'TWO_STARS': '二星', 'ONE_STAR': '一星', 'BIB_GOURMAND': '必比登'}[card['award']]
    assert expected_label in award_label, (card['id'], 'award differs')
    price = re.search(r'>\s*(\${1,4})\s*<', html)
    assert price, (card['id'], 'official price missing')
    address = restaurant['address']['streetAddress']
    # Use the official regional tag rather than inferring a legal district from a street.
    district = re.search(r'data-dtm-district="([^"]*)"', html)
    record = {'id': card['id'], 'key': 'hong-kong_' + card['id'], 'name': restaurant['name'],
              'url': restaurant['url'], 'lat': restaurant['latitude'], 'lng': restaurant['longitude'],
              'award': card['award'], 'category': AWARDS[card['award']], 'price': price[1],
              'cuisine': restaurant['servesCuisine'], 'address': address,
              'district': unescape(district[1]) if district else '', 'phone': restaurant.get('telephone', ''),
              'year': EDITION}
    if card['id'] in english_names:
        record['englishName'] = english_names[card['id']]
    # These changes are explicitly named in the 2026 official release, not inferred
    # from a page badge, a renamed branch, or the review's last modification date.
    if card['id'] in NEW_IDS:
        record['distinctionChange'] = 'new'
    elif card['id'] in PROMOTED_IDS:
        record['distinctionChange'] = 'promoted'
    if card['id'] in GREEN_IDS:
        record['greenStar'] = True
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
        locale = 'zh_HK' if language == 'zh' else 'en'
        for page in (1, 2, 3, 4):
            url = LISTING.replace('/zh_HK/', '/' + locale + '/') + ('' if page == 1 else '/page/' + str(page))
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
    missing = {'id': MISSING_ID, 'key': 'hong-kong_' + MISSING_ID,
               'name': '潮樂園', 'englishName': 'Chiuchow Delicacies',
               'url': MISSING_URL, 'lat': None, 'lng': None, 'award': 'BIB_GOURMAND',
               'category': 'bib', 'price': '', 'cuisine': '潮州菜', 'address': '', 'district': '',
               'phone': '', 'year': EDITION, 'locationStatus': 'unverified', 'directoryStatus': 'not-listed',
               'directoryNote': '保留《香港澳門米芝蓮指南2026》官方完整發布名單中的必比登記錄。核對時香港實時目錄未列此店，原官方詳情頁返回404；不單憑目錄缺失判定停業。地址、價位、電話和官方坐標未能重新核實，因此不顯示地圖點位。'}
    records.append(missing)
    order = {'3': 0, '2': 1, '1': 2, 'bib': 3}
    records.sort(key=lambda r: (order[r['category']], r.get('englishName', r['name'])))
    metadata = {
        'edition': EDITION, 'announcedAt': '2026-03-19', 'verifiedAt': args.verified_at,
        'scope': '《香港澳門米芝蓮指南2026》香港發布版全部77家星級餐廳與70家必比登推介；只收錄中國香港特別行政區，不含澳門及72家僅入選餐廳。綠星為獨立獎項，不另行重複計數。',
        'counts': {'3': 7, '2': 13, '1': 57, 'bib': 70}, 'mappedCount': 146,
        'sources': [
            {'label': '米芝蓮官方：2026香港澳門完整發布名單（繁體中文）', 'url': ANNUAL_LIST},
            {'label': '米芝蓮官方：2026完整發布名單（英文名稱對照）', 'url': ANNUAL_LIST_EN},
            {'label': '米芝蓮官方：2026年3月19日正式發布與分類統計', 'url': RELEASE},
            {'label': '米芝蓮官方：香港星級與必比登實時目錄（共4頁）', 'url': LISTING},
        ],
        'unmappedEntries': [{
            'id': MISSING_ID, 'name': missing['name'], 'url': MISSING_URL,
            'reason': missing['directoryNote'],
            'sources': [
                {'label': '官方2026完整發布名單：香港70家必比登中列有潮樂園', 'url': ANNUAL_LIST},
                {'label': '原官方餐廳詳情（核對時404）', 'url': MISSING_URL},
                {'label': '米芝蓮官方：潮樂園的潮州菜介紹及原門店連結', 'url': BASE + '/hk/zh_HK/article/travel/michelin-restaurants-hotels-hong-kong-island-metro-line-east'},
            ],
        }],
        'verificationNote': '按2026年3月19日官方發布口徑收錄147家（7家三星、13家二星、57家一星、70家必比登）；目前官方香港目錄為146家，少了潮樂園。146條地圖記錄逐店核對官方目錄及JSON-LD，2026年份、評級、餐廳身份、地址、電話、料理及WGS-84坐標一致，addressCountry均為HKG、貨幣均為HKD；價位直接保留官方$至$$$$檔位，不推算人均，不與人民幣或韓圜換算。district取官方data-dtm-district片區（香港島、九龍東/西、新界東/西），並非香港18個法定行政區；7家未提供片區的記錄留空。潮樂園保留為未定位檔案，不估算坐標，也不憑缺頁判定停業。新入選、晉升及綠星標記僅依官方2026發布名單；未核實實時營業、臨時停業或可訂座位。',
    }
    for relative, value in [('data/venues/hong-kong-michelin.json', records), ('data/guides/hong-kong.json', metadata)]:
        path = args.output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Hong Kong 2026: 147 records, 146 verified map positions; 7 three-star + 13 two-star + 57 one-star + 70 Bib Gourmand.')


if __name__ == '__main__':
    main()
