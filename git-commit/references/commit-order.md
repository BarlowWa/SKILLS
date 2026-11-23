# 提交顺序核对（测试先提交 / 修复后提交）

`SKILL.md` 的 COMMIT-005 要求：同一批变更同时包含「新增/修改测试」与「修复生产代码」时，拆成两个提交且**测试提交在前**。
「在前」不能只靠自述，须在两组都提交后用下列命令证明两条同时成立：
① 测试组提交是修复组提交的祖先；② 测试组提交**晚于本批起点**（即它确实由本批产生，而非历史上改过同一文件的旧提交）。

本文是该核对的唯一细则来源；SKILL.md 只保留规则与确认页要求，不重复脚本与分支判定。

## 1. 命令

```bash
TEST_FILE="<测试文件>"             # 多个用空格分隔，整体加引号（见 §5）
SRC_FILE="<源文件>"                # 多个用空格分隔，整体加引号（见 §5）
TEST_COMMIT=<测试组提交>           # 用户确认的测试组提交哈希；本次无测试组时留空
FIX_COMMIT=<修复组提交>            # 用户确认的修复组提交哈希；修复尚未提交时留空
BASE_COMMIT=<本批起点>             # 拆成两个提交之前那一刻的 `git rev-parse HEAD`；根提交场景写 ROOT

# 证据留存：先于任何分支打印，保证每条路径都能看到本批起点与相关文件的历史
echo "--- 证据：本批起点 BASE_COMMIT=$BASE_COMMIT ---"
echo "--- 证据：$TEST_FILE / $SRC_FILE 的提交历史 ---"
git log --format='%h %ad %s' --date=short -- $TEST_FILE $SRC_FILE
echo "TEST_COMMIT=${TEST_COMMIT:-<空>}  FIX_COMMIT=${FIX_COMMIT:-<空>}"

if [ -z "$TEST_COMMIT" ]; then
  echo "不适用：本次无测试组提交"
  exit 0
fi
if [ -z "$FIX_COMMIT" ]; then
  echo "尚未闭合：修复提交待完成"
  exit 0
fi
if [ -z "$BASE_COMMIT" ]; then
  echo "输入错误：缺少 BASE_COMMIT（本批拆分开始前的 HEAD；根提交写 ROOT）"
  exit 2
fi
# 输入守卫（逐文件）：TEST_COMMIT 必须改动了每个 TEST_FILE，FIX_COMMIT 必须改动了每个 SRC_FILE
for f in $TEST_FILE; do
  [ -z "$(git show --format= --name-only "$TEST_COMMIT" -- "$f")" ] && { echo "输入错误：TEST_COMMIT 未改动测试文件 $f"; exit 2; }
done
for f in $SRC_FILE; do
  [ -z "$(git show --format= --name-only "$FIX_COMMIT" -- "$f")" ] && { echo "输入错误：FIX_COMMIT 未改动源文件 $f"; exit 2; }
done
# ★ 本批判定：TEST_COMMIT 必须晚于 BASE_COMMIT。只看「是 FIX 的祖先」无法区分
#   「本批测试提交」与「历史上改过同一测试文件的旧提交」（见 §3 的复现）。
if [ "$(git cat-file -t "$BASE_COMMIT" 2>/dev/null)" = "tree" ]; then
  echo "输入错误：BASE_COMMIT 是 tree，不是 commit（根提交请写 ROOT）"
  exit 2
fi
if [ "$BASE_COMMIT" = "ROOT" ]; then
  # 根提交模式：没有 HEAD 基线，要求 TEST_COMMIT 本身是仓库的根提交。
  # 不能用空树哈希充当 BASE_COMMIT——`git merge-base --is-ancestor` 只接受 commit。
  ROOT_COMMIT=$(git rev-list --max-parents=0 "$TEST_COMMIT" | tail -n 1)
  [ "$ROOT_COMMIT" = "$(git rev-parse "$TEST_COMMIT")" ] || { echo "输入错误：ROOT 模式下 TEST_COMMIT 必须是仓库的根提交"; exit 2; }
else
  git merge-base --is-ancestor "$TEST_COMMIT" "$BASE_COMMIT" && { echo "输入错误：TEST_COMMIT 已包含在 BASE_COMMIT 中（历史提交，不是本批的）"; exit 2; }
  git merge-base --is-ancestor "$BASE_COMMIT" "$TEST_COMMIT" || { echo "输入错误：BASE_COMMIT 不是 TEST_COMMIT 的祖先（哈希或分叉有误）"; exit 2; }
fi
# 顺序：测试组是修复组的祖先
if ! git merge-base --is-ancestor "$TEST_COMMIT" "$FIX_COMMIT"; then
  echo "顺序错误：测试提交不在修复之前"
  exit 1
fi
# 污染：修复提交不得也改动测试文件；测试提交不得也改动源文件
POLLUTION=""
for f in $TEST_FILE; do
  [ -n "$(git show --format= --name-only "$FIX_COMMIT" -- "$f")" ] && POLLUTION="${POLLUTION:+$POLLUTION；}修复提交也含测试文件 $f"
done
for f in $SRC_FILE; do
  [ -n "$(git show --format= --name-only "$TEST_COMMIT" -- "$f")" ] && POLLUTION="${POLLUTION:+$POLLUTION；}测试提交也含源文件 $f"
done
if [ -n "$POLLUTION" ]; then
  echo "顺序未证明：$POLLUTION"
  exit 2
fi
echo "顺序正确"
exit 0
```

