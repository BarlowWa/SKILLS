#!/usr/bin/env python3
"""fetch.py — 抓取网页/接口并输出内容。

覆盖三类目标:
    1. 公开网页    -> 提取干净正文（标题 + 段落）
    2. 登录页      -> --cookie-jar 持久化 session，--data/--method 支持登录 POST
    3. 局域网服务器 -> --insecure 跳过自签证书校验；HTTP 直接可用
    4. API 接口    -> --raw 输出原始响应（JSON 等），或按 Content-Type 自动直出

用法:
    # 公开文章
    python fetch.py https://example.com/article

    # 登录后抓取（先登录存 cookie，再用同一 jar 抓）
    python fetch.py --cookie-jar /tmp/session.txt --data "user=a&pass=b" https://x.com/login
    python fetch.py --cookie-jar /tmp/session.txt https://x.com/dashboard

    # 带 token 的 API
    python fetch.py --raw --header "Authorization: Bearer TOKEN" https://api.x.com/v1/data

    # 局域网自签证书
    python fetch.py --insecure https://192.168.1.10:8443/page

    # POST JSON 到 API
    python fetch.py --raw --header "Content-Type: application/json" \
        --data '{"q":"x"}' https://api.x.com/search

依赖: 仅标准库 + lxml（仅 HTML 正文提取时用到，--raw 时不需要）。
"""
import argparse
import gzip
import io
import re
import ssl
import sys
import urllib.error
import urllib.request
import zlib
from http.cookiejar import MozillaCookieJar
from urllib.parse import urljoin

DEFAULT_TIMEOUT = 20
MAX_REDIRECTS = 5
DEFAULT_MAX_CHARS = 60000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def build_opener(cookie_jar=None, insecure=False, timeout=DEFAULT_TIMEOUT):
    handlers = [
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context() if insecure else None),
    ]
    if cookie_jar:
        handlers.insert(0, urllib.request.HTTPCookieProcessor(cookie_jar))
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Encoding", "gzip, deflate"),
        ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
    ]
    return opener


