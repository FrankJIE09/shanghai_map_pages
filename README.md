# shanghai_map_pages

上海探店地图（三张）：米其林 / 必吃榜×扫街榜 / 酒吧×Livehouse×夜店。

页面是**自包含的单文件 HTML**：数据与共用地图逻辑在构建期内联进去，产物零依赖、可离线双击打开。

## 目录结构

```
data/
  venues/  bars.json  bichi.json  michelin.json   店铺数据（唯一数据源）
  map/     roads.json                             227 条道路，三页共用
           areas/     downtown.json  greater.json
           landmarks/ downtown.json  greater.json
src/
  pages/   bars.html  bichi.html  michelin.html   页面模板，含构建标记
  static/  map-base.js  theme.js                  共用地图底座
scripts/   extract_data.py  validate_data.py
           patch_bars_dianping.py  patch_all_stores.py
build.py   render.sh
dist/                                           构建产物，提交进 git
```

## 数据流

```
data/*.json + src/static/*.js  --build.py-->  dist/*.html
```

源数据只写 JSON，**不要手改 HTML 里的数据**——那只在构建时生成。改数据请改 `data/`，然后重新构建。

## 构建

```bash
python3 scripts/validate_data.py   # 数据自检（key 唯一、坐标范围、枚举、必填字段）
python3 build.py                   # 内联 JSON 与共用 JS，输出 dist/
python3 build.py --check           # 只校验，不写盘
```

或一步到位：

```bash
./render.sh
```

`build.py` 会把每个生成区的 sha256 记进 `dist/.build-manifest.json`。若检测到 dist 里的生成内容被手改过，会报错退出，加 `--force` 才覆盖。

## 构建标记

模板 `<script>` 内用 JS 注释标记注入点：

```javascript
/* @@BUILD:json data/venues/bars.json -> VENUES@@ */
const VENUES = [ /* 构建生成，勿手改 */ ];
/* @@BUILD:end@@ */

/* @@BUILD:js src/static/map-base.js@@ */
/* @@BUILD:end@@ */
```

## 本地预览

直接用浏览器打开 `dist/*.html` 即可（`file://` 也能正常工作）。

需要 http 环境时：

```bash
python3 -m http.server 8000    # 然后访问 http://localhost:8000/dist/
```

## 部署（帽子云）

- 仓库：`FrankJIE09/shanghai_map_pages`
- 分支：`main`
- **构建命令：留空**
- **输出目录：`dist`**

因为 `dist/` 已提交进 git，平台不需要跑构建，直接当静态站点发布即可。

## 与旧仓库的关系

这三个页面原本在 `gemini_htmls` 仓库中，数据内联在 HTML 里。本仓库把它拆成「JSON 源 + 构建期 内联」并抽出了共用的地图底座。

`gemini_htmls` 里的同名页面是**冻结的历史快照**，不再更新；那个仓库的 `index.html` 目前仍指向它们，尚未切到本仓库部署的地址。
