---
name: agent-docs
description: 设计或审查 AI agent 的项目文档组织——CLAUDE.md / AGENTS.md / .claude/rules / skills / docs 目录 / ADR。当要新建或精简常驻指令文件、判断某类知识该放常驻指令/按路径规则/按需文档/skill/subagent/hook、规划 monorepo 的文档分层、排查指令矛盾或文档漂移时使用。
---

# Agent 文档组织

给 Claude Code / Codex / Cursor 等 coding agent 写项目文档时，先做**知识分拣**，
再决定**放在哪一层**。核心目标：常驻上下文只保留高信号 token，其余按需加载。

项目级的具体结构（某个仓库的目录、约定）**写进项目自己的文件**，不要塞进本 skill——
这条对本 skill 自身同样适用：它的正文只放跨项目判据。

## 核心判据

1. **注意力预算**：上下文是有限资源，规则越多越容易被整体忽略（500 条指令下最强模型
   准确率约 68%，且偏向靠前指令）。目标是 "smallest possible set of high-signal tokens"。
2. **剔除判据**（内部实践总结，非官方原文）：*"Would removing this cause Claude to make mistakes? If not, cut it."* 拿不准就先删，agent 真犯错再加回。
3. **无矛盾**：两条指令冲突时，模型可能任选一条 → 行为不稳定。写规则前先检索是否已有相反规定。
4. **确定性优于劝告**：CLAUDE.md 里的规则是 advisory；必须每次都发生的事放 **hook / CI**。
5. **指针优于副本**：引用 `file:line` 或文档路径，不要复制代码/规格——副本必然漂移。

## 知识分拣表

| 知识类型 | 载体 | 加载时机 | 判据 |
|---|---|---|---|
| 每次都适用的硬规则、构建/测试命令、架构地图 | 根 `CLAUDE.md`（或 `AGENTS.md`） | 每会话全文 | 删掉它 agent 会犯错 |
| 只与某目录相关的约束 | 嵌套 `CLAUDE.md` | 按需：首次读/写/编辑该目录内文件时载入 | 放根文件会污染无关任务 |
| 只与某类文件相关的约束（如某扩展名） | `.claude/rules/*.md`（带 `paths:`） | 按需：对匹配文件 Read/Write/Edit 时载入；无 `paths` 的规则 launch 即载 | 跨多个目录、按文件类型生效 |
| 多步 playbook、参考文档、固定流程 | skill（`SKILL.md` + `references/`） | 启动只载 name+description，正文按需 | 同一流程第三次粘贴 |
| 打包分发给团队 | plugin / managed settings（分发层） | 封装下层的 skill / subagent / hook | 要跨仓库复用同一套设置 |
| 深搜、并行、会污染主上下文的调查 | subagent | 独立窗口，只回摘要 | 主上下文装不下或需隔离 |
| 绝不能发生的动作 | hook / permissions / CI | 事件触发，零常驻 | 违反一次就是事故 |
| 全局行为/人格调整 | output styles / `--append-system-prompt` | 输出风格每会话进 system prompt、不被 compact；append 仅本次调用追加、不持久 | 要改「怎么回答」；output style 遵从度最高、须节制 |
| 一次性过程记录、审计原始材料 | `.claude/plans/` 等本地目录 | 不加载 | 时点信息，可丢弃 |
| 已定夺的方案与理由 | `docs/decisions/`（ADR） | 按需读 | 日后会被重提「为什么不用 X」 |
| 面向人的用法与指南 | `docs/` / README | 按需读 | 人也读，agent 也可检索 |

**关于 `paths:` 的两个坑**：① 带 `paths:` 的规则按需载入（匹配文件被 Read/Write/Edit 时），
不带 `paths:` 的 `.claude/rules/` 却在 launch 即载入——别混为一谈。② v2.1.211 的变更点是
「按需载入的规则不再绕过 `--setting-sources` 排除 project 设置」，**不是**「路径规则改成
launch 加载」。历史 issue（#62049 / #90004 / #93248）与证据见
`references/research-2026-10.md`；其中「新建文件不触发」（#93248）是**特性请求**而非已确认缺陷。

