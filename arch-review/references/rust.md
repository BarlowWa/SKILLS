# Rust 架构审查参考（arch-review / references）

> 由 arch-review 在识别为 Rust（存在 Cargo.toml 或 `.rs` 源文件）时加载。
> 通用 ARCH 规则见 `arch-review/SKILL.md`；本文提供**证据采集方式**与 Rust 专属规则。

## 一、证据采集

### 1.1 目标与 workspace 清单（首选 `cargo metadata`）

1. 执行 `cargo metadata --format-version 1`，读取以下字段，作为模块边界与目标清单的权威来源：
   - `workspace_members` / `workspace_default_members`：workspace 的完整成员与默认成员。
   - `packages[].targets[]`：`kind`（`lib` / `bin` / `example` / `test` / `bench` / `custom-build`）、`crate_types`（`lib` / `rlib` / `dylib` / `cdylib` / `staticlib` / `proc-macro`）、`src_path`、`test`、`doctest`。
   - `resolve.nodes[].deps[].dep_kinds[]`：`kind` 为 `null`（normal）/ `dev` / `build`，`target` 为 cfg 条件或 `null`。**同一条依赖边可有多条 `dep_kinds`**（同一包既是 build-dependency 又是 dev-dependency，或同一包在不同 `cfg` 下分别被依赖）——判定时须遍历整个数组，不能取第一条。
2. **记录 feature 选择与 target**：不给出 feature 选项时默认启用每个选中包的 default features；`--all-features` / `--no-default-features` / `--features` 会改变解析结果。`resolve` 默认包含所有目标平台，`--filter-platform <triple>` 可收窄。报告须写明本次分析用的是哪一种。官方文档：Cargo Book — cargo metadata。
   > **`workspace.resolver` 版本**：`resolver` 是 workspace 全局选项（依赖里的值被忽略），取值 `"1"`（默认）/ `"2"`（edition 2021 默认）/ `"3"`（edition 2024 默认，需 Rust 1.84+），影响 feature 统一（unification）策略——`"2"` 起 build-deps 与 proc-macro 不再与 normal 依赖共享 feature，dev-deps 只在构建测试/示例时激活。虚拟 workspace 无 `package.edition` 可推断，必须显式写 `[workspace] resolver`。分析 feature 面与「同名依赖是否被重复构建」前先确认它。官方文档：Cargo Book — Resolver「Resolver versions」、Workspaces。
3. `--no-deps` 时 `resolve` 为 `null`，只剩清单信息，不能用来构建依赖图。

### 1.2 crate 级依赖图（`cargo tree`）

1. 架构图基线用 `cargo tree --workspace --edges normal,build`。
   > ⚠️ **默认 edges 是 `normal,build,dev`，默认 target 是 host**。不显式排除 dev，会把测试专用依赖算进架构图；需要目标平台依赖时加 `--target all`。官方文档：Cargo Book — cargo tree。
2. `cargo tree -d`（`--duplicates`）只显示多版本依赖，用于 ARCH-RS-010；`cargo tree -e features` 显示 feature 流向；`cargo tree --invert <crate>` 求反向依赖（入度）；`--depth workspace` 只看 workspace 成员。
3. 输出会用 `(*)` 去重并**合并 feature**（feature unification），接近但不等价于实际构建。官方文档同上。
4. crate 级依赖矩阵从上述输出推导；普通 crate 环通常为空（Cargo 拒绝），dev-dependency 环是唯一例外（见 ARCH-RS-004）。
   > **与 1.1 的证据差异**：`cargo metadata` 的 `resolve` 是 Cargo 的**内部解析结果**（含全部 `dep_kinds` 与 `target` 条件，默认覆盖所有目标平台），`cargo tree` 是**渲染视图**（默认 host、默认含 dev、默认合并 feature）。两者条目不同不代表任一方出错：如 `[target.'cfg(any())'.dependencies]` 这类在 host 上恒假的条件依赖，会出现在 `resolve` 中但被 host 视角的 `cargo tree` 过滤掉（加 `--target all` 可看到目标平台依赖）。报告须写明依赖图取自哪一份、什么 feature/target 组合；两者不一致时以 `resolve` 解释「为什么」，以 `tree` 描述默认构建面，不要互相「纠错」。