def fetch(url, method="GET", data=None, headers=None, cookie_jar=None,
          insecure=False, timeout=DEFAULT_TIMEOUT):
    opener = build_opener(cookie_jar, insecure, timeout)
    req = urllib.request.Request(url, method=method, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    resp = opener.open(req, timeout=timeout)
    body = resp.read()
    return decode_body(body, resp.headers.get("Content-Encoding", "")), resp.geturl(), resp.headers


def decode_body(data: bytes, content_encoding: str) -> bytes:
    enc = (content_encoding or "").lower()
    try:
        if "gzip" in enc:
            return gzip.decompress(data)
        if "deflate" in enc:
            try:
                return zlib.decompress(data)
            except zlib.error:
                return zlib.decompress(data, -zlib.MAX_WBITS)
    except Exception:
        pass
    # 兜底：部分网关/反代不回 Content-Encoding 头，但响应体确实是 gzip。
    # 不解压会输出压缩字节（满屏乱码），故按魔数嗅探再试一次。
    if not enc and len(data) > 2 and data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except Exception:
            pass
    return data


HTML_ENTITIES = {
    "&nbsp;": " ", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&#39;": "'", "&apos;": "'", "&amp;": "&",
}


def unescape(text: str) -> str:
    """反转义常见 HTML 实体。

    lxml 的 itertext() 返回的是未反转义的原始文本，不去转义会把
    `&amp;` `&lt;` 原样喂给模型，读起来像乱码。数字实体用正则补。
    """
    if "&" not in text:
        return text
    for k, v in HTML_ENTITIES.items():
        text = text.replace(k, v)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    return text


# 空元素/无语义元素：跳过自身但继续下钻子节点
_SKIP_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "canvas", "template",
    "head", "meta", "link", "title", "option", "source", "track", "map",
    "area", "object", "embed", "param", "col", "colgroup",
}
# 行内元素：文本与子节点同处一行，不换行
_INLINE_TAGS = {
    "a", "span", "b", "strong", "i", "em", "u", "code", "small", "big",
    "sub", "sup", "mark", "abbr", "cite", "q", "time", "label", "button",
    "kbd", "samp", "var", "s", "del", "ins", "font", "bdi", "bdo", "ruby",
    "wbr", "data", "dfn",
}
# 块级元素：文本单独成段
_BLOCK_TAGS = {
    "p", "li", "pre", "blockquote", "td", "th", "dt", "dd", "figcaption",
    "caption", "summary", "legend", "address",
}
# 标题元素：成段并加 Markdown 标记
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def to_text(html: str, base_url: str, selector: str | None = None) -> str:
    """把 HTML 提取为 Markdown 风格纯文本。

    模型：每个块级元素独立产出一个段落；行内元素只在段内拼接、不换行。
    这样既避免「一个 <p> 被 span/b 切成多行」，也保证相邻段落不会粘连。
    """
    from lxml import etree

    parser = etree.HTMLParser(recover=True)
    tree = etree.parse(io.BytesIO(html.encode("utf-8")), parser)
    root = tree.getroot()

    # 先取 <title>（_SKIP_TAGS 稍后会删除 title 元素，须在此之前读取）
    title = ""
    t = root.xpath("//title/text()")
    if t:
        title = unescape(t[0].strip())

    for tag in _SKIP_TAGS:
        for el in root.iter(tag):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    pending_title = re.sub(r"\s+", " ", title).strip().lower() if title else None

    blocks = []

    def add(block: str):
        """追加一个段落；与 <title> 重复的首个标题会被丢弃。"""
        nonlocal pending_title
        block = re.sub(r"[ \t]{2,}", " ", unescape(block)).strip()
        if not block:
            return
        if pending_title is not None:
            probe = re.sub(r"[\s#]+", " ", block).strip().lower()
            if probe == pending_title:
                pending_title = None
                return
            pending_title = None
        blocks.append(block)

    def inline_text(node) -> str:
        """递归拼接行内子树为一个字符串，不换行。

        返回 **含自身 tail** 的完整文本。调用方一律直接追加返回值，
        不得再单独拼 child.tail，否则会重复。
        """
        if not isinstance(node.tag, str):
            return node.tail or ""
        tag = node.tag.lower()
        # 自闭合/无文本元素：给出替代文本后必须接上自己的 tail，
        # 否则紧随其后的文本（如 <p>a<br>b</p> 里的 b）会整段丢失。
        if tag == "br":
            return "\n" + (node.tail or "")
        if tag == "img":
            alt = node.get("alt", "").strip()
            return (f"![{unescape(alt)}]" if alt else "") + (node.tail or "")
        if tag == "a":
            href = node.get("href", "")
            text = inline_children(node)
            if href and text:
                return f"[{text}]({urljoin(base_url, href)})" + (node.tail or "")
            return (text or "") + (node.tail or "")
        return inline_children(node) + (node.tail or "")

    def inline_children(node) -> str:
        """拼接子节点：每个子节点连同其 tail 一并追加（tail 已含在 child 的返回值里）。"""
        parts = [node.text or ""]
        for child in node:
            parts.append(inline_text(child))
        return "".join(parts)

    def walk(node):
        """块级遍历：每个块级元素产出一个（或多个）段落。"""
        if not isinstance(node.tag, str):
            # 注释/处理指令节点：跳过节点本身，但保留 tail 以免丢文本
            tail = (node.tail or "").strip()
            if tail:
                blocks.append(unescape(tail))
            return
        tag = node.tag.lower()
        if tag in _SKIP_TAGS:
            return
        if tag == "br":
            return  # 段内换行交给 inline_text 处理
        if tag in _HEADING_TAGS:
            add("## " + inline_children(node))
            return
        if tag in _BLOCK_TAGS or tag in ("a", "img"):
            # 块级文本单元；段内 <br> 会拆成多个段落
            for piece in inline_text(node).split("\n"):
                add(piece)
            return
        # 容器（div/section/body/table/ul/...）：继续下钻
        for child in node:
            walk(child)

    scope = root
    if selector:
        try:
            found = root.cssselect(selector)
        except Exception as e:
            print(f"[warn] selector 不支持（lxml 未装 cssselect？）: {e}", file=sys.stderr)
            found = []
        if found:
            scope = found[0]
        else:
            print(f"[warn] selector 未命中: {selector}，已回退为全文提取", file=sys.stderr)

    for child in scope:
        walk(child)

    text = "\n\n".join(blocks)
    for ch in (" ", "​", "﻿"):
        text = text.replace(ch, " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    out = []
    if title:
        out.append(f"# {title}")
        out.append("")
    out.append(text)
    return "\n".join(out).strip()


def detect_charset(raw: bytes, content_type: str) -> str:
    m = re.search(rb"charset=([A-Za-z0-9._-]+)", raw[:4096])
    if m:
        return m.group(1).decode("ascii", "ignore")
    m = re.search(r"charset=([A-Za-z0-9._-]+)", content_type or "")
    if m:
        return m.group(1)
    return "utf-8"


def is_json_content(headers) -> bool:
    ct = (headers.get("Content-Type", "") or "").lower()
    return "json" in ct


def _normalize_curl_cookiefile(path: str) -> None:
    """就地改写 curl 生成的 Netscape cookie 文件，使 Python 能正确发送 cookie。

    两处 curl 与 Python 的格式差异：
      1. curl 用 "#HttpOnly_" 前缀标记 HttpOnly cookie；Python 标准库其实
         也识别该前缀（MozillaCookieJar._really_load 会剥离），但为稳妥仍统一剥掉。
      2. curl 用 expires=0 表示「session cookie 不过期」；Python 却把 0 当作
         epoch 时间戳 1970-01-01，加载后 add_cookie_header 判定已过期而静默丢弃，
         导致登录态丢失（curl 能 200、Python 却 401 的根因）。
         把 expires=0 改成空字段，Python 会解析为 expires=None + discard=True，
         即真正的 session cookie。
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return
    changed = False
    out = []
    for line in lines:
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
            changed = True
        # 非注释的 cookie 行：第 5 列（expires）为 "0" 时清空该列
        stripped = line.rstrip("\n")
        if stripped and not stripped.startswith(("#", "$")):
            cols = stripped.split("\t")
            if len(cols) >= 7 and cols[4] == "0":
                cols[4] = ""
                line = "\t".join(cols) + ("\n" if line.endswith("\n") else "")
                changed = True
        out.append(line)
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(out)


def main(argv):
    # Windows 下 stdout 默认 GBK，遇中文会 UnicodeEncodeError，强制 UTF-8
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="抓取网页/接口并输出内容")
    ap.add_argument("url")
    ap.add_argument("--selector", default=None, help="CSS 选择器，限定 HTML 正文范围")
    ap.add_argument("--raw", action="store_true", help="输出原始响应体（API/JSON/任意二进制）")
    ap.add_argument("--method", default="GET", help="HTTP 方法 (GET/POST/PUT/DELETE...)")
    ap.add_argument("--data", default=None, help="请求体（POST 等），字符串直接使用")
    ap.add_argument("--header", action="append", default=[], help="自定义请求头，可重复，格式 'Name: value'")
    ap.add_argument("--referer", default=None, help="设置 Referer 请求头（部分系统如 Confluence/Seraph 校验来源页，缺少会被 401）")
    ap.add_argument("--cookie-jar", default=None, help="cookie 文件路径，用于持久化登录态")
    ap.add_argument("--insecure", action="store_true", help="跳过 TLS 证书校验（自签证书）")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                    help=f"输出字符数上限，超出则截断并提示（默认 {DEFAULT_MAX_CHARS}；0 表示不限制）")
    args = ap.parse_args(argv)

    # 解析请求头
    headers = {}
    for h in args.header:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    if args.referer:
        headers.setdefault("Referer", args.referer)

    # 数据编码
    data = None
    if args.data is not None:
        data = args.data.encode("utf-8")

    # cookie jar
    cj = None
    if args.cookie_jar:
        cj = MozillaCookieJar(args.cookie_jar)
        try:
            # curl 生成的 cookie 文件与 Python 有两处格式差异（前缀、expires=0），
            # 直接加载会导致 session cookie 无法发送。先就地规范化再加载。
            _normalize_curl_cookiefile(args.cookie_jar)
            cj.load(ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass

    try:
        body, final_url, resp_headers = fetch(
            args.url, method=args.method, data=data, headers=headers,
            cookie_jar=cj, insecure=args.insecure, timeout=args.timeout,
        )
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[error] HTTP {e.code} {e.reason}\n")
        return 2
    except urllib.error.URLError as e:
        sys.stderr.write(f"[error] {e.reason}\n")
        return 3
    except Exception as e:
        sys.stderr.write(f"[error] {e}\n")
        return 4

    # 保存 cookie（登录后回写）
    if cj is not None:
        try:
            cj.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass

    # 原始输出（API / JSON / 显式 --raw）
    if args.raw or is_json_content(resp_headers):
        out = body.decode("utf-8", "replace")
        if args.max_chars and len(out) > args.max_chars:
            total = len(out)
            omitted = total - args.max_chars
            sys.stderr.write(f"[warn] 已截断至 {args.max_chars} 字符（原始 {total}）\n")
            out = out[: args.max_chars] + f"\n\n... [truncated, {omitted} chars omitted]"
        sys.stdout.write(out)
        return 0

    # HTML 正文提取
    charset = detect_charset(body, resp_headers.get("Content-Type", ""))
    try:
        text_html = body.decode(charset, "replace")
    except LookupError:
        text_html = body.decode("utf-8", "replace")

    try:
        result = to_text(text_html, final_url, args.selector)
    except Exception as e:
        sys.stderr.write(f"[error] 解析失败: {e}\n")
        return 5

    # 空正文诊断：JS 渲染 / 反爬 / 选择器失配都会走到这里，
    # 静默返回空输出会让使用者无从判断，故显式提示。
    if len(result.strip()) < 200:
        sys.stderr.write(
            "[warn] 正文几乎为空（提取到 %d 字符）。常见原因：\n"
            "       1) 页面靠 JS 渲染（SPA），静态 HTML 里没有正文 —— 试 --raw 看原始响应\n"
            "       2) 需要登录态 —— 试 --cookie-jar\n"
            "       3) 反爬拦截（返回验证页）—— 检查上方 HTTP 状态与 --raw 内容\n"
            "       4) 正文在非默认容器内 —— 试 --selector 指定范围\n"
            % len(result.strip())
        )

    if args.max_chars and len(result) > args.max_chars:
        total = len(result)
        omitted = total - args.max_chars
        sys.stderr.write(f"[warn] 已截断至 {args.max_chars} 字符（原始 {total}）\n")
        result = result[: args.max_chars] + f"\n\n... [truncated, {omitted} chars omitted]"

    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
