"""chrome-bridge 回归测试集：本地金丝雀站点 + 三套验收脚本。

本机验证用，不面向用户。任何改动 scripts/chrome.py 之后跑一遍确认不回归。

用法：
    python tests/canary-server.py          # 起服务（保持前台，另开一个终端）
    python tests/e2e.py                    # 端到端 11 项
    python tests/regression.py             # 缺陷回归 14 项
    python tests/login-e2e.py              # 登录闸门完整生命周期

所有路径相对本文件定位，不依赖任何绝对路径。测试用的 profile 在 tests/.work/ 下，跑完自动 close。

## 覆盖了什么

- **端到端**：静态页 / SPA / 截图 / 表单登录 / cookie 导出 / cookie 直接请求 / 优雅关闭后持久化 / 已登录判定
- **缺陷回归**：每个修过的 bug 一条用例（emoji 输出、`--headful` 两种写法、`--scroll` 单次导航、
  `--wait-for` 精确等待、两类登录误判、域名严格匹配、`--field` 两种解析、`--wait-for` 语法错误）
- **登录闸门**：未登录 → 轮询 → 期间登录 → 识别成功

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
- 如果看到 `另一个 chrome-bridge 正在使用该 profile`，是上一个用例的浏览器没关干净。
"""
