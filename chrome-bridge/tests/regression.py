"""针对代码审查发现的每个 blocker / major 的回归测试。

缺陷用例在修复前应当失败；纯防回归门（修复前也能通过）会在用例上方注明，
用来防止修复实现引入新的退化。
用法：先启动 tests/canary-server.py，再跑本脚本。
"""
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request

from common import BASE, CHROME_PY, WORK, Checker, close_all, fresh_profile, run  # noqa: E402

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

# ---------------------------------------------------------------- N7
print("== N7) networkidle 必须等在途请求完成 ==")
# 设计依据（test-author）：
#   契约：--wait networkidle = load 后 1.5s 无新请求，且无在途请求。
#   边界：慢响应 2.5s（旧实现只按请求开始计时，1.5s 即提前返回，本用例修复前为红）；
#         fetch abort 触发 loadingFailed（在途计数必须清理，不能卡死）。
#   期望来源：chrome.py nav() 的等待契约 + CDP Network 事件语义，不由当前实现反推。
#   未覆盖：HTTP 5xx/重定向仍属 loadingFinished，不单独构造。
#   定位：abort 用例是**修复后的防回归门**——旧实现不维护在途计数，修复前也通过；
#         它防的是修复引入 loadingFailed 漏清理导致 networkidle 卡到导航超时。
P = prof("reg-n7")


def render_timed(url, out_name):
    out = WORK / out_name
    out.unlink(missing_ok=True)  # 防止上次运行的残留文件造成假绿
    t0 = time.monotonic()
    code, _, _ = run(["render", BASE + url, "--wait", "networkidle",
                      "--timeout", "15", "-o", str(out)], P)
    return code, read(out), time.monotonic() - t0


# 12s 上界：高于本机实测（慢响应 ~4.9s、abort ~2.1s，均含 Chrome 启动），
# 又明显低于 15s 导航超时；慢机若误报，优先查实现是否卡到超时，不要直接放宽到 15s。



code, body, elapsed = render_timed("/slow-api", "reg-n7.md")
check("慢响应返回前不应判定 networkidle", code == 0 and "SLOW-API-DONE" in body,
      f"exit={code} elapsed={elapsed:.1f}s body={body[-80:]!r}")
check("networkidle 不应等到导航超时", elapsed < 12, f"elapsed={elapsed:.1f}s")

code, body, elapsed = render_timed("/slow-abort", "reg-n7b.md")
check("被 abort 的请求不应卡住 networkidle", code == 0 and "ABORTED" in body,
      f"exit={code} elapsed={elapsed:.1f}s body={body[-80:]!r}")
check("abort 后不应等到导航超时", elapsed < 12, f"elapsed={elapsed:.1f}s")

# ---------------------------------------------------------------- B5 / B6（标签页不得抢焦点）
# 设计依据（test-author）：
#   契约：抓取类命令在 headful 下**不得改动窗口的激活状态**——
#         用户可能正拿这台机器并行干别的，窗口被还原/抬到前台就是打扰。
#   期望来源：用户诉求 + CDP 语义（Target.createTarget 的 background 参数 /
#             PUT /json/new 的隐含激活行为），不由当前实现反推。
#   只在 headful 下判：headless 没有窗口，断言不成立也无意义。
#   判据取的是**最小化状态**（窗口丢失了"最小化"就意味着被抬回桌面），
#   这是 OS 层的可观测量，不依赖测量时刻谁恰好持有前台焦点。

user32 = ctypes.windll.user32 if os.name == "nt" else None
SW_MINIMIZE = 6


def chrome_windows():
    """当前所有 Chrome 顶层窗口 (hwnd, title)。"""
    rows = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.endswith("Google Chrome"):
            rows.append((hwnd, buf.value))
        return True

    user32.EnumWindows(_cb, 0)
    return rows


def _owner_pid(hwnd):
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_of_profile(profile):
    """按 profile 定位**这个** chrome-bridge 实例的窗口。

    不能用「标题含 about:blank」去找：本机可能同时跑着别的 profile 的浏览器
    （实测有日常 Chrome 开着 about:blank 标签），会测到别人的窗口上，
    用例变成假绿/假红。profile 路径只出现在本实例的启动命令行里，所以按 PID 找。
    """
    ps = ('Get-CimInstance Win32_Process -Filter "Name=\'chrome.exe\'" | '
          "Where-Object { $_.CommandLine -like '*--remote-debugging-port=0*' -and "
          f"$_.CommandLine -like '*{profile}*' }} | Select-Object -First 1 -ExpandProperty ProcessId")
    p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if not p.stdout.strip().isdigit():
        return None
    pid = int(p.stdout.strip())
    return next((h for h, _ in chrome_windows() if _owner_pid(h) == pid), None)


def minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


if user32 is None:
    print("== B5/B6) 跳过：窗口激活状态只能在 Windows 上观测 ==")
