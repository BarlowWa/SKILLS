# 低频路径与异常处理

`SKILL.md` 的流程主线之外、只在特定情形才用到的分支细则。主线每轮必做的检查（`git status` 里的合并冲突、
暂存区已有内容、敏感文件与大文件）保留在 SKILL.md，不在此重复。

## 1. 回滚 / 撤销

若用户要求撤销或回滚：

- **撤销上一次提交但保留变更**：`git reset --soft HEAD~1`（变更保留在暂存区）
- **回滚已提交的变更**：`git revert <commit>`（生成反向提交，保留历史）

均需先展示将受影响的范围并请用户确认，不自动执行。

## 2. Amend 提交

命令形态见 `git-commands.md` §2。必守三条：

- 审查范围是「上一次提交的内容 + 本次新增变更」，不是只审本次 diff（`git diff HEAD~1 --cached`；root 提交
  另按 `git-commands.md` §2 处理）；工作区未暂存改动不会被 amend 纳入，不要混入。
- **不得 amend 已 push 的提交**。
- 裸 `--amend -m` 会提交整个索引；优先用 `--only`。且**所有选项必须写在 `--` 之前**
  （`--` 之后一律按 pathspec 解析，`--no-edit` 写在 `--` 后会被当成文件名而报错）。

## 3. 审查 agent 失败（降级自查）

派发失败或 agent 未返回有效报告时，**不得视为「无问题」通过**。应说明失败原因，由主 agent 按对应指南自查：

- 代码侧：按 `agent-prompts.md` §1 步骤 4 的同一份清单加载规则（`code-rules` + 路由表命中的语言
  references + `test-author`/`test-review` + `arch-review`/`db-rules`）。`code-rules` 路由表无专属规则文件的
  编程语言仅应用 G-xxx 基线，并标注「未加载语言专属规则：<lang>」；
- 构建 / 配置 / 脚本侧：按 `build-review.md` 的检查清单；
- 文档侧：按 `doc-review.md`。

并在报告中标注「审查降级：主 agent 自查」。多类别同时降级时，各自按对应指南核对，不得只查其中一类。

## 4. 初始提交

若 `git rev-parse --verify HEAD` 失败（仓库尚无提交），`git diff HEAD` 不可用：
按 `SKILL.md` 步骤 2 的初始提交说明，用 `git diff --cached` + 未跟踪列表确定范围。
