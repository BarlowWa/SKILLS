---
name: code-rules
description: 在编写、编辑、审查或重构 C++ / Rust / Java / Python 源码时使用（.h/.hpp/.cpp/.cc/.cxx/.hh/.hxx/.ipp/.inl/.tpp/.cppm/.rs/.java/.py/.pyi）。提供强制性编码规范：通用基线（安全、资源、复杂度、日志）加按语言加载的专属规则（内存与所有权、命名、OOP、多线程、错误处理、现代惯用法、禁用模式）。当用户创建、修改或要求审查源码时激活。测试与基准文件不适用本技能，按『豁免』处理；SQL 由 db-rules 负责。
---

# 编码规范强制执行

对每个源码变更，先**识别语言并加载对应规则文件**，再对照规则逐条检查。此 skill 是**强制性关卡**——所有 blocker 必须在报告完成前修复（写新代码/重构），或在报告中明确指出并给出修复方案（**仅审查**模式）。

## 工作流程

1. **识别语言**：按文件扩展名查下方路由表。一个任务涉及多语言时，逐个语言分别加载。
2. **加载规则**：用 `Read` 读取命中的 `references/<lang>.md`（本技能目录下的绝对路径），并通读本文件的 G-xxx 通用基线。
   - **语言已识别但无对应参考文件** → 只应用 G-xxx，并在报告顶部标注：`⚠️ 未加载语言专属规则：<lang>`。不得静默跳过。
   - **语言无法识别**（无扩展名、生成文件、混合格式）→ 同走 G-xxx 并注明。
3. **写中**：边写边应用，不推迟到事后。
4. **写后/审查**：逐条对照「G 基线 + 该语言文件」检查；发现违规立即修复。
5. **报告**：按『审查输出格式』输出，分类只列本任务实际加载过的语言。

## 语言路由表

| 语言 | 扩展名 | 规则文件 | 状态 |
| ---- | ------ | -------- | ---- |
| C++ | `.h` `.hpp` `.cpp` `.cc` `.cxx` `.hh` `.hxx` `.ipp` `.inl` `.tpp` `.cppm` | `references/cpp.md` | ✅ 已就绪 |
| Rust | `.rs` | `references/rust.md` | ✅ 已就绪（cxx 1.0.205 实测；CONC / no_std 未被该样本覆盖，按文档判） |
| Java | `.java` | `references/java.md` | ✅ 已就绪（JDK 25 + jsoup 1.18.3 实测；多-release / `--release` / `Locale` / 集合 / 相等性等已校准） |
| Python | `.py` `.pyi` | `references/python.md` | ✅ 已就绪（CPython 3.14.6 + pytest 9.2.0 / ruff 0.17.6 / mypy 2.4.1 实测；httpx 样本真实审查拦下 B904 / S101 / BLE001，独立复核 **PASS**：PY-EXC-003 / PY-EXC-004 / PY-EXC-001。**样本未触达**：free-threaded 构建的并发行为按文档判） |

> `.h` 也可能是 C 头文件：按项目语境判定；项目为纯 C 且已有 C 规则文件时按其执行，否则按 C++ 处理（`cpp.md` 的 C 互操作豁免适用）。
> 以 `_` 开头的参考文件（如 `_template.md`）不参与路由。
> **路由优先级**：先按扩展名、再看是否属于豁免路径；扩展名能唯一确定语言但目录未列出时，仍按该语言处理并在报告中注明依据，不得因路径未命中而静默跳过。多语言任务逐个语言分别加载。

## 严重级别

| 级别    | 含义                                  |
| ------- | ------------------------------------- |
| blocker | 必须修复，违规代码不得提交             |
| warning | 优化建议，应处理但不阻塞提交           |

---

## G：通用基线（语言中立，所有语言适用）

- **G-SECRET**（blocker）：禁止密码、API 密钥、Token、私钥等敏感信息以字面量写入源码；用环境变量、不入库的配置文件或密钥管理服务。
- **G-CMDINJ**（blocker）：禁止把外部可控字符串拼接进 shell/系统命令；必须调用外部命令时用**参数列表 API**（不经 shell 解析）并白名单校验可执行路径。
- **G-SWALLOW**（blocker）：禁止吞掉错误——空的 catch/except、忽略返回的错误值、或把错误打成日志后继续执行而调用方无从感知。要么传播（可包装，但保留原始信息），要么**显式注明有意忽略及理由**。
- **G-RELEASE**（blocker）：资源（文件、连接、锁、句柄）必须绑定对象生命周期自动释放（析构/`with`/try-with-resources/defer 等）；任何在异常或提前返回路径上会漏释放的写法均属违规。
- **G-MAGIC**（blocker）：有业务/领域语义的字面值必须是命名常量或枚举。`0` / `1` / `-1` / 空串 / 布尔及上下文自明的惯用值不视为魔法数字。
- **G-COMPLEX-DUP**（warning）：语义等价或高度相似的代码块应提取公共函数（跨变量名/类型的结构性重复，工具查不出，需人工判断）。
- **G-COMPLEX-PARAM**（warning）：成组出现的参数（如 `x1,y1,x2,y2`、`host,port,timeout`）应封装为结构体/数据类，降低传参顺序错误。
- **G-COMPLEX-SRP**（warning）：函数只做一件事；解析 + 业务计算 + I/O 混在一个函数里应拆分。
- **G-COMPLEX-NEST**（warning）：嵌套深度 >4 层考虑早返回或提取子函数；状态机等合理场景由审查者判断，不机械报警。
- **G-LOG**（warning）：日志等级集合与日志回调/接口在单一中心位置定义，禁止各模块自定义等级。

