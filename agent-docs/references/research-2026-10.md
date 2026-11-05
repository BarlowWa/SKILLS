# Agent 文档组织：调研来源与证据（2026-10-19）

> **时效声明**：本文的数字、行数上限、工具行为均为 2026-10 的核实结果；
> 2026-11-04 依据当前官方文档修订了 `paths:` 加载行为与「七种手段」口径。
> 引用前先核对原始文档；判据（如「删掉不会让 agent 犯错就删」）比数字稳定得多。
> `last-verified: 2026-11-04`

## 一、Claude Code 官方规定

来源：<https://code.claude.com/docs/en/memory>

- **四级指令文件**：Managed policy → User `~/.claude/CLAUDE.md` → Project `./CLAUDE.md`
  或 `./.claude/CLAUDE.md` → Local `./CLAUDE.local.md`（入 gitignore）。启动加载 cwd 及
  所有上级，root→cwd 顺序拼接。
- **嵌套文件按需加载**：子目录 CLAUDE.md 不在启动时加载，"loads each one once Claude
  reads, writes, or edits another file in that subdirectory"。
- **`@import`**：启动即展开，最多 4 跳。原文："Imports help you organize a long file but
  don't reduce its context cost"。
- **长度**："target under 200 lines per CLAUDE.md file. Longer files consume more context
  and reduce adherence."
- **矛盾**："If two instructions contradict each other, Claude may pick one arbitrarily."
- **AGENTS.md**：可直接替代 CLAUDE.md；共用一份时用 `@AGENTS.md` 导入（Windows 上优于
  symlink）。Claude Code v2.1.277+ 在无 CLAUDE.md 时直接读 AGENTS.md。
- **工具**：`/memory` 编辑；`/context` 查看已加载内容；`/doctor` 裁剪冗余；
  `/doctor prompt-audit`（v2.1.283+）查过时引用与矛盾指令。
- **auto memory**：存 `~/.claude/projects/<project>/memory/`，`MEMORY.md` 是索引，
  每会话载前 200 行或 25KB。**只从项目目录加载，不是全局机制。**

来源：<https://code.claude.com/docs/en/best-practices>

- 该写：agent 猜不到的 Bash 命令、偏离默认的风格、测试方式、仓库礼仪、架构决策、
  环境怪癖、gotcha。
- 不该写：代码可推断者、通用语言规范、详细 API 文档、易变信息、长篇教程、逐文件说明。
- 判据 *"Would removing this cause Claude to make mistakes? If not, cut it."* 在官方
  best-practices / memory 全文检索**未命中**（2026-11-04 核实），属**内部实践总结 / 非官方
  原文**；判据本身可用，但引用时勿冠以官方出处。
- 膨胀的代价是真实存在的：官方点名 `IMPORTANT` 堆叠会反噬（「piling on emphasis mostly
  makes Claude over-apply the rule」），文件过长会让核心行「gets lost」——参见下方的
  确定性/非确定性二分（同一页）。
- 确定性约束放 hooks：官方把指令分为 non-deterministic（CLAUDE.md / skill，模型可自行判断）
  与 **deterministic**（hook / deny rule / managed setting，harness 强制执行）两类；
  必须每次发生的事归后者。

### 1.1 `paths:` 门控的加载行为（2026-11-04 依据当前官方文档修订）

**当前行为（官方文档，v2.1.212）**：带 `paths:` 的路径规则是**按需**的——「A path-scoped
rule loads when Claude uses the Read, Write, or Edit tool on a matching file」，并且「when
Claude views a matching file with a Bash command that counts as a read, such as `cat` or
`head`」（<https://code.claude.com/docs/en/memory.md#path-specific-rules>）。**不带
`paths:` 的 `.claude/rules/` 在 launch 时即载入**：「Rules without `paths` frontmatter are
loaded at launch with the same priority as `.claude/CLAUDE.md`」。嵌套 `CLAUDE.md` 另属一条
机制：子目录文件不在 launch 载入，「Claude Code loads each one once Claude reads, writes,
or edits another file in that subdirectory」。

> ⚠️ **v2.1.211 变更点的常见误读**：文档「Before v2.1.211, rules that load on demand …
> loaded even when `project` was excluded」指的是**按需载入的规则不再绕过
> `--setting-sources` 排除 project 设置**；它**不是**「路径规则从按需改成 launch 载入」。
> 路径规则始终是按需的。

**历史 issue（旧版记录，仅作历史，勿当当前事实）**：

