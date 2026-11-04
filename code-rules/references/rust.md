# Rust 编码规范（code-rules / references）

> 本文件由 code-rules 按扩展名路由加载。工作流程、严重级别、审查输出格式、豁免与「冲突取更严者」见 `code-rules/SKILL.md`；与 G-xxx 同义时以本文 ID 为准。
> 本文 ID 为 Rust 专属命名空间，不得改名；跨技能引用时写全 ID（如 arch-review 引用 `RUST-UNSAFE-*` 划分 unsafe 边界）。

## 适用

- 扩展名：`.rs`（含 `build.rs`，其构建期权限见『本语言专属豁免』）。
- 构建/工具链：cargo、rustc、clippy、rustfmt。
- 版本：edition 与 MSRV 以 `Cargo.toml` 的 `edition` / `rust-version` 为唯一准绳；条目内标注 edition 2024 的行为差异，按该 crate 的实际 edition 判定。
- 不在本文件范围：架构级问题（模块依赖、分层、循环依赖、API/ABI 兼容）归 `arch-review`；测试/基准的设计与质量归 `test-author` / `test-review`；SQL 归 `db-rules`。

## OWN：所有权、借用与析构

> 借用能表达的一律不复制；析构是资源安全与 runtime 稳定性的最后一道闸。

- **RUST-OWN-001**（warning）：参数优先借用——字符串、切片、路径分别用 `&str` / `&[T]` / `&Path`，禁止 `&String` / `&Vec<T>` / `&PathBuf`。
  > 为什么：具体容器类型把调用方绑死到一种存储，并多一层间接；接受 `&str` 才能同时接受 `String`、字面量与切片。
  > 反例：`fn load(p: &PathBuf)`、`fn parse(s: &String)`。
  > 例外：ABI 视图转换 API（典型的重解释查询器 `fn as_string(&self) -> &String`、`fn as_vec(&self) -> &Vec<T>`）必须返回具体容器类型以保持视图一致。本条约束的是**参数侧**借用；返回值侧由 RUST-API-004 的命名与 `RUST-TYPE` 组约束。
  > 检测：Clippy `ptr_arg`（默认 warn，直接生效）、`needless_pass_by_value`（pedantic，需启用）。

- **RUST-OWN-002**（warning）：禁止非必要的 `clone` / `to_owned` / `format!`。
  > 为什么：静默复制会掩盖所有权意图，并在热路径上按调用次数放大分配；跨所有权边界才复制，必要时用 `Cow`。
  > 反例：`let v = v.clone();` 之后只读；`format!("{}", s)` 代替 `s.to_string()`。
  > 检测：Clippy `clone_on_copy`（默认 warn，直接生效）；`redundant_clone` 属 nursery 组，官方已知存在漏报，只作人工判据，不依赖其门禁。

- **RUST-OWN-003**（blocker）：`Drop` 不得 panic，不得阻塞或等待；资源释放交给 RAII；`mem::forget` / `Box::leak` 必须有意为之并注释理由。
  > 为什么：Drop 中 panic 在 unwinding 期间会中止进程（double panic abort，按本机工具链版本核对）；阻塞型 Drop 会拖死 runtime；forget/leak 则永久泄漏。
  > 例外：为阻止 panic 穿越 non-unwinding FFI 边界而**有意**在 Drop 中触发 abort（double panic）是安全机制，不算本条违规，但必须在紧邻处注明理由与边界契约。
  > 对应：G-RELEASE、API Guidelines C-DTOR-FAIL / C-DTOR-BLOCK。

## UNSAFE：不安全代码与 FFI

> unsafe 是承诺，不是逃生舱：每个块都必须能被审阅者独立验证其安全前提。

