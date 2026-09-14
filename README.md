# shanghai_map_pages

上海探店地图（四张）：米其林 / 必吃榜×扫街榜 / 酒吧×Livehouse×夜店 / **餐饮总览（三榜合并）**。

**在线访问：<https://frankjie09.github.io/shanghai_map_pages/>**（GitHub Pages 托管的落地页，四张图的总入口）

页面是**自包含的单文件 HTML**：数据与共用地图逻辑在构建期内联进去，产物零依赖、可离线双击打开。

## 目录结构

```
data/
  venues/  bars.json  bichi.json  michelin.json   店铺数据（唯一数据源）
  map/     roads.json                             227 条道路，各页共用
           areas/     downtown.json  greater.json
           landmarks/ downtown.json  greater.json
           metro/     lines.json  stations.json    地铁线路 / 站点（仅 bars 页用，见下文）
.github/   workflows/deploy-pages.yml          GitHub Pages 发布（把 dist/ 发上线）
src/
  pages/   index.html                            落地页模板（总入口，不含数据）
           bars.html  bichi.html  michelin.html  eat.html   地图页模板，含构建标记
  static/  map-base.js  theme.js                  共用地图底座
           geo-controls.js                        定位控件（bichi/michelin/eat 内联）
           venue-links.js                        详情卡的「导航 / 百度店铺页」链接（四页内联）
           mobile-boot.js                        首屏前给 <html> 打手机端标记
           mobile-shell.js                       手机端外壳行为（抽屉 / 返回键 / 深链 / 分享）
           mobile.css                            手机端外壳样式（只在窄屏命中）
           tailwind.css  tailwind.src.css        静态 Tailwind（构建期生成 / 源）
           vendor/leaflet/                       vendored Leaflet（构建期内联，含 VERSION）
scripts/   extract_data.py  validate_data.py              抽取与校验
           extract_metro.py                               地铁数据抽取（离线维护，不在构建链路上）
           merge_venues.py                                 bichi + michelin 合并（eat 页数据）
           jslit.py  js_eval_literal.js                   抽取时求值 JS 字面量
           patch_bars_dianping.py  patch_all_stores.py    定点补丁（改 JSON）
           build_css.sh                                   生成 src/static/tailwind.css（偶发）
           vendor_leaflet.sh                              更新 vendored Leaflet（偶发）
           mobile_probe.sh  mobile_probe.js               手机端验收（无头 Chrome，可一键复跑）
           parity_diag.html  parity_geo_diag.html  parity_ui_diag.html   渲染结果对比探针
tailwind.config.js                   只给 scripts/build_css.sh 用的 Tailwind 静态构建配置
build.py   render.sh
index.html                                      手写的平台入口页（转发到 dist/index.html，不参与构建）
dist/                                           构建产物，提交进 git（含 index.html 落地页）
```

> 根目录的 `index.html` 和 `dist/index.html` 是两回事：前者是手写的，只为满足「静态托管平台要在部署目录根部找到 `index.html` 或 `package.json`」的识别规则（见下文部署一节）；后者是构建产物，才是真正的站点首页。

`eat.html` 没有自己的数据文件：它的数据由构建期把 `bichi.json` 与 `michelin.json` **合并生成**（规则见 `scripts/merge_venues.py`），所以不存在需要手工维护的 `eat.json`。

`index.html` 是四张地图的**落地页**（GitHub Pages 的首页），不含 `json` / `merge` 数据，只用 `count` 标记读取条数——所以它里面的「37 家 / 131 家」永远和数据一致，不会写死。

## 数据流

```
data/*.json + src/static/*.js  --build.py-->  dist/*.html
data/venues/bichi.json + michelin.json  --merge_venues-->  eat 页的 EAT_STORES
data/map/metro/lines.json + stations.json  --build.py-->  bars 页的 METRO_LINES / METRO_STATIONS
```

源数据只写 JSON，**不要手改 HTML 里的数据**——那只在构建时生成。改数据请改 `data/`，然后重新构建。

### 地铁图层（bars 页）

`data/map/metro/` 只有 bars 页用到，两份文件都是**裸顶层数组**：

- `lines.json` —— 13 条线，形状 `{ id, name, color, path:[[lat,lng]…], stations:[stationId…] }`，`id` 形如 `m_1`、`m_2`、`m_7`（线号直接写进 id）。
- `stations.json` —— 87 个站，形状 `{ id, name, coords:[lat,lng] }`。**故意不带 `lines` 字段**：所属线路与「是否换乘」都在渲染时由 `lines.json` 反查派生（被 2 条及以上线路引用即换乘，实测 47 个换乘站）。

