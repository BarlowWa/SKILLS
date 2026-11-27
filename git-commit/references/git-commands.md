# 提交与修正命令细则

`SKILL.md`「提交执行」包含三条主命令的引导与一份必做项清单（不展开陷阱），本文给出完整的命令形态、
amend 用法与逐条核对步骤。**两者冲突时以本文为准**：撞上陷阱时以这里的说明执行，不要照 SKILL.md 的简述脑补。

## 1. 按提交模式执行

用户确认后，按确认的提交模式执行：

```bash
# 全量（git add -A 在审查之前就已执行，见下）
git commit -m "<提交信息>"

# 仅暂存区：不再 git add
git commit -m "<提交信息>"

# 指定文件（<路径...> 为确认范围内的文件）
git add -- <路径...>
git commit -m "<提交信息>" -- <路径...>
```

- **全量模式的 `git add -A` 必须放在审查之前**（`SKILL.md` 步骤 2 已如此规定），提交阶段**只 `git commit`**。
  若审查后再 `add -A`，则「审查完 → 提交」之间对工作区的任何改动都会被静默入库
  （实测：审查后把工作区改成 `UNREVIEWED`，再 `add -A && commit`，落库就是 `UNREVIEWED`）。
  审查后确实又有改动时，**重新审查**这部分，而不是靠再 `add` 一次「跟上」。
- 指定文件模式下 `git commit -- <路径...>` 只提交这些路径的工作区内容，范围外已暂存的文件会保留在暂存区。
- 指定文件模式若某个路径存在**分块暂存**（index 与工作区不一致），本命令提交的是该路径的**工作区**内容，
  不会保留索引里的部分版本；执行前按 `SKILL.md` 步骤 2 向用户确认，未确认不得默认。
- **例外：该路径已经从索引里被移除时，提交取的是索引**（实测：`git rm --cached m.txt` 后
  `git commit -- m.txt` 会命中）——但此时 `git diff HEAD --name-only -- m.txt` 报空，
  与「nothing to commit」不可区分。所以指定文件模式下若某个路径处于「不在索引、也不在 HEAD」的状态，
  先向用户确认意图，不要直接提交。

## 2. amend（修正上一次提交）

若用户要求 amend，使用 `git commit --amend`。此时：

- 先展示上一次提交信息。
- 展示本次新的变更。
- 审查范围应覆盖「上一次提交的内容 + 本次新增变更」，而不是只审本次 diff。**基准随 amend 的形态变**：

  | amend 形态 | 取的是 | 审查命令 |
  |---|---|---|
  | 裸 `--amend`（含 `--no-edit` / `-m`） | **索引** | `git diff HEAD~1 --cached` |
  | 给了路径（`--only` 可省略）——`--amend --only -- <路径...>`、`--amend -m "…" -- <路径...>` | 这些路径的**工作区内容**，其它路径不入库 | `git diff HEAD~1 -- <路径...>` |
  | `--amend -a`（**不能**带 pathspec） | 所有已跟踪文件的**工作区内容** | `git diff HEAD~1` |
  | `--amend --include -- <路径...>` | **混合**：指定路径取**工作区**，其余已暂存内容取**索引**。索引侧必须**排除**这些路径，否则会虚报一条根本没入库的索引版本 | 工作区侧 `git diff HEAD~1 -- <路径...>`；索引侧 `git diff HEAD~1 --cached -- . ':(exclude)<路径...>'`（实测：不排除时索引侧报 `+INDEXED`，而落库是 `WORKTREE`） |
  | `--only` / `--include` 不带路径 | 只改提交信息（`--include` 不带路径直接报错） | 无内容基准 |

  官方文档对 `--only` 的定义是「taking the **updated working tree contents** of the paths specified on the
  command line, disregarding any contents that have been staged for other paths」，而 pathspec 模式下
  `--only` 本就是默认行为——所以**只要命令行给了 pathspec 且没有 `--include`，取的就是工作区**。
  `--include` 与它相反：**保留**已暂存内容，再把这些路径的工作区版本叠加进去，故是混合基准。
  `-a/--all` 是「把所有已跟踪文件的工作区内容一并加入」，同样不含索引里的其它内容。
  用错基准会审到根本没入库的那一份（实测：索引 `STAGED`、工作区 `WORKTREE` 时，`--only -- a.txt` 落库为
  `WORKTREE`，而 `--cached` 显示的是 `STAGED`）。
  **`-a` / `--include` 的两种非法写法**（实测，退出码均为 128）：`--amend -a -- <路径...>` →
  `fatal: paths '<p> ...' with -a does not make sense`；`--amend --include`（不带路径）→
  `fatal: No paths with --include/--only does not make sense.`（`--only` 不带路径则是合法的，见上表末行）。
  root 提交（无 `HEAD~1`）时改用空树基准 `git hash-object -t tree /dev/null`：索引形态用
  `git diff --cached <空树>`，工作区形态用 `git diff <空树> -- <路径...>`，整树工作区形态用 `git diff <空树>`。
  **未跟踪的路径 amend 不进去**，必须先 `git add`（实测：`--amend --only -- u.txt` 对未跟踪文件报
  `error: pathspec 'u.txt' did not match any file(s) known to git`，退出码 1）。