- <https://github.com/anthropics/claude-code/issues/62049>（**closed，`not_planned`**；标签
  `bug`、`has repro`、`stale`、`platform:windows`、`platform:vscode`、`area:skills`）：报告
  skill 的 `paths:` 从未触发自动加载。**上游附有复现步骤（`has repro`），但关闭结论为
  not_planned / stale**——「附有复现步骤」不等于「已在本机复现或已定位根因」，只能作为历史
  记录，勿当当前事实。
- <https://github.com/anthropics/claude-code/issues/90004>（**open**；标签 `bug`、`has repro`、
  `platform:linux`、`area:tools`、`area:skills`）：auto 模式的 `bashFirst` 让模型用 Bash 读写
  文件，而门控只监听 Read/Edit/Write → 可能不激活。**上游附有复现步骤（`has repro`）**；
  注：官方文档明确「Bash 中 `cat`/`head` 这类算作 read 的命令会触发」，故该 issue 描述的
  可能只是一部分 Bash 场景。**本机是否仍可复现：未能判定**（未在当前版本实测）。
- <https://github.com/anthropics/claude-code/issues/93248>（**open**；标签 `enhancement`、
  `area:core`、`area:skills`）：**这是 FEATURE 请求，绝不是已确认缺陷**——作者希望 `paths:`
  也对「新建文件」的 target path 匹配（当前只对 Read/Write/Edit 匹配）。现状「新建文件不
  触发」属设计行为，非 bug。（标注为 `enhancement`，无 `bug` / `has repro` 标签。）

**结论（经验性建议，不是「因为它坏了」）**：按扩展名/路径分流规则时，**优先**在 SKILL.md
正文放「扩展名 → references 文件」路由表由模型显式 Read，并写明「识别成功但无对应文件 →
应用通用基线并注明」。理由：路由表**可读、可测、不依赖任何触发机制**，比隐式的 `paths:`
更可控；即便路径规则可靠，显式路由也更易审查。（本仓库 `code-rules` 即按此实现。）
「`paths:` 当前不可靠」这一硬结论**未能判定**——`bashFirst` 场景（#90004）是否仍存在，
需在当前版本实测确认。


## 二、知识该放哪（官方博客）

来源：<https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more>

| 载体 | 加载方式 | 适用 |
|---|---|---|
| CLAUDE.md | 每会话全文 | "always do X"、构建命令、架构 |
| `.claude/rules/` | 无 `paths:` 则 launch 载入；带 `paths:` 则对匹配文件 Read/Write/Edit 时按需载入 | 语言/目录特定约束 |
| Skill | 启动仅 name+description，正文按需 | 多步 playbook、参考文档 |
| Subagent | 独立窗口，只回摘要 | 深搜、并行、防污染主上下文 |
| Hook | 事件触发，零常驻 | 必须每次发生的事 |
| Output styles | 每会话进 system prompt，不被 compact，首请求后缓存 | 全局行为/人格；遵从度最高，须节制 |
| `--append-system-prompt` | 调用时传入，仅对该次调用生效、不持久 | 特定编码标准/输出格式/领域知识 |

**官方口径是「七种手段」**：CLAUDE.md、rules、skills、subagents、hooks、**output styles**、
**appending the system prompt**。「There are seven methods for instructing Claude's
behavior」。plugin / managed settings **不是第八种指令手段**，而是其中若干手段的**打包分发层**
（「bundle many of them (skills, subagents, hooks, output styles) as a plugin」；
skill 也可「distribute it through a plugin or managed settings」，
<https://code.claude.com/docs/en/skills>）。

触发规则：同一约定**错第二次** → 写进 CLAUDE.md；同一 playbook **第三次粘贴** → 做成 skill；
30 行流程 → skill；"never" 类硬约束 → hook / permissions。

预算数字（官方）：
- skill 的 description + when_to_use 在 listing 中截断于 **1,536 字符**
  （<https://code.claude.com/docs/en/skills>）。
- subagent 描述合计超 **15,000 tokens** 时启动告警。
- SKILL.md 正文 **< 500 行**理想（skill-creator）；Agent Skills 规范建议 instructions
  **< 5,000 tokens**、description ≤ 1,024 字符（<https://agentskills.io/specification>）。

## 三、Anthropic Engineering 博客

