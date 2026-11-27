"""本地金丝雀站点：带登录表单 + 受保护页面 + SPA 渲染页。
只用标准库，用来在无法扫码时（例如手机远程连接）验证 chrome-bridge 的整条链路。
"""
import http.server
import json
import os
import socketserver
import sys
import time
import urllib.parse
import uuid

SESSIONS = set()
COUNTS = {}
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>测试站 · 登录</title></head>
<body><h1>请登录 😀</h1>
<form id="f" method="POST" action="/do_login">
  <label>账号 <input id="user" name="user" autocomplete="off"></label><br>
  <label>密码 <input id="pass" name="pass" type="password"></label><br>
  <button id="submit" type="submit">登录</button>
</form>
<p>账号 canary / 密码 canary123 🎉</p>
</body></html>"""

PROTECTED_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>测试站 · 私密页</title></head>
<body><h1>私密内容</h1>
<p id="secret">SECRET-CONTENT-OK</p>
<p>只有登录后才能看到这段文字。</p>
<button id="logout" onclick="document.cookie='sid=; Max-Age=0; path=/'; location.href='/login'">退出登录</button>
</body></html>"""

SPA_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>测试站 · SPA</title>
<style>body{font-family:sans-serif}</style></head>
<body><div id="app">loading…</div>
<script>
setTimeout(function(){
  document.getElementById('app').innerHTML = '<h1>JS 渲染完成</h1><p>RENDERED-BY-JS</p>';
}, 1200);
</script></body></html>"""

# 慢速 SPA：load 后 3 秒才渲染，用于验证 stable 的 min_wait
SLOW_SPA_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>测试站 · 慢 SPA</title></head>
<body><div id="app">shell-loading</div>
<script>
setTimeout(function(){
  document.getElementById('app').innerHTML = '<p>SLOW-RENDERED-OK</p>';
}, 3000);
</script></body></html>"""

# 未登录、非登录路径、没有登录特征，但 JS 会写 3 个追踪 cookie（B2 误判复现）
TRACKER_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>追踪页</title></head>
<body><h1>公开首页</h1><p>${PAD}</p>
<script>
setTimeout(function(){
  document.cookie = 'trk_a=1; path=/; Max-Age=3600';
  document.cookie = 'trk_b=1; path=/; Max-Age=3600';
  document.cookie = 'trk_c=1; path=/; Max-Age=3600';
}, 300);
</script></body></html>"""

# 滚动才追加内容的懒加载页（B4 复现：二次导航会把这些冲掉）
LAZY_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>懒加载页</title>
<style>body{font-family:sans-serif} .item{padding:20px;border-bottom:1px solid #ccc}</style></head>
<body><h1>列表</h1><div id="list"><div class="item">ITEM-1</div></div>
<script>
var n = 1;
window.addEventListener('scroll', function(){
  if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 50 && n < 6) {
    n++;
    var d = document.createElement('div');
    d.className = 'item';
    d.textContent = 'ITEM-' + n;
    document.getElementById('list').appendChild(d);
    document.body.style.minHeight = (n * 200) + 'px';
  }
});
document.body.style.minHeight = '2000px';
</script></body></html>"""

# 用户在别处完成登录后才会出现的页面（用于登录闸门"页面特征"判定）
FLOW_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>登录闸门测试</title></head>
<body><h1>欢迎</h1><form id="f" method="POST" action="/do_login">
<input id="user" name="user"><input id="pass" name="pass" type="password">
<button id="submit" type="submit">登录</button></form>
<p>验证码 1234</p></body></html>"""

# 加载后自弹对话框。真实站点的登录页/引导页会这么干（"请先扫码登录"之类），
# 而原生模态对话框会把页面主线程挂起：任何一次 Runtime.evaluate 都不会返回，
# 旧实现因此会一直卡到 90s socket 超时。
DIALOG_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>对话框页</title></head>
<body><h1>请扫码登录</h1><p>DIALOG-PAGE-BODY</p>
<script>
window.addEventListener('load', function(){ alert('请先扫码登录'); });
</script></body></html>"""

# 登录页 + 自弹对话框。真站的登录页常这么干（"请先扫码登录"引导弹窗），
# 而 chrome-bridge 每轮都要读 DOM 判登录态 —— 对话框如果没被自动关掉，
# 每次读取都会挂到 socket 超时，用户完全没法在页面上操作。
DIALOG_LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>弹窗登录页</title></head>
<body><h1>请扫码登录</h1>
<form id="f" method="POST" action="/do_login">
  <label>账号 <input id="user" name="user" autocomplete="off"></label>
  <label>密码 <input id="pass" name="pass" type="password"></label>
  <button id="submit" type="submit">登录</button>