- **RUST-UNSAFE-001**（blocker）：`pub unsafe fn` / `pub unsafe trait` / `unsafe impl` 必须有 `# Safety`（或 `// SAFETY:`）段落，逐条说明调用方/实现方必须维持的前提；`unsafe` 块中涉及裸指针解引用或算术、`transmute`、跨 FFI 构造切片/引用、或依赖非局部不变量的，必须有 `// SAFETY:` 说明依据。
  > 为什么：无说明的 unsafe 无法审阅，前提变化后仍会被误认为「当时已证明」；但仅直接调用 `unsafe extern` 声明、且契约已由类型级 `# Invariants` 或 FFI 文档保证的块，逐块重复论证收益很低。
  > 判定：直接调用 `unsafe extern` 且能找到类型/文档级契约依据的块，缺块级注释记 **warning**；本条第 1 句列举的四类高风险块（裸指针解引用或算术、`transmute`、跨 FFI 构造切片/引用、依赖非局部不变量）缺说明记 **blocker**；所有缺失 `# Safety` 的 `pub unsafe fn` / `pub unsafe trait` / `unsafe impl` 亦记 **blocker**。
  > 检测：Clippy `undocumented_unsafe_blocks`（restriction，需启用）；`missing_safety_doc`（默认 warn）只覆盖 `unsafe fn` 与 `unsafe trait`，**不覆盖 `unsafe impl`**——后者只能人工核对。项目若显式 `allow` 这些 lint，须在仓库内说明理由，否则按本条判定。

- **RUST-UNSAFE-002**（blocker）：禁止 `mem::transmute`；用 `from_ne_bytes` / `try_into` / 显式字节解析或 `zerocopy` 等替代。
  > 为什么：transmute 绕过全部类型检查，布局、大小、对齐不匹配即 UB。
  > 例外：确需时 SAFETY 必须证明源/目标布局一致、大小相等、目标值合法；`const_assert!` / `static_assert` 的机械布局断言可作为该证明的**引用依据**，但 SAFETY 注释本身不可省略。proc-macro 通过 `quote!` 生成的 transmute 同样受本条约束。

- **RUST-UNSAFE-003**（blocker）：FFI 边界必须显式管控——`extern "C"` 不得 unwind；跨 FFI 结构体用 `#[repr(C)]`；不得跨 dylib 暴露 Rust 私有布局、泛型或 vtable。
  > 为什么：Rust panic 到达 non-unwinding ABI 边界会被转为 abort（Drop 是否运行未指定）；native 异常（如 C++）越入该边界才是 UB。Rust 无稳定 ABI，私有类型跨动态库边界布局无保证。
  > 做法：需要跨语言传播用 `extern "C-unwind"` 或 `catch_unwind`；边界类型只暴露 C ABI 类型。
  > **FFI 入口一致性**：项目若已定义统一的 unwind 防护机制（如所有导出 shim 走同一个 guard 函数），所有 C ABI 导出 shim 必须走同一机制。单个 shim 靠 panic→abort 形式上满足「不 unwind」，但会绕过该机制、丢失防护标签，按 blocker 报。
  > **edition 2024**：`extern` 块必须写 `unsafe extern`（2021 不要求）；缺失时 2024 crate 直接编译失败，按 blocker 报。
  > 依据：官方文档：Rust Reference「Unwinding」；Rustonomicon「FFI」；Edition Guide「unsafe extern」。

- **RUST-UNSAFE-004**（blocker）：禁止 `static mut`；用 `OnceLock` / `LazyLock` / `Atomic*` / `Mutex`。
  > 为什么：对 `static mut` 取引用本身即 UB（即使从不解引用）；edition 2024 下 `static_mut_refs` 默认 deny。
  > 依据：官方文档：Edition Guide「static_mut_refs」。

- **RUST-UNSAFE-005**（blocker）：`unsafe impl Send` / `Sync` 必须附 SAFETY，逐条说明内部字段为何满足 trait 合约。
  > 为什么：错误的 Send/Sync 会引入数据竞争，而编译器此后不再拦截；必须证明所有字段的跨线程访问方式。
  > 与 RUST-UNSAFE-001 重叠时按本条报一次（001 负责其他 `unsafe impl` 与 unsafe trait）。

