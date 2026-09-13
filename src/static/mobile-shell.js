/* 手机端外壳的行为层（样式在 src/static/mobile.css）。

   做四件事，四个地图页共用，页面只打 [data-m-*] 标记 + 调一次 init：
     1. 全屏地图 + 底部抽屉的开关（顶栏按钮 / ✕ / 再点一次收起）
     2. 返回键：抽屉打开时按返回是「收起抽屉」，而不是退出网页
     3. 深链：#v=<key> 直接打开某家店的详情，可分享、可收藏
     4. 分享：navigator.share（手机上有系统分享面板），不支持就复制链接

   只在窄屏（html.m-mobile）下接管抽屉与返回键；桌面端仍然可以用 #v= 深链与分享。
   与页面的唯一约定是 init({ select }) —— select(key) 是页面自己的「选中场所」函数。 */
window.MobileShell = (function () {
    'use strict';

    const MQ = '(max-width: 900px)';
    const root = document.documentElement;

    let mq = null;
    let select = null;          // 页面注入的 select(key)
    let pageTitle = '';         // 分享标题（页面标题）
    let currentKey = null;      // 当前选中的场所 key
    let openName = null;        // 当前打开的抽屉名
    let restoring = false;      // 由 popstate / 首次加载恢复选中时抑制再次入栈
    let toastEl = null;

    function isMobile() {
        return mq ? mq.matches : root.classList.contains('m-mobile');
    }

    /* ================= 抽屉 ================= */

    function sheetEl(name) {
        return name ? document.querySelector('[data-m-sheet="' + name + '"]') : null;
    }

    /** #detail-card 所在的那个抽屉叫什么 —— 页面自己不用管，从 DOM 反查。 */
    function detailSheet() {
        const card = document.getElementById('detail-card');
        const host = card && card.closest ? card.closest('[data-m-sheet]') : null;
        return host ? host.getAttribute('data-m-sheet') : null;
    }

    function apply(name) {
        openName = name || null;
        if (openName) root.setAttribute('data-m-open', openName);
        else root.removeAttribute('data-m-open');
        const btns = document.querySelectorAll('[data-m-open]');
        for (let i = 0; i < btns.length; i++) {
            btns[i].setAttribute('aria-pressed',
                String(btns[i].getAttribute('data-m-open') === openName));
        }
        // 抽屉开合会改变地图可视区域，让 Leaflet 重新测量（它自己监听 window resize）
        window.dispatchEvent(new Event('resize'));
    }

    /** 滚动抽屉内部到某个元素（不用 scrollIntoView：它会连带滚动祖先元素）。 */
    function scrollSheetTo(name, anchor) {
        const host = sheetEl(name);
        if (!host) return;
        if (!anchor) { host.scrollTop = 0; return; }
        const target = host.querySelector(anchor);
        if (!target) { host.scrollTop = 0; return; }
        const delta = target.getBoundingClientRect().top - host.getBoundingClientRect().top;
        host.scrollTop = Math.max(0, host.scrollTop + delta - 48);
    }

    function openSheet(name, anchor, pushHistory) {
        if (!isMobile() || !name || !sheetEl(name)) return;
        if (openName !== name) {
            apply(name);
            if (pushHistory !== false) {
                try { history.pushState({ mSheet: name }, '', location.href); } catch (e) { /* 忽略 */ }
            }
        }
        scrollSheetTo(name, anchor);
    }

    function closeSheet(useHistory) {
        if (!openName) return;
        if (useHistory !== false && history.state && history.state.mSheet) {
            history.back();     // 回到入栈前那一格，返回键与点 ✕ 走同一条路
            return;
        }
        apply(null);
    }

    /* ================= 选择与深链 ================= */

    function readHashKey() {
        const m = /[#&]v=([^&]*)/.exec(location.hash || '');
        if (!m) return null;
        try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
    }

    function writeHashKey(key) {
        if (!key) return;
        try {
            history.replaceState(history.state, '', '#v=' + encodeURIComponent(key));
        } catch (e) { /* 忽略：file:// 或某些内嵌浏览器会拒绝 */ }
    }

    /** 页面选中某家店时调用：更新深链；手机端顺带把详情抽屉推上来。 */
    function onSelect(key) {
        currentKey = key;
        writeHashKey(key);
        if (restoring || !isMobile()) return;
        const host = detailSheet();
        if (host) openSheet(host, '#detail-card', true);
    }

    /** 首次加载带 #v=<key> 时直接打开那家店（分享链接的落地动作）。 */
    function restoreFromHash() {
        const key = readHashKey();
        if (!key || !select) return;
        restoring = true;
        try { select(key); } catch (e) { restoring = false; return; }
        restoring = false;
        const host = detailSheet();
        if (host && isMobile()) openSheet(host, '#detail-card', true);
    }

    function onPop(e) {
        const st = e.state;
        apply(st && st.mSheet ? st.mSheet : null);
        // 前进/后退都可能把 hash 换掉：让详情内容跟上
        const key = readHashKey();
        if (key && key !== currentKey && select) {
            restoring = true;
            try { select(key); } catch (err) { /* 忽略 */ }
            restoring = false;
        }
    }

    /* ================= 分享 ================= */

    function toast(text, ms) {
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.className = 'm-toast';
            document.body.appendChild(toastEl);
        }
        toastEl.textContent = text;
        toastEl.classList.add('is-on');
        clearTimeout(toast._t);
        toast._t = setTimeout(function () { toastEl.classList.remove('is-on'); }, ms || 2200);
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(
                function () { toast('链接已复制'); },
                function () { toast(text, 6000); });
            return;
        }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        toast(ok ? '链接已复制' : text, ok ? 2200 : 6000);
    }

    /** 分享。带 key 时分享这家店，否则分享当前页面。 */
    function share(key) {
        const title = document.title || pageTitle;
        let text = title;
        if (key) {
            const el = document.getElementById('detail-title');
            const name = el ? String(el.textContent || '').trim() : '';
            if (name) text = name + ' · ' + title;
        }
        if (navigator.share) {
            navigator.share({ title: title, text: text, url: location.href })
                .catch(function () { /* 用户取消，不算错误 */ });
            return;
        }
        copyText(location.href);
    }

    /* ================= DOM 注入 ================= */

    /** 每个抽屉顶部补一条抓手 + 标题 + ✕（页面不需要为此写任何 HTML）。 */
    function injectSheetHeaders() {
        const sheets = document.querySelectorAll('[data-m-sheet]');
        for (let i = 0; i < sheets.length; i++) {
            const host = sheets[i];
            if (host.querySelector(':scope > .m-sheet-top')) continue;
            const name = host.getAttribute('data-m-title') || '详情';
            const top = document.createElement('div');
            top.className = 'm-sheet-top';
            top.innerHTML = '<div class="m-sheet-grip"></div>' +
                '<div class="m-sheet-head">' +
                '<span class="m-sheet-name">' + name + '</span>' +
                '<button type="button" class="m-sheet-x" data-m-close aria-label="收起">✕</button>' +
                '</div>';
            host.insertBefore(top, host.firstChild);
        }
    }

    /** 详情卡底部补一个「分享」按钮（和导航 / 店铺页并排，桌面端也有）。 */
    function injectShare() {
        const row = document.getElementById('detail-links');
        if (row && !document.getElementById('detail-share')) {
            const b = document.createElement('a');
            b.id = 'detail-share';
            b.href = '#';
            b.textContent = '🔗 分享这家店';
            b.addEventListener('click', function (ev) {
                ev.preventDefault();
                share(currentKey);
            });
            row.appendChild(b);
        }
        // 顶栏上的 🔗（id 由页面给，没有就不接）
        const bar = document.getElementById('m-btn-share');
        if (bar && !bar.dataset.wired) {
            bar.dataset.wired = '1';
            bar.addEventListener('click', function (ev) {
                ev.preventDefault();
                share(currentKey);
            });
        }
    }

    /* ================= 接线 ================= */

    function onDocClick(e) {
        const opener = e.target.closest ? e.target.closest('[data-m-open]') : null;
        if (opener) {
            e.preventDefault();
            const name = opener.getAttribute('data-m-open');
            const anchor = opener.getAttribute('data-m-scroll');
            if (openName === name) closeSheet(true);         // 再点一次收起
            else openSheet(name, anchor, true);
            return;
        }
        const closer = e.target.closest ? e.target.closest('[data-m-close]') : null;
        if (closer) {
            e.preventDefault();
            closeSheet(true);
        }
    }

    function onMqChange() {
        root.classList.toggle('m-mobile', !!(mq && mq.matches));
        if (!mq || !mq.matches) apply(null);            // 回到桌面宽度：收起抽屉
        else window.dispatchEvent(new Event('resize'));
    }

    /* 脚本一解析就跑：把标记、按钮、返回键接好，不等 window.onload。
       （抽屉标题要在首屏就存在，否则手机上会看到抽屉没有抓手。） */
    (function boot() {
        mq = window.matchMedia ? window.matchMedia(MQ) : null;
        if (mq) {
            root.classList.toggle('m-mobile', mq.matches);
            if (mq.addEventListener) mq.addEventListener('change', onMqChange);
            else if (mq.addListener) mq.addListener(onMqChange);       // 老 Safari
        }
        injectSheetHeaders();
        injectShare();
        window.addEventListener('popstate', onPop);
        document.addEventListener('click', onDocClick);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeSheet(false);      // 桌面端 Esc 收起抽屉
        });
    })();

    return {
        isMobile: isMobile,
        /** 页面在 window.onload 末尾调用：select(key) 是页面自己的「选中场所」。 */
        init: function (opts) {
            opts = opts || {};
            select = opts.select || null;
            pageTitle = opts.title || document.title || '';
            injectShare();
            restoreFromHash();
        },
        onSelect: onSelect,
        open: function (name, anchor) { openSheet(name, anchor, true); },
        close: function () { closeSheet(true); },
        share: share,
        toast: toast
    };
})();
