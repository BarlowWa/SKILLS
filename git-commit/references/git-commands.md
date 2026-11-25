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

1. **将要入库的文件集**——**统一以「提交时刻的索引」为准**：`git commit` 提交的是索引，不是工作区，
   所以本步骤在任何模式下都先确认索引内容，再谈范围。
   | 模式 | 命令 |
   |---|---|
   | 全量 / 仅暂存区 / 初始提交 | `git diff --cached --name-status` |
   | 指定文件（有 HEAD） | `git diff HEAD --name-only -- <路径...>` **与** `git ls-files --others --exclude-standard -- <路径...>` 取并集 |

   > **为什么全量/仅暂存区不再用 `--dry-run`**：`git commit --dry-run --porcelain` 在**不带 pathspec** 时会把
   > **工作区的未暂存改动**也列出来（` M research-docs/...`），而 `git commit` 根本不会提交它们（实测：索引里只有
   > 2 个文件，dry-run 却列出 6 行）。真正入库的是索引，二者不一致会让人在核对时把范围看大。
   > 「全量」的语义是**先 `git add -A` 再 `git commit`**——执行 `add` 之后索引即最终内容，所以查索引才是查真值；
   > 若还没 `add`，本步骤会显示索引为空，这本身就是「还没暂存、先按 §1 执行 `git add -A`」的正确提示。
   > **指定文件模式为什么绕开索引**：该模式 `git commit -- <路径...>` 提交的是**工作区内容**，范围由 pathspec
   > 决定，索引里有什么都不影响提交；而 `git commit --dry-run --porcelain -- <路径...>` **不会滤掉范围外改动**
   > （范围外文件若有未暂存改动会以 ` M other.txt` 一并列出，实测）。「`diff HEAD`（已跟踪目标）+ `ls-files --others`
   > （未跟踪目标）」按 pathspec 精确收窄，范围外一律不出现，与 `SKILL.md` 步骤 2 表格里该模式的审查命令是同一对命令。

   把输出与用户确认范围比对。**输出为空要分两种情形**（退出码同为 1，靠 stderr 区分）：
   ```bash
   git diff --cached --name-status >"$out" 2>"$err"
   grep -v '^warning:' "$err"        # 过滤后还有内容 = 输入错误；空 = 正常
   ```
   - 过滤后 **stderr 非空**（如 `error: pathspec 'x' did not match any file(s)`）→ **输入错误**，不是 nothing to commit。
   - stderr 为空且 `$out` 为空 → 才是「索引里没有待提交内容」。**全量模式下这通常意味着还没执行 `git add -A`**，
     按 §1 先 `add` 再回到本步骤，不要把「还没暂存」误读成「无事可提交」。
   > **不能直接判「stderr 非空」**：本机 `core.autocrlf=true` 时，diff 会**恒定**打印
   > `warning: ... LF will be replaced by CRLF`，连「确实没有改动」时也照打（实测），必须先滤掉 `warning:` 行。
   范围不符时用 `git reset -- <路径>` 修正索引。**指定文件模式例外**：它的范围由 pathspec 决定，索引里有什么
   都不影响提交内容，所以不能用 `reset` 纠正范围（要改范围就改 pathspec）；全量模式若已执行过 `git add -A`，
   也不宜用 `reset` 再指望它生效——下一次 `add -A` 会把它重新加回来（实测），应从源头改 `add` 的路径集或改用指定文件模式。
2. **空白错误**——基准必须**与提交实际取用的内容一致**，用错基准会同时导致漏检与误报。
   先明确每个模式提交的是**什么**：
   | 模式 | 提交的是 | 空白检查命令 |
   |---|---|---|
   | 全量 | **索引**（`git add -A` 之后） | `git diff --cached --check` |
   | 仅暂存区 | **索引** | `git diff --cached --check` |
   | 指定文件（有 HEAD） | **工作区内容** | `git diff HEAD --check -- <路径...>` |
   | 初始提交（全量 / 仅暂存区） | **索引** | `git diff --cached --check` |
   | 初始提交 + 指定文件 | **工作区内容** | `git diff "$(git hash-object -t tree /dev/null)" --check -- <路径...>` |

   > **`git diff HEAD --check` 在「全量」下是错的**：它比的是 HEAD↔工作区，而提交取的是**索引**。
   > 「已 add 带空格、又改回干净」时它报 clean 而脏内容照样入库（漏检）；反之报脏而入库干净（误报）。两者均已实测。
   > **用「提交取什么 → 就查什么」一句话定基准**，不要凭模式名字推断。
   > **初始提交的路径模式用空树基准**：`git hash-object -t tree /dev/null` 给出空树，比之即等于「从无到有」，
   > 一次覆盖索引与工作区。原先「`--cached` + `git diff` 两段并查」会误报——`--cached` 段查的是**索引**，
   > 而该模式提交的是工作区（实测：索引脏、工作区干净时它报脏，入库却是干净的）。空树写法在
   > 干净 / 索引脏 / 两个方向的 B4 四种状态下均与真值一致。`git hash-object -t tree /dev/null` 在 Windows 上同样可用；
   > §2 amend 节已用同一写法，保持一致。
   > 命中时退出码非零并打印 `文件:行`；**只查新增行**——HEAD/索引中本来就存在的行尾空格不在此列。
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
  传入的 `-m` 干净而落库信息被污染。**不要用 `git show --stat --oneline` 或 `%s` 查注脚**：规范的 trailer
  （前面有空行）在 `--oneline` 下看不出来，但**没有空行的畸形 trailer 会被并进同一行**，`%s` 同样被污染——
  两种形态都不该拿来当判据。裸 `git show --stat` 会显示 footer，但它把提交信息与 diffstat 混在一起，仍以
  `%B` 为准。出现 `Co-Authored-By` 等作者注脚必须删除后重新提交（项目明确要求 `Signed-off-by` / DCO 时
  只允许该 trailer）。
- `git show --stat --oneline HEAD` 复核**实际提交范围**。实测：`pre-commit` hook 改写文件内容并 `git add` 后，
  提交前索引与最终入库内容不一致，只有本节能看到。范围与确认不一致时立即报告。
- 指定文件模式下若索引中仍有范围外暂存内容，清理信息必须用
  `git commit --amend --only -m "<清理后的提交信息>"`，不要用裸 `--amend -m`（它会把整个索引带入）；
  重新提交后再次核对本节与前项。若环境反复自动追加且无法删除，停止并报告冲突。
- `git commit` 非零退出（hook 失败、nothing to commit、pre-commit 改写文件等）时，不得报告成功；
  说明退出码与输出，保留现场并询问用户。