构建期用 `json` 标记把两份数据分别内联成 `METRO_LINES` / `METRO_STATIONS`（见 `src/pages/bars.html` 约 541/545 行），绘制与右上角 🚇 多选面板在 `MapBase.drawMetro()`（`src/static/map-base.js`）。缩放分级：z11-12 只画线不画站 / z13 只画换乘站 / z≥14 全部站 / z≥15 hover 出站名；默认**全不选**，勾选后才入图。

`extract_metro.py` 是**离线维护脚本**（重跑抽取才用它），**不在 `render.sh` 链路上**，平时改数据不需要碰它。

**已知偏差：没有 6 号线（`m_6`）。** 6 号线全在浦东，核心区 bbox 内 0 站（最近的高科西路距东边界约 400 m），按「范围外不收录 / 严禁编造坐标」的铁律被跳过，因此 `lines.json` 里没有它。但 `data/venues/bars.json` 的 `metro` 文本里确实引用了 6 号线（赤红 EKA·天物那条「6号线金桥路站 / 9号线金桥站」），所以 `validate_data.py` 的线号交叉校验带一个**显式白名单 `MISSING_LINES = {6: …}`**：白名单内的线号只打印 `⚠ SKIP` 说明，白名单外的任何缺失线号照样报错（这条断言的作用就是抓「新开线忘了收录」，不要把它放宽成「忽略找不到的线号」）。

## 三榜合并口径（eat 页）

`eat` 把「必吃榜」「扫街榜」「米其林指南」合成一份 **132 家**的记录，规则只有两条，且都可校验：

1. **去重**：两源**坐标完全一致**（距离 0）判为同一家店。实测恰好 13 对，与 bichi 侧 `michelin != 0` 的 13 条一一对应，星级也一致。两源命名不同（如「临湖素食（保利·时光里店）」vs 官方「临湖素食」），所以**不能**靠店名匹配。坐标接近但不等（4 m、8 m 等）的不合并——实测那是不同餐厅。
2. **标签**：合并成一维可多选的 `tags`（`both`/`bichi`/`saojie`/`michelin3`/`michelin2`/`michelin1`/`bib`），`primary` 取优先级最高的一项作为主色分类：
   双榜 > 必吃 > 扫街 > 三星 > 二星 > 一星 > 必比登。即上榜门店以榜单为主色、米其林走左下角金角标；只被米其林收录的以星级为主色。

字段取值：有 bichi 侧就用 bichi 侧（中文描述与菜系更细、有真实人均），仅米其林收录的用官方字段。米其林侧只有 ¥ 档位、没有具体人均，故其独有门店在页面上如实标注「人均待核实」。

`python3 scripts/validate_data.py` 会断言上述不变量（13 对配对、星级一致、无重复 key/坐标、标签合法、米其林标签条数与米其林数据条数相等），数据更新后若有漏合并/错合并会直接报错。

## 构建

```bash
python3 scripts/validate_data.py   # 数据自检（key 唯一、坐标范围、枚举、必填字段、合并不变量、地铁线与站点）
python3 build.py                   # 内联 JSON 与共用 JS，输出 dist/
python3 build.py --check           # 只校验，不写盘
```

或一步到位：

```bash
./render.sh
```

`build.py` 会把每个生成区的 sha256 记进 `dist/.build-manifest.json`。若检测到 dist 里的生成内容被手改过，会报错退出，加 `--force` 才覆盖。

### 零运行时依赖（构建期内联 CSS / JS）

产物是**自包含单文件**：Tailwind、Leaflet、四个页面的共用脚本、全部数据都在构建期内联，页面里没有任何 `<script src>` / `<link rel="stylesheet">` / 字体的外部请求。`--check` 有四组正面断言守着这件事，破坏了会直接构建失败：

- **无外链**：产物里不许再有 http(s) 的 JS/CSS 与 Google Fonts 请求（弱网 / 离线 / 大陆访问 CDN 不稳时会白屏或裸排版）。
- **运行时真的进来了**：页面用了 Leaflet 就必须能在产物里找到 Leaflet（这条是踩坑加的——只删 CDN 标签、忘了加内联标记时，「无外链」反而更绿，而页面会在运行时丢 `L is not defined`，地图整块空白）。
- **Tailwind 类名覆盖**：产物里每个静态 `class="…"` 的类名都要能在内联 CSS 里找到定义。改页面加了新类名却忘了重建 CSS，浏览器不报错、只是那个元素悄悄没了样式。JS 里拼出来的类名（`class="…${x}…"`）不判，没法与变量名区分。
- **手机端外壳结构**：`data-m-sheet` 不许和 `#detail-card` 落在同一个标签上（`mobile.css` 给后者的 `position: relative !important` 会顶掉抽屉的 `fixed`，闭合态的详情卡会浮在视口正中——桌面端看不出来，只有手机上有；bars 页真踩过）、百度链接不许带 `target="_blank"`（App 调起必须同 tab 走 `location.href`，新标签会被当弹窗拦掉）、有 `#m-bar` 就必须有抽屉。

