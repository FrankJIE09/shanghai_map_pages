#!/usr/bin/env bash
# 渲染流水线：先校验数据，再构建 dist/。
#
#   ./render.sh                     校验 + 构建
#   ./render.sh --check             只校验（数据 + 产物新鲜度），不写盘
#   ./render.sh --force             覆盖检测到被手改过的 dist 产物
#
# 数据改动请改 data/*.json，页面骨架改 src/pages/*.html，共用地图逻辑改
# src/static/*.js —— 都不要直接改 dist/，那是生成物。
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
    echo "需要 python3" >&2
    exit 1
fi

# 只有 --check 需要 git 之外的额外参数，其余原样透传给 build.py
exec python3 build.py "$@"