- **RUST-UNSAFE-006**（warning）：unsafe 必须隔离在专用模块，对外只暴露安全 API（内部不变量在边界处校验并文档化）。
  > 为什么：把 unsafe 集中到少数模块，才能把审计面从整个 crate 缩到一个文件。
  > 配置：可不用 unsafe 的 crate 用 `#![forbid(unsafe_code)]`；unsafe fn 内开 `#![deny(unsafe_op_in_unsafe_fn)]`，强制逐个操作标注。
  > 与 RUST-BUILD-003 重叠时：结构性隔离报本条，缺少 crate 级 lint 配置报 BUILD-003。

## ERR：错误处理

> 错误是 API 契约的一部分；panic 只用于程序缺陷，不用于可恢复失败。

- **RUST-ERR-001**（blocker）：生产路径禁止 `unwrap` / `expect`；`expect` 仅用于可证明不变量且必须带具体消息。
  > 为什么：panic 在生产等于请求级 DoS 或进程退出，且调用方无法捕获处理。
  > 反例：`serde_json::from_str(&body).unwrap()`、`lock().expect("mutex")`。
  > 例外：proc-macro 中对解析器已保证的非空结构、或其他紧邻处已校验不变量并注释说明的 `unwrap`，记 warning；无说明仍为 blocker。
  > 检测：Clippy `unwrap_used` / `expect_used`（restriction，需启用）；两者存在形状漏报（如宏体内部定义的 `.unwrap()`），不能视为完备门禁。

- **RUST-ERR-002**（blocker）：禁止丢弃 `Result` / `Option` 的错误——`let _ =`、`.ok()`、`mem::drop` 不得用于消除 `must_use` 警告。
  > 为什么：错误被静默吞掉后，调用方既得不到失败信号，也无从追溯；G-SWALLOW。
  > 做法：传播、显式处理，或注释「有意忽略及理由」；注释缺失即违规。

- **RUST-ERR-003**（blocker）：库的公开错误类型必须实现 `core::error::Error + Send + Sync`（trait object 再加 `'static`）；`std` crate 直接适用，`no_std` crate 用 `core::error::Error`。禁止用 `Box<dyn Error>` / `anyhow::Error` 作为库的公开错误类型；禁止 `()` 作错误类型。
  > 为什么：否则调用方无法组合、下转型或追溯根因，也无法把它包装进 `io::Error`（`std` crate 的典型场景）。
  > 依据：API Guidelines C-GOOD-ERR；`core::error::Error` 自 Rust 1.81 起稳定。

- **RUST-ERR-004**（warning）：可恢复错误用 `Result`，不用 `panic!` / `assert!`；`Option` 表达「无值」，不表达「失败」。
  > 为什么：panic 不可被调用方处理；Option 丢失失败原因，调用方无法区分「不存在」与「出错了」。

- **RUST-ERR-005**（warning）：公开错误枚举加 `#[non_exhaustive]`；错误链必须保留 `source`。
  > 为什么：下游穷尽 `match` 后新增变体即破坏兼容；丢 `source` 等于丢根因。
  > 与 RUST-API-002 的 `#[non_exhaustive]` 重叠时按本条报一次。

- **RUST-ERR-006**（blocker）：外部输入或尺寸计算的算术必须用 `checked_*` / `saturating_*` / `wrapping_*` 或显式校验。
  > 为什么：debug 构建溢出会 panic，release 构建静默回绕；不得把 release 的正确性寄托在 debug 检查上，回绕后的尺寸可绕过校验。
  > 反例：`let n = user_len * elem_size;` 之后直接用于分配或索引。
  > 依据：官方文档：The Rust Book「Data Types」。

- **RUST-ERR-007**（warning）：错误转换优先 `From` / `thiserror`，避免手写样板，并保留 `source`。
  > 为什么：手写转换易漏掉 source 链；derive 生成的 `source` 才能被上层统一追溯。

