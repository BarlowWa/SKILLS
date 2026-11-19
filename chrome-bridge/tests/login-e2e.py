"""验证登录闸门的完整生命周期：未登录 → 开始轮询 → 期间登录 → 检测到 logged_in。

模拟真实场景：AI 打开登录页截图给用户，用户用别的窗口完成登录，AI 靠 cookie 变化检测到。
这里用同一个 profile 的另一个标签页完成登录（cookie 是浏览器级共享的，等价于"别的窗口登录"）。
用法：先启动 tests/canary-server.py，再跑本脚本。
"""
import json
import subprocess
import sys
import time

from common import BASE, CHROME_PY, WORK, fresh_profile  # noqa: E402

PROFILE = fresh_profile("login-e2e")
time.sleep(0.5)
CB = [sys.executable, str(CHROME_PY)]

print("== 启动 login（后台，未登录状态）==")
login_proc = subprocess.Popen(
    CB + ["--profile", str(PROFILE), "login", BASE + "/login", "--timeout", "90",
          "--interval", "1", "--shot", str(WORK / "login-shot.png")],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    encoding="utf-8", errors="replace",
)

time.sleep(6)  # 让 login 完成导航 + 截图 + 进入轮询
print("  login 已启动并进入轮询")

print("== 模拟'用户在别处登录'：另一个进程用 fill 登录同一 profile ==")
r = subprocess.run(
    CB + ["--profile", str(PROFILE), "fill", BASE + "/login",
          "--field", "#user=canary", "--field", "#pass=canary123",
          "--submit-selector", "#submit", "--settle", "2"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
)
print("  fill exit =", r.returncode)

print("== 等待 login 检测到 ==")
try:
    out, err = login_proc.communicate(timeout=60)
except subprocess.TimeoutExpired:
    login_proc.kill()
    out, err = login_proc.communicate()
    print("  login 未在超时前结束 → FAIL")
    sys.exit(1)

print("  login exit =", login_proc.returncode)
print("  login stdout =", (out or "").strip())

ok = False
try:
    j = json.loads((out or "").strip().splitlines()[-1])
    ok = j.get("status") in ("logged_in", "already_logged_in")
    print("  判定:", j.get("status"), "| reason:", j.get("reason"))
except Exception as e:
    print("  解析失败:", e)

subprocess.run(CB + ["--profile", str(PROFILE), "close"], capture_output=True, timeout=60)
print("\n===== 登录闸门下半程:", "PASS" if ok else "FAIL", "=====")
sys.exit(0 if ok else 1)
