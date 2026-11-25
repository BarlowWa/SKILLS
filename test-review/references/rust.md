# Rust 测试审查参考（test-review / references）

> 由 test-review 在测试文件为 Rust 时加载。通用判据见 `test-review/SKILL.md`；本文提供 **Cargo / libtest / rustdoc 的执行证据获取方式**、跳过与断言不可达的形态词表，以及 Rust 项目中最容易造成误判的陷阱。工具行为均引自 Cargo、rustc、rustdoc 官方文档或 libtest 公开源码，**不代表任何一次具体运行的结果**；无法取得构建/运行证据时记「未能判定（缺构建/运行证据）」。

## 一、执行证据获取（EXEC-001 / EXEC-002 / EXEC-006）

### 1.1 构建配置与目标清单（EXEC-001；ORG-001/002/003）

- 机器可读的目标清单：在包/工作区根执行 `cargo metadata --format-version 1`，读 `packages[].targets[]` 的 `kind`（`lib`/`bin`/`test`/`bench`/`example`/`custom-build`）、`src_path`、`test`、`doctest`、`required-features`（官方文档：cargo-metadata）。
- 测试源归属（ORG-001/002）：单元测试写在源文件的 `#[cfg(test)] mod tests`；集成测试放 `tests/`，每个顶层 `.rs` 独立编译为一个 crate（官方文档：Cargo Targets — Integration tests）。`tests/common/mod.rs` 是文档指定的共享辅助模块，**不是**测试目标，不得报「未进构建」。
- 双向差集：`targets[]` 中 `kind = ["test"]` 的 `src_path` ↔ 仓库 `tests/**` 测试源；**不要**用文本搜 `tests/` 或 `mod` 就下结论。trybuild / compiletest 的夹具（`tests/ui/**`、`tests/compile-fail/**` 等）是测试**输入**，不是测试目标，差集必须排除；否则每个 fixture 都会被误报为「未进构建」。
- `autotests = false` 关闭自动发现，未在 `[[test]]` 声明的 `tests/` 文件**不会被编译**（官方文档：Cargo Targets — Target auto-discovery）。这类文件在源码里完全正常，只能反查。
- `[[test]] test = false`：与 `autotests = false` 同类——**目标存在但不默认构建**。`test = false` 的目标不会被裸 `cargo test` 构建/运行，`--tests` 也按其声明跳过，只有显式 `cargo test --test <name>` 才进入（官方文档：cargo-test — Target Selection）；`test` 字段在 `cargo metadata` 的 `targets[]` 里可见，须同时核对 `test` 字段与 `kind`，不要只看 `kind = ["test"]` 就判「会跑」。`doctest = false` / `bench = false` / `test = false` 分别控制 doctest / bench / test 目标的默认构建。注意 **`doc = false` 不是 doctest 开关**：它只影响 `cargo doc`，与 doctest 无关；实测（cargo 1.99.1）`[lib] doc = false` 时 `cargo test --doc` 仍会运行该 crate 的 doctest，`cargo metadata` 中的 `doctest` 字段也仍为 `true`——要关掉 doctest 必须用 `doctest = false`。
- `required-features` 未启用的目标会被跳过（官方文档：Cargo Targets — required-features）：测试文件存在但 CI 未开对应 feature 时等于没跑，按 EXEC-001/EXEC-003 记录。
- 测试层级（ORG-003）：集成测试只能用库的 public API；声明为 unit 却依赖真实网络/子进程/全局状态的，按层级失当处理。

### 1.2 注册与执行范围（EXEC-002）

