#!/usr/bin/env bash
# 把 Leaflet 的 CSS/JS 下载到 src/static/vendor/leaflet/，供 build.py 内联进产物。
#
# 为什么要 vendor 而不是继续用 unpkg CDN：
#   产物是「自包含单文件 HTML」，页面里再挂一个 CDN 请求就等于把首屏交给了第三方，
#   弱网 / 大陆访问 unpkg 不稳时页面会卡在白屏。vendor 一次、构建期内联，
#   产物就真的零依赖（唯一还需要网络的只剩地图瓦片与百度跳转页）。
#
# CSS 里的三张图片（layers / layers-2x / marker-icon）会被转成 data URI 内联，
# 否则内联后相对路径 images/... 无处可寻。marker-icon 虽然四个页面都用自己的
# divIcon（不依赖 Leaflet 默认图标），但 leaflet.css 里有它的引用，一并处理掉。
#
# 仅在需要升级 Leaflet 版本时跑一次：./scripts/vendor_leaflet.sh [版本号]
# 平时改数据 / 改页面都不需要执行本脚本。
set -euo pipefail

VERSION="${1:-1.9.4}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/src/static/vendor/leaflet"
BASE="https://unpkg.com/leaflet@${VERSION}/dist"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$OUT"
echo "-> 下载 Leaflet ${VERSION} 到 $OUT"

curl -sSL -o "$TMP/leaflet.css" "$BASE/leaflet.css"
curl -sSL -o "$TMP/leaflet.js" "$BASE/leaflet.js"
for img in layers layers-2x marker-icon; do
    curl -sSL -o "$TMP/$img.png" "$BASE/images/$img.png"
done

# 去掉 sourceMappingURL：内联进单文件后没有配套的 .map，留着只会在控制台报 404
grep -v '^//# sourceMappingURL=' "$TMP/leaflet.js" > "$OUT/leaflet.js"

# 图片 -> data URI（用 python3 做二进制安全替换，避免 sed 处理 base64 中的 / 与 &）
python3 - "$TMP" "$OUT/leaflet.css" <<'PY'
import base64, os, re, sys

tmp, dst = sys.argv[1], sys.argv[2]
css = open(os.path.join(tmp, "leaflet.css"), encoding="utf-8").read()

def to_data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

for name in ("layers", "layers-2x", "marker-icon"):
    uri = to_data_uri(os.path.join(tmp, name + ".png"))
    css = css.replace("url(images/%s.png)" % name, "url(%s)" % uri)

left = re.findall(r"url\((?!data:|#)[^)]*\)", css)
if left:
    raise SystemExit("还有未内联的 url(): %s" % left)

with open(dst, "w", encoding="utf-8") as f:
    f.write(css)
print("  leaflet.css %d B（图片已内联为 data URI）" % len(css.encode()))
PY

cat > "$OUT/VERSION" <<EOF
Leaflet ${VERSION}
来源 ${BASE}
由 scripts/vendor_leaflet.sh 生成：leaflet.css 的三张图片已内联为 data URI，
leaflet.js 已去掉 sourceMappingURL。
EOF

ls -la "$OUT"
echo "完成。"
