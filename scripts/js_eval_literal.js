/**
 * 把 stdin 上的一个 JS 表达式求值后，以 JSON 写到 stdout。
 *
 * 只用来把本仓库自带的数据字面量转成 JSON（不是通用沙箱，勿用于不可信输入）。
 * 之所以借 JS 引擎而不是手写解析，是因为数据里有注释、单引号、无引号键等
 * JSON 不接受的写法。
 *
 * 用法：
 *   echo "[{a:1}]" | node scripts/js_eval_literal.js
 */
'use strict';

let src = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { src += chunk; });
process.stdin.on('end', () => {
  try {
    const value = new Function('return (' + src + ');')();
    process.stdout.write(JSON.stringify(value));
  } catch (e) {
    process.stderr.write('JS 求值失败: ' + e.message + '\n');
    process.exit(1);
  }
});
