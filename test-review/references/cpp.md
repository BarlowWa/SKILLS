# C++ 测试审查参考（test-review / references）

> 由 test-review 在测试文件为 C++ 时加载。通用判据见 `test-review/SKILL.md`；本文提供 **CMake/CTest 的执行证据获取方式**、gtest/Catch2 的形态词表，以及 C++ 实测中最容易造成误判的陷阱。

## 一、执行证据获取（EXEC 组）

### 1.1 构建配置与目标清单

- 测试目标清单：`build/CMakeFiles/TargetDirectories.txt`；或 `cmake --build <dir> --target help`。
- 测试源是否进构建：与目标清单做双向差集，**不要**用文本搜 `add_subdirectory`（相对路径写法各异，实测误报 3–4 条）。
- 构建产物反查：`bin/<config>/` 或 `CMAKE_RUNTIME_OUTPUT_DIRECTORY` 下是否有对应测试可执行文件。

> ⚠️ **多配置生成器（VS/Ninja Multi-Config）下各 config 产物目录内容不同且新旧不一**：实测某仓库 `bin/Release/` 有 24 个测试 exe，`bin/Debug/` 只有 5 个陈旧残留。拿后者对账会得出「19 个没进构建」的假 blocker。**先确认当前构建使用的 config**。

### 1.2 注册清单（EXEC-002）

- **必须在构建目录**执行 `ctest -N`（或 `ctest --show-only`）。实测某仓库根目录的 CMakeLists 含 `enable_testing()`，在仓库根跑 `ctest -N` **成功返回 `Total Tests: 0`**——不是报错，是静默给 0，据此判"全部未注册"就是一个假 blocker。先确认 `CTestTestfile.cmake` 在哪个目录。
- **不得用 CMakeLists 字面文本做差集**：注册常由变量/foreach 生成：
  ```cmake
  foreach(test_target ObjectPoolTest ThreadPoolTest ...)
    add_test(NAME ${test_target} COMMAND ${test_target})   # 字面 grep 查不到
  endforeach()
  ```
  实测某仓库字面比对待出 10 条"未注册"，**全部是假阳性**。
- **范围限定**：`add_executable` 还包含 DLL、驱动、工具等非测试目标（实测 24 个里有 `ODBCDriver` 等），先确认哪些 target 是测试。

### 1.3 跳过与红灯证据（EXEC-003 / EXEC-005）

- gtest：`--gtest_output=xml` 产出每个 testcase 的运行状态（官方示例形如 `<testcase name="..." status="run" .../>`；**具体"未运行/被抑制"的取值以本地 gtest 版本的实际输出为准**，不要凭文档片段推断）。
- CTest：跳过项写入 `LastTestsDisabled.log`；`--print-labels` 查看标签。
- ⚠️ **`LastTestsDisabled.log` 只在有跳过项时更新**：全绿重跑不刷新它，实测某条目 mtime 已过期 3 小时而重跑该测试是 Passed。读取前**先核对 mtime**。
- ⚠️ **源码扫描 0 命中只能证明"没用这些宏"，不能证明"没有跳过"**：实测某仓库框架跳过宏 0 命中，而 CTest 日志确实记录了被跳过的测试。
- ⚠️ **自研 harness 没有现成运行产物**：`--gtest_output=xml` 这条路径不存在，`LastTestsDisabled.log` 可能只记录 CMake 层 `SKIP_RETURN_CODE`、不记录测试内部自跳过。此时只能回到源码扫描，须放宽结论并明说"跳过情况未能完整核对"。

### 1.4 计数与对账（EXEC-006）

- 裸 `grep -c TEST_CASE` 会把**注释里提到 `TEST_CASE` 的行**算进去（实测 527 vs 真实 516，差 11 全在注释）。用 `^TEST_CASE(` 这类行首锚定写法。
- 名字可能含转义引号或多字节字符（实测 `TEST_CASE("...value(key, \"literal\")...")`），自动比对前先归一化。
- **按名字做双向差集**，对每处差异回读 `#ifdef` 结构；**不要用总数相减判红**。

## 二、C++ 跳过形态词表（EXEC-003）

- `GTEST_SKIP()`、`DISABLED_` 前缀、`doctest::skip()`、Catch2 的 `[.]` 标签；
- `#if 0` 包裹测试体；
- 条件编译包裹整个 `TEST_CASE`（`#ifdef _WIN32`、`#ifndef NDEBUG` 等）——先看 `#ifdef` 是否**配对**（同名替换属正当，静默消失才隐蔽）；
- 用例体只有 `return;`（空壳占位，永远通过）；
- **前置 guard + 提早 return（最易漏检）**：
  ```cpp
  TEST_CASE("...") {
      const std::string& dll = odbcDriverPath();
      if (dll.empty()) return;      // ← 无标记的静默跳过，运行时 [PASS]
      ...真正的断言...
  }
  ```
  实测某仓库有 9 处此形态，源码注释自述为「SKIP 约定」——这是该仓库**最主流的跳过机制**，而 `GTEST_SKIP`/`DISABLED_`/`[.]` 等标准词表**一条都覆盖不到**。判定：依赖外部资源的 guard 可能是合理防御，但必须能与"真的测过了"区分；只在运行时 `[PASS]` 而不留痕迹的，按 blocker，至少记 warning 要求补标记。
- `SKIP_RETURN_CODE <码>` + 实现侧在缺依赖时主动返回该码（而非静默 `return 0`）——**正当用法**，不报缺陷。

## 三、DEATH：死亡/崩溃断言（warning）

- **DEATH-001**：Death test（`EXPECT_DEATH` / `ASSERT_DEATH` / `EXPECT_DEATH_IF_SUPPORTED` / `EXPECT_EXIT`）仅用于验证程序的断言/abort/致命崩溃行为及退出码。**禁止**用于验证普通异常抛出——异常用 `EXPECT_THROW` 验证。
  > Death test 在独立子进程运行：POSIX 下 gtest 默认 fork（开销较低）；Windows 无 fork，回退到 threadsafe 风格（spawn 新进程并重跑整个测试到死亡点，开销可达数百 ms~秒级）。且 death test 不继承测试夹具的内存态、其副作用不会回流主进程。滥用会显著拖慢测试套件，Windows 上尤甚。

## 四、实测中的假阳性陷阱（定性前必读）

- **`*ReproTest` 全绿且无标记**：先看提交顺序。实测某仓库 7 个 `*ReproTest` 全绿无标记，但提交顺序证明红灯曾生效（测试提交早于各修复提交）且断言写的是「应该提供/应该返回正确值」——属「红灯已修复」，不该报 blocker。
- **平台 `#ifdef` 配对替换**：`#ifdef _WIN32` / `#else` 各一条 `TEST_CASE`，总数守恒、名字互换，运行时只注册 1 条——这是同一个测试的两种平台实现，不是"用例静默消失"。读注释与技术理由；带说明且另一平台已覆盖的，记 warning。
- **`friend` 可见性**：仅为测试可见性的前置声明（如 `class FooTest;`）在部分代码库属既有约定，存量可分期整改；**断言私有成员取值**与 `#define private public` 不豁免。
- **环境问题**（并行运行改写日志、产物目录与工作目录不在同一盘、缺 `-C` 参数）不是测试代码缺陷——报告「未能判定」并说明所需环境。

## 五、本语言特有豁免

- 基准测试（`*_bench.cpp`、`bench/`）：豁免全部规则，**仅保留 EXEC-001/EXEC-002** 的工程性判据（基准必须真的被构建并注册）。
- DET-002（实时时钟）在专门测试时间相关逻辑的 integration test 中可例外，需注释说明原因。
