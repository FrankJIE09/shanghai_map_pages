/** Tailwind 静态构建配置。
 *
 *  这些页面原来用的是 `cdn.tailwindcss.com`（Play CDN）：浏览器里跑 JIT，
 *  先下载 ~100KB JS 再扫描 DOM 现场生成 CSS。手机上表现为「先裸排版、再突然
 *  跳成正常样式」，而且离线打开时整页样式直接失效。现在改成构建期用
 *  `scripts/build_css.sh` 生成一份静态 CSS（约 19KB）内联进产物，运行时零 JS。
 *
 *  ⚠️ 改页面时如果新增了 Tailwind 类名，必须重新跑 `./scripts/build_css.sh`，
 *     否则新类名不会出现在 src/static/tailwind.css 里（build.py 的
 *     --check 会逐类名核对产物，漏了会直接报错）。
 */
const path = require('path');

module.exports = {
  content: [
    path.join(__dirname, 'src/pages/*.html'),
    path.join(__dirname, 'src/static/*.js'),
  ],
  theme: { extend: {} },
  corePlugins: { preflight: true },
};