- **Effective context engineering**（2025-09-29）：
  <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
  注意力预算是稀缺资源；目标是 "smallest possible set of high-signal tokens"。
  Claude Code 是混合策略："CLAUDE.md files are naively dropped into context up front"，
  其余靠 glob/grep 即时检索。长任务用 compaction、结构化笔记、子 agent（只回约 1,000–2,000 tokens）。
- **Agent Skills**：
  <https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills>
  三级渐进披露——启动预载 name+description，命中才读 SKILL.md 正文，附文件按需。
  "Progressive disclosure is the core design principle."
- **Writing tools for agents**：
  <https://www.anthropic.com/engineering/writing-tools-for-agents>
  返回高信号、token 高效的上下文；Claude Code 工具响应默认上限 25,000 tokens。
- **Long-running agents**：
  <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
  用 `feature_list.json`、进度文件、`init.sh` 把状态放文件按需读取，而非全塞进常驻上下文。

## 四、跨工具标准与长度限制

| 工具 | 文件与机制 | 官方长度约束 |
|---|---|---|
| AGENTS.md（<https://agents.md/>，Linux Foundation 托管，6 万+ 仓库） | 纯 Markdown，无 schema；monorepo 用嵌套文件 | 无固定上限 |
| OpenAI Codex（<https://learn.chatgpt.com/docs/agent-configuration/agents-md>） | 从 Git 根逐级下走到 cwd，每目录取 `AGENTS.override.md` → `AGENTS.md` → fallback 列表第一项；近者优先 | 总量默认 **32 KiB**（`project_doc_max_bytes`） |
| Cursor Rules（<https://cursor.com/docs/context/rules>） | `.cursor/rules/*.mdc`，frontmatter `description` / `globs` / `alwaysApply`；同目录 `.md` 被忽略 | 单规则建议 **< 500 行** |
| GitHub Copilot（<https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions>） | `.github/copilot-instructions.md`（仓库级）；`.github/instructions/**/*.instructions.md`（`applyTo` glob，可 `excludeAgent`） | 生成指令的官方提示词要求「不超过 2 页」 |
| Windsurf/Devin（<https://docs.devin.ai/desktop/cascade/memories>） | `.devin/rules/*.md`，`trigger: always_on / model_decision / glob / manual` | 全局 **6,000 字符**、单文件 **12,000 字符** |
| Aider（<https://aider.chat/docs/usage/conventions.html>） | `CONVENTIONS.md` 经 `/read` 或 `.aider.conf.yml` 的 `read:` 常驻 | 无固定 |
| VS Code 汇总（<https://code.visualstudio.com/docs/agent-customization/custom-instructions>） | 指令源叠加；明确建议多 harness 共用同一格式，**不要依赖优先级解冲突** | 无 |

**Spec-driven 的持久/临时分层**：
- Spec Kit（<https://github.github.com/spec-kit/quickstart.html>）：
  `.specify/memory/constitution.md`（活契约）+ `specs/NNN-name/{spec,plan,tasks}.md`；
  feature 目录是**不可变历史**，`spec.md` 是活契约。
- Kiro（<https://kiro.dev/docs/steering/>）：`.kiro/steering/{product,tech,structure}.md`，
  frontmatter `inclusion: always | fileMatch | manual | auto`；`specs/<feature>/` 下
  `requirements.md` → `design.md` → `tasks.md`。

**单一事实来源的落地方式**：
- 原生支持：Claude Code v2.1.277+ 可读 AGENTS.md；可配置 `CLAUDE.md` + `AGENTS.md` 并用。
- 过渡做法：`CLAUDE.md` 内写 `@AGENTS.md`；Aider / Gemini CLI 用配置指向 AGENTS.md。
- 反面做法：同一规则复制两份——必然漂移。

## 五、真实仓库样本

| 仓库 | 结构 | 要点 |
|---|---|---|
| <https://github.com/anthropics/claude-code/blob/main/CLAUDE.md> | 根 CLAUDE.md 约 **40 行 / 2.2KB** | 只写 GitHub Actions 安全加固 3 条，并指向 `.github/scripts/check_workflow_hardening.py` 与豁免表——**文档配机械校验** |
| <https://github.com/apache/airflow/blob/main/AGENTS.md> | 根 AGENTS.md 约 250 行、20+ KB，另 3 个嵌套文件 | 用 `<!-- START generated-commands ... auto update -->` 标记自动生成命令段 |
| <https://github.com/gastownhall/beads/blob/main/AGENTS.md> | 根 AGENTS.md 末尾有**路由表** | "改到 cmd/bd/ → 先读 cmd/bd/AGENTS.md"；`CLAUDE.md` 是同级 AGENTS.md 的 symlink |
| openai/codex | 2026-09-30 删除仓库内 Codex 指引（19 文件 / −2,310 行），当前 main 无 AGENTS.md | 头部仓库长期保留指令文件**不是**必然规律 |

