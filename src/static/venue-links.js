/* 详情卡底部的「导航 / 店铺页」链接（四页共用）。

   背景：百度没有「经纬度 -> 店铺页」的公开接口。店面界面（评分、评价、电话、
   营业时间、团购）只能靠 POI 身份打开，所以这里按数据完备度三档降级，且
   **每一档都不需要任何密钥**（产物必须保持零密钥、可离线打开）：

     1. venue.baidu_url  -> 人工收集的 j.map.baidu.com 短链，直达店铺页
     2. venue.baidu_uid  -> place/detail，直达该 POI 详情页（手上有 uid 时用）
     3. 都没有（出厂状态）-> place/search 关键词检索：名字够独特时百度会直接
                            落在该店，连锁/重名则落在候选列表，再点一次进店

   三个字段都是可选字段，缺省不会报错，只是页面按钮退到下一档。

   导航按钮维持原有行为：有定位走步行路线规划，无定位退化为打点标点。

   接口规范（百度地图开放平台 · 地图调起 API web 端）：
     place/detail  uid + output=html + src            -> POI 详情页
     place/search  query + region[+location+radius]   -> POI 检索结果列表
     direction     origin + destination + mode        -> 路线规划
     marker        location + title + content         -> 单点标注
   coord_type 必须显式传 wgs84 —— 本站坐标统一为 WGS-84，不传会整体偏移。 */
window.VenueLinks = (function () {
    'use strict';

    const SRC = 'webapp.shanghai-map-pages';   // 百度统计必填参数（webapp.company.app）
    const REGION = '上海';
    const RADIUS = 2000;                       // 关键词检索的周边半径（米）：容错 ±400 m 的街道近似点

    function enc(s) {
        return encodeURIComponent(String(s == null ? '' : s));
    }

    /** 百度店铺页：有 POI 身份就直达店面，否则退回关键词检索。 */
    function poi(v) {
        if (!v) return null;
        if (v.baidu_url) {
            return {
                kind: 'short',
                href: v.baidu_url,
                label: '🏪 百度店铺页',
                tip: '打开人工核实的百度地图店铺页'
            };
        }
        if (v.baidu_uid) {
            return {
                kind: 'detail',
                href: 'https://api.map.baidu.com/place/detail?uid=' + enc(v.baidu_uid) +
                    '&output=html&src=' + SRC,
                label: '🏪 百度店铺页',
                tip: '在百度地图打开该店详情页：评分、评价、电话与营业时间'
            };
        }
        let href = 'https://api.map.baidu.com/place/search?query=' + enc(v.name) +
            '&region=' + enc(REGION);
        // 带上本店坐标做周边检索，结果列表里正主会排在最前（region 优先级最低，兜底用）
        if (v.coords) {
            href += '&location=' + v.coords[0] + ',' + v.coords[1] +
                '&radius=' + RADIUS + '&coord_type=wgs84';
        }
        return {
            kind: 'search',
            href: href + '&output=html&src=' + SRC,
            label: '🔍 在百度找这家店',
            tip: '用店名在百度检索：名字够独特时会直接落在该店，连锁/重名则落在一列候选里。' +
                '想直达店面页可以给这条补 baidu_url（百度地图分享短链），见 README「百度店铺页」'
        };
    }

    /** 导航：有定位就规划步行路线，没有就把这家店标在图上。 */
    function nav(v, me) {
        if (!v || !v.coords) return null;
        const lat = v.coords[0], lng = v.coords[1];
        const name = enc(v.name);
        if (me) {
            return {
                kind: 'direction',
                href: 'https://api.map.baidu.com/direction?origin=latlng:' + me[0] + ',' + me[1] +
                    '|name:我的位置&destination=latlng:' + lat + ',' + lng + '|name:' + name +
                    '&mode=walking&region=' + enc(REGION) +
                    '&output=html&coord_type=wgs84&src=' + SRC,
                label: '🧭 百度步行导航到店',
                tip: '以你的位置为起点，调起百度步行路线规划'
            };
        }
        return {
            kind: 'marker',
            href: 'https://api.map.baidu.com/marker?location=' + lat + ',' + lng +
                '&title=' + name + '&content=' + name +
                '&output=html&coord_type=wgs84&src=' + SRC,
            label: '🧭 在百度地图打开',
            tip: '在百度地图上标出这家店；先点页面右上角 🧭 定位可换成步行导航'
        };
    }

    /** 当前记录 + 我的位置 -> 两个按钮的 href / 文案 / 提示。me 为 null 表示未定位。 */
    function bundle(v, me) {
        return { nav: nav(v, me), poi: poi(v) };
    }

    /** 详情卡底部链接的 DOM 接线。ids 默认对应四页共用的三个元素。
        返回 { update(v, me), hide() }——页面只负责把记录与定位喂进来。 */
    function mount(ids) {
        const o = Object.assign({ row: 'detail-links', nav: 'detail-nav', poi: 'detail-poi' }, ids || {});
        function el(k) {
            return document.getElementById(o[k]);
        }

        function hide() {
            const row = el('row');
            // 用内联 display 而非切 class：Tailwind 的 .hidden 只是普通选择器，
            // 内联样式稳赢，且不依赖页面是否加载了 Tailwind。
            if (row) row.style.display = 'none';
        }

        function update(v, me) {
            const row = el('row');
            if (!row) return;
            if (!v || !v.coords) { hide(); return; }
            const L = bundle(v, me);
            const a = el('nav');
            const b = el('poi');
            if (a && L.nav) {
                a.href = L.nav.href;
                a.textContent = L.nav.label;
                a.title = L.nav.tip;
                a.dataset.kind = L.nav.kind;
            }
            if (b && L.poi) {
                b.href = L.poi.href;
                b.textContent = L.poi.label;
                b.title = L.poi.tip;
                b.dataset.kind = L.poi.kind;
            }
            row.style.display = 'flex';
        }

        return { update: update, hide: hide };
    }

    return { SRC: SRC, nav: nav, poi: poi, bundle: bundle, mount: mount };
})();