### 1.3 模块级依赖

1. crate 内模块边界按 `lib.rs` / `main.rs` 与 `mod` 树确定；从 `mod` 声明与 `use crate::` / `super::` / 绝对路径推导模块图，用 DFS/Tarjan 查环。
2. 可选工具 `cargo modules`（第三方，非 Cargo 内置）可直接生成模块图；不可用时从源码推导并在报告中注明方法。
3. **crate 级普通依赖环被 Cargo 拒绝**；**模块级环可以编译**（Rust 路径解析不要求声明顺序）。模块不是编译单元，环本身不构成编译或链接危害；仅当环跨 crate 边界、或涉及 `pub` 公共 API 且导致分层倒置时记 minor（见 ARCH-RS-004）。

### 1.4 构建产物与补充证据

1. 产物位于 `target/<triple>/<profile>/deps`；用 `cargo metadata` 的 `target_directory` 定位。**不要盲扫 `target/`**：多 target、多 profile 与增量构建残留会新旧混杂，导致误判。
2. `build.rs` 与 proc-macro 在 **host** 上编译/运行，其产物不代表目标平台；交叉编译时尤其要区分。
3. 可选工具（第三方，均非内置能力）：`cargo-semver-checks`、`cargo-public-api`、`cargo-hack`、`cargo-deny`、`cargo-machete`、`cargo-udeps`、`cargo bloat`。工具缺失时只能做源码级启发式判断，须在报告中注明。
4. Cargo **内置**的 `cargo build --timings` 可补充构建耗时证据，产物写入 `target/cargo-timings/cargo-timing.html`（官方文档：cargo-build `--timings`）；它不提供依赖图或 API 面。

## 二、Rust 专属规则

### ARCH-RS-001：二进制目标应薄（major）

业务逻辑放在 lib crate，`bin` 只做参数解析、装配与调用。否则集成测试无法 import bin（`tests/` 编译为独立 crate，只能用库的 public API），逻辑也不可复用。
**证据**：`cargo metadata` 中 `targets[].kind` 只有 `["bin"]` 而无 `lib`；`src/main.rs` 的规模与它依赖的模块数。
**豁免**：`examples/`、`demo/` 等示例 crate（`publish = false`、无对外契约、规模很小）不适用本条。

### ARCH-RS-002：公开面最小化（major）

内部项用 `pub(crate)` / `pub(super)`；`pub` 只留给稳定契约。`pub use` 只重导出稳定 API，禁止 `pub use internal::*` 把内部模块整体泄漏出去。`#[doc(hidden)]` 不是访问控制，不能作为隐藏实现的手段。
**证据**：可选 `cargo public-api` 导出清单；或源码中 `pub` 项与 `pub use` 的统计。

### ARCH-RS-003：feature 必须 additive（major）

启用 feature 不得关闭功能或改变 API 语义；任意组合都应可用，`--all-features` 必须能构建。互斥 feature（如 `foo` 与 `bar` 不能共存）属应避免的形态。组合验证可用 `cargo hack --feature-powerset check`（可选）。
**互斥 feature 的变体**：多个 feature 同时启用时按优先级静默取值（如 C++ 标准取最大）也是互斥形态；若在文档中写明该优先级并用编译期断言/测试固定，记 minor；静默改变语义且无说明记 major。
**依据**：官方文档 Cargo Book — Features：features 应可加，且不得引入 SemVer 不兼容变更。

### ARCH-RS-004：依赖环与 dev-dependency 环（crate 级 major / 模块级 minor）

普通依赖环被 Cargo 拒绝。**dev-dependency 环被允许**（foo 的 dev-dependency 依赖 bar，bar 正常依赖 foo），因为 dev-deps 不参与库本身构建；但它会让同一库出现两份拷贝（一份带测试、一份不带），两者类型不互通，**禁止用它绕过分层**，记 major。模块级环在 Rust 内不构成编译或链接问题（模块不是编译单元）；仅当环跨越 crate 边界、或涉及 `pub` 公共 API 且导致分层倒置时记 minor——本条是 Rust 环状的**唯一**判级依据，SKILL 的 ARCH-004 不复报。`lib.rs` / `mod.rs` 的 re-export（barrel）产生的边不计入环检测。
**证据**：`cargo tree -e dev` / `-e normal,dev`；官方文档 Cargo Book — Resolver 的 dev-dependency cycles 一节。

