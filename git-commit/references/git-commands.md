# 提交与修正命令细则

`SKILL.md`「提交执行」包含三条主命令的引导与一份必做项清单（不展开陷阱），本文给出完整的命令形态、
amend 用法与逐条核对步骤。**两者冲突时以本文为准**：撞上陷阱时以这里的说明执行，不要照 SKILL.md 的简述脑补。

## 1. 按提交模式执行

用户确认后，按确认的提交模式执行：

```bash
# 全量
git add -A
git commit -m "<提交信息>"

# 仅暂存区：不再 git add
git commit -m "<提交信息>"

# 指定文件（<路径...> 为确认范围内的文件）
git add -- <路径...>
git commit -m "<提交信息>" -- <路径...>
```

- 指定文件模式下 `git commit -- <路径...>` 只提交这些路径的工作区内容，范围外已暂存的文件会保留在暂存区。
- 指定文件模式若某个路径存在**分块暂存**（index 与工作区不一致），本命令提交的是该路径的**工作区**内容，
  不会保留索引里的部分版本；执行前按 `SKILL.md` 步骤 2 向用户确认，未确认不得默认。

## 2. amend（修正上一次提交）

若用户要求 amend，使用 `git commit --amend`。此时：

- 先展示上一次提交信息。
- 展示本次新的变更。
- 审查范围应覆盖「上一次提交的内容 + 本次新增变更」，而不是只审本次 diff。`git commit --amend`
  只提交索引，因此用 `git diff HEAD~1 --cached` 查看将进入 amend 的内容；无 `HEAD~1`（root 提交）时
  用 `git diff --cached $(git hash-object -t tree /dev/null)`（或 `git show HEAD` + `git diff --cached`）。
  工作区未暂存改动不会被 amend 纳入，不要混入审查范围。若上一次提交不在本会话内且无法完整获取，先向用户确认范围。
- 生成修正后的提交信息供用户确认。
- 提示：**不得 amend 已 push 的提交**。

按意图选形态：

| 意图 | 命令 | 说明 |
|---|---|---|
| 只加内容、保留原提交信息 | `git commit --amend --no-edit` | 会提交整个索引；只想加入指定路径用下一行 |
| 只加指定路径、保留原提交信息 | `git commit --amend --only --no-edit -- <路径...>` | 只纳入指定路径，保留其它暂存内容 |
| 只改提交信息 | `git commit --amend --only -m "<新提交信息>"` | 不改索引中的其它暂存内容；若索引与 HEAD 一致，也可用普通 `git commit --amend -m "<新提交信息>"`（执行前可用 `git diff --cached --quiet` 判断） |
| 两者都有 | `git commit --amend --only -m "<新提交信息>" -- <路径...>` | 只纳入指定路径，保留其它暂存内容；若索引中只有目标内容，也可用普通 `git commit --amend -m "<新提交信息>"` |

- 注意：裸 `--amend -m` 会提交整个索引；索引与 HEAD 不一致时，已暂存改动会一同进入 amend，优先用 `--only`。
- **所有选项必须写在 `--` 之前**：`--` 之后一律按 pathspec 解析，
  `git commit --amend --only -- <路径...> --no-edit` 会把 `--no-edit` 当成文件名并报
  `error: pathspec '--no-edit' did not match any file(s) known to git`（退出码 1）。
  正确形态：`git commit --amend --only --no-edit -- <路径...>`、`git commit --amend --only -m "<信息>" -- <路径...>`

## 3. 提交前核对（每轮必做，`git commit` 之前的最后一道闸）

**原则：能在 `git commit` 之前发现的错误，必须在之前发现。** 提交后再发现，代价是 `--amend`
（改写提交对象、与 hook 交互、可能把范围外内容带入）；能用只读命令提前查出的，就不要靠事后返工。

在**暂存完成之后、`git commit` 之前**逐条执行：