</form>
<p>LOGIN-PAGE-BODY-OK</p>
<script>
window.addEventListener('load', function(){ alert('请先扫码登录'); });
</script></body></html>"""

# load 后发起一个慢请求；用于验证 networkidle 必须等在途请求完成（N7）
SLOW_API_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>慢接口</title></head>
<body><h1>慢接口</h1><div id="result">WAITING</div>
<script>
setTimeout(function(){
  fetch('/slow-api-data').then(function(r){ return r.text(); }).then(function(t){
    document.getElementById('result').innerText = t;
  });
}, 100);
</script></body></html>"""

# 发起慢请求后主动 abort；用于验证 loadingFailed 能清理在途计数（N7 的失败路径）
SLOW_ABORT_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>中断请求</title></head>
<body><h1>中断请求</h1><div id="result">WAITING</div>
<script>
var c = new AbortController();
fetch('/slow-api-data', {signal: c.signal}).then(function(r){ return r.text(); })
  .then(function(t){ document.getElementById('result').innerText = t; })
  .catch(function(e){ document.getElementById('result').innerText = 'ABORTED'; });
setTimeout(function(){ c.abort(); }, 200);
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _sid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sid" and v in SESSIONS:
                return v
        return None

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/login"):
            # 已登录用户访问登录页 → 跳到受保护页（真实站点的常见行为），
            # 这样「已登录时 login 命令能否识别出来」才是可验证的。
            if self._sid():
                self._send(302, "", headers={"Location": "/protected"})
            else:
                self._send(200, LOGIN_HTML)
        elif path == "/protected":
            if self._sid():
                self._send(200, PROTECTED_HTML)
            else:
                self._send(302, "", headers={"Location": "/login"})
        elif path == "/api/me":
            if self._sid():
                self._send(200, json.dumps({"code": 0, "isLogin": True, "user": "canary"}),
                           "application/json; charset=utf-8")
            else:
                self._send(200, json.dumps({"code": -101, "isLogin": False}),
                           "application/json; charset=utf-8")
        elif path == "/spa":
            self._send(200, SPA_HTML)
        elif path == "/slow-spa":
            self._send(200, SLOW_SPA_HTML)
        elif path == "/tracker":
            self._send(200, TRACKER_HTML.replace("${PAD}", "这只是一个公开页面，没有任何登录相关内容。" * 30))
        elif path == "/lazy":
            self._send(200, LAZY_HTML)
        elif path == "/flow":
            self._send(200, FLOW_HTML)
        elif path == "/dialog":
            self._send(200, DIALOG_HTML)
        elif path == "/dialog-login":
            self._send(200, DIALOG_LOGIN_HTML)
        elif path == "/slow-api":
            self._send(200, SLOW_API_HTML)
        elif path == "/slow-abort":
            self._send(200, SLOW_ABORT_HTML)
        elif path == "/slow-api-data":
            time.sleep(2.5)
            self._send(200, "SLOW-API-DONE", "text/plain; charset=utf-8")
        elif path == "/guest-session":
            # 未登录的普通首页，但服务端给游客也发了一个「会话」cookie。
            # 这类 cookie 名不能当登录证据（复审 N2 的复现用例）。
            self._send(200, FLOW_HTML, headers={
                "Set-Cookie": f"koa:sess={uuid.uuid4().hex}; Path=/; HttpOnly; Max-Age=3600",
            })
        elif path == "/counted":
            # 记录请求次数，用于验证 --scroll 不会二次导航
            COUNTS[path] = COUNTS.get(path, 0) + 1
            self._send(200, LAZY_HTML)
        elif path == "/count":
            self._send(200, json.dumps(COUNTS), "application/json; charset=utf-8")
        elif path == "/file":
            body = b"CANARY-DOWNLOAD-OK\n" * 100
            self._send(200, body, "application/octet-stream", headers={
                "Content-Disposition": 'attachment; filename="canary-download.txt"',
            })
        elif path == "/needlogin":
            if self._sid():
                self._send(200, PROTECTED_HTML)
            else:
                self._send(401, "unauthorized", "text/plain; charset=utf-8")
        else:
            self._send(404, "not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/do_login":
            n = int(self.headers.get("Content-Length", 0))
            form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"))
            user = (form.get("user") or [""])[0]
            pwd = (form.get("pass") or [""])[0]
            if user == "canary" and pwd == "canary123":
                sid = uuid.uuid4().hex
                SESSIONS.add(sid)
                # Max-Age 让它是持久 cookie：这样「浏览器重启后登录态还在」
                # 检验的是 chrome-bridge 的优雅关闭，而不是浏览器的会话 cookie 语义
                self._send(302, "", headers={
                    "Location": "/protected",
                    "Set-Cookie": f"sid={sid}; Path=/; HttpOnly; Max-Age=3600",
                })
            else:
                self._send(200, LOGIN_HTML.replace("请登录 😀</h1>", "请登录 😀</h1><p style='color:red'>账号或密码错误</p>", 1))
        else:
            self._send(404, "not found")

    def log_message(self, fmt, *args):
        sys.stderr.write("[canary] " + (fmt % args) + "\n")


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.daemon_threads = True
        print(f"[canary] http://127.0.0.1:{PORT}/login", flush=True)
        httpd.serve_forever()
