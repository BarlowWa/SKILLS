#!/usr/bin/env python3
"""fetch.py — 抓取网页/接口并输出内容。

覆盖四类目标:
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

    # 非 UTF-8 文本（--raw 默认逐字节输出，需可读文本时显式指定字符集）
    python fetch.py --raw --encoding gb18030 https://example.com/gb-page

    # 局域网自签证书
    python fetch.py --insecure https://192.168.1.10:8443/page

    # POST JSON 到 API
    python fetch.py --raw --header "Content-Type: application/json" \
        --data '{"q":"x"}' https://api.x.com/search

依赖: 仅标准库 + lxml（仅 HTML 正文提取时用到，--raw 时不需要）。
版本: 需 Python >= 3.10（代码使用了 `str | None` 联合类型语法）。
安全: 只访问 http/https；其它 scheme（file/ftp/data 等）以及重定向到这些
      scheme 的响应一律拒绝，不发起读取。
"""
import argparse
import gzip
import os
import re
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import zlib
from http.cookiejar import MozillaCookieJar
from urllib.parse import urljoin, urlparse

DEFAULT_TIMEOUT = 20
MAX_REDIRECTS = 5
DEFAULT_MAX_CHARS = 60000
# 只允许访问网络资源。file:// / ftp:// / data:// 等会被 urllib 处理器当成
# 本机资源读取（file:// 可读任意本地文件），必须显式拒绝。
ALLOWED_SCHEMES = ("http", "https")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class SchemeNotAllowed(ValueError):
    """URL scheme 不在白名单内。

    用专门类型区分「scheme 不允许」与其它 ValueError：入口校验与重定向校验
    都据此统一返回退出码 2（参数/目标非法），不落进通用的 exit 4 分支。
    """