两份需要**手工、偶发**重建的内联资源（产物都提交进 git，日常改数据 / 改文案不用碰）：

```bash
./scripts/build_css.sh       # 改了页面、新增了 Tailwind 类名之后：生成 src/static/tailwind.css
./scripts/vendor_leaflet.sh  # 只在要升级 Leaflet 版本时：下载 Leaflet 到 src/static/vendor/leaflet/
```

`build_css.sh` 需要 npx（首次会去下 `tailwindcss@3.4.17`）；它把 `src/pages/*.html` 与 `src/static/*.js` 扫一遍生成静态 CSS（约 19KB），替代原来的 `cdn.tailwindcss.com`——那个是在浏览器里跑 JIT，手机上会「先裸排版、样式晚一步跳出来」，离线打开则完全没有样式。`vendor_leaflet.sh` 会把 Leaflet CSS 里的三张图片转成 data URI（内联后相对路径无处可寻），并去掉 JS 的 `sourceMappingURL`。

## 手机端

四个地图页共用一套「全屏地图 + 底部抽屉」外壳，样式在 `src/static/mobile.css`，行为在 `src/static/mobile-shell.js`，**只在窄屏（≤900px）生效**，桌面端一个选择器都不命中、原有三栏布局与 `lg:sticky` 详情卡照旧。

标记打在 `<html>` 上（`src/static/mobile-boot.js` 在 `<head>` 里同步执行，避免首屏先闪一下桌面布局）：

| 标记 | 含义 |
| --- | --- |
| `html.m-mobile` | 窄屏：启用全屏地图 + 抽屉外壳 |
| `html.m-touch` | 粗指针（手机 / 平板）：只做触控尺寸修正，不改布局 |
| `html[data-m-open="xxx"]` | 当前打开的抽屉名，由 `mobile-shell.js` 读写 |

页面只需要在 DOM 上打 `[data-m-*]` 标记，不需要为手机端写第二套 HTML：

| 标记 | 作用 |
| --- | --- |
| `[data-m-pane="map"]` | 地图卡片 → 铺满视口（`dvh` + safe-area） |
| `[data-m-sheet="xxx"]` + `data-m-title` | 该块在手机上变成固定底部抽屉，标题栏与抓手由 shell 注入 |
| `[data-m-open="xxx"]` / `data-m-close` | 抽屉开关；`data-m-scroll="#sel"` 打开后滚到该元素；再点一次收起 |
| `[data-m-hide]` | 手机上不需要的块 |

外壳另外做了四件事：**返回键**在抽屉打开时是「收起抽屉」而不是退出网页（走 `history.pushState`，点 ✕ 与按返回键同一条路径）；**深链** `#v=<key>` 直接打开某家店的详情，可分享可收藏；**分享**优先用 `navigator.share`（系统分享面板），不支持就复制链接；**触控细节**见下一节。触屏上另有一处行为差异：地铁站名在 `pointer: coarse` 时提前常显（没有 hover 可用，见 `src/static/map-base.js`）。

### 触控细节（`@media (pointer: coarse)` 里）

桌面端一行都不命中，改这些不会动到电脑上的排版：

| 项 | 触屏上 | 桌面 |
| --- | --- | --- |
| 筛选 chip / 分类 / 排序 | `min-height: 34px` | 25px（原样） |
| 「↺ 重置筛选」 | `min-height: 34px` | 27px（原样） |
| 复选框 / 单选框 | 本体 20px，外层 `label` 撑到 34px | 13px |
| 搜索框等输入 | `font-size: 16px` | 12px（原样） |
| hover 效果 | 全部包在 `@media (hover: hover)` 里，触屏下不生效 | 正常 |
| 地铁站名常显门槛 | z15 | z16（z15 靠悬停） |

