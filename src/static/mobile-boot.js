/* 首屏渲染前就把「手机端」标记打到 <html> 上。
   必须在 <head> 里同步执行：等 body 末尾的脚本再打，手机上会先闪一下桌面版布局
   （长页面 + 需要往下滚才见到地图），再跳成全屏地图。

   两个标记分开加，因为它们的适用条件不一样：
     m-mobile  窄屏：启用全屏地图 + 底部抽屉外壳（src/static/mobile.css）
     m-touch   粗指针（手机/平板，含横向的 iPad）：只做触控尺寸修正，不改布局 */
(function () {
    'use strict';
    var matchMedia = window.matchMedia;
    if (!matchMedia) return;
    var root = document.documentElement;
    if (matchMedia('(max-width: 900px)').matches) root.classList.add('m-mobile');
    if (matchMedia('(pointer: coarse)').matches) root.classList.add('m-touch');
})();
