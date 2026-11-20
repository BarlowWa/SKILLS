---
name: chrome-bridge
description: 用真实 Chrome 抓取 fetch.py 抓不到的页面——需要登录（含扫码/短信/验证码）、JS 渲染的 SPA、被反爬/Cloudflare 拦截的站点。提供登录闸门（把登录页截图给用户扫，登录后把 cookie 交给 fetch.py 接力）。凡遇到「正文为空」「401」「需要登录」「人机验证」「动态内容加载不出来」「拿不到 cookie」时用它。
---

# chrome-bridge —— 真浏览器抓取

## 什么时候用

**只在 fetch.py 解决不了的时候用。** 默认先走 `fetch-page` skill，命中下面任一条再升级到本 skill：

| 症状（fetch.py 的输出） | 升级到 |
|---|---|
| `正文几乎为空` / 只有导航栏 | `render` |
| `需要登录态` / 401 / 登录墙 | `login` → `cookies --values` → fetch.py 接力 |
| SPA 内容在 `<script>` 里，DOM 是空壳 | `render`（默认 `--wait stable`） |
| 人机验证 / Cloudflare / `Just a moment`（需要人工过闸） | **`login --headful --timeout 420`**（登录闸门会阻塞轮询并保持窗口，见下）；页面自动过盾、无需人工时 `render --headful` 亦可。**`render` 生命周期只到导航+等待为止，不等用户交互**，别用它做过闸 |
| 要截图看页面长什么样 | `snapshot` |
| 要 cookie 但不想开浏览器登录 | `cookies`（前提：profile 里已经有登录态） |

**不要用于**：纯 API、静态页、内网 JSON 接口——那是 fetch.py 的活，它快一个数量级。

## 快速上手

```powershell
$CB = "C:\Users\Barlow\.claude\skills\chrome-bridge\scripts\chrome.py"
$FETCH = "$HOME\.claude\skills\fetch-page\scripts\fetch.py"

# 抓 SPA（渲染后正文）
python $CB render "https://www.bilibili.com" -o out.md

# 截图（模型可直接 Read 这个 PNG 看图）
python $CB snapshot --url "https://example.com" -o shot.png

# 登录闸门：截图给用户扫，等登录成功
python $CB login "https://passport.bilibili.com/login" --timeout 420 --shot login.png

# 登录后导出 cookie，喂给 fetch.py
$h = python $CB cookies bilibili.com --values
python $FETCH --raw --header "Cookie: $h" "https://api.bilibili.com/x/web-interface/nav"

# 用完关掉（建议；不关不丢登录态，但会占着 profile 锁与后台资源）
python $CB close
```

> **PowerShell 不展开 `~`**：原生程序（python）收到的是字面量 `~/.claude/...`，必然找不到文件。
> 一律写绝对路径，或用 `"$HOME\.claude\..."`。

## 核心机制（务必理解，否则会踩坑）

1. **浏览器常驻，进程一次一退。** 每次命令新建自己连浏览器、干完活退出；Chrome 本身留在后台，
   下次命令通过 `<profile>\DevToolsActivePort` 自动附着（实测 0.19–0.4s）。
   → **不要指望两次命令之间保留「页面状态」，只保留 cookie/localStorage。**
2. **必须优雅关闭。** 登录态靠 Chrome 自己落盘；`kill` 掉进程会让 cookie 全丢（已实测对照）。
   要关就用 `chrome.py close`（内部走 CDP `Browser.close`），**不要 `taskkill`**。
   用户手动点窗口的 × 也等价于强杀，**登录态会丢**——登录完不要手动关窗。
3. **一个 profile 同一时刻只能有一个浏览器。** 已有一个在跑时，即使传 `--headful` 也只会附着到它。
4. **登录态是全局共享的。** 所有站点都在同一个专用 profile 里，和用户的日常 Chrome 完全隔离。
   代价：首次登录每个站点都要手动一次。
5. **锁只覆盖启动段。** 登录闸门跑着的时候，别的 `render`/`cookies` 命令照样能用（各开各的标签页）。
6. **`--scroll` 不会再导航一次。** 它在首次渲染之后滚动并重新读页面，懒加载出来的内容不会丢。

## 已实测的耗时（判断该不该用它）

| 场景 | 耗时 |
|---|---|
| 附着到已运行的浏览器 | 0.2–0.4s |
| 冷启动（profile 已存在） | ~0.5–2.5s |
| 单次导航（同域热） | 0.15–1.8s |
| 截图 | 82–93ms |
| 对比 `fetch.py` 抓同样内容 | ~0.02s |

→ **`fetch.py` 能干的活，别用 chrome-bridge。** 差两个数量级。

## 子命令