- Rust 没有 CTest 式单独注册步骤：Cargo 用 `--test` 编译测试目标，libtest 自动收集 `#[test]`（官方文档：cargo-test）。注册证据 = 目标清单 + 运行时 `--list`，不是 Cargo.toml 字面文本。
- `cargo test` 默认目标：lib 单测、bins 单测、集成测试、lib 的 doctest；examples 仅编译不运行（官方文档：cargo-test — Target Selection）。
- 工作区：workspace 根直接 `cargo test` 只跑 `default-members`；未设置时非 virtual workspace 用 root package，virtual workspace 用全部成员（官方文档：Cargo Workspaces）。**必须记录命令与 cwd**。CI 建议 `cargo test --workspace --all-features`（**两者都要**：`--workspace` 避免成员测试静默缺席，`--all-features` 让 feature 门控用例可见，见 §1.3）；若存在不可链接的夹具/辅助 crate（符号由父包的测试目标定义），`--workspace` 会在链接阶段失败——实测某样本以 LNK2019 失败、stdout 0 条——此时按项目 CI 的 `--exclude` 清单执行并记录，不得静默缩小范围。`--all-features` 只切换 feature，**不能**解除链接失败，不要把它当作修复手段。
- doctest 只对 **library 目标**生成且 `doctest = true`（默认）；`doctest = false` 关闭，bin-only crate 没有 doctest（`cargo test --doc` 报 `no library targets found`）。**proc-macro crate 也是 library 目标**（`[lib] proc-macro = true`，`cargo metadata` 的 `kind` 为 `["proc-macro"]` 且 `doctest: true`），其文档示例会被收集并运行——不要因 `kind` 不是 `lib` 就判定无 doctest（官方文档：Cargo Targets — doctest / proc-macro）。

### 1.3 注册清单与执行状态（EXEC-002 / EXEC-003）

- 清单：`cargo test --workspace --all-features -- --list`（Cargo 对每个测试目标分别调用 libtest）。**必须带 `--all-features`**：不带时 `#[cfg(feature = ...)]` 门控的用例**完全不出现**在 `--list` 里（实测 cargo 1.99.1：workspace 样本不带时为 1 条、带 `--all-features` 后为 2 条），EXEC-006 对账会把「未启用」误判为「不存在」。`--all-features` 与上条的 `--exclude` **不矛盾**：前者用于让 feature 门控用例可见（只切 feature），后者用于绕开不可链接的夹具 crate（链接失败不是 feature 问题）。
- **`--message-format=json` 不能与 `-- --list` 混用解析**：`--message-format=json` 必须放在 `--` **之前**（否则被当成 libtest 参数），且**只覆盖 Cargo 自身事件**（`compiler-message` / `compiler-artifact` / `build-finished` 等 JSON 行）；`-- --list` 的用例清单仍是**纯文本**（`用例名: test`），Cargo 的 `Finished ...` / `Running unittests ...` 也以纯文本混在同一 stdout。实测 `cargo test --message-format=json -- --list` 的输出是 JSON 行与非 JSON 行混杂，**按行 `json.loads` 会崩**。
  - 推荐做法：先 `cargo test --no-run --message-format=json`，逐行筛出以 `{` 开头的 JSON 行解析，取每个测试目标 `compiler-artifact.executable` 的路径；再**逐个可执行文件**执行 `--list` 得到各自用例清单——两者分两步，不对同一份 stdout 混合解析。