## TYPE：类型与边界安全

> 拒绝隐式截断与未校验索引——Rust 的安全保证止于 panic，而 panic 对服务即不可用。

- **RUST-TYPE-001**（blocker）：整数窄化与符号转换禁止 `as`，用 `TryFrom` / `try_into()` 并处理错误。
  > 为什么：`as` 静默截断或回绕，越界值会变成看似合法的小数/负数。
  > 反例：`let n = u64_val as u32;`、`let i = u8_val as i8;`。
  > 例外：FFI 或位运算中，若转换范围可由类型宽度、常量约束或紧邻校验静态证明，允许 `as` 并在紧邻处写明证明；无证明仍为 blocker。
  > 检测：Clippy `cast_possible_truncation`、`cast_sign_loss`、`cast_possible_wrap`（均属 pedantic，需启用）。

- **RUST-TYPE-002**（warning）：同宽无损转换用 `From` / `into`。
  > 为什么：用 `as` 会掩盖意图，且重构改变类型时不会报错；`From` 会在类型不再兼容时编译失败。

- **RUST-TYPE-003**（blocker）：不可信或无法证明在界内的索引用 `get` / `get_mut`；`v[i]` 仅当可证明界内时使用。
  > 为什么：越界会 panic，对不可信输入即 DoS；`get` 把越界转成可处理的 `Option`。
  > 反例：`v[req.index]`、`data[offset as usize]`。
  > 依据：官方文档：`std::ops::Index`「Panics」。

- **RUST-TYPE-004**（blocker）：字符串/切片边界必须校验——`&s[..n]`、`split_at` 前用 `get` 或 `is_char_boundary` 确认 UTF-8 char boundary；`str::from_utf8` 必须处理错误；不得对不可信字节 `unwrap`。
  > 为什么：非 char boundary 的切片与非法 UTF-8 都会直接 panic，外部输入可稳定触发。
  > 边界证明：`Utf8Error::valid_up_to()` 给出的偏移、或 `is_char_boundary(n) == true` 的检查结果，可作为切片合法性的证明，不必重复校验。
  > 依据：官方文档：`str::split_at`「Panics」；`str::from_utf8` 返回 `Result`。

## API：公开 API 设计

> 公开 API 的每次变更都要按 SemVer 评估；本类规则用于减少未来的破坏性变更。

- **RUST-API-001**（warning）：公开类型必须实现 `Debug`；公开结构体字段私有，经构造函数或 Builder 构造。
  > 为什么：字段公开后任何布局调整都是破坏性变更；无法 Debug 的类型难以排障。
  > 依据：API Guidelines C-DEBUG / C-STRUCT-PRIVATE。

- **RUST-API-002**（warning）：可能扩展的公开 enum/struct 加 `#[non_exhaustive]`；不期望下游实现的 trait 用 sealed（私有 supertrait 或私有模块）。
  > 为什么：下游穷尽匹配或自行实现后，类型无法演进；`#[non_exhaustive]` 在定义 crate 内无效果。
  > 依据：API Guidelines C-SEALED；官方文档：Reference「non_exhaustive」。

- **RUST-API-003**（warning）：有领域含义的 `bool` / `Option` 位置参数改 newtype 或 enum。
  > 为什么：`connect(url, true, false)` 在调用点不可读，参数顺序错误编译器无法发现。
  > 依据：API Guidelines C-NEWTYPE / C-CUSTOM-TYPE。

- **RUST-API-004**（warning）：转换命名遵守 `as_`（借用、零成本）/ `to_`（复制）/ `into_`（消耗）；getter 不用 `get_` 前缀；标识符遵守 C-CASE。
  > 为什么：名字必须反映成本与所有权，否则调用方会误判是否发生复制。
  > 依据：API Guidelines C-CONV / C-GETTER / C-CASE。

## DOC：文档

> 文档是公开契约的一部分；doctest 是防止示例腐烂的机制。

