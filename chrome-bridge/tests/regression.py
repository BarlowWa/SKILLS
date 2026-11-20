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
# 两层判据，都是「应该怎样」而非「现在怎样」：
#  (a) 单元层：直接测纯函数 cookie_matches_domain 的严格匹配契约（含子串反例）。
#      这是唯一可行的反例入口 —— Chrome 拒绝存储跨域 Set-Cookie（已实测），
#      所以 CLI 层无法构造「仿冒域名 cookie」来驱动反例。
#  (b) CLI 层：在**有 cookie 的** profile 上查自己的域，cookie 必须被回收。
#      旧用例用 fresh_profile() 空 profile + 不存在的域断言「输出为空」，
#      对 cookie_matches_domain 零区分度（恒 True/False 都过），已删除。
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("chrome_mod", __import__("common").CHROME_PY)
_chrome = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_chrome)
_cm = _chrome.cookie_matches_domain
check("cookie=example.com 对 example.com 命中", _cm("example.com", "example.com") is True, "")
check("cookie=.example.com 前导点忽略后命中", _cm(".example.com", "example.com") is True, "")
check("cookie=sub.example.com 对 example.com 命中", _cm("sub.example.com", "example.com") is True, "")
check("子串反例：cookie=bilibili.com 对 evilbilibili.com 不应命中",
      _cm("bilibili.com", "evilbilibili.com") is False, "")
check("子串反例：cookie=evilbilibili.com 对 bilibili.com 不应命中",
      _cm("evilbilibili.com", "bilibili.com") is False, "")
check("空 domain 不应命中", _cm("", "example.com") is False, "")
# 以下四条的区分度经**变异矩阵**核对：每条都必须能杀死「去掉对应守卫」的变异。
#   ("127.0.0.1","0.0.1")：杀「去掉 IP 守卫」（旧实现返回 True）
#   ("foo.st","st")      ：杀「去掉单标签守卫」（旧实现返回 True）
#   ("localhost","st") 仅能杀子串变异——单标签守卫的缺口由上面那条补上
#   IP 等值正例：防止实现退化成「IP 一律 False」
check("IP 只在相等时命中：cookie=127.0.0.1 对 domain=0.0.1 不应命中",
      _cm("127.0.0.1", "0.0.1") is False, "")
check("IP 等值正例：cookie=127.0.0.1 对 127.0.0.1 应命中",
      _cm("127.0.0.1", "127.0.0.1") is True, "")
check("单标签不参与后缀：cookie=foo.st 对 domain=st 不应命中",
      _cm("foo.st", "st") is False, "")
check("单标签主机不参与后缀：cookie=localhost 对 domain=st 不应命中",
      _cm("localhost", "st") is False, "")

# (b) CLI 层正例：真的产生一个 sid，再按宿主域取回。
#     注意：未登录的 /login 页**不发** sid（sid 只在 POST /do_login 成功后下发），
#     所以必须先走一遍登录，否则这条正例本身是空断言。
P = prof("reg-m4")
run(["fill", BASE + "/login", "--field", "#user=canary", "--field", "#pass=canary123",
     "--submit-selector", "#submit", "--settle", "2.5"], P)
code, out, err = run(["cookies", "127.0.0.1", "--values"], P)
check("CLI：登录后 sid 能按 127.0.0.1 取回", "sid=" in out, f"out={out.strip()[:80]!r}")

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
print("== N3) --wait-for 语法错误应明确报错（不崩溃、也不假装成功）==")
# 早先只断言 exit=0（「不崩」），但 0 与「成功拿到页面」不可区分——非法选择器会白等满
# timeout 再以成功退出，把用户引向「元素没出现」的错误排查方向。现在约定：语法错误 exit=4。
code, out, err = run(["render", BASE + "/spa", "--wait-for", "#bad[", "--timeout", "12"],
                     prof("reg-n3"))
check("非法选择器明确报错（exit=4），而非静默成功", code == 4, f"exit={code}")
check("报错信息点明是选择器语法问题", "选择器" in err, err.strip().splitlines()[-1][:100])

# ---------------------------------------------------------------- N4
print("== N4) --wait-for 等不到时不能报成功 ==")
# 契约：--wait-for 是「等到才返回」的强承诺。选择器合法但永不出现 → 必须非零退出（3），
# 且 meta 里 timed_out=true。旧实现跑满 timeout 后照常 return 0，调用方会把半渲染页当成功。
code, out, err = run(["render", BASE + "/spa", "--wait-for", "#never-appears-xyz",
                      "--timeout", "3"], prof("reg-n4"))
check("--wait-for 超时退出码为 3（非 0）", code == 3, f"exit={code}")
check("meta 标注 timed_out=true", '"timed_out": true' in err, err.strip().splitlines()[-1][:120])

# ---------------------------------------------------------------- N5
print("== N5) --chrome-arg 危险 flag 必须被代码拒绝 ==")
# 安全边界不能只写在 SKILL.md 里：这些 flag 会覆盖专用 profile 或把调试口暴露到局域网。
for bad in ("--user-data-dir=/tmp/evil", "--remote-debugging-address=0.0.0.0",
            "--disable-features=DevToolsDebuggingRestrictions"):
    code, out, err = run([f"--chrome-arg={bad}", "render", BASE + "/login", "--max-chars", "20"],
                         prof("reg-n5"))
    check(f"拒绝 {bad.split('=')[0]}", code == 4, f"exit={code} err={err.strip().splitlines()[-1][:70]}")
# 正常调优 flag 不该被误伤（用 --headful 以外的无害 flag 验证放行逻辑，这里只验证不因黑名单误拒）
code, out, err = run(["--chrome-arg=--disable-features=Translate", "render", BASE + "/login",
                      "--max-chars", "20"], prof("reg-n5b"))
check("正常 --disable-features 不被误拒", code == 0, f"exit={code}")

# ---------------------------------------------------------------- N6
print("== N6) 相对 --profile 路径必须可用 ==")
# 旧实现把相对路径原样交给 Chrome：Chrome 用**自己的** cwd 解析 --user-data-dir，
# 而 _wait_port 用本进程 cwd 找 DevToolsActivePort，两边对不上 → 稳定超时 30s + 孤儿进程。
# 契约：profile_dir() 必须返回绝对路径。
_relargs = type("A", (), {"profile": "tests/.work/reg-rel-probe"})()
_abs = _chrome.profile_dir(_relargs)
check("profile_dir 返回绝对路径", _abs.is_absolute(), str(_abs))

close_all(*PROFILES)
sys.exit(0 if check.summary("回归") else 1)