- **list 中出现 ≠ 会执行**：libtest 默认 `RunIgnored::No` 只保留 `ignore` 标记、不移除用例（源码：libtest `filter_tests` 中 `RunIgnored::No => {}`；`list_tests_console` 遍历过滤结果并累计 `desc.ignore`）。**`--list` 输出本身不标注 ignored**（`ui: test ... ignored, requires nightly` 这类标记只在执行时出现）；忽略状态须另查源码属性、运行输出的 `ignored` 计数或 `--ignored --list` 子集（见下条）。
- `#[ignore]` 用例仍被编译；`--ignored` 只跑忽略项，`--include-ignored` 两者都跑（官方文档：rustc Tests / Reference）。**`--ignored` 是 libtest 参数，必须放在 `--` 之后**：正确形式是 `cargo test -- --ignored --list`，写成 `cargo test --ignored --list` 会直接报错（实测 cargo 1.99.1：`error: unexpected argument '--ignored' found`，退出码 1）。**`--ignored --list` 是过滤后的子集**：它会**只列出被忽略的用例**（实测 cargo 1.99.1：全量 `--list` 为 `ignored_a` / `ignored_b` / `normal_a` 三条，加 `--ignored` 后只剩 `ignored_a` / `ignored_b` 两条），可作为「哪些用例被忽略」的机器可读集合证据；但它**不给出每条的忽略理由**——理由须回源码的 `#[ignore = "..."]` 属性或运行输出核对。这与上条「`--list` 输出本身不标注 ignored」不矛盾：`--list` 是全量、不标状态；`--ignored --list` 是过滤后只留 ignored 的子集。
- `harness = false` 的目标自行提供 `main`，不走 libtest（官方文档：Cargo Targets — harness）；`--list` 不会枚举其用例，且 `cargo test -- --list` 会把 `--list` **原样传给自定义 `main`**——自定义 harness 可能不识别该参数而**真的执行用例**（产生副作用/失败），不能把这次运行当作「只列清单」。必须单独核对其收集/执行逻辑。
- 可选证据：`cargo test --no-run --message-format=json` 可确认测试目标确实被编译（只编译不运行）。
- nextest：`cargo nextest run` **不运行 doctest**（官方文档/issue；按项目 nextest 版本核对）；CI 只用 nextest 时须另跑 `cargo test --doc`。

### 1.4 计数与对账（EXEC-006）

- 静态搜索 `#[test]` 会漏掉 `#[tokio::test]`、`#[rstest]`、`#[test_case]` 等过程宏生成的用例；**以 `--list` 的运行时清单为准**。
- doctest 由 rustdoc 驱动的独立 harness 运行，通常在输出中单列（`Doc-tests <crate>`）；计数时单独核对，不要与 libtest 目标混算。以 `cargo test --doc` 的运行输出为准；`--list` 与该组合的实际行为按本机工具链版本核对。
- 清单不标注 ignored，**不是**执行集合；对账前先按忽略状态分组（查源码属性、运行输出的 `ignored` 计数或 `--ignored --list` 子集）。
- 按名字双向差集（测试源码 ↔ 目标清单 ↔ `--list`），归一化模块路径与多字节/转义字符；不要用「声明总数 − 执行总数」判红。**目标名 = 目录 stem**（Cargo Targets — Integration tests）：`tests/x.rs` → `x`，`tests/x/main.rs` → `x`（取**目录名**，不是 `main`）。据此直接与 `tests/**` 对照。

## 二、跳过与条件编译形态词表（EXEC-003 / EXEC-005）

- `#[ignore]`、`#[ignore = "reason"]`、`#[cfg_attr(cond, ignore)]`。
- `#[cfg(feature = "...")]`、`#[cfg(target_os = "...")]`、`#[cfg(not(...))]` 包裹整个测试函数或 `mod tests`：未开 feature/平台不符时**静默不编译**，既不进目标也不进 `--list`；先看 `cfg` 是否成对替换。
- `[[test]] required-features` 未启用：整个集成测试目标被跳过（同 EXEC-001）。
- `[[test]] test = false`：目标存在但不默认构建，裸 `cargo test` 与 `--tests` 都不跑，只有 `cargo test --test <name>` 才执行——「目标在 metadata 里」不等于「会跑」（同 EXEC-001/EXEC-002）。
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
- `debug_assert!`：**默认 `cargo test`（test profile 继承 dev）下生效**——实测（cargo 1.99.1，probe 用 `black_box` 防止常量折叠）其触发 panic；`cargo test --release`（optimized test profile）或显式设 `[profile.test] debug-assertions = false` 后失效。不要写成「默认跑测试不生效」：默认 profile 下它确实生效，只有切到 release 或显式关闭才被编译掉（官方文档：std `debug_assert!`、Cargo Profiles — debug-assertions）。依赖它触发 panic/失败的测试，**结论须标注所用 profile**（`cargo test` 还是 `cargo test --release`）；未标注 profile 时记「未能判定（缺 profile）」。测试辅助代码中的 `debug_assert!` 属内部一致性检查，不作为被测契约的断言；仅当它是该用例唯一的验证手段时才按陷阱处理。
- `?` 与提前返回：`#[test] fn f() -> Result<(), E>` 只有返回 `Ok` 才通过，`?` 把 `Err` 变成失败（合法）；但 `let _ = result;` 吞掉错误、`if let Ok(x) = ... { ... }` 无 else 时 Err 路径**静默通过**，其后的断言也不可达。
- `catch_unwind`：断言只在捕获到 panic 时执行；须确认正常路径也有断言，且闭包满足 `UnwindSafe`。
- 空测试/弱断言（ASRT-001/002）：只有 `assert!(true)`、只 `println!`、只验证 `is_ok()` 不验证值，按父技能判。
- 编译期约束型测试（如 `fn assert_send<T: Send>() {}` 后在用例中实例化）的证据是**编译成功**，不是运行时断言，不按 ASRT-001 弱断言判；trybuild 的 compile-fail 用例同理，证据是预期编译失败。
- 浮点相等断言：`.5`、`0.25` 等二进制可精确表示的值直接相等是安全的；整数值仅在尾数范围内精确（f64 `|n| ≤ 2^53`、f32 `|n| ≤ 2^24`），超出后 `2^53 + 1` 与 `2^53` 已无法区分；非精确运算或超范围的值须用容差（父技能 ASRT-003 例外）。
- panic 策略：稳定 Cargo 下 tests/benchmarks **忽略** profile 的 `panic` 设置，libtest 以 unwind 构建才能在进程内捕获用例 panic（官方文档：Cargo Profiles — panic、rustc Tests）；若失败被误归因于 abort，先确认构建配置（含 `panic-abort-tests` 或自定义 harness），而非判测试缺陷。

