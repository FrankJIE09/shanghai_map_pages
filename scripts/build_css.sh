#!/usr/bin/env bash
# 生成 src/static/tailwind.css（构建期要内联的静态 Tailwind CSS）。
#
# 为什么不用 Play CDN：见 tailwind.config.js 顶部注释。简单说——CDN 版在浏览器里
# 跑 JIT，手机首屏会先裸排版再跳样式，离线打开则完全没有样式。
#
# 需要网络（npx 首次会拉 tailwindcss），但**只有在改页面用到新类名时才需要重跑**。
# 产物提交进 git，所以日常构建（build.py / render.sh）仍然只需要 python3。
#
# 用法： ./scripts/build_css.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v npx >/dev/null; then
    echo "需要 npx（Node.js）来生成 Tailwind CSS" >&2
    exit 1
fi

echo "-> 扫描 src/pages/*.html + src/static/*.js，生成 src/static/tailwind.css"
npx --yes tailwindcss@3.4.17 \
    -c tailwind.config.js \
    -i src/static/tailwind.src.css \
    -o src/static/tailwind.css \
    --minify

echo "完成：$(wc -c < src/static/tailwind.css) B"
