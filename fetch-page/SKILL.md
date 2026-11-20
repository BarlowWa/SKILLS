---
name: fetch-page
description: 抓取网页或 HTTP 接口内容。本环境 WebFetch 被拦截，凡需要访问 URL、抓取网页、读取线上页面、抓链接、调 API 接口、抓登录后页面、访问局域网/内网服务器，一律用本 skill 的 fetch.py，不要用 WebFetch。默认提取正文，--raw 拿原始响应。
---

# 网页/接口抓取

**背景**：当前网络环境里 `WebFetch` 工具会被拦截（它回调 claude.ai 做域名校验失败），而直接 `curl` 或本脚本可正常访问。所以抓取任务一律用本脚本 `scripts/fetch.py`，不要用 WebFetch。

## 调用方式

脚本位于本 skill 目录下的 `scripts/fetch.py`。下文统一用 `~/.claude/skills/fetch-page/scripts/fetch.py` 表示；
**若本 skill 安装在其它位置，请把该前缀替换为实际的安装路径**（同一份文档里不要与简写混用）。

```bash
python ~/.claude/skills/fetch-page/scripts/fetch.py <url> [选项]
```

运行环境要求 **Python ≥ 3.10**（脚本使用了 `str | None` 联合类型语法），另需 `lxml`（已装）。

## 按目标类型选择参数

| 目标 | 命令要点 |
| ---- | -------- |
| 公开文章/网页 | `python ~/.claude/skills/fetch-page/scripts/fetch.py <url>` — 自动提取标题 + 正文纯文本 |
| API 接口（JSON） | 同上加 `--raw <url>` — 逐字节输出原始响应，不套正文提取 |
| 带 token 的 API | `--raw --header "Authorization: Bearer TOKEN" <url>` |
| POST 到 API | `--raw --method POST --header "Content-Type: application/json" --data '{"q":"x"}' <url>` |
| 登录后页面 | 先 `--method POST --cookie-jar <file> --data "user=..&pass=.." <login_url>` 存 session，再带同一 `--cookie-jar` 抓内页（**`--method` 默认 GET，登录必须显式写 POST**，否则凭据以 GET 请求体发出、登录静默失败） |
| 局域网/自签证书 | 加 `--insecure` 跳过证书校验（HTTP 则不需要） |
| Confluence / Seraph 登录 | 登录 POST 必须带 `--referer "<登录页URL>"`，否则返回 401（`X-Seraph-LoginReason` 头校验来源页） |

## 常用选项

- `--raw` — **逐字节**输出响应体（API/JSON/任意二进制，不经解码、不做字符截断）；文本页面若显示乱码，加 `--encoding`
- `--encoding <charset>` — 显式指定响应字符集（如 `gb18030`）。带 `--raw` 时按该字符集解码为文本再输出（此时才受 `--max-chars` 截断）；抓正文时覆盖自动探测
- `--selector "css"` — 限定 HTML 正文范围。**需另装 `cssselect`**（`pip install cssselect`）——当前环境未装，未装时该选项会走回退分支、等同于不限定，见「注意事项」
- `--max-chars N` — 输出字符数上限（默认 60000，`0` 不限，**负值会被拒绝**）；超出会截断并在 stderr 提示
- `--method GET|POST|PUT|DELETE` — HTTP 方法
- `--data "..."` — 请求体
- `--header "Name: value"` — 自定义请求头，可重复
- `--referer <url>` — 设置 Referer 头（Confluence/Seraph 等登录必需）
- `--cookie-jar <file>` — cookie 持久化文件，登录态复用（读取时不改写原文件、用临时副本；抓到响应后会把新 cookie 保存回原 jar，见「注意事项」）
- `--insecure` — 跳过 TLS 证书校验
- `--timeout <秒>` — 默认 20

## 排障：输出为空或异常

stderr 会给出提示，按提示对照：