### ARCH-RS-005：unsafe 的跨 crate 隔离与收口（major）

**跨模块 / 跨 crate 的分布与收口**：`unsafe` 是否集中在专用 crate 或 `-sys` crate；其余 crate 是否 `#![forbid(unsafe_code)]`；安全边界是否在每个 crate 的出口处收口（对外只暴露安全 API，不安全原语不得越过 crate 边界向外泄漏）。判据是**分布**：同一 workspace 内 unsafe 是否被散落到多个业务 crate、每个 crate 出口是否已收口、不需 unsafe 的 crate 是否关闭了 unsafe。
**证据**：按 crate 统计 `unsafe` 块与 `unsafe impl` 的分布；各 crate 的 `forbid` / `deny(unsafe_code)` lint 配置；crate 的公开 API 面是否含 `unsafe` 项。
**与 code-rules 的分工**：
- **单 crate 内**的 unsafe 集中形态（unsafe 是否隔离在专用模块、对外是否只暴露安全 API）由 `code-rules` RUST-UNSAFE-006（warning）判定，**本条不重复报告**；只有该形态上升为跨 crate 分布问题（多个 crate 各自散落 unsafe、crate 出口未收口、未 `forbid`）时才由本条报；
- 单个 `unsafe impl Send/Sync` 的 SAFETY 论证、`unsafe` 块内具体操作的正确性属**单文件写法**，由 `code-rules` RUST-UNSAFE-001 / RUST-UNSAFE-005（blocker）判定，本条同样不重复报告。

### ARCH-RS-006：FFI / 动态库边界只用 C ABI（critical）

跨 FFI 或动态库边界只暴露 C ABI：`#[repr(C)]` 类型、`extern "C"` / `"C-unwind"` 函数。不得暴露 Rust 私有布局、泛型实例或 vtable——Rust 没有稳定 ABI。panic 不得穿越 non-unwinding ABI：Rust panic 会在边界被转成 abort（是否运行 Drop 未指定），native 异常（如 C++）进入该边界则属 UB；需要传播时用 `extern "C-unwind"` 或 `catch_unwind`。
**证据**：`crate_types` 含 `cdylib` / `staticlib`，以及 `extern` 块、`#[repr(C)]` 的导出面。导出符号属性须同时识别两种写法：**edition 2024 起须写 `#[unsafe(no_mangle)]` / `#[unsafe(export_name = "...")]` / `#[unsafe(link_section = "...")]`**（这些属性在 2024 中被要求 `unsafe` 限定，否则编译失败），2021 及更早仍允许不带 `unsafe` 的 `#[no_mangle]`；只查旧写法会对 2024 crate 漏检导出面。依据：Rust Reference「The no_mangle attribute」段落 `abi.no_mangle.unsafe` / `abi.no_mangle.edition2024`（按本机工具链核对）。

### ARCH-RS-007：对外 crate 的 SemVer 兼容（major）

公开 API 变更用 `cargo semver-checks`（可选）检查。破坏性变更走 major 版本；可扩展的公开 enum/struct 应规划 `#[non_exhaustive]`，不可下游实现的 trait 应 sealed——本条只判**发布面策略**：该 crate 是否对外承诺稳定 API、扩展与破坏性变更是否有版本路径（如能否在不 bump major 前加变体）。
**与 code-rules 的分工**：单个类型的写法（何时加 `#[non_exhaustive]`、sealed 用私有 supertrait 还是私有模块、变体/字段的文档标注）归 `code-rules/references/rust.md` RUST-API-002（warning）；同一条缺陷只报一次，重叠时按 code-rules 报，本条只在「发布面整体缺 SemVer 策略」时单独成项。
**依据**：官方 API Guidelines（C-SEALED、C-STRUCT-PRIVATE）；`#[non_exhaustive]` 语义见 Rust Reference「attributes/type_system — non_exhaustive」（`r-attributes.type-system.non_exhaustive`，在定义 crate 内无效果）。

