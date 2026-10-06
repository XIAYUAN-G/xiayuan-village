#!/usr/bin/env python3
"""厦园新手村静态站点与硅基流动知识问答服务。仅使用 Python 标准库。"""

from __future__ import annotations

import html
import json
import os
import re
import base64
import binascii
import getpass
import hashlib
import mimetypes
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import defaultdict, deque
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit


SITE_ROOT = Path(__file__).resolve().parent
HOME_PAGE = "厦园新手村·一站式导航.html"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
DEFAULT_MODEL = "Qwen/Qwen3-8B"
AI_REQUEST_ATTEMPTS = 3

# 资料存放区配置。默认使用本地 data/materials，部署到腾讯云时可切换为 COS。
MATERIAL_DATA_ROOT = Path(os.getenv("MATERIAL_DATA_ROOT", str(SITE_ROOT / "data"))).resolve()
MATERIALS_DIR = (MATERIAL_DATA_ROOT / "materials").resolve()
MATERIAL_DB_PATH = Path(os.getenv("MATERIAL_DB_PATH", str(MATERIAL_DATA_ROOT / "materials.sqlite3"))).resolve()
MATERIAL_STORAGE = os.getenv("MATERIAL_STORAGE", "local").strip().lower()
MATERIAL_MAX_BYTES = max(1, int(os.getenv("MATERIAL_MAX_BYTES", str(50 * 1024 * 1024))))
MATERIAL_ALLOWED_EXTENSIONS = {
    item.strip().lower()
    for item in os.getenv(
        "MATERIAL_ALLOWED_EXTENSIONS",
        ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.rar,.7z,.txt,.md,.csv,.jpg,.jpeg,.png,.webp",
    ).split(",")
    if item.strip()
}

# 本地预览默认管理员；正式部署时建议通过 /etc/xiayuan.env 覆盖这两项。
ADMIN_USERNAME = os.getenv("MATERIAL_ADMIN_USERNAME", "Saturday").strip()
ADMIN_PASSWORD = os.getenv("MATERIAL_ADMIN_PASSWORD", "").strip()
ADMIN_PASSWORD_HASH = os.getenv(
    "MATERIAL_ADMIN_PASSWORD_HASH",
    "pbkdf2$sha256$310000$zZy_wZY1Bqm3K95lrjGH3w$9tdd1lCJgIsT85W7B7iwPDPRS4jDdgnN3mTQY_5Bx9Q",
).strip()
ADMIN_SESSION_TTL = max(300, int(os.getenv("MATERIAL_ADMIN_SESSION_TTL", str(12 * 60 * 60))))
ADMIN_SESSIONS: dict[str, float] = {}
ADMIN_LOGIN_LOG: dict[str, deque] = defaultdict(deque)

COS_BUCKET = os.getenv("COS_BUCKET", "").strip()
COS_REGION = os.getenv("COS_REGION", "").strip()
COS_SECRET_ID = os.getenv("COS_SECRET_ID", "").strip()
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "").strip()
COS_SESSION_TOKEN = os.getenv("COS_SESSION_TOKEN", "").strip()
_COS_CLIENT = None
_COS_IMPORT_ERROR = None

# ---------------------------------------------------------------------------
# 厦大教务系统课表同步：统一身份认证（CAS）登录 + 我的课表页面解析。
# 仅在内存中完成登录，学号密码不落盘、不写日志；纯标准库实现 AES-CBC 加密。
# ---------------------------------------------------------------------------
CAS_LOGIN_URL = "https://ids.xmu.edu.cn/authserver/login"
CAS_SERVICE_URL = "https://jw.xmu.edu.cn/new/index.html"
CAS_NEED_CAPTCHA_URL = "https://ids.xmu.edu.cn/authserver/checkNeedCaptcha.htl"
CAS_CAPTCHA_URL = "https://ids.xmu.edu.cn/authserver/getCaptcha.htl"
# 金智 EMAP 平台：本科在 jwapp、研究生在 gsapp，均保留旧地址兜底。
JW_SCHEDULE_CANDIDATES = (
    "https://jw.xmu.edu.cn/jwapp/sys/wdkbapp/*default/index.do",
    "https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/*default/index.do",
    "https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/index.do",
    "https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/app/index.do",
)
# 2025 年底改版后「我的课表」前端异步加载数据，初始 HTML 为空壳；
# 课表数据走金智模块接口（各校通用路径，也用于自动发现的兜底）。
JW_JSON_ENDPOINTS = (
    "https://jw.xmu.edu.cn/jwapp/sys/wdkbapp/modules/xskccxs/xskccxs_cxXskccs.do",
    "https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/modules/xskccxs/xskccxs_cxXskccs.do",
    "https://jw.xmu.edu.cn/jwapp/sys/wdkbapp/modules/xskccxs/xskccxs_cxXsKb.do",
    "https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/modules/xskccxs/xskccxs_cxXsKb.do",
)
# 课表读取失败时的现场抓包目录（仅保留最近几份，供站长适配解析用）。
JW_DEBUG_DIR = SITE_ROOT / "data" / "jw-debug"
JW_DEBUG_KEEP = 3
JW_DEBUG_BODY_LIMIT = 200_000
XMU_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
CAS_HEADERS = {
    "User-Agent": XMU_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://ids.xmu.edu.cn/authserver/login",
}
CAS_AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
TIMETABLE_RATE_LOG: dict[str, deque] = defaultdict(deque)

# 两段式登录的预检会话：先拿登录页（salt/execution/验证码），用户提交时再完成登录。
# 仅存内存（opener/cookie 会话与隐藏字段），学号密码不在此阶段出现，TTL 过期即弃。
CAS_PREFLIGHT_TTL = 600.0
CAS_PREFLIGHT_MAX = 400
CAS_PREFLIGHT: dict[str, dict] = {}
CAS_PREFLIGHT_LOCK = threading.Lock()

# AES S 盒（仅加密方向，AES-128）。实现对照 FIPS-197 测试向量校验。
_AES_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16"
)
_AES_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _aes_xtime(value: int) -> int:
    value <<= 1
    if value & 0x100:
        value ^= 0x11B
    return value & 0xFF


