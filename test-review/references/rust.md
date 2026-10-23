# Rust 测试审查参考（test-review / references）

> 由 test-review 在测试文件为 Rust 时加载。通用判据见 `test-review/SKILL.md`；本文提供 **Cargo / libtest / rustdoc 的执行证据获取方式**、跳过与断言不可达的形态词表，以及 Rust 项目中最容易造成误判的陷阱。工具行为均引自 Cargo、rustc、rustdoc 官方文档或 libtest 公开源码，**不代表任何一次具体运行的结果**；无法取得构建/运行证据时记「未能判定（缺构建/运行证据）」。

## 一、执行证据获取（EXEC-001 / EXEC-002 / EXEC-006）

### 1.1 构建配置与目标清单（EXEC-001；ORG-001/002/003）

- 机器可读的目标清单：在包/工作区根执行 `cargo metadata --format-version 1`，读 `packages[].targets[]` 的 `kind`（`lib`/`bin`/`test`/`bench`/`example`/`custom-build`）、`src_path`、`test`、`doctest`、`required-features`（官方文档：cargo-metadata）。
- 测试源归属（ORG-001/002）：单元测试写在源文件的 `#[cfg(test)] mod tests`；集成测试放 `tests/`，每个顶层 `.rs` 独立编译为一个 crate（官方文档：Cargo Targets — Integration tests）。`tests/common/mod.rs` 是文档指定的共享辅助模块，**不是**测试目标，不得报「未进构建」。
- 双向差集：`targets[]` 中 `kind = ["test"]` 的 `src_path` ↔ 仓库 `tests/**` 测试源；**不要**用文本搜 `tests/` 或 `mod` 就下结论。
- `autotests = false` 关闭自动发现，未在 `[[test]]` 声明的 `tests/` 文件**不会被编译**（官方文档：Cargo Targets — Target auto-discovery）。这类文件在源码里完全正常，只能反查。
- `required-features` 未启用的目标会被跳过（官方文档：Cargo Targets — required-features）：测试文件存在但 CI 未开对应 feature 时等于没跑，按 EXEC-001/EXEC-003 记录。
- 测试层级（ORG-003）：集成测试只能用库的 public API；声明为 unit 却依赖真实网络/子进程/全局状态的，按层级失当处理。

### 1.2 注册与执行范围（EXEC-002）

- Rust 没有 CTest 式单独注册步骤：Cargo 用 `--test` 编译测试目标，libtest 自动收集 `#[test]`（官方文档：cargo-test）。注册证据 = 目标清单 + 运行时 `--list`，不是 Cargo.toml 字面文本。
- `cargo test` 默认目标：lib 单测、bins 单测、集成测试、lib 的 doctest；examples 仅编译不运行（官方文档：cargo-test — Target Selection）。
- 工作区：workspace 根直接 `cargo test` 只跑 `default-members`；未设置时非 virtual workspace 用 root package，virtual workspace 用全部成员（官方文档：Cargo Workspaces）。**必须记录命令与 cwd**；CI 建议 `cargo test --workspace --all-features`，否则成员测试会静默缺席。
- doctest 只对 lib 目标生成且 `doctest = true`（默认）；`doctest = false` 关闭，bin-only crate 没有 doctest（官方文档：Cargo Targets — doctest）。

### 1.3 注册清单与执行状态（EXEC-002 / EXEC-003）

- 清单：`cargo test --workspace --all-features -- --list`（Cargo 对每个测试目标分别调用 libtest）。需要机器可读的目标/产物信息时用 Cargo 侧的 `--message-format=json`，它必须放在 `--` **之前**，否则会被当成 libtest 参数。
- **list 中出现 ≠ 会执行**：libtest 默认 `RunIgnored::No` 只保留 `ignore` 标记、不移除用例（源码：libtest `filter_tests` 中 `RunIgnored::No => {}`；`list_tests_console` 遍历过滤结果并累计 `desc.ignore`）。忽略状态须另查源码属性或运行输出中的 `ignored` 计数。
- `#[ignore]` 用例仍被编译；`--ignored` 只跑忽略项，`--include-ignored` 两者都跑（官方文档：rustc Tests / Reference）。
- `harness = false` 的目标自行提供 `main`，不走 libtest（官方文档：Cargo Targets — harness）；`--list` 不会枚举其用例，必须单独核对其收集/执行逻辑。
- 可选证据：`cargo test --no-run --message-format=json` 可确认测试目标确实被编译（只编译不运行）。
- nextest：`cargo nextest run` **不运行 doctest**（官方文档/issue；按项目 nextest 版本核对）；CI 只用 nextest 时须另跑 `cargo test --doc`。

### 1.4 计数与对账（EXEC-006）

