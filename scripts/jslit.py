#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位并求值 HTML 里的 JS 数据字面量。

偏移量一律由 Python 计算（按 Unicode 码点），**不要**用 Node 返回的偏移量：
Node 的字符串索引是 UTF-16 码元，遇到 emoji（如 🗂，代理对占 2 个码元）
就会与 Python 的码点位置错开，进而把文件改坏。
"""
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_EVAL = os.path.join(ROOT, "scripts", "js_eval_literal.js")

_ASSIGN = r'(?:^|\n)([ \t]*)(?:const|let|var)[ \t]+{name}[ \t]*=[ \t]*'


def find_literal(src, name):
    """定位 `const NAME = <字面量>`，返回 raw 文本与替换所需的三个偏移量。

    返回 dict：
      raw        字面量原文（含外层括号）
      stmt_start `const` 关键字起点
      end         字面量闭合括号之后（已吃掉尾随空白与分号）
      indent      该语句所在行的缩进
    """
    pattern = re.compile(_ASSIGN.format(name=re.escape(name)))
    matches = list(pattern.finditer(src))
    if not matches:
        raise LookupError("未找到字面量: " + name)
    if len(matches) > 1:
        raise LookupError("字面量 {} 出现 {} 次，无法确定替换目标".format(name, len(matches)))

    m = matches[0]
    indent = m.group(1) or ""
    stmt_start = m.start() + (1 if m.group(0)[0] == "\n" else 0) + len(indent)

    i = m.end()
    while i < len(src) and src[i].isspace():
        i += 1
    start = i
    if start >= len(src) or src[start] not in "[{":
        got = src[start:start + 20] if start < len(src) else "<EOF>"
        raise ValueError("{} 的字面量不是数组/对象，实际以 {!r} 开头".format(name, got))
    open_ch = src[start]
    close_ch = "]" if open_ch == "[" else "}"

    depth = 0
    quote = None        # 单/双引号字符串
    in_template = False  # 模板字符串
    in_line = False     # // 行注释
    in_block = False    # /* */ 块注释

    while i < len(src):
        c = src[i]
        n = src[i + 1] if i + 1 < len(src) else ""

        if in_line:
            if c == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            if c == "*" and n == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if in_template:
            if c == "\\":
                i += 2
                continue
            if c == "`":
                in_template = False
            i += 1
            continue

        if c == "/" and n == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and n == "*":
            in_block = True
            i += 2
            continue
        if c in ("'", '"'):
            quote = c
            i += 1
            continue
        if c == "`":
            in_template = True
            i += 1
            continue

        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                end = i + 1
                while end < len(src) and src[end].isspace():
                    end += 1
                if end < len(src) and src[end] == ";":
                    end += 1
                return {
                    "raw": src[start:i + 1],
                    "stmt_start": stmt_start,
                    "end": end,
                    "indent": indent,
                }
        i += 1

    raise ValueError(name + " 的字面量未闭合")


def eval_to_json(raw):
    """借 Node 把 JS 字面量求值成 Python 对象。"""
    proc = subprocess.run(
        ["node", JS_EVAL], input=raw, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ValueError((proc.stderr or proc.stdout).strip())
    return json.loads(proc.stdout)
