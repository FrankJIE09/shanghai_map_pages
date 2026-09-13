/* 共用地图底座：底图、道路骨架、区域/地标注记、球面几何。
   三页共用同一套 MAIN_ROADS（227 条），此前后者在三个 HTML 里各存一份，
   合计约 281 KB 纯冗余。

   依赖：Leaflet、window.MAP_THEMES（见 theme.js）。
   用法见各页 window.onload。 */
window.MapBase = (function () {
    'use strict';

    /* 内部状态：原先散落在各页的全局变量集中到这里 */
    const S = {
        map: null,
        roadsGroup: null,
        roadLabelsA: null,
        roadLabelsB: null,
        areasGroup: null,
        landmarksGroup: null,
        roadsVisible: true,
        poiVisible: true,
        roadStyle: null,
        btn: null,
        poiMinZoom: { area: 10, landmark: 12 },

        /* 地铁图层（drawMetro）：图层组、索引与勾选状态 */
        metroLinesGroup: null,
        metroStationsGroup: null,
        metroLineLayers: null,      // 线路 id -> polyline（建好但不入图，勾选后再 add）
        metroLineColor: null,       // 线路 id -> 线色（线色是线路固有属性，不进 theme.js）
        metroStationMarkers: null,  // 站 id -> marker
        metroStationLines: null,    // 站 id -> [线路 id]（由 lines.json 反查派生）
        metroStationNames: null,    // 站 id -> 站名
        metroSelected: null,        // Set<线路 id>，默认空 = 首屏不画任何地铁
        metroPanel: null,
        metroNamesOn: false,
        metroLineCount: 0,          // 13（数据驱动，不硬编码）
        metroStationCount: 0,       // 87
        metroTransferCount: 0,      // 47（被引用线路数 > 1 的站）
        metroZoom: { lines: 11, stations: 13, allStations: 14, names: 15 }
    };

    function getMap() {
        return S.map;
    }

    /* ---------------- 底图 ---------------- */

    function createMap(elId, opts) {
        const o = opts || {};
        const theme = o.theme || window.MAP_THEMES.light;
        const m = L.map(elId, Object.assign({
            center: [31.2304, 121.4737],
            zoom: 12,
            minZoom: 10,
            maxZoom: 18,
            zoomControl: true
        }, o.view));
        L.tileLayer(theme.tile.url, theme.tile.options).addTo(m);
        S.map = m;
        return m;
    }

    /* ---------------- 道路骨架 + 路名 ---------------- */

    function btnCss(theme, on) {
        const b = (theme && theme.btn) || {};
        return 'display:flex;align-items:center;justify-content:center;width:30px;height:30px;' +
            'font-size:15px;text-decoration:none;background:' + (on ? b.on : b.off) +
            (b.fg ? ';color:' + b.fg : '') + ';';
    }

    function drawRoads(opts) {
        const o = opts || {};
        const roads = o.roads || [];
        const theme = o.theme || window.MAP_THEMES.light;
        const map = S.map;
        S.roadStyle = theme.road;
        S.btn = theme.btn;

        map.createPane('roadsPane');
        map.getPane('roadsPane').style.zIndex = 350;
        map.createPane('roadLabelsPaneA');
        map.getPane('roadLabelsPaneA').style.zIndex = 355;
        map.getPane('roadLabelsPaneA').style.pointerEvents = 'none';
        map.createPane('roadLabelsPaneB');
        map.getPane('roadLabelsPaneB').style.zIndex = 354;
        map.getPane('roadLabelsPaneB').style.pointerEvents = 'none';

        S.roadsGroup = L.layerGroup();
        S.roadLabelsA = L.layerGroup();
        S.roadLabelsB = L.layerGroup();

        roads.forEach(function (r) {
            const st = S.roadStyle[r.tier] || S.roadStyle[3];
            L.polyline(r.path, {
                pane: 'roadsPane',
                color: st.color,
                weight: st.weight,
                opacity: st.opacity,
                lineCap: 'round',
                lineJoin: 'round',
                interactive: false
            }).addTo(S.roadsGroup);

            // 一级路名常驻（放大后），二级路名需更高缩放级别
            if (r.tier === 1 || r.tier === 2) {
                const mid = r.path[Math.floor(r.path.length / 2)];
                const mk = L.marker(mid, {
                    pane: r.tier === 1 ? 'roadLabelsPaneA' : 'roadLabelsPaneB',
                    interactive: false,
                    keyboard: false,
                    icon: L.divIcon({
                        className: '',
                        html: '<span class="road-name' + (r.tier === 1 ? ' road-name-major' : '') + '">' + r.name + '</span>',
                        iconSize: [0, 0],
                        iconAnchor: [0, 0]
                    })
                });
                (r.tier === 1 ? S.roadLabelsA : S.roadLabelsB).addLayer(mk);
            }
        });

        S.roadsGroup.addTo(map);
        S.roadLabelsA.addTo(map);
        S.roadLabelsB.addTo(map);
        updateRoadLabelVisibility();
        map.on('zoomend', updateRoadLabelVisibility);

        // 右上角开关
        const RoadsToggle = L.Control.extend({
            options: { position: 'topright' },
            onAdd: function () {
                const wrap = L.DomUtil.create('div', 'leaflet-bar');
                const btn = L.DomUtil.create('a', '', wrap);
                btn.href = '#';
                btn.title = '显示 / 隐藏道路骨架';
                btn.innerHTML = '🛣️';
                btn.style.cssText = btnCss(theme, true);
                L.DomEvent.on(btn, 'click', function (e) {
                    L.DomEvent.stop(e);
                    S.roadsVisible = !S.roadsVisible;
                    [S.roadsGroup, S.roadLabelsA, S.roadLabelsB].forEach(function (g) {
                        if (S.roadsVisible) { g.addTo(map); } else { map.removeLayer(g); }
                    });
                    btn.style.cssText = btnCss(theme, S.roadsVisible);
                    updateRoadLabelVisibility();
                });
                return wrap;
            }
        });
        map.addControl(new RoadsToggle());
    }

    function updateRoadLabelVisibility() {
        const map = S.map;
        const pa = map.getPane('roadLabelsPaneA');
        const pb = map.getPane('roadLabelsPaneB');
        const z = map.getZoom();
        if (pa) pa.style.display = (S.roadsVisible && z >= 13) ? '' : 'none';
        if (pb) pb.style.display = (S.roadsVisible && z >= 15) ? '' : 'none';
    }

    /* ---------------- 区域锚点 / 地标参照 ---------------- */

    function drawAreas(opts) {
        const o = opts || {};
        const map = S.map;
        map.createPane('areaLabelsPane');
        map.getPane('areaLabelsPane').style.zIndex = 370;
        map.getPane('areaLabelsPane').style.pointerEvents = 'none';

        const container = o.grouped ? (S.areasGroup = L.layerGroup()) : map;
        (o.areas || []).forEach(function (a) {
            const cls = a.kind === 'origin' ? 'area-label origin' : 'area-label';
            L.marker(a.coords, {
                pane: 'areaLabelsPane',
                interactive: false,
                keyboard: false,
                icon: L.divIcon({
                    className: '',
                    html: '<span class="' + cls + '">' + a.name + '</span>',
                    iconSize: [0, 0],
                    iconAnchor: [0, 0]
                })
            }).addTo(container);
        });
        if (o.grouped) S.areasGroup.addTo(map);
    }

    function drawLandmarks(opts) {
        const o = opts || {};
        const map = S.map;
        const theme = o.theme || window.MAP_THEMES.light;
        if (o.poiMinZoom) S.poiMinZoom = o.poiMinZoom;

        map.createPane('landmarksPane');
        map.getPane('landmarksPane').style.zIndex = 365;
        map.getPane('landmarksPane').style.pointerEvents = 'none';

        const container = o.grouped ? (S.landmarksGroup = L.layerGroup()) : map;
        (o.landmarks || []).forEach(function (p) {
            const k = p.kind;
            L.marker(p.coords, {
                pane: 'landmarksPane',
                interactive: false,
                keyboard: false,
                icon: L.divIcon({
                    className: '',
                    html: '<div class="poi-mark"><span class="poi-dot ' + k + '"></span>' +
                        '<span class="poi-name ' + k + '">' + p.name + '</span></div>',
                    iconSize: [0, 0],
                    iconAnchor: [0, 0]
                })
            }).addTo(container);
        });
        if (!o.grouped) return;

        S.landmarksGroup.addTo(map);
        updatePoiVisibility();
        map.on('zoomend', updatePoiVisibility);

        const PoiToggle = L.Control.extend({
            options: { position: 'topright' },
            onAdd: function () {
                const wrap = L.DomUtil.create('div', 'leaflet-bar');
                const btn = L.DomUtil.create('a', '', wrap);
                btn.href = '#';
                btn.title = '显示 / 隐藏地标参照';
                btn.innerHTML = '📍';
                btn.style.cssText = btnCss(theme, true);
                L.DomEvent.on(btn, 'click', function (e) {
                    L.DomEvent.stop(e);
                    S.poiVisible = !S.poiVisible;
                    [S.areasGroup, S.landmarksGroup].forEach(function (g) {
                        if (!g) return;
                        if (S.poiVisible) { g.addTo(map); } else { map.removeLayer(g); }
                    });
                    btn.style.cssText = btnCss(theme, S.poiVisible);
                    updatePoiVisibility();
                });
                return wrap;
            }
        });
        map.addControl(new PoiToggle());
    }

    function updatePoiVisibility() {
        const map = S.map;
        const pa = map.getPane('areaLabelsPane');
        const pl = map.getPane('landmarksPane');
        const z = map.getZoom();
        if (pa) pa.style.display = (S.poiVisible && z >= S.poiMinZoom.area) ? '' : 'none';
        if (pl) pl.style.display = (S.poiVisible && z >= S.poiMinZoom.landmark) ? '' : 'none';
    }

    /* ---------------- 地铁：线路折线 + 站点 ----------------

       lines.json 给线路（id / name / color / path / stations 引用），stations.json 只给
       站（id / name / coords，故意不带 lines 字段）：「所属线路」与「是否换乘」都在这里
       由 lines.json 反查派生（被引用线路数 > 1 即换乘站）。线色是线路的固有属性、不随主题
       变化，所以存在 lines.json 上，不塞进 theme.js 的「主题配色」。

       缩放分级（与默认 fitBounds(maxZoom:13/14) 贴合）：
         z 11~12 只画勾选的线路（细线），不画站
         z 13    画站，但只画换乘站
         z >=14  画全部站
         z >=15  站名可用（靠 hover，不用 permanent tooltip —— 密集站会铺满地图）
       pane：metroLinesPane(352) 压在道路骨架之上、路名之下；metroStationsPane(356) 在
       路名之上、地标之下。站点必须显式 pane，否则会落进默认 markerPane(600) 去和店铺
       图标抢位置。 */
    function drawMetro(opts) {
        const o = opts || {};
        const lines = o.lines || [];
        const stations = o.stations || [];
        const theme = o.theme || window.MAP_THEMES.light;
        const map = S.map;

        // 反查索引：站 -> 所属线路（lines 由 station 反查，换乘与否由此派生）
        const stationLines = {};
        const lineColor = {};
        const stationNames = {};
        lines.forEach(function (l) {
            lineColor[l.id] = l.color;
            (l.stations || []).forEach(function (sid) {
                if (!stationLines[sid]) stationLines[sid] = [];
                stationLines[sid].push(l.id);
            });
        });
        stations.forEach(function (s) { if (s && s.id) stationNames[s.id] = s.name; });

        S.metroStationLines = stationLines;
        S.metroStationNames = stationNames;
        S.metroLineColor = lineColor;
        S.metroLineCount = lines.length;
        S.metroStationCount = stations.length;
        S.metroTransferCount = stations.filter(function (s) {
            return (stationLines[s.id] || []).length > 1;
        }).length;
        S.metroSelected = new Set();     // 默认全不选：首屏已有 37 个店标，不再叠地铁
        S.metroNamesOn = false;

        map.createPane('metroLinesPane');
        map.getPane('metroLinesPane').style.zIndex = 352;
        map.getPane('metroLinesPane').style.pointerEvents = 'none';
        map.createPane('metroStationsPane');
        const stPane = map.getPane('metroStationsPane');
        stPane.style.zIndex = 356;
        stPane.classList.add('metro-stations-pane');   // 供页面 CSS 与 parity 探针定位

        S.metroLinesGroup = L.layerGroup().addTo(map);
        S.metroStationsGroup = L.layerGroup().addTo(map);

        // 线路：一次建好，勾选后再入图层组（未勾选的不画 —— 1/2/8/10/12/13 号线在人民
        // 广场一带高度重叠，13 条全亮会直接压掉店标）
        S.metroLineLayers = {};
        lines.forEach(function (l) {
            S.metroLineLayers[l.id] = L.polyline(l.path, {
                pane: 'metroLinesPane',
                color: l.color,
                weight: 2,
                opacity: 0.85,
                lineCap: 'round',
                lineJoin: 'round',      // 相邻保留站直连会有折角（如 7 号线 4182 m 跨站直连）
                interactive: false,
                className: 'metro-line'
            });
        });

        // 站点：普通站单环、换乘站白底双环；多线共用时外环按线路色分割（CSS 里做）。
        // 视觉权重明显低于 32px 的店铺图标：普通站 9px、换乘站 13px，无填充高亮。
        S.metroStationMarkers = {};
        stations.forEach(function (s) {
            if (!s || !s.coords) return;
            const ids = stationLines[s.id] || [];
            const cols = ids.map(function (id) { return lineColor[id]; }).filter(Boolean);
            if (!cols.length) return;                       // 不在任何线路上：不画（数据兜底）
            const isTransfer = ids.length > 1;
            const size = isTransfer ? 13 : 9;
            const mk = L.marker(s.coords, {
                pane: 'metroStationsPane',
                interactive: true,                          // hover 出站名（z>=15）
                keyboard: false,
                icon: L.divIcon({
                    className: 'metro-station' + (isTransfer ? ' transfer' : ''),
                    html: '',
                    iconSize: [size, size],
                    iconAnchor: [size / 2, size / 2]
                })
            });
            // Leaflet 接管 marker 的 DOM：元素由 divIcon 生成，data-* 与线色在入图时补上
            mk.on('add', function () {
                const el = mk.getElement();
                if (!el) return;
                el.dataset.stationId = s.id;
                el.dataset.lines = ids.join(',');
                el.dataset.transfer = isTransfer ? '1' : '0';
                el.style.setProperty('--mc', cols[0]);
                if (cols[1]) el.style.setProperty('--mc2', cols[1]);
                if (cols[2]) el.style.setProperty('--mc3', cols[2]);
            });
            S.metroStationMarkers[s.id] = mk;
        });

        updateMetroVisibility();
        map.on('zoomend', updateMetroVisibility);

        // 右上角 🚇：展开线路多选面板（chip 复用页面已有的 .chip / .chip.active）
        const MetroControl = L.Control.extend({
            options: { position: 'topright' },
            onAdd: function () {
                const wrap = L.DomUtil.create('div', 'metro-ctl');
                const bar = L.DomUtil.create('div', 'leaflet-bar', wrap);
                const btn = L.DomUtil.create('a', '', bar);
                btn.href = '#';
                btn.title = '地铁线路图层（可多选）';
                btn.innerHTML = '🚇';
                btn.style.cssText = btnCss(theme, false);

                const panel = L.DomUtil.create('div', 'metro-panel hidden', wrap);
                panel.innerHTML =
                    '<div class="metro-panel-head">🚇 地铁线路' +
                    '<span class="metro-panel-stat" data-metro-stat></span></div>' +
                    '<div class="metro-panel-acts">' +
                    '<button type="button" class="chip px-2 py-0.5 text-[10px] rounded" data-metro-act="all">全选</button>' +
                    '<button type="button" class="chip px-2 py-0.5 text-[10px] rounded" data-metro-act="none">全不选</button>' +
                    '</div><div class="metro-panel-chips" data-metro-chips></div>';

                const chips = panel.querySelector('[data-metro-chips]');
                lines.forEach(function (l) {
                    const b = document.createElement('button');
                    b.type = 'button';
                    b.className = 'chip px-2 py-0.5 text-[10px] rounded';
                    b.dataset.line = l.id;
                    b.innerHTML = '<span class="metro-dot" style="background:' + l.color + '"></span>' + l.name;
                    chips.appendChild(b);
                });

                L.DomEvent.disableClickPropagation(wrap);
                L.DomEvent.disableScrollPropagation(panel);

                L.DomEvent.on(btn, 'click', function (e) {
                    L.DomEvent.stop(e);
                    const open = !panel.classList.contains('hidden');
                    panel.classList.toggle('hidden');
                    btn.style.cssText = btnCss(theme, !open);
                });

                L.DomEvent.on(panel, 'click', function (e) {
                    const act = e.target.closest('[data-metro-act]');
                    if (act) {
                        S.metroSelected.clear();
                        if (act.dataset.metroAct === 'all') {
                            lines.forEach(function (l) { S.metroSelected.add(l.id); });
                        }
                        applyMetroSelection();
                        return;
                    }
                    const chip = e.target.closest('[data-line]');
                    if (!chip) return;
                    const id = chip.dataset.line;
                    if (S.metroSelected.has(id)) S.metroSelected.delete(id);
                    else S.metroSelected.add(id);
                    applyMetroSelection();
                });

                S.metroPanel = panel;
                return wrap;
            }
        });
        map.addControl(new MetroControl());
        syncMetroUi();
    }

    /** 按 S.metroSelected 重算「画哪些线、画哪些站」，再走一次分级显隐。 */
    function applyMetroSelection() {
        const sel = S.metroSelected;
        S.metroLinesGroup.clearLayers();
        sel.forEach(function (id) {
            const lyr = S.metroLineLayers[id];
            if (lyr) S.metroLinesGroup.addLayer(lyr);
        });
        S.metroStationsGroup.clearLayers();
        if (sel.size) {
            Object.keys(S.metroStationMarkers).forEach(function (sid) {
                const ids = S.metroStationLines[sid] || [];
                for (let i = 0; i < ids.length; i++) {
                    // 换乘站若其任一线被勾选即显示
                    if (sel.has(ids[i])) { S.metroStationsGroup.addLayer(S.metroStationMarkers[sid]); return; }
                }
            });
        }
        updateMetroVisibility();
        syncMetroUi();
    }

    function updateMetroVisibility() {
        const map = S.map;
        if (!map || !S.metroLinesGroup) return;
        const z = map.getZoom();
        const Z = S.metroZoom;
        const has = !!(S.metroSelected && S.metroSelected.size);

        const pl = map.getPane('metroLinesPane');
        const ps = map.getPane('metroStationsPane');
        if (pl) pl.style.display = (has && z >= Z.lines) ? '' : 'none';
        const showStations = !!(has && z >= Z.stations);
        if (ps) {
            ps.style.display = showStations ? '' : 'none';
            // z13 只留换乘站，z>=14 全部站：整块 pane 切一个 class，不逐个 add/removeLayer
            ps.classList.toggle('hide-minor', z < Z.allStations);
        }

        // 低缩放只要一根细线，放大后再加粗
        const weight = z >= Z.allStations ? 3.2 : (z >= Z.stations ? 2.4 : 1.8);
        if (S.metroSelected) {
            S.metroSelected.forEach(function (id) {
                const lyr = S.metroLineLayers[id];
                if (lyr) lyr.setStyle({ weight: weight });
            });
        }
        // 站名只在 z>=15 可用，且靠 hover 出（密集站点不用 permanent tooltip）
        setMetroStationNames(z >= Z.names);
    }

    function setMetroStationNames(on) {
        if (S.metroNamesOn === on || !S.metroStationMarkers) return;
        S.metroNamesOn = on;
        Object.keys(S.metroStationMarkers).forEach(function (sid) {
            const mk = S.metroStationMarkers[sid];
            if (on) {
                if (!mk.getTooltip()) {
                    mk.bindTooltip(S.metroStationNames[sid] || '', {
                        direction: 'top', offset: [0, -7], className: 'm-tip metro-tip'
                    });
                }
            } else if (mk.getTooltip()) {
                mk.unbindTooltip();
            }
        });
    }

    function syncMetroUi() {
        const panel = S.metroPanel;
        if (!panel || !S.metroSelected) return;
        panel.querySelectorAll('[data-line]').forEach(function (b) {
            b.classList.toggle('active', S.metroSelected.has(b.dataset.line));
        });
        const stat = panel.querySelector('[data-metro-stat]');
        if (stat) {
            stat.textContent = '已选 ' + S.metroSelected.size + '/' + S.metroLineCount + ' 条线 · ' +
                S.metroStationCount + ' 站（换乘 ' + S.metroTransferCount + '）';
        }
    }

    /* ---------------- 标记上的常驻名称 ---------------- */

    function bindLabels(items, markerMap, permanent) {
        (items || []).forEach(function (r) {
            const mk = markerMap[r.key];
            if (!mk) return;
            if (mk.getTooltip && mk.getTooltip()) mk.unbindTooltip();
            mk.bindTooltip(r.name, {
                permanent: !!permanent,
                direction: 'top',
                offset: [0, -12],
                className: 'm-tip'
            });
        });
    }

    /* ---------------- 球面几何 ---------------- */

    /** 两点球面距离（米）。a、b 均为 [lat, lng]。 */
    function geoDist(a, b) {
        const R = 6371000, rad = d => d * Math.PI / 180;
        const dLat = rad(b[0] - a[0]), dLng = rad(b[1] - a[1]);
        const la1 = rad(a[0]), la2 = rad(b[0]);
        const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
        return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
    }

    function fmtDist(m) {
        if (m == null) return '';
        if (m < 1000) return `${Math.round(m / 10) * 10} m`;
        return `${(m / 1000).toFixed(m < 10000 ? 1 : 0)} km`;
    }

    /** 从 userPos 看向 target.coords 的 8 向方位。 */
    function bearingOf(userPos, target) {
        if (!userPos || !target || !target.coords) return '';
        const rad = d => d * Math.PI / 180;
        const y = Math.sin(rad(target.coords[1] - userPos[1])) * Math.cos(rad(target.coords[0]));
        const x = Math.cos(rad(userPos[0])) * Math.sin(rad(target.coords[0])) -
            Math.sin(rad(userPos[0])) * Math.cos(rad(target.coords[0])) *
            Math.cos(rad(target.coords[1] - userPos[1]));
        const deg = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
        return ['正北', '东北', '正东', '东南', '正南', '西南', '正西', '西北'][Math.round(deg / 45) % 8];
    }

    return {
        state: S,
        getMap: getMap,
        createMap: createMap,
        drawRoads: drawRoads,
        updateRoadLabelVisibility: updateRoadLabelVisibility,
        drawAreas: drawAreas,
        drawLandmarks: drawLandmarks,
        updatePoiVisibility: updatePoiVisibility,
        drawMetro: drawMetro,
        updateMetroVisibility: updateMetroVisibility,
        bindLabels: bindLabels,
        geoDist: geoDist,
        fmtDist: fmtDist,
        bearingOf: bearingOf
    };
})();