> 执行前把前五行占位符换成实际值（前两行已带引号；后三行的 `<...>` 尖括号直接粘进 bash 会语法错）。
> **`TEST_FILE` / `SRC_FILE` 是空格分隔的多文件列表**：**赋值时用引号包住整个列表**
> （`TEST_FILE="a.py b.py"`）——不加引号时 bash 会把第二个路径当命令执行，且列表变量在脚本
> shell 中为空，**逐文件守卫全部未执行**（实测：未加引号时 `regression.py` 被当作命令，守卫
> 循环 0 次，脚本仍可能报「顺序正确」）。
> 使用时展开**不加**引号（`$TEST_FILE`），否则 `"$TEST_FILE"` 会整体当成一个路径；
> 循环体里单个元素**必须**加引号（`-- "$f"`），以免该路径含空格或通配符时被再次拆分。
> 哈希用 `git rev-parse --short` 或完整哈希均可。`BASE_COMMIT` 取「最先把测试与修复拆成两批之前」的 HEAD；
> 仓库尚无提交（根提交）时写 `ROOT`：此时没有 HEAD 基线，脚本要求 `TEST_COMMIT` 本身是仓库的根提交。
> **不要用空树哈希**——`git merge-base --is-ancestor` 只接受 commit，传 tree 会以 128 退出（实测）。

## 2. 分支判定（与脚本输出一一对应）

退出码 `0` 不阻断、`1` 顺序错误须阻止、`2` 需用户处理（顺序未证明或输入错误）。脚本共 **12 个 `exit`**
（两个文件循环 `exit 2` 在多数场景只触发一次），归入**六个结论**——七个输入错误分支合并为一个「输入错误」结论。
以下顺序与脚本自上而下一致：

- `TEST_COMMIT` 为空（本次无测试组，如只提交修复）→ 「不适用：本次无测试组提交」，退出码 0，**不阻断**；
- `FIX_COMMIT` 为空（只提交了测试组，修复尚未提交）→ 「尚未闭合：修复提交待完成」，退出码 0，**不阻断**；
  记录「顺序核对尚未闭合」，不得宣称已通过，修复组提交后再跑一次；
- **输入错误**（任一：`BASE_COMMIT` 为空；`BASE_COMMIT` 是 tree 而非 commit；`TEST_COMMIT` 未改动某测试文件；
  `FIX_COMMIT` 未改动某源文件；`ROOT` 模式下 `TEST_COMMIT` 不是仓库根提交；`TEST_COMMIT` 已包含在
  `BASE_COMMIT` 中；`BASE_COMMIT` 不是 `TEST_COMMIT` 的祖先）→ 退出码 2，
  **不产出顺序结论**，由用户核对哈希与路径后重跑；
