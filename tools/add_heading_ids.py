#!/usr/bin/env python3
# 厦园新手村 · 小节锚点补齐脚本
# 用法：python3 tools/add_heading_ids.py
# 为 pages/*.html 中没有 id 的 <h1>-<h4> 标题生成稳定锚点 id（h- + 文本哈希），
# 已有 id 的标题保持不变；重复运行幂等。补齐后请重新运行 tools/build_search_index.py。

import html
import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "pages"
HEADING_RE = re.compile(r"<h([1-4])([^>]*)>(.*?)</h\1>", re.S | re.I)


def fnv1a32(text: str) -> str:
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return format(value, "x")


def to_text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def main():
    total_new = 0
    for file_path in sorted(PAGES_DIR.glob("*.html")):
        raw = io.open(file_path, "r", encoding="utf-8").read()
        used_ids = {m.group(1) for m in re.finditer(r"""\bid\s*=\s*["']([^"']+)["']""", raw)}
        added = 0

        def repl(match):
            nonlocal added
            level, attrs, inner = match.group(1), match.group(2), match.group(3)
            if re.search(r"""\bid\s*=\s*["']""", attrs, re.I):
                return match.group(0)
            text = to_text(inner)
            if not text:
                return match.group(0)
            base = "h-" + fnv1a32(f"{text}|{level}")
            new_id = base
            serial = 2
            while new_id in used_ids:
                new_id = f"{base}-{serial}"
                serial += 1
            used_ids.add(new_id)
            added += 1
            return f"<h{level} id=\"{new_id}\"{attrs}>{inner}</h{level}>"

        new_raw = HEADING_RE.sub(repl, raw)
        if added:
            io.open(file_path, "w", encoding="utf-8").write(new_raw)
            total_new += added
        print(f"· {file_path.name}  新增锚点 {added}")
    print(f"√ 完成，共新增 {total_new} 个小节锚点")


if __name__ == "__main__":
    main()
