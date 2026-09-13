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
        poiMinZoom: { area: 10, landmark: 12 }
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
        bindLabels: bindLabels,
        geoDist: geoDist,
        fmtDist: fmtDist,
        bearingOf: bearingOf
    };
})();
