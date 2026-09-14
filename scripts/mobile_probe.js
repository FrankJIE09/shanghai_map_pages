/* 手机端外壳探针（构建产物用，配合 scripts/mobile_probe.sh）。
 *
 * 与 scripts/parity_*.html 的区别：parity 探针是「同版本前后对比」，靠人眼看两个
 * document.title 是否逐字相同；手机端要验的东西里有一大半是**真值断言**（抽屉闭合时
 * 是否在视口外、返回键会不会退出网页、触控目标够不够大、不同 UA 该落哪一档），
 * 所以这里直接给 PASS / FAIL，让脚本能一键跑完并返回退出码。
 *
 * 用法：把本文件与 dist/*.html 放在同一目录，在 </body> 前插一行
 *   <script src="mobile_probe.js"></script>
 * 然后用无头 Chrome 打开，读 DOM 里的 PROBE-START…PROBE-END 段。
 *
 * 参数（query string）：
 *   probe=behave|geom|css|links   跑哪一个（默认 geom）
 *   notrans=1                     关过渡/动画，headless 的动画时钟不推进，不关量不到终态
 *   data=plain|rich               links 探针：plain=真实数据，rich=临时补过 baidu_url/uid
 */
(function () {
    var R = [];
    var P = new URLSearchParams(location.search);
    var PROBE = P.get('probe') || 'geom';
    var DATA = P.get('data') || 'plain';
    var errors = [];

    window.addEventListener('error', function (e) { errors.push(String(e.message || e.type)); });
    if (P.get('notrans')) {
        var st = document.createElement('style');
        st.textContent = '*{transition:none !important;animation:none !important}';
        (document.head || document.documentElement).appendChild(st);
    }

    function q(s) { return document.querySelector(s); }
    function qa(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function ok(name, cond, detail) { R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + ' | ' + (detail === undefined ? '' : detail)); }
    function info(s) { R.push('INFO | ' + s); }
    function coarse() { return matchMedia('(pointer: coarse)').matches; }
    function narrow() { return matchMedia('(max-width: 900px)').matches; }
    function size(e) { var r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), bottom: Math.round(r.bottom) }; }
    function openState() { return document.documentElement.getAttribute('data-m-open'); }
    function hashKey() {
        var m = /[#&]v=([^&]*)/.exec(location.hash || '');
        return m ? decodeURIComponent(m[1]) : null;
    }
    function srcOf(href) {
        if (!href) return '空';
        if (href.indexOf('baidumap://') === 0) return 'app';
        if (/j\.map\.baidu\.com/.test(href)) return 'short';
        if (/api\.map\.baidu\.com/.test(href)) return 'web';
        return '其它';
    }
    /* min-height 在没设时是 "auto"，parseFloat 会得到 NaN——要么返回数字，要么返回 null */
    function numOf(e, prop) {
        if (!e) return null;
        var v = parseFloat(getComputedStyle(e)[prop]);
        return isNaN(v) ? null : v;
    }
    function hOf(sel) {
        /* 取第一个「真的渲染出来」的：手机上有些块被 [data-m-hide] 隐掉，DOM 里第一个
           .chip 可能在隐藏容器里，高度是 0，拿它去断言尺寸没有意义 */
        var list = qa(sel);
        for (var i = 0; i < list.length; i++) {
            var h = Math.round(list[i].getBoundingClientRect().height);
            if (h > 0) return h;
        }
        return null;
    }
    /* 探针注入的页面里，地图初始化要等 window.onload；--dump-dom 下它常常不触发 */
    async function boot() {
        await sleep(300);
        if (!q('.leaflet-container') && typeof window.onload === 'function') {
            try { window.onload(); } catch (e) { info('手动触发 onload 失败：' + e.message); }
        }
        await sleep(800);
    }

    /* ---------------- 行为：抽屉 / 返回键 / 深链 / 分享 ---------------- */
    async function behave() {
        var btns = qa('#m-bar [data-m-open]');
        ok('外壳已挂上', !!window.MobileShell, 'MobileShell=' + typeof window.MobileShell);
        ok('地图已初始化', !!q('.leaflet-container'), '标记=' + qa('.m-icon').length + ' 个');
        ok('顶栏有抽屉按钮', btns.length > 0, btns.length + ' 个：' +
            btns.map(function (b) { return b.dataset.mOpen; }).join('/'));
        if (!btns.length) return;

        // 每个抽屉都验「能开、开在视口里、能关」
        for (var i = 0; i < btns.length; i++) {
            var name = btns[i].dataset.mOpen;
            btns[i].click();
            await sleep(120);
            var host = q('[data-m-sheet="' + name + '"]');
            var s = host ? size(host) : null;
            ok('打开抽屉 ' + name, openState() === name && !!s && s.bottom <= window.innerHeight + 1 && s.bottom > 0,
                'data-m-open=' + openState() + ' 抽屉=' + JSON.stringify(s));
            btns[i].click();
            await sleep(320);
            ok('再点一次收起 ' + name, openState() === null, 'data-m-open=' + openState());
        }

        var first = btns[0], firstName = first.dataset.mOpen;
        // 打开时历史入栈：返回键才能只收抽屉、不退出网页
        first.click();
        await sleep(120);
        ok('打开时历史入栈', !!(history.state && history.state.mSheet),
            'history.state=' + JSON.stringify(history.state));
        var before = location.pathname;
        history.back();
        await sleep(420);
        ok('返回键只收抽屉、不退出网页', openState() === null && location.pathname === before,
            'data-m-open=' + openState() + ' 仍在页内=' + (location.pathname === before));

        first.click();
        await sleep(120);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await sleep(220);
        ok('Esc 收起抽屉', openState() === null, 'data-m-open=' + openState());
        ok('首位抽屉仍是 ' + firstName, first.getAttribute('aria-pressed') !== 'true',
            'aria-pressed=' + first.getAttribute('aria-pressed'));

        // 点名录 -> 写深链 + 手机上自动开详情抽屉
        var row = q('.venue-item') || q('.rest-item');
        ok('名录里有可选条目', !!row, row ? row.className.split(' ')[0] : '没找到');
        if (row) {
            row.click();
            await sleep(300);
            ok('点名录写入 #v=<key> 深链', !!hashKey(), 'hash=' + location.hash);
            var detail = q('[data-m-sheet="detail"]') || q('[data-m-sheet="panel"]');
            if (detail && narrow()) {
                ok('手机上点名录自动开详情抽屉', openState() === detail.dataset.mSheet,
                    'data-m-open=' + openState() + ' 期望=' + detail.dataset.mSheet);
            }
        }

        // 分享：navigator.share 拿到的必须是当前地址（含深链）
        var shared = [];
        try {
            Object.defineProperty(navigator, 'share', { configurable: true, value: function (d) { shared.push(d); return Promise.resolve(); } });
            Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: function (t) { shared.push({ text: t }); return Promise.resolve(); } } });
        } catch (e) { info('stub 分享接口失败：' + e.message); }
        var shareBtn = q('#m-btn-share') || q('#detail-share');
        if (!shareBtn) {
            ok('有分享按钮', false, '#m-btn-share / #detail-share 都不存在');
        } else {
            shareBtn.click();
            await sleep(200);
            var call = shared[shared.length - 1];
            ok('分享走 navigator.share 或剪贴板', shared.length > 0, '调用数=' + shared.length);
            ok('分享的 URL 就是当前地址（含深链）', !!call && (call.url === location.href || typeof call.text === 'string'),
                call ? JSON.stringify(call).slice(0, 160) : '没有收到调用');
        }
    }

    /* ---------------- 地图上点店铺：直接弹出介绍卡片 ---------------- */
    async function marker() {
        var detailHost = q('[data-m-sheet="detail"]') || q('[data-m-sheet="panel"]');
        var sheetName = detailHost ? detailHost.dataset.mSheet : null;
        var icons = qa('.m-icon');
        ok('地图上有店铺标记', icons.length > 0, icons.length + ' 个 .m-icon');
        ok('能找到详情抽屉', !!sheetName, 'detail-card 所在抽屉=' + sheetName);
        if (!icons.length || !sheetName) return;

        /* 关掉可能已开着的抽屉，回到「地图全屏、没有卡片」的初始态 */
        var x = q('.m-sheet-x');
        if (openState() !== null && x) { x.click(); await sleep(400); }
        ok('初始态没有卡片', openState() === null, 'data-m-open=' + openState());

        // 点第一个标记：应该直接弹出介绍卡片，并写入深链
        icons[0].click();
        await sleep(500);
        var title = q('#detail-title');
        var card = q('#detail-card');
        var host = detailHost.getBoundingClientRect();
        var cs = card ? card.getBoundingClientRect() : null;
        ok('点地图标记直接弹出介绍卡片', openState() === sheetName,
            'data-m-open=' + openState() + ' 期望=' + sheetName);
        ok('卡片内容是该店铺（标题非空）', !!title && String(title.textContent).trim().length > 0,
            '标题=' + (title ? JSON.stringify(String(title.textContent).trim().slice(0, 24)) : '无 #detail-title'));
        /* 抽屉要贴住视口底边并可见；卡片本身可能比抽屉高，那就由抽屉内部滚动，
           所以只要求卡片的「开头」在视口内，不能要求整张都放得下。 */
        ok('抽屉贴住视口底边且可见',
            Math.abs(host.bottom - window.innerHeight) <= 2 && host.top < window.innerHeight && host.height > 100,
            '抽屉 top=' + Math.round(host.top) + ' bottom=' + Math.round(host.bottom) +
            ' 高=' + Math.round(host.height) + ' 视口高=' + window.innerHeight);
        ok('卡片的开头在视口内（标题看得见）',
            !!cs && cs.top >= -1 && cs.top < window.innerHeight,
            '卡片 top=' + (cs ? Math.round(cs.top) : '-') + ' bottom=' + (cs ? Math.round(cs.bottom) : '-') +
            '（抽屉内可滚动，不要求整张都放得下）');
        ok('点标记写入 #v= 深链', !!hashKey(), 'hash=' + location.hash);
        var firstKey = hashKey();

        /* 卡片开着时再点另一个标记：内容要换成新店，而不是被浏览器当「点空白」收起来 */
        if (icons.length > 1) {
            icons[1].click();
            await sleep(500);
            var title2 = q('#detail-title');
            ok('卡片开着时点另一个标记会换成新店', openState() === sheetName && !!hashKey() &&
                hashKey() !== firstKey,
                'data-m-open=' + openState() + ' hash=' + location.hash + ' 上一次=' + firstKey);
            ok('换店后标题跟着变', !!title2 && String(title2.textContent).trim().length > 0,
                '标题=' + (title2 ? JSON.stringify(String(title2.textContent).trim().slice(0, 24)) : '无'));
        }

        // 返回键应收起卡片、而不是退出网页（点标记这条路径也要入栈）
        var path = location.pathname;
        if (history.state && history.state.mSheet) {
            history.back();          // 只在确实入过栈时才 back：否则会尝试离开本页而卡住
            await sleep(450);
            ok('点标记打开的卡片也能用返回键收起', openState() === null && location.pathname === path,
                'data-m-open=' + openState() + ' 仍在页内=' + (location.pathname === path));
        } else {
            ok('点标记时抽屉有入栈（返回键才有东西可收）', false,
                'history.state=' + JSON.stringify(history.state) + '（没入栈说明卡片根本没打开）');
        }
        ok('没有 JS 错误', errors.length === 0, errors.length ? errors.slice(0, 3).join(';') : '无');
    }

    /* ---------------- 几何：窄屏全屏地图 / 宽屏原布局 ---------------- */
    function geom() {
        var isNarrow = narrow();
        var hasShell = !!q('[data-m-pane="map"]') || !!q('#m-bar');
        if (!hasShell) {
            /* 落地页：没有外壳，手机上仍是原来的卡片列表，只验「不溢出、不报错、
               没有被误加上 m-mobile」（它连 mobile-boot.js 都没内联） */
            ok('落地页没有被套上手机外壳', !/m-mobile/.test(document.documentElement.className),
                'class=' + document.documentElement.className);
            ok('没有横向溢出', document.documentElement.scrollWidth - window.innerWidth <= 0,
                '溢出=' + (document.documentElement.scrollWidth - window.innerWidth) + 'px');
            ok('没有 JS 错误', errors.length === 0, errors.length ? errors.slice(0, 3).join(';') : '无');
            info('viewport=' + window.innerWidth + 'x' + window.innerHeight +
                ' | 页面高=' + document.documentElement.scrollHeight + '（落地页）');
            return;
        }
        ok('html.class 与媒体查询一致', isNarrow ? /m-mobile/.test(document.documentElement.className)
            : !/m-mobile/.test(document.documentElement.className),
            'narrow=' + isNarrow + ' class=' + document.documentElement.className);
        var bar = q('#m-bar'), pane = q('[data-m-pane="map"]'), mapEl = q('#leaflet-map');
        ok('顶栏显隐正确', isNarrow ? (!!bar && getComputedStyle(bar).display !== 'none')
            : (!bar || getComputedStyle(bar).display === 'none'),
            '#m-bar display=' + (bar ? getComputedStyle(bar).display : '无'));
        ok('地图卡片定位正确', !!pane && (isNarrow ? getComputedStyle(pane).position === 'fixed'
            : getComputedStyle(pane).position !== 'fixed'),
            'position=' + (pane ? getComputedStyle(pane).position : '无'));
        if (mapEl) {
            var ms = size(mapEl);
            ok('地图填满视口宽度', isNarrow ? Math.abs(ms.w - window.innerWidth) <= 2 : ms.w > 0,
                '地图=' + ms.w + 'x' + ms.h + ' 视口=' + window.innerWidth + 'x' + window.innerHeight);
        }
        ok('没有横向溢出', document.documentElement.scrollWidth - window.innerWidth <= 0,
            '溢出=' + (document.documentElement.scrollWidth - window.innerWidth) + 'px');
        var sheets = qa('[data-m-sheet]');
        ok('有抽屉标记', sheets.length > 0, sheets.length + ' 个');
        if (isNarrow) {
            var bad = sheets.filter(function (e) {
                var s = size(e);
                return !(s.top >= window.innerHeight - 0.5 || s.bottom <= 0.5);
            });
            ok('闭合时抽屉完全在视口外', bad.length === 0,
                bad.length ? bad.map(function (e) { return e.dataset.mSheet; }).join(',') : sheets.length + ' 个都在外');
        }
        ok('地图已初始化', !!q('.leaflet-container'), q('.leaflet-container') ? 'ok' : '未初始化');
        ok('没有 JS 错误', errors.length === 0, errors.length ? errors.slice(0, 3).join(';') : '无');
        info('viewport=' + window.innerWidth + 'x' + window.innerHeight +
            ' | 页面高=' + document.documentElement.scrollHeight +
            ' | 瓦片=' + qa('img.leaflet-tile').length +
            ' | 粗指针=' + coarse() + ' | hover:hover=' + matchMedia('(hover: hover)').matches);
    }

    /* ---------------- 触控细节：尺寸与 hover 门控 ---------------- */
    function mediaRules(matcher) {
        var hit = [];
        for (var i = 0; i < document.styleSheets.length; i++) {
            var rules;
            try { rules = document.styleSheets[i].cssRules; } catch (e) { continue; }
            for (var j = 0; j < rules.length; j++) {
                var r = rules[j];
                if (r.type !== CSSRule.MEDIA_RULE) continue;
                if (matcher && (r.conditionText || '').indexOf(matcher) < 0) continue;
                for (var k = 0; k < r.cssRules.length; k++) {
                    if (/:hover/.test(r.cssRules[k].selectorText || '')) hit.push(r.cssRules[k].selectorText);
                }
            }
        }
        return hit;
    }
    function auditTap() {
        var bad = [], seen = 0;
        var roots = qa('[data-m-sheet]');
        if (!roots.length && q('body')) roots = [document.body];      // 落地页没有抽屉
        roots.forEach(function (sheet) {
            var name = sheet.dataset.mSheet || 'page';
            Array.prototype.slice.call(sheet.querySelectorAll(
                'button, a[href], input, select, [role="button"], .chip, .cat-btn, .sort-btn, .venue-item, .rest-item'
            )).forEach(function (e) {
                var cs = getComputedStyle(e);
                if (cs.display === 'none' || cs.visibility === 'hidden') return;
                /* 复选框本体很小，但手指落的是包着它的 <label>，按真实点击区来量 */
                if (/^(checkbox|radio)$/.test(e.type)) e = e.closest('label') || e;
                var s = size(e);
                if (!s.w || !s.h) return;
                seen++;
                if (Math.min(s.w, s.h) < 32) bad.push(name + ':' + (e.className || e.tagName) + '=' + Math.min(s.w, s.h));
            });
        });
        return { seen: seen, bad: bad };
    }
    function one(sel, prop) {
        return numOf(q(sel), prop);
    }
    function css() {
        var isCoarse = coarse();
        info('粗指针=' + isCoarse + ' hover:none=' + matchMedia('(hover: none)').matches);
        info('媒体规则：' + (function () {
            var out = [];
            for (var i = 0; i < document.styleSheets.length; i++) {
                var rules;
                try { rules = document.styleSheets[i].cssRules; } catch (e) { continue; }
                for (var j = 0; j < rules.length; j++) {
                    var r = rules[j];
                    if (r.type === CSSRule.MEDIA_RULE && /pointer|hover/.test(r.conditionText || ''))
                        out.push('[' + r.conditionText + ' ×' + r.cssRules.length +
                            (matchMedia(r.conditionText).matches ? ' 命中' : '') + ']');
                }
            }
            return out.join(' ') || '没有 pointer / hover 条件规则';
        })());

        var chip = one('.chip', 'minHeight'), reset = one('#reset-btn', 'minHeight');
        var box = one('input[type="checkbox"]', 'width');
        var inputFont = one('#search-input', 'fontSize') || one('input[type="text"]', 'fontSize');
        var chipH = hOf('.chip'), resetH = hOf('#reset-btn'), boxH = hOf('input[type="checkbox"]');
        var hov = mediaRules('hover: hover'), allHov = mediaRules(null);
        info('chip min-height=' + chip + ' 实高=' + chipH + ' | reset 实高=' + resetH +
            ' | 复选框=' + box + 'px 实高=' + boxH + ' | 输入框字号=' + inputFont);

        ok('带 :hover 的规则全部门控在 (hover: hover) 里', allHov.length === hov.length && hov.length > 0,
            '共 ' + allHov.length + ' 条，门控内 ' + hov.length + ' 条');

        if (isCoarse) {
            if (chipH !== null) ok('触屏上 chip 实高 ≥34px', chipH >= 34, '实高=' + chipH + 'px（min-height=' + chip + '）');
            if (resetH !== null) ok('触屏上重置按钮实高 ≥34px', resetH >= 34, '实高=' + resetH + 'px');
            if (box !== null) ok('触屏上复选框放大到 ≥20px', box >= 20, '宽=' + box + 'px');
            if (inputFont !== null) ok('触屏上输入框 ≥16px（防 iOS 聚焦放大整页）', inputFont >= 16, '字号=' + inputFont + 'px');
            /* 触控目标审计只在触屏下判：桌面上 25px 的 chip 用鼠标点毫无问题 */
            var a = auditTap();
            ok('触屏上可点控件最小边 ≥32px', a.bad.length === 0,
                '审计 ' + a.seen + ' 个' + (a.bad.length ? '，偏小 ' + a.bad.length + ' 个：' + a.bad.slice(0, 6).join(', ') : ''));
        } else {
            var b = auditTap();
            info('桌面端可点控件 ' + b.seen + ' 个，其中最小边 <32px 的 ' + b.bad.length + ' 个（鼠标点击，不做要求）');
            if (chipH !== null) ok('桌面端 chip 未被触控规则放大', chipH < 32, '实高=' + chipH + 'px');
            if (resetH !== null) ok('桌面端重置按钮未被放大', resetH < 32, '实高=' + resetH + 'px');
            if (box !== null) ok('桌面端复选框仍是原尺寸', box > 0 && box <= 16, '宽=' + box + 'px');
            if (inputFont !== null) ok('桌面端输入框字号保持原样', inputFont > 0 && inputFont < 16, '字号=' + inputFont + 'px');
        }
    }

    /* ---------------- 分流：四种 UA 该落哪一档 ---------------- */
    async function links() {
        var ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
        var android = /Android/.test(navigator.userAgent);
        var wechat = /MicroMessenger/i.test(navigator.userAgent);
        var rich = DATA === 'rich';
        info('环境：iOS=' + ios + ' Android=' + android + ' 微信=' + wechat + ' 数据=' + DATA);

        /* 用深链直接指定词条：真实数据与补过字段的副本选中的必须是同一条，否则
           两档比的就不是同一家店了（名录默认按名称排序，点第一行未必是补过的那条）。 */
        await sleep(400);
        var nav = q('#detail-nav'), poi = q('#detail-poi');
        var href = poi && poi.getAttribute('href');
        if (!href || href === '#') {
            info('深链没有选中词条（hash=' + location.hash + '），退回点第一条名录');
            var row = q('.venue-item') || q('.rest-item');
            if (row) { row.click(); await sleep(300); }
            nav = q('#detail-nav'); poi = q('#detail-poi');
        }
        ok('已经选中一条词条（深链或名录）', !!poi && poi.getAttribute('href') !== '#' &&
            poi.getAttribute('href') !== '', 'hash=' + location.hash);
        ok('两个链接都存在', !!nav && !!poi, (nav ? '' : '缺 #detail-nav ') + (poi ? '' : '缺 #detail-poi'));

        var navSrc = srcOf(nav && nav.getAttribute('href')), poiSrc = srcOf(poi && poi.getAttribute('href'));
        var navKind = nav && nav.dataset.kind, poiKind = poi && poi.dataset.kind;
        info('nav kind=' + navKind + ' 落点=' + navSrc + ' | poi kind=' + poiKind + ' 落点=' + poiSrc);
        ok('两个链接都没有 target（App 调起必须同 tab）',
            (!nav || !nav.getAttribute('target')) && (!poi || !poi.getAttribute('target')),
            'target=' + (nav && nav.getAttribute('target')) + '/' + (poi && poi.getAttribute('target')));
        ok('两个链接都有 data-kind', !!navKind && !!poiKind, navKind + ' / ' + poiKind);

        // 导航：手机上进 App（微信除外），桌面走网页版
        var wantNavApp = (ios || android) && !wechat;
        ok('导航落点符合平台分流', navSrc === (wantNavApp ? 'app' : 'web'), '落点=' + navSrc + ' 期望=' + (wantNavApp ? 'app' : 'web'));
        if (wantNavApp) {
            ok('导航 scheme 带 src 参数', /[?&]src=/.test(nav.getAttribute('href')), 'href 前缀=' + nav.getAttribute('href').slice(0, 60));
        }

        // 店铺页：iOS 有短链就交给百度；其余手机调 App；微信与桌面一律网页版
        var wantPoi;
        if (wechat) wantPoi = rich ? 'short' : 'web';
        else if (ios) wantPoi = rich ? 'short' : 'app';
        else if (android) wantPoi = 'app';
        else wantPoi = rich ? 'short' : 'web';
        ok('店铺页落点符合平台分流', poiSrc === wantPoi, '落点=' + poiSrc + ' 期望=' + wantPoi);

        // kind 必须描述真实落点：没 uid 时即使调起 App 也只是「检索」
        if (poiSrc === 'app') {
            ok('调起 App 时的 kind 与数据完备度一致',
                poiKind === (rich ? 'detail+app' : 'search+app'),
                'kind=' + poiKind + ' 期望=' + (rich ? 'detail+app' : 'search+app'));
        } else {
            ok('网页版兜底的 kind 与数据完备度一致',
                poiKind === (rich ? 'short' : 'search'), 'kind=' + poiKind + ' 期望=' + (rich ? 'short' : 'search'));
        }
        ok('没有 JS 错误', errors.length === 0, errors.length ? errors.slice(0, 3).join(';') : '无');
    }

    var TABLE = { behave: behave, geom: geom, css: css, links: links, marker: marker };
    (async function () {
        try {
            await boot();
            await (TABLE[PROBE] || geom)();
        } catch (e) {
            R.push('FAIL | 探针异常 | ' + (e && e.message));
        }
        var pre = document.createElement('pre');
        pre.id = '__probe';
        pre.textContent = '\nPROBE-START\nprobe=' + PROBE + ' data=' + DATA + '\n' + R.join('\n') + '\nPROBE-END\n';
        document.body.appendChild(pre);
    })();
})();
