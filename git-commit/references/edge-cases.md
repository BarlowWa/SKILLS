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

- 审查范围是「上一次提交的内容 + 本次新增变更」，不是只审本次 diff。**基准随 amend 形态变**
  （权威表述见 `git-commands.md` §2 的形态表，此处只列结论，两处不一致时以该表为准）：
  裸 `--amend`（含 `--no-edit` / `-m`）取**索引** → `git diff HEAD~1 --cached`；
  `--only -- <路径...>` 取这些路径的**工作区内容** → `git diff HEAD~1 -- <路径...>`；
  `--amend -a`（不能带 pathspec）取**所有已跟踪文件的工作区内容** → `git diff HEAD~1`；
  `--include -- <路径...>` 是**混合**（指定路径取工作区、其余已暂存内容取索引）→ 工作区侧
  `git diff HEAD~1 -- <路径...>` + 索引侧 `git diff HEAD~1 --cached -- . ':(exclude)<路径...>'`（索引侧须排除这些路径）；
  `--only` 不带路径只改提交信息，无内容基准。root 提交另按 §4 用空树基准。
  未跟踪路径 amend 不进去，须先 `git add`。
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
**降级自查同样要产出「结论索引」**（格式见 `agent-prompts.md` 顶部约定），否则步骤 5 的对账无从进行、
条目会在确认页静默消失——降级不是跳过闭环的理由。

## 4. 初始提交

若 `git rev-parse --verify HEAD` 失败（仓库尚无提交），`git diff HEAD` 不可用：
按 `SKILL.md` 步骤 2 的初始提交说明，用 `git diff --cached` + 未跟踪列表确定范围。
**指定文件子形态例外**：它提交的是指定路径的工作区内容，索引里其它已暂存文件不入库，
所以查文件集和查空白都用空树基准 `git diff "$(git hash-object -t tree /dev/null)" -- <路径...>`
（先 `git add -- <路径...>`，否则未跟踪文件查不到）。用 `--cached` 会把索引里全部暂存文件都报进来——
实测：索引暂存了 a/b/c 三个文件、只提交 `-- a.txt` 时，`--cached` 报 3 个而实际入库 1 个。
命令细节见 `git-commands.md` §3。

root 提交可以 `--amend`，但 amend 前它就没有 `HEAD~1`（不是 amend 造成的）：
`git diff HEAD~1` 与 `git diff HEAD~1 --cached` 都直接 `fatal: ambiguous argument`（退出 128），
审查改用空树基准（索引形态 `git diff --cached <空树>`，工作区形态 `git diff <空树> -- <路径...>`）。
