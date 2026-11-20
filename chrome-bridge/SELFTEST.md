# chrome-bridge 验收脚本（本机验证用，不面向用户）

任何改动 `scripts/chrome.py` 之后跑一遍，确认不回归。

## 用法

```bash
python tests/canary-server.py      # 起服务（保持前台，另开一个终端）
python tests/e2e.py                # 端到端 11 项
python tests/regression.py         # 缺陷回归 32 项（N5 用循环跑 3 个 flag，故运行时多于源码里的 check 调用数）
python tests/login-e2e.py          # 登录闸门完整生命周期
```

所有路径相对本文件定位，不依赖任何绝对路径。测试用的 profile 在 `tests/.work/` 下（gitignore）。

**每套脚本都必须可重复运行**：跑第二次与第一次结果一致。`e2e.py` 在开跑前会真正删除
`tests/.work/e2e`（只 `close` 不够——profile 里的 `sid` 是持久 cookie，上次的登录态会留到下一次）。

## 覆盖了什么

- **端到端**：静态页 / SPA / 截图 / 表单登录 / cookie 导出 / cookie 直接请求 / 优雅关闭后持久化 / 已登录判定。
  用例 1 是**前置断言**（服务端确实未登录）——它红了说明前提不成立，后续未登录用例无意义。
- **缺陷回归**：每个修过的 bug 至少一条用例——
  emoji 输出、`--headful` 两种写法、`--scroll` 单次导航、`--wait-for` 精确等待与超时语义、
  两类登录误判、**cookie 域名严格匹配（单元层正/反例 + CLI 层正例）**、
  `--field` 两种解析、**`--chrome-arg` 危险 flag 拒绝**、**相对 profile 路径可用**。
- **登录闸门**：未登录 → 轮询 → 期间登录 → 识别成功。

## 判据要求（写新用例时遵守）

- 断言写「**应该怎样**」，不写「现在怎样」。
- 凡涉及「不存在/不应命中」的断言，必须在**非空输入**上做，否则对被测函数零区分度
  （反例：旧 M4 用空 profile 断言输出为空，实现改成恒 True/False 都能过）。
- 领域纯函数优先走**单元断言**（直接 import `scripts/chrome.py` 调函数）——CLI 层构造不出反例时
  （如 Chrome 拒绝存储跨域 Set-Cookie），单元层是唯一能测严格性的地方。

## 金丝雀站端点

| 端点 | 用途 |
|---|---|
| `/login` `#user` `#pass` `#submit`（canary/canary123） | 表单登录；已登录时 302 到 `/protected` |
| `/protected` | 受保护页（未登录 302），含 `SECRET-CONTENT-OK` |
| `/spa` | load 后 1.2s 由 setTimeout 渲染 |
| `/slow-spa` | load 后 3s 渲染（验证 `--wait-for`） |
| `/tracker` | 未登录但 JS 写 3 个追踪 cookie（验证不误判） |
| `/guest-session` | 游客也发 `koa:sess`（验证不误判） |
| `/counted` + `/count` | 请求计数（验证 `--scroll` 只导航一次） |
| `/lazy` | 滚动才追加内容 |
| `/file` | 附件下载 |
| `/api/me` | JSON 登录态（给 cookie 接力验证用） |

## 注意

- 测试脚本通过 `common.py` 统一把 stdout 改成 UTF-8 —— 它们也跑在 GBK 终端下。
- 如果看到 `另一个 chrome-bridge 正在使用该 profile`，是上一个用例的浏览器没关干净；
  `python scripts/chrome.py --profile <绝对路径> close` 可优雅回收。
- **`--profile` 必须传绝对路径**（脚本里 `common.py` 已保证）。相对路径会被 Chrome 按自己的 cwd 解析，
  导致稳定超时 30s 并留下孤儿进程（`chrome.py:profile_dir` 已强制转绝对路径，此处仅留作排障记忆）。