- **RUST-DOC-001**（blocker）：公开项必须有 `///` 文档；可能失败写 `# Errors`，可能 panic 写 `# Panics`，`unsafe fn` 写 `# Safety`。
  > 为什么：调用方无法预知失败、panic 与安全前提，只能读实现。
  > 检测：`missing_safety_doc`（默认 warn，直接生效）；`missing_errors_doc` / `missing_panics_doc` 属 pedantic，需启用。
  > 依据：API Guidelines C-FAILURE。
  > 去重：unsafe 相关的 `# Safety` 缺失按 RUST-UNSAFE-001 报一次。

- **RUST-DOC-002**（warning）：文档示例用 `?` 不用 `unwrap`；示例应能作为 doctest 编译运行；`no_run` 必须写明理由。
  > 为什么：不参与编译的示例会随 API 漂移腐烂；`unwrap` 会给复制示例的用户传递错误习惯。
  > 依据：API Guidelines C-QUESTION-MARK；官方文档：Cargo doctests。

- **RUST-DOC-003**（warning）：crate 级 `//!` 写概述与可运行示例；公开 crate 可开 `#![deny(missing_docs)]`。
  > 为什么：入口文档决定使用者能否在几分钟内跑通；`missing_docs` 让新增公开项必须补文档。
  > 依据：API Guidelines C-CRATE-DOC。

## SEC：安全

> 外部输入在进入系统边界时必须被当作敌意数据。

- **RUST-SEC-001**（blocker）：外部命令用 `Command::new(prog).args([...])`，参数不经 shell；禁止把外部字符串拼进 `sh -c` / `cmd /C`；Windows 下 `cmd.exe` / `.bat` 对不可信输入有特殊解析规则，须额外校验。
  > 为什么：命令行注入等价于任意代码执行；`arg`/`args` 原样传参，不做引号、变量替换或通配符展开。
  > 反例：`Command::new("sh").arg("-c").arg(format!("ls {}", user_dir))`。
  > 依据：G-CMDINJ；官方文档：`std::process::Command::arg`。

- **RUST-SEC-002**（blocker）：用户可控路径拼接必须防穿越——`Path::join` 遇绝对路径会**替换**基路径；必须拒绝绝对路径与 `..` 组件，`canonicalize` 后校验 `starts_with(base)`。
  > 为什么：仅做字符串拼接会让 `../../etc/passwd` 或绝对路径逃出基目录，导致任意文件读写。
  > 依据：官方文档：`std::path::Path::join`。

- **RUST-SEC-003**（blocker）：敏感信息不得以字面量写入源码；`env!` 会在编译期把值嵌入二进制，密钥用运行时 `std::env::var` 或密钥管理服务。
  > 为什么：源码、构建产物与镜像都会携带该值，泄露后无法通过改环境变量撤销。G-SECRET。
  > 依据：官方文档：`env!`「在编译期读取环境变量」。

- **RUST-SEC-004**（warning）：`Debug` 与日志可能泄露密钥/PII；含密类型必须手写 `Debug` 或脱敏，禁止直接 derive 后打印。
  > 为什么：日志会被聚合、转发与长期保留，泄露后难以撤回。

## CONC：并发与 async

> async 的正确性依赖三件事：不阻塞、不跨 await 持锁、不丢任务。
> **本组以 tokio 为示例实现**：API 名（`spawn_blocking` / `block_in_place` / `select!` / `JoinHandle`）取自 tokio。使用其他 runtime（async-std / smol / embassy 等）时，按**等价契约**判定：阻塞写法的对应替代、任务句柄的 join 语义、取消安全的等价保证；报告须注明所用 runtime 与对应的等价 API，不得因名称不匹配判为通过。（`await_holding_lock` 是 runtime 无关的 Clippy 标准 lint，检测 guard 跨 await，其他 runtime 同样适用。）

