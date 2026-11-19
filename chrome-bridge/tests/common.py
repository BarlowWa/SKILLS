"""chrome-bridge 测试公共部分：路径定位、子进程调用、结果收集。

所有测试脚本都从这里导入，保证：
  * 路径相对本文件定位（仓库可移植，不依赖任何绝对盘符路径）
  * 测试脚本自身在 GBK 终端下也能打印含 emoji 的结果
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
CHROME_PY = SKILL_ROOT / "scripts" / "chrome.py"
CANARY = HERE / "canary-server.py"
WORK = HERE / ".work"          # profile 与产物都放这里（仓库内，git 忽略）
PORT = int(os.environ.get("CANARY_PORT", "8765"))
BASE = f"http://127.0.0.1:{PORT}"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def run(args, profile, timeout=180):
    """跑一条 chrome.py 命令。刻意不设 PYTHONIOENCODING —— 验证脚本在默认 GBK 环境可用。"""
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    p = subprocess.run(
        [sys.executable, str(CHROME_PY), "--profile", str(profile)] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )
    return p.returncode, p.stdout, p.stderr


def fresh_profile(name):
    """关掉残留浏览器并清空该 profile，返回路径。"""
    p = WORK / name
    subprocess.run([sys.executable, str(CHROME_PY), "--profile", str(p), "close"],
                   capture_output=True, timeout=120)
    shutil.rmtree(p, ignore_errors=True)
    return p


def close_all(*names):
    for n in names:
        subprocess.run([sys.executable, str(CHROME_PY), "--profile", str(WORK / n), "close"],
                       capture_output=True, timeout=120)


def api_me():
    with urllib.request.urlopen(BASE + "/api/me", timeout=10) as r:
        return json.loads(r.read())


class Checker:
    def __init__(self):
        self.results = []

    def __call__(self, name, cond, detail=""):
        cond = bool(cond)
        self.results.append((name, cond, detail))
        print(("  PASS  " if cond else "  FAIL  ") + name + (("  | " + detail) if detail else ""))
        return cond

    def summary(self, label):
        ok = sum(1 for _, c, _ in self.results if c)
        print(f"\n===== {label} {ok}/{len(self.results)} 通过 =====")
        return ok == len(self.results)


WORK.mkdir(parents=True, exist_ok=True)
