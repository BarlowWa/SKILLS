---
name: cpp-test-review
description: 审查 C++ 测试代码质量。覆盖测试文件组织、Mock/Fake 策略、测试确定性、异常路径覆盖、Death Test 使用等方面。当用户要求审查测试代码、检查测试质量时激活。
---

# C++ 测试代码审查

对 C++ 测试代码进行质量审查，确保测试可靠性、可维护性和有效性。

## 适用范围

- 测试目录：`tests/`、`test/`、`unittest/`、`*_test.*`、`*_unittest.*`
- 测试框架：Google Test（gtest）、Catch2、doctest、Boost.Test 等
- **不适用**：生产代码的编码规范（由 `cpp-rules` 负责）、测试用例设计（由 `cpp-test-author` 负责）、模块架构审查（由 `cpp-arch-review` 负责）

## 工作流程

1. **读取用例设计清单（若有）**：若存在 `cpp-test-author` 产出的「用例矩阵 + 未覆盖项」，先读取作为核对基准
2. **识别测试文件**：扫描测试目录和命名模式，确定审查范围
3. **逐文件审查**：对照下方 checklist 逐条检查
4. **输出报告**：按底部格式输出审查结果

## 严重级别

| 级别    | 含义                                              |
| ------- | ------------------------------------------------- |
| blocker | 必须修复，违规测试可能产生假阳性/假阴性，削弱测试可信度 |
| warning | 优化建议，应处理但不阻塞提交                       |

---

## Blocker 检查清单

### ORG：文件组织

- **ORG-001**：测试文件必须与源文件有明确对应关系。命名规范：`<source>_test.cpp` / `<source>_unittest.cpp` / `<module>_test.cpp`；禁止无关联的随机测试文件名
  > 对应关系确保他人能快速定位测试，避免测试成为黑盒。
- **ORG-002**：测试目录结构应镜像源代码目录结构。如 `src/foo/bar.cpp` 对应 `tests/foo/bar_test.cpp` 或其等价路径

### MOCK：Mock 与 Fake 策略

- **MOCK-001**：禁止 mock 不拥有的类型。只能 mock/fake 自己代码中的接口，禁止 mock 第三方库、STL 或系统 API 的具象类
  > mock 第三方类型会在库升级时无声失效（接口变化但 mock 不报错，测试继续通过），导致虚假安全感。
- **MOCK-002**：禁止对值类型和 STL 容器（`std::vector`、`std::string` 等）使用 mock——直接构造真实实例即可，mock 值类型不增加价值反而增加复杂度

### DET：测试确定性

- **DET-001**：禁止在测试断言中使用 `std::rand()` / `std::random_device` / `std::mt19937` 等非确定性随机源。若需要随机数据，使用确定性的种子生成器并在测试中显式注入
  > 非确定性随机源导致测试偶发性失败（flaky test），极难调试且破坏 CI 可信度。
- **DET-002**：禁止在测试断言中直接使用 `std::chrono::system_clock::now()` / `time()` / `gettimeofday()` 等实时时钟。使用可注入的假时钟（fake clock）配合时间源抽象
  > 实时时钟依赖导致测试在跨时区、夏令时切换、系统时间调整时失败，且运行速度不可控。注意：`std::chrono::steady_clock` 仅保证单调（免墙钟回拨），**不能**让测试确定性——真实时间仍流逝；确定性解法是"时间源抽象 + 注入假时钟"，`steady_clock` 不能替代。
- **DET-003**：测试用例之间禁止通过全局变量、静态变量、单例状态共享可变数据。每个测试必须是独立的（isolated），运行顺序不应影响结果
  > SetUp/TearDown 中必须重置所有全局/静态状态。测试框架通常不保证用例执行顺序。
- **DET-004**：异步/并发测试必须确定性——异步操作须显式等待完成（`future.get()`/`wait()`、事件/条件变量通知），测试内创建的线程必须 join（未 join 的 `std::thread` 析构会 `std::terminate`），竞态敏感点用确定性同步手段，禁止依赖调度时序或 sleep 猜测

### ASRT：断言质量

- **ASRT-001**：每个测试用例必须包含至少一个有效断言（EXPECT/ASSERT）。禁止空测试或无断言测试——一个不含断言的 TEST 默认通过，给出"已覆盖"的虚假安全感
- **ASRT-002**：断言须验证关键语义。禁止恒真/无意义断言（`EXPECT_TRUE(true)`、`ASSERT_TRUE(ptr != nullptr)` 后不验证具体行为）；比较用 `EXPECT_EQ`/`EXPECT_NE` 而非 `EXPECT_TRUE(a == b)`（失败信息差异巨大）
- **ASRT-003**：浮点比较禁止直接 `EXPECT_EQ`，使用 `EXPECT_NEAR` / `EXPECT_DOUBLE_EQ` 并显式设定容差（EPSILON）
- **ASRT-004**：正确选用 `EXPECT`（非致命，继续执行）与 `ASSERT`（致命，失败即终止当前用例）；依赖后续语句安全时（如解引用指针前）用 `ASSERT` 提前拦截

---

## Warning 检查清单

### COV：路径覆盖

- **COV-001**：每个被测公开接口（函数/方法）的测试集应覆盖正常路径和至少一个边界条件或异常/错误路径。禁止仅有 happy-path 的完整接口测试集
  > 仅有正常路径的测试给人以"已测试"的错觉，实际上异常分支完全未验证，是测试覆盖率中最常见的盲区。
