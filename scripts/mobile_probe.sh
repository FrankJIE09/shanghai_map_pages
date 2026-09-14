#!/usr/bin/env bash
# 手机端外壳验收：无头 Chrome 跑 scripts/mobile_probe.js，全绿才退 0。
#
#   ./scripts/mobile_probe.sh              # 跑全部（几何 + 行为 + 点标记 + 触控 + 分流）
#   ./scripts/mobile_probe.sh geom         # 只跑其中一项：geom|behave|marker|css|links
#   KEEP=1 ./scripts/mobile_probe.sh       # 保留临时目录，便于手翻产物
#
# 为什么不用 scripts/parity_*.html 那套：那套是「同版本前后对比」，要人眼看两个
# document.title。手机端要验的多半是真值（抽屉闭合时在不在视口外、返回键会不会退出
# 网页、触控目标够不够大、不同 UA 落哪一档），这里直接给 PASS/FAIL 与退出码。
#
# 依赖：google-chrome（或 chromium）+ python3。产物要先构建好（python3 build.py）。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK:-/tmp/mobile_probe}"
PORT="${PORT:-8987}"
ONLY="${1:-all}"

CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
if [ -z "$CHROME" ]; then
    echo "找不到 google-chrome / chromium，无法跑无头验收" >&2
    exit 2
fi
if [ ! -d "$ROOT/dist" ] || [ -z "$(ls -A "$ROOT/dist"/*.html 2>/dev/null)" ]; then
    echo "dist/ 里没有产物，先跑 python3 build.py" >&2
    exit 2
fi