> 通用基线只含**对任意语言都成立**的判据。类型系统、所有权/生命周期、空值表示、错误模型、并发原语、命名与文件布局、构建与警告策略一律放在各语言文件中，**不从语言文件上抽**——抽象会弱化约束。

### G ↔ 语言文件去重表

同一缺陷同时命中 G 规则与语言文件同义条目时，**只报一次，以语言文件 ID 为准**；语言文件没有对应条目时才用 G ID。若语言文件条目级别低于 G，按**更严者**报级别。

| G 规则 | C++ 对应 | Rust 对应 | Java 对应 | Python 对应 |
| ------ | -------- | --------- | --------- | ----------- |
| G-MAGIC | MAGIC-001 | RUST-MAGIC-001 | JAVA-MAGIC-001 | PY-MAGIC-001 |
| G-RELEASE | ERR-003 | RUST-OWN-003 | JAVA-RES-001 | PY-RES-001 |
| G-COMPLEX-DUP | CPLX-W001 | （无对应，按 G-COMPLEX-DUP 报） | （同上） | （无对应） |
| G-COMPLEX-PARAM | CPLX-W002 | （无对应，按 G-COMPLEX-PARAM 报） | （同上） | （无对应） |
| G-COMPLEX-SRP | CPLX-W003 | （无对应，按 G-COMPLEX-SRP 报） | （同上） | （无对应） |
| G-COMPLEX-NEST | CPLX-W004 | （无对应，按 G-COMPLEX-NEST 报） | （同上） | （无对应） |
| G-LOG | LOG-W001 | RUST-LOG-W001 | JAVA-LOG-W001 | PY-LOG-W001 |
| G-SECRET | SEC-C003 | RUST-SEC-003 | JAVA-SEC-001 | PY-SEC-001 |
| G-CMDINJ | SEC-C002 | RUST-SEC-001 | JAVA-SEC-002 | PY-SEC-002 |
| G-SWALLOW | （无对应，按 G-SWALLOW 报） | RUST-ERR-002 | JAVA-EXC-001 | PY-EXC-002 |

---

## 审查输出格式

```
## 编码规范审查

**语言**：<实际加载的语言与规则文件；降级时写明「未加载语言专属规则：<lang>」>

### Blocker 检查
- [x] G：通用基线 —— 通过
- [x] <语言类别，如 MEM/NAME/SEC> —— 通过
- [ ] <类别>：<问题> —— <规则 ID> @ <文件:行>；修复：<方案>

### Warning 检查
- [x] G-COMPLEX / G-LOG —— 通过
- [ ] <类别>：<问题> —— <规则 ID> @ <文件:行>；建议：<方案>

### 总结
- Blocker：N 项 —— 必须修复
- Warning：N 项
```

分类名一律取自**实际加载的语言文件**的章节标题，不写死任何语言的类别。

## 豁免

| 语言 | 豁免范围 | 由谁负责 |
| ---- | -------- | -------- |
| C++ | `tests/`、`test/`、`unittest/`、`*_test.*`、`*_unittest.*` | `test-author`（设计）/ `test-review`（审查） |
| C++ | `*_bench.cpp`、`bench/`、`benchmark/` 基准 | 全部豁免 |
| Rust | `tests/`、`benches/`；`src/` 内 `#[cfg(test)]` 模块 | `test-author`（设计）/ `test-review`（审查） |
| Java | `src/test/`、`src/testFixtures/`、`*Test.java`、`*Tests.java`、`*IT.java` | 同上 |
| Python | `tests/`、`test_*.py`、`*_test.py`、`conftest.py` | 同上 |
| 全部 | SQL / DDL / migration（`.sql`）不在本技能范围 | `db-rules` |
| 全部 | 模块依赖、分层、循环依赖、API/ABI 等架构级问题 | `arch-review`（C++ / Rust / Java / Python 证据均已就绪） |

- 测试文件**豁免本技能全部规则**，由 `test-author`（设计）/ `test-review`（审查）负责；对应语言参考未就绪时，报告须写「未加载语言专属细化/执行证据：<lang>」，不得判为「通过」。
- 基准文件同样豁免 code-rules：`test-author` 不适用；`test-review` **仅保留执行链判据**（必须真的被构建并注册）。
- 与 C 遗留库互操作时，C++ 文件可按 `references/cpp.md` 的「豁免」条款放宽，并在使用处注释说明。
- **冲突一律取更严者**：通用基线与语言文件、或不同规则来源冲突时，取更严格的级别与要求，禁止让较松的来源静默降级。

## 添加新语言

1. 复制 `references/_template.md` 为 `references/<lang>.md`；只收「模型默认会做错 / 本人明确偏好」的条目，不抄通用常识。
2. 在上方路由表新增一行（扩展名 → 文件），在豁免表补该语言的测试/基准路径。
3. 规则 ID 用该语言前缀（Rust 为 `RUST-<CAT>-NNN`，Java / Python 用 `JAVA-` / `PY-`；warning 类条目可沿用字母编号如 `RUST-LOG-W001`，与 C++ 的 `CPLX-W001` 同风格），**不与 C++ 的 ID 命名空间共用**；G-xxx 是有意共享的基线。
4. 完成判据：该语言某次真实审查报告中无已知漏报，且至少拦下 1 条真实违规。