else:
    print("== B5) headful 抓取不得把浏览器窗口抬回桌面 ==")
    P = prof("reg-b5")
    code, out, err = run(["snapshot", "--url", BASE + "/spa", "--headful", "-o", str(WORK / "reg-b5.png")], P)
    check("headful 冷启动成功", code == 0, f"exit={code}")
    hwnd = window_of_profile(P)
    if hwnd is None:
        check("找到本实例的 headful 窗口", False, "未按 profile 定位到窗口")
    else:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        time.sleep(0.8)
        check("前置：窗口已最小化", minimized(hwnd), "初始就没最小化，后续断言无意义")
        code, out, err = run(["render", BASE + "/spa", "--headful", "-o", str(WORK / "reg-b5b.md")], P)
        check("headful 抓取成功", code == 0 and "RENDERED-BY-JS" in read(WORK / "reg-b5b.md"), f"exit={code}")
        time.sleep(0.5)  # 激活是异步的：不等一下，快路径下会漏报
        check("抓取后窗口仍最小化（没被抬回桌面）", minimized(hwnd), "")
        code, out, err = run(["snapshot", "--url", BASE + "/spa", "--headful", "-o", str(WORK / "reg-b5d.png")], P)
        time.sleep(0.5)
        # 截图是唯一允许动窗口的动作：最小化时截图不可靠（实测第二张挂到 90s），
        # 所以 screenshot() 会先把窗口还原。这是本轮新增代码里唯一会改变窗口状态的分支。
        check("最小化状态下截图仍成功（截图前自动还原窗口）",
              code == 0 and (WORK / "reg-b5d.png").is_file()
              and (WORK / "reg-b5d.png").stat().st_size > 3000, f"exit={code}")
        check("截图前的还原生效了（窗口已不再是最小化）", not minimized(hwnd), "")
        code, out, err = run(["login", BASE + "/protected", "--headful", "--timeout", "4",
                              "--interval", "1", "--shot", str(WORK / "reg-b5c.png")], P)
        time.sleep(0.5)
        # login 是**例外**：它要用户看着扫码，所以会显式把窗口/标签页显示出来。
        # 这里断言的是相反的契约 —— 它确实显示了，而不是悄悄留在最小化状态。
        check("login --headful 会把窗口显示出来（用户要扫码）", not minimized(hwnd), f"exit={code}")

    print("== B6) 轮询探测不得反复打扰 ==")
    # 用**OS 层**观测：窗口是否被反复激活/还原。
    # 不用页面 visibilityState：焦点仿真（为了让隐藏标签页照常渲染而开的）会把页面骗成
    # visible —— 连探测标签页都报 visible，拿它当判据测的是仿真的副作用。
    # 已知局限：标签页在标签栏里被换进换出这一层，在窗口不在前台时 OS 侧观测不到；
    # 它由结构保证（open_tab 一律 background=True，见 chrome.py）与 B6b 共同守住。
    P = prof("reg-b6")
    code, out, err = run(["snapshot", "--url", BASE + "/spa", "--headful", "-o", str(WORK / "reg-b6.png")], P)
    hwnd = window_of_profile(P)
    if code != 0 or hwnd is None:
        check("B6 前置：headful 冷启动成功", False, f"exit={code} hwnd={hwnd}")
    else:
        port = int((P / "DevToolsActivePort").read_text().splitlines()[0].strip())
        bg = subprocess.Popen(
            [sys.executable, str(CHROME_PY), "--profile", str(P), "login", BASE + "/tracker",
             "--headful", "--timeout", "12", "--interval", "1", "--shot", str(WORK / "reg-b6b.png")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        seq, tabs, restored_late = [], [], 0
        try:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 9 and bg.poll() is None:
                seq.append((user32.GetForegroundWindow() == hwnd, minimized(hwnd)))
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10) as r:
                    tabs.append(len([t for t in json.loads(r.read()) if t.get("type") == "page"]))
                time.sleep(0.25)
        finally:
            bg.wait(timeout=120)
        # login 只该显示一次（用户要扫码），此后轮询不应再有「最小化 → 还原」或抢前台
        pairs = list(zip(seq, seq[1:]))
        restored_late = sum(1 for a, b in pairs if a[1] and not b[1])
        raises = sum(1 for a, b in pairs if b[0] and not a[0])
        check("轮询期间窗口不被反复还原", restored_late <= 1, f"还原 {restored_late} 次 / 采样 {len(seq)} 次")
        check("轮询期间窗口不抢前台", raises == 0, f"抢前台 {raises} 次")
        # 峰值 = login 页 + 探测页 + chrome://newtab；关键是它不随时间增长
        check("轮询期间标签页数量不累积", max(tabs) <= 3, f"峰值 {max(tabs)} 个页面")
        check("B6 前置：login 确实显示了页面（否则上面几条是空断言）", not all(m for _, m in seq),
              "全程都处于最小化，说明 bringToFront 没生效")

    print("== B6b) 单次抓取不得抢走用户的活动标签页 ==")
    # 用 Win32 侧判断：抓取期间窗口不得被激活。这是「不打扰」的最直接观测。
    P = prof("reg-b6b")
    code, out, err = run(["snapshot", "--url", BASE + "/spa", "--headful", "-o", str(WORK / "reg-b6c.png")], P)
    hwnd = window_of_profile(P)
    if code != 0 or hwnd is None:
        check("B6b 前置：headful 冷启动成功", False, f"exit={code} hwnd={hwnd}")
    else:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)
        user32.ShowWindow(hwnd, SW_MINIMIZE)      # 收起窗口 = 用户此刻没在看它
        time.sleep(0.6)
        code, out, err = run(["render", BASE + "/spa", "--headful", "-o", str(WORK / "reg-b6d.md")], P)
        check("抓取成功", code == 0 and "RENDERED-BY-JS" in read(WORK / "reg-b6d.md"), f"exit={code}")
        time.sleep(0.5)
        check("抓取不会把窗口还原到前台", user32.GetForegroundWindow() != hwnd and minimized(hwnd), "")
