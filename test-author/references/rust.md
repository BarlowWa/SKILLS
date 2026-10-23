# Rust 测试设计参考（test-author / references）

> 由 test-author 在测试文件为 Rust（`tests/*.rs`、`src/**` 内 `#[cfg(test)]`、doctest）时加载。通用规则见 `test-author/SKILL.md`；本文只补 **Rust 独有的边界形态、惯用写法与语言约束**，不新增规则 ID。

## 测试框架与惯用写法

- **内置 libtest**（无需额外依赖）：
  - 单元测试放在 `#[cfg(test)] mod tests { use super::*; ... }`，可访问本 target 的**私有** API；
  - 集成测试放 `tests/*.rs`，**每个文件编译为独立 crate**，只能访问库的 **public API**；共享辅助代码放 `tests/common/mod.rs` 并 `mod common;`；
  - doctest 是 `///` 文档注释中的示例，`cargo test` 默认运行，可单跑 `cargo test --doc`；每个代码块独立编译执行。
- **可选 crate**（第三方，非标准库）：rstest（`#[case]`/`#[values]` 参数化）、trybuild（编译失败测试）、tokio（`#[tokio::test]`）、tempfile、serial_test、loom。
- `#[should_panic(expected = "...")]` 的 `expected` 是**子串匹配**（panic 消息包含即通过），且该测试返回类型必须是 `()`；**panic 之后的语句永不执行**，不要把关键断言写在触发 panic 的语句之后（与 `test-review` EXEC-004 呼应）。
- 测试函数可返回 `Result<(), E>`，返回 `Ok(())` 即通过，可用 `?`。**期望返回 `Err` 的用例写成普通 `#[test]` 并用 `assert!(matches!(...))`**，不要用 `#[should_panic]`——后者只描述 panic，不是错误返回值。

## BVA-002 细化：容器/序列

- `Vec` / `String` / `HashMap` 等覆盖：空、1 元素、恰好容量、扩容前后（`len == capacity` 与 `len == capacity + 1`）。
- `HashMap` / `HashSet` 的**迭代顺序不确定**：断言不得依赖 `iter()` 收集出的 `Vec` 顺序；用按键取值、排序后比较，或直接比较集合相等。比较两个 `HashSet` 本身是顺序无关的。
- `Vec::with_capacity(n)` 允许分配**多于** n 的容量，不要断言 `capacity() == n`，断言 `>= n` 或只断言 `len` 与行为。
- `Vec::with_capacity(0)` 不分配；首次 `push` 才可能分配——空容器与「有容量但 len 为 0」是两种状态。
- `windows(0)` / `chunks(0)` 会 panic；`windows(k)` 在 `len < k` 时产出空迭代器；`chunks` 末尾余数块单独覆盖。
- `split_at(n)`：`n == len` 合法（尾段为空），`n > len` panic；`str` 的 `split_at` 还要求 char boundary（见 BVA-003）。

## BVA-003 细化：字符串/字节

- `str::len()` 是**字节数**，`chars().count()` 是 Unicode 标量数；含多字节字符时两者不同，断言分别设计。
- 字节切片 `&s[..n]` 与 `split_at(n)` 在 **非 UTF-8 char boundary** 会 panic；在 `n-1` / `n` / `n+1` 处各取用例（n 为某多字节字符起点）。
- 非法 UTF-8 用 `&[0xFF]` 等字节走 `std::str::from_utf8` 的 `Err(Utf8Error)` 路径，并断言 `valid_up_to()` 等错误信息；`from_utf8_lossy` 是另一条替换路径。
- Rust 的 `String` / `&str` **允许内嵌 NUL**；传给 C 互操作时 `CString::new` 会因内部 NUL 返回 `Err(NulError)`——这是独立于长度边界的错误路径。
- `chars()` 是标量而非字素簇（用户感知字符）；涉及组合字符/emoji 的契约须写明按哪种计数。

## BVA-005 细化：索引与迭代

- `0`、`len - 1`、`len`（越界）：`v[i]` 越界 panic，`v.get(i)` 返回 `None`；两条路径分别覆盖。
- `usize::MAX` 作为索引/长度输入；有符号负数 `as usize` 会**静默回绕**成巨大值（典型 bug），负值输入应走 `try_into()` 错误路径并断言拒绝。
- 迭代器首/末/末+1：空迭代器、单元素、`next()` 耗尽后返回 `None`；`enumerate` 的末索引为 `len - 1`。
- Range 边界：`0..len`、`len..len`（空）、`..=len - 1`；对切片用超界 range 的 panic 路径。

## BRP-004 细化：Rust 空值形态

`None`、空 `&str`、空 `Vec`、`Err` 语义各不相同，必须分别设计用例：
- `Option` 的 `None` 表示**缺失**，`Result` 的 `Err` 表示**失败**；二者不可互当。
- `Option<Box<T>>` 的 `None` 与 `Some(Box::new(...))` 分开测（后者仍有堆分配与 Drop）。
- `Option::take()` 后原位置变 `None`、值被移出；`unwrap_or` / `?` 等消费路径各覆盖。
- `#[non_exhaustive]` 枚举在本 crate 内可构造全部变体；跨 crate 测试无法构造未来变体，在「未覆盖项」注明。

## BRP-003 细化：错误与 panic