34px 是刻意取的折中：iOS HIG 建议 44pt、Material 建议 48dp，但筛选区是一排排胶囊，全按 44px 会把抽屉撑长一屏多；30px 一档实测偏小（无头审计里 `#reset-btn` 只有 23–27px，复选框连外层 `label` 一起才 16px）。复选框放大用的是 `label:has(> input[type=checkbox])`，浏览器不支持 `:has()` 时这两条会被整条丢弃、退回原样，不会更糟。

顶栏与抽屉都吃 `env(safe-area-inset-*)`，所以页面 head 里配了 `apple-mobile-web-app-status-bar-style: black-translucent`（iOS 加到主屏后内容顶到状态栏下面，靠 safe-area 让开）。四个地图页还有 `theme-color: #16141C`，让安卓 Chrome 的地址栏跟着深色地图走；落地页是浅底，配的是 `#FAF5EB`。

**没有做 Service Worker / PWA**：产物本来就是自包含单文件，存到本地即可离线打开；而 SW 要额外引入一份带缓存版本号的独立文件，一旦缓存策略写错会长期给用户喂旧页面（且很难撤回），收益与风险不成比例。真要做离线，建议先确定发布环境（GitHub Pages 之外还有帽子云）再决定缓存键与失效策略。

### 怎么验手机端

`scripts/` 下的 parity 探针是桌面语义的，验手机端用无头 Chrome 直接量：

```bash
# ?notrans=1 关过渡：headless 的动画时钟不推进，transform 会停在闭合态的插值上，量不到真实位置
# --virtual-time-budget 要给够：外壳是 setTimeout 链推进的（打开→量→返回→量…）
google-chrome --headless=new --window-size=500,844 --virtual-time-budget=20000 \
  --dump-dom "http://localhost:8000/dist/shanghai_bars_livehouse_2026.html?notrans=1#v=beer_aunt" \
  | grep -E 'data-m-open|m-bar'
```

要看的量：`html.class` 是否含 `m-mobile`、抽屉闭合时是否**完全在视口外**、打开时上沿 y 是否贴到视口底部、`#m-bar` 在桌面端是否 `display:none`、有没有横向溢出、控制台有没有 JS 错误。验证「跳 App」的分流用 `--user-agent` 换 iOS / 安卓 / 微信的 UA，读 `#detail-poi` 的 `href` 与 `data-kind`。

三个 headless 特有的坑（踩过、会直接给出假结论）：

1. **触屏模拟要用 `primaryPointerType=2`**（Blink 的枚举：`1=None`、`2=Coarse`、`4=Fine`），`=1` 或 `=4` 都不会让 `matchMedia('(pointer: coarse)')` 为真，触控那套 CSS 就永远测不到：
   `--blink-settings=primaryPointerType=2,availablePointerTypes=2,primaryHoverType=1,availableHoverTypes=1`
2. **量缩放要先关动画**：`map.options.zoomAnimation = false; map._zoomAnimated = false; map.setView(center, z, {animate:false})`，否则 `setZoom()` 会「开始」但永不提交，`getZoom()` 一直停在初始级别，读到的全是错位一档的旧状态。
3. **`window.onload` 在 `--dump-dom` 下常常不触发**，地图不会初始化。注入的探针里要兜一手：没找到 `.leaflet-container` 就手动调一次 `window.onload()`。

验「触控尺寸」这类要真手指才碰得到的规则时，别去模拟 `:hover`（合成 `mouseover` 事件不会让 `:hover` 生效），直接从 CSSOM 读：`document.styleSheets` 里筛出 `conditionText` 含 `pointer` / `hover` 的 `MEDIA_RULE`，看规则条数、是否 `matchMedia(...).matches`、以及带 `:hover` 的选择器有没有全部落在 `(hover: hover)` 条件里。

上面这些坑都固化进了一个可一键复跑的脚本 —— `scripts/mobile_probe.sh`（探针在 `scripts/mobile_probe.js`），它把 5 个页面 × 7 种视口 × 4 种 UA 的 700 多条断言跑完并给出退出码，全绿才退出 0：

```bash
python3 build.py                  # 产物要先是最新的
./scripts/mobile_probe.sh         # 全部：几何 + 行为 + 触控 + 分流
./scripts/mobile_probe.sh css     # 只跑其中一项：geom | behave | css | links
VERBOSE=1 ./scripts/mobile_probe.sh geom   # 连 INFO 行（实测数值）一起打出来
KEEP=1 ./scripts/mobile_probe.sh  # 保留 /tmp 临时目录，便于手翻产物
```

四组各管什么：

