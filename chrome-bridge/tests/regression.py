"""针对代码审查发现的每个 blocker / major 的回归测试。

每条用例对应一个具体缺陷，修好之前应当失败。
用法：先启动 tests/canary-server.py，再跑本脚本。
"""
import json
import sys
import urllib.request

from common import BASE, WORK, Checker, close_all, fresh_profile, run  # noqa: E402

check = Checker()
PROFILES = []


def prof(name):
    PROFILES.append(name)
    return fresh_profile(name)


def count(path):
    with urllib.request.urlopen(BASE + "/count", timeout=10) as r:
        return json.loads(r.read()).get(path, 0)


def last_status(out):
    try:
        return json.loads(out.strip().splitlines()[-1]).get("status", "")
    except Exception:
        return ""


def read(path):
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# ---------------------------------------------------------------- B1
print("== B1) 非 GBK 字符不应让命令崩溃（默认环境，不设 PYTHONIOENCODING）==")
P = prof("reg-b1")
code, out, err = run(["text", BASE + "/login"], P)
check("text 输出含 emoji 且不崩", code == 0 and "😀" in out, f"exit={code}")
code, out, err = run(["render", BASE + "/login", "--max-chars", "500"], P)
check("render 上屏含 emoji 且不崩", code == 0 and "😀" in out, f"exit={code}")

# ---------------------------------------------------------------- B3
print("== B3) --headful 必须真的生效（两种写法）==")
code, out, err = run(["render", BASE + "/spa", "--headful"], prof("reg-b3"))
check("子命令后置 --headful 生效", "启动 Chrome（headful）" in err, err.strip()[:90])
code, out, err = run(["--headful", "render", BASE + "/spa"], prof("reg-b3b"))
check("全局前置 --headful 生效", "启动 Chrome（headful）" in err, err.strip()[:90])

# ---------------------------------------------------------------- B4
print("== B4) --scroll 只导航一次，且懒加载内容保留 ==")
P = prof("reg-b4")
c0 = count("/counted")
code, out, err = run(["render", BASE + "/counted", "--scroll", "4", "-o", str(WORK / "reg-b4.md")], P)
c1 = count("/counted")
body = read(WORK / "reg-b4.md")
reqs = c1 - c0
check("只请求一次（不是 2 次）", reqs == 1, f"请求次数={reqs}")
check("滚动后内容保留", "ITEM-2" in body or "ITEM-3" in body,
      "含 " + ", ".join(i for i in ("ITEM-2", "ITEM-3", "ITEM-4") if i in body))

# ---------------------------------------------------------------- M1
print("== M1) stable 应等到延迟渲染 ==")
P = prof("reg-m1")
code, out, err = run(["render", BASE + "/spa", "-o", str(WORK / "reg-m1c.md")], P)
check("默认参数拿到 1.2s 渲染的 SPA", "RENDERED-BY-JS" in read(WORK / "reg-m1c.md"), "")
code, out, err = run(["render", BASE + "/slow-spa", "--wait-for", "#app", "-o",
                      str(WORK / "reg-m1b.md")], P)
check("--wait-for 精确等待 3s 渲染", "SLOW-RENDERED-OK" in read(WORK / "reg-m1b.md"), "")

# ---------------------------------------------------------------- B2 / N2
print("== B2/N2) 未登录页面不应被判成 logged_in ==")
code, out, err = run(["login", BASE + "/tracker", "--timeout", "8", "--interval", "1",
                      "--shot", str(WORK / "reg-b2.png")], prof("reg-b2"))
check("追踪 cookie 页面判为 timeout", last_status(out) == "timeout", last_status(out))

code, out, err = run(["login", BASE + "/guest-session", "--timeout", "8", "--interval", "1",
                      "--shot", str(WORK / "reg-n2.png")], prof("reg-n2"))
check("游客会话 cookie 页判为 timeout", last_status(out) == "timeout", last_status(out))

# ---------------------------------------------------------------- M4
print("== M4) cookie 域名严格匹配 ==")
code, out, err = run(["cookies", "notcanary.test"], prof("reg-m4"))
check("不匹配的子串域不返回 cookie", out.strip() == "", f"out={out.strip()[:60]!r}")

# ---------------------------------------------------------------- M5 / N1
print("== M5/N1) --field 解析边界 ==")
code, out, err = run(["fill", BASE + "/flow", "--field", "input[name=user]=canary",
                      "--field", "input[name=pass]=canary123",
                      "--submit-selector", "#submit", "--settle", "2"], prof("reg-m5"))
check("属性选择器能填且提交成功", code == 0 and "SECRET-CONTENT-OK" in out, f"exit={code}")

code, out, err = run(["fill", BASE + "/flow", "--field", "input[name=user]=a=b",
                      "--field", "input[name=pass]=canary123",
                      "--submit-selector", "#submit", "--settle", "2"], prof("reg-n1"))
check("值含 = 不崩溃（账号错误，仍在登录页）", code == 0 and "SECRET" not in out, f"exit={code}")

# ---------------------------------------------------------------- N3
print("== N3) --wait-for 语法错误不应崩溃 ==")
code, out, err = run(["render", BASE + "/spa", "--wait-for", "#bad[", "--timeout", "12"],
                     prof("reg-n3"))
check("非法选择器不崩（exit=0）", code == 0, f"exit={code}")

close_all(*PROFILES)
sys.exit(0 if check.summary("回归") else 1)