## 六、证据强度（区分「实验/案例」与「经验之谈」）

**有实验或案例支撑**：
- HumanLayer（2025-11-25）：<https://www.humanlayer.dev/blog/writing-a-good-claude-md>
  社区共识 <300 行、越短越好，自家根文件 <60 行；Claude Code 的系统提示已占约 50 条指令，
  总指令量约 150–200 条后遵循度下降；建议 progressive disclosure（`agent_docs/*.md` 按需读）、
  写 `file:line` 指针而非代码副本、别让 LLM 当 linter、别用 `/init` 自动生成后不管。
- IFScale（arXiv:2507.11538）：500 条指令下最强模型仅 68% 准确，且偏向靠前指令。
  <https://arxiv.org/abs/2507.11538>
- Lulla 等（arXiv:2601.20404）：10 仓库 124 PR 配对实验，有 AGENTS.md 时中位运行时间
  −28.64%、输出 token −16.58%，完成度相当。<https://arxiv.org/abs/2601.20404>
  （社区研究，非官方。）
- Chroma Context Rot（2025-07-14）：18 个模型，输入变长时性能非均匀下降。
  <https://research.trychroma.com/context-rot>
  ⚠️ 测的是通用长上下文，**未直接测 CLAUDE.md 长度**；「指令文件越长越被忽略」是合理外推。
- Codified Context（arXiv:2602.20478，2026-02）：10.8 万行 C# 项目、283 会话、19 个专家
  agent、34 份按需规格。**规格陈旧是首要失败模式**（战斗规格引用已迁移字段，agent 走废弃
  路径）。对策：session-start drift detector + 双周全量审阅。
  <https://arxiv.org/abs/2602.20478>
  ⚠️ 单开发者、观察性研究、无对照实验。

**经验之谈**：
- Geoffrey Huntley（2026-10）：<https://ghuntley.com/agency/>
  AGENTS.md 迟早漂移，改让 pre-commit hook 做确定性检查；主张每隔几个月删掉 skills /
  AGENTS.md 重新验证是否还有用。
- Builder.io：<https://www.builder.io/blog/agents-md>
  按文件给命令、给项目结构索引、嵌套 AGENTS.md 让各包保留自己的版本规则。
- rolker/agent_workspace issue #207：<https://github.com/rolker/agent_workspace/issues/207>
  四层漂移机制：计划里强制写 doc-impact → pre-commit 提示 → CI 只阻断高价值路径 →
  定期 audit。三种病因：diff-blindness、无检查点、判断过载。

## 七、失败模式与规避

| 失败模式 | 后果 | 规避 |
|---|---|---|
| 规则互相矛盾 | 模型任选其一，行为不稳定 | 定期审阅；`/doctor prompt-audit` |
| 把变更日志/历史塞进常驻文件 | 每会话付费、稀释注意力 | 历史进 `docs/changes` 或本地 plans |
| 复制多份 CLAUDE.md/AGENTS.md | 漂移、互相矛盾 | `@AGENTS.md` 或 symlink 单一真源 |
| 根常驻文件过长（官方建议每份 CLAUDE.md < 200 行；社区共识 < 300 行） | 规则被整体忽略 | 拆 path-scoped rules / 嵌套文件；import 不省 token |
| 文档与代码行为不符 | agent 按旧规格生成看似正确的错代码 | 指针替代副本 + CI/hook 校验 + 定期审计 |
| 活文档依赖被 gitignore 的路径 | 换机/克隆后规则失效 | 持久内容必须入库（见 flutter_bloc_app 先例） |
| 规则只写不验证 | 规则形同虚设 | 能机械检查的写成 CI/pre-commit |
| `/init` 自动生成后不再维护 | 低信号内容长期驻留 | 手写并逐行审阅 |

先例：<https://github.com/redjadet/flutter_bloc_app/blob/main/docs/plans/README.md>
——`docs/plans/` 整体 gitignore，但明确写「plan 成为耐久决策后要落到 ADR / change note /
topic owner，不要让活文档依赖被忽略的路径」，并在 README 维护 promotion 映射表。