- 生成修正后的提交信息供用户确认。
- 提示：**不得 amend 已 push 的提交**。

按意图选形态：

| 意图 | 命令 | 说明 |
|---|---|---|
| 只加内容、保留原提交信息 | `git commit --amend --no-edit` | 会提交整个索引；只想加入指定路径用下一行 |
| 只加指定路径、保留原提交信息 | `git commit --amend --only --no-edit -- <路径...>` | 只纳入指定路径，保留其它暂存内容 |
| 只改提交信息 | `git commit --amend --only -m "<新提交信息>"` | 不改索引中的其它暂存内容；若索引与 HEAD 一致，也可用普通 `git commit --amend -m "<新提交信息>"`（执行前可用 `git diff --cached --quiet` 判断） |
| 两者都有 | `git commit --amend --only -m "<新提交信息>" -- <路径...>` | 只纳入指定路径，保留其它暂存内容；若索引中只有目标内容，也可用普通 `git commit --amend -m "<新提交信息>"` |

- 注意：裸 `--amend -m` 会提交整个索引；索引与 HEAD 不一致时，已暂存改动会一同进入 amend。
  「只改提交信息」的两种写法里，`--only -m`（不带路径）**不消耗暂存内容**，裸 `--amend -m`（索引 == HEAD 时）
  走的是同一条路径；「两者都有」时**必须带 `-- <路径...>`**——`--only -m` 不带路径不会纳入任何内容，
  带了路径才取工作区。上表每一行的内容来源与上方审查基准表一一对应。
- **所有选项必须写在 `--` 之前**：`--` 之后一律按 pathspec 解析，
  `git commit --amend --only -- <路径...> --no-edit` 会把 `--no-edit` 当成文件名并报
  `error: pathspec '--no-edit' did not match any file(s) known to git`（退出码 1）。
  正确形态：`git commit --amend --only --no-edit -- <路径...>`、`git commit --amend --only -m "<信息>" -- <路径...>`

## 3. 提交前核对（每轮必做，`git commit` 之前的最后一道闸）

**原则：能在 `git commit` 之前发现的错误，必须在之前发现。** 提交后再发现，代价是 `--amend`
（改写提交对象、与 hook 交互、可能把范围外内容带入）；能用只读命令提前查出的，就不要靠事后返工。

在**暂存完成之后、`git commit` 之前**逐条执行：