- **RUST-CONC-001**（blocker）：async 任务中禁止阻塞——`std::thread::sleep`、同步 I/O、重 CPU 计算；用 runtime 的异步定时器（如 `tokio::time::sleep`）、异步 I/O、`spawn_blocking` / `block_in_place` 的等价物。
  > 为什么：worker 线程被阻塞后，同 runtime 上的其他任务无法推进，延迟会整体放大。

- **RUST-CONC-002**（blocker）：禁止跨 `.await` 持有 `std::sync::MutexGuard` / `RwLockGuard`。
  > 为什么：std guard 不是为跨 await 设计的，可能导致 lock 跨越任务调度；缩到无 await 的块内即可。
  > 例外：确需跨 await 持锁才用 `tokio::sync::Mutex`；std Mutex 通常更优，async mutex 更贵。
  > 检测：Clippy `await_holding_lock`（suspicious，默认 warn，直接生效）；依据：官方文档：`tokio::sync::Mutex`。

- **RUST-CONC-003**（blocker）：不得静默丢弃任务句柄（tokio 的 `tokio::spawn` 返回 `JoinHandle`，其他 runtime 有等价类型）。
  > 为什么：丢弃即 detach，任务错误与 panic 无人处理，任务生命周期也不受控。
  > 做法：await 并处理 join 错误，或显式 `let _ =` 并注释「故意 detach」。
  > 检测：**无对应 Clippy lint**（`let_underscore_future` 只查未绑定的 Future，无法区分任务句柄），只能人工核对。
  > 依据：Tokio 文档：`JoinHandle`；G-SWALLOW。

- **RUST-CONC-004**（warning）：多锁必须固定全局加锁顺序，缩小临界区，优先消息传递。
  > 为什么：顺序不一致即死锁，且往往只在特定调度下复现。

- **RUST-CONC-005**（warning）：非 `SeqCst` 的 `Ordering` 必须注释说明选择理由。
  > 为什么：错误内存序造成难复现的可见性/数据竞争问题，review 时无法从代码看出意图。

- **RUST-CONC-006**（warning）：`select!`（或等价的「多 future 竞速」原语）中的 future 必须 cancel-safe。
  > 为什么：select! 完成一个分支会取消其余分支；非 cancel-safe API 被取消会丢数据或留下不一致状态。
  > 反例：在 `select!` 分支里直接 `read_exact` / `write_all`（官方文档列为非 cancel-safe）。
  > 依据：Tokio 文档：`select!`「Cancellation safety」。

- **RUST-CONC-007**（warning）：`block_in_place` 仅用于 multi-thread runtime；current_thread 下调用会 panic。
  > 为什么：current_thread runtime 没有其他 worker 可接管被让出的任务。
  > 依据：Tokio 文档：`block_in_place`「Panics」。

## BUILD：构建与工具链

> 工具链配置决定规则能否被机械执行；不能只写在文档里。

- **RUST-BUILD-001**（blocker）：CI 与本地必须执行 `cargo fmt --check` 与 `cargo clippy --all-targets --all-features -- -D warnings`，警告清零。
  > 为什么：依赖人工审查的规则无法规模化；警告堆积后 `-D warnings` 将不可用。
  > **检测能力边界**：`-D warnings` 只把**默认级别为 warn** 的 lint 升级为 error，**不会启用** allow-by-default 的 lint。本文标注「需启用」的 lint（pedantic / restriction 组；nursery 组唯一相关的 `redundant_clone` 只作人工判据，见 RUST-OWN-002）在裸命令下不会报，相关规则的机械门禁为 0，只能靠人工。
  > **推荐基线**（逐条 `-W`；**不要**启用 `clippy::pedantic` / `clippy::restriction` 整组——整组会引入大量与本文无关的噪声）：
  > ```text
  > cargo clippy --all-targets --all-features -- \
  >   -D warnings \
  >   -W clippy::needless_pass_by_value \
  >   -W clippy::cast_possible_truncation -W clippy::cast_sign_loss -W clippy::cast_possible_wrap \
  >   -W clippy::unwrap_used -W clippy::expect_used \
  >   -W clippy::undocumented_unsafe_blocks \
  >   -W clippy::allow_attributes_without_reason \
  >   -W clippy::missing_errors_doc -W clippy::missing_panics_doc
  > ```
  > 测试与基准路径（`tests/`、`benches/`、`#[cfg(test)]`）按 SKILL.md『豁免』不受编码规则约束，`unwrap_used` 等会误伤：须在测试 target 上 `#[allow]` 或在 CI 中分开执行，并把该策略写进仓库说明。基线可按项目裁剪，裁剪须记录理由。
  > 工具行为引用自 Clippy lint 列表（分组与默认级别），版本变化时按本机工具链重新核对。