### ARCH-RS-008：build.rs 纪律（major）

必须输出 `cargo::rerun-if-changed` / `cargo::rerun-if-env-changed` 缩小重跑范围——不输出时 Cargo 会扫描整个包目录。build-dependencies 最小化；不访问未声明的资源或网络；`links` 键全局唯一（Cargo 要求同一 native 库至多一个包声明）。只能写 `OUT_DIR`，不得修改包外文件；检查目标平台配置用 `CARGO_CFG_*` 而非 `cfg!`（后者检查 host）。
**证据**：`build.rs` 的 rerun 指令、`Cargo.toml` 的 `[build-dependencies]` 与 `links`。官方文档：Cargo Book — Build Scripts。

### ARCH-RS-009：proc-macro crate 只做薄转换（minor）

proc-macro crate 只负责语法到语法的转换，业务逻辑放普通 lib。proc-macro 目标只能导出 `#[proc_macro*]` 形式的宏，不能作为普通 item 的导出口；把业务逻辑塞进宏 crate 会使其无法被普通测试与复用。
**证据**：`cargo metadata` 中 `crate_types` 含 `proc-macro` / `proc-macro = true`，以及宏 crate 内非宏代码的规模。

### ARCH-RS-010：workspace 依赖与 lint 一致性（major）

共享版本放 `[workspace.dependencies]`，lint 配置放 `[workspace.lints]`，成员用 `workspace = true` 继承。用 `cargo tree -d`（`--duplicates`）查多版本依赖：它**只列出同一包出现多个版本**（隐含 `--invert`），不会列同一版本。同一 workspace 内**自控**依赖重复 major，是 maintenance drift（版本约束不一致、同一 API 两套写法、需多份编译），按本条记 major；第三方传递依赖的重复版本很常见，单凭 `cargo tree -d` 有输出不算缺陷。
**类型不互通只发生在 dev-dependency 环**：同一 package 同一版本在 `resolve` 中只有一个条目；`resolver = "2"`/`"3"` 下同一版本可能因 feature 不同被多次编译，但这不是「两份类型不兼容的拷贝」，`cargo tree -d` 也不会列出它（若要省编译时间用 `-e features` / `-f "{p} {f}"` 看 feature 分裂）。真正会把同一库链接成两份拷贝、使两者类型不兼容的是 dev-dependency 环，按 ARCH-RS-004 判定。
**证据**：`Cargo.toml` 中 `workspace.dependencies` / `workspace.lints` 的覆盖情况；`cargo tree -d` 输出（核对版本号是否确实不同）。`cargo tree -d` 不与 `-e features` 组合（该组合直接报错 `the -e features flag does not support --duplicates`），feature 差异须另用 `cargo tree -e features` / `-f "{p} {f}"` 观察。官方文档：Cargo Book — Workspaces、cargo tree「--duplicates」。

## 三、Rust 场景下的证据注意事项

