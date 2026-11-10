# 提交与修正命令细则

`SKILL.md`「提交执行」与「特殊情况处理 / Amend 提交」的命令形态与陷阱。SKILL.md 保留主命令、提交后核对的要点
与 amend 的三条硬性提醒，本文展开完整形态；两者冲突时以本文为准。

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

## 3. 提交后核对（每轮必做，快速路径也不例外）

1. `git show --stat --oneline HEAD`：核对实际提交的文件与用户确认范围一致；不一致时立即报告。
2. `git log -1 --format=%B`：核对完整提交信息（**COMMIT-010**）。`git show --stat` 不显示 footer，不能替代这一步；
   若出现 `Co-Authored-By` 等作者注脚，必须删除后重新提交。
3. 指定文件模式下若索引中仍有范围外暂存内容，清理信息必须用
   `git commit --amend --only -m "<清理后的提交信息>"`，不要用裸 `--amend -m`（它会把整个索引带入）；
   重新提交后再次核对第 1、2 步。若环境反复自动追加且无法删除，停止并报告冲突。
4. `git commit` 非零退出（hook 失败、nothing to commit、pre-commit 改写文件等）时，不得报告成功；
   说明退出码与输出，保留现场并询问用户。提交 hook 改写了文件时，重新核对 diff 与提交信息。