| 组 | 覆盖 | 典型断言 |
| --- | --- | --- |
| `geom` | 360×640 / 390×844 / 640×360（横屏）/ 768×1024 / 899×800 / 901×800 / 1440×900 | 窄屏地图铺满视口且 `position:fixed`、闭合抽屉完全在视口外、无横向溢出、`#m-bar` 在桌面端 `display:none`、无 JS 错误 |
| `behave` | 每个抽屉都开一遍 | 打开写 `history.state`、返回键只收抽屉不退出网页、Esc 收起、点名录写 `#v=` 深链并自动开详情抽屉、分享拿到的 URL 就是当前地址 |
| `css` | 触屏（`pointer:coarse`）与桌面各一遍 | 触屏上可点控件最小边 ≥32px、chip 实高 ≥34px、复选框 ≥20px、输入框 ≥16px；带 `:hover` 的规则全部落在 `(hover: hover)` 里；桌面端尺寸不被放大 |
| `links` | 4 页 × 2 档数据 × 4 种 UA | 按「iOS 短链 / 其余手机 scheme / 微信与桌面网页版」分流；两个链接都没有 `target`；`data-kind` 与数据完备度一致 |

`links` 那项的「2 档数据」是必要的：出厂状态**一条 `baidu_url` / `baidu_uid` 都没有**，只跑真实数据的话，「有短链」「有 uid」两条分支永远测不到。脚本会复制一份产物、临时给一条词条补上这两个字段再跑一遍（`data=rich`），并用 `#v=<key>` 深链把两档都定位到**同一条词条**上，否则比的不是同一家店。补充一句：`scripts/parity_*.html` 那套仍然是「同一版本前后对比、靠人眼看 title」，两者是互补关系，不是一个替代另一个。

如果哪天要在这套里加用例：注意端口。脚本会先写一个带随机 token 的文件再确认能读回来（被上次跑剩的 `http.server` 占着端口、目录却已删掉时，页面会静默 404、探针一片空白），端口被占就自动换 8987–8999 里的下一个，结束时把服务关掉。

## 补数据

`data/venues/*.json` 是唯一数据源。批量补字段用两个补丁脚本，它们只改 JSON，不再碰 HTML：

```bash
python3 scripts/patch_bars_dianping.py --dry    # 先看会改什么
python3 scripts/patch_bars_dianping.py          # 写回 bars.json
python3 scripts/patch_all_stores.py             # 写回 bichi.json
./render.sh                                     # 校验 + 重新构建
```

两个脚本都是**幂等**的：重复运行第二次不再有变更。`patch_bars_dianping.py` 里 `NOTE` / `SRC_ADD` 只在 `UPDATES` 命中的 key 上生效——这是原脚本的语义，脚本每次都会把「不生效的遗留条目」列出来，便于清理。`patch_all_stores.py` 里 `AVG` 是人均的唯一来源（先把所有 `avg` 清成 `null` 再写入），所以从 `AVG` 删掉一个 key 就能真正清掉它的人均。

### 百度店铺页（详情卡底部的两个链接）

详情卡底部是 **🧭 导航** 与 **🏪 百度店铺页** 两个按钮，都在 `src/static/venue-links.js`（四页共用），页面只把「当前记录 + 我的位置」喂进去。**两者都不需要任何密钥**——产物必须保持「零密钥、可离线双击打开」。

导航按钮的行为没变：有定位走 `direction` 步行路线，没定位退化为 `marker` 打点。

**店铺页**这里有个百度的硬限制要交代清楚：百度没有「经纬度 → 店铺页」的公开接口。URI API 的 `place/detail` 只认 POI 身份 `uid`，传坐标只能拿到打点或检索列表。所以按钮按数据完备度三档降级，**出厂状态用第 3 档，什么都不用填**：

| 档 | 数据 | 链接 | 落点 |
| --- | --- | --- | --- |
| 1 | `baidu_url` | 直接用该链接 | 人工收集的 `j.map.baidu.com` 短链，直达店铺页 |
| 2 | `baidu_uid` | `api.map.baidu.com/place/detail?uid=…` | 该 POI 的详情页（手上有 uid 时用） |
| 3 | 都没有 ← **出厂状态** | `api.map.baidu.com/place/search?query=…&region=上海&location=…` | 百度的检索页。名字够独特时**直接落在该店**（实测「啤酒阿姨（南苏州路店）」落点标题就是店名）；连锁/重名会落在候选列表，再点一次 |

三个字段都是**可选字段**，缺省不算数据错误。`validate_data.py` 只校验它们「填了的话得像样」：`baidu_url` 是 http(s)、`baidu_uid` 是 id 形态的字符串、`baidu_uid_at` 是日期。