- **pure lib vs bin-only**：bin-only 包没有 lib 目标，也没有可运行 doctest（`doctest` 仅对 library 有效）；评估「可测试性/可复用性」时先看 `targets[]`，不要假定存在 lib。
- **cdylib / staticlib**：生成 C ABI 动态/静态库时按 ARCH-RS-006 检查；只导出 Rust ABI 符号的 cdylib 无法被 C/C++ 消费。
- **no_std / feature-gated 模块**：默认 feature 下可能看不到整块代码；用 `--all-features` 再分析一次，并在报告中写明 feature 组合，避免把「未启用」误判为「不存在」。
- **target-specific deps**：`[target.'cfg(...)'.dependencies]` 在 host 视角的 `cargo tree` 中会被过滤；跨平台评估需 `--target all` 或按目标 triple 分别分析。
- **dev-dependencies**：只用于 `tests/`、`benches/`、`examples/`，不得进入架构主图；`cargo tree` 默认包含它们，务必显式 `--edges normal,build`。
- **重复版本**：`cargo tree -d` 只列**多版本**（隐含 `--invert`），有输出很常见（传递依赖版本窗口不同），本身不是缺陷；该命令不与 `-e features` 组合（会报 `the -e features flag does not support --duplicates`）。判级前先核对版本号是否真的不同；同一 workspace 内自控依赖重复 major，按 ARCH-RS-010 记 major。
- **同版本多份实例**：同一 package 同一版本在 Cargo 中只有一个实例（feature 已统一），所以「同版本两份、类型不互通」不会来自版本重复——它只来自 dev-dependency 环（见 ARCH-RS-004 / Cargo Book — Resolver 的 dev-dependency cycles 一节）。不要用 `cargo tree -d` 的输出推断同版本分裂。
- **feature 跨 crate 传播（feature unification）**：某包被多个依赖方启用不同 feature 时，Cargo 默认按**并集**构建（`resolver = "2"`/`"3"` 收窄统一：build-deps 与 proc-macro、未构建的目标平台依赖、未被测试/示例使用的 dev-deps 各自独立取 feature，不再并入 normal 依赖的并集）。因此「feature 只在测试路径使用」这类断言必须查 `cargo tree -e features` 或 `-f "{p} {f}"`，不能按声明位置推断；`resolver` 版本（见 1.1）会改变结论。依据：Cargo Book — Features「Feature unification」、Resolver「Resolver versions」。
- **thread-local 全局态**：`thread_local!` 声明的状态**每个线程各有一份**，不跨线程共享，但仍是进程内隐式全局态（生命周期贯穿线程、逃逸出调用方控制）；`LocalKey::with` 在该 key 的析构器正在运行时会 panic，析构器已在本线程跑过之后也可能 panic（std `LocalKey::with` 文档）。ARCH-016 判「跨模块暴露的可变全局态」时须单列 thread-local：它不构成跨线程数据竞争，但构成隐式状态与测试污染（测试线程池复用同一线程时状态会串）。依据：std `thread_local!` / `LocalKey` 文档（按本机工具链核对）。
- **`#[cfg(doc)]` 下的 `static mut`**：`#[cfg(doc)]` 项只为文档构建存在（rustdoc 设置该 cfg），不进入正常构建；因此其中出现的 `static mut` 不改变运行时安全性，但它会出现在公开文档中并被当作可用 API。判据：`#[cfg(doc)]` 项按「文档可见面」计入 ARCH-007/ARCH-RS-002，不按运行时全局态计入 ARCH-016；若该 `static mut` 同时带 `#[cfg(any(..., doc))]` 则在某平台真实构建中生效，按真实形态判定。依据：rustdoc Book「Advanced features — `#[cfg(doc)]`」。
- **edition 2024 导出属性**：2024 crate 的 `#[no_mangle]` 必须写成 `#[unsafe(no_mangle)]`（`export_name` / `link_section` 同理），只查旧写法会漏掉导出面，见 ARCH-RS-006。
- **workspace default-members**：在 workspace 根执行命令且未指定 package 时只作用于 `default-members`；「全部模块」的范围应用 `workspace_members` 或 `--workspace` 确认，否则会漏审。
- **cargo tree 会合并 feature**：同一依赖在 `[dependencies]` 与 `[dev-dependencies]` 中启用不同 feature 时，`cargo tree` 可能合并显示并标 `(*)`；不要据此断言某 feature 只在测试路径使用。
- **模块级环**：Rust 模块不是编译单元，环不导致编译/链接问题；环检测用于发现分层倒置，`lib.rs` / `mod.rs` 的 re-export 桶边应排除后再判断，不能因「能编译」直接判 critical。
- **软链/共享源码**：快照或仓库中经软链共享的目录可能被物化为多份相同文件（哈希一致）；不要据此报重复代码或复制粘贴缺陷。
- **可选工具不是内置能力**：未安装 `cargo-semver-checks` / `cargo-public-api` / `cargo-hack` 等工具时，相关规则只能按源码启发式判断，报告须标注「工具不可用」而非「未发现问题」。