def _aes128_expand_key(key: bytes):
    if len(key) != 16:
        raise ValueError("AES-128 密钥必须为 16 字节。")
    words = [list(key[index * 4:index * 4 + 4]) for index in range(4)]
    for index in range(4, 44):
        temp = list(words[index - 1])
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_AES_SBOX[byte] for byte in temp]
            temp[0] ^= _AES_RCON[index // 4 - 1]
        words.append([left ^ right for left, right in zip(words[index - 4], temp)])
    return [words[4 * round_index:4 * round_index + 4] for round_index in range(11)]


def _aes128_encrypt_block(round_keys, block: bytes) -> bytes:
    state = list(block)

    def add_round_key(round_index):
        for column in range(4):
            for row in range(4):
                state[column * 4 + row] ^= round_keys[round_index][column][row]

    # 扁平布局：index = column * 4 + row（与 AES 列主序输入一致）
    flat_key0 = [byte for word in round_keys[0] for byte in word]
    state = [left ^ right for left, right in zip(state, flat_key0)]

    for round_index in range(1, 11):
        state = [_AES_SBOX[byte] for byte in state]
        shifted = [0] * 16
        for row in range(4):
            for column in range(4):
                shifted[column * 4 + row] = state[((column + row) % 4) * 4 + row]
        state = shifted
        if round_index != 10:
            for column in range(4):
                s0, s1, s2, s3 = state[column * 4:column * 4 + 4]
                mixed = s0 ^ s1 ^ s2 ^ s3
                state[column * 4 + 0] = s0 ^ mixed ^ _aes_xtime(s0 ^ s1)
                state[column * 4 + 1] = s1 ^ mixed ^ _aes_xtime(s1 ^ s2)
                state[column * 4 + 2] = s2 ^ mixed ^ _aes_xtime(s2 ^ s3)
                state[column * 4 + 3] = s3 ^ mixed ^ _aes_xtime(s3 ^ s0)
        add_round_key(round_index)
    return bytes(state)


def aes128_cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128-CBC + PKCS7 填充加密。"""
    if len(iv) != 16:
        raise ValueError("AES IV 必须为 16 字节。")
    pad_len = 16 - len(data) % 16
    data = data + bytes([pad_len]) * pad_len
    round_keys = _aes128_expand_key(key)
    previous = iv
    output = bytearray()
    for offset in range(0, len(data), 16):
        chunk = bytes(left ^ right for left, right in zip(data[offset:offset + 16], previous))
        previous = _aes128_encrypt_block(round_keys, chunk)
        output.extend(previous)
    return bytes(output)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁用自动跳转，便于手动跟踪 CAS 登录链。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WdkbScheduleParser(HTMLParser):
    """解析教务系统「我的课表」页面：td[xq/jc/jcxq] 内的 div.arrage 课程块。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.courses: list[dict] = []
        self._td = None          # 当前 td 属性：xq / jc / jcxq / rowspan / hidden
        self._stack: list[dict] = []  # div 节点栈：{"buffer": 文本, "children": 子div文本}
        self._in_td = False

    def handle_starttag(self, tag, attrs):
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag == "td":
            style = attr_map.get("style", "").replace(" ", "").lower()
            self._td = {
                "xq": attr_map.get("xq", ""),
                "jc": attr_map.get("jc", ""),
                "jcxq": attr_map.get("jcxq", ""),
                "rowspan": attr_map.get("rowspan", ""),
                "hidden": "display:none" in style,
            }
            self._in_td = True
            self._stack = []
        elif tag == "div" and self._in_td:
            classes = attr_map.get("class", "").split()
            self._stack.append({"buffer": [], "children": [], "arrage": "arrage" in classes})

    def handle_endtag(self, tag):
        if tag == "td":
            self._td = None
            self._in_td = False
            self._stack = []
        elif tag == "div" and self._stack:
            node = self._stack.pop()
            text = "".join(node["buffer"]).strip()
            if node["arrage"]:
                self._emit_course(node["children"], text)
            elif self._stack:
                parent = self._stack[-1]
                if node["children"]:
                    parent["children"].append(" ".join(part for part in [text, *node["children"]] if part))
                else:
                    parent["children"].append(text)

    def handle_data(self, data):
        for node in self._stack:
            node["buffer"].append(data)

    def _emit_course(self, parts, extra_text):
        td = self._td or {}
        fields = [part.strip() for part in parts if part and part.strip()]
        if extra_text and extra_text not in fields:
            fields.append(extra_text)
        if not td.get("xq") or td.get("hidden") or len(fields) < 2:
            return
        try:
            day = int(str(td.get("xq", "")).strip())
        except ValueError:
            return
        if not 1 <= day <= 7:
            return
        jc_text = str(td.get("jc", "")).strip()
        jcxq_text = str(td.get("jcxq", "")).strip()
        start_period = None
        if jc_text.isdigit():
            start_period = int(jc_text)
        elif jcxq_text:
            match = re.match(r"\s*(\d+)", jcxq_text)
            if match:
                start_period = int(match.group(1))
        if not start_period or not 1 <= start_period <= 15:
            return
        try:
            span = int(str(td.get("rowspan", "")).strip() or "0")
        except ValueError:
            span = 0
        if span < 1 and jcxq_text:
            range_match = re.match(r"\s*(\d+)\s*[-–—~至到]\s*(\d+)", jcxq_text)
            if range_match:
                span = int(range_match.group(2)) - start_period + 1
        span = max(1, min(span or 1, 12))
        weeks = None
        parity = None
        weeks_match = re.search(
            r"(\d{1,2})\s*[-–—~至到]\s*(\d{1,2})\s*周?\s*[（(]?\s*([单双])?\s*[）)]?", fields[0]
        )
        if weeks_match:
            weeks = [int(weeks_match.group(1)), int(weeks_match.group(2))]
            parity = {"单": "odd", "双": "even"}.get(weeks_match.group(3))
        else:
            single = re.search(r"第?\s*(\d{1,2})\s*周", fields[0])
            if single:
                weeks = [int(single.group(1)), int(single.group(1))]
        if weeks and weeks[0] > weeks[1]:
            weeks[0], weeks[1] = weeks[1], weeks[0]
        name = re.sub(r"\([^()]*\)", "", fields[1]).strip() or fields[1].strip()
        loc = ""
        if len(fields) >= 4:
            loc = re.sub(r"（[^（）]*）", "", fields[3]).strip()
        elif len(fields) >= 3:
            candidate = re.sub(r"（[^（）]*）", "", fields[2]).strip()
            if re.search(r"(楼|馆|室|教室|校区|场|厅|中心)", candidate):
                loc = candidate
        teacher = fields[2].strip() if len(fields) >= 4 and fields[2].strip() != loc else ""
        course = {
            "name": name[:40],
            "day": day,
            "p1": start_period,
            "p2": start_period + span - 1,
            "loc": loc[:30],
            "weeks": weeks,
            "parity": parity,
        }
        if teacher:
            course["teacher"] = teacher[:20]
        if not course["name"]:
            return
        if not any(
            existing["name"] == course["name"]
            and existing["day"] == course["day"]
            and existing["p1"] == course["p1"]
            for existing in self.courses
        ):
            self.courses.append(course)


def _extract_cas_field(page: str, field: str):
    """从 CAS 登录页提取隐藏字段值，兼容属性顺序差异。"""
    for pattern in (
        rf'id="{field}"[^>]*value="([^"]*)"',
        rf'name="{field}"[^>]*value="([^"]*)"',
        rf'value="([^"]*)"[^>]*id="{field}"',
        rf'value="([^"]*)"[^>]*name="{field}"',
    ):
        match = re.search(pattern, page)
        if match:
            return match.group(1)
    return None


def _cas_page_error(page: str) -> str:
    # CAS 失败原因通常写在 id="msg" 的 span 里，且常内嵌 <s></s> 等图标标签，
    # 必须容忍内部标签、剥离后取纯文本，否则会把验证码错误误判成密码错误。
    for pattern in (
        r'id="msg"[^>]*>(.*?)</span>',
        r'id="(?:errorMsg|errorContent|showError|idcheckmsg)"[^>]*>(.*?)</(?:span|em|div)>',
    ):
        match = re.search(pattern, page, re.DOTALL)
        if match:
            text = html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
            if text:
                return text
    # 厦大 CAS 登录页常驻隐藏的验证码组件（captcha item hide），不能见到 captcha 字样就认定要验证码。
    # 只有验证码块实际展示（页面上不存在 hide 态）或响应明确提到验证码出错时，才提示验证码。
    captcha_visible = ("captcha item" in page and "captcha item hide" not in page) or bool(
        re.search(r'id="captchaImg"[^>]*style="[^"]*display:\s*(?!none)', page)
    )
    captcha_error_hint = any(
        hint in page for hint in (
            "请输入验证码", "验证码不正确", "验证码错误", "验证码有误",
            "验证码已", "图片验证码", "你输入的验证码", "您输入的验证码",
        )
    )
    if captcha_visible or captcha_error_hint:
        return "需要验证码：请输入图片中的验证码后重新登录。"
    if "密码" in page and ("错误" in page or "不正确" in page):
        return "账号或密码不正确。"
    return "登录未成功：学号或密码不正确，或统一身份认证暂时不可用。"


def _http_fetch(opener, url, data=None, headers=None, timeout=30):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        response = opener.open(request, timeout=timeout)
        return response.getcode() or 200, response.read(), response.headers, response.geturl()
    except urllib.error.HTTPError as error:
        return error.code, error.read() if hasattr(error, "read") else b"", error.headers, error.url


def _follow_redirects(opener, start_url, headers, limit=6):
    """手动跟踪 30x 跳转链，返回最终页面 HTML（含相对跳转补全）。"""
    url = start_url
    html = ""
    for _ in range(limit):
        if not url:
            break
        code, body, step_headers, _ = _http_fetch(opener, url, headers=headers)
        if code in (301, 302, 303, 307, 308):
            location = step_headers.get("Location", "") if step_headers else ""
            if location and location.startswith("/"):
                parsed = urlsplit(url)
                location = f"{parsed.scheme}://{parsed.netloc}{location}"
            url = location
            continue
        html = body.decode("utf-8", errors="replace")
        url = None
    return html


def _cas_build_opener():
    """构造带 Cookie 会话、不自动跟随跳转的 opener（跳转需手动确认登录成功）。"""
    import http.cookiejar  # 局部引用，保持模块顶部整洁

    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(_NoRedirectHandler, urllib.request.HTTPCookieProcessor(jar))


def _cas_service_param() -> str:
    return quote(CAS_SERVICE_URL, safe="")


def _cas_open_login_page(opener):
    """拉取 CAS 登录页，返回 (page, salt, execution)。"""
    _, page_bytes, _, _ = _http_fetch(
        opener, f"{CAS_LOGIN_URL}?service={_cas_service_param()}", headers=CAS_HEADERS
    )
    page = page_bytes.decode("utf-8", errors="replace")
    salt = _extract_cas_field(page, "pwdEncryptSalt")
    execution = _extract_cas_field(page, "execution")
    if not salt or not execution:
        raise RuntimeError(
            "无法读取统一身份认证登录页面（站点临时不可用或网络受限），请稍后再试。"
        )
    return page, salt, execution


def _cas_need_captcha(opener, username: str) -> bool:
    """查询该账号本次登录是否需要图片验证码；接口异常时按“需要”处理，宁可多一步。"""
    url = f"{CAS_NEED_CAPTCHA_URL}?username={quote(username, safe='')}&pwdEncrypt2=pwdEncryptSalt"
    try:
        code, body, _, _ = _http_fetch(opener, url, headers=CAS_HEADERS, timeout=10)
        if code == 200:
            data = json.loads(body.decode("utf-8", errors="replace"))
            return bool(data.get("isNeed"))
    except (ValueError, OSError):
        pass
    return True


def _cas_captcha_dataurl(opener) -> str:
    """拉取与会话绑定的图片验证码，转成 data URL 供前端直接显示。"""
    code, body, resp_headers, _ = _http_fetch(
        opener,
        f"{CAS_CAPTCHA_URL}?ts={int(time.time() * 1000)}",
        headers={**CAS_HEADERS, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
        timeout=10,
    )
    ctype = (resp_headers.get("Content-Type", "") if resp_headers else "").lower()
    if code == 200 and body[:3] == b"\xff\xd8\xff" and "image" in ctype:
        return "data:image/jpeg;base64," + base64.b64encode(body).decode("ascii")
    raise RuntimeError("获取验证码图片失败，请稍后再试。")


def _cas_submit_login(opener, username: str, password: str, salt: str, execution: str, captcha: str = ""):
    """提交 CAS 登录（密码按厦大规则 AES-CBC 加密），返回 (是否成功, 最终页/失败页 HTML)。"""
    plain = "".join(secrets.choice(CAS_AES_CHARS) for _ in range(64)) + password
    encrypted = base64.b64encode(
        aes128_cbc_encrypt(
            salt.encode("utf-8")[:16].ljust(16, b"\x00"), secrets.token_bytes(16), plain.encode()
        )
    ).decode()
    form = urlencode({
        "username": username,
        "password": encrypted,
        "captcha": captcha or "",
        "_eventId": "submit",
        "cllt": "userNameLogin",
        "dllt": "generalLogin",
        "lt": "",
        "execution": execution,
    }).encode()
    code, body, resp_headers, _ = _http_fetch(
        opener,
        f"{CAS_LOGIN_URL}?service={_cas_service_param()}",
        data=form,
        headers={**CAS_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
    )
    if code in (301, 302, 303, 307, 308):
        location = resp_headers.get("Location", "") if resp_headers else ""
        html = _follow_redirects(opener, location, CAS_HEADERS) if location else ""
        return True, html
    return False, body.decode("utf-8", errors="replace")


def _jw_debug_record(captures: list[dict], tag: str, url: str, method: str, code, body, headers, final: str = "") -> None:
    try:
        text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    except Exception:
        text = ""
    captures.append({
        "tag": tag,
        "url": url,
        "method": method,
        "status": code,
        "ctype": (headers.get("Content-Type", "") if headers else ""),
        "final": final,
        "body": text,
    })


def _jw_debug_dump(captures: list[dict]) -> str:
    """把本轮课表读取的所有请求现场写入 data/jw-debug/<时间戳>/，返回目录名（失败返回空串）。"""
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bundle = JW_DEBUG_DIR / stamp
        bundle.mkdir(parents=True, exist_ok=True)
        manifest = []
        for index, entry in enumerate(captures):
            name = f"{index:02d}-{entry['tag']}.txt"
            (bundle / name).write_text(
                "URL: {}\nMETHOD: {}\nSTATUS: {}\nCONTENT-TYPE: {}\nFINAL-URL: {}\n\n{}".format(
                    entry["url"], entry["method"], entry["status"], entry["ctype"], entry["final"],
                    entry["body"][:JW_DEBUG_BODY_LIMIT],
                ),
                encoding="utf-8",
            )
            manifest.append({
                "file": name, "tag": entry["tag"], "url": entry["url"], "method": entry["method"],
                "status": entry["status"], "ctype": entry["ctype"], "final": entry["final"],
                "captured_bytes": min(len(entry["body"]), JW_DEBUG_BODY_LIMIT),
            })
        (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(JW_DEBUG_DIR, 0o700)
            os.chmod(bundle, 0o700)
        except OSError:
            pass
        for old in sorted(JW_DEBUG_DIR.iterdir())[:-JW_DEBUG_KEEP]:
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
        return stamp
    except OSError:
        return ""


def _courses_from_json_rows(rows: list):
    """从金智模块接口返回的 rows 里尽量提取课程（字段名各校略有差异，做通用启发式）。"""
    courses = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        strings = {key: str(value).strip() for key, value in row.items() if isinstance(value, (str, int, float))}

        def pick(*keys):
            for key in keys:
                value = strings.get(key)
                if value:
                    return value
            return ""

        name = pick("KCMC", "KCZW", "KCM", "KC_MC")
        if not name:
            continue
        day = 0
        for key in ("XQJ", "XQ", "WEEK_DAY", "XQJ_Display"):
            value = strings.get(key, "")
            if value.isdigit() and 1 <= int(value) <= 7:
                day = int(value)
                break
        if not day:
            week_day_match = re.search(r"([一二三四五六日])", pick("XQMC", "XQ_DISPLAY", "WEEK_DAY_DISPLAY"))
            if week_day_match:
                day = "一二三四五六日".index(week_day_match.group(1)) + 1
        p1, p2 = 0, 0
        for key_first, key_last in (("JC_1", "JC_2"), ("KSJC", "JSJC"), ("QSJC", "JXJC")):
            first, last = strings.get(key_first, ""), strings.get(key_last, "")
            if first.isdigit() and last.isdigit():
                p1, p2 = int(first), int(last)
                break
        if not p1:
            section_match = re.search(r"(\d{1,2})\s*[-–—~]\s*(\d{1,2})\s*节", " ".join(strings.values()))
            if section_match:
                p1, p2 = int(section_match.group(1)), int(section_match.group(2))
        weeks, parity = None, None
        for value in strings.values():
            weeks_match = re.search(r"(\d{1,2})\s*[-–—~至到]\s*(\d{1,2})\s*周?\s*[（(]?\s*([单双])?\s*[）)]?", value)
            if weeks_match:
                weeks = [int(weeks_match.group(1)), int(weeks_match.group(2))]
                parity = {"单": "odd", "双": "even"}.get(weeks_match.group(3))
                break
        loc = pick("JASMC", "JSMC", "JXM", "JXDZ", "JAS_Name")
        teacher = pick("JSXM", "JS_MC", "TEACHER")
        if not (name and 1 <= day <= 7 and p1 >= 1):
            continue
        p2 = p2 if p2 >= p1 else p1
        course = {
            "name": name[:40], "day": day, "p1": p1, "p2": min(p2, p1 + 11),
            "loc": loc[:30],
            "weeks": weeks if weeks and weeks[0] <= weeks[1] else None,
            "parity": parity,
        }
        if teacher:
            course["teacher"] = teacher[:24]
        courses.append(course)
    return courses


def _rows_from_schedule_json(text: str):
    """金智模块接口的返回结构常见为 {"datas":{"<模块>":{"rows":[...]}}}，做兼容提取。"""
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    datas = payload.get("datas")
    if isinstance(datas, dict):
        for value in datas.values():
            if isinstance(value, dict) and isinstance(value.get("rows"), list):
                return value["rows"]
            if isinstance(value, list):
                return value
    if isinstance(payload.get("rows"), list):
        return payload["rows"]
    if isinstance(payload.get("data"), list):
        return payload["data"]
    return None


def _cas_discover_module_urls(opener, shell_entries: list) -> list[str]:
    """从课表页壳 HTML 及其引用的 JS 里自动发现金智模块接口地址。"""
    discovered: list[str] = []
    for entry in shell_entries:
        if not entry["body"]:
            continue
        candidates = re.findall(r"sys/wdkbapp/modules/[\w/]+\.do", entry["body"])
        for candidate in candidates:
            absolute = candidate if candidate.startswith("http") else f"https://jw.xmu.edu.cn/{candidate}"
            if absolute not in discovered:
                discovered.append(absolute)
        js_urls = re.findall(r"""src=["']([^"']+\.js[^"']*)["']""", entry["body"])
        for js_url in js_urls[:6]:
            if "wdkbapp" not in js_url and "modules" not in js_url and "appmain" not in js_url.lower():
                continue
            absolute = js_url if js_url.startswith("http") else f"https://jw.xmu.edu.cn/{js_url.lstrip('/')}"
            try:
                code, body, headers, final = _http_fetch(opener, absolute, headers=CAS_HEADERS, timeout=15)
            except (urllib.error.URLError, OSError):
                continue
            js_text = body.decode("utf-8", errors="replace")
            _jw_debug_record(shell_entries, "js", absolute, "GET", code, js_text, headers, final)
            for candidate in re.findall(r"sys/wdkbapp/modules/[\w/]+\.do", js_text):
                path = candidate if candidate.startswith("http") else f"https://jw.xmu.edu.cn/{candidate}"
                if path not in discovered:
                    discovered.append(path)
    return discovered[:12]


def _cas_follow(opener, captures: list, tag: str, method: str, url: str, headers, data=None, limit=8):
    """手动跟随 30x 跳转链（教务平台 302 → CAS 换票 → 回跳，即金智 SSO 击穿）。
    返回 (最终code, 最终body, 最终headers, 最终URL)。全程记录到 captures。"""
    chain: list[str] = []
    origin = url
    code, body, resp_headers, final = 0, b"", None, url
    for _ in range(limit):
        code, body, resp_headers, final = _http_fetch(opener, url, data=data, headers=headers)
        location = (resp_headers.get("Location", "") if resp_headers else "") or ""
        chain.append(f"{code} {url} -> {location or '-'}")
        if code not in (301, 302, 303, 307, 308) or not location:
            _jw_debug_record(captures, tag, f"{method} {url}", method, code, body, resp_headers, final)
            break
        _jw_debug_record(captures, tag, f"{method} {url} [redirect {code}]", method, code, b"", resp_headers, final)
        if location.startswith("/"):
            parsed = urlsplit(url)
            location = f"{parsed.scheme}://{parsed.netloc}{location}"
        url = location
        data = None  # 302 后按规范转 GET
    else:
        _jw_debug_record(captures, tag, f"{method} {url} [chain-too-long]", method, code, body, resp_headers, final)
    _jw_debug_record(captures, "chain", origin, method, "trace", "\n".join(chain), None, "")
    return code, body, resp_headers, url


def _cas_cookie_summary(opener) -> str:
    """列出会话 Cookie 的域与名字（不含值），用于判断登录态是否完整。"""
    try:
        for handler in opener.handlers:
            jar = getattr(handler, "cookiejar", None)
            if jar is not None:
                return "\n".join(f"{cookie.domain} {cookie.name}" for cookie in jar) or "(空)"
    except Exception:
        pass
    return "(无法读取)"


def _cas_fetch_schedule(opener):
    """登录成功后读取「我的课表」：候选页面/JSON 接口遇 302 一路跟随（自动 CAS 换票），
    全程抓包存档，失败时留下现场供站长适配。返回 (courses, semester)。"""
    captures: list[dict] = []
    _jw_debug_record(captures, "cookies", "cookie jar (domain name)", "INFO", "info", _cas_cookie_summary(opener), None)

    # 1) 旧版服务端渲染页面（td[xq/jc] + div.arrage）
    for candidate in JW_SCHEDULE_CANDIDATES:
        page_code, page_body, page_headers, final_url = _cas_follow(
            opener, captures, "html", "GET", candidate, CAS_HEADERS
        )
        page_html = page_body.decode("utf-8", errors="replace")
        if page_code != 200 or "arrage" not in page_html:
            continue
        parser = WdkbScheduleParser()
        parser.feed(page_html)
        parser.close()
        if parser.courses:
            semester_match = re.search(r"(20\d{2}-20\d{2}学年\s*(?:春|秋|夏)?季?学期)", page_html)
            return parser.courses, semester_match.group(1) if semester_match else ""

    # 2) 新版异步加载：从壳页面/JS 发现模块接口，加上通用兜底地址，逐个尝试。
    #    POST 若遇 302 说明该应用会话未建立——跟随跳转（自动 CAS 换票）后补发一次 POST。
    discovered = _cas_discover_module_urls(opener, [c for c in captures if c["tag"] == "html"])
    endpoints = discovered + [url for url in JW_JSON_ENDPOINTS if url not in discovered]
    json_headers = {
        **CAS_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://jw.xmu.edu.cn/jwapp/sys/wdkbapp/*default/index.do",
    }
    semester = ""
    for endpoint in endpoints:
        for method in ("post", "get"):
            data = b"" if method == "post" else None
            code, body, resp_headers, final_url = _cas_follow(
                opener, captures, "json", method, endpoint, json_headers, data=data
            )
            if code in (301, 302, 303, 307, 308) or code == 0:
                continue
            if code != 200:
                break
            text = body.decode("utf-8", errors="replace")
            rows = _rows_from_schedule_json(text)
            if not rows:
                continue
            courses = _courses_from_json_rows(rows)
            if courses:
                for row in rows[:1]:
                    if isinstance(row, dict):
                        semester = str(row.get("XNXQDM_DISPLAY") or row.get("XNXQMC") or "").strip()
                        break
                return courses, semester

    stamp = _jw_debug_dump(captures)
    detail = f"（现场已记录：jw-debug/{stamp}）" if stamp else ""
    raise RuntimeError(
        "登录成功，但没有读到课表数据（教务系统近期改版，站长会尽快适配）。"
        f"{detail} 当前请改用「从教务系统导出文件 / 粘贴文本」方式导入。"
    )


def _cas_preflight_store(token: str, state: dict) -> None:
    with CAS_PREFLIGHT_LOCK:
        now = time.time()
        for key in [k for k, v in CAS_PREFLIGHT.items() if now - v["created"] > CAS_PREFLIGHT_TTL]:
            CAS_PREFLIGHT.pop(key, None)
        if len(CAS_PREFLIGHT) >= CAS_PREFLIGHT_MAX:
            oldest = min(CAS_PREFLIGHT, key=lambda k: CAS_PREFLIGHT[k]["created"])
            CAS_PREFLIGHT.pop(oldest, None)
        CAS_PREFLIGHT[token] = state


def _cas_preflight_pop(token: str):
    with CAS_PREFLIGHT_LOCK:
        state = CAS_PREFLIGHT.pop(token, None) if token else None
    if state and time.time() - state["created"] > CAS_PREFLIGHT_TTL:
        return None
    return state


def xmu_fetch_timetable(username: str, password: str):
    """兼容旧调用：一次性完成 CAS 登录并读取课表（若触发验证码则抛错提示）。"""
    opener = _cas_build_opener()
    _, salt, execution = _cas_open_login_page(opener)
    ok, page = _cas_submit_login(opener, username, password, salt, execution)
    if not ok:
        raise RuntimeError(_cas_page_error(page))
    return _cas_fetch_schedule(opener)


def initialise_material_store():
    MATERIAL_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(MATERIAL_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                object_key TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT '其他',
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                size INTEGER NOT NULL DEFAULT 0,
                storage TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def material_connection():
    connection = sqlite3.connect(MATERIAL_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def material_row(row):
    return {
        "id": row["id"],
        "name": row["original_name"],
        "object_key": row["object_key"],
        "category": row["category"],
        "mime_type": row["mime_type"],
        "size": row["size"],
        "storage": row["storage"],
        "created_at": row["created_at"],
        "download_url": f"/api/materials/download?id={row['id']}",
    }


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return "pbkdf2$sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def verify_password(password: str) -> bool:
    if ADMIN_PASSWORD_HASH:
        try:
            parts = ADMIN_PASSWORD_HASH.split("$")
            algorithm = parts[0]
            if algorithm == "pbkdf2" and len(parts) == 5:
                _, digest_name, iterations_value, salt_value, digest_value = parts
                if digest_name != "sha256":
                    return False
                pad_salt = "=" * (-len(salt_value) % 4)
                pad_digest = "=" * (-len(digest_value) % 4)
                salt = base64.urlsafe_b64decode((salt_value + pad_salt).encode("ascii"))
                expected = base64.urlsafe_b64decode((digest_value + pad_digest).encode("ascii"))
                actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_value), dklen=len(expected))
                return secrets.compare_digest(actual, expected)
            if algorithm != "scrypt" or len(parts) != 6 or not hasattr(hashlib, "scrypt"):
                return False
            _, n_value, r_value, p_value, salt_value, digest_value = parts
            pad_salt = "=" * (-len(salt_value) % 4)
            pad_digest = "=" * (-len(digest_value) % 4)
            salt = base64.urlsafe_b64decode((salt_value + pad_salt).encode("ascii"))
            expected = base64.urlsafe_b64decode((digest_value + pad_digest).encode("ascii"))
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n_value),
                r=int(r_value),
                p=int(p_value),
                dklen=len(expected),
            )
            return secrets.compare_digest(actual, expected)
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            return False
    return bool(ADMIN_PASSWORD) and secrets.compare_digest(password, ADMIN_PASSWORD)


def admin_configured() -> bool:
    return bool(ADMIN_USERNAME and (ADMIN_PASSWORD_HASH or ADMIN_PASSWORD))


def cleanup_admin_sessions():
    now = time.time()
    expired = [token for token, expires_at in ADMIN_SESSIONS.items() if expires_at <= now]
    for token in expired:
        ADMIN_SESSIONS.pop(token, None)


# ---------------------------------------------------------------------------
# 用户账号体系：邮箱注册 + 课表云端保存（SQLite，纯标准库）
# ---------------------------------------------------------------------------
USER_DB_PATH = Path(os.getenv("USER_DB_PATH", str(MATERIAL_DATA_ROOT / "users.sqlite3"))).resolve()
ACCOUNT_SESSION_TTL = 30 * 24 * 3600  # 30 天
# 允许注册的邮箱域：默认放开任意邮箱；如需限制校园邮箱，改为 "stu.xmu.edu.cn,xmu.edu.cn"
ACCOUNT_EMAIL_DOMAINS = [d.strip().lower() for d in os.getenv("ACCOUNT_EMAIL_DOMAINS", "any").split(",") if d.strip()]

_ACCOUNT_DB_LOCK = threading.Lock()


def account_connection():
    connection = sqlite3.connect(USER_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def init_account_db():
    USER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                pw_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_timetables (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def verify_stored_hash(stored: str, password: str) -> bool:
    try:
        parts = stored.split("$")
        if parts[0] != "pbkdf2" or len(parts) != 5:
            return False
        _, digest_name, iterations_value, salt_value, digest_value = parts
        if digest_name != "sha256":
            return False
        pad = lambda v: "=" * (-len(v) % 4)  # noqa: E731
        salt = base64.urlsafe_b64decode((salt_value + pad(salt_value)).encode("ascii"))
        expected = base64.urlsafe_b64decode((digest_value + pad(digest_value)).encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_value), dklen=len(expected))
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return False


def validate_email(email: str):
    """返回 (email, 错误信息)。合法返回 (email.lower(), None)。"""
    email = email.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        return None, "邮箱格式不正确。"
    if "any" not in ACCOUNT_EMAIL_DOMAINS:
        domain = email.split("@", 1)[1]
        if not any(domain == d or domain.endswith("." + d) for d in ACCOUNT_EMAIL_DOMAINS):
            allowed = " / ".join(f"@{d}" for d in ACCOUNT_EMAIL_DOMAINS)
            return None, f"目前仅支持校园邮箱注册（{allowed}）。"
    return email, None


def account_register(email: str, password: str):
    email, error = validate_email(email)
    if error:
        return None, error
    if len(password) < 8:
        return None, "密码至少 8 位。"
    if len(password) > 72:
        return None, "密码过长（最多 72 位）。"
    pw_hash = password_hash(password)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        existing = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return None, "该邮箱已注册，请直接登录。"
        cursor = connection.execute(
            "INSERT INTO users (email, pw_hash, created_at) VALUES (?, ?, ?)", (email, pw_hash, now)
        )
        user_id = cursor.lastrowid
    return user_id, None


def account_login(email: str, password: str):
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        row = connection.execute("SELECT id, pw_hash FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not row or not verify_stored_hash(row["pw_hash"], password):
        return None, "邮箱或密码不正确。"
    return row["id"], None


def account_create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        connection.execute(
            "INSERT INTO account_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, time.time() + ACCOUNT_SESSION_TTL),
        )
    return token


def account_user_from_token(token: str):
    if not token:
        return None
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        row = connection.execute(
            "SELECT u.id, u.email FROM account_sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, time.time()),
        ).fetchone()
    return dict(row) if row else None


def account_delete_session(token: str):
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        connection.execute("DELETE FROM account_sessions WHERE token = ?", (token,))


def account_save_timetable(user_id: int, courses: list):
    payload = json.dumps(courses, ensure_ascii=False)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        connection.execute(
            "INSERT INTO user_timetables (user_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (user_id, payload, now),
        )
    return now


def account_get_timetable(user_id: int):
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        row = connection.execute("SELECT data, updated_at FROM user_timetables WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None, None
    try:
        return json.loads(row["data"]), row["updated_at"]
    except (ValueError, TypeError):
        return None, None


def account_delete_user(user_id: int):
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        connection.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM user_timetables WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM account_sessions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))


PROFILE_CAMPUSES = ("未设置校区", "思明校区", "翔安校区", "漳州校区")


def clean_profile(payload: dict) -> dict:
    nickname = str(payload.get("nickname", "")).strip()[:24] or "厦园同学"
    campus = payload.get("campus") if payload.get("campus") in PROFILE_CAMPUSES else "未设置校区"
    grade = str(payload.get("grade", "")).strip()[:12] or "未设置年级"
    return {"nickname": nickname, "campus": campus, "grade": grade}


def account_save_profile(user_id: int, data: dict):
    payload = json.dumps(data, ensure_ascii=False)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        connection.execute(
            "INSERT INTO user_profiles (user_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (user_id, payload, now),
        )
    return now


def account_get_profile(user_id: int):
    with _ACCOUNT_DB_LOCK, account_connection() as connection:
        row = connection.execute("SELECT data, updated_at FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None, None
    try:
        return json.loads(row["data"]), row["updated_at"]
    except (ValueError, TypeError):
        return None, None


init_account_db()


def make_object_key(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    stamp = time.strftime("%Y/%m")
    return f"materials/{stamp}/{secrets.token_hex(16)}{extension}"


def safe_filename(filename: str) -> str:
    name = Path(str(filename or "资料")).name.replace("\x00", "").strip()
    name = re.sub(r"[\r\n\t]+", " ", name)
    return name[:180] or "资料"


def validate_material_meta(name: str, size: int, mime_type: str):
    filename = safe_filename(name)
    extension = Path(filename).suffix.lower()
    if extension not in MATERIAL_ALLOWED_EXTENSIONS:
        raise ValueError("暂不支持这个文件类型，请上传 PDF、Office、压缩包或常见图片文件。")
    if size <= 0:
        raise ValueError("文件不能为空。")
    if size > MATERIAL_MAX_BYTES:
        raise ValueError(f"文件不能超过 {MATERIAL_MAX_BYTES // (1024 * 1024)} MB。")
    return filename, (mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream")[:160]


def cos_client():
    global _COS_CLIENT, _COS_IMPORT_ERROR
    if _COS_CLIENT is not None:
        return _COS_CLIENT
    if not all((COS_BUCKET, COS_REGION, COS_SECRET_ID, COS_SECRET_KEY)):
        raise RuntimeError("COS 配置不完整，请检查 COS_BUCKET、COS_REGION、COS_SECRET_ID 和 COS_SECRET_KEY。")
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as error:
        _COS_IMPORT_ERROR = error
        raise RuntimeError("服务器尚未安装 cos-python-sdk-v5，请先安装 requirements.txt 中的依赖。") from error
    config = CosConfig(
        Region=COS_REGION,
        SecretId=COS_SECRET_ID,
        SecretKey=COS_SECRET_KEY,
        Token=COS_SESSION_TOKEN or None,
        Scheme="https",
    )
    _COS_CLIENT = CosS3Client(config)
    return _COS_CLIENT


def cos_presigned_url(method: str, object_key: str, filename: str = "", mime_type: str = ""):
    params = {}
    headers = {}
    if method == "PUT" and mime_type:
        headers["Content-Type"] = mime_type
    if method == "GET":
        params["response-content-disposition"] = "attachment; filename*=UTF-8''" + quote(filename or "资料")
        params["response-content-type"] = mime_type or "application/octet-stream"
    return cos_client().get_presigned_url(
        Method=method,
        Bucket=COS_BUCKET,
        Key=object_key,
        Expired=600 if method == "PUT" else 300,
        Headers=headers,
        Params=params,
    )


def parse_multipart(body: bytes, content_type: str):
    match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type, re.I)
    if not match:
        raise ValueError("上传请求缺少 boundary。")
    boundary = (match.group(1) or match.group(2)).encode("utf-8")
    parts = []
    for section in body.split(b"--" + boundary):
        if section.startswith(b"\r\n"):
            section = section[2:]
        if section in {b"", b"--", b"\r\n", b"--\r\n"}:
            continue
        if section.endswith(b"\r\n"):
            section = section[:-2]
        if not section or b"\r\n\r\n" not in section:
            continue
        header_blob, content = section.split(b"\r\n\r\n", 1)
        headers = header_blob.decode("utf-8", errors="replace")
        disposition = re.search(r'Content-Disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?', headers, re.I)
        if disposition:
            parts.append((disposition.group(1), disposition.group(2), content))
    return parts


initialise_material_store()


class PageTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip_depth += 1
        if tag == "iframe":
            srcdoc = dict(attrs).get("srcdoc")
            if srcdoc:
                nested = PageTextExtractor()
                nested.feed(html.unescape(srcdoc))
                self.parts.extend(nested.parts)
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "svg", "noscript"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        joined = " ".join(self.parts)
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r"\s*\n\s*", "\n", joined)
        return joined.strip()


def search_tokens(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    grams = {cjk[index:index + 2] for index in range(max(0, len(cjk) - 1))}
    words = set(re.findall(r"[a-z0-9][a-z0-9._-]{1,}", normalized))
    return grams | words


def build_knowledge():
    chunks = []
    html_files = [SITE_ROOT / HOME_PAGE, *sorted((SITE_ROOT / "pages").glob("*.html"))]
    for path in html_files:
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        parser = PageTextExtractor()
        parser.feed(raw)
        text = parser.text()
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else path.stem
        paragraphs = [item.strip() for item in text.splitlines() if len(item.strip()) >= 12]
        buffer = ""
        for paragraph in paragraphs:
            if len(buffer) + len(paragraph) + 1 <= 900:
                buffer = f"{buffer}\n{paragraph}".strip()
                continue
            if buffer:
                chunks.append({"title": title, "source": path.name, "text": buffer, "tokens": search_tokens(buffer + title)})
            buffer = paragraph
        if buffer:
            chunks.append({"title": title, "source": path.name, "text": buffer, "tokens": search_tokens(buffer + title)})
    return chunks


KNOWLEDGE = build_knowledge()
REQUEST_LOG: dict[str, deque] = defaultdict(deque)


def retrieve(question: str, limit: int = 8):
    query_tokens = search_tokens(question)
    query_compact = re.sub(r"\s+", "", question.lower())
    ranked = []
    for chunk in KNOWLEDGE:
        overlap = len(query_tokens & chunk["tokens"])
        phrase_bonus = 8 if query_compact and query_compact in re.sub(r"\s+", "", chunk["text"].lower()) else 0
        score = overlap + phrase_bonus
        if score:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return []

    # 只有出现足够的关键词重合，才把资料交给模型；否则应走通用问答，
    # 避免把“资料库第一段”误当成与问题有关的内容。
    best_score = ranked[0][0]
    threshold = 1 if len(query_tokens) <= 2 else max(2, (len(query_tokens) + 4) // 5)
    if best_score < threshold:
        return []
    return [chunk for score, chunk in ranked[:limit] if score >= threshold]


def format_ai_answer(answer: str) -> str:
    """将模型输出整理成聊天窗口适合阅读的纯文本。"""
    cleaned = str(answer or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"```(?:[a-zA-Z0-9_-]+)?", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*\*+\s*", "• ", cleaned)
    cleaned = re.sub(r"\*+", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-+]\s+", "• ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class XiayuanHandler(SimpleHTTPRequestHandler):
    server_version = "XiayuanGuide/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if self.path.split("?", 1)[0].endswith(".html") or self.path.split("?", 1)[0] == "/":
            self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def route(self):
        return urlsplit(self.path).path

    def request_json(self, max_length=64 * 1024):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("请求长度不正确。") from error
        if length > max_length:
            raise OverflowError("请求太大。")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def admin_token(self):
        match = re.search(r"(?:^|;\s*)xiayuan_admin=([^;]+)", self.headers.get("Cookie", ""))
        return match.group(1) if match else ""

    def account_token(self):
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:].strip()
        return ""

    def is_admin(self):
        cleanup_admin_sessions()
        token = self.admin_token()
        return bool(token and token in ADMIN_SESSIONS and ADMIN_SESSIONS[token] > time.time())

    def require_admin(self):
        if self.is_admin():
            return True
        self.send_json({"error": "请先登录管理员账号。"}, HTTPStatus.UNAUTHORIZED)
        return False

    def login_rate_limit_ok(self):
        address = self.client_address[0]
        now = time.time()
        window = ADMIN_LOGIN_LOG[address]
        while window and now - window[0] > 300:
            window.popleft()
        if len(window) >= 12:
            return False
        window.append(now)
        return True

    def local_material_path(self, object_key):
        root = MATERIAL_DATA_ROOT.resolve()
        path = (root / object_key).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError("文件路径不合法。") from error
        return path

    def get_material(self, material_id):
        try:
            material_id = int(material_id)
        except (TypeError, ValueError):
            return None
        with material_connection() as connection:
            return connection.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()

    def material_list(self, query, category):
        query = query.strip()[:80]
        category = category.strip()[:40]
        sql = "SELECT * FROM materials WHERE 1 = 1"
        params = []
        if query:
            sql += " AND (original_name LIKE ? OR category LIKE ?)"
            params.extend((f"%{query}%", f"%{query}%"))
        if category and category != "全部":
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY id DESC LIMIT 200"
        with material_connection() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [material_row(row) for row in rows]

    def insert_material(self, *, name, object_key, category, mime_type, size, storage):
        created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with material_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO materials (original_name, object_key, category, mime_type, size, storage, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, object_key, category, mime_type, size, storage, created_at),
            )
            material_id = cursor.lastrowid
        return self.get_material(material_id)

    def send_local_material(self, row):
        try:
            path = self.local_material_path(row["object_key"])
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = path.stat().st_size
            with path.open("rb") as file_handle:
                content = file_handle.read()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", row["mime_type"] or "application/octet-stream")
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(row["original_name"]))
        self.send_header("Content-Length", str(size))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        route = self.route()
        if route == "/":
            self.path = "/" + HOME_PAGE
        if route == "/data" or route.startswith("/data/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if route == "/api/health":
            self.send_json({"ok": True, "model": os.getenv("SILICONFLOW_MODEL", DEFAULT_MODEL), "knowledge_chunks": len(KNOWLEDGE)})
            return
        if route in ("/api/stations", "/api/search"):
            self._proxy_train_planner(self.path)
            return
        if route == "/api/materials/config":
            self.send_json({
                "storage": MATERIAL_STORAGE if MATERIAL_STORAGE in {"local", "cos"} else "local",
                "max_upload_bytes": MATERIAL_MAX_BYTES,
                "max_upload_mb": MATERIAL_MAX_BYTES // (1024 * 1024),
            })
            return
        if route == "/api/admin/session":
            if self.is_admin():
                self.send_json({"authenticated": True, "username": ADMIN_USERNAME})
            else:
                self.send_json({"authenticated": False}, HTTPStatus.UNAUTHORIZED)
            return
        if route == "/api/materials":
            params = parse_qs(urlsplit(self.path).query)
            query = params.get("q", [""])[0]
            category = params.get("category", [""])[0]
            self.send_json({"materials": self.material_list(query, category)})
            return
        if route == "/api/materials/download":
            params = parse_qs(urlsplit(self.path).query)
            row = self.get_material(params.get("id", [""])[0])
            if not row:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if row["storage"] == "local":
                self.send_local_material(row)
                return
            try:
                self.send_redirect(cos_presigned_url("GET", row["object_key"], row["original_name"], row["mime_type"]))
            except RuntimeError as error:
                self.send_json({"error": str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route == "/api/account/session":
            user = account_user_from_token(self.account_token())
            if not user:
                self.send_json({"authenticated": False})
                return
            self.send_json({"authenticated": True, "email": user["email"]})
            return
        if route == "/api/account/timetable":
            user = account_user_from_token(self.account_token())
            if not user:
                self.send_json({"error": "请先登录。"}, HTTPStatus.UNAUTHORIZED)
                return
            courses, updated_at = account_get_timetable(user["id"])
            self.send_json({"ok": True, "courses": courses or [], "updated_at": updated_at, "has_cloud": courses is not None})
            return
        if route == "/api/account/profile":
            user = account_user_from_token(self.account_token())
            if not user:
                self.send_json({"error": "请先登录。"}, HTTPStatus.UNAUTHORIZED)
                return
            profile_data, updated_at = account_get_profile(user["id"])
            self.send_json({"ok": True, "profile": profile_data, "updated_at": updated_at, "has_cloud": profile_data is not None})
            return
        super().do_GET()

    def _proxy_train_planner(self, upstream_path: str, data: bytes | None = None):
        """拼票规划器：把 /api/plan、/api/search、/api/stations 同源转发给本机 Node 服务。"""
        upstream = os.getenv("TRAIN_PLANNER_UPSTREAM", "http://127.0.0.1:3721").rstrip("/")
        request = urllib.request.Request(
            upstream + upstream_path,
            data=data,
            method="POST" if data is not None else "GET",
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as resp:
                payload, status = resp.read(), resp.status
        except urllib.error.HTTPError as error:
            payload, status = error.read(), error.code
        except (urllib.error.URLError, OSError):
            traceback.print_exc(file=sys.stderr)
            self.send_json(
                {"ok": False, "error": "拼票服务暂时不可用，请稍后再试。"},
                HTTPStatus.BAD_GATEWAY,
            )
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        route = self.route()
        if route == "/api/plan":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            body = self.rfile.read(length) if 0 < length <= 1_000_000 else b"{}"
            self._proxy_train_planner("/api/plan", data=body)
            return
        if route == "/api/admin/login":
            if not admin_configured():
                self.send_json({"error": "管理员账号尚未配置，请先在服务器环境变量中设置。"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if not self.login_rate_limit_ok():
                self.send_json({"error": "登录尝试过多，请 5 分钟后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            try:
                payload = self.request_json()
                username = str(payload.get("username", "")).strip()[:80]
                password = str(payload.get("password", ""))[:200]
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "登录信息格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            if not secrets.compare_digest(username, ADMIN_USERNAME) or not verify_password(password):
                self.send_json({"error": "账号或密码不正确。"}, HTTPStatus.UNAUTHORIZED)
                return
            cleanup_admin_sessions()
            token = secrets.token_urlsafe(32)
            ADMIN_SESSIONS[token] = time.time() + ADMIN_SESSION_TTL
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
            cookie = f"xiayuan_admin={token}; Path=/; Max-Age={ADMIN_SESSION_TTL}; HttpOnly; SameSite=Strict{secure}"
            self.send_json({"ok": True, "username": ADMIN_USERNAME}, headers={"Set-Cookie": cookie})
            return
        if route == "/api/admin/logout":
            token = self.admin_token()
            ADMIN_SESSIONS.pop(token, None)
            self.send_json({"ok": True}, headers={"Set-Cookie": "xiayuan_admin=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
            return
        if route == "/api/admin/materials/upload-url":
            if not self.require_admin():
                return
            try:
                payload = self.request_json()
                name, mime_type = validate_material_meta(
                    payload.get("name", ""),
                    int(payload.get("size", 0)),
                    str(payload.get("mime_type", "")),
                )
                category = str(payload.get("category", "其他")).strip()[:40] or "其他"
                size = int(payload.get("size", 0))
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, OverflowError) as error:
                self.send_json({"error": str(error) or "上传信息不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            object_key = make_object_key(name)
            if MATERIAL_STORAGE != "cos":
                self.send_json({"mode": "local", "name": name, "mime_type": mime_type, "size": size, "category": category, "object_key": object_key})
                return
            try:
                upload_url = cos_presigned_url("PUT", object_key, name, mime_type)
            except RuntimeError as error:
                self.send_json({"error": str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self.send_json({
                "mode": "cos",
                "upload_url": upload_url,
                "headers": {"Content-Type": mime_type},
                "name": name,
                "mime_type": mime_type,
                "size": size,
                "category": category,
                "object_key": object_key,
            })
            return
        if route == "/api/admin/materials/upload":
            if not self.require_admin():
                return
            if MATERIAL_STORAGE == "cos":
                self.send_json({"error": "当前使用 COS 直传模式，请从管理页面重新开始上传。"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MATERIAL_MAX_BYTES + 2 * 1024 * 1024:
                    raise OverflowError(f"文件不能超过 {MATERIAL_MAX_BYTES // (1024 * 1024)} MB。")
                body = self.rfile.read(length)
                parts = parse_multipart(body, self.headers.get("Content-Type", ""))
                file_part = next((part for part in parts if part[0] == "file" and part[1]), None)
                category_part = next((part for part in parts if part[0] == "category"), None)
                if not file_part:
                    raise ValueError("没有找到要上传的文件。")
                name, filename, file_content = file_part
                filename, mime_type = validate_material_meta(filename, len(file_content), self.headers.get("X-File-Type", ""))
                category = category_part[2].decode("utf-8", errors="replace").strip()[:40] if category_part else "其他"
                category = category or "其他"
                object_key = make_object_key(filename)
                path = self.local_material_path(object_key)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(file_content)
                row = self.insert_material(name=filename, object_key=object_key, category=category, mime_type=mime_type, size=len(file_content), storage="local")
            except (ValueError, TypeError, UnicodeError, OverflowError, OSError, sqlite3.Error) as error:
                self.send_json({"error": str(error) or "上传失败。"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"ok": True, "material": material_row(row)})
            return
        if route == "/api/admin/materials/complete":
            if not self.require_admin():
                return
            try:
                payload = self.request_json()
                name, mime_type = validate_material_meta(payload.get("name", ""), int(payload.get("size", 0)), str(payload.get("mime_type", "")))
                object_key = str(payload.get("object_key", ""))
                if not re.fullmatch(r"materials/[0-9]{4}/[0-9]{2}/[a-f0-9]{32}[^/]*", object_key):
                    raise ValueError("文件路径不合法。")
                category = str(payload.get("category", "其他")).strip()[:40] or "其他"
                if MATERIAL_STORAGE != "cos":
                    raise ValueError("当前不是 COS 存储模式。")
                try:
                    cos_client().head_object(Bucket=COS_BUCKET, Key=object_key)
                except Exception as error:
                    raise ValueError("腾讯云 COS 中没有找到刚刚上传的文件，请重试。") from error
                row = self.insert_material(name=name, object_key=object_key, category=category, mime_type=mime_type, size=int(payload.get("size", 0)), storage="cos")
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, OverflowError, sqlite3.Error) as error:
                self.send_json({"error": str(error) or "上传记录保存失败。"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"ok": True, "material": material_row(row)})
            return
        if route == "/api/timetable/preflight":
            address = self.client_address[0]
            now = time.time()
            window = TIMETABLE_RATE_LOG[address]
            while window and now - window[0] > 300:
                window.popleft()
            if len(window) >= 6:
                self.send_json({"error": "读取尝试过于频繁，请 5 分钟后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            try:
                payload = self.request_json()
                username = str(payload.get("username", "")).strip()[:20]
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            if not username:
                self.send_json({"error": "请输入学号。"}, HTTPStatus.BAD_REQUEST)
                return
            window.append(now)
            try:
                opener = _cas_build_opener()
                _, salt, execution = _cas_open_login_page(opener)
                need_captcha = _cas_need_captcha(opener, username)
                token = secrets.token_urlsafe(24)
                _cas_preflight_store(token, {
                    "opener": opener,
                    "salt": salt,
                    "execution": execution,
                    "username": username,
                    "created": now,
                })
                response = {"ok": True, "token": token, "needCaptcha": need_captcha}
                if need_captcha:
                    response["captchaImage"] = _cas_captcha_dataurl(opener)
            except RuntimeError as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
                return
            except Exception as error:
                traceback.print_exc()
                self.send_json(
                    {"error": "连接统一身份认证失败，请稍后再试。"},
                    HTTPStatus.BAD_GATEWAY,
                )
                return
            self.send_json(response)
            return
        if route == "/api/timetable/sync":
            address = self.client_address[0]
            now = time.time()
            window = TIMETABLE_RATE_LOG[address]
            while window and now - window[0] > 300:
                window.popleft()
            if len(window) >= 6:
                self.send_json({"error": "读取尝试过于频繁，请 5 分钟后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            window.append(now)
            try:
                payload = self.request_json()
                username = str(payload.get("username", "")).strip()[:20]
                password = str(payload.get("password", ""))[:100]
                token = str(payload.get("token", ""))
                captcha = str(payload.get("captcha", "")).strip()[:10]
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            if not username or not password:
                self.send_json({"error": "请输入学号和统一身份认证密码。"}, HTTPStatus.BAD_REQUEST)
                return
            state = _cas_preflight_pop(token)
            if not state or state.get("username") != username:
                self.send_json(
                    {"error": "登录会话已过期，请重新点击「登录」获取新会话。", "expired": True},
                    HTTPStatus.UNAUTHORIZED,
                )
                return
            try:
                opener = state["opener"]
                ok, page = _cas_submit_login(
                    opener, username, password, state["salt"], state["execution"], captcha
                )
                if not ok:
                    # 失败页本身就是新的登录页：取新 salt/execution 存回会话，供验证码重试。
                    retry_salt = _extract_cas_field(page, "pwdEncryptSalt")
                    retry_execution = _extract_cas_field(page, "execution")
                    error_message = _cas_page_error(page)
                    # 失败页存档（不含密码），便于核对 CAS 返回的真实拒绝原因。
                    stamp = _jw_debug_dump([{
                        "tag": "cas-login-fail", "url": "CAS login submit", "method": "POST",
                        "status": "fail", "ctype": "", "final": "",
                        "body": page,
                    }])
                    print(
                        f"[timetable/sync] {username[:4]}*** 登录被拒: {error_message}"
                        + (f" (现场: jw-debug/{stamp})" if stamp else ""),
                        file=sys.stderr,
                    )
                    response = {"error": error_message}
                    if retry_salt and retry_execution:
                        new_token = secrets.token_urlsafe(24)
                        _cas_preflight_store(new_token, {
                            "opener": opener,
                            "salt": retry_salt,
                            "execution": retry_execution,
                            "username": username,
                            "created": time.time(),
                        })
                        response["token"] = new_token
                        response["needCaptcha"] = _cas_need_captcha(opener, username)
                        if response["needCaptcha"]:
                            response["captchaImage"] = _cas_captcha_dataurl(opener)
                    self.send_json(response, HTTPStatus.UNAUTHORIZED)
                    return
                courses, semester = _cas_fetch_schedule(opener)
            except RuntimeError as error:
                self.send_json({"error": str(error)}, HTTPStatus.UNAUTHORIZED)
                return
            except Exception as error:
                traceback.print_exc()
                print(f"[timetable/sync] {username[:4]}*** 读取失败: {error!r}", file=sys.stderr)
                self.send_json(
                    {"error": "连接教务系统失败，请稍后再试；也可以改用文件导入或粘贴文本。"},
                    HTTPStatus.BAD_GATEWAY,
                )
                return
            self.send_json({"ok": True, "courses": courses, "semester": semester})
            return
        if route == "/api/account/register":
            if not self.login_rate_limit_ok():
                self.send_json({"error": "尝试过于频繁，请 5 分钟后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            try:
                payload = self.request_json()
                email = str(payload.get("email", ""))
                password = str(payload.get("password", ""))
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            user_id, error = account_register(email, password)
            if error:
                self.send_json({"error": error}, HTTPStatus.BAD_REQUEST)
                return
            token = account_create_session(user_id)
            self.send_json({"ok": True, "token": token, "email": email.strip().lower()})
            return
        if route == "/api/account/login":
            if not self.login_rate_limit_ok():
                self.send_json({"error": "尝试过于频繁，请 5 分钟后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            try:
                payload = self.request_json()
                email = str(payload.get("email", ""))
                password = str(payload.get("password", ""))
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            user_id, error = account_login(email, password)
            if error:
                self.send_json({"error": error}, HTTPStatus.UNAUTHORIZED)
                return
            token = account_create_session(user_id)
            self.send_json({"ok": True, "token": token, "email": email.strip().lower()})
            return
        if route == "/api/account/logout":
            account_delete_session(self.account_token())
            self.send_json({"ok": True})
            return
        if route == "/api/account/timetable":
            user = account_user_from_token(self.account_token())
            if not user:
                self.send_json({"error": "请先登录。"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self.request_json()
                courses = payload.get("courses")
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(courses, list) or len(courses) > 200:
                self.send_json({"error": "课表数据格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            clean = []
            for row in courses[:200]:
                if not isinstance(row, dict):
                    continue
                try:
                    clean.append({
                        "name": str(row.get("name", ""))[:40],
                        "day": min(max(int(row.get("day", 0)), 1), 7),
                        "p1": min(max(int(row.get("p1", 0)), 1), 12),
                        "p2": min(max(int(row.get("p2", 0)), 1), 12),
                        "loc": str(row.get("loc", ""))[:30],
                        "weeks": row.get("weeks") if isinstance(row.get("weeks"), list) else None,
                        "parity": row.get("parity") if row.get("parity") in ("odd", "even", None) else None,
                    })
                except (ValueError, TypeError):
                    continue
            updated_at = account_save_timetable(user["id"], clean)
            self.send_json({"ok": True, "updated_at": updated_at})
            return
        if route == "/api/account/profile":
            user = account_user_from_token(self.account_token())
            if not user:
                self.send_json({"error": "请先登录。"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self.request_json()
                data = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
            except (ValueError, UnicodeError, json.JSONDecodeError, OverflowError):
                self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(data, dict):
                self.send_json({"error": "资料格式不正确。"}, HTTPStatus.BAD_REQUEST)
                return
            clean = clean_profile(data)
            updated_at = account_save_profile(user["id"], clean)
            self.send_json({"ok": True, "profile": clean, "updated_at": updated_at})
            return
        if route == "/api/account/delete":
            user = account_user_from_token(self.account_token())
            if not user:
                self.send_json({"error": "请先登录。"}, HTTPStatus.UNAUTHORIZED)
                return
            account_delete_user(user["id"])
            self.send_json({"ok": True})
            return
        if route != "/api/ask":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        
        if not self.rate_limit_ok():
            self.send_json({"error": "提问太频繁，请稍后再试。"}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 16_384)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            question = str(payload.get("question", "")).strip()[:500]
            history = payload.get("history", [])[-6:]
        except (ValueError, UnicodeError, json.JSONDecodeError):
            self.send_json({"error": "请求格式不正确。"}, HTTPStatus.BAD_REQUEST)
            return
        if len(question) < 2:
            self.send_json({"error": "请输入更具体的问题。"}, HTTPStatus.BAD_REQUEST)
            return
        api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            self.send_json({"error": "机器人服务尚未配置 API Key。"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return

        selected = retrieve(question)
        context = "\n\n".join(f"【{item['title']}｜{item['source']}】\n{item['text']}" for item in selected)
        if selected:
            system_prompt = (
                "你是厦园新手村的小助手。优先依据下方站点资料回答，并把资料中的信息组织成清晰、简洁、友好的中文。"
                "如果资料没有覆盖用户问题，再使用你的一般知识正常回答，但必须明确说明‘以下为一般性回答，资料库未覆盖该问题’，"
                "不能把一般知识伪装成厦大官方口径。涉及厦门大学的时间、规则、流程、联系方式时，以最新官方通知为准；不要编造。"
                "回复排版要求：不要出现星号字符，不要使用Markdown加粗、斜体、表格或代码围栏；需要列项时使用‘1、’或‘•’，标题单独成行，段落之间空一行，先给结论再给补充说明。"
            )
        else:
            system_prompt = (
                "你是厦园新手村的小助手。当前站点资料库没有检索到与问题直接相关的内容，请使用一般知识正常回答。"
                "回答开头或结尾明确说明‘以下为一般性回答，资料库未覆盖该问题’，不要把一般知识伪装成厦大官方口径。"
                "涉及厦门大学的时间、规则、流程、联系方式时，以最新官方通知为准；不要编造。"
                "回复排版要求：不要出现星号字符，不要使用Markdown加粗、斜体、表格或代码围栏；需要列项时使用‘1、’或‘•’，标题单独成行，段落之间空一行，先给结论再给补充说明。"
            )
        messages = [{
            "role": "system",
            "content": system_prompt
        }]
        for item in history:
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
                messages.append({"role": item["role"], "content": str(item.get("content", ""))[:800]})
        messages.append({
            "role": "user",
            "content": f"站点资料（仅在与问题相关时使用）：\n{context or '未检索到直接相关资料。'}\n\n用户问题：{question}"
        })
        body = json.dumps({
            "model": os.getenv("SILICONFLOW_MODEL", DEFAULT_MODEL),
            "messages": messages,
            "stream": False,
            "max_tokens": 700,
            "temperature": 0.25,
            "enable_thinking": False,
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(API_URL, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }, method="POST")
        try:
            result = None
            last_error = None
            for attempt in range(AI_REQUEST_ATTEMPTS):
                try:
                    with urllib.request.urlopen(request, timeout=50) as response:
                        result = json.loads(response.read().decode("utf-8"))
                    break
                except urllib.error.HTTPError as error:
                    detail = error.read().decode("utf-8", errors="ignore")[:300]
                    print(f"SiliconFlow HTTP {error.code}: {detail}")
                    if error.code not in {429, 500, 502, 503, 504} or attempt == AI_REQUEST_ATTEMPTS - 1:
                        self.send_json({"error": "AI 服务暂时不可用，请稍后再试。"}, HTTPStatus.BAD_GATEWAY)
                        return
                    last_error = error
                except (urllib.error.URLError, TimeoutError) as error:
                    last_error = error
                    print(f"SiliconFlow connection attempt {attempt + 1}/{AI_REQUEST_ATTEMPTS} failed: {error}")
                    if attempt == AI_REQUEST_ATTEMPTS - 1:
                        raise
                if attempt < AI_REQUEST_ATTEMPTS - 1:
                    time.sleep(1.5 * (attempt + 1))
            if result is None:
                raise last_error or RuntimeError("SiliconFlow returned no result")
            answer = format_ai_answer(result["choices"][0]["message"]["content"])
            self.send_json({"answer": answer})
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, TypeError) as error:
            print(f"SiliconFlow error: {error}")
            self.send_json({"error": "AI 服务连接失败，请稍后再试。"}, HTTPStatus.BAD_GATEWAY)

    def do_DELETE(self):
        if self.route() != "/api/admin/materials":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self.require_admin():
            return
        params = parse_qs(urlsplit(self.path).query)
        row = self.get_material(params.get("id", [""])[0])
        if not row:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            if row["storage"] == "local":
                path = self.local_material_path(row["object_key"])
                if path.exists():
                    path.unlink()
            else:
                cos_client().delete_object(Bucket=COS_BUCKET, Key=row["object_key"])
            with material_connection() as connection:
                connection.execute("DELETE FROM materials WHERE id = ?", (row["id"],))
                connection.commit()
        except (OSError, RuntimeError, ValueError) as error:
            self.send_json({"error": str(error) or "删除失败。"}, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json({"ok": True})

    def rate_limit_ok(self):
        address = self.client_address[0]
        now = time.time()
        window = REQUEST_LOG[address]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= 18:
            return False
        window.append(now)
        return True

    def send_redirect(self, location, status=HTTPStatus.TEMPORARY_REDIRECT):
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(self, data, status=HTTPStatus.OK, headers=None):
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--make-password-hash":
        password = getpass.getpass("管理员密码：")
        if not password:
            raise SystemExit("密码不能为空。")
        print(password_hash(password))
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--list-users":
        with account_connection() as connection:
            rows = connection.execute("SELECT id, email, created_at FROM users ORDER BY id").fetchall()
        if not rows:
            print("还没有注册用户。")
        for row in rows:
            print(f"{row['id']}\t{row['email']}\t{row['created_at']}")
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--reset-password":
        if len(sys.argv) < 3:
            raise SystemExit("用法：python3 server.py --reset-password 用户邮箱")
        target_email = sys.argv[2].strip().lower()
        with _ACCOUNT_DB_LOCK, account_connection() as connection:
            row = connection.execute("SELECT id FROM users WHERE email = ?", (target_email,)).fetchone()
        if not row:
            raise SystemExit(f"没有找到邮箱为 {target_email} 的用户。可先执行 --list-users 查看。")
        new_password = getpass.getpass("新密码（至少 8 位，输入不会回显）：")
        if len(new_password) < 8:
            raise SystemExit("密码至少 8 位。")
        confirm = getpass.getpass("再输入一次确认：")
        if new_password != confirm:
            raise SystemExit("两次输入不一致，未做修改。")
        with _ACCOUNT_DB_LOCK, account_connection() as connection:
            connection.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (password_hash(new_password), row["id"]))
            connection.execute("DELETE FROM account_sessions WHERE user_id = ?", (row["id"],))
        print(f"已重置 {target_email} 的密码，该账号的所有登录会话已失效。")
        raise SystemExit(0)
    port = int(os.getenv("PORT", "8080"))
    print(f"Xiayuan Guide serving on 0.0.0.0:{port}; knowledge chunks={len(KNOWLEDGE)}")
    ThreadingHTTPServer(("0.0.0.0", port), XiayuanHandler).serve_forever()
