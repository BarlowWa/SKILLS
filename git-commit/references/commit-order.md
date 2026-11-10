# 提交顺序核对（测试先提交 / 修复后提交）

`SKILL.md` 的 COMMIT-005 要求：同一批变更同时包含「新增/修改测试」与「修复生产代码」时，拆成两个提交且**测试提交在前**。
「在前」不能只靠自述，须在两组都提交后用下列命令证明「测试组提交是修复组提交的祖先」。

本文是该核对的唯一细则来源；SKILL.md 只保留规则与确认页要求，不重复脚本与分支判定。

## 1. 命令

```bash
TEST_FILE=<测试文件>               # 测试组提交所修改的测试文件
SRC_FILE=<源文件>                  # 被该测试覆盖、发生修复的源文件
TEST_COMMIT=<测试组提交>           # 用户确认的测试组提交哈希；本次无测试组时留空
FIX_COMMIT=<修复组提交>            # 用户确认的修复组提交哈希；修复尚未提交时留空

# 证据留存：先于任何分支打印，保证每条路径都能看到两者的提交历史
echo "--- 证据：$TEST_FILE / $SRC_FILE 的提交历史 ---"
git log --format='%h %ad %s' --date=short -- "$TEST_FILE" "$SRC_FILE"
echo "TEST_COMMIT=${TEST_COMMIT:-<空>}  FIX_COMMIT=${FIX_COMMIT:-<空>}"

if [ -z "$TEST_COMMIT" ]; then
  echo "不适用：本次无测试组提交"
  exit 0
fi
if [ -z "$FIX_COMMIT" ]; then
  echo "尚未闭合：修复提交待完成"
  exit 0
fi
if [ -z "$(git show --format= --name-only "$TEST_COMMIT" -- "$TEST_FILE")" ]; then
  echo "输入错误：TEST_COMMIT 未改动指定测试文件"
  exit 2
fi
if [ -z "$(git show --format= --name-only "$FIX_COMMIT" -- "$SRC_FILE")" ]; then
  echo "输入错误：FIX_COMMIT 未改动指定源文件"
  exit 2
fi
if ! git merge-base --is-ancestor "$TEST_COMMIT" "$FIX_COMMIT"; then
  echo "顺序错误：测试提交不在修复之前"
  exit 1
fi
POLLUTION=""
[ -n "$(git show --format= --name-only "$FIX_COMMIT" -- "$TEST_FILE")" ] && POLLUTION="${POLLUTION:+$POLLUTION；}修复提交也含测试文件"
[ -n "$(git show --format= --name-only "$TEST_COMMIT" -- "$SRC_FILE")" ] && POLLUTION="${POLLUTION:+$POLLUTION；}测试提交也含源文件"
if [ -n "$POLLUTION" ]; then
  echo "顺序未证明：$POLLUTION"
  exit 2
fi
echo "顺序正确"
exit 0
```

> 执行前把前四行 `=<>` 的占位符换成实际值（尖括号直接粘进 bash 会语法错）；`TEST_COMMIT` / `FIX_COMMIT`
> 用 `git rev-parse --short` 或完整哈希均可。

## 2. 分支判定（与脚本输出一一对应）

退出码 `0` 不阻断、`1` 顺序错误须阻止、`2` 需用户处理（顺序未证明或输入错误）。脚本共 7 个 `exit`，
归入**六个结论**——两个输入校验分支都记作「输入错误」。以下顺序与脚本自上而下一致：

- `TEST_COMMIT` 为空（本次无测试组，如只提交修复）→ 「不适用：本次无测试组提交」，退出码 0，**不阻断**；
- `FIX_COMMIT` 为空（只提交了测试组，修复尚未提交）→ 「尚未闭合：修复提交待完成」，退出码 0，**不阻断**；
  记录「顺序核对尚未闭合」，不得宣称已通过，修复组提交后再跑一次；
- **输入错误**（`TEST_COMMIT` 未改动 `TEST_FILE`，或 `FIX_COMMIT` 未改动 `SRC_FILE`——传入了无关提交或路径写错）
  → 退出码 2，**不产出顺序结论**，由用户核对两个哈希与两个路径后重跑；
- **顺序错误**（`TEST_COMMIT` 不是 `FIX_COMMIT` 的祖先）→ 「顺序错误：测试提交不在修复之前」，退出码 1，阻止继续；
- **顺序未证明**（已确认是祖先关系，但两个提交互相污染：修复提交也改动了测试文件，或测试提交也改动了源文件）
  → 退出码 2。同一提交（`TEST_COMMIT` == `FIX_COMMIT`）若同时改了这两类文件必然命中此分支；只改其一则由上面的
  输入校验先报「输入错误」。要求用户拆开提交或**显式接受**（记录理由）；
- 否则 → 「顺序正确」，退出码 0。

## 3. 为什么两个哈希都要显式传入

**不能用 `git log --diff-filter=A -- "$TEST_FILE"` 取「测试文件首次加入的提交」。** 真实项目里测试文件通常
**早已存在**，`--diff-filter=A` 返回的就是基线提交（永远早于任何修复），于是「先修复、后改测试」也会被判为
「顺序正确」——恰好放过了要拦的情形。已复现：基线存在 `tests/test_calc.py` 时，按「先 fix、后 test」的顺序提交，
旧写法输出「顺序正确」、退出码 0。

**也不能靠源文件历史推断。** 源文件在基线中已存在时，`git log -1 -- "$SRC_FILE"` 返回的是基线提交而非空，
无法区分「修复尚未提交」与「修复早于测试」。故两个组提交都必须由用户确认后显式传入。

**脚本内置输入守卫**：先验证 `TEST_COMMIT` 确实改动了 `TEST_FILE`、`FIX_COMMIT` 确实改动了 `SRC_FILE`；
任一为空即输出「输入错误」、退出码 2，**不产出顺序结论**。这是为了让「传错哈希」与「顺序错误」彻底分开——
否则一个无关提交会被判成顺序错误。

**两侧污染检查**放在祖先判定之后：`TEST_COMMIT` 是祖先并不代表这一对提交干净。修复提交顺带修了测试预期、
或测试提交顺带改了源文件，都会让「先红后绿」的证据变弱，因此单独报「顺序未证明」交用户裁决
（合法的「修复时更新既有测试预期」可由用户显式接受并记录理由）。

顺序要求只关心「测试组提交早于修复组提交」，故不把修复跨多个提交的情形纳入本脚本。

## 4. 确认页要求

确认页须留「提交顺序核对」一行，写明命令（含 `TEST_COMMIT=<测试组哈希>` 与 `FIX_COMMIT=<修复组哈希>`）、
两个哈希与结论（上述六个结论之一）。
