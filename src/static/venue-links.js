/* 详情卡底部的「导航 / 店铺页 / 分享」链接（四页共用）。

   背景：百度没有「经纬度 -> 店铺页」的公开接口。店面界面（评分、评价、电话、
   营业时间、团购）只能靠 POI 身份打开，所以店铺页按数据完备度三档降级，
   且**每一档都不需要任何密钥**（产物必须保持零密钥）：

     1. venue.baidu_url  -> 人工收集的 j.map.baidu.com 短链，直达店铺页
     2. venue.baidu_uid  -> place/detail，直达该 POI 详情页（手上有 uid 时用）
     3. 都没有（出厂状态）-> place/search 关键词检索：名字够独特时百度会直接
                            落在该店，连锁/重名则落在候选列表，再点一次进店

   ================== 手机端「直接跳 App」（2026-09 起） ==================
   以前这两个按钮只指 https://api.map.baidu.com/...&output=html —— 那是百度
   地图调起 API 的 **web 端**，手机上只会打开一个网页，进不了 App。现在按
   平台分流：

     iOS + 有 baidu_url   -> 直接用短链（j.map.baidu.com），交给百度自己决定
                             「开 App 还是开网页」，体验最好且无需兜底
     其余手机（含安卓）    -> 用 baidumap:// scheme 直接调起 App；
                             2.2 秒内没离开页面（说明没装 App / 被拦）就回落到
                             网页版链接，绝不制造死链
     微信内置浏览器 / 桌面 -> 一律走网页版：微信会拦掉 scheme，桌面也没有 App

   注意 scheme 调起必须**同 tab 导航**（location.href），不能用 target="_blank"：
   _blank 在移动浏览器里常被当弹窗拦掉，失败后还会留一个空白 tab。所以四个页面
   的这两个 <a> 都去掉了 target/rel。

   开 App 协议的 src 是必选参数，格式按平台分开（官方：不传不保证服务）：
     ios.companyName.appName / andr.companyName.appName
   网页版另有自己的 webapp.companyName.appName，两套不要混用。

   接口规范（百度地图开放平台 · 地图调起 API）：
     web     place/detail  uid + output=html + src
             place/search  query + region[+location+radius]
             direction     origin + destination + mode
             marker        location + title + content
     app     baidumap://map 下同名 service/action，参数一致、去掉 output
   coord_type 必须显式传 wgs84 —— 本站坐标统一为 WGS-84，不传会整体偏移。 */