- **RUST-BUILD-002**（warning）：`#[allow(...)]` 必须带理由；禁止无理由的 crate 级 allow。crate 级 `#![allow(a, b, c)]` 单行多 lint 时，须整体给出一条覆盖全部的理由或逐条理由；只覆盖其中一部分不算通过。`#[expect(...)]` 同样必须带理由，且过期未触发会报 `unfulfilled_lint_expectations`（`-D warnings` 下直接失败），须随代码变化清理。
  > 为什么：`#![allow(dead_code)]` 之类会永久掩盖新问题，且没有到期机制。
  > 检测：Clippy `allow_attributes_without_reason`（restriction，需启用）。

- **RUST-BUILD-003**（warning）：可不使用 unsafe 的 crate 加 `#![forbid(unsafe_code)]`；含 unsafe 的 crate 开 `#![deny(unsafe_op_in_unsafe_fn)]`。
  > 为什么：让新增 unsafe 成为显式、可审查的决策，而不是在 unsafe fn 内隐式扩散。
  > 说明：rustc lint，按本机工具链版本核对。

- **RUST-BUILD-004**（warning）：声明 `rust-version`（MSRV），CI 至少跑一次 MSRV 构建。
  > 为什么：否则新语法或依赖升级会把用户挡在编译门外，且通常到发布后才暴露。

- **RUST-BUILD-005**（warning）：不要依赖 `panic = "abort"` 改变测试行为——稳定 Cargo 下 tests/benchmarks 会**忽略**该设置，测试仍以 unwind 构建；只有启用不稳定的 `panic-abort-tests` 或自定义 harness 时才会变化，此时须确认构建配置并标注「未能判定」。
  > 为什么：把「测试为何失败」归因于 abort 策略通常是查错了地方；libtest 需要 unwind 才能在进程内捕获用例 panic。
  > 依据：官方文档：Cargo Profiles — panic（“Tests, benchmarks, build scripts, and proc macros ignore the panic setting”）、rustc Tests；criterion 等自定义 `harness = false` 基准按其自身要求处理。

- **RUST-BUILD-006**（warning）：二进制与可部署应用提交 `Cargo.lock`；纯库按团队约定。
  > 为什么：可部署物需要可复现构建；库的 lockfile 不会传递给下游，约束有限。

## LOG：日志

> 库只产生日志事件，不决定输出去向。

- **RUST-LOG-W001**（warning）：库不得用 `println!` / `eprintln!` 当日志；用 `log` / `tracing` 门面，由应用决定输出与过滤。
  > 为什么：库直接写 stdout 会污染调用方输出，且无法被统一关闭或分级（G-LOG）。

- **RUST-LOG-W002**（warning）：日志使用结构化字段并脱敏，不要拼接含密钥的字符串。
  > 为什么：结构化字段可检索、可过滤；拼接后无法可靠脱敏。
  > 反例：`info!("login {}", token)`；正例：`info!(user_id = %id, "login")`。

## MAGIC：魔法值

> 魔法值让语义变更无法全局定位。

- **RUST-MAGIC-001**（blocker）：有业务/领域语义的字面值必须是 `const` 或 `enum`；`0` / `1` / `-1` / 空串 / 布尔等惯用值除外（G-MAGIC）。
  > 反例：`if status == 3`、`Duration::from_secs(86400)` 散落在业务代码中。

