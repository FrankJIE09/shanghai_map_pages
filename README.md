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
           geo-controls.js                        定位控件（仅 bichi/michelin 内联）
scripts/   extract_data.py  validate_data.py              抽取与校验
           jslit.py  js_eval_literal.js                   抽取时求值 JS 字面量
           patch_bars_dianping.py  patch_all_stores.py    定点补丁（改 JSON）
           parity_diag.html  parity_geo_diag.html         渲染结果对比探针
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

## 补数据

`data/venues/*.json` 是唯一数据源。批量补字段用两个补丁脚本，它们只改 JSON，不再碰 HTML：

```bash
python3 scripts/patch_bars_dianping.py --dry    # 先看会改什么
python3 scripts/patch_bars_dianping.py          # 写回 bars.json
python3 scripts/patch_all_stores.py             # 写回 bichi.json
./render.sh                                     # 校验 + 重新构建
```

两个脚本都是**幂等**的：重复运行第二次不再有变更。`patch_bars_dianping.py` 里 `NOTE` / `SRC_ADD` 只在 `UPDATES` 命中的 key 上生效——这是原脚本的语义，脚本每次都会把「不生效的遗留条目」列出来，便于清理。`patch_all_stores.py` 里 `AVG` 是人均的唯一来源（先把所有 `avg` 清成 `null` 再写入），所以从 `AVG` 删掉一个 key 就能真正清掉它的人均。

## 构建标记

模板 `<script>` 内用 JS 注释标记注入点：

```javascript
/* @@BUILD:json data/venues/bars.json -> VENUES@@ */
const VENUES = [ /* 构建生成，勿手改 */ ];
/* @@BUILD:end@@ */

/* @@BUILD:js src/static/map-base.js@@ */
/* @@BUILD:end@@ */
```

## 变更后如何验证

重构过地图底座之后，要确认产物与重构前「渲染结果一致」，不能只看代码。`scripts/parity_diag.html` 就是为此准备的探针：

它把一张地图页塞进同源 iframe，点一遍 🛣️ / 📍 开关，把两轮开关后的 DOM 计数与 Leaflet 真实状态（缩放、中心、bounds、pane 可见性）写进 `document.title`，供人或脚本读取。

```bash
mkdir -p /tmp/a /tmp/b
cp dist/*.html scripts/parity_diag.html /tmp/a/          # 旧版本
cp dist/*.html scripts/parity_diag.html /tmp/b/          # 新版本
(cd /tmp/a && python3 -m http.server 8766 &)
(cd /tmp/b && python3 -m http.server 8765 &)
# 浏览器打开 http://localhost:8766/parity_diag.html#shanghai_michelin_2026.html
# 与     http://localhost:8765/parity_diag.html#shanghai_michelin_2026.html
# 对比两边页面标题里的这几十个计数：应逐字相同
```

关注这些量：`polylines` / `road_labels` / `areas` / `pois` / `icons` / `list`，以及开关前后的增减与 `mapstate`。**不要用 `firstTileZ` 判断缩放**——Leaflet 会保留 `fitBounds` 之前的旧瓦片，DOM 里第一个瓦片的 z 可能是初始值，而 `mapstate.z` 才是真实缩放。

定位流程用另一个探针，它会伪造 `navigator.geolocation`，再依次点 🧭 / 📏 / ✕，记录每步的提示条文案、按钮状态、我的位置标记数、精度圆数与名录前三项：

```bash
# 两个端口同样各开一个，对比页面标题
# http://localhost:8766/parity_geo_diag.html#shanghai_bichi_saojie_2026.html
# http://localhost:8765/parity_geo_diag.html#shanghai_bichi_saojie_2026.html
```

（`bars` 的定位实现是页面自己的，它不给 🧭 / ✕ 按钮设 id，所以这个探针只适用于 `bichi` 与 `michelin`。）

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