**想升级到第 1 档（不用 AK）**：在百度地图 App 里搜到店 → 分享 → 复制 `j.map.baidu.com/xxxx` 短链，写进该条的 `baidu_url`，重跑 `./render.sh`。不必 181 家全补——只有「检索会落在一列候选上」的重名/连锁店才值得手工补，其余靠第 3 档就够。

### 手机端点「在百度地图打开」：按平台分流 + 三档降级

上面那张表管的是**落点**（店铺页 / 检索页）；手机上还要决定**用 App 开还是用网页开**。以前两个按钮只指 `api.map.baidu.com/...&output=html`——那是调起 API 的 web 端，手机上只会再开一个网页，进不了 App。现在的分流（`src/static/venue-links.js`）：

| 环境 | 行为 |
| --- | --- |
| iOS 且该条有 `baidu_url` | 直接用 `j.map.baidu.com` 短链，交给百度自己决定开 App 还是开网页（通用链接） |
| 其余手机（含安卓） | 用 `baidumap://map/...` scheme 直接调起 App；**2.2 秒内没离开页面**（多半是没装 App 或被拦）就回落到网页版链接，绝不制造死链 |
| 微信内置浏览器 | 一律走网页版：微信会拦掉 scheme，试了只会白点一次 |
| 桌面 | 一律走网页版：桌面本来也没有 App |

两个坑：**scheme 调起必须同 tab 导航**（`location.href`），不能用 `target="_blank"`——`_blank` 在移动浏览器里常被当弹窗拦掉，失败后还留一个空白标签页回不去，所以四个页面的这两个 `<a>` 都去掉了 `target`/`rel`；**`src` 参数按平台分开**（`ios.` / `andr.` / 网页版 `webapp.`），官方要求必传，不传不保证服务。回落计时器会被 `visibilitychange` / `pagehide` 取消，避免用户从 App 返回时被莫名跳到网页版。

排查时读两个 `<a>` 上的 `data-kind`，它标的是**这一档的真实落点**：`marker` / `direction` 是导航按钮，`search` / `detail` / `short` 是店铺页按钮（`detail` = 直达 POI 详情，必须有 `baidu_uid`；`short` = `j.map` 短链；`search` = 按店名检索），带 `+app` 后缀表示这个是 scheme、会先试调起 App，不带就是网页版地址。注意没有 uid 时**即使走 App 也是检索**（`baidumap://…/place/search`），标签是 `search+app` 而不是 `detail+app`——别把「能调起 App」当成「能直达店铺页」。（这条标签修过一次：原先按 `app` 是否非空来定，安卓上没 uid 的词条也被标成 `detail+app`，与「出厂状态全是检索」的实际落点不符。）

## 构建标记

模板 `<script>` 内用 JS 注释标记注入点：

```javascript
/* @@BUILD:json data/venues/bars.json -> VENUES@@ */
const VENUES = [ /* 构建生成，勿手改 */ ];
/* @@BUILD:end@@ */

/* @@BUILD:js src/static/map-base.js@@ */
/* @@BUILD:end@@ */

/* @@BUILD:css src/static/vendor/leaflet/leaflet.css@@ */
/* @@BUILD:end@@ */

/* @@BUILD:merge data/venues/bichi.json,data/venues/michelin.json -> EAT_STORES@@ */
const EAT_STORES = [ /* 构建生成：多源合并，勿手改 */ ];
/* @@BUILD:end@@ */
```

`css` 把 CSS 文件整段内联进 `<style>`（Tailwind、Leaflet、mobile.css 都走这条）。它是「原样拷贝」，不跑任何 CSS 处理，所以内联的资源里不能出现 `</style`（构建期会拦住）。

`merge` 标记的多个数据源用逗号分隔（源名取 JSON 文件名），构建期调用 `merge_venues.merge_sources()` 合成一份再内联。

`index.html` 里还有一个不产出 JS 的标记：把数据条数写进 HTML 文本。

```html
<span class="count">
  /* @@BUILD:count data/venues/bars.json@@ */
  0
  /* @@BUILD:end@@ */
  家
</span>
```

`count` 只接受数据源（逗号分隔，同 `merge` 的多源写法），不接受 `-> 目标名`，替换结果就是条数（如 `37`）。标记必须**整行出现**且起止缩进一致——所以它不能写成行内。

## 变更后如何验证

重构过地图底座之后，要确认产物与重构前「渲染结果一致」，不能只看代码。`scripts/parity_diag.html` 就是为此准备的探针：