rm -rf "$WORK"
mkdir -p "$WORK"
cp "$ROOT"/dist/*.html "$WORK/"
cp "$ROOT/scripts/mobile_probe.js" "$WORK/"

# 注入探针：每页都在 </body> 前挂一行；rich 版顺手给一条词条补上 baidu_url / baidu_uid，
# 否则「有短链 / 有 uid」这两档在真实数据里根本跑不到（出厂状态下一条都没有）。
python3 - "$WORK" <<'PY'
import glob, json, os, re, sys
work = sys.argv[1]
PROBE = '<script src="mobile_probe.js"></script>\n'
RICH = {"baidu_url": "https://j.map.baidu.com/probe-baidi", "baidu_uid": "PROBE-UID-0001"}

for path in glob.glob(os.path.join(work, '*.html')):
    html = open(path, encoding='utf-8').read()
    base = os.path.basename(path)[:-5]
    open(os.path.join(work, '_p_%s.html' % base), 'w', encoding='utf-8').write(
        html.replace('</body>', PROBE + '</body>'))
    # 找一个「元素是对象数组、且元素带 key/name」的内联数据块（各页变量名不同）
    for m in re.finditer(r'(?s)const ([A-Z_]+) = (\[.*?\]);', html):
        try:
            items = json.loads(m.group(2))
        except ValueError:
            continue
        if not items or not isinstance(items[0], dict) or 'key' not in items[0] or 'name' not in items[0]:
            continue
        key = items[0]['key']
        for it in items:
            if it.get('key') == key:
                it.update(RICH)
        rich = html[:m.start()] + 'const %s = %s;' % (m.group(1), json.dumps(items, ensure_ascii=False)) + html[m.end():]
        open(os.path.join(work, '_p_%s_rich.html' % base), 'w', encoding='utf-8').write(
            rich.replace('</body>', PROBE + '</body>'))
        # 把补过的词条 key 记下来：分流探针要用 #v=<key> 直接选中它，两档数据才可比
        with open(os.path.join(work, 'keys.tsv'), 'a', encoding='utf-8') as fh:
            fh.write('%s\t%s\n' % (base, key))
        print('  补齐数据：%-32s 变量=%-12s 词条=%s' % (base, m.group(1), key))
        break
PY

# 起一个「确实在服务本次 WORK 目录」的本地服务。
# 不能只看端口有没有响应：之前跑剩下的 http.server 会占着端口、目录却早被删了，
# 于是每个用例都拿到 404，探针一片空白（排查半天）。所以写个带随机 token 的文件，
# 必须能读到同一个 token 才算成功；端口被占就换下一个，结束时把服务关掉。
TOKEN="mp$(date +%s)$$"
echo "$TOKEN" > "$WORK/_probe_token"
PORT=""
for p in $(seq 8987 8999); do
    ( cd "$WORK" && nohup python3 -m http.server "$p" --bind 127.0.0.1 >/dev/null 2>&1 & echo $! > "$WORK/.pid" )
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        got=$(curl -s --max-time 1 "http://127.0.0.1:${p}/_probe_token" 2>/dev/null || true)
        if [ "$got" = "$TOKEN" ]; then PORT="$p"; break; fi
        sleep 0.3
    done
    [ -n "$PORT" ] && break
done

if [ -z "$PORT" ]; then
    echo "起不了本地 http 服务（8987-8999 都被占用或 python3 http.server 不可用）" >&2
    exit 2
fi

cleanup() {
    [ -f "$WORK/.pid" ] && kill "$(cat "$WORK/.pid")" 2>/dev/null
    if [ -z "${KEEP:-}" ]; then rmdir "$WORK" 2>/dev/null || rm -rf "$WORK"; fi
}
trap cleanup EXIT

PASS=0
FAIL=0
run() {   # run <页名> <probe> <宽> <高> <ua关键字|-> [data] [hash]
    local page="$1" probe="$2" w="$3" h="$4" ua="${5:--}" data="${6:-plain}" hash="${7:-}"
    local extra=() budget=25000
    case "$ua" in
        touch)  extra=(--blink-settings=primaryPointerType=2,availablePointerTypes=2,primaryHoverType=1,availableHoverTypes=1) ;;
        iphone) extra=(--user-agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1") ;;
        android) extra=(--user-agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36") ;;
        wechat) extra=(--user-agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003129) NetType/WIFI Language/zh_CN") ;;
    esac
    # marker / behave 两档要多等：探针是 setTimeout 链推进的（打开→量→返回→量…）
    case "$probe" in behave|marker) budget=40000 ;; esac
    local out
    # rich 档要加载补过字段的那份副本：data=rich 只改探针的期望，文件得跟着换
    local file="_p_${page}.html"
    [ "$data" = "rich" ] && file="_p_${page}_rich.html"
    out=$("$CHROME" --headless=new --disable-gpu --no-first-run --no-default-browser-check \
        --hide-scrollbars --force-device-scale-factor=1 \
        --user-data-dir="/tmp/mprobe-${w}x${h}-${ua}" \
        --window-size="${w},${h}" --virtual-time-budget="$budget" \
        ${extra[@]+"${extra[@]}"} \
        --dump-dom "http://127.0.0.1:${PORT}/${file}?probe=${probe}&notrans=1&data=${data}${hash}" 2>/dev/null \
        | sed -n '/PROBE-START/,/PROBE-END/p' | grep -v 'PROBE-')

    local label="${page:0:28} $probe ${w}x${h} ${ua}"
    if [ -z "$out" ]; then
        echo "  ✗ $label —— 探针没有输出（页面没加载起来？）"
        FAIL=$((FAIL + 1))
        return
    fi
    local p f
    p=$(echo "$out" | grep -c '^PASS'); f=$(echo "$out" | grep -c '^FAIL')
    PASS=$((PASS + p)); FAIL=$((FAIL + f))
    printf "  %s %-46s PASS=%-3s FAIL=%s\n" "$([ "$f" = 0 ] && echo ✓ || echo ✗)" "$label" "$p" "$f"
    [ "$f" != 0 ] && echo "$out" | grep '^FAIL' | sed 's/^/       /'
    [ -n "${VERBOSE:-}" ] && echo "$out" | grep '^INFO' | sed 's/^/       /'
    return 0
}

ALL_PAGES=$(cd "$WORK" && ls _p_*.html | grep -v '_rich' | sed 's/^_p_//;s/\.html$//' | sort)
# 落地页没有手机外壳（[data-m-*] 标记与 mobile.css 都不内联），行为 / 分流 / 触控
# 那三项对它没有意义，只跟着验几何。
MAP_PAGES=$(echo "$ALL_PAGES" | grep -v '^index$')

if [ "$ONLY" = all ] || [ "$ONLY" = geom ]; then
    echo "── 几何：窄屏全屏地图 / 宽屏原布局、无溢出、无 JS 错误 ──"
    for page in $ALL_PAGES; do
        for vp in "360 640 touch" "390 844 iphone" "640 360 touch" "768 1024 touch" "899 800 touch"; do
            set -- $vp; run "$page" geom "$1" "$2" "$3"
        done
        for vp in "901 800 -" "1440 900 -"; do
            set -- $vp; run "$page" geom "$1" "$2" "$3"
        done
    done
fi

if [ "$ONLY" = all ] || [ "$ONLY" = behave ]; then
    echo "── 行为：抽屉开合 / 返回键 / Esc / 深链 / 分享 ──"
    for page in $MAP_PAGES; do
        run "$page" behave 390 844 iphone
        run "$page" behave 390 844 wechat
    done
fi

if [ "$ONLY" = all ] || [ "$ONLY" = marker ]; then
    echo "── 地图上点店铺：应直接弹出介绍卡片 ──"
    for page in $MAP_PAGES; do
        run "$page" marker 390 844 iphone
        run "$page" marker 390 844 touch
    done
fi

if [ "$ONLY" = all ] || [ "$ONLY" = css ]; then
    echo "── 触控：控件尺寸、hover 门控；桌面端须保持原尺寸 ──"
    for page in $ALL_PAGES; do
        run "$page" css 390 844 touch
        run "$page" css 1280 900 -
    done
fi

if [ "$ONLY" = all ] || [ "$ONLY" = links ]; then
    echo "── 分流：四种 UA × 两档数据该落哪一档 ──"
    for page in $MAP_PAGES; do
        key=$(grep -P "^${page}\t" "$WORK/keys.tsv" 2>/dev/null | cut -f2)
        hash=""
        [ -n "$key" ] && hash="#v=${key}"
        for data in plain rich; do
            if [ "$data" = rich ] && [ ! -f "$WORK/_p_${page}_rich.html" ]; then
                echo "  - $page 没有可补的内联数据块，跳过 rich 档"
                continue
            fi
            run "$page" links 390 844 iphone "$data" "$hash"
            run "$page" links 390 844 android "$data" "$hash"
            run "$page" links 390 844 wechat "$data" "$hash"
            run "$page" links 1280 900 - "$data" "$hash"
        done
    done
fi

echo
echo "合计：PASS=$PASS FAIL=$FAIL"
if [ -n "${KEEP:-}" ]; then
    echo "临时目录保留在 $WORK（服务端口 $PORT，收尾时已停）"
fi
[ "$FAIL" = 0 ] || exit 1