- 静态搜索 `#[test]` 会漏掉 `#[tokio::test]`、`#[rstest]`、`#[test_case]` 等过程宏生成的用例；**以 `--list` 的运行时清单为准**。
- doctest 由 rustdoc 驱动的独立 harness 运行，通常在输出中单列（`Doc-tests <crate>`）；计数时单独核对，不要与 libtest 目标混算。以 `cargo test --doc` 的运行输出为准；`--list` 与该组合的实际行为按本机工具链版本核对。
- 清单含 ignored，**不是**执行集合；对账前先按忽略状态分组。
- 按名字双向差集（测试源码 ↔ 目标清单 ↔ `--list`），归一化模块路径与多字节/转义字符；不要用「声明总数 − 执行总数」判红。目标名 = 文件名 stem，可直接与 `tests/*.rs` 对照。

## 二、跳过与条件编译形态词表（EXEC-003 / EXEC-005）

- `#[ignore]`、`#[ignore = "reason"]`、`#[cfg_attr(cond, ignore)]`。
- `#[cfg(feature = "...")]`、`#[cfg(target_os = "...")]`、`#[cfg(not(...))]` 包裹整个测试函数或 `mod tests`：未开 feature/平台不符时**静默不编译**，既不进目标也不进 `--list`；先看 `cfg` 是否成对替换。
- `[[test]] required-features` 未启用：整个集成测试目标被跳过（同 EXEC-001）。
- 前置 guard + 提早 return（无标记、运行时报通过，最易漏检）：
  ```rust
  #[test]
  fn parses_real_config() {
      if std::env::var("CONFIG_FIXTURE").is_err() { return; } // ← 无标记的静默跳过
      assert_eq!(parse(&read_fixture()), EXPECTED);
  }
  ```
  同类：`cfg!(...)` + `return`、`let Ok(x) = setup() else { return; };`、`if let Ok(x) = result { assert_eq!(...) }`（无 else）。
- doctest：`ignore`（连编译都跳过）、`no_run`（编译不运行）、`ignore-<target>`（按目标跳过）。
- `#[should_panic]` 不得被用来「把失败变绿」：它表示契约要求 panic，不是跳过，见第三节。
- 定性：依赖网络/昂贵资源/平台缺口的 `#[ignore = "理由"]`、`ignore-<target>` 属正当防御，记 warning；**无理由者按 blocker（EXEC-003）**；**已知红灯被 ignore 且无可追踪标记**按 blocker（EXEC-005）。`#[ignore]` 只在输出里计为 ignored，不区分「环境依赖」与「已知失败」，理由与关联工单是必需信息。
- 静默的判据同父技能：有无解释、该逻辑在另一环境是否覆盖；`#[cfg]` 本身不是缺陷。

## 三、断言可达性与假绿（EXEC-004；ASRT-001/002）

- `#[should_panic]`：panic 之后的语句永不执行；裸属性下「任何原因的 panic」都通过。应带 `expected = "子串"`（`MetaNameValueStr` 或 `MetaListNameValueStr`，子串匹配，官方文档：Reference — should_panic）；返回类型必须是 `()`。
- `#[should_panic]` 测试中 panic 之前的断言若失败，失败本身也是 panic——裸属性会把它判绿；`expected` 可把这类错误原因的 panic 暴露出来。
- `debug_assert!`：仅在非优化构建默认启用，优化构建被编译掉（官方文档：std `debug_assert!`）。依赖它触发 panic/失败的测试在 `cargo test --release` 下失真；结论须标注所用 profile。
- `?` 与提前返回：`#[test] fn f() -> Result<(), E>` 只有返回 `Ok` 才通过，`?` 把 `Err` 变成失败（合法）；但 `let _ = result;` 吞掉错误、`if let Ok(x) = ... { ... }` 无 else 时 Err 路径**静默通过**，其后的断言也不可达。
- `catch_unwind`：断言只在捕获到 panic 时执行；须确认正常路径也有断言，且闭包满足 `UnwindSafe`。
- 空测试/弱断言（ASRT-001/002）：只有 `assert!(true)`、只 `println!`、只验证 `is_ok()` 不验证值，按父技能判。
- panic 策略：稳定 Cargo 下 tests/benchmarks **忽略** profile 的 `panic` 设置，libtest 以 unwind 构建才能在进程内捕获用例 panic（官方文档：Cargo Profiles — panic、rustc Tests）；若失败被误归因于 abort，先确认构建配置（含 `panic-abort-tests` 或自定义 harness），而非判测试缺陷。

## 四、doctest 执行链（EXEC-001/002/003/004；COV-001）

- 来源：lib 目标的文档注释；README 需显式引入（官方文档：rustdoc — Include items only when collecting doctests）：
  ```rust
  #[doc = include_str!("../README.md")]
  #[cfg(doctest)]
  pub struct ReadmeDoctests;
  ```
  `#[cfg(doctest)]` 只在收集 doctest 时生效。