它把一张地图页塞进同源 iframe，依次点 🛣️ / 📍 开关（页面没有的会跳过），再对 bars 页额外「点 🚇 开面板 → 勾第 1 条线」，每步把 DOM 计数与 Leaflet 真实状态（缩放、中心、bounds、pane 可见性）写进 `document.title`，供人或脚本读取。

```bash
mkdir -p /tmp/a /tmp/b
cp dist/*.html scripts/parity_diag.html /tmp/a/          # 版本 A
cp dist/*.html scripts/parity_diag.html /tmp/b/          # 版本 B（同一版本时用于确认探针自洽）
(cd /tmp/a && python3 -m http.server 8766 &)
(cd /tmp/b && python3 -m http.server 8765 &)
# 浏览器打开 http://localhost:8766/parity_diag.html#shanghai_michelin_2026.html
# 与     http://localhost:8765/parity_diag.html#shanghai_michelin_2026.html
# 对比两边页面标题里的这几十个计数：应逐字相同
```

**必须同版本前后对比**：两个目录放**同一版本**的产物、用**同一份探针**分别跑（例如重构前后各构建一次，各自复制进一个目录）。不要拿旧产物当基线去对新产物，否则新增图层（如地铁 pane 与站点）会被误判成回归。只想确认「新图层没有动到旧计数」时，也可以只跑新版本，看 `initial → metro_line1` 这一步里除地铁相关量外其余计数是否纹丝不动。

关注这些量：`polylines` / `road_labels` / `areas` / `pois` / `icons` / `list`，以及开关前后的增减与 `mapstate`。地铁新增 `metro_lines` / `metro_stations` / `metro_stations_visible` / `metro_stations_transfer` / `metro_chips` / `metro_chips_active` / `metro_stat` 与 `paneMetroLines` / `paneMetroStations` / `metro_hide_minor`。注意两点：

- `polylines` 只数 `.leaflet-roads-pane svg path`，地铁折线在独立的 `metroLinesPane` 里，所以**不进入** `polylines`，要看 `metro_lines`。
- `metro_stations` 是 **DOM 里的站数**，`metro_stations_visible` 是**几何可见的站数**：未勾线时站点根本不在 DOM；勾线后 z13 时普通站仍在 DOM，只是被 `.metro-stations-pane.hide-minor .metro-station:not(.transfer)` 用 `display:none` 藏掉。两个数要分开看，别混成一个。

**不要用 `firstTileZ` 判断缩放**——Leaflet 会保留 `fitBounds` 之前的旧瓦片，DOM 里第一个瓦片的 z 可能是初始值，而 `mapstate.z` 才是真实缩放。

定位流程用另一个探针，它会伪造 `navigator.geolocation`，再依次点 🧭 / 📏 / ✕，记录每步的提示条文案、按钮状态、我的位置标记数、精度圆数与名录前三项；最后一步「选中一家 + 已定位」会读出详情卡底部的两个链接落点（`navHref` / `poiHref` 取 `marker` / `direction` / `place-detail` / `place-search` / `short-link`，以及整行 `linkRow` 显隐）：

```bash
# 两个端口同样各开一个，对比页面标题
# http://localhost:8766/parity_geo_diag.html#shanghai_bichi_saojie_2026.html
# http://localhost:8765/parity_geo_diag.html#shanghai_bichi_saojie_2026.html
```

（`bars` 的定位实现是页面自己的，它不给 🧭 / ✕ 按钮设 id，所以这个探针只适用于 `bichi`、`michelin` 与 `eat`。）

