#!/usr/bin/env python3
# 厦园新手村 · 搜索索引构建脚本
# 用法：python3 tools/build_search_index.py
# 读取 nav-data.js 里的栏目清单，抓取每个 pages/*.html 的标题、分段正文和链接文本，
# 生成 assets/search-index.js（window.XMU_SEARCH_INDEX）。
# 内容更新后重新运行本脚本即可刷新搜索结果；零第三方依赖。

import io
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAV_FILE = ROOT / "assets" / "nav-data.js"
OUT_FILE = ROOT / "assets" / "search-index.js"

HEADING_RE = re.compile(r"<h([1-4])\b([^>]*)>(.*?)</h\1>", re.S | re.I)
LINK_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
HREF_RE = re.compile(r"""(?:href)\s*=\s*["']([^"']+)["']""", re.I)


def strip_blocks(raw: str) -> str:
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    for tag in ("script", "style", "noscript", "template", "svg"):
        raw = re.sub(rf"<{tag}\b.*?</{tag}\s*>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<footer\b.*?</footer\s*>", " ", raw, flags=re.S | re.I)
    return raw


def to_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def attr(attrs: str, name: str):
    match = re.search(rf"""\b{name}\s*=\s*["']([^"']+)["']""", attrs or "", re.I)
    return match.group(1) if match else ""


def parse_nav_targets() -> dict:
    nav = io.open(NAV_FILE, "r", encoding="utf-8").read()
    targets = {}
    for item in re.finditer(r"\{([^{}]*?)\}", nav, re.S):
        block = item.group(1)
        id_match = re.search(r"""\bid:\s*['"]([^'"]+)['"]""", block)
        src_match = re.search(r"""src:\s*['"]([^'"]+?\.html)""", block)
        if id_match and src_match:
            targets[id_match.group(1)] = src_match.group(1).strip()
    return targets


def extract(file_path: Path):
    raw = io.open(file_path, "r", encoding="utf-8", errors="replace").read()
    raw = strip_blocks(raw)

    headings = []
    for match in HEADING_RE.finditer(raw):
        text = to_text(match.group(3))
        if not text:
            continue
        headings.append({
            "start": match.start(), "end": match.end(),
            "level": match.group(1), "id": attr(match.group(2), "id"), "text": text,
        })

    title = next((h["text"] for h in headings if h["level"] == "1"), file_path.stem)

    segments = []
    for index, heading in enumerate(headings):
        body_end = headings[index + 1]["start"] if index + 1 < len(headings) else len(raw)
        body = to_text(raw[heading["end"]:body_end])[:1400]
        segments.append({"heading": heading["text"], "text": body or heading["text"], "id": heading["id"] or "", "panelId": ""})

    # 链接文本作为独立分段：四六级报名这类入口靠它被搜到；锚点挂到最近一个带 id 的上级标题。
    seen_links = set()
    last_heading_with_id = {"start": -1, "id": ""}
    heading_cursor = 0
    current_heading_id = ""
    for match in LINK_RE.finditer(raw):
        while heading_cursor < len(headings) and headings[heading_cursor]["start"] < match.start():
            if headings[heading_cursor]["id"]:
                last_heading_with_id = {"start": headings[heading_cursor]["start"], "id": headings[heading_cursor]["id"]}
            heading_cursor += 1
        text = to_text(match.group(2))
        href = attr(match.group(1), "href")
        if len(text) < 2 or len(text) > 40 or not text or text in seen_links:
            continue
        if not href or href.startswith(("javascript:", "#")):
            continue
        seen_links.add(text)
        segments.append({"heading": text, "text": text, "id": last_heading_with_id["id"], "panelId": ""})
        if len(segments) >= 220:
            break

    body_text = to_text(raw)[:24000]
    return {"title": title, "segments": segments, "bodyText": body_text}


def main():
    targets = parse_nav_targets()
    if not targets:
        raise SystemExit("未能从 nav-data.js 解析出栏目清单")
    entries = []
    for target in sorted(targets, key=lambda t: int(t.replace("page", "") or 0)):
        file_path = ROOT / targets[target]
        if not file_path.exists():
            print(f"! 跳过缺失文件：{targets[target]}")
            continue
        data = extract(file_path)
        entries.append({"target": target, "file": targets[target], **data})
        print(f"· {target}  {targets[target]}  分段 {len(data['segments'])}  正文 {len(data['bodyText'])} 字")
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    OUT_FILE.write_text(
        "/* 由 tools/build_search_index.py 生成；内容更新后请重新运行该脚本。 */\n"
        f"window.XMU_SEARCH_INDEX = {payload};\n",
        encoding="utf-8",
    )
    print(f"√ 已生成 {OUT_FILE.relative_to(ROOT)}（{OUT_FILE.stat().st_size // 1024} KB，共 {len(entries)} 个栏目）")


if __name__ == "__main__":
    main()