| 现象 | 原因 | 对策 |
| ---- | ---- | ---- |
| `正文几乎为空` | 页面靠 JS 渲染（SPA） | 用 `--raw` 看原始响应；内容确在 JS 里则此法抓不到，改用 `chrome-bridge render`（见下节） |
| `正文几乎为空` | 需要登录态 | 先 `--method POST --cookie-jar <file> --data "..." <login_url>` 登录，再带同一 jar 抓内页；扫码/短信登录用 `chrome-bridge login --headful --timeout 420`（人工过闸用 login，不用 render） |
| `正文几乎为空` | 反爬拦截，返回验证页 | 检查 HTTP 状态码与 `--raw` 返回内容；Cloudflare 类需人工过闸时用 `chrome-bridge login --headful --timeout 420`（登录闸门会阻塞并保持窗口；`render` 不等用户交互，别用它过闸） |
| 正文乱码 | 自动探测的字符集不对 | 加 `--encoding <字符集>`（如 `gb18030`）显式指定；可先 `--raw` 看字节、或用文件头/HTTP 头判断编码 |
| `--raw` 输出乱码 | `--raw` 是**逐字节**输出，不做解码，终端按自身编码显示非 UTF-8 文本会乱 | 文本类目标加 `--encoding <字符集>`；真正的二进制（图片/压缩包）应重定向到文件而不是看终端 |
| 内容被截断 | 超出 `--max-chars` | 调大 `--max-chars`；或用 `--selector` 缩小范围（**前提是已装 `cssselect`**，否则无效） |
| 连接被重置 / `ERR_CONNECTION_RESET` | 网络层（墙 / 代理 / 企业策略）拦截 | 不是脚本问题。换网络或走代理。`chrome-bridge render` **只在拦截基于浏览器特征**（TLS 指纹、UA、JS 挑战）时有帮助；纯 TCP/IP 层的 reset 换浏览器同样被拦——判断不了就先 `chrome-bridge render` 试一次，仍 reset 即属网络层 |

## 抓不到时：升级到 chrome-bridge

**页面需要登录、是 JS 渲染的 SPA、或被人机验证/Cloudflare 拦住时，`fetch.py` 原理上就抓不到**——
它不做 JS 执行、也不持浏览器身份。这时用配套的 **`chrome-bridge` skill**（`~/.claude/skills/chrome-bridge/scripts/chrome.py`）：

```powershell
$CB = "$HOME\.claude\skills\chrome-bridge\scripts\chrome.py"
$FETCH = "$HOME\.claude\skills\fetch-page\scripts\fetch.py"

# ① JS 渲染的页面 → 取渲染后正文（知道目标元素时加 --wait-for "#main" 最稳）
python $CB render "https://www.example.com" -o out.md

# ② 需要登录 → 登录闸门（把截图给用户扫），然后导出 cookie
python $CB login "https://passport.example.com/login" --timeout 420 --shot login.png
$h = python $CB cookies example.com --values

# ③ 拿到 cookie 后回 fetch.py 接力（比每次开浏览器快一个数量级）
python $FETCH --raw --header "Cookie: $h" "https://api.example.com/x"

# ④ 用完优雅关闭（不关不丢登录态，但会占着浏览器与 profile 锁）
python $CB close
```

> PowerShell 不展开 `~`，上面用 `$HOME` 拼路径；直接写 `~/.claude/...` 会被 python 当成字面量路径而报错。

分工原则：**fetch.py 优先**，只有它原理上做不到时才开浏览器；拿到 cookie 后立刻回到 fetch.py。
完整用法见 `chrome-bridge` 的 SKILL.md。

## 注意事项

- 只支持 `http` / `https`。`file://`、`ftp://`、`data:` 等其它 scheme（以及重定向到这些 scheme 的响应）一律报错退出、不发起读取——防止借本地文件 scheme 读到任意本机文件。**入口 scheme 非法与重定向目标 scheme 非法都返回退出码 2**（统一视作「目标非法/拒绝访问」）
- 默认对 HTML 会提取正文；对 `Content-Type: application/json` 会自动直接输出原始响应（无需加 `--raw`）
- **正文提取会做行内合并**（`<p>已处理 <b>3</b> 条</p>` → `已处理 3 条`），块级元素之间分段，标题转 `##`，链接转 `[文本](url)`，并反转义 HTML 实体
- 输出默认截断到 60000 字符，避免长页面挤爆上下文；需要全文时显式调大 `--max-chars`
- **只有显式 `--raw`** 逐字节输出时不受 `--max-chars` 限制（二进制无法按字符截断）；需要限制长度就配合 `--encoding` 走文本路径，或重定向到文件。**JSON 自动直出仍按 `--max-chars` 截断并提示**，与正文提取一致
- 登录态用 MozillaCookieJar，`--cookie-jar` 指向同一文件即可跨命令复用
- `--cookie-jar` 的**读取**阶段不会改写原文件：为兼容 curl 格式（`#HttpOnly_` 前缀、`expires=0`）做的规范化写进临时副本，只用于本次加载。抓到响应后会把新 cookie 保存回原 jar，但 `MozillaCookieJar.save()` 是**整份重写**——不是「保留原有条目并追加」：原文件里的非 cookie 行会丢失、`expires=0` 会被写成空字段（同样是 session cookie 语义）、换行可能变为 CRLF。文件若同时给 curl 复用，建议各用一份 jar
- `--selector` 需 `cssselect`（**当前未装，`--selector` 会失效**并回退为全文提取）。无 requests/bs4
- 抓到的正文可能较长，应只向用户展示关键结论，不要整篇倾倒
