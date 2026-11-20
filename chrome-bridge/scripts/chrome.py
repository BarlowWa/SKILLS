#!/usr/bin/env python3
"""chrome-bridge —— 真浏览器抓取（含登录闸门），供 Claude Code 以命令行方式调用。

设计要点（全部来自本机实测，2026-11-11）：
  * 不用常驻进程：Chrome 冷启动仅 ~0.5-0.8s，<profile>/DevToolsActivePort 文件就是单例发现机制。
  * 每次调用 attach-or-launch：端口文件在且 /json/version 通 → 附着；否则冷启动。
  * 浏览器跨调用常驻，登录态活在 profile 里（不在本进程里）。
  * **必须优雅关闭**（Browser.close）：kill() 会导致 cookie/localStorage 全丢（已实测对照）。
  * headless 即可完成扫码登录：把登录页截图回传给模型，用户扫码，轮询判定登录成功。

技能边界：只解决 fetch.py 解决不了的三类 —— JS 渲染 / 需要登录 / 反爬风控。
拿到的 cookie 交给 fetch.py --header 接力，后续轻量抓取不必再开浏览器。
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

IS_WINDOWS = os.name == "nt"
try:
    import fcntl  # POSIX
except ImportError:  # Windows
    fcntl = None

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("USERPROFILE", ""), r"AppData\Local\Google\Chrome\Application\chrome.exe"),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

DEFAULT_PROFILE = Path(os.environ.get("CHROME_BRIDGE_PROFILE", "") or
                       (Path.home() / ".claude" / "chrome-bridge" / "profile"))

DEFAULT_TIMEOUT = 30
DEFAULT_LOGIN_TIMEOUT = 300
COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")

# Windows 上 Python 的 stdout 默认是 GBK(strict)：页面正文一旦含 emoji / CJK 扩展区字符，
# print 会抛 UnicodeEncodeError 导致整条命令失败且零输出。脚本必须在默认环境可用，
# 不能要求使用者先设 PYTHONIOENCODING。统一改成 UTF-8 + replace。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


# ----------------------------------------------------------------------------- 基础工具

def die(msg: str, code: int = 1) -> "NoReturn":
    print(f"[chrome-bridge] {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg: str) -> None:
    print(f"[chrome-bridge] {msg}", file=sys.stderr)


def find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    die("找不到 chrome.exe；可用 CHROME_BRIDGE_CHROME 指定路径")


def profile_dir(args) -> Path:
    """profile 目录一律转成**绝对路径**。

    不能用相对路径：Chrome 以自己的 cwd 解析 `--user-data-dir`（Windows 上通常是安装目录），
    而 `_wait_port` 用本进程 cwd 找 `DevToolsActivePort` —— 两边对不上就会稳定超时 30s，
    并在别处留下一个无人认领的 Chrome。实测：`--profile tests/.work/x` 必失败，
    `--profile <绝对路径>` 正常。
    """
    p = Path(args.profile).expanduser() if getattr(args, "profile", None) else DEFAULT_PROFILE
    p = p.expanduser().absolute()
    p.mkdir(parents=True, exist_ok=True)
    return p


def devtools_port_file(prof: Path) -> Path:
    return prof / "DevToolsActivePort"


def read_devtools_port(prof: Path) -> int | None:
    f = devtools_port_file(prof)
    try:
        first = (f.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0].strip()
        return int(first) if first.isdigit() else None
    except (OSError, ValueError, IndexError):
        return None


def devtools_ws_path(prof: Path) -> str | None:
    """DevToolsActivePort 第 2 行是 browser 级 ws 路径（如 /devtools/browser/uuid）。
    拿不到时退化为按端口猜。"""
    f = devtools_port_file(prof)
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > 1 and lines[1].strip().startswith("/"):
            return lines[1].strip()
    except OSError:
        pass
    return None


def port_alive(port: int | None, timeout: float = 1.5) -> bool:
    if not port:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


# ----------------------------------------------------------------------------- 单例锁

class ProfileLock:
    """同一个 profile 同时只能有一个 bridge 在操作浏览器。"""

    def __init__(self, prof: Path):
        self.path = prof / ".bridge.lock"
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            if IS_WINDOWS:
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            die("另一个 chrome-bridge 正在使用该 profile（可能正在登录授权），请稍后再试或指定 --profile")
        return self

    def __exit__(self, *exc):
        try:
            if IS_WINDOWS:
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            self.fh.close()


# ----------------------------------------------------------------------------- 最小 WebSocket（RFC 6455，仅客户端，够连 CDP 用）

class WSClosed(Exception):
    pass


class WSClient:
    """只实现 CDP 需要的那部分：客户端握手、发送 masked 文本帧、接收分片文本帧。
    CDP 消息通常在几 KB 到几百 KB（截图 base64 可达 1MB+），必须支持分片与 64 位长度。
    """

    def __init__(self, url: str, timeout: float = 90.0):
        m = re.match(r"^ws://([^/:]+|\[[^\]]+\])(?::(\d+))?(/.*)$", url)
        if not m:
            raise ValueError(f"不支持的 WebSocket URL: {url}")
        host, port, path = m.group(1).strip("[]"), int(m.group(2) or 80), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        # 读到 \r\n\r\n 为止
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WSClosed("握手期间连接被关闭")
            head += chunk
        head, self._buf = head.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if " 101 " not in status:
            raise WSClosed(f"WebSocket 握手失败: {status}")

    # -- 发送 --

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        self._send_frame(0x1, payload)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    # -- 接收 --

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self._buf)))
            if not chunk:
                raise WSClosed("连接已关闭")
            self._buf += chunk
        if n == 0:
            return b""
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv_text(self, timeout: float | None = None) -> str:
        """读一条完整文本消息（自动拼接分片）。timeout=None 用 socket 默认超时。

        注意：一旦收到帧头，就会**阻塞读完整帧**（后续读不再受本次 timeout 约束）。
        这样短超时的 pump() 只可能在**帧边界**退出，不会停在半帧上把流读乱；
        大消息（如 900KB 截图）途中临时挂起时，这个超时也可能被拉长——这是刻意取舍。
        """
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            while True:
                b1, b2 = self._recv_exact(2)
                if timeout is not None:
                    self.sock.settimeout(None)  # 帧已开始，读完整帧前不再超时
                fin = b1 & 0x80
                opcode = b1 & 0x0F
                n = b2 & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self._recv_exact(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._recv_exact(8))[0]
                payload = self._recv_exact(n) if n else b""
                if opcode == 0x8:           # close
                    raise WSClosed("收到 close 帧")
                if opcode == 0x9:           # ping → pong
                    self._send_frame(0xA, payload)
                    continue
                if opcode == 0xA:           # pong
                    continue
                frame = payload
                while not fin:              # 连续帧
                    b1, b2 = self._recv_exact(2)
                    fin = b1 & 0x80
                    op = b1 & 0x0F
                    n = b2 & 0x7F
                    if n == 126:
                        n = struct.unpack(">H", self._recv_exact(2))[0]
                    elif n == 127:
                        n = struct.unpack(">Q", self._recv_exact(8))[0]
                    chunk = self._recv_exact(n) if n else b""
                    if op == 0x9:           # 分片间夹的 ping
                        self._send_frame(0xA, chunk)
                        continue
                    if op in (0x8, 0xA):
                        continue
                    frame += chunk
                return frame.decode("utf-8", errors="replace")
        except socket.timeout:
            # 只可能在「等下一帧的帧头」时发生，缓冲区里没有半帧 —— 流仍然同步
            raise
        finally:
            if timeout is not None:
                try:
                    self.sock.settimeout(90)
                except OSError:
                    pass

    def can_read(self) -> bool:
        """非阻塞探测：socket 上是否已有可读数据（帧边界）。"""
        import select
        try:
            r, _, _ = select.select([self.sock], [], [], 0)
            return bool(r)
        except (OSError, ValueError):
            return True  # 出错时交给 recv 去抛

    def read_buffered(self) -> bool:
        return bool(self._buf)

    def settimeout(self, t):
        self.sock.settimeout(t)

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------- CDP 客户端

class CDP:
    # 只保留真正需要的页面事件；网络事件只维护「在途请求」状态，不进事件桶
    INTERESTING_EVENTS = {"Page.loadEventFired", "Page.frameNavigated"}

    def __init__(self, ws_url: str):
        self.ws = WSClient(ws_url, timeout=90)
        self._id = 0
        self._events: dict[str, list] = {}
        # 在途请求状态独立于事件桶：事件桶有 64 条上限，丢弃事件会让计数卡死
        self.network_in_flight: set[str] = set()
        self.network_last_activity: float = 0.0

    def _on_event(self, msg: dict) -> None:
        name = msg.get("method")
        params = msg.get("params") or {}
        if name == "Network.requestWillBeSent":
            rid = params.get("requestId")
            if rid:
                self.network_in_flight.add(rid)
            self.network_last_activity = time.monotonic()
        elif name in ("Network.loadingFinished", "Network.loadingFailed"):
            rid = params.get("requestId")
            if rid:
                self.network_in_flight.discard(rid)
            self.network_last_activity = time.monotonic()
        if name in self.INTERESTING_EVENTS:
            bucket = self._events.setdefault(name, [])
            bucket.append(params)
            if len(bucket) > 64:  # 兜底上限，防止极端情况下堆积
                del bucket[:32]

    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send_text(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 90
        self.ws.settimeout(90)
        while time.monotonic() < deadline:
            msg = json.loads(self.ws.recv_text())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} 失败: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self._on_event(msg)
        raise TimeoutError(f"CDP {method} 超时")

    def pump(self, timeout: float = 0.05) -> None:
        """在等待期间把事件读进来。只在帧边界读：没有可读数据就直接返回，不设短超时。"""
        if not (self.ws.read_buffered() or self.ws.can_read()):
            return
        try:
            text = self.ws.recv_text()
        except WSClosed:
            raise
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if "method" in msg:
            self._on_event(msg)

    def events(self, name: str) -> list:
        return self._events.pop(name, [])

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def http_json(port: int, path: str, method: str = "GET") -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            # /json/close 等端点返回纯文本（如 "Target is closing"），不是 JSON
            return {"_text": raw.decode("utf-8", errors="replace").strip()}


# ----------------------------------------------------------------------------- 浏览器会话

ANTIBOT_PATTERNS = [
    ("just a moment", "Cloudflare 人机验证"),
    ("attention required", "Cloudflare 拦截"),
    ("enable javascript and cookies to continue", "Cloudflare JS 挑战"),
    ("verify you are human", "人机验证"),
    ("unusual traffic", "Google 异常流量拦截"),
    ("访问验证", "访问验证"),
    ("安全验证", "安全验证"),
    ("滑动验证", "滑块验证"),
    ("请完成验证", "人机验证"),
]


class Session:
    """一次命令生命周期内与浏览器的连接。"""

    def __init__(self, prof: Path, headless: bool, port: int, cdp: CDP, target_id: str, launched: bool):
        self.prof = prof
        self.headless = headless
        self.port = port
        self.cdp = cdp
        self.target_id = target_id
        self.launched = launched  # 本进程是否是新起的浏览器（退出时是否负责关）

    # -- 生命周期 --

    def close_target(self) -> None:
        try:
            http_json(self.port, f"/json/close/{self.target_id}")
        except Exception:
            pass
        self.cdp.close()

    def close_browser(self) -> None:
        """优雅关闭整个浏览器 —— 必须走 CDP Browser.close，不能用 kill。"""
        try:
            self.cdp.send("Browser.close")
        except Exception:
            pass
        self.cdp.close()


# 不允许经 `--chrome-arg` 生效的 flag：它们是本技能安全边界的前提（见 SKILL.md「安全边界」）。
# 只挡「会覆盖/越界」的形态，正常调优 flag（--proxy-server 等）照常透传。
_FORBIDDEN_CHROME_ARGS = {
    "--user-data-dir": "会覆盖专用 profile，使登录态泄漏到日常 Chrome 或反之",
    "--remote-debugging-address": "会把调试端口暴露到 loopback 之外（局域网可接管浏览器）",
}


def _check_extra_args(extra_args: list[str]) -> None:
    """在启动前拒绝危险 flag —— 安全边界必须落在代码里，不能只写在文档里。

    只做前缀匹配：`--user-data-dir=/x`、`--user-data-dir /x`、`--remote-debugging-address=0.0.0.0`
    都会被拦下；`--disable-features` 仅在显式带 `DevToolsDebuggingRestrictions` 时拦
    （否则会误伤正常用 `--disable-features=A,B` 调优的场景）。
    """
    for raw in extra_args:
        a = (raw or "").strip()
        if not a:
            continue
        name = a.split("=", 1)[0]
        # `--user-data-dir /x` 这种「空格分参数」的写法：name 就是完整的 --user-data-dir
        if name in _FORBIDDEN_CHROME_ARGS and name != "--disable-features":
            die(f"--chrome-arg 禁止传 {name}：{_FORBIDDEN_CHROME_ARGS[name]}", code=4)
        # `--disable-features` 只有在显式带 DevToolsDebuggingRestrictions 时才拦——
        # 正常的 `--disable-features=A,B` 调优不该被误伤。
        if name == "--disable-features" and "DevToolsDebuggingRestrictions" in a:
            die(f"--chrome-arg 禁止传 --disable-features=DevToolsDebuggingRestrictions："
                f"等于让任意进程接管浏览器调试口", code=4)


def _launch_chrome(chrome: str, prof: Path, headless: bool, extra_args: list[str]) -> "subprocess.Popen":
    _check_extra_args(extra_args)
    port_file = devtools_port_file(prof)
    try:
        port_file.unlink()
    except OSError:
        pass
    args = [
        chrome,
        # 调试端口只绑 loopback。不依赖 Chrome 的默认绑定——显式写死，
        # 这样「边界在代码里」可被机械核对，而不是靠 Chromium 某版本的默认行为。
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0",
        f"--user-data-dir={prof}",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-crash-restore-bubble",
        "--disable-gpu",
        "--window-size=1440,900",
    ]
    if headless:
        args.append("--headless=new")
    args += extra_args
    args.append("about:blank")
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if IS_WINDOWS:
        # 独立进程组：父进程退出后浏览器继续活着（登录态要跨调用保持）
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(args, **kwargs)


def _wait_port(prof: Path, timeout: float = 30.0, proc: "subprocess.Popen | None" = None) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        p = read_devtools_port(prof)
        if p and port_alive(p):
            return p
        time.sleep(0.05)
    # 启动失败必须回收刚拉起的子进程：它是 DETACHED 的，不 kill 就成孤儿——
    # 持着 profile 锁、占着 profile 目录，下一次启动会继续失败（实测：僵尸 Chrome
    # 锁住 tests/.work/<profile>/OptimizationGuideModelsManifest，目录删不掉）。
    if proc is not None and proc.poll() is None:
        try:
            if IS_WINDOWS:
                proc.kill()          # DETACHED_PROCESS 下 Popen.kill() 走 TerminateProcess
            else:
                proc.terminate()
            proc.wait(timeout=5)
            log("启动超时，已回收刚拉起的 Chrome 进程")
        except Exception as e:
            log(f"启动超时想回收 Chrome 但失败：{type(e).__name__}: {e}")
    die(f"Chrome 启动超时（{timeout}s）：未在 {devtools_port_file(prof)} 拿到可用端口")


def ensure_session(args, headless: bool | None = None, force_headful: bool = False) -> Session:
    """附着到已在跑的浏览器；没有就冷启动一个。

    注意：已有一个 headless 浏览器在跑时，即使调用方要 headful 也只能附着
    （同一个 profile 不能开第二个实例）。login 命令靠 headless 截图即可，不受影响。

    锁只覆盖「发现端口 / 冷启动」这一小段 —— 防止两个进程同时判定「没在跑」
    并各起一个 Chrome。附着之后各进程各开各的标签页，互不干扰，不必持锁。
    """
    prof = profile_dir(args)
    if headless is None:
        headless = getattr(args, "headless", True)
    with ProfileLock(prof):
        port = read_devtools_port(prof)
        launched = False
        if port and port_alive(port):
            log(f"附着到已运行的浏览器，端口 {port}")
        else:
            chrome = os.environ.get("CHROME_BRIDGE_CHROME") or find_chrome()
            mode = "headful" if force_headful else ("headless" if headless else "headful")
            log(f"启动 Chrome（{mode}）…")
            proc = _launch_chrome(chrome, prof, headless and not force_headful,
                                  getattr(args, "chrome_arg", None) or [])
            port = _wait_port(prof, proc=proc)
            launched = True
            log(f"就绪，端口 {port}")

    meta = http_json(port, "/json/version")
    version = meta.get("Browser", "?")
    target = http_json(port, "/json/new?about:blank", method="PUT")
    cdp = CDP(target["webSocketDebuggerUrl"])
    for m in ("Page.enable", "Runtime.enable", "Network.enable"):
        cdp.send(m)
    # 统一去掉 "HeadlessChrome" 特征：headless 默认 UA 会被部分站点直接拒。
    # 放在这里而不是某个子命令里，保证所有命令一致。
    ua = default_ua(version)
    if ua:
        try:
            cdp.send("Network.setUserAgentOverride",
                     {"userAgent": ua, "acceptLanguage": "zh-CN,zh;q=0.9,en;q=0.8"})
        except Exception:
            pass
    sess = Session(prof, headless, port, cdp, target["id"], launched)
    sess.version = version
    return sess


# ----------------------------------------------------------------------------- 页面操作

def default_ua(version: str) -> str:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", version or "")
    if not m:
        return ""
    return (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{m.group(1)}.0.0.0 Safari/537.36")


def strip_dom(html: str) -> str:
    html = re.sub(r"(?is)<script.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?</style>", " ", html)
    html = re.sub(r"(?is)<head.*?</head>", " ", html)
    html = re.sub(r"(?is)<(noscript).*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;?", " ", html)
    html = re.sub(r"&amp;?", "&", html)
    html = re.sub(r"&lt;?", "<", html)
    html = re.sub(r"&gt;?", ">", html)
    html = re.sub(r"&quot;?", '"', html)
    html = re.sub(r"&#x?[0-9a-fA-F]+;?", " ", html)
    return html


def read_page(sess: Session) -> dict:
    """读当前页面（不导航）。"""
    res = sess.cdp.send("Runtime.evaluate", {
        "expression": "JSON.stringify({url: location.href, title: document.title, "
                      "text: document.body ? document.body.innerText : ''})",
        "returnByValue": True,
    })
    data = json.loads(res["result"]["value"])
    text = data["text"].strip()
    m = re.search(r"<!doctype html[^>]*>|<html[\s\S]*</html>", text, re.I)
    if m:  # 整页被当成纯文本（站点返回 text/html 给纯文本），剥标签
        data["raw_html"] = True
        text = strip_dom(m.group(0)).strip()
    data["text"] = text
    return data


def nav(sess: Session, url: str, wait: str, timeout: float,
        settle: float = 0.8, min_wait: float = 3.5, wait_for: str | None = None) -> dict:
    """导航到 url 并等待渲染；返回 {url, title, text}。

    wait 取值：
      load        —— loadEventFired 即返回（最快；静态页首选）
      networkidle —— load 后 1.5s 内**没有任何网络事件**（请求开始/完成），且**所有在途请求
                     都已完成**（loadingFinished/loadingFailed 都会重置计时并清理计数；
                     不只看「有没有新请求开始」）
      stable      —— 默认。load 后至少观察 min_wait 秒，之后 DOM 文本长度连续 settle 秒
                     不变才返回。

    为什么 stable 要等满 min_wait 而**不能**提前返回：在渲染真正发生之前，静态页和
    慢 SPA 在 DOM 上无法区分（一段长度不变的内容 / 空壳），也都没有网络活动。
    任何「看起来已经稳定了」的提前退出都会把慢 SPA 截断在半渲染状态。
    所以：拿不准就等；确定是静态页就用 `--wait load`（快 4 倍）。

    两个精确手段：
      --min-wait N        渲染更慢（如 5-6 秒）就调大
      --wait-for SELECTOR 等到该元素出现且有文本才返回 —— 唯一确定性的等待方式
    """
    cdp = sess.cdp
    # 选择器语法预校验必须在 Page.navigate **之前**：语法错误是「输入错误」，
    # 不该先发起一次导航再报错。与「等不到」（退出码 3）区分开（退出码 4）。
    if wait_for:
        try:
            r = cdp.send("Runtime.evaluate", {
                "expression": "(() => { try { document.querySelector(%s); return ''; } "
                              "catch (e) { return String(e && e.name || e); } })()"
                              % json.dumps(wait_for),
                "returnByValue": True,
            })
            if ((r.get("result", {}).get("value") or "").strip()):
                return {"url": url, "title": "", "text": "", "timed_out": False,
                        "reached": False, "selector_invalid": True,
                        "selector_error": f"非法的 CSS 选择器：{wait_for!r}"}
        except Exception:
            pass
    for m in ("Page.loadEventFired", "Page.frameNavigated"):
        cdp.events(m)  # 清空旧页面事件
    cdp.network_in_flight.clear()
    cdp.network_last_activity = time.monotonic()
    cdp.send("Page.navigate", {"url": url})
    deadline = time.monotonic() + timeout
    load_start = None
    load_fired = False
    dom_len, dom_since = -1, None

    def selector_ready() -> bool:
        """--wait-for 的判定。选择器语法错误时**不能**让整条命令崩掉
        （_eval 遇到页面异常会 die），这里必须吞掉并当作「未就绪」。"""
        if not wait_for:
            return True
        try:
            expr = ("(() => { try { const el = document.querySelector(%s);"
                    " return !!el && (el.innerText || el.textContent || '').trim().length > 0; }"
                    " catch (e) { return false; } })()" % json.dumps(wait_for))
            r = sess.cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return bool(r.get("result", {}).get("value"))
        except Exception:
            return False

    # 选择器语法预校验已在导航前完成（见上），此处不再重复。
    reached = False          # 等待条件是否真的达成（超时退出时为 False）
    while time.monotonic() < deadline:
        cdp.pump(0.05)
        now = time.monotonic()
        if cdp._events.get("Page.loadEventFired"):
            if not load_fired:
                load_start = now
            load_fired = True
            cdp._events["Page.loadEventFired"].clear()
        if wait == "load" and load_fired and selector_ready():
            reached = True
            break
        if (wait == "networkidle" and load_fired and not cdp.network_in_flight
                and now - cdp.network_last_activity > 1.5 and selector_ready()):
            reached = True
            break
        if wait == "stable" and load_fired and now - load_start > 0.3:
            try:
                n = _eval(sess, "(document.body ? document.body.innerText.length : 0)") or 0
            except Exception:
                n = dom_len
            if n != dom_len:
                # DOM 变了 → 重新开始计稳定窗口
                dom_since = None
            elif selector_ready():
                # 注意：这里**不**要求 networkidle 式的「在途为 0」。定时器渲染不产生请求，
                # 而页面加载完后网络活动立刻就静下来，用它做门槛等于没有门槛（实测慢 SPA 会被截断）。
                if dom_since is None:
                    dom_since = now
                # 不做「静态页提前返回」的优化：在渲染发生之前，静态页与慢 SPA 在 DOM 上
                # 完全无法区分（都是一段长度不变的内容/空壳），任何提前退出都会误伤慢 SPA。
                # 代价是静态页也要等满 min_wait —— 想快就用 `--wait load` 或 `--wait-for`。
                if now - dom_since > settle and now - load_start > min_wait:
                    reached = True
                    break
            dom_len = n
        time.sleep(0.02)

    data = read_page(sess)
    # 只有 --wait-for 是「等到才返回」的**强承诺**；其余模式等不到条件属正常（超时即返回当前页）。
    # 但调用方必须能区分「等到了」与「等超时」，否则会把半渲染空壳当成成功（旧行为，实测踩坑）。
    data["timed_out"] = bool(wait_for) and not reached
    data["reached"] = reached
    return data


def check_antibot(text: str) -> str | None:
    low = text.lower()
    if len(text) > 6000:
        return None
    for pat, name in ANTIBOT_PATTERNS:
        if pat in low:
            return name
    if len(text) < 200 and ("login" in low or "登录" in text):
        return "疑似登录墙"
    return None


def scroll_bottom(sess: Session, max_rounds: int = 12) -> int:
    last_h = -1
    stable = 0
    rounds = 0
    for rounds in range(1, max_rounds + 1):
        h = sess.cdp.send("Runtime.evaluate", {
            "expression": "(() => { window.scrollTo(0, document.body.scrollHeight); "
                          "return document.body.scrollHeight; })()",
            "returnByValue": True,
        })["result"]["value"]
        time.sleep(0.6)
        if h == last_h:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        last_h = h
    sess.cdp.send("Runtime.evaluate", {"expression": "window.scrollTo(0,0)"})
    return rounds


def screenshot(sess: Session) -> bytes:
    res = sess.cdp.send("Page.captureScreenshot", {"format": "png"})
    return base64.b64decode(res["data"])


def cookie_header(cookies: list[dict], with_values: bool) -> str:
    parts = []
    for c in cookies:
        name = c.get("name", "")
        if not COOKIE_NAME_RE.match(name):
            continue
        parts.append(f"{name}={c.get('value', '')}" if with_values else name)
    return "; ".join(parts)


# ----------------------------------------------------------------------------- 子命令

def _force_headful(args) -> bool:
    return bool(getattr(args, "headful", False))


def cmd_render(args) -> int:
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        data = nav(sess, args.url, args.wait, args.timeout,
                   settle=args.settle, min_wait=args.min_wait, wait_for=args.wait_for)
        if data.get("selector_invalid"):
            # 非法选择器是输入错误，不是页面问题：直接报错退出，不打印半成品正文。
            die(f"{data['selector_error']}（--wait-for 语法错误，已中止）", code=4)
        # 滚动必须在 nav 之后、且不能再导航一次 —— 否则会把懒加载出来的内容冲掉，
        # 还会对目标站发出双倍请求。
        if args.scroll:
            rounds = scroll_bottom(sess, args.scroll)
            log(f"向下滚动 {rounds} 轮以触发懒加载")
            timed_out = data.get("timed_out", False)   # 滚动前 nav 的结论，滚动后 read_page 会丢
            data = read_page(sess)
            data["timed_out"] = timed_out

        if args.screenshot:
            p = Path(args.screenshot)
            p.write_bytes(screenshot(sess))
            log(f"截图已保存 {p}")

        summary = f"# {data['title']}\n{data['url']}\n\n{data['text']}"
        if args.full_html:
            html = sess.cdp.send("Runtime.evaluate", {
                "expression": "document.documentElement.outerHTML", "returnByValue": True,
            })["result"]["value"]
            summary += f"\n\n<!-- FULL HTML -->\n{html}"

        warning = check_antibot(data["text"])
        out = Path(args.out) if args.out else None
        if out:
            out.write_text(summary, encoding="utf-8")
            log(f"正文已写入 {out}（{len(data['text'])} 字）")
        else:
            if len(summary) > args.max_chars:
                summary = summary[:args.max_chars] + f"\n\n…[已截断，原 {len(data['text'])} 字；用 -o 落盘看全文]"
            print(summary)

        meta = {"url": data["url"], "title": data["title"], "chars": len(data["text"]),
                "warning": warning, "screenshot": args.screenshot, "out": args.out,
                "timed_out": data.get("timed_out", False)}
        if data.get("timed_out"):
            meta["error"] = f"--wait-for 未在 {args.timeout}s 内出现：{args.wait_for}"
            log(f"⚠ {meta['error']}；返回的是当前（可能未渲染完的）页面")
        print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
        # --wait-for 是强承诺：等不到就不算成功。页面仍输出（便于排查），但退出码 3 让调用方
        # 能机械区分（脚本里 `if python chrome.py render ... --wait-for X; then ...`）。
        return 3 if data.get("timed_out") else 0
    finally:
        sess.close_target()


def cmd_snapshot(args) -> int:
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        if args.url:
            nav(sess, args.url, "load", args.timeout)
        else:
            die("快照需要 --url")
        p = Path(args.out or "snapshot.png")
        p.write_bytes(screenshot(sess))
        log(f"截图已保存 {p.resolve()}")
        print(str(p.resolve()))
        return 0
    finally:
        sess.close_target()


def cmd_text(args) -> int:
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        nav(sess, args.url, "load", args.timeout)
        if args.selector:
            expr = (f"(() => {{ const el = document.querySelector({json.dumps(args.selector)});"
                    f" return el ? el.innerText : ''; }})()")
            r = sess.cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            print(r["result"]["value"] or "")
        else:
            r = sess.cdp.send("Runtime.evaluate",
                              {"expression": "document.body ? document.body.innerText : ''",
                               "returnByValue": True})
            print(r["result"]["value"] or "")
        return 0
    finally:
        sess.close_target()


def cmd_cookies(args) -> int:
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        all_cookies = sess.cdp.send("Network.getAllCookies")["cookies"]
        # 严格匹配，不能用子串：`"x.com" in "evilx.com.attacker.net"` 会为真
        cookies = [c for c in all_cookies if cookie_matches_domain(c.get("domain", ""), args.domain)]

        if args.format == "json":
            out = []
            for c in cookies:
                item = {"name": c["name"], "domain": c["domain"], "path": c.get("path", "/"),
                        "httpOnly": c.get("httpOnly", False), "secure": c.get("secure", False),
                        "expires": c.get("expires")}
                if args.values:
                    item["value"] = c.get("value", "")
                else:
                    item["value_len"] = len(c.get("value", ""))
                out.append(item)
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            header = cookie_header(cookies, args.values)
            if not args.values:
                print("值已脱敏（只输出 cookie 名）。要带值请加 --values。", file=sys.stderr)
            print(header)
        return 0
    finally:
        sess.close_target()


def cmd_click(args) -> int:
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        nav(sess, args.url, "load", args.timeout)
        time.sleep(args.wait_after)
        expr = (f"(() => {{ const el = document.querySelector({json.dumps(args.selector)});"
                f" if (!el) return 'not-found'; el.click(); return 'clicked'; }})()")
        r = sess.cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        log(f"点击 {args.selector}: {r['result']['value']}")
        time.sleep(0.6)
        return 0
    finally:
        sess.close_target()


def split_field(spec: str) -> tuple[str, str, str]:
    """解析 --field 的「选择器=值」。

    难点：选择器自身常含 `=`（`input[name=user]`、`input[value="a=b"]`），值也可能含 `=`。
    规则：**跳过方括号（属性选择器）和引号内部的 `=`**，取第一个在括号外的 `=` 作为分隔符。

      "#q=a=b"                  → ("#q", "=", "a=b")
      "input[name=user]=alice"  → ("input[name=user]", "=", "alice")
      'input[value="a=b"]=c'    → ('input[value="a=b"]', "=", "c")
      "form > input=x"          → ("form > input", "=", "x")
    """
    depth = 0
    quote = ""
    for i, ch in enumerate(spec):
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif ch == "=" and depth == 0:
            return spec[:i], "=", spec[i + 1:]
    return spec, "", ""


def _eval(sess: Session, expr: str, await_promise: bool = False):
    params = {"expression": expr, "returnByValue": True}
    if await_promise:
        params["awaitPromise"] = True
    r = sess.cdp.send("Runtime.evaluate", params)
    if "exceptionDetails" in r:
        die(f"页面脚本出错: {r['exceptionDetails'].get('text', '')}")
    return r.get("result", {}).get("value")


def cmd_fill(args) -> int:
    """一次导航内填完整张表单：填多个字段 → 点击提交。

    这是表单登录的正确姿势 —— 每次命令都是一次新导航，分多次调用会在
    下一次导航时丢掉上一次填的值。
    """
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        nav(sess, args.url, "load", args.timeout)
        if args.wait_after:
            time.sleep(args.wait_after)

        for sel in args.click_selector or []:
            v = _eval(sess, f"(() => {{ const el = document.querySelector({json.dumps(sel)});"
                            f" if (!el) return 'not-found'; el.click(); return 'clicked'; }})()")
            if v != "clicked":
                die(f"找不到可点击元素 {sel}")
            log(f"已点击 {sel}")
            time.sleep(0.4)

        for spec in args.field:
            sel, sep, val = split_field(spec)
            if not sep:
                die(f"--field 需要「选择器=值」的形式，收到: {spec}")
            # 用原生 setter + 派发 input/change 事件，兼容 React/Vue 受控组件
            expr = (
                "(() => {"
                f"  const el = document.querySelector({json.dumps(sel)});"
                "  if (!el) return 'not-found';"
                "  const proto = el instanceof HTMLTextAreaElement"
                "    ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;"
                "  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;"
                f"  setter.call(el, {json.dumps(val)});"
                "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                "  return 'filled';"
                "})()"
            )
            v = _eval(sess, expr)
            if v != "filled":
                die(f"找不到输入框 {sel}")
            log(f"已填写 {sel}（{len(val)} 字符）")

        for sel in args.submit_selector or []:
            v = _eval(sess, f"(() => {{ const el = document.querySelector({json.dumps(sel)});"
                            f" if (!el) return 'not-found'; el.click(); return 'clicked'; }})()")
            if v != "clicked":
                die(f"找不到提交元素 {sel}")
            log(f"已点击提交 {sel}")

        if args.submit_enter:
            sess.cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter",
                                                     "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
            log("已按 Enter 提交")

        time.sleep(args.settle)
        info = _eval(sess, "JSON.stringify({url: location.href, "
                           "text: document.body ? document.body.innerText.slice(0,400) : ''})")
        print(info)
        return 0
    finally:
        sess.close_target()


def cmd_type(args) -> int:
    """往输入框填文本；配合 --click-selector / --submit-selector 走完一个表单。

    ⚠️ 每次调用都是一次独立导航，所以「填账号、填密码、点提交」必须一条命令完成。
    """
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    try:
        nav(sess, args.url, "load", args.timeout)
        for sel in args.click_selector or []:
            r = sess.cdp.send("Runtime.evaluate", {
                "expression": f"(() => {{ const el = document.querySelector({json.dumps(sel)});"
                              f" if (!el) return 'not-found'; el.click(); return 'clicked'; }})()",
                "returnByValue": True})
            if r["result"]["value"] != "clicked":
                die(f"找不到可点击元素 {sel}")
            log(f"已点击 {sel}")
            r = sess.cdp.send("Runtime.evaluate", {
                "expression": "new Promise(res => setTimeout(res, 300))", "awaitPromise": True})
        if args.wait_after:
            time.sleep(args.wait_after)

        if args.text:
            sel = args.selector
            expr = (f"(() => {{ const el = document.querySelector({json.dumps(sel)});"
                    f" if (!el) return 'not-found'; el.click(); el.focus(); return 'focused'; }})()")
            r = sess.cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            if r["result"]["value"] != "focused":
                die(f"找不到元素 {sel}，无法输入")
            for ch in args.text:
                sess.cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": ch})
            log(f"已向 {sel} 输入 {len(args.text)} 个字符")

        for sel in args.submit_selector or []:
            r = sess.cdp.send("Runtime.evaluate", {
                "expression": f"(() => {{ const el = document.querySelector({json.dumps(sel)});"
                              f" if (!el) return 'not-found'; el.click(); return 'clicked'; }})()",
                "returnByValue": True})
            if r["result"]["value"] != "clicked":
                die(f"找不到提交元素 {sel}")
            log(f"已点击提交 {sel}")

        if args.submit:
            sess.cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter",
                                                     "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
            log("已提交（Enter）")

        time.sleep(args.settle)
        info = sess.cdp.send("Runtime.evaluate", {
            "expression": "JSON.stringify({url: location.href, text: document.body ? document.body.innerText.slice(0,300) : ''})",
            "returnByValue": True})["result"]["value"]
        print(info)
        return 0
    finally:
        sess.close_target()


# --- 登录闸门 ---------------------------------------------------------------

# 只把「登录后才会出现」的 cookie 名当作强证据。
# 注意不要放通用会话名（sessionid/sid/csrftoken/koa:sess/express:sess）——
# 游客态也常发这些，实测会把未登录页面判成已登录。
LOGIN_COOKIE_NAMES = {
    "SESSDATA", "DedeUserID", "DedeUserID__ckMd5", "bili_jct",  # bilibili
    "MUSIC_U", "MUSIC_A",                                      # 网易云
    "pt_key", "pt_pin",                                        # 京东
    "__Host-authjs.csrf-token", "authjs.session-token",        # Auth.js / NextAuth
    "EGG_SESS", "connect.sid",                                 # Node 常见：仅在服务端签发登录态时出现
}

# 只在登录页上出现、登录后就不再出现的字样
LOGIN_PAGE_MARKERS = re.compile(r"验证码|扫码登录|扫码立即下载|短信登录|密码登录|忘记密码|立即注册|Sign in", re.I)

# 登录后才会出现的页面特征（用于「没有已知 cookie 名」的站点兜底）
LOGGED_IN_MARKERS = re.compile(
    r"退出登录|注销|登出|Sign out|Log out|个人中心|我的账户|我的订单|账号设置|控制台|Dashboard", re.I)

# 常见的二级公共后缀（用于把 co.uk / com.au 这类退化域名纠正回组织域）
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "ne", "or", "go", "gob"}


def hint_from_url(url: str) -> str:
    """取组织域名。IP 原样返回；对 co.uk / com.au 这类取两段后缀。"""
    m = re.search(r"https?://([^/:]+)", url)
    if not m:
        return ""
    host = m.group(1).lower()
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        return host
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _is_ip(host: str) -> bool:
    """判断宿主是否 IP 字面量（IPv4 / IPv6）。IPv6 cookie 域常带方括号，一并剥掉。"""
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def cookie_matches_domain(cookie_domain: str, domain: str) -> bool:
    """严格匹配：域名相等，或以 `.<domain>` 结尾。

    不能简单用 `in`：`"bilibili.com" in "evilbilibili.com"` 为真，会把仿冒域算进来。
    两个额外约束，都是实测踩出来的：
      1. 后缀比较必须带前导点，且 `d` 必须是**多标签**域名——`localhost` 不能被 `st` 命中。
      2. **IP 地址只接受相等匹配，不参与后缀匹配**——`127.0.0.1` 与 `0.0.1` 都是合法 IP 字面量，
         按点切分会被误当成父子域；而 cookie 本就绑在单个 IP 宿主上。
    """
    c = (cookie_domain or "").lstrip(".").lower()
    d = (domain or "").lstrip(".").lower()
    if not c or not d:
        return False
    if c == d:
        return True
    if _is_ip(c) or _is_ip(d):
        return False
    # 后缀分支只在 d 是多标签域名时成立（单标签主机名不参与后缀匹配）
    if "." not in d:
        return False
    return c.endswith("." + d)


def login_state(sess: Session, domain_hint: str) -> dict:
    cookies = sess.cdp.send("Network.getAllCookies")["cookies"]
    names = {c["name"] for c in cookies if cookie_matches_domain(c.get("domain", ""), domain_hint)}
    r = sess.cdp.send("Runtime.evaluate", {
        "expression": "JSON.stringify({url: location.href, text: document.body ? document.body.innerText.slice(0,800) : ''})",
        "returnByValue": True,
    })
    d = json.loads(r["result"]["value"])
    url, text = d["url"], d["text"]
    on_login_path = bool(re.search(r"passport|/login|/signin|/sso|account.?login", url, re.I))
    text_has_login = bool(LOGIN_PAGE_MARKERS.search(text))
    return {
        "cookies": names,
        "url": url,
        "on_login_path": on_login_path,
        "text_has_login": text_has_login,
        "logged_in_marker": bool(LOGGED_IN_MARKERS.search(text)),
        "session_hit": sorted(names & LOGIN_COOKIE_NAMES),
        "hint": hint_from_url(url) or domain_hint,
    }


def judge_login(st: dict) -> tuple[bool, str]:
    """判定是否登录成功。返回 (是否成功, 依据)。

    顺序很重要：
      A. 命中已知登录 cookie —— 这是最强证据，即使在登录页路径上也成立
         （例：用户已登录却直接打开 /login，站点不重定向；此时 URL 还是 /login，
          但 SESSDATA 这种 cookie 只有登录后才有）。
      B. 页面出现登录后特征（退出登录/个人中心…）且不在登录路径上 —— 与 cookie 名无关，
         这是对「登录 cookie 不在已知名单」站点最可靠的兜底。
    注意：**不**用「新增 cookie 数 >= N」这类兜底 —— 游客态/追踪 cookie 同样会新增，
    实测会把未登录页面判成 logged_in。
    """
    if st["session_hit"]:
        return True, "命中已知登录 cookie: " + ",".join(st["session_hit"])
    if st["on_login_path"]:
        return False, "仍在登录页路径"
    if st["logged_in_marker"]:
        return True, "页面出现登录后特征"
    return False, "无登录证据"


def probe_login_url(sess: Session, url: str, domain: str) -> dict | None:
    """在**独立标签页**里重新访问登录 URL，看站点是否已把登录用户重定向走。

    为什么要独立标签页：当前标签页可能正显示二维码，重新导航会把它刷掉，
    用户的扫码就白做了。探测页只读、用完即关。
    """
    target = None
    try:
        target = http_json(sess.port, "/json/new?about:blank", method="PUT")
        probe_cdp = CDP(target["webSocketDebuggerUrl"])
        try:
            for m in ("Page.enable", "Runtime.enable", "Network.enable"):
                probe_cdp.send(m)
            probe = Session(sess.prof, sess.headless, sess.port, probe_cdp, target["id"], False)
            ua = default_ua(getattr(sess, "version", ""))
            if ua:
                try:
                    probe_cdp.send("Network.setUserAgentOverride",
                                   {"userAgent": ua, "acceptLanguage": "zh-CN,zh;q=0.9,en;q=0.8"})
                except Exception:
                    pass
            nav(probe, url, "load", 15)
            return login_state(probe, domain)
        finally:
            probe_cdp.close()
    except Exception as e:
        log(f"探测登录状态失败（可忽略）: {type(e).__name__}: {e}")
        return None
    finally:
        # 无论成功失败都要关掉探测标签页，否则每次轮询都会漏一个
        if target:
            try:
                http_json(sess.port, f"/json/close/{target['id']}")
            except Exception:
                pass


def cmd_login(args) -> int:
    # 登录期间浏览器必须活着，且脚本退出后要保持 —— headless 也能渲染二维码，
    # 靠截图交给模型看；headful 用 --headful 显式开。
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    domain = hint_from_url(args.url)
    shot_path = Path(args.shot or (Path.home() / ".claude" / "chrome-bridge" / "login-shot.png"))
    try:
        nav(sess, args.url, "stable", args.timeout)
        if args.wait_after:
            time.sleep(args.wait_after)
        st = login_state(sess, domain)
        initial_cookies = set(st["cookies"])
        log(f"初始：url={st['url']} 登录路径={st['on_login_path']} "
            f"页面含登录字样={st['text_has_login']} cookie {len(initial_cookies)} 个 命中={st['session_hit']}")

        ok, why = judge_login(st)
        if ok:
            print(json.dumps({"status": "already_logged_in", "reason": why, "url": st["url"],
                              "cookies": sorted(st["cookies"])}, ensure_ascii=False))
            return 0

        # 第一屏：把登录页截图给模型看（headless 也能渲染二维码）
        shot = screenshot(sess)
        shot_path.parent.mkdir(parents=True, exist_ok=True)
        shot_path.write_bytes(shot)
        log(f"登录页截图 {shot_path}（{len(shot)} 字节）")

        deadline = time.monotonic() + args.timeout
        attempts = 0
        last = None
        while time.monotonic() < deadline:
            time.sleep(args.interval)
            attempts += 1
            st = login_state(sess, domain)
            last = st
            ok, why = judge_login(st)
            # 当前标签页通常停在登录页（尤其是扫码页），站点不会主动刷新它。
            # 所以要另开一个只读标签页重访一次，看站点是否已把这次访问当成登录用户。
            # 探测节奏：每隔几次轮询探一次（不能每轮都探，否则会把目标站请求几十次）。
            if not ok and args.probe_every > 0 and attempts % args.probe_every == 0:
                ps = probe_login_url(sess, args.url, domain)
                if ps:
                    ok2, why2 = judge_login(ps)
                    if ok2:
                        log(f"探测标签页判定：{why2} (url={ps['url']})")
                        ok, why, st = True, "探测标签页：" + why2, ps
            if ok:
                print(json.dumps({"status": "logged_in", "reason": why, "url": st["url"],
                                  "cookies": sorted(st["cookies"]), "session_hit": st["session_hit"],
                                  "added": sorted(st["cookies"] - initial_cookies),
                                  "attempts": attempts}, ensure_ascii=False))
                return 0
        # 超时：再截一张，让模型看看卡在哪
        shot = screenshot(sess)
        shot_path.write_bytes(shot)
        print(json.dumps({"status": "timeout", "url": last["url"] if last else "",
                          "screenshot": str(shot_path.resolve()),
                          "on_login_path": last["on_login_path"] if last else None,
                          "text_has_login": last["text_has_login"] if last else None,
                          "logged_in_marker": last["logged_in_marker"] if last else None,
                          "session_hit": last["session_hit"] if last else [],
                          "cookies": sorted(last["cookies"]) if last else []},
                         ensure_ascii=False))
        return 2
    finally:
        sess.close_target()
        # 不调用 Browser.close：登录态要跨命令保留，浏览器继续常驻


def cmd_download(args) -> int:
    sess = ensure_session(args, headless=True, force_headful=_force_headful(args))
    out = Path(args.out or ".").resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        sess.cdp.send("Browser.setDownloadBehavior", {"behavior": "allow",
                                                      "downloadPath": str(out)})
        before = set(os.listdir(out))
        nav(sess, args.url, "load", args.timeout)
        deadline = time.monotonic() + args.timeout
        new_files = []
        while time.monotonic() < deadline:
            time.sleep(0.5)
            now = set(os.listdir(out))
            new_files = [f for f in now - before if not f.endswith(".crdownload")]
            if new_files:
                # 等文件大小稳定
                time.sleep(0.8)
                break
        if not new_files:
            log("未检测到下载文件（可能需要登录或链接不是直接下载）")
            return 1
        for f in new_files:
            print(str(out / f))
        return 0
    finally:
        sess.close_target()


def cmd_attach(args) -> int:
    """不新建浏览器，只验证当前 profile 的浏览器是否活着并给出诊断。"""
    prof = profile_dir(args)
    port = read_devtools_port(prof)
    ok = port_alive(port)
    info = {"profile": str(prof), "port": port, "alive": ok}
    if ok:
        try:
            info.update(http_json(port, "/json/version"))
        except Exception as e:
            info["error"] = str(e)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_close(args) -> int:
    prof = profile_dir(args)
    port = read_devtools_port(prof)
    if not port_alive(port):
        log("浏览器未在运行")
        try:
            devtools_port_file(prof).unlink()
        except OSError:
            pass
        return 0
    with ProfileLock(prof):  # 与「启动」互斥：避免 close 和冷启动撞车
        target = http_json(port, "/json/new?about:blank", method="PUT")
        cdp = CDP(target["webSocketDebuggerUrl"])
        try:
            cdp.send("Browser.close")
            log("已优雅关闭（登录态已落盘）")
        except Exception:
            pass
        finally:
            cdp.close()
        for _ in range(100):
            if not port_alive(port):
                break
            time.sleep(0.1)
        try:
            devtools_port_file(prof).unlink()
        except OSError:
            pass
    print(json.dumps({"closed": True, "profile": str(prof)}, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chrome.py", description="真浏览器抓取（含登录闸门）")
    p.add_argument("--profile", help="Chrome 专用 profile 目录（默认 ~/.claude/chrome-bridge/profile）")
    # SUPPRESS：全局写法 --headful 放在子命令之前也能保留下来，
    # 否则子命令的 default=False 会把顶层值覆盖掉。
    p.add_argument("--headful", action="store_true", default=argparse.SUPPRESS,
                   help="首次启动用有头窗口（已有浏览器在跑时不生效）")
    p.add_argument("--chrome-arg", action="append", metavar="ARG",
                   help="透传给 Chrome 的额外参数，可重复（如 --chrome-arg=--proxy-server=...）")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_headful(sp):
        sp.add_argument("--headful", action="store_true", default=argparse.SUPPRESS,
                        help="首次启动用有头窗口（已有浏览器在跑时不生效）")

    def common(sp, url=True):
        if url:
            sp.add_argument("url", help="目标 URL")
        sp.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"超时秒数（默认 {DEFAULT_TIMEOUT}）")
        add_headful(sp)

    r = sub.add_parser("render", help="打开页面并取渲染后正文")
    common(r)
    r.add_argument("-o", "--out", help="正文写入文件（推荐，长页面不上屏）")
    r.add_argument("--screenshot", help="同时保存截图到该路径")
    r.add_argument("--wait", choices=["load", "networkidle", "stable"], default="stable",
                   help="load=load事件即返回；networkidle=1.5s内无网络事件且在途请求完成；stable=至少观察min-wait秒后DOM稳定（默认）")
    r.add_argument("--settle", type=float, default=0.8,
                   help="stable 模式：DOM 连续多少秒不变才算稳定（默认 0.8）")
    r.add_argument("--min-wait", type=float, default=3.5,
                   help="stable 模式：load 后至少观察多少秒（默认 3.5；渲染更慢就调大）")
    r.add_argument("--wait-for", metavar="SELECTOR",
                   help="等到该 CSS 元素出现且有文本才返回（最可靠，知道目标元素时优先用）")
    r.add_argument("--scroll", type=int, default=0, help="向下滚动 N 轮以触发懒加载（0=不滚）")
    r.add_argument("--max-chars", type=int, default=30000, help="上屏时的字符上限")
    r.add_argument("--full-html", action="store_true", help="附带完整 HTML（体积大，慎用）")
    r.set_defaults(func=cmd_render)

    s = sub.add_parser("snapshot", help="截图")
    s.add_argument("--url", help="先导航到该 URL 再截图")
    s.add_argument("-o", "--out", default="snapshot.png")
    s.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    add_headful(s)
    s.set_defaults(func=cmd_snapshot)

    t = sub.add_parser("text", help="取正文（可限定 selector）")
    common(t)
    t.add_argument("--selector", help="CSS 选择器，只取该元素内的文本")
    t.set_defaults(func=cmd_text)

    c = sub.add_parser("cookies", help="导出 cookie 头")
    c.add_argument("domain", help="域名，如 bilibili.com")
    c.add_argument("--url", action="append", help="（预留）按 URL 过滤")
    c.add_argument("--values", action="store_true", help="包含值（默认脱敏，只给 cookie 名）")
    c.add_argument("--format", choices=["header", "json"], default="header")
    add_headful(c)
    c.set_defaults(func=cmd_cookies)

    k = sub.add_parser("click", help="点击元素（触发下载等）")
    common(k)
    k.add_argument("selector", help="CSS 选择器")
    k.add_argument("--wait-after", type=float, default=1.0)
    k.set_defaults(func=cmd_click)

    ty = sub.add_parser("type", help="填写表单（可一次填、点、提交）")
    ty.add_argument("url", help="表单页 URL")
    ty.add_argument("selector", help="要输入的 CSS 选择器")
    ty.add_argument("text", nargs="?", default="", help="要输入的文本")
    ty.add_argument("--click-selector", action="append", metavar="SEL",
                    help="输入前先点击的元素（如「扫码登录」切换按钮），可重复、按顺序")
    ty.add_argument("--submit-selector", action="append", metavar="SEL",
                    help="输入后点击的元素（如提交按钮），可重复、按顺序")
    ty.add_argument("--submit", action="store_true", help="输入后按 Enter")
    ty.add_argument("--wait-after", type=float, default=0.3, help="首次操作前的等待")
    ty.add_argument("--settle", type=float, default=2.0, help="操作后等待页面跳转/渲染")
    ty.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    add_headful(ty)
    ty.set_defaults(func=cmd_type)

    fl = sub.add_parser("fill", help="一次填完整张表单并提交（推荐用于登录表单）")
    fl.add_argument("url", help="表单页 URL")
    fl.add_argument("--field", action="append", metavar="SEL=VALUE", required=True,
                    help="要填的字段，可重复：--field \"#user=alice\" --field \"#pass=secret\"")
    fl.add_argument("--click-selector", action="append", metavar="SEL",
                    help="填写前先点击（如切到密码登录标签）")
    fl.add_argument("--submit-selector", action="append", metavar="SEL",
                    help="填写后点击提交按钮")
    fl.add_argument("--submit-enter", action="store_true", help="填写后按 Enter")
    fl.add_argument("--wait-after", type=float, default=0.5, help="导航后等待")
    fl.add_argument("--settle", type=float, default=2.0, help="提交后等待跳转")
    fl.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    add_headful(fl)
    fl.set_defaults(func=cmd_fill)

    l = sub.add_parser("login", help="登录闸门：截图 + 轮询直到登录成功")
    l.add_argument("url", help="登录页 URL")
    l.add_argument("--timeout", type=float, default=DEFAULT_LOGIN_TIMEOUT, help="等待人工登录的最长秒数")
    l.add_argument("--interval", type=float, default=3.0, help="轮询间隔秒")
    l.add_argument("--wait-after", type=float, default=1.5, help="导航后等待秒")
    l.add_argument("--shot", help="登录页截图落盘路径")
    l.add_argument("--probe-every", type=int, default=2,
                   help="每 N 轮轮询另开只读标签页探测一次登录态（默认 2；设 0 关闭探测）")
    add_headful(l)
    l.set_defaults(func=cmd_login)

    d = sub.add_parser("download", help="触发下载并返回落盘路径")
    common(d)
    d.add_argument("-o", "--out", default=".", help="下载目录")
    d.set_defaults(func=cmd_download)

    a = sub.add_parser("attach", help="检查当前 profile 的浏览器状态")
    a.set_defaults(func=cmd_attach)

    cz = sub.add_parser("close", help="优雅关闭浏览器（保留登录态）")
    cz.set_defaults(func=cmd_close)

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