1. **将要入库的文件集**——**基准 = 该模式实际提交的内容**。按「提交取什么 → 就查什么」定基准，
   不要凭模式名字推断。三行主模式 + 初始提交的两小类，共五格；**其中三格共用 `--cached`，
   真正不同的只有三条命令**：

   | 模式 | 实际提交的 | 查文件集 |
   |---|---|---|
   | 全量（已 `git add -A`） | 索引 | `git diff --cached --name-status` |
   | 仅暂存区 | 索引 | `git diff --cached --name-status` |
   | 指定文件（有 HEAD） | 指定路径的**工作区内容** | `git diff HEAD --name-only -- <路径...>` |
   | 初始提交（全量 / 仅暂存区） | 索引 | `git diff --cached --name-status` |
   | 初始提交 + 指定文件 | 指定路径的**工作区内容** | `git diff "$(git hash-object -t tree /dev/null)" --name-only -- <路径...>` |

   指定文件模式还要并入**未跟踪**的范围内文件：`git ls-files --others --exclude-standard -- <路径...>`。

   > **为什么全量/仅暂存区不再用 `--dry-run`**：`git commit --dry-run --porcelain` 在**不带 pathspec** 时会把
   > **工作区的未暂存改动**也列出来（` M research-docs/...`），而 `git commit` 根本不会提交它们（实测：索引里只有
   > 2 个文件，dry-run 却列出 6 行）。官方文档对这个选项的原话就是它「show a list of paths that are to be
   > committed, **paths with local changes that will be left uncommitted** and paths that are untracked」——
   > 它本来就不是「将入库文件集」的清单。
   > 「全量」的语义是**先 `git add -A` 再 `git commit`**——执行 `add` 之后索引即最终内容，所以查索引才是查真值；
   > 若还没 `add`，本步骤会显示索引为空，此时按 §1 的口径先 `add` 再回到本步骤。
   > 审查同样要在 `add` 之后做（`SKILL.md` 步骤 2 的全量行已按此改为 `git diff --cached`）：
   > 否则「审查完到 `add` 之间」对工作区的改动不会被审到，而 `add` 会把它入库。
   > **指定文件模式为什么绕开索引**：该模式 `git commit -- <路径...>` 提交的是**工作区内容**，范围由 pathspec
   > 决定，索引里有什么都不影响提交（实测：索引 `M a`、工作区已还原成 HEAD 时，`--cached` 报有内容，
   > 而 `git commit -- a` 报 nothing to commit）；而 `git commit --dry-run --porcelain -- <路径...>`
   > **不会滤掉范围外改动**（范围外文件若有未暂存改动会以 ` M other.txt` 一并列出，实测）。
   > 「`diff HEAD`（已跟踪目标）+ `ls-files --others`（未跟踪目标）」按 pathspec 精确收窄，范围外一律不出现，
   > 与 `SKILL.md` 步骤 2 表格里该模式的审查命令是同一对命令。
   > 上面那句「`--cached` 报有内容」是用来说明**索引不是该模式的基准**，不是 `--cached` 本身有错——
   > 在索引模式（全量 / 仅暂存区）里它正是唯一正确的基准。

   把输出与用户确认范围比对。**空输出先分辨「范围为空」还是「路径打错了」**——这两件事在
   `git diff` 里长得一模一样。用一条命令做路径校验：

   ```bash
   git add --dry-run -- <路径...>
   ```

   | 退出码 | stderr | 含义 |
   |---|---|---|
   | **128** | `fatal: pathspec '<x>' did not match any files` | 路径在**工作区和索引里都没有** → 输入错误；**但见下方删除例外** |
   | **1** | `The following paths are ignored by one of your .gitignore files` | 该路径被忽略且**未被跟踪** → 不可能入库 |
   | **0** | — | 路径合法 |

   > **⚠️ 128 不等于「路径不存在」——删除会被误判**：文件已被 `git rm`（索引里是 `D`）时，
   > `git add --dry-run -- gone.txt` 同样返回 **128** `fatal: pathspec 'gone.txt' did not match any files`，
   > 而 `git commit -- gone.txt` **能正常入库这条删除**（实测：提交后 `D gone.txt`）。
   > 删除是 `SKILL.md` 分析要点里明列的常见变更，按 128 一律中止会把合法删除拦掉。
   > 判别办法：**128 时再查一次 `git diff --cached --name-status -- <路径...>`**，输出里带 `D` 的路径
   > 是合法删除，其余才是真打错（实测：已 `git rm` 的报 `D gone.txt`，真不存在的报空）。
   > 不能改用 `git ls-files --deleted`：删除已进索引时它返回空，起不到区分作用。
   > 工作区里删掉但**尚未** `git rm` 的文件不受影响——它在索引里还在，`add --dry-run` 返回 0。
   - 被 `.gitignore` 匹配但**已被跟踪**的文件不受影响（实测：`git add --dry-run -- log.txt` 返回 0 并输出
     `add 'log.txt'`，可正常提交）；指向空目录的合法路径同样返回 0，但永远没有内容。
   - **多条路径混排时没有「部分成功」**：任一路径不合法即整条命令 128，须逐条定位后再整批重跑。
   - **它只证明「路径合法」，不能用来判「有没有内容」**：`git add --dry-run` 只报**新内容**，
     已暂存且未再改动的文件它恒为空（实测：`b.txt` 已 `A` 暂存、`diff --cached` 看得见，本命令输出为空）。
     判空走下面按模式区分的办法。
   - **判「有没有待提交内容」**：索引模式用 `git diff --cached --quiet`（无差异 **0** / 有差异 **1**，
     与不带 `--quiet` 的 `git diff --cached` 不同——后者**恒为 0**，信号只在 stdout）。
     - **全量**退出码 0 → 是「索引里没有待提交内容」。**先确认审查前是否已 `git add -A`**：
       全量要求 add 在审查之前完成，此时索引空意味着工作区本来就没有变更，按「工作区无变更」处理；
       若还没 add（本流程走出了相反的次序），按 §1 先 add 再回到本步骤。
     - **仅暂存区**退出码 0 → 是「用户没暂存任何东西」。**不得因此 `git add`**（§1 明令该模式不 `add`），
       应把现象报给用户，由用户决定改模式还是补暂存。
   - 非索引模式（指定文件）判空要**同时**看两条：本节表格的 diff 输出为空，**且**
     `git ls-files --others --exclude-standard -- <路径...>` 也为空。只看前者会把「只有一个未跟踪新文件」
     误判成无内容（diff 看不见未跟踪文件）。

   > **为什么不能用 stderr 判路径错误**：`git diff` 对不存在的 pathspec **静默成功**——
   > `git diff --cached --name-status -- nosuch`、`git diff HEAD --name-only -- nosuch`、
   > 乃至 `git diff --cached --quiet -- nosuch` 都是退出码 0、stderr 空（实测，含本机 `core.autocrlf=true` 时）。
   > `git ls-files --others` 对不存在的路径同样静默返回空。所以「stderr 非空 = 输入错误」这条判别根本不成立；
   > 只有 `git add --dry-run` 会因路径不存在而 `fatal`（退出码 128），故用它做路径校验。
   > 另一个容易记错的：`git commit --dry-run` 在**有内容可提交时退出码为 0**，只有 nothing-to-commit 才是 1，
   > 与 `--quiet` 的 0/1 方向恰好相反。它无副作用：执行前后 `git write-tree` 哈希不变（实测）。

   范围不符时用 `git reset -- <路径>` 修正索引——**但 `reset` 对打错的路径静默 `exit 0`、无任何提示**
   （实测 `git reset -- nosuch` 返回 0），所以必须先跑上面的 `git add --dry-run` 校验、再 `reset`。
   **指定文件模式例外**：它的范围由 pathspec 决定，索引里有什么
   都不影响提交内容，所以不能用 `reset` 纠正范围（要改范围就改 pathspec）；全量模式若已执行过 `git add -A`，
   也不宜用 `reset` 再指望它生效——下一次 `add -A` 会把它重新加回来（实测），应从源头改 `add` 的路径集或改用指定文件模式。
