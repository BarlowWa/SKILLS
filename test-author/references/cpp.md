# C++ 测试设计参考（test-author / references）

> 由 test-author 在测试文件为 C++ 时加载。通用规则见 `test-author/SKILL.md`；本文只补 **C++ 独有的边界形态、惯用写法与语言约束**。

## 测试框架与惯用写法

- 常见框架：Google Test、Catch2、doctest、Boost.Test。
- **参数化集中管理（OGN-001）**：gtest `INSTANTIATE_TEST_SUITE_P` / `TEST_P`；Catch2 `GENERATE` + `SECTION`；doctest 子用例（`SUBCASE`）。
- **命名（OGN-002）**：`ReturnsZero_WhenQueueEmpty`、`DivByZero_Throws`、`ExactCapacity_Ok`。
- **断言选择**：`EXPECT_*` 非致命 / `ASSERT_*` 致命；浮点用 `EXPECT_NEAR` / `EXPECT_DOUBLE_EQ`（见 `test-review` ASRT）。

## BVA-002 细化：STL 容器

`std::vector` / `std::string` / `std::map` 等的边界：
- 0 → 1 元素、`capacity()` 恰好用满、扩容翻倍处的**拷贝/移动语义**；
- `pop_back` 至空后再访问、`clear()` 后复用；
- 迭代器失效：`insert`/`erase` 使迭代器失效后继续使用（与 `code-rules` SEC-A002 呼应）；
- `reserve` 恰好等于 size 与 size+1；
- 空容器上调用需前置条件的成员（`front()`/`back()`）。

## BVA-003 细化：C 字符串与缓冲区

- NUL 终止符占位：`char buf[N]` 可写 **N-1** 个字符 + 终止符；
- `snprintf` / `strncpy` 类接口必须测「长度 == 缓冲区大小」与「长度 == 大小-1」两侧，并断言返回值与终止符行为；
- 含内嵌 `\0` 的 `std::string` 传给 C API 时的截断；
- 多字节 UTF-8 在缓冲边界处被截断（可能产生半个码点）；
- `std::string_view` 指向的底层对象生命周期（借用临时 `std::string` 即悬垂）。

## BVA-005 细化：索引与迭代器

- `0`、`size()-1`、`size()`（越界首个）、有符号负数索引（转为巨大无符号值是典型 bug，见 `code-rules` SEC-B001）；
- 迭代器首/末/末+1；`end()` 解引用；
- `std::span<T>` 的 `size == 0` 与 `data == nullptr` 两种"空"。

## BRP-004 细化：C++ 空值形态

`nullptr`、`std::nullopt`、空 `std::span`、空 `std::string_view`、空 `std::vector`、默认构造的 `std::function`（调用即 `bad_function_call`）。每种"空"的语义不同，须分别设计用例。

## BRP-003 细化：异常安全

- 三个保证等级：basic / strong / **nothrow**。
- `noexcept` 是说明符：`code-rules`（cpp.md）ERR-002 声明为 `noexcept` 的路径用 `EXPECT_NO_THROW` 显式验证；也须验证"该 noexcept 函数内部抛出会被 `std::terminate`"这一契约边界。
- strong 保证：抛出后对象状态回滚到可观测的等价状态——需多条断言或拷贝比对，单条断言无法验证。
- 析构顺序：构造逆序析构，异常传播时已构造成员的退还。

## CONC-001 细化：C++ 并发原语

- 覆盖 `std::mutex` / `std::shared_mutex` 的加锁与解锁、条件变量的虚假唤醒（谓词循环）、`std::atomic` 的内存序（默认 `seq_cst`，非默认序须在该路径设计可见性用例）；
- 测试内创建的线程必须 join；未 join 的 `std::thread` 析构会 `std::terminate`；
- 竞态用例需可确定性复现（同步屏障/事件），禁止依赖 sleep 猜测。

## RLC-001 细化：C++ 资源

- RAII 对象的析构路径：正常返回、提前 return、异常展开；
- **move-from 后复用**：标准库保证 moved-from 对象处于"有效但未指定"状态，断言其可析构、可重新赋值，不断言其原值；
- 拷贝 vs 移动语义（`std::move` 后源对象状态）；
- 双重释放、释放后使用（`unique_ptr::release()` 后悬垂）；
- 析构幂等性（显式 `close()` + 析构二次释放）。

## 本语言特有豁免

- 基准测试（`*_bench.cpp`、`bench/`）：不适用本文与父技能全部规则。
- 与 C 互操作时，涉及裸指针/`void*` 的用例按被测契约设计，不受 `code-rules` BAN-* 约束（被侧面豁免的是被测代码的写法，不是测试可观测性要求）。
