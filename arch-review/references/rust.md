# Rust 架构审查参考（arch-review / references）

> 由 arch-review 在识别为 Rust（存在 Cargo.toml 或 `.rs` 源文件）时加载。
> 通用 ARCH 规则见 `arch-review/SKILL.md`；本文提供**证据采集方式**与 Rust 专属规则。

## 一、证据采集

### 1.1 目标与 workspace 清单（首选 `cargo metadata`）

1. 执行 `cargo metadata --format-version 1`，读取以下字段，作为模块边界与目标清单的权威来源：
   - `workspace_members` / `workspace_default_members`：workspace 的完整成员与默认成员。
   - `packages[].targets[]`：`kind`（`lib` / `bin` / `example` / `test` / `bench` / `custom-build`）、`crate_types`（`lib` / `rlib` / `dylib` / `cdylib` / `staticlib` / `proc-macro`）、`src_path`、`test`、`doctest`。
   - `resolve.nodes[].deps[].dep_kinds[]`：`kind` 为 `null`（normal）/ `dev` / `build`，`target` 为 cfg 条件或 `null`。
2. **记录 feature 选择与 target**：不给出 feature 选项时默认启用每个选中包的 default features；`--all-features` / `--no-default-features` / `--features` 会改变解析结果。`resolve` 默认包含所有目标平台，`--filter-platform <triple>` 可收窄。报告须写明本次分析用的是哪一种。官方文档：Cargo Book — cargo metadata。
3. `--no-deps` 时 `resolve` 为 `null`，只剩清单信息，不能用来构建依赖图。

### 1.2 crate 级依赖图（`cargo tree`）

1. 架构图基线用 `cargo tree --workspace --edges normal,build`。
   > ⚠️ **默认 edges 是 `normal,build,dev`，默认 target 是 host**。不显式排除 dev，会把测试专用依赖算进架构图；需要目标平台依赖时加 `--target all`。官方文档：Cargo Book — cargo tree。
2. `cargo tree -d`（`--duplicates`）只显示多版本依赖，用于 ARCH-RS-010；`cargo tree -e features` 显示 feature 流向；`cargo tree --invert <crate>` 求反向依赖（入度）；`--depth workspace` 只看 workspace 成员。
3. 输出会用 `(*)` 去重并**合并 feature**（feature unification），接近但不等价于实际构建。官方文档同上。
4. crate 级依赖矩阵从上述输出推导；普通 crate 环通常为空（Cargo 拒绝），dev-dependency 环是唯一例外（见 ARCH-RS-004）。

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

### ARCH-RS-004：依赖环与 dev-dependency 环（major）

普通依赖环被 Cargo 拒绝。**dev-dependency 环被允许**（foo 的 dev-dependency 依赖 bar，bar 正常依赖 foo），因为 dev-deps 不参与库本身构建；但它会让同一库出现两份拷贝（一份带测试、一份不带），两者类型不互通，**禁止用它绕过分层**。模块级环在 Rust 内不构成编译或链接问题（模块不是编译单元）；仅当环跨越 crate 边界、或涉及 `pub` 公共 API 且导致分层倒置时记 minor。`lib.rs` / `mod.rs` 的 re-export（barrel）产生的边不计入环检测。
**证据**：`cargo tree -e dev` / `-e normal,dev`；官方文档 Cargo Book — Resolver 的 dev-dependency cycles 一节。

### ARCH-RS-005：unsafe 隔离（major）

`unsafe` 集中在专用模块或 `-sys` crate，对外只暴露安全 API；其余 crate 可加 `#![forbid(unsafe_code)]`。每个 `unsafe impl Send/Sync` 必须有 SAFETY 论证，说明为何满足线程安全契约。
**证据**：按模块统计 `unsafe` 块与 `unsafe impl` 的数量与分布。

### ARCH-RS-006：FFI / 动态库边界只用 C ABI（critical）

跨 FFI 或动态库边界只暴露 C ABI：`#[repr(C)]` 类型、`extern "C"` / `"C-unwind"` 函数。不得暴露 Rust 私有布局、泛型实例或 vtable——Rust 没有稳定 ABI。panic 不得穿越 non-unwinding ABI：Rust panic 会在边界被转成 abort（是否运行 Drop 未指定），native 异常（如 C++）进入该边界则属 UB；需要传播时用 `extern "C-unwind"` 或 `catch_unwind`。
**证据**：`crate_types` 含 `cdylib` / `staticlib`，以及 `extern` 块、`#[repr(C)]`、`#[no_mangle]` 的使用面。

### ARCH-RS-007：对外 crate 的 SemVer 兼容（major）