# ---------------------------------------------------------------- B7（对话框不得挂死命令）
print("== B7) 页面自弹对话框不得让抓取命令挂死 ==")
# 原生模态对话框会挂起页面主线程：Runtime.evaluate 永不返回，DOM 也读不到。
# 旧实现对此没有防御 —— 轮询里的每次 evaluate 都要等满 90s socket 超时，
# 一个 --timeout 12 的 login 实测跑了 102.7s 才以 TimeoutError 退出。
P = prof("reg-b7")
t0 = time.monotonic()
code, out, err = run(["render", BASE + "/dialog", "--timeout", "25", "-o", str(WORK / "reg-b7.md")],
                     P, timeout=100)
elapsed = time.monotonic() - t0
check("render 在对话框页面上正常返回", code == 0, f"exit={code} elapsed={elapsed:.1f}s")
check("拿到了正文（对话框被自动关闭）", "DIALOG-PAGE-BODY" in read(WORK / "reg-b7.md"),
      f"文件={read(WORK / 'reg-b7.md')[:60]!r}")
# 上界 40s：正常路径 ~5s；旧实现会卡在 90s 的 socket 超时上。
check("没有卡到 socket 超时", elapsed < 40, f"elapsed={elapsed:.1f}s")

t0 = time.monotonic()
code, out, err = run(["login", BASE + "/dialog-login", "--timeout", "8", "--interval", "1",
                      "--shot", str(WORK / "reg-b7b.png")], P, timeout=150)
elapsed = time.monotonic() - t0
check("login 在弹窗登录页上按时结束", elapsed < 30, f"elapsed={elapsed:.1f}s exit={code}")
check("login 返回 timeout 而不是崩溃（确实没登录）", last_status(out) == "timeout",
      f"status={last_status(out)!r} err={err.strip()[-90:]!r}")
shot = WORK / "reg-b7b.png"
check("弹窗登录页截图成功（用户能看见二维码/表单）",
      shot.is_file() and shot.stat().st_size > 3000, f"size={shot.stat().st_size if shot.is_file() else 0}")

# ---------------------------------------------------------------- N8（标签页不累积）
print("== N8) 轮询探测不得漏掉标签页 ==")
# 旧实现在结束探测时用 HTTP /json/close 关标签页，但没等浏览器确认；
# 久而久之残留一堆标签页，用户切标签时全是空白探测页。
# 判据用「跑之前 vs 跑之后」的标签页数量差，不能用绝对值：Chrome 自己会保留
# 一个 chrome://newtab/，绝对值为 0 永远达不到。
P = prof("reg-n8")
code, out, err = run(["login", BASE + "/tracker", "--timeout", "6", "--interval", "1",
                      "--shot", str(WORK / "reg-n8.png")], P)


def _page_count(profile):
    line = (profile / "DevToolsActivePort").read_text().splitlines()[0].strip()
    with urllib.request.urlopen(f"http://127.0.0.1:{line}/json/list", timeout=10) as r:
        return len([t for t in json.loads(r.read()) if t.get("type") == "page"])


before = _page_count(P)
code, out, err = run(["login", BASE + "/tracker", "--timeout", "6", "--interval", "1",
                      "--shot", str(WORK / "reg-n8b.png")], P)
time.sleep(1.0)
after = _page_count(P)
check("轮询探测后标签页数量不增长", after <= before, f"{before} → {after}")
check("命令行结束后不残留探测标签页", after <= 1, f"剩余 {after} 个")

close_all(*PROFILES)
sys.exit(0 if check.summary("回归") else 1)