## 四、doctest 执行链（EXEC-001/002/003/004；COV-001）

- 来源：lib 目标的文档注释；README 需显式引入（官方文档：rustdoc — Include items only when collecting doctests）：
  ```rust
  #[doc = include_str!("../README.md")]
  #[cfg(doctest)]
  pub struct ReadmeDoctests;
  ```
  `#[cfg(doctest)]` 只在收集 doctest 时生效。
- 生成条件：library 目标（含 proc-macro）+ `doctest = true`；`cargo test --doc` 单独跑。每个代码块用 rustc 即时编译为可执行文件并运行（官方文档：cargo-test — Documentation tests）；2024 edition 起兼容的 doctest 会先合并再运行，但仍各自独立进程（官方文档：rustdoc — standalone_crate）。**合并后 `--list` 的计数形态可能改变**（合并前后「一个代码块 = 一条用例」的对应关系不再一一对齐）；对 2024 edition crate 做 EXEC-006 对账时，须按**所用工具链版本实测** `--list` 计数，无法确认时标「未能判定」，不要用旧版计数口径直接判差异。
- 编译/运行目录：rustdoc 编译在 workspace 根，运行 cwd 是包根（官方文档：cargo-test — Working directory of tests）。路径断言失败先核对这一点。
- 属性语义（官方文档：rustdoc — Attributes）：`ignore` 完全不编译（伪代码/缺依赖）；`no_run` 只编译不运行；`compile_fail` 要求编译失败；`should_panic` 要求运行 panic；`ignore-<target>` 按目标跳过；`test_harness` 运行块内 `#[test]`；`#` 开头的行隐藏但参与编译。
- CI 风险：只用 nextest 会**完全漏掉** doctest；`doctest = false` 或 bin-only crate 无 doctest。报告须写明「doctest 是否被收集与运行」。
- 收集范围：私有项（`pub(crate)` / 私有 `mod` 内）的 doctest **会被收集**——名字以模块路径出现在 `--list` 里；`#[cfg(test)] mod tests` 内的 doctest **不会被收集**（该模块只在 test 构建可见）。前者是文档契约的一部分，后者不是测试目标，差集时须分别处理。
- COV-001：doctest 多为 happy-path 示例，不能因其存在就认定错误路径已覆盖。

## 五、假阳性陷阱（定性前必读）