- **顺序错误**（`TEST_COMMIT` 不是 `FIX_COMMIT` 的祖先）→ 「顺序错误：测试提交不在修复之前」，退出码 1，阻止继续；
- **顺序未证明**（祖先关系成立，但任一侧污染：修复提交改动了某测试文件，或测试提交改动了某源文件）
  → 退出码 2。同一提交（`TEST_COMMIT` == `FIX_COMMIT`）若同时改了这两类文件必然命中；只改其一由输入校验先报
  「输入错误」。要求用户拆开提交或**显式接受**（记录理由）；
- 否则 → 「顺序正确」，退出码 0。

## 3. 为什么必须传 BASE_COMMIT（假阳性根因）

**「`TEST_COMMIT` 是 `FIX_COMMIT` 的祖先」不足以证明本批测试先提交。** 只要历史上有一个更早、同样改过该
测试文件的提交，把它当 `TEST_COMMIT` 传进去，它天然早于 `FIX_COMMIT`，脚本就报「顺序正确」——哪怕本批真正的
测试提交其实晚于修复。已实测复现：

```
历史：base → c2(改 test.txt) → c3(FIX 改 src.txt) → c4(本批 test，晚于 FIX —— 顺序实际是错的)
传本批 c4：顺序错误 exit=1            ✅
误传历史 c2：顺序正确 exit=0          ❌ 假阳性（缺 BASE_COMMIT 断言的旧脚本）
```

`BASE_COMMIT` 把判据从「文件历史」锚到「本批提交集合」：要求 `TEST_COMMIT` 必须晚于本批起点，同文件的旧提交
于是被「输入错误」挡下。

**不能用 `git log --diff-filter=A -- "$TEST_FILE"` 取「测试文件首次加入的提交」**：真实项目里测试文件通常
**早已存在**，`--diff-filter=A` 返回的就是基线提交（永远早于任何修复），「先修复、后改测试」会被判「顺序正确」。

**也不能靠源文件历史推断**：源文件在基线中已存在时，`git log -1 -- "$SRC_FILE"` 返回基线提交而非空，
无法区分「修复尚未提交」与「修复早于测试」。

**两侧污染检查**放在祖先判定之后：`TEST_COMMIT` 是祖先并不代表这一对提交干净。修复提交顺带修了测试预期、
或测试提交顺带改了源文件，都会让「先红后绿」的证据变弱，因此单独报「顺序未证明」交用户裁决
（合法的「修复时更新既有测试预期」可由用户显式接受并记录理由）。

顺序要求只关心「测试组提交早于修复组提交」，故不把修复跨多个提交的情形纳入本脚本。

## 4. 确认页要求

确认页须留「提交顺序核对」一行，写明命令（含 `TEST_COMMIT=`、`FIX_COMMIT=`、`BASE_COMMIT=`）、
三个标识（`BASE_COMMIT` 为哈希或 `ROOT`）与结论（上述六个结论之一）。

## 5. 多文件批次

一次拆分可能涉及多个测试文件与多个源文件。脚本对 `TEST_FILE` / `SRC_FILE` **逐文件**做输入守卫与污染检查
（§1 的 `for` 循环），多文件时把所有测试文件放进 `TEST_FILE`、所有源文件放进 `SRC_FILE`（空格分隔）即可。

但脚本**无法推断「哪个测试文件覆盖哪个源文件」的配对关系**——它只验证「这一组测试提交早于这一组修复提交，
且两者互不污染」。若不同测试文件覆盖不同源文件、且分属**不同的**修复提交，应**逐对运行并取最严结论**
（任一「顺序错误」即阻止；「顺序未证明」交用户裁决）。把多个不相关修复塞进一次拆分核对是错的——
那是多个逻辑意图，应先按 COMMIT-005 拆成多次「测试+修复」批次。