## PERF：性能

> 先正确后性能；只在热点上优化可观测的分配与遍历。

- **RUST-PERF-W001**（warning）：热路径避免不必要的 `clone` / `to_owned` / `format!`，优先借用或 `Cow`。
  > 为什么：每处分配都会在热路径上被调用次数放大。
  > 去重：与 RUST-OWN-002 重叠时按 RUST-OWN-002 报一次；本条只在「正确性无误但分配进入热点」时报。

- **RUST-PERF-W002**（warning）：已知容量时用 `with_capacity` 预分配；索引用途明确时优先迭代器。
  > 为什么：反复 realloc 与手工下标都增加成本与越界面。
  > 检测：Clippy `needless_range_loop`（style，默认 warn，直接生效）。

## 本语言专属豁免

- **测试/基准**：`tests/`、`benches/`、`src/` 内 `#[cfg(test)]` 模块按 `code-rules/SKILL.md` 全量豁免，交 `test-author`（设计）/ `test-review`（审查）；`#[bench]` 与基准同样豁免。
- **FFI 模块**：可在 `// SAFETY:` 说明下使用裸指针、`union`、`extern` 声明；UNSAFE-002 的 transmute 禁令不因 FFI 放宽，确需时仍须给出布局/大小证明。
- **build.rs**：可执行构建期命令、读写 `OUT_DIR`，但仍受 G-SECRET / G-CMDINJ 与 RUST-SEC-001 约束；构建期生成的值不等于运行时密钥。
- **生成代码（OUT_DIR / bindgen 产物 / proc-macro 展开产物）**：风格类问题（OWN/API/DOC/PERF）只作 warning，不阻塞提交；安全类 blocker 仍须在生成配置、宏的输入写法或调用边界修复。proc-macro 展开出的 `transmute`、`unsafe impl`、`unsafe extern` 同属生成代码，但**宏定义处的输入写法**（`quote!` 模板本身）按源码审查，不受本条豁免。
- **no_std crate**（`#![no_std]`，用 `core` / `alloc`）：
  - **默认全部规则照常适用**；下列四点是本文件中最常被误判的差异，不代表其余规则不适用。
  - 错误类型按 RUST-ERR-003 用 `core::error::Error`（按本机工具链版本核对，Rust 1.81+ 可用）。
  - RUST-CONC 组的 tokio 示例不适用；按所选的异步/并发设施（如 `embassy`、`core` 原子、`critical-section`）依等价契约判定。
  - RUST-LOG / RUST-DOC / RUST-PERF 的判据不依赖 std，照常适用；`RUST-BUILD-003`（`forbid(unsafe_code)` / `deny(unsafe_op_in_unsafe_fn)`）同样适用。
  - 测试代码不在本条豁免范围（测试目标通常可用 std）；但 `#[cfg(test)]` 单测若在 no_std crate 内，`format!` 等需 `alloc` 的宏不可用，需 `extern crate alloc` 或改用 `core::write!`，这是设计限制而非规则问题。
- **文档示例**：按 RUST-DOC-002 执行；`unwrap` 仅允许出现在 `compile_fail` 或明确标注的反例中。

## 编写约束

1. 本文 ID 统一使用 `RUST-` 命名空间，不与 C++ 的 ID、`G-*` 或 `ARCH-RS-*` 共用；引用时写全 ID。
2. 每条规则必须指向可观测的代码形态（具体 token、属性、API 或构建配置），不写「保持整洁」类劝告。
3. 每条须含「为什么 / 违反后果」，必要时给最短反例；仅纯风格条目可省略反例。
4. 不重复 G-COMPLEX-DUP / PARAM / SRP / NEST；复杂度问题统一由 G 报。
5. 工具行为只引用官方文档，或标注「按本机工具链版本核对」；不得声称已运行工具链，不得编造版本号或命令输出。
