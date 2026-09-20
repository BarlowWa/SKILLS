---
name: fetch-page
description: 抓取网页或 HTTP 接口内容。本环境 WebFetch 被拦截，凡需要访问 URL、抓取网页、读取线上页面、抓链接、调 API 接口、抓登录后页面、访问局域网/内网服务器，一律用本 skill 的 fetch.py，不要用 WebFetch。默认提取正文，--raw 拿原始响应。
---

# 网页/接口抓取

**背景**：当前网络环境里 `WebFetch` 工具会被拦截（它回调 claude.ai 做域名校验失败），而直接 `curl` 或本脚本可正常访问。所以抓取任务一律用本脚本 `scripts/fetch.py`，不要用 WebFetch。

## 调用方式

脚本路径：`~/.claude/skills/fetch-page/scripts/fetch.py`

```bash
python ~/.claude/skills/fetch-page/scripts/fetch.py <url> [选项]
```

## 按目标类型选择参数

| 目标 | 命令要点 |
| ---- | -------- |
| 公开文章/网页 | `python fetch.py <url>` — 自动提取标题 + 正文纯文本 |
| API 接口（JSON） | `python fetch.py --raw <url>` — 输出原始响应，不套正文提取 |
| 带 token 的 API | `python fetch.py --raw --header "Authorization: Bearer TOKEN" <url>` |
| POST 到 API | `python fetch.py --raw --method POST --header "Content-Type: application/json" --data '{"q":"x"}' <url>` |
| 登录后页面 | 先 `--cookie-jar <file> --data "user=..&pass=.." <login_url>` 存 session，再带同一 `--cookie-jar` 抓内页 |
| 局域网/自签证书 | 加 `--insecure` 跳过证书校验（HTTP 则不需要） |
| Confluence / Seraph 登录 | 登录 POST 必须带 `--referer "<登录页URL>"`，否则返回 401（`X-Seraph-LoginReason` 头校验来源页） |

## 常用选项

- `--raw` — 输出原始响应体（API/JSON/二进制），不提取正文
- `--selector "css"` — 限定 HTML 正文范围
- `--max-chars N` — 输出字符数上限（默认 60000，`0` 不限）；超出会截断并在 stderr 提示
- `--method GET|POST|PUT|DELETE` — HTTP 方法
- `--data "..."` — 请求体
- `--header "Name: value"` — 自定义请求头，可重复
- `--referer <url>` — 设置 Referer 头（Confluence/Seraph 等登录必需）
- `--cookie-jar <file>` — cookie 持久化文件，登录态复用
- `--insecure` — 跳过 TLS 证书校验
- `--timeout <秒>` — 默认 20

## 排障：输出为空或异常

stderr 会给出提示，按提示对照：

| 现象 | 原因 | 对策 |
| ---- | ---- | ---- |
| `正文几乎为空` | 页面靠 JS 渲染（SPA） | 用 `--raw` 看原始响应；内容确在 JS 里则此法抓不到，需改用浏览器/接口 |
| `正文几乎为空` | 需要登录态 | 先 `--cookie-jar` 登录，再带同一 jar 抓内页 |
| `正文几乎为空` | 反爬拦截，返回验证页 | 检查 HTTP 状态码与 `--raw` 返回内容 |
| 乱码 | 编码判定错误 | 用 `--raw` 取原始字节自行判断；或检查页面 `charset` |
| 内容被截断 | 超出 `--max-chars` | 调大 `--max-chars`，或用 `--selector` 缩小范围 |

## 注意事项

- 默认对 HTML 会提取正文；对 `Content-Type: application/json` 会自动按原始输出（等效 --raw）
- **正文提取会做行内合并**（`<p>已处理 <b>3</b> 条</p>` → `已处理 3 条`），块级元素之间分段，标题转 `##`，链接转 `[文本](url)`，并反转义 HTML 实体
- 输出默认截断到 60000 字符，避免长页面挤爆上下文；需要全文时显式调大 `--max-chars`
- 登录态用 MozillaCookieJar，`--cookie-jar` 指向同一文件即可跨命令复用
- 脚本依赖仅标准库 + lxml（已装），无 requests/bs4
- 抓到的正文可能较长，应只向用户展示关键结论，不要整篇倾倒