2. **空白错误**——基准同上一条：**该模式实际提交的内容**，用错基准会同时导致漏检与误报。

   | 模式 | 提交的是 | 空白检查命令 |
   |---|---|---|
   | 全量（已 `git add -A`） | **索引** | `git diff --cached --check` |
   | 仅暂存区 | **索引** | `git diff --cached --check` |
   | 指定文件（有 HEAD） | **工作区内容** | `git diff HEAD --check -- <路径...>` |
   | 初始提交（全量 / 仅暂存区） | **索引** | `git diff --cached --check` |
   | 初始提交 + 指定文件 | **工作区内容** | `git diff "$(git hash-object -t tree /dev/null)" --check -- <路径...>` |

   > **`git diff HEAD --check` 在「全量」下是错的**：它比的是 HEAD↔工作区，而提交取的是**索引**。
   > 「已 add 带空格、又改回干净」时它报 clean 而脏内容照样入库（漏检）；反之报脏而入库干净（误报）。两者均已实测。
   > **初始提交的路径模式用空树基准**：`git hash-object -t tree /dev/null` 给出空树，比之即等于「从无到有」。
   > 原先「`--cached` + `git diff` 两段并查」会误报——`--cached` 段查的是**索引**，
   > 而该模式提交的是工作区。空树写法在「索引脏/工作区脏 × 两个方向」共四种状态下均与真值一致
   > （已逐态构造验证：索引脏工作区干净时 `--cached` 报脏而入库干净，空树不报；工作区脏索引干净时
   > `--cached` 不报而入库脏，空树报出——两个方向各验一次）。
   > `git hash-object -t tree /dev/null` 在 Windows 上同样可用；§2 amend 节已用同一写法，保持一致。
   > **⚠️ 该基准读的是工作区，且看不见未跟踪文件**：未 `git add` 的新文件它完全查不到
   > （实测：初始提交下未跟踪的 `u.txt` 带行尾空格，`git diff <空树> --check -- u.txt` 退出码 0 漏检，
   > `git add` 之后才报出）。该模式本就要求先 `git add -- <路径...>`（见 `SKILL.md` 步骤 2），
   > 所以顺序必须是**先 add、后查**；指定文件（有 HEAD）那一行同理，未 add 的新文件同样漏检。
   > **「索引」与「工作区」两类在三个标签下的判定方向相反，别记反**：
   > 索引基准（`--cached --check`）在索引脏、工作区干净时**报**（入库确实是脏的，正确）；
   > 工作区基准（`diff HEAD --check`）在同样的状态下**不报**（工作区干净，但入库是脏的——漏检）。
   > 这就是「提交取什么就查什么」的全部含义。
   > 命中时退出码非零并打印 `文件:行`；**只查新增行**——HEAD/索引中本来就存在的行尾空格不在此列。
