# 提交顺序核对（测试先提交 / 修复后提交）

`SKILL.md` 的 COMMIT-005 要求：同一批变更同时包含「新增/修改测试」与「修复生产代码」时，拆成两个提交且**测试提交在前**。
「在前」不能只靠自述，须在修复提交完成后用下列命令证明「测试文件的首次提交是修复提交的祖先」。

本文是该核对的唯一细则来源；SKILL.md 只保留规则与确认页要求，不重复脚本与分支判定。

## 1. 命令

```bash
TEST_FILE=<测试文件>               # 本次提交涉及、对应源文件修复的测试文件
SRC_FILE=<源文件>                  # 被该测试覆盖、发生修复的源文件
FIX_COMMIT=<修复提交>              # 用户确认的修复组提交；只提交测试组、修复尚未提交时留空
TEST_FIRST=$(git log --diff-filter=A --format=%H -- "$TEST_FILE" | tail -1)   # 测试文件首次加入的提交

# 证据留存：先于任何分支打印，保证每条路径都能看到两者的提交顺序与时间
echo "--- 证据：$TEST_FILE / $SRC_FILE 的提交历史（测试文件在前）---"
git log --format='%h %ad %s' --date=short -- "$TEST_FILE" "$SRC_FILE"
echo "TEST_FIRST=${TEST_FIRST:-<空>}  FIX_COMMIT=${FIX_COMMIT:-<空>}"

if [ -z "$TEST_FIRST" ]; then
  echo "不适用：测试文件不在本次提交范围"
  exit 0
fi
if [ -z "$FIX_COMMIT" ]; then
  echo "尚未闭合：修复提交待完成"
  exit 0
fi
if [ -z "$(git show --format= --name-only "$FIX_COMMIT" -- "$SRC_FILE")" ]; then
  echo "输入错误：FIX_COMMIT 未改动指定源文件，未产出顺序结论"
  exit 2
fi
if [ -n "$(git show --format= --name-only "$FIX_COMMIT" -- "$TEST_FILE")" ]; then
  echo "顺序未证明：测试与修复在同一提交"
  exit 2
elif git merge-base --is-ancestor "$TEST_FIRST" "$FIX_COMMIT"; then
  echo "顺序正确"
  exit 0
else
  echo "顺序错误：测试提交不在修复之前"
  exit 1
fi
```

## 2. 分支判定（与脚本输出一一对应）

退出码 `0` 不阻断、`1` 顺序错误须阻止、`2` 需用户处理（顺序未证明或输入错误）。共六个结果，对应脚本体中
4 个 `if` + 1 个 `elif` + 1 个 `else` 的六个 `exit`；「顺序正确 / 顺序错误」是同一判定的两个方向。

- `TEST_FIRST` 为空（测试文件不在本次提交范围）→ 「不适用：测试文件不在本次提交范围」，退出码 0，**不阻断**；
- `FIX_COMMIT` 为空（只提交测试组，修复尚未提交）→ 「尚未闭合：修复提交待完成」，退出码 0，**不阻断**；
  记录「顺序核对尚未闭合」，不得宣称已通过，修复组提交后再跑一次；
- **输入错误**（`git show --format= --name-only "$FIX_COMMIT" -- "$SRC_FILE"` 为空，即 `FIX_COMMIT` 未改动指定源文件
  ——传入了无关提交或 `SRC_FILE` 写错）→ 「输入错误：FIX_COMMIT 未改动指定源文件，未产出顺序结论」，退出码 2，
  **不产出顺序结论**，由用户核对 `FIX_COMMIT` / `SRC_FILE` 后重跑；
- **修复提交本身改动了测试文件**（`git show --format= --name-only "$FIX_COMMIT" -- "$TEST_FILE"` 非空）
  → 「顺序未证明：测试与修复在同一提交」，退出码 2，覆盖「新增测试与修复同一提交」与「已有测试与修复同批修改」
  两种形态；要求用户拆开提交或显式接受（记录理由）；
- 否则以 `git merge-base --is-ancestor` 退出码判定，0 为「顺序正确」（退出码 0），非 0 为「顺序错误」（退出码 1）；
  检出「顺序错误」时阻止继续。

## 3. 为什么 `FIX_COMMIT` 要显式传入

源文件在基线中已存在时，`git log -1 -- "$SRC_FILE"` 返回的是基线提交而非空，脚本便无法区分「修复尚未提交」
与「修复早于测试」——这两种情形（「尚未闭合」与「顺序错误」）的源文件历史从哈希上看完全一样，只能靠
「当前轮是否已产出修复组提交」来分辨。故 `FIX_COMMIT` 取修复组提交的哈希，只提交测试组时留空。

**脚本内置输入守卫**：在 `FIX_COMMIT` 非空判断之后、同提交判断之前，先用
`git show --format= --name-only "$FIX_COMMIT" -- "$SRC_FILE"` 确认该提交确实改动了源文件；输出为空说明传入的
不是修复提交（或 `SRC_FILE` 写错），脚本输出「输入错误」并以退出码 2 结束，**不产出顺序结论**，
由用户核对输入后重跑。

顺序要求只关心「测试的首次加入早于修复提交」，故不把修复跨多个提交的情形纳入本脚本。

## 4. 确认页要求

确认页须留「提交顺序核对」一行，写明命令（含 `FIX_COMMIT=<修复组哈希>`）与结论（上述六个结果之一）。