公开 API 变更用 `cargo semver-checks`（可选）检查。可扩展的公开 enum/struct 加 `#[non_exhaustive]`；不可下游实现的 trait 用 sealed 模式；破坏性变更走 major 版本。
**依据**：官方 API Guidelines（C-SEALED、C-STRUCT-PRIVATE）；`#[non_exhaustive]` 语义见 Rust Reference。

### ARCH-RS-008：build.rs 纪律（major）

必须输出 `cargo::rerun-if-changed` / `cargo::rerun-if-env-changed` 缩小重跑范围——不输出时 Cargo 会扫描整个包目录。build-dependencies 最小化；不访问未声明的资源或网络；`links` 键全局唯一（Cargo 要求同一 native 库至多一个包声明）。只能写 `OUT_DIR`，不得修改包外文件；检查目标平台配置用 `CARGO_CFG_*` 而非 `cfg!`（后者检查 host）。
**证据**：`build.rs` 的 rerun 指令、`Cargo.toml` 的 `[build-dependencies]` 与 `links`。官方文档：Cargo Book — Build Scripts。

### ARCH-RS-009：proc-macro crate 只做薄转换（minor）

proc-macro crate 只负责语法到语法的转换，业务逻辑放普通 lib。proc-macro 目标只能导出 `#[proc_macro*]` 形式的宏，不能作为普通 item 的导出口；把业务逻辑塞进宏 crate 会使其无法被普通测试与复用。
**证据**：`cargo metadata` 中 `crate_types` 含 `proc-macro` / `proc-macro = true`，以及宏 crate 内非宏代码的规模。

### ARCH-RS-010：workspace 依赖与 lint 一致性（major）

共享版本放 `[workspace.dependencies]`，lint 配置放 `[workspace.lints]`，成员用 `workspace = true` 继承。用 `cargo tree -d` 查重复 major 版本：重复版本既增加编译时间，不同版本的类型也互不兼容，无法直接互通。
**证据**：`Cargo.toml` 中 `workspace.dependencies` / `workspace.lints` 的覆盖情况；`cargo tree -d` 输出。官方文档：Cargo Book — Workspaces、cargo tree。

## 三、Rust 场景下的证据注意事项

- **pure lib vs bin-only**：bin-only 包没有 lib 目标，也没有可运行 doctest（`doctest` 仅对 library 有效）；评估「可测试性/可复用性」时先看 `targets[]`，不要假定存在 lib。
- **cdylib / staticlib**：生成 C ABI 动态/静态库时按 ARCH-RS-006 检查；只导出 Rust ABI 符号的 cdylib 无法被 C/C++ 消费。
- **no_std / feature-gated 模块**：默认 feature 下可能看不到整块代码；用 `--all-features` 再分析一次，并在报告中写明 feature 组合，避免把「未启用」误判为「不存在」。
- **target-specific deps**：`[target.'cfg(...)'.dependencies]` 在 host 视角的 `cargo tree` 中会被过滤；跨平台评估需 `--target all` 或按目标 triple 分别分析。
- **dev-dependencies**：只用于 `tests/`、`benches/`、`examples/`，不得进入架构主图；`cargo tree` 默认包含它们，务必显式 `--edges normal,build`。
- **重复版本**：`cargo tree -d` 有输出很常见（传递依赖版本窗口不同），本身不是缺陷；它也可能列出**同一版本、不同 feature 集**的条目，这不是重复版本。判级前先核对版本号；同一 workspace 内自控依赖重复 major，按 ARCH-RS-010 记 major。
- **workspace default-members**：在 workspace 根执行命令且未指定 package 时只作用于 `default-members`；「全部模块」的范围应用 `workspace_members` 或 `--workspace` 确认，否则会漏审。
- **cargo tree 会合并 feature**：同一依赖在 `[dependencies]` 与 `[dev-dependencies]` 中启用不同 feature 时，`cargo tree` 可能合并显示并标 `(*)`；不要据此断言某 feature 只在测试路径使用。
- **模块级环**：Rust 模块不是编译单元，环不导致编译/链接问题；环检测用于发现分层倒置，`lib.rs` / `mod.rs` 的 re-export 桶边应排除后再判断，不能因「能编译」直接判 critical。
- **软链/共享源码**：快照或仓库中经软链共享的目录可能被物化为多份相同文件（哈希一致）；不要据此报重复代码或复制粘贴缺陷。
- **可选工具不是内置能力**：未安装 `cargo-semver-checks` / `cargo-public-api` / `cargo-hack` 等工具时，相关规则只能按源码启发式判断，报告须标注「工具不可用」而非「未发现问题」。