- **平台 `#[cfg]` 配对替换**：`#[cfg(unix)]` / `#[cfg(windows)]` 各一条测试，总数守恒、名字互换，属同一测试的两种实现；读理由，另一平台已覆盖的记 warning（EXEC-006），不要按「用例消失」处理。
- **带理由的 `#[ignore = "..."]`**、`ignore-<target>`：可能是正当防御，不要只看形态。
- **`no_run`** 有时为文档示例避免副作用（官方文档给出的典型理由）；须确认关键断言没有只存在于 `no_run` 块中。
- **`#[should_panic(expected = "...")]`** 是合法契约测试，不是跳过，也不是「把错误当成功」。
- **profile 差异**：默认 `cargo test`（test profile 继承 dev）下整数溢出 panic、`debug_assert!` 生效——实测 `debug_assert!(false)` 触发 panic、`250u8 + 10u8` 触发 overflow panic；`cargo test --release` 或显式设 `[profile.test] overflow-checks = false` / `debug-assertions = false` 后才改为回绕 / 编译掉（官方文档：The Book — Integer Overflow、Cargo Profiles）。这不是测试缺陷，是**证据口径**问题——记「未能判定/需指定 profile」。
- **测试并行**：libtest 默认多线程（官方文档：cargo-test），环境变量、cwd、全局状态会竞态；edition 2024 中 `std::env::set_var`/`remove_var` 为 unsafe，多线程调用不健全（官方文档：Edition Guide）。先判断是测试缺陷（DET-003）还是运行环境问题；固定 `sleep` 等待按 TPERF-002。
- **cwd 假设**：单测/集成测试 cwd = 包根；doctest 编译在 workspace 根、运行在包根（官方文档：cargo-test）。相对路径失败常被误判为代码缺陷。
- **examples 默认只编译不运行**、`tests/common/mod.rs` 不是目标：都不构成「测试未注册」。
- **`harness = false` + `-- --list`**：`--list` 被原样传给自定义 `main`，该 harness 可能不识别而**真的执行用例**（产生副作用或失败）——这时的输出不是清单，不能据此判「用例集合」或「用例未注册」；须单独核对其收集逻辑。
- **集成测试目标串行**：每个 `tests/*.rs` 是独立可执行文件且 Cargo 串行运行（官方文档：Cargo Targets）；套件变慢属结构成本，TPERF-001 仅在单用例测量层面作参考，不能据此判缺陷。

## 六、本语言特有豁免

- 基准：`benches/`、criterion、nightly `#[bench]` 豁免本技能的**形态类与覆盖类判据**（ORG/MOCK/DET/ASRT/COV/THR/TPERF），仅保留 EXEC-001/EXEC-002——必须真的被构建并注册：`cargo bench --no-run`、`cargo test --benches`（官方文档：cargo-test — --benches）。`#[bench]` 仅 nightly；stable 常用 criterion 且通常 `harness = false`，其「注册」由 bench 目标的构建/运行证明。
- 属性测试与 fuzz（proptest/quickcheck/cargo-fuzz）不在本技能范围；如需覆盖，显式标注「未覆盖」而非记通过。
- 可选工具：`cargo llvm-cov`、`cargo tarpaulin`、`cargo nextest`、`miri`、`loom`、`rstest`、`serial_test`、`trybuild` 均为**可选**，不是 Cargo 内置能力；引用其输出时须注明工具与版本。
- 私有可见性：`#[cfg(test)] mod tests` 访问同模块私有项是 Rust 既有惯例，不按 ASRT-006 后门处理；但**断言内部缓存/实现细节**仍违反 ASRT-006，仅为可见性放宽的 `#[cfg(test)] pub(crate)` 属分期整改。
- `panic = "abort"` 等非 unwind 构建：测试前提不成立时记「未能判定（构建配置不支持）」，不判测试缺陷。
- Tokio 测试可用 `start_paused = true` 控制时间（官方文档：tokio `#[tokio::test]` 属性，**按所用 tokio 版本核对**——`start_paused` 的存在与语义随版本变化，无法确认版本时标「未能判定」）；DET-002 在专门验证时间语义的测试中可带注释例外。