def check_scheme(url: str) -> None:
    """校验 URL scheme；不允许时抛 SchemeNotAllowed（调用方报参数错误，不发起请求）。"""
    scheme = urlparse(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SchemeNotAllowed(
            f"不支持的 URL scheme: {scheme or '(空)'}；只允许 {'/'.join(ALLOWED_SCHEMES)}"
        )


class _SchemeSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """纵深防御：入口已做 scheme 白名单（check_scheme），本 handler 在重定向时再查一次。

    urllib 的基类 HTTPRedirectHandler 本身会拒绝 file:// / data: 等重定向目标，
    但会放行 ftp:// 这类它支持抓取的 scheme；在这里再拦一道，保证重定向链上
    只出现 ALLOWED_SCHEMES 中的 scheme。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_scheme(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(cookie_jar=None, insecure=False):
    handlers = [
        _SchemeSafeRedirectHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context() if insecure else None),
    ]
    # 注意：必须按 is not None 判断。MozillaCookieJar 定义了 __len__，
    # 空 jar（首次登录时必然为空）的布尔值为 False，用 `if cookie_jar:`
    # 会静默跳过 HTTPCookieProcessor，响应里的 Set-Cookie 全部丢失。
    if cookie_jar is not None:
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
    opener = build_opener(cookie_jar, insecure)
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

    入参 html 必须是**已解码**的文本。不能把它 encode 回字节再交给 lxml：
    lxml 会按页面 `<meta charset=...>` 二次解码，把 UTF-8 字节当成 GB18030，
    导致整个页面变成「锟斤拷」。故这里直接把 str 交给 etree.HTML()
    （lxml 对 str 输入按 Unicode 处理，不再看 meta）。

    但 str 输入**不能带 XML 声明**：XHTML 页面开头的 `<?xml version=...
    encoding=...?>` 会让 lxml 抛 “Unicode strings with encoding declaration
    are not supported”。该声明对已解码文本毫无用处，先剥离再交给 lxml。
    """
    from lxml import etree

    # 只剥离开头（允许前导空白）的 XML 声明；正文中出现同样文本的概率极低
    html = re.sub(r"^\s*<\?xml\b[^>]*\?>", "", html, count=1)

    parser = etree.HTMLParser(recover=True)
    root = etree.HTML(html, parser=parser)
    if root is None:
        raise ValueError("HTML 解析失败（输入为空或无法构建文档树）")

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
    """推断响应字符集：BOM > HTTP 头 > <meta charset> > utf-8。

    优先级按 WHATWG 编码嗅探规范：**传输层声明的字符集优先于页内 meta**。
    两者冲突时以 HTTP 头为准；若反过来先看 meta，服务端错误地声明 utf-8
    而页面里留着旧的 gb18030 meta 时，整页会按错误编码解码成乱码。

    页内 HTML 两种写法都要覆盖：
        <meta charset="gb18030">
        <meta http-equiv="Content-Type" content="text/html; charset=gb18030">
    旧实现只匹配 `charset=` 紧跟字符的写法，带引号的 `<meta charset="...">`
    会漏判并回落到 utf-8，整页变成 U+FFFD。
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    # HTTP 头优先（传输层 > 页内声明）
    m = re.search(r"charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)", content_type or "", re.IGNORECASE)
    if m:
        return m.group(1)
    # 再退回页内 <meta>
    m = re.search(rb"charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)", raw[:4096], re.IGNORECASE)
    if m:
        return m.group(1).decode("ascii", "ignore")
    return "utf-8"


def is_json_content(headers) -> bool:
    ct = (headers.get("Content-Type", "") or "").lower()
    return "json" in ct


def _normalize_curl_cookiefile(path: str) -> str:
    """返回一个可交给 MozillaCookieJar 加载的规范化 cookie 文件路径。

    原有 curl 格式问题（见 _normalize_cookie_text）在**临时副本**里修正，
    本函数（加载阶段）不改写用户原文件；无需修正时直接返回原路径。

    注意作用范围：本函数只保证**加载**不落地写原文件。命令结束时仍会调用
    cj.save()，而 MozillaCookieJar.save() 是**整份重写**（截断后只写 jar 内
    已有的 cookie），会丢掉原文件里的非 cookie 行、并把 expires=0 规范化成
    空字段——这是登录态回写的既定行为，用 curl 复用同一份 jar 时须留意。
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
    except OSError:
        return path
    normalized = _normalize_cookie_text(original)
    if normalized == original:
        return path
    fd, tmp = tempfile.mkstemp(prefix="fetch-page-cookies-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(normalized)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return tmp


def _normalize_cookie_text(text: str) -> str:
    """修正 curl cookie 文件与 Python 的两处格式差异，返回新文本。

    两处 curl 与 Python 的格式差异：
      1. curl 用 "#HttpOnly_" 前缀标记 HttpOnly cookie；Python 标准库其实
         也识别该前缀（MozillaCookieJar._really_load 会剥离），但为稳妥仍统一剥掉。
      2. curl 用 expires=0 表示「session cookie 不过期」；Python 却把 0 当作
         epoch 时间戳 1970-01-01，加载后 add_cookie_header 判定已过期而静默丢弃，
         导致登录态丢失（curl 能 200、Python 却 401 的根因）。
         把 expires=0 改成空字段，Python 会解析为 expires=None + discard=True，
         即真正的 session cookie。
    """
    out = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        # 非注释的 cookie 行：第 5 列（expires）为 "0" 时清空该列
        stripped = line.rstrip("\n")
        if stripped and not stripped.startswith(("#", "$")):
            cols = stripped.split("\t")
            if len(cols) >= 7 and cols[4] == "0":
                cols[4] = ""
                line = "\t".join(cols) + ("\n" if line.endswith("\n") else "")
        out.append(line)
    return "".join(out)


def _non_negative_int(value: str) -> int:
    """argparse 校验：--max-chars 只接受 >= 0（0 表示不限制，负值无意义）。

    负值若放行，截断分支会执行 text[:-1] + "..."，把输出尾部切掉、
    留下一段不完整的 HTML/文本，且 stderr 仍提示「已截断至 -1 字符」。
    """
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"需要整数，收到 {value!r}")
    if n < 0:
        raise argparse.ArgumentTypeError(f"不能为负数，收到 {n}（0 表示不限制）")
    return n


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
    ap.add_argument("--raw", action="store_true",
                    help="逐字节输出原始响应体（API/JSON/任意二进制，不经解码）")
    ap.add_argument("--encoding", default=None,
                    help="显式指定响应字符集（如 gb18030）。--raw 时取代逐字节输出；"
                         "正文提取时覆盖自动探测")
    ap.add_argument("--method", default="GET", help="HTTP 方法 (GET/POST/PUT/DELETE...)")
    ap.add_argument("--data", default=None, help="请求体（POST 等），字符串直接使用")
    ap.add_argument("--header", action="append", default=[], help="自定义请求头，可重复，格式 'Name: value'")
    ap.add_argument("--referer", default=None, help="设置 Referer 请求头（部分系统如 Confluence/Seraph 校验来源页，缺少会被 401）")
    ap.add_argument("--cookie-jar", default=None,
                    help="cookie 文件路径，用于持久化登录态（读取时用规范化临时副本、不改写原文件；"
                         "抓到响应后会把新 cookie 整份重写回原 jar——原文件的非 cookie 行会丢失）")
    ap.add_argument("--insecure", action="store_true", help="跳过 TLS 证书校验（自签证书）")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--max-chars", type=_non_negative_int, default=DEFAULT_MAX_CHARS,
                    help=f"输出字符数上限，超出则截断并提示（默认 {DEFAULT_MAX_CHARS}；0 表示不限制）")
    args = ap.parse_args(argv)

    if args.encoding and not args.raw:
        print("[info] --encoding 将用于指定响应字符集（覆盖自动探测）", file=sys.stderr)

    # scheme 白名单：file:// 等可读本机资源，必须在发起请求前拒绝
    try:
        check_scheme(args.url)
    except ValueError as e:
        sys.stderr.write(f"[error] {e}\n")
        return 2

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
        cookie_load_path = args.cookie_jar
        try:
            # curl 生成的 cookie 文件与 Python 有两处格式差异（前缀、expires=0），
            # 直接加载会导致 session cookie 无法发送。规范化写进临时副本，
            # 只在整理阶段落地；**命令结束时 cj.save() 仍会整份重写原 jar**
            # （见下方保存段：那是唯一一次写原文件，加载阶段不改写它）。
            cookie_load_path = _normalize_curl_cookiefile(args.cookie_jar)
            cj.load(cookie_load_path, ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass
        finally:
            if cookie_load_path != args.cookie_jar:
                try:
                    os.unlink(cookie_load_path)
                except OSError:
                    pass

    try:
        body, final_url, resp_headers = fetch(
            args.url, method=args.method, data=data, headers=headers,
            cookie_jar=cj, insecure=args.insecure, timeout=args.timeout,
        )
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[error] HTTP {e.code} {e.reason}\n")
        return 2
    except SchemeNotAllowed as e:
        # 入口校验与重定向校验统一语义：scheme 不允许 → 退出码 2
        # （默认 opener 自己的 scheme 校验抛 HTTPError，落到上面的 exit 2；
        #  本 handler 在重定向链上抛出的是下面的自定义异常，统一到 2）。
        sys.stderr.write(f"[error] {e}\n")
        return 2
    except urllib.error.URLError as e:
        sys.stderr.write(f"[error] {e.reason}\n")
        return 3
    except Exception as e:
        sys.stderr.write(f"[error] {e}\n")
        return 4

    # 保存 cookie（登录后回写）。注意：cj.save() **整份重写** jar 文件
    # （截断后只写 jar 内已有的 cookie，并非「保留原有条目并追加」）：
    # 原文件中的非 cookie 行会丢失、expires=0 会被规范化成空字段。
    # 这是登录态复用的既定行为；只想读 cookie 时不要期望原文件保持不变。
    # 上面的临时副本只用于**加载**阶段，不影响这里的回写。
    if cj is not None:
        try:
            cj.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass

    # 原始输出（API / JSON / 显式 --raw）
    if args.raw or is_json_content(resp_headers):
        if args.encoding:
            # --encoding：按用户指定字符集解码为文本再输出
            try:
                out = body.decode(args.encoding, "replace")
            except LookupError:
                sys.stderr.write(f"[error] 未知编码: {args.encoding}\n")
                return 2
            if args.max_chars and len(out) > args.max_chars:
                total = len(out)
                omitted = total - args.max_chars
                sys.stderr.write(f"[warn] 已截断至 {args.max_chars} 字符（原始 {total}）\n")
                out = out[: args.max_chars] + f"\n\n... [truncated, {omitted} chars omitted]"
            sys.stdout.write(out)
            return 0
        if not args.raw:
            # JSON 自动直出：仍是文本路径，**要**遵守 --max-chars。
            # 只有显式 --raw 才逐字节、不截断（二进制无法按字符截断）；
            # 曾因 json 与 --raw 共用同一分支导致 --max-chars 被静默忽略。
            out = body.decode("utf-8", "replace")
            if args.max_chars and len(out) > args.max_chars:
                total = len(out)
                omitted = total - args.max_chars
                sys.stderr.write(f"[warn] 已截断至 {args.max_chars} 字符（原始 {total}）\n")
                out = out[: args.max_chars] + f"\n\n... [truncated, {omitted} chars omitted]"
            sys.stdout.write(out)
            return 0
        # 显式 --raw：逐字节输出，二进制无损、不受 --max-chars 限制。
        # 若响应看起来是文本，提示可用 --encoding 走可读文本路径。
        if (resp_headers.get("Content-Type", "") or "").lower().startswith("text/"):
            sys.stderr.write(
                "[info] --raw 已逐字节输出响应体。若中文等非 ASCII 文本显示为乱码，"
                "请加 --encoding <字符集>（如 gb18030）。\n"
            )
        sys.stdout.flush()
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
        return 0

    # HTML 正文提取
    charset = args.encoding or detect_charset(body, resp_headers.get("Content-Type", ""))
    try:
        text_html = body.decode(charset, "replace")
    except LookupError:
        # 低于标准的别名（如 <meta charset="x-gbk">）会让 codecs 抛 LookupError。
        # 回落到 utf-8 而不是报错退出：保留「拿到含替换字符的内容」这一可用退路，
        # 并提示可用 --encoding 指定正确字符集。显式 --encoding 打错时仍报错（见上）。
        sys.stderr.write(
            f"[warn] 未知字符集 {charset!r}，已回落 utf-8 解码；"
            f"若中文乱码请用 --encoding <字符集> 指定\n"
        )
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