- `Result` 的每个变体、错误枚举的每个变体至少一个用例（含 `#[non_exhaustive]` 的已定义 sentinel）。
- 契约规定的 panic 用 `#[should_panic(expected = "...")]` 固定消息，**不要只写裸 `#[should_panic]`**——后者对任意 panic 都放行，区分度为零。
- `catch_unwind` 仅在需要检查 panic **负载**或测试必须继续执行时使用；普通错误路径不要用 panic 模拟。
- Drop 中 panic 与展开中的 panic 叠加会 **abort**，不能在同一进程内当普通用例验证；析构契约默认「不 panic」。
- 测试 profile 必须可 unwind；`panic = "abort"` 不适配 libtest。
- `debug_assert!` 与整数溢出 panic 只在 debug 生效；不要用「release 下回绕」的测试替代显式 `checked_*` / `saturating_*` 的断言。

## CONC-001 细化：异步与线程

- `#[tokio::test]` 默认 `current_thread`（单线程运行时）；只有确实需要并发执行时才用 `flavor = "multi_thread"`，并用 `worker_threads` 固定线程数。
- 定时器用 `start_paused = true`（需 tokio `test-util` feature）配合 `tokio::time::advance`；**禁止用 `sleep` 等待或制造时序**。
- 测试内 spawn 的任务必须 `await` 其 `JoinHandle`；drop `JoinHandle` 只会分离任务，不能据此判断结果或清理。
- 竞态用同步原语（barrier、channel、锁/原子）构造确定性交错，而不是靠调度顺序。
- Send/Sync 用静态断言固定：`fn assert_send<T: Send>() {}`，在测试中 `assert_send::<MyType>();`；需要模型检查时可用 loom（可选）。
- 避免在 `.await` 期间持有 std 锁（clippy `await_holding_lock`）；需要跨 await 持锁时按 `tokio::sync::Mutex` 契约设计。

## RLC-001 细化：资源与所有权

- Drop 顺序：局部变量按声明**逆序**析构，结构体字段按声明**顺序**析构；用可观测的日志/计数断言顺序。
- `Arc::strong_count` / `Arc::weak_count`：在无并发时断言计数；`Weak::upgrade` 在强引用归零后返回 `None`；循环引用会泄漏（计数不归零）。
- `Option::take()` 留下的 `None` 与资源是否随之释放是两条路径。
- `ManuallyDrop` / `std::mem::forget` 跳过析构：用计数/句柄验证「未释放」这一契约，避免误以为泄漏是 bug。
- `File` 的 Drop 丢弃 `close` 错误；要观察 flush / sync_all 失败必须显式调用并断言 `Result`（析构不得失败）。

## CONTRACT-001 细化：编译期契约（Rust 特有）

- 借用检查、生命周期、trait bound、auto trait（`Send` / `Sync` / `Unpin`）错误**无法在运行时测**；它们属于契约表「错误契约」的一部分。
- 用 trybuild（可选）的 compile-fail 用例固定「**应当编译失败**」的契约，并快照错误输出；否则这类回归完全无声。
- doctest 的 `compile_fail` 属性也能固定编译失败，但它只要求「任意编译错误」，无法保证错在预期的 trait/借用上；精确契约优先 trybuild。
- 需要固定「应当可编译」的 trait 实现时用静态断言（如 `fn assert_clone<T: Clone>() {}`），让缺失实现变成编译失败。

## 确定性（BVA-006 / `test-review` DET）

- 随机数据用显式种子的 `StdRng`（`rand` 为可选 crate），禁止未播种的 `thread_rng` / `rand::random`（DET-001）。
- 时间用注入时钟或 tokio `start_paused`；断言中不得直接读 `Instant::now()` / `SystemTime::now()`（DET-002）。
- 环境变量是进程全局状态，并行测试会竞态；edition 2024 中 `set_var` / `remove_var` 为 `unsafe`。用 serial_test（可选）串行化或进程隔离，优先改为注入配置。
- 单元/集成测试运行时 cwd = **包根目录**；doctest 编译在 **workspace 根**、运行时 cwd = 包根目录。相对路径必须显式，跨目录用 `env!("CARGO_MANIFEST_DIR")` 拼接。
- 用例间不共享全局可变状态（DET-003）；异步/线程任务必须 join/await（DET-004）。

## OGN-001 / OGN-002 细化：组织与命名

- Rust 测试名用 **snake_case 场景描述**：`returns_zero_when_queue_empty`、`div_by_zero_panics`、`exact_capacity_ok`。
- rstest（可选）为每个 `#[case]` 生成独立测试，优于复制粘贴（OGN-001）。
- 表驱动 `for` 循环整体算**一个**用例，首个失败即中止后续数据；关键边界应拆成独立用例或参数化 case，避免被前一个失败遮蔽。
- doctest 也是测试：与集成测试一起设计契约（EXPECT/DIST 同样适用），不要只当作文档示例。

## 本语言特有豁免

- 性能基准（`benches/`、`#[bench]`）不适用本文与父技能全部规则；`#[bench]` 需 nightly 与 `#![feature(test)]`（使用 libtest 内置 bench harness；criterion 等 `harness = false` 工具按其自身要求）。
- 属性测试 / fuzz 不在本技能范围（父技能已定）。
- 可选 crate 的行为以其所用版本文档为准，不得写成标准库内置能力。

> 行为依据：Cargo 参考（Tests / Integration tests / Working directory of tests）、rustc 参考（testing attributes）、rustdoc 文档测试、Tokio `#[tokio::test]` 文档、std 文档（`Vec` / `str` / `CString` / `Drop` / `Arc`）。
