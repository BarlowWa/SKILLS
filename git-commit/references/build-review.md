# 构建 / 配置 / 脚本变更审查指南

供 git-commit 派发的**构建 / 配置 / 脚本审查 agent** 使用（与 `doc-review.md` 的文档审查并列，
不是文档审查的一部分）。

## 0. 审查对象

纳入：shell/PowerShell/Batch 脚本（`.sh` `.bash` `.zsh` `.ps1` `.bat` `.cmd`）；CI 配置（`.github/workflows/*`、
`.gitlab-ci.yml`、`Jenkinsfile`、`.circleci/*`、`azure-pipelines.yml`）；构建文件（`Makefile`/`*.mk`、
`Dockerfile`/`Containerfile`、`CMakeLists.txt`/`*.cmake`、`Cargo.toml`、`pom.xml`/`*.xml`、`build.gradle*`、
`package.json`、`pyproject.toml`、`setup.py`、`go.mod`）；项目配置（`.gitignore`/`.gitattributes`/`.dockerignore`、
`.yml` `.yaml` `.toml` `.ini` `.conf` `.properties` `.json` `.jsonc`、`.env.example`）。

不纳入：lockfile（见 §3，**优先于 `.json` 匹配**）、生成物（见 §3）、被忽略目录（`vendor/` `build/`
`node_modules/` `dist/`）。编程语言的源码文件（含 C/C++/Rust/Java/Python 以及 Go/JS/TS/Ruby/Kotlin 等）
一律归代码审查，**不在本类兜底**；未识别的非源码文本按文档审查或显式豁免处理。

这些文件的约束是**可执行行为与安全风险**，不是自然语言陈述；因此不走文档审查的完整性/一致性口径
（那是 `doc-review.md` §1–§8），也不走 code-rules 的语言规则（那些规则面向 C++/Rust/Java/Python 源码，
不覆盖 YAML/TOML/Makefile 语法）。两者判据互不通用，不得混用。

本文是构建 / 配置 / 脚本审查的唯一细则来源；SKILL.md 只负责触发与派发，不重复这里的判据。

## 1. 检查清单

| 类别 | 检查项 | 判据 | 级别 |
|---|---|---|---|
| shell 脚本 | 错误处理 | 有 `set -euo pipefail`；或无管道失败但显式 `\|\| exit` / 检查 `$?` / `set -e` | 裸脚本无任何错误处理：warning；错误处理**形同虚设**（`set -e` 后紧跟被吞的 `\|\| true`、命令在 `if`/管道左侧导致 `-e` 失效且无说明）：blocker |
| shell 脚本 | 引号与变量展开 | 变量展开加引号（`"$VAR"`），`[[ ]]` 优先于 `[ ]`；`$*` 不用于需要逐参数处理的场景 | 未加引号导致分词/通配风险（`rm $DIR`、`[ $x = y ]`）：warning；在 `rm`/`mv`/重定向目标等破坏性位置：blocker |
| shell 脚本 | 危险命令 | `rm -rf`/`mv`/`dd`/`>` 的目标不得直接来自未校验变量；`xargs` 不带 `-r` 且有空格/换行风险 | `rm -rf $VAR` / `rm -rf "$VAR"` 且 `VAR` 可能为空或是外部输入：blocker |
| shell 脚本 | 密钥泄漏 | 参照 code-rules **G-SECRET**：密码、Token、私钥以字面量写入脚本 | 命中即 blocker |
| shell 脚本 | 命令注入 | 参照 code-rules **G-CMDINJ**：外部可控字符串拼进 `sh -c`/`eval`/未加引号的命令替换 | 命中即 blocker |
| CI 配置 | 密钥明文 | workflow / pipeline 文件中出现明文密钥、Token、私钥；或把 `secrets.*` 直接 `echo`/写日志 | 明文密钥：blocker；日志泄露风险：blocker |
| CI 配置 | 权限范围 | 使用 `permissions:` 且最小化（`contents: read` 起步）；`pull_request_target` + 检出 PR 代码 + 使用仓库密钥的组合 | 权限全开或 `write-all` 且无说明：warning；`pull_request_target` 执行不可信 PR 代码且持有写权限/密钥：blocker |
| CI 配置 | 触发条件 | `on:` 分支/路径过滤、`workflow_dispatch` 的输入校验、是否会在 fork PR 上执行 | 触发范围意外扩大（如 `on: [push, pull_request]` 且部署步骤无分支守卫）：warning |
| 构建文件 | 依赖可复现 | 依赖是否声明了精确版本或锁定（`==` / 精确 tag / lockfile 配合）；`latest`、无版本约束、`FROM` 无 tag/digest | `FROM` 无 tag 或依赖用 `latest`：warning；同时影响部署产物：blocker |
| 构建文件 | 硬编码环境 | 绝对路径、本机用户名、内网地址、凭证路径写死在构建脚本 / Dockerfile / Makefile | 硬编码凭证或仅本机存在的路径导致构建在其他环境失败：blocker；提示性硬编码（可覆盖的默认值）：warning |
| 配置文件 | 语义变更 | `.gitignore` 误伤源码、`.dockerignore` 漏掉密钥、`.env.example` 写入真实值、权限/忽略规则反转 | 导致密钥进入版本控制或产物：blocker；其余按影响给 warning |
| PowerShell / Batch | 错误处理与注入 | `$ErrorActionPreference = 'Stop'` 或显式检查 `$LASTEXITCODE`；`Invoke-Expression` / `cmd /c` 拼接外部输入 | 未处理失败且后续步骤依赖其结果：warning；`Invoke-Expression` 拼外部可控字符串（G-CMDINJ）：blocker |
| 依赖清单（`*.xml` / `go.mod` / `*.properties`） | 版本与凭证 | Maven/Gradle 依赖版本可变范围、`go.mod` 替换指向本地路径、`.properties` 内明文口令 | 明文口令/Token：blocker；依赖版本不可复现：warning |

