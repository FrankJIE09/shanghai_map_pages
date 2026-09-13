/* 定位控件（授权 → 落点/精度圈 → 距离排序 → 清除）。

   只有需要「距离 + 近→远排序」的两页（bichi / michelin）内联本文件；bars 不内联，
   否则它要白白背上这段用不到的代码（约 9 KB）。

   依赖：先内联 map-base.js（用到 MapBase.geoDist / fmtDist）。
   用法：MapBase.initGeoControls(map, { ... }) —— 参数见下。 */
(function () {
    'use strict';

    /* cfg：
     zoom          定位后 flyTo 的最低缩放（默认 15）
     el            提示条元素 id（默认 map-hint）
     hint          提示条配色 { plain, err, border:{ok,err}, bg }
     onPosition    位置变化后刷新名录与标记
     onSortChanged 「近→远」开关切换后刷新名录
     onHintReset   提示条 5 秒复原时的回调
     onClear       清除定位后的额外收尾（如收起详情卡）
   */
MapBase.initGeoControls = function (map, cfg) {
    const c = Object.assign({
        zoom: 15, el: 'map-hint',
        onPosition: null, onSortChanged: null, onHintReset: null, onClear: null
    }, cfg || {});
    const h = Object.assign({ plain: '#1F402B', err: '#B91C1C' }, c.hint || {});

    const S = { marker: null, circle: null, latlng: null, watchId: null, busy: false, sortByDist: false };
    const OPTS = { enableHighAccuracy: true, timeout: 12000, maximumAge: 20000 };

        /** 某条记录到「我的位置」的距离（米）；未定位返回 null。 */
        function distOf(r) {
            return (S.latlng && r && r.coords) ? MapBase.geoDist(S.latlng, r.coords) : null;
        }

    /* 定位/错误提示：借用地图上方的 hint 条，5 秒后恢复默认统计 */
    function flashHint(text, isErr) {
        const el = document.getElementById(c.el);
        if (!el) return;
        el.textContent = text;
        el.style.color = isErr ? h.err : h.plain;
        if (h.border) el.style.borderColor = isErr ? h.border.err : h.border.ok;
        if (h.bg) el.style.background = h.bg;
        clearTimeout(flashHint._t);
        flashHint._t = setTimeout(function () {
            el.style.color = '';
            if (h.border) el.style.borderColor = '';
            if (h.bg) el.style.background = '';
            if (c.onHintReset) c.onHintReset();
        }, 5000);
    }

    function paintSortBtn() {
        const b = document.getElementById('sort-dist');
        if (!b) return;
        b.classList.toggle('active', S.sortByDist);
        b.textContent = S.sortByDist ? '📏 近→远 ✓' : '📏 近→远';
        b.title = S.sortByDist
            ? '已按距你远近排序，再点一次恢复按店名排序'
            : '按距我的位置远近排序（首次点击会请求定位授权）';
    }

    function setGeoBtn(on, busy) {
        const btn = document.getElementById('locate-btn');
        const clr = document.getElementById('locate-clear');
        if (btn) {
            btn.classList.toggle('locate-on', !!on);
            btn.innerHTML = busy ? '⏳' : '🧭';
            btn.title = on ? '重新居中到我的位置' : '定位到我的位置（需浏览器授权）';
        }
        if (clr) clr.style.display = on ? 'flex' : 'none';
    }

    /* 把定位结果显示到地图上；recenter=true 时才移动地图 */
    function applyUserPos(pos, recenter) {
        const crd = pos.coords;
        const next = [crd.latitude, crd.longitude];
        const moved = S.latlng ? geoDist(S.latlng, next) : Infinity;
        S.latlng = next;

        if (!S.marker) {
            S.marker = L.marker(S.latlng, {
                zIndexOffset: 2000,
                keyboard: false,
                icon: L.divIcon({ className: '', html: '<div class="user-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] })
            }).addTo(map).bindTooltip('我的位置', { permanent: true, direction: 'top', offset: [0, -12], className: 'user-tip' });
        } else {
            S.marker.setLatLng(S.latlng);
        }

        const acc = Math.max(20, crd.accuracy || 50);
        if (!S.circle) {
            S.circle = L.circle(S.latlng, {
                radius: acc, color: '#2563EB', weight: 1.2, opacity: 0.55,
                fillColor: '#3B82F6', fillOpacity: 0.13, interactive: false
            }).addTo(map);
        } else {
            S.circle.setLatLng(S.latlng).setRadius(acc);
        }

        if (recenter) map.flyTo(S.latlng, Math.max(map.getZoom(), c.zoom), { duration: 0.8 });
        if (recenter || moved > 40) { if (c.onPosition) c.onPosition(); }
        return acc;
    }

    function onGeoOk(pos) {
        S.busy = false;
        setGeoBtn(true, false);
        const acc = applyUserPos(pos, true);
        paintSortBtn();
            flashHint('📍 已定位（精度约 ' + MapBase.fmtDist(acc) + '）· 名录已显示距离', false);
    }

    function onGeoErr(err) {
        S.busy = false;
        setGeoBtn(!!S.latlng, false);
        const code = err && err.code;
        flashHint(code === 1 ? '🚫 定位被拒绝：请点地址栏的「位置」图标允许授权后重试'
            : code === 3 ? '⏱️ 定位超时：请到窗边 / 室外，并确认系统定位服务已开启'
                : '⚠️ 暂时拿不到位置：请检查系统定位服务或稍后重试', true);
    }

    /* 点击 🧭：首次请求授权定位，之后仅重新居中 */
    function locateMe() {
        if (!navigator.geolocation) { flashHint('❌ 当前浏览器不支持定位（Geolocation API）', true); return; }
        if (S.latlng) { map.flyTo(S.latlng, Math.max(map.getZoom(), c.zoom), { duration: 0.8 }); return; }
        if (S.busy) return;
        S.busy = true;
        setGeoBtn(true, true);
        navigator.geolocation.getCurrentPosition(onGeoOk, onGeoErr, OPTS);
        if (S.watchId == null) {
            // 持续跟踪：位置变化只刷新标记与距离，不打断正在浏览的地图
            S.watchId = navigator.geolocation.watchPosition(
                p => applyUserPos(p, false),
                () => { },
                OPTS
            );
        }
    }

    function clearLocation() {
        if (S.watchId != null) { navigator.geolocation.clearWatch(S.watchId); S.watchId = null; }
        if (S.marker) { map.removeLayer(S.marker); S.marker = null; }
        if (S.circle) { map.removeLayer(S.circle); S.circle = null; }
        S.latlng = null;
        S.busy = false;
        setGeoBtn(false, false);
        if (c.onPosition) c.onPosition();
        paintSortBtn();
        if (c.onClear) c.onClear();
        flashHint('已清除定位：距离与排序已恢复默认', false);
    }

    function toggleSortDist() {
        if (S.sortByDist) {
            S.sortByDist = false;
        } else {
            S.sortByDist = true;
            if (!S.latlng) locateMe();       // 未定位时顺手请求授权
        }
        paintSortBtn();
        if (c.onSortChanged) c.onSortChanged();
    }

    /* 右上角定位控件（🧭 定位 / ✕ 清除） */
    function init() {
        const LocateControl = L.Control.extend({
            options: { position: 'topright' },
            onAdd: function () {
                const wrap = L.DomUtil.create('div', 'leaflet-bar');
                const css = 'display:flex;align-items:center;justify-content:center;width:30px;height:30px;text-decoration:none;background:#FCF9F2;';

                const btn = L.DomUtil.create('a', '', wrap);
                btn.id = 'locate-btn';
                btn.href = '#';
                btn.innerHTML = '🧭';
                btn.title = '定位到我的位置（需浏览器授权）';
                btn.style.cssText = css + 'font-size:15px;';
                L.DomEvent.on(btn, 'click', function (e) { L.DomEvent.stop(e); locateMe(); });

                const clr = L.DomUtil.create('a', '', wrap);
                clr.id = 'locate-clear';
                clr.href = '#';
                clr.innerHTML = '✕';
                clr.title = '清除定位与距离';
                clr.style.cssText = css + 'display:none;font-size:13px;color:#7F1D1D;';
                L.DomEvent.on(clr, 'click', function (e) { L.DomEvent.stop(e); clearLocation(); });
                return wrap;
            }
        });
        map.addControl(new LocateControl());
        setGeoBtn(false, false);
        paintSortBtn();
    }

    return {
        init: init,
        /** 当前定位点 [lat, lng]；未定位为 null。 */
        pos: function () { return S.latlng; },
        distOf: distOf,
        isSortByDist: function () { return S.sortByDist; },
        syncSortButton: paintSortBtn,
        toggleSortDist: toggleSortDist,
        locateMe: locateMe,
        clearLocation: clearLocation,
        applyUserPos: applyUserPos
    };
};
})();