- 生成条件：lib 目标 + `doctest = true`；`cargo test --doc` 单独跑。每个代码块用 rustc 即时编译为可执行文件并运行（官方文档：cargo-test — Documentation tests）；2024 edition 起兼容的 doctest 会先合并再运行，但仍各自独立进程（官方文档：rustdoc — standalone_crate）。
- 编译/运行目录：rustdoc 编译在 workspace 根，运行 cwd 是包根（官方文档：cargo-test — Working directory of tests）。路径断言失败先核对这一点。
- 属性语义（官方文档：rustdoc — Attributes）：`ignore` 完全不编译（伪代码/缺依赖）；`no_run` 只编译不运行；`compile_fail` 要求编译失败；`should_panic` 要求运行 panic；`ignore-<target>` 按目标跳过；`test_harness` 运行块内 `#[test]`；`#` 开头的行隐藏但参与编译。
- CI 风险：只用 nextest 会**完全漏掉** doctest；`doctest = false` 或 bin-only crate 无 doctest。报告须写明「doctest 是否被收集与运行」。
- COV-001：doctest 多为 happy-path 示例，不能因其存在就认定错误路径已覆盖。

## 五、假阳性陷阱（定性前必读）

- **平台 `#[cfg]` 配对替换**：`#[cfg(unix)]` / `#[cfg(windows)]` 各一条测试，总数守恒、名字互换，属同一测试的两种实现；读理由，另一平台已覆盖的记 warning（EXEC-006），不要按「用例消失」处理。
- **带理由的 `#[ignore = "..."]`**、`ignore-<target>`：可能是正当防御，不要只看形态。
- **`no_run`** 有时为文档示例避免副作用（官方文档给出的典型理由）；须确认关键断言没有只存在于 `no_run` 块中。
- **`#[should_panic(expected = "...")]`** 是合法契约测试，不是跳过，也不是「把错误当成功」。
- **profile 差异**：debug 构建整数溢出 panic、release 构建回绕（官方文档：The Book — Integer Overflow）；`debug_assert!` 同理。这不是测试缺陷，是**证据口径**问题——记「未能判定/需指定 profile」。
- **测试并行**：libtest 默认多线程（官方文档：cargo-test），环境变量、cwd、全局状态会竞态；edition 2024 中 `std::env::set_var`/`remove_var` 为 unsafe，多线程调用不健全（官方文档：Edition Guide）。先判断是测试缺陷（DET-003）还是运行环境问题；固定 `sleep` 等待按 TPERF-002。
- **cwd 假设**：单测/集成测试 cwd = 包根；doctest 编译在 workspace 根、运行在包根（官方文档：cargo-test）。相对路径失败常被误判为代码缺陷。
- **examples 默认只编译不运行**、`tests/common/mod.rs` 不是目标：都不构成「测试未注册」。
- **集成测试目标串行**：每个 `tests/*.rs` 是独立可执行文件且 Cargo 串行运行（官方文档：Cargo Targets）；套件变慢属结构成本，TPERF-001 仅在单用例测量层面作参考，不能据此判缺陷。

## 六、本语言特有豁免

- 基准：`benches/`、criterion、nightly `#[bench]` 豁免本技能**全部**规则，仅保留 EXEC-001/EXEC-002——必须真的被构建并注册：`cargo bench --no-run`、`cargo test --benches`（官方文档：cargo-test — --benches）。`#[bench]` 仅 nightly；stable 常用 criterion 且通常 `harness = false`，其「注册」由 bench 目标的构建/运行证明。
- 属性测试与 fuzz（proptest/quickcheck/cargo-fuzz）不在本技能范围；如需覆盖，显式标注「未覆盖」而非记通过。
- 可选工具：`cargo llvm-cov`、`cargo tarpaulin`、`cargo nextest`、`miri`、`loom`、`rstest`、`serial_test`、`trybuild` 均为**可选**，不是 Cargo 内置能力；引用其输出时须注明工具与版本。
- 私有可见性：`#[cfg(test)] mod tests` 访问同模块私有项是 Rust 既有惯例，不按 ASRT-006 后门处理；但**断言内部缓存/实现细节**仍违反 ASRT-006，仅为可见性放宽的 `#[cfg(test)] pub(crate)` 属分期整改。
- `panic = "abort"` 等非 unwind 构建：测试前提不成立时记「未能判定（构建配置不支持）」，不判测试缺陷。
- Tokio 测试可用 `start_paused = true` 控制时间（官方文档：tokio `#[tokio::test]` 属性，按版本核对）；DET-002 在专门验证时间语义的测试中可带注释例外。
