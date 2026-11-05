# 跨 skill 严重级别映射

> **已内联：映射表已移入 `references/blocking-criteria.md` 的「与其他 skill 的级别换算」一节**——`plan-review` 审查子 agent 只加载 `review-dimensions.md` 与 `blocking-criteria.md` 两个 reference，不再加载本文件。**本文件保留作独立核检工具**：下面的核对命令用于验证映射表未随他 skill 改版而过期；表内容如与 `blocking-criteria.md` 不一致，以 `blocking-criteria.md` 为准并**两处同步**。

仅在审查涉及 C++ / Rust / Java / Python / 数据库实现、需引用他 skill 结论作依据时使用（目前 C++ 与 Rust 有专属语言规则文件，Java / Python 按各技能降级路径）。本文件是**外部快照**——他 skill 的级别口径变更时须同步本表（下方附有核对命令）。

---

## 映射表

- **blocker** ≈ 各 skill 的**最高级**：`code-rules` blocker、`arch-review` critical、`test-review` blocker、`test-author` blocker、`db-rules` blocker
- **major** ≈ `arch-review` major（其余 skill 为两级，无对应级）
- **minor** ≈ `arch-review` minor、各两级 skill（`code-rules` / `test-review` / `test-author` / `db-rules`）的 `warning`

> 现有 skill 的严重级别并不统一（两级与三级并存），引用时以本表为准换算。注意两级 skill 的 `warning` 只能落到本技能 `minor`——两级 skill 中「不阻塞提交」的建议，在本技能里没有 `major` 的对应级，不要为了对齐而拔高或压低其级别。

## 附录：核对他 skill 实际级别

映射表会随他 skill 改版而静默过期。怀疑不一致时，在 skills 根目录执行：

```bash
# code-rules 的 blocker/warning 规则在 references/<lang>.md（C++ / Rust 已就绪）
grep -nE 'critical|blocker|warning|major|minor' \
  arch-review/SKILL.md arch-review/references/rust.md \
  code-rules/SKILL.md code-rules/references/cpp.md code-rules/references/rust.md \
  test-review/SKILL.md test-review/references/rust.md \
  test-author/SKILL.md test-author/references/rust.md db-rules/SKILL.md
```

- `arch-review` 应为 `critical` / `major` / `minor` 三级；
- 其余四个（`code-rules` / `test-review` / `test-author` / `db-rules`）应为 `blocker` / `warning` 两级。