**检查项编号**（报告里用这些 ID 指代，便于追溯）：
`shell-EF`（shell 错误处理）、`shell-quote`（引号/变量展开）、`shell-danger`（危险命令）、`shell-secret`
（密钥，引用 code-rules **G-SECRET**）、`shell-inject`（命令注入，引用 code-rules **G-CMDINJ**）、`ci-secret`
（CI 密钥明文）、`ci-perm`（CI 权限）、`ci-trigger`（CI 触发）、`build-repro`（依赖可复现）、`build-path`
（硬编码环境）、`config-semantics`（配置语义变更）、`ps-error` / `ps-inject`（PowerShell/Batch）、
`dep-version` / `dep-secret`（依赖清单）。

级别口径：blocker = 会导致安全事故（密钥外泄 / 命令注入 / 不可逆删除）或让提交过程本身出错（构建/CI 必然失败且无回退）；
warning = 可改进，不阻塞。与 `arch-review` 等技能的级别换算按 SKILL.md「跨技能级别换算与去重」执行——
本节检查项直接产出本技能级别，无需二次换算。

## 2. 证据要求

- 每条 blocker 必须附 `文件:行` + 原文片段 + 反证（命令输出、文件位置或规则条文）。
- shell 语法类问题可跑 `bash -n <脚本>`、`shellcheck <脚本>`（只读）作为证据；解释器不可用或 shellcheck 未安装时
  标「未能判定」，不据此判 blocker。
- Dockerfile 需要核对时只用 `docker build --check`（不实际构建）或人工阅读；不得真的构建/推送镜像。
- CI 配置无法在本地验证实际权限与密钥时，按文本证据判定；「该密钥是否真实有效」超出审查范围，标「未能判定」。

## 3. 不做专项审查的类别（显式豁免）

- **lockfile**（`package-lock.json`、`yarn.lock`、`Cargo.lock`、`poetry.lock`、`uv.lock`、`pnpm-lock.yaml`、
  `go.sum` 等）：包管理器产出，逐行审阅无意义。**原因**：内容是求解结果而非人工决策，真正需要审的是
  「依赖声明是否同时改动了」——若 lockfile 变了而对应 manifest（`package.json` / `Cargo.toml` / `pyproject.toml`）
  未在本提交范围内，报 warning「lockfile 变更缺少对应声明变更」。
- **生成物**（自动生成的文档、构建产物、代码生成器输出）：按 `doc-review.md` §1「不纳入」处理；
  若源文件未改而生成物被改动，报 warning「生成物疑似手工修改」。
- **被忽略目录**（`vendor/`、`build/`、`node_modules/`、`dist/`）不进入提交范围，不审。
- 上述类别**必须在确认页与审查输出中显式列出「已豁免 + 原因」**，不得静默略过——静默落空与服务端错误无法区分。