3. **待写入的提交信息字符串**（马上要传给 `-m` 的那段）：按 **COMMIT-010** 确认不含 `Co-Authored-By`
   等作者注脚；按 **COMMIT-001** 确认「标题行不超过 72 字符、使用中文描述、末尾不加句号」。
   > **中文标题不要用 `wc -c` 数字数**——它按字节计，UTF-8 下一个汉字 3 字节，42 个汉字会被数成 126 而误判超长。
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
- **实际提交范围**用 `git show --stat --oneline HEAD` 复核。实测：`pre-commit` hook 改写文件**内容**并重新
  `add` 新文件后，提交前索引与最终入库内容不一致，只有本节能看到。
  **但它对「hook 改写了已入库文件的内容」是盲的**：文件名与行数统计都可能不变，`--stat` 看上去与提交前
  一模一样（实测：hook 把 `v2` 改成 `v2-REWRITTEN`，`--stat` 仍只显示 `a.txt | 2 +-`）。
  要抓这一类，**按路径逐个比对 blob**——这比整棵树比对更稳，因为索引里常有范围外暂存内容
  （指定文件模式、`--amend --only` 之后），整树比对会对完全正常的提交误报：

  ```bash
  # ① 提交前（暂存完成后）为每个将入库的路径记下 blob，写进清单（每个提交用新文件，别 >> 追加）
  #    基准由【提交模式】决定，不要用「rev-parse 是否成功」去猜——索引里常有该路径的旧 blob，
  #    那样会把工作区形态误记成索引 blob，之后一律误报「被 hook 改写」。
  : > /tmp/expected.blobs
  MODE=index        # ← 全量 / 仅暂存区 / 初始提交的索引形态
  # MODE=worktree   # ← 指定文件 / --only -- <路径> / --amend -a / --include -- <路径>
  for p in <路径...>; do
      b=
      case "$MODE" in
        index)    b=$(git rev-parse -q --verify ":$p") ;;
        worktree) [ -e "$p" ] && b=$(git hash-object -- "$p") ;;
      esac
      # 取不到（已删除 / 未被跟踪）就写哨兵，绝不留空行：空字段会让提交后的比对把任何值都判成不一致
      printf '%s\t%s\n' "$p" "${b:-(ABSENT)}" >> /tmp/expected.blobs
  done

  # ② 提交后逐条比对（IFS=制表符：文件名含空格时按空白切分会把路径截断）
  while IFS=$'\t' read -r p b; do
      if [ "$b" = "(ABSENT)" ]; then
          echo "未能核对（提交前取不到 blob，已删除或未被跟踪）：$p"
      else
          [ "$(git rev-parse -q --verify "HEAD:$p")" = "$b" ] || echo "被 hook 改写：$p"
      fi
  done < /tmp/expected.blobs
  ```

  取不到 blob 的路径（工作区已删 / 从未被跟踪）**如实报「未能核对」，不要静默跳过**——
  这正是「没有数据 ≠ 没有问题」在脚本层的落点。

  **基准必须显式声明**（与 §3 文件集表一致），**不要用「`rev-parse` 是否成功」反推模式**：
  索引里常有该路径的旧 blob，指定文件 / `--only -- <路径>` / `--amend -a` 这些**工作区**形态
  会被误记成索引 blob，于是正常提交一律误报「被 hook 改写」（实测：工作区 `WT_ONLY`、索引仍是 `v1` 时，
  按索引记 `626799f0`，而落库是 `ecaf8066`）。
  三个必须留意的坑，均已实测：
  - **`git rev-parse` 失败时仍会向 stdout 打印参数**（`:gone.txt` 报错的同时输出 `:gone.txt`），
    被 `$( )` 捕获后会污染清单、并在提交后与同样失败的 `HEAD:gone.txt` 一起造成空 vs 空之外的假结果。
    **必须加 `-q --verify`**：失败时退出码 1 且 stdout 为空。
  - 路径是**目录**时 `rev-parse ":<dir>"` 也失败，同样靠 `-q --verify` 兜住。
  - 清单**每个提交单独新建**（`:` 覆盖），不要 `>>` 累积——拆分提交时上一提交的旧行会全部误报。
  **提交前必须采集**——本节的检查发生在提交后，但取值动作在提交前，漏了这一步检查恒通过、形同虚设。
  发现不一致时用 `git show --name-only --format= HEAD` 看范围、`git show HEAD -- <路径>` 看内容。
  范围与确认不一致时立即报告。
- 指定文件模式下若索引中仍有范围外暂存内容，清理信息必须用
  `git commit --amend --only -m "<清理后的提交信息>"`，不要用裸 `--amend -m`（它会把整个索引带入）；
  重新提交后再次核对本节与前项。若环境反复自动追加且无法删除，停止并报告冲突。
- `git commit` 非零退出（hook 失败、nothing to commit、pre-commit 改写文件等）时，不得报告成功；
  说明退出码与输出，保留现场并询问用户。