window.VenueLinks = (function () {
    'use strict';

    const SRC_WEB = 'webapp.shanghai-map-pages';   // 网页版来源（百度统计参数）
    const SRC_IOS = 'ios.shanghai-map-pages';      // iOS 调起 App 的来源
    const SRC_ANDROID = 'andr.shanghai-map-pages'; // 安卓调起 App 的来源
    const REGION = '上海';
    const RADIUS = 2000;                       // 关键词检索的周边半径（米）：容错 ±400 m 的街道近似点
    const APP_TIMEOUT = 2200;                  // 调起 App 的等待上限（毫秒），到点视为「没装 App」

    const UA = typeof navigator === 'undefined' ? '' : (navigator.userAgent || '');
    const IS_IOS = /iPhone|iPad|iPod/i.test(UA) ||
        // iPadOS 13+ 的 Safari 伪装成 macOS，靠触摸点数把它认回来
        (/Macintosh/.test(UA) && typeof navigator !== 'undefined' && navigator.maxTouchPoints > 1);
    const IS_ANDROID = /Android|HarmonyOS/i.test(UA);
    const IS_MOBILE = IS_IOS || IS_ANDROID;
    const IS_WECHAT = /MicroMessenger/i.test(UA);      // 微信内会拦 scheme，直接走网页版
    const IS_TOUCH = IS_MOBILE ||
        (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(pointer:coarse)').matches);

    function enc(s) {
        return encodeURIComponent(String(s == null ? '' : s));
    }

    /** 该不该尝试用 scheme 调起 App。桌面 / 微信一律不试，避免点出空白页。 */
    function canLaunchApp() {
        return IS_MOBILE && !IS_WECHAT;
    }

    /** 百度店铺页的网页版地址：有 POI 身份就直达店面，否则退回关键词检索。 */
    function poiWebHref(v) {
        if (v.baidu_url) return v.baidu_url;
        if (v.baidu_uid) {
            return 'https://api.map.baidu.com/place/detail?uid=' + enc(v.baidu_uid) +
                '&output=html&src=' + SRC_WEB;
        }
        let href = 'https://api.map.baidu.com/place/search?query=' + enc(v.name) +
            '&region=' + enc(REGION);
        // 带上本店坐标做周边检索，结果列表里正主会排在最前（region 优先级最低，兜底用）
        if (v.coords) {
            href += '&location=' + v.coords[0] + ',' + v.coords[1] +
                '&radius=' + RADIUS + '&coord_type=wgs84';
        }
        return href + '&output=html&src=' + SRC_WEB;
    }

    /** 百度店铺页的 App scheme；没有 POI 身份（只能关键词搜）时返回 null。 */
    function poiAppHref(v) {
        if (v.baidu_uid) {
            return 'baidumap://map/place/detail?uid=' + enc(v.baidu_uid) + '&src=' + appSrc();
        }
        let href = 'baidumap://map/place/search?query=' + enc(v.name) + '&region=' + enc(REGION);
        if (v.coords) {
            href += '&location=' + v.coords[0] + ',' + v.coords[1] +
                '&radius=' + RADIUS + '&coord_type=wgs84';
        }
        return href + '&src=' + appSrc();
    }

    function appSrc() {
        return IS_IOS ? SRC_IOS : SRC_ANDROID;
    }

    /** 装一个链接对象：web 是兜底网页地址，app 为空表示不要尝试调起 App。 */
    function makeLink(kind, web, app, label, tip) {
        return { kind: kind, web: web, app: app || null, label: label, tip: tip };
    }

    /** 百度店铺页：按平台与数据完备度选最终跳转方式。 */
    function poi(v) {
        if (!v) return null;
        const web = poiWebHref(v);
        const app = poiAppHref(v);
        const label = v.baidu_url || v.baidu_uid ? '🏪 百度店铺页' : '🔍 在百度找这家店';
        /* kind 描述的是「这一档到底能不能直达店铺页」，要按分支各自的真实落点写，
           不能拿 app 的真假去推：没有 uid 时 poiAppHref 也会返回一个 scheme，但那是
           baidumap://…/place/search（按店名检索），标成 detail 会让人误判「直达生效了」。
           App 分支持的是 uid（detail），网页兜底才是 url 短链（short）。 */
        const direct = !!v.baidu_url || !!v.baidu_uid;
        const webKind = v.baidu_url ? 'short' : (v.baidu_uid ? 'detail' : 'search');

        // iOS 有短链：交给百度自己决定开 App 还是开网页（j.map 短链会走通用链接）
        if (IS_IOS && v.baidu_url) {
            return makeLink('short', v.baidu_url, null, label,
                '打开人工核实的百度地图店铺页（iOS 上会优先跳 App）');
        }
        if (canLaunchApp()) {
            return makeLink(v.baidu_uid ? 'detail' : 'search', web, app, label,
                direct
                    ? '直接在百度地图 App 打开该店详情：评分、评价、电话与营业时间'
                    : '在百度地图 App 里按店名检索：名字够独特会直接落在该店。' +
                      '想直达店面页可以给这条补 baidu_url（百度地图分享短链），见 README「百度店铺页」');
        }
        return makeLink(webKind, web, null,
            label,
            direct
                ? '在网页版百度地图打开该店详情页'
                : '用店名在百度检索：名字够独特时会直接落在该店，连锁/重名则落在一列候选里。' +
                  '想直达店面页可以给这条补 baidu_url（百度地图分享短链），见 README「百度店铺页」');
    }

    /** 导航：有定位就规划步行路线，没有就把这家店标在图上。 */
    function nav(v, me) {
        if (!v || !v.coords) return null;
        const lat = v.coords[0], lng = v.coords[1];
        const name = enc(v.name);
        const src = appSrc();
        if (me) {
            const origin = 'latlng:' + me[0] + ',' + me[1] + '|name:我的位置';
            const dest = 'latlng:' + lat + ',' + lng + '|name:' + name;
            return makeLink('direction',
                'https://api.map.baidu.com/direction?origin=' + origin + '&destination=' + dest +
                    '&mode=walking&region=' + enc(REGION) +
                    '&output=html&coord_type=wgs84&src=' + SRC_WEB,
                canLaunchApp()
                    ? 'baidumap://map/direction?origin=' + origin + '&destination=' + dest +
                      '&mode=walking&region=' + enc(REGION) + '&coord_type=wgs84&src=' + src
                    : null,
                '🧭 百度步行导航到店',
                '以你的位置为起点，调起百度步行路线规划');
        }
        return makeLink('marker',
            'https://api.map.baidu.com/marker?location=' + lat + ',' + lng +
                '&title=' + name + '&content=' + name +
                '&output=html&coord_type=wgs84&src=' + SRC_WEB,
            canLaunchApp()
                ? 'baidumap://map/marker?location=' + lat + ',' + lng +
                  '&title=' + name + '&content=' + name +
                  '&coord_type=wgs84&src=' + src
                : null,
            '🧭 在百度地图打开',
            '在百度地图上标出这家店；先点页面右上角 🧭 定位可换成步行导航');
    }

    /** 当前记录 + 我的位置 -> 两个按钮的链接对象。me 为 null 表示未定位。 */
    function bundle(v, me) {
        return { nav: nav(v, me), poi: poi(v) };
    }

    /* ---------------- 调起 App：同 tab 导航 + 超时回落 ---------------- */

    let pending = null;      // 正在等待的调起：{ timer, cleanup }

    function clearPending() {
        if (!pending) return;
        clearTimeout(pending.timer);
        document.removeEventListener('visibilitychange', pending.onVis);
        window.removeEventListener('pagehide', pending.onHide);
        pending = null;
    }

    /**
     * 用 location.href 打开 scheme；若 APP_TIMEOUT 内页面仍可见，判定「没装 App」，
     * 回落到网页版。页面被切到后台（visibilitychange / pagehide）说明 App 起来了，
     * 立刻取消回落，避免用户从 App 返回时被莫名跳到网页版。
     */
    function launchApp(scheme, webFallback) {
        clearPending();
        const onVis = function () { if (document.hidden) clearPending(); };
        const onHide = function () { clearPending(); };
        const timer = setTimeout(function () {
            clearPending();
            if (!document.hidden) location.href = webFallback;
        }, APP_TIMEOUT);
        pending = { timer: timer, onVis: onVis, onHide: onHide };
        document.addEventListener('visibilitychange', onVis);
        window.addEventListener('pagehide', onHide);
        location.href = scheme;
    }

    function bindLink(a, getLink) {
        // 每次点击都重新问一次（定位状态可能已变），但只在同一个元素上挂一个监听
        a.addEventListener('click', function (ev) {
            const link = getLink();
            if (!link) return;
            if (!link.app) return;                    // 普通 https 链接，交给浏览器默认行为
            ev.preventDefault();
            launchApp(link.app, link.web);
        });
    }

    /** 详情卡底部链接的 DOM 接线。ids 默认对应四页共用的元素。
        返回 { update(v, me), hide() }——页面只负责把记录与定位喂进来。 */
    function mount(ids) {
        const o = Object.assign({ row: 'detail-links', nav: 'detail-nav', poi: 'detail-poi' }, ids || {});
        function el(k) {
            return document.getElementById(o[k]);
        }

        const a = el('nav');
        const b = el('poi');
        let cur = { nav: null, poi: null };

        function hide() {
            const row = el('row');
            // 用内联 display 而非切 class：Tailwind 的 .hidden 只是普通选择器，
            // 内联样式稳赢，且不依赖页面是否加载了 Tailwind。
            if (row) row.style.display = 'none';
        }

        if (a) bindLink(a, function () { return cur.nav; });
        if (b) bindLink(b, function () { return cur.poi; });

        function update(v, me) {
            const row = el('row');
            if (!row) return;
            if (!v || !v.coords) { hide(); return; }
            const L = bundle(v, me);
            cur = L;
            if (a && L.nav) {
                a.href = L.nav.app || L.nav.web;
                a.textContent = L.nav.label;
                a.title = L.nav.tip;
                a.dataset.kind = L.nav.kind + (L.nav.app ? '+app' : '');
            }
            if (b && L.poi) {
                b.href = L.poi.app || L.poi.web;
                b.textContent = L.poi.label;
                b.title = L.poi.tip;
                b.dataset.kind = L.poi.kind + (L.poi.app ? '+app' : '');
            }
            row.style.display = 'flex';
        }

        return { update: update, hide: hide };
    }

    return {
        SRC_WEB: SRC_WEB,
        canLaunchApp: canLaunchApp,
        isMobile: IS_MOBILE,
        isWechat: IS_WECHAT,
        isTouch: IS_TOUCH,
        nav: nav,
        poi: poi,
        bundle: bundle,
        mount: mount,
        launchApp: launchApp
    };
})();
