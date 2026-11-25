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

1. `git diff --cached --name-status`：核对**将要入库的文件集**与用户确认范围一致。这等价于事后的
   `git show --stat --oneline HEAD`，但此时还没写提交对象——范围不符只需 `git reset -- <路径>`，
   不必 amend。**三种模式都适用**（全量模式在 `git add -A` 之后查；仅暂存区模式索引已是最终内容；
   指定文件模式查 `git diff --cached -- `<路径...>` 确认只有这些路径在索引里）。
2. `git diff --cached --check`：空白错误。提交后再查同样要 amend 才能修，提前查则一分钟改完。
3. 核对**待写入的提交信息字符串**（即马上要传给 `-m` 的那段）：按 **COMMIT-010** 确认不含
   `Co-Authored-By` 等作者注脚；按 COMMIT-001 确认标题 ≤72 **字符**且无句号。
   > **中文标题不要用 `wc -c` 数字数**——它按字节计，UTF-8 下一个汉字 3 字节，42 字的标题会被数成 82 而误判超长。
   > 用 `py -c "print(len('''<标题>'''))"` 或等价的字符计数方式。
4. `git commit` 自身是否可能非零退出：`nothing to commit` 时第 1 步的文件集就是空的；
   若项目配置了 pre-commit hook，可在提交前单独跑该 hook 的命令，避免它中途改写文件。

**唯一无法前移的一项**：`commit-msg` / `prepare-commit-msg` hook 可以在 `-m` 字符串**固定之后**再改写提交信息
（实测：hook 追加 `Co-Authored-By` 时，传入的 `-m` 干净而落库信息被污染）。因此**提交后仍必须跑 §3.1**：

### 3.1 提交后核对（唯一必要项）

- `git log -1 --format=%B` 核对**最终落库**的提交信息（COMMIT-010）。`git show --stat` 不显示 footer，
  不能替代这一步；若出现 `Co-Authored-By` 等作者注脚，必须删除后重新提交。
- 若 hook 改写了提交信息或文件（`git commit` 输出提示 hook 生效），`git show --stat --oneline HEAD`
  复核实际提交范围是否仍与确认一致。
- 指定文件模式下若索引中仍有范围外暂存内容，清理信息必须用
  `git commit --amend --only -m "<清理后的提交信息>"`，不要用裸 `--amend -m`（它会把整个索引带入）；
  重新提交后再次核对本节与前项。若环境反复自动追加且无法删除，停止并报告冲突。
- `git commit` 非零退出（hook 失败、nothing to commit、pre-commit 改写文件等）时，不得报告成功；
  说明退出码与输出，保留现场并询问用户。