**分流建议**：即使路径规则可靠，按扩展名/语言分流也宜用 SKILL.md 正文的**显式路由表**
（「扩展名 → references 文件」），由模型显式 Read——路由表可读、可测、不依赖触发机制。

## 常驻文件该写什么

**写**：agent 猜不到的命令（非标准构建/测试入口）、偏离默认的风格、仓库礼仪
（分支/提交规矩）、架构决策与「为什么不是另一个方案」、环境怪癖与踩过的坑、
必须遵守的安全边界。

**不写**：代码本身能推断出的内容、通用语言规范、详细 API 文档、易变信息
（计数/日期/当前缺陷数）、长篇教程、逐文件说明、"写干净代码"。

**长度**：目标 **< 200 行**（Cursor 建议单规则 < 500 行；HumanLayer 建议根文件 < 60 行）。
`@import` 只是组织手段，**不减少上下文成本**——被导入文件仍全文加载。

## 推荐目录结构

```
repo/
├── CLAUDE.md                 # 全局默认：项目地图 + 硬规则 + 路由表（≤150 行）
├── docs/                     # 入库、持久
│   ├── README.md             # 索引 + owner / last-verified
│   ├── architecture.md       # 模块与依赖（从常驻文件迁出）
│   ├── testing/README.md     # 测试分层、标签口径（口径而非数字）
│   ├── decisions/0001-*.md   # ADR
│   └── guides/               # 各模块用法
├── tools/<module>/CLAUDE.md  # 只写该目录的差异，不复制根规则
└── .claude/                  # 本地、可丢
    ├── plans/                # 一次性计划与过程记录
    └── settings.json         # hooks / permissions / env（改走 update-config skill）
```

**改 `settings.json`（hooks / permissions / env）优先走 `update-config` skill**，不要手工
编辑——本机全局配置由 cc-switch 托管，手工改会被覆盖。

跨工具共用一个源文件时：根文件用 `AGENTS.md`，`CLAUDE.md` 只留 `@AGENTS.md`
（不要维护两份；Windows 上 symlink 需管理员权限，import 更稳）。

**路由表**：根文件末尾列出「改到哪里 → 先读哪个文件」，避免 agent 误读无关子项目规则。

## 审查既有文档（清单）

逐条检查，命中即修：

- [ ] 根文件行数是否超预算？超了先找「按需内容」迁出，而不是删规则。
- [ ] 是否混入历史流水 / 变更日志 / 时点实测（"2026-xx-xx 实测"）？
- [ ] 是否写了易变数字（测试计数、当前红灯数）？→ 改为「口径 + 用哪条命令去数」。
- [ ] 是否引用了 **gitignore 路径**里的判据/规格？→ 迁移入库（换机/克隆后失效）。
- [ ] 是否存在互相矛盾的规则？→ 跑 `/doctor prompt-audit`（v2.1.283+）或人工全文对照。
- [ ] 是否有同一规则的多份副本？→ 收敛为单一事实来源 + 指针。
- [ ] 文档描述的行为与代码是否一致？→ 加能机械校验的检查兜底（CI / hook / 测试）。
- [ ] 每条「必须/绝不」是否真有执行机制？没有就考虑 hook。

## 常见失败模式

低信号内容膨胀、规则互相矛盾、变更日志混入常驻、多份副本漂移、规格与代码脱节、
活文档依赖 gitignore 路径、`/init` 生成后不维护——完整对照表与规避方式见
`references/research-2026-10.md`「七、失败模式与规避」（单一真源，不在此重复）。

## 输出时

给出**具体的**搬迁映射（段落 → 目标文件），而不是只说「应精简」。
写新文件时同时说明：哪条规则由什么机制保证（人读 / hook / CI / 测试）。

## References

- `references/research-2026-10.md`：来源、各工具长度上限、真实仓库样本、证据强度。
  其中的数字有时效性，引用前核对。
- `references/templates/root-agent-file.md`：根指令文件骨架（含路由表）。
- `references/templates/adr.md`：ADR 模板。