| 命令 | 用途 | 关键参数 |
|---|---|---|
| `render <url>` | 渲染后正文 | `-o` 落盘（长页面必须）、`--screenshot`、`--wait stable\|networkidle\|load`、`--wait-for <sel>`、`--scroll N`、`--full-html` |
| `snapshot --url <url>` | 截图 | `-o` 输出路径 |
| `text <url>` | 只取正文 | `--selector` 限定 CSS 元素 |
| `cookies <domain>` | 导出 cookie | `--values`（带值）、`--format json` |
| `login <url>` | 登录闸门 | `--timeout`、`--shot`、`--interval` |
| `fill <url>` | **一次填完整张表单** | `--field "SEL=VALUE"`（可重复）、`--submit-selector`、`--click-selector` |
| `type <url> <sel> <text>` | 单字段输入 | `--submit-selector`、`--submit`（Enter） |
| `click <url> <sel>` | 点击元素 | — |
| `download <url>` | 触发下载 | `-o` 目录 |
| `attach` | 诊断浏览器状态 | 无参 |
| `close` | 优雅关闭 | 无参 |

全局参数：`--profile <目录>`（默认 `~/.claude/chrome-bridge/profile`）、`--chrome-arg <参数>`
（透传 Chrome flag，如 `--chrome-arg=--proxy-server=...`；**危险 flag 会被拒绝**，见「安全边界」）。

环境变量：`CHROME_BRIDGE_PROFILE`（不改 `--profile` 时的默认 profile 目录）、
`CHROME_BRIDGE_CHROME`（指定 chrome 可执行文件路径，找不到浏览器时用）。

退出码：`0` 成功；`1` 一般错误（Chrome 启动失败、页面异常等）；`2` `login` 超时未检测到登录态
（页面已截图，状态在 stdout 的 JSON 里）；`3` **`render --wait-for` 等不到目标元素**（页面仍输出到
stdout / `-o`，meta 里 `timed_out=true`）；`4` 输入错误（非法 CSS 选择器、被拒绝的 `--chrome-arg`）。

`--headful` 例外：它在全局和各抓取类子命令上都注册了，**放在子命令前或后都可以**
（`attach` / `close` 这两个元命令上没有，用不到）；
`--profile` / `--chrome-arg` 只能放在子命令**之前**。

### ⚠️ 表单登录要用 `fill`，不能分多次 `type`

**每次调用都是一次新导航**，所以「先填账号、再填密码」这种分两步的做法，第二步会把第一步的输入冲掉。
要填多字段就走一条 `fill`：

```powershell
python $CB fill "https://x.com/login" --field "#user=alice" --field "#pass=secret" --submit-selector "#submit"
# 属性选择器也可以；解析时跳过方括号/引号内的 =，取括号外的第一个 = 作分隔符
python $CB fill "https://x.com/login" --field "input[name=user]=alice" --submit-enter
# 值里也可以带 =
python $CB fill "https://x.com/login" --field "#pass=a=b"
```

`type` 只适合「单字段 + 回车」的场景（如搜索框）。

## 等待策略：`--wait` 怎么选

| 值 | 含义 | 何时用 |
|---|---|---|
| `stable`（默认） | load 后**至少观察 3.5s**，之后 DOM 文本长度稳定 0.8s 才返回 | 拿不准时；SPA |
| `networkidle` | load 后网络静默 1.5s | 接口驱动的列表页 |
| `load` | 只等 load 事件 | **确定是静态页时首选**（比 stable 快 4 倍） |

**为什么 `stable` 不能提前返回**：渲染发生之前，静态页和慢 SPA 在 DOM 上无法区分
（都是一段长度不变的内容 / 空壳），也都没有网络活动。任何「看起来稳定了」的提前退出
都会把慢 SPA 截断在半渲染状态。所以默认宁可多等 3.5 秒。

两个精确手段：

- **`--wait-for "#content"`** —— 等到该元素出现且有文本才返回。**唯一确定性的等待方式**，知道目标元素时优先用
- **`--min-wait 6`** —— 渲染更慢（5–6 秒）就调大窗口

实测参考（本地金丝雀站，暖启动，不含 Chrome 冷启动的 ~1s）：

| 场景 | stable（默认 3.5） | --wait load |
|---|---|---|
| 静态页 | 4.3s | 0.9s |
| load 后 1.2s 渲染 | 4.4s ✅ | 0.9s，只拿到 loading |
| load 后 3s 渲染 | 4.5s ✅（3.5 秒窗口刚好够） | 拿不到 |

→ **静态页用 `--wait load` 快 4 倍以上。** 确定不了就别省，stable 的默认值买的是正确性。

## 登录闸门怎么跑（模型侧流程）

**这是本 skill 最重要的交互。** `login` 会**阻塞**直到登录成功或超时（默认 300s），期间模型这边是空转的。
所以按这个流程走：