- **COV-003**：若存在 `cpp-test-author` 产出的用例设计清单（用例矩阵 + 未覆盖项），对照逐项核对实际测试是否落地；缺失的 BVA/ECP/BRP 覆盖需在报告中显式列出。本条衔接 `cpp-test-author`（写时设计 → 写后审查）
  > COV-002（覆盖率阈值）见下方「COV-W：覆盖率建议」小节。

### MOCK-W：Mock 深入建议

- **MOCK-004**：优先使用 Fake（轻量内存实现）而非 Mock（期望验证框架）。Fake 更简洁、可复用，且与实现解耦；Mock 适用于需验证交互协议的场景（如回调次数、调用顺序）
  > 过度使用 EXPECT_CALL / ON_CALL 会使测试脆弱——被测类的内部重构不应破坏测试。
- **MOCK-005**：区分 Stub / Fake / Mock 三概念——Stub（固定返回值，无交互验证）、Fake（可用轻量实现）、Mock（期望验证）。优先用 Stub/Fake 表达"桩"语义，避免为简单固定返回值引入完整 Mock 框架
- **MOCK-003**：单个测试用例中 mock 对象数量宜控制在 3 个以内。超出时通常是被测类职责过重的信号，建议重构而非继续堆砌 mock（本条为启发式建议，不阻塞提交）

### DEATH：Death Test 规范

- **DEATH-001**：Death test（`EXPECT_DEATH` / `ASSERT_DEATH` / `EXPECT_DEATH_IF_SUPPORTED` / `EXPECT_EXIT`）仅用于验证程序的断言/abort/致命崩溃行为及退出码。**禁止**用于验证普通异常抛出——异常用 `EXPECT_THROW` 验证
  > Death test 在独立子进程运行：POSIX（Linux/macOS）下 gtest 默认用 fork 子进程（开销较低）；Windows 无 fork，gtest 回退到 threadsafe 风格（spawn 新进程并重跑整个测试到死亡点，开销可达数百 ms~秒级）。且 death test 运行在独立进程，不继承测试夹具的内存态、其副作用不会回流主进程。滥用会显著拖慢测试套件，Windows 上尤甚。

### COV-W：覆盖率建议

- **COV-002**：建议语句/分支覆盖率阈值 ≥ 80%，核心模块建议 ≥ 90%。本条为可配置的目标声明（需运行时工具测量），仅作为审查时的参考建议

### TPERF：测试执行效率

- **TPERF-001**：单个测试用例平均执行时间应控制在 100ms 以内。超过 500ms 的测试应标记为慢速测试并确认必要性
  > 本条依赖运行时测量数据，静态审查时作为参考建议。
- **TPERF-002**：禁止在测试中使用 `sleep()` / `std::this_thread::sleep_for()` 等主动等待——用条件变量、fake clock 或轮询超时替代

---

## 审查输出格式

```
## 测试审查报告

**审查文件**：N 个测试文件
**测试框架**：<gtest / Catch2 / doctest>

### Blocker 检查
- [x] ORG：文件组织 —— 通过
- [ ] MOCK：Mock 策略 —— MOCK-001：`tests/network_test.cpp:42` mock 了第三方 `libcurl::Session`，应封装为自有接口
- [ ] DET：测试确定性 —— DET-002：`tests/timer_test.cpp:18` 直接使用 `system_clock::now()`，应使用 fake clock
- [ ] ASRT：断言质量 —— ASRT-002：`tests/foo_test.cpp:30` 使用 `EXPECT_TRUE(a == b)`，应改为 `EXPECT_EQ`
- ...

### Warning 检查
- [x] COV：路径覆盖 —— 通过
- [x] MOCK-W：Mock 深入建议 —— 通过
- [x] DEATH：Death Test —— 通过
- [x] COV-W：覆盖率建议 —— 通过
- [x] TPERF：测试执行效率 —— 通过
- [ ] <类别>：<问题> —— ...

### 设计覆盖核对（若有 cpp-test-author 清单）
- [x] BVA：边界值分析 —— 已落地 / 缺失项见下
- [x] ECP：等价类划分 —— 已落地 / 缺失项见下
- [x] BRP：分支路径覆盖 —— 已落地 / 缺失项见下
- [x] FLT：故障注入 —— 已落地 / 缺失项见下
- [x] CONC：并发与线程安全 —— 已落地 / 缺失项见下
- [x] RLC：资源生命周期 —— 已落地 / 缺失项见下
- 缺失覆盖项：
  - <规则>：<缺失描述>
（无 cpp-test-author 设计清单时，本小节标记"未提供设计清单，跳过核对"）

### 总结
- Blocker：2 项违规 —— 必须修复
- Warning：1 项建议
```

---

## 豁免

- 用例设计由 `cpp-test-author` 主动规划（边界值/等价类/分支路径），本技能专注落地后的质量审查；两者协同形成「先设计、后审查」闭环
- 与已有大型遗留测试集集成时，ORG-001/002（文件组织）的目录结构改造可分期实施，新建测试必须遵守
- 性能基准测试（benchmark）使用独立的 `*_bench.cpp` 或 `bench/` 目录，豁免本技能中与正确性相关的规则（DET/COV 类），性能相关规则（TPERF-001/TPERF-002）也不适用
- DET-002（实时时钟）在专门测试时间相关逻辑的 integration test 中可例外，需注释说明原因
- 其余规则无一例外
