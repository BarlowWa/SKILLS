"""chrome-bridge 端到端验收（本地金丝雀站点，假凭据，不需要真实站点登录）。

用法：先启动 tests/canary-server.py，再跑本脚本。
"""
import json
import subprocess
import sys
import time
import urllib.request

from common import BASE, WORK, Checker, api_me, close_all, run  # noqa: E402

check = Checker()
PROFILES = ("e2e",)

print("== 0) 清理旧 profile ==")
close_all(*PROFILES)
time.sleep(0.5)
P = WORK / "e2e"

print("== 1) 服务端未登录 ==")
check("/api/me 未登录", api_me().get("isLogin") is False, json.dumps(api_me()))

print("== 2) 未登录访问受保护页 ==")
code, out, err = run(["render", BASE + "/protected", "--max-chars", "400"], P)
check("受保护页不含 SECRET", "SECRET-CONTENT-OK" not in out, out.strip()[:90].replace("\n", " "))
check("重定向到登录页", "/login" in out, out.strip()[:90].replace("\n", " "))

print("== 3) SPA 渲染 ==")
code, out, err = run(["render", BASE + "/spa", "--max-chars", "400"], P)
check("SPA 渲染出 JS 内容", "RENDERED-BY-JS" in out, out.strip()[:90].replace("\n", " "))

print("== 4) fill 一次填完整张表单 ==")
code, out, err = run(["fill", BASE + "/login",
                      "--field", "#user=canary", "--field", "#pass=canary123",
                      "--submit-selector", "#submit", "--settle", "2.5"], P)
check("提交后跳到 /protected", "/protected" in out, out.strip()[:140].replace("\n", " "))
check("提交后能看到 SECRET", "SECRET-CONTENT-OK" in out, out.strip()[:140].replace("\n", " "))

print("== 5) cookie 导出 ==")
code, out, err = run(["cookies", "127.0.0.1", "--values"], P)
header = [l for l in out.strip().splitlines() if "sid=" in l]
header = header[0] if header else ""
check("cookie 含 sid", "sid=" in header, repr(out.strip()[:100]))

print("== 6) 用这份 cookie 直接请求受保护接口 ==")
req = urllib.request.Request(BASE + "/api/me", headers={"Cookie": header})
with urllib.request.urlopen(req, timeout=15) as r:
    body = r.read().decode("utf-8")
check("带 cookie 请求 isLogin=true", '"isLogin": true' in body, body[:100])

print("== 7) 优雅关闭 → 重启，登录态保留 ==")
run(["close"], P)
time.sleep(1)
code, out, err = run(["render", BASE + "/protected", "--max-chars", "400"], P)
check("重启后仍登录", "SECRET-CONTENT-OK" in out, out.strip()[:90].replace("\n", " "))

print("== 8) login 闸门对已登录站点 ==")
code, out, err = run(["login", BASE + "/login", "--timeout", "15", "--wait-after", "1"], P)
check("login 返回已登录", '"already_logged_in"' in out or '"logged_in"' in out, out.strip()[:140])

print("== 9) 截图 ==")
shot = WORK / "shot.png"
code, out, err = run(["snapshot", "--url", BASE + "/protected", "-o", str(shot)], P)
check("截图落盘", shot.is_file() and shot.stat().st_size > 5000,
      f"{shot.stat().st_size if shot.is_file() else 0} bytes")

print("== 10) 清理 ==")
close_all(*PROFILES)

sys.exit(0 if check.summary("端到端") else 1)