1. **将要入库的文件集**——用 `git commit --dry-run --porcelain`，过滤掉未跟踪与未暂存项：
   ```bash
   # 全量 / 仅暂存区
   git commit --dry-run --porcelain | grep -vE '^\?\?|^ [MADR]'
   # 指定文件（<路径...> 为确认范围内的文件）
   git commit --dry-run --porcelain -- <路径...> | grep -vE '^\?\?|^ [MADR]'
   ```
   输出与用户确认范围比对；**输出为空即「nothing to commit」**（`--dry-run` 此时退出码为 1）。
   范围不符时用 `git reset -- <路径>`（或重新 `add`）纠正，不必 amend。
   > **为什么用 `--dry-run` 而不是 `git diff --cached`**：后者列的是**索引**，而指定文件模式下
   > `git commit -- <路径...>` 提交的是**工作区内容**——`--cached` 会把范围外但已暂存的文件算进来（实测误报），
   > 也会漏掉「只改了工作区、没 add」的文件。`--dry-run` 走的是真实的提交逻辑，三种模式都正确，且
   > **不触发任何 hook**（实测 `pre-commit` / `commit-msg` / `prepare-commit-msg` 均不执行）。
   > 过滤规则的必要性：`--porcelain` 的输出里 `??` 是未跟踪、首列空格的 ` M` 是未暂存，两者都不该计入
   > 「将要入库」。但**指定文件模式例外**：该模式下 `git commit -- <路径...>` 取的是工作区内容，
   > 「只改了工作区、没 add」的文件**确实会被提交**，而它在 porcelain 里与「未暂存」同形——
   > 所以那里的区分只能靠 pathspec 限定，不能靠过滤掉首列空格来实现。
2. **空白错误**——按模式选对基准，**用错基准会同时导致漏检与误报**：
   | 模式 | 命令 | 为什么 |
   |---|---|---|
   | 全量 | `git diff HEAD --check` | 工作区+索引全部入库，两者都要查 |
   | 仅暂存区 | `git diff --cached --check` | 只查索引；用 `HEAD` 会把范围外的未暂存改动算进来（实测误报） |
   | 指定文件 | `git diff HEAD --check -- <路径...>` | 提交取工作区内容；用 `--cached` 会漏掉「只改了工作区」的尾随空格（实测漏检） |
   | 初始提交 | `git diff --cached --check` | 无 `HEAD` 可比 |

   > 同一个 `--cached` 在仅暂存区模式**正确**、在指定文件模式**漏检**；反过来 `HEAD` 在指定文件模式正确、
   > 在仅暂存区模式**误报**。两者都已实测，不要当成可以互换的等价写法。命中时退出码非零并打印 `文件:行`。
3. **待写入的提交信息字符串**（马上要传给 `-m` 的那段）：按 **COMMIT-010** 确认不含 `Co-Authored-By`
   等作者注脚；按 **COMMIT-001** 确认「标题行不超过 72 字符、使用中文描述、末尾不加句号」。
   > **中文标题不要用 `wc -c` 数字数**——它按字节计，UTF-8 下一个汉字 3 字节，42 字的标题会被数成 82 而误判超长。
   > 用 `py -c "print(len('''<标题>'''))"` 或等价的字符计数方式。
4. **项目若配置了 hook**：提交前单独跑一次该 hook 的命令（`pre-commit run` / `npx lint-staged` 等），
   跑完 `git status --porcelain` 看它是否改写了文件——改了就重新 `git add` 并重跑直到通过，
   避免 `git commit` 中途被打断。

**以下两项无法前移，交给 §3.1**：`commit-msg` / `prepare-commit-msg` hook 能在 `-m` 固定之后改写提交信息；
`pre-commit` hook 能改写文件并重新 `add`，使**提交前看到的索引 ≠ 最终入库内容**（两者均已实测）。

### 3.1 提交后核对（无法前移的两项）

- `git log -1 --format=%B` 核对**最终落库**的提交信息（COMMIT-010）。实测：hook 追加 `Co-Authored-By` 时，
  传入的 `-m` 干净而落库信息被污染；`git show --stat` 不显示 footer，不能替代这一步。出现注脚必须删除后重新提交。
- `git show --stat --oneline HEAD` 复核**实际提交范围**。实测：`pre-commit` hook 改写文件内容并 `git add` 后，
  提交前索引与最终入库内容不一致，只有本节能看到。范围与确认不一致时立即报告。
- 指定文件模式下若索引中仍有范围外暂存内容，清理信息必须用
  `git commit --amend --only -m "<清理后的提交信息>"`，不要用裸 `--amend -m`（它会把整个索引带入）；
  重新提交后再次核对本节与前项。若环境反复自动追加且无法删除，停止并报告冲突。
- `git commit` 非零退出（hook 失败、nothing to commit、pre-commit 改写文件等）时，不得报告成功；
  说明退出码与输出，保留现场并询问用户。