1. **后台启动**（否则会卡住整个回合，用户没法回话）：
   ```
   python $CB login <登录页URL> --timeout 420 --shot login.png       # run_in_background=true
   ```
   ⚠️ Windows 上超时会被终端环境（如企业终端超时）截断，留足余量；超时值是「等多久」不是「多久一定结束」。
2. **等 3–5 秒，Read 那张 `login.png`**，确认二维码/登录框清晰可见。
3. **把二维码展示给用户**（截图路径已给出），明确说：「请用手机扫码，扫完我这边会自动检测」。
   **不要**反复刷截图——二维码不会变，刷屏只会淹没对话。
4. 后台任务结束时会给你 JSON：
   - `{"status":"logged_in", "reason":"...", "session_hit":[...]}` → 成功，接着 `cookies --values`
   - `{"status":"timeout", "screenshot":"..."}` → 超时，**Read 新的截图**看卡在哪（验证码没通过？扫错账号？）
   - `{"status":"already_logged_in", ...}` → 本来就有登录态
5. 登录成功的判据（`reason` 字段会告诉你命中了哪条）：
   - **A. 命中已知登录 cookie**（`SESSDATA`/`MUSIC_U`/`pt_key`…）——最强证据，即使在 `/login` 路径上也成立
   - **B. 页面出现登录后特征**（「退出登录」「个人中心」…）且不在登录路径上——对 cookie 名不常见的站点最可靠
   - **C. 探测标签页**：扫码页通常不会自己刷新，所以脚本会另开只读标签页重访一次，
     看站点是否已把这次访问当成登录用户（成功时 `reason` 以「探测标签页：」开头）

   **不使用**「新增 cookie 数 ≥ N」这种兜底——游客 cookie 和追踪 cookie 同样会新增，
   实测会把未登录页面判成 `logged_in`。若 300 秒内三条都不成立，返回 `timeout` 并附截图，
   而不是猜测。

**不要**替用户输账号密码，**不要**点击验证码——AI 只做只读探测（取 URL、查 cookie、截图）。

登录完成后**不要手动关浏览器窗口**（会丢登录态）；要么留着（默认），要么用 `chrome.py close`。

## 与 fetch.py 的分工

```
未登录内容 / API / 内网          → fetch.py（20ms 级）
登录后，静态可解析               → chrome.py cookies --values → fetch.py --header "Cookie: ..."
登录后，JS 渲染                  → chrome.py render
需要人工过闸                     → chrome.py login → cookies → render
```

拿到 cookie 后**优先回 fetch.py**：比每次开浏览器渲染快一个数量级，也不占 profile 锁。

## 安全边界

- **`cookies --values` 输出的是会话令牌明文**，会进命令历史和模型上下文。只在确实需要接力时才带 `--values`；
  其余场景用默认的脱敏模式（只列 cookie 名，够用来判断「有没有登录」）。
- profile 目录含加密后的登录态，**不要**提交进 git、不要复制给别的机器。
- 以下三类 `--chrome-arg` **会被 chrome.py 直接拒绝（退出码 4）**，不只是文档建议：
  `--user-data-dir`（覆盖专用 profile）、`--remote-debugging-address`（把调试端口暴露到局域网）、
  `--disable-features=DevToolsDebuggingRestrictions`（让本机任意进程接管浏览器调试口）。
- 调试端口只绑 `127.0.0.1`（启动参数里显式写死，不依赖 Chrome 默认绑定），且用完建议 `close`，不留常驻端口。

## 排障

| 现象 | 原因 / 对策 |
|---|---|
| `另一个 chrome-bridge 正在使用该 profile` | 两个进程同时判定「浏览器没在跑」并抢启动。等 2 秒重试即可；持续出现说明有僵尸进程 |
| 启动超时 | 看是不是有残留 Chrome 占着 profile；`attach` 诊断，必要时 `close` 或手动结束 |
| `render` 正文比截图里看到的少 | 内容还在懒加载/延迟渲染。知道目标元素就加 `--wait-for "#main"`；否则 `--min-wait 6 --scroll 3` |
| `render` 每次都慢 3–4 秒 | `stable` 的固定观察窗口。确定是静态页就用 `--wait load`（快 4 倍） |
| 页面是「无法访问此网站 / ERR_CONNECTION_RESET」 | 网络层问题，不是脚本问题；该站可能被墙/OEM 代理拦截 |
| 登录一直 timeout | 读 `--shot` 截图；常见是二维码过期（重新跑一次即可）或二次验证 |
| 关不掉浏览器 | `taskkill /IM chrome.exe /F` 会丢登录态；先试 `close` |
| 终端里中文显示乱码 | 输出是 UTF-8，但 PowerShell 可能按 GBK 解码。**不影响功能**（正文/落盘文件都正确），只是显示问题。要看清楚可 `chcp 65001` |
