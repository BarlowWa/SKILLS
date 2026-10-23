# 跨 skill 严重级别映射

仅在审查涉及 C++ / 数据库实现、需引用他 skill 结论作依据时使用。本文件是**外部快照**——他 skill 的级别口径变更时须同步本表（下方附有核对命令）。

---

## 映射表

- **blocker** ≈ 各 skill 的**最高级**：`code-rules` blocker、`arch-review` critical、`test-review` blocker、`test-author` blocker、`db-rules` blocker
- **major** ≈ `arch-review` major（其余 skill 为两级，无对应级）
- **minor** ≈ `arch-review` minor、各两级 skill（`code-rules` / `test-review` / `test-author` / `db-rules`）的 `warning`

> 现有 skill 的严重级别并不统一（两级与三级并存），引用时以本表为准换算。注意两级 skill 的 `warning` 只能落到本技能 `minor`——两级 skill 中「不阻塞提交」的建议，在本技能里没有 `major` 的对应级，不要为了对齐而拔高或压低其级别。

## 附录：核对他 skill 实际级别

映射表会随他 skill 改版而静默过期。怀疑不一致时，在 skills 根目录执行：

```bash
# code-rules 的 blocker/warning 规则在 references/cpp.md（其他语言文件按需创建）
grep -nE 'critical|blocker|warning|major|minor' \
  arch-review/SKILL.md code-rules/SKILL.md code-rules/references/cpp.md \
  test-review/SKILL.md test-author/SKILL.md db-rules/SKILL.md | head -30
```

- `arch-review` 应为 `critical` / `major` / `minor` 三级；
- 其余四个（`code-rules` / `test-review` / `test-author` / `db-rules`）应为 `blocker` / `warning` 两级。