详情弹窗与筛选计数用 `scripts/parity_ui_diag.html`：点地图标记 → 点列表行 → 开筛选 → 复位，每步读详情卡标题/类型/地址块/**底部两个链接**（导航按钮文案 + 整行显隐 + 店铺页按钮文案与降级档位 `data-kind`）与列表行数、计数文案。三页都能跑。

注意它依赖的类名各页不同：`bars` 的列表行是 `.venue-item`，`bichi` / `michelin` / `eat` 是 `.rest-item`；筛选复位要点第 0 个「全部」chip，因为 chip 再点一次并不会取消筛选。`eat` 页的筛选按钮是标签多选（`data-tag` + `.cat-btn`），探针里按 `.cat-btn` 第 0 个「全部」复位仍然适用，但标签是**可叠加多选**，与 `bichi` 的「榜单多选」语义一致、与 `michelin` 的「单选」不同。

## 本地预览

打开 `dist/index.html` 就是四张图的总入口；也可以直接用浏览器打开任一张 `dist/*.html`（`file://` 也能正常工作）。产物已经完全自包含——样式、脚本、数据、Leaflet 的运行时代码与图片全在单个 HTML 里，**断网也能正常渲染**（只有地图瓦片与百度跳转需要联网）。

需要 http 环境时：

```bash
python3 -m http.server 8000    # 然后访问 http://localhost:8000/dist/
```

## 部署（GitHub Pages）

**已上线**：<https://frankjie09.github.io/shanghai_map_pages/>

| 页面 | 线上地址 |
| --- | --- |
| 落地页（四张图总入口） | <https://frankjie09.github.io/shanghai_map_pages/> |
| 餐饮总览（三榜合一） | <https://frankjie09.github.io/shanghai_map_pages/shanghai_eat_2026.html> |
| 必吃榜 × 扫街榜 | <https://frankjie09.github.io/shanghai_map_pages/shanghai_bichi_saojie_2026.html> |
| 米其林指南 2026 | <https://frankjie09.github.io/shanghai_map_pages/shanghai_michelin_2026.html> |
| 酒吧 × Livehouse × 夜店 | <https://frankjie09.github.io/shanghai_map_pages/shanghai_bars_livehouse_2026.html> |

发布由 `.github/workflows/deploy-pages.yml` 完成：`main` 每次推送（或手动 `workflow_dispatch`）时，把 `dist/` 整个目录作为 Pages 产物上传发布；站点根页就是 `dist/index.html`，所以落地页的文件名必须是 `index.html`。

一次性配置（**均已完成**）：

- 仓库为 **public** —— 免费计划下 GitHub 不允许私有仓库使用 Pages。
- Pages 的 `Build and deployment → Source` 为 **GitHub Actions**（等价于 `POST /repos/{owner}/{repo}/pages` 带 `build_type=workflow`）。
- 推送凭据带 `workflow` scope。注意 `gh auth refresh -s workflow` **只更新 gh 自己的 keyring**，`~/.git-credentials` 里若存着旧 token，推送 `.github/workflows/*` 仍会被拒（报 `without 'workflow' scope`），需把凭据文件里的 token 一并换新。

日常注意：

- 工作流**不构建**，只在发布前跑一次 `python3 build.py --check` 当门禁：产物必须与源模板一致、落地页链接不得断开，否则拒发。
- 因此 **改了 `data/` 或 `src/` 就要跑 `./render.sh` 并提交 `dist/`**。`build.py` 里 `EXPECT` 记的条数是「数据体量」的护栏：数据增删后条数变了，`--check` 会报错要求你同步更新 `EXPECT`（落地页 `count` 标记的条数会自动算，不用手改）。

`dist/` 已提交进 git，所以旧平台（帽子云等）那种「构建命令留空 + 输出目录 `dist`」的静态托管方式同样仍然可用。

### 帽子云等静态平台

帽子云在**部署目录根部**找 `index.html` 或 `package.json` 来判定「这是不是一个静态站」，两个都没有就会拒绝部署并报：

```
ERROR: 未知服务类型：检测到当前应用非 Some[static] 应用。
```

本仓库的站点文件都在 `dist/`，根目录原本两个文件都没有，所以照下面配：

| 设置项 | 值 |
| --- | --- |
| 安装命令 | 留空 |
| 构建命令 | 留空（产物已提交，平台侧不需要构建） |
| 输出目录 | `dist` |
| 根目录 | 留空 |

根目录那个 `index.html` 是给平台做识别的兜底（转发到 `dist/index.html`），同时也是「输出目录误配成仓库根」时仍能跳对地方的安全网。**不要**改成加根目录 `package.json`：那会让平台以为这是个 Node 项目，可能去跑 `npm install` / `npm run build`，反而多一层失败点。

改平台配置后要**先保存再部署**，否则用的还是旧配置。

## 与旧仓库的关系

这些页面原本在 `gemini_htmls` 仓库中，数据内联在 HTML 里。本仓库把它拆成「JSON 源 + 构建期内联」并抽出了共用的地图底座；`eat`（三榜合并总览）是本仓库新增的页面，`gemini_htmls` 里没有对应快照。

`gemini_htmls` 里的同名页面是**冻结的历史快照**，不再更新。本仓库自己有一张 `dist/index.html` 落地页作为四张图的总入口，线上地址为 <https://frankjie09.github.io/shanghai_map_pages/>；`gemini_htmls` 的 `index.html` 可以改成指向它。
