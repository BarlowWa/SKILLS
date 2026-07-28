---
name: cpp-rules
description: 在编写、编辑、审查或重构 C++ 代码（.h、.hpp、.cpp、.cc 文件）时使用。提供强制性编码规范，涵盖内存管理、命名约定、OOP 设计、跨平台兼容性、头文件、多线程、日志及禁用模式。当用户创建、修改或要求审查 C++ 源文件时激活。
---

# C++ 编码规范强制执行

对每个 C++ 文件变更，必须对照下方 checklist 逐条检查。此 skill 是**强制性关卡**——所有 blocker 必须在报告完成前修复。

## 工作流程

### 写新代码 / 重构

1. **写前**：阅读相关章节，理解约束
2. **写中**：边写边应用规则，不推迟
3. **写后**：通读变更文件，逐条对照 checklist 审查；发现违规立即修复
4. **报告**：按底部格式输出审查结果

### 仅审查已有代码（不修改）

1. **了解范围**：确认需审查的文件列表
2. **逐文件审查**：对照 checklist 逐条检查，记录所有违规
3. **输出报告**：按底部格式输出审查结果，标注违规位置与修复建议

## 严重级别

| 级别    | 含义                                              |
| ------- | ------------------------------------------------- |
| blocker | 必须修复，违规代码不得提交                         |
| warning | 优化建议，应处理但不阻塞提交                       |

---

## Blocker 检查清单

### MEM：内存与指针

- **MEM-001**：智能指针必须用 `make_unique`/`make_shared`，禁止 `new` 构造
  > 通过 `new` 构造智能指针存在异常不安全与二次分配问题。
- **MEM-002**：禁止裸 `new`/`delete`/`delete[]`；堆内存全由智能指针/容器管理
- **MEM-003**：裸指针 `T*` 仅限非拥有型观测，所有权归智能指针
  > 裸指针不管理对象生命周期；所有权场景必须使用 `std::unique_ptr` / `std::shared_ptr` / `std::weak_ptr`。

### NAME：命名规范

- **NAME-001**：成员 `m_`、静态 `s_`、全局 `g_`、编译期常量 `k` 前缀；POD 结构体不加前缀
- **NAME-002**：标识符禁止以下划线开头或结尾
- **NAME-003**：函数 `camelCase`；类/结构体/枚举 `PascalCase`；宏/枚举常量 `UPPER_SNAKE_CASE`
- **NAME-004**：纯虚抽象基类以 `I` 前缀命名（如 `IWorker`、`ILogSink`）

### PLAT：跨平台与第三方依赖

- **PLAT-001**：平台 API 必须隔离在 `Platform` 抽象层后，业务代码不得直接调用 OS 专有 API 或系统头文件
- **PLAT-002**：使用 `<cstdint>` 定长类型（`int32_t` / `uint64_t` 等），禁止 `long` / 裸 `int`
- **PLAT-003**：第三方原生句柄/指针必须二次封装，禁止直接暴露至业务层；禁止同时引入功能重叠的第三方库
- **PLAT-004**：优先前向声明减少头文件包含，杜绝循环依赖

### OOP：类设计

- **OOP-001**：有虚函数（多态继承）的基类必须有 `virtual` 析构函数；不作为多态基类时析构可设为 `protected` 非虚
- **OOP-002**：派生类重写虚函数必须标记 `override`
- **OOP-003**：单参数构造函数必须 `explicit`
- **OOP-004**：禁止全局裸函数；所有函数必须归属类或命名空间
- **OOP-005**：类成员默认 `private`；对外接口放 `public`；内部工具/中间状态放 `private` / `protected`
- **OOP-006**：不需要拷贝的类用 `= delete` 禁用拷贝构造/赋值
- **OOP-007**：成员变量优先类内直接初始化，构造函数使用初始化列表

### HEADER：头文件

- **HEADER-001**：头文件包含保护，新项目强制 `#pragma once`；存量项目若已有 `#ifndef` 守卫可保留但不再强制双重保护
- **HEADER-002**：头文件仅放声明，实现放 `.cpp`；禁止 `using` 声明和 `using namespace`
- **HEADER-003**：头文件公开 API/类/枚举必须有 `/** @brief ... */` Doxygen，按需 `@param`、`@return`、`@note`；`.cpp` 实现文件仅用 `//` 行注释

### THREAD：多线程与 Lambda

- **THREAD-001**：Lambda 捕获必须显式书写，禁止 `[=]` 全隐式值捕获
- **THREAD-002**：线程创建统一用 `std::thread`，禁止 OS 原生线程 API
- **THREAD-003**：共享成员变量读写必须通过 `std::mutex` / `std::shared_mutex` 加锁保护；简单数值可用 `std::atomic` 替代

### BAN：强制禁止项

- **BAN-001**：禁止 `goto`，分支跳转用状态机重构
- **BAN-002**：禁止 C 风格强转 `(Type)var`，用 `static_cast` / `const_cast` / `reinterpret_cast`（后者严格管控）
- **BAN-003**：禁止 `NULL` / `0` 表空指针，统一 `nullptr`
- **BAN-004**：业务接口禁止 `va_list` / `va_arg`，用 `std::format` / 模板参数包替代
- **BAN-005**：禁止函数式宏，常量用 `constexpr`，工具函数用 `inline` / 模板

### ERR：错误处理与异常

- **ERR-001**：底层/工具类返回 `std::error_code`；业务逻辑可抛自定义异常；禁止无信息裸 `throw;`（`throw;` 重抛合法）
  > 自定义异常类必须携带完整描述信息。
- **ERR-002**：析构函数、移动构造/赋值、确定不抛异常的函数必须 `noexcept`
- **ERR-003**：所有资源必须 RAII 自动释放

### CONST：常量、传参与类型转换

- **CONST-001**：大型只读参数用 `const&` / `string_view`；禁止按值传大对象
- **CONST-002**：`auto` 仅用于复杂模板/迭代器/`make_*` 返回值，基础类型不用
- **CONST-003**：优先范围 `for` 而非下标迭代

### NS：命名空间

- **NS-001**：所有业务代码归属项目顶层命名空间；`using namespace std` 全局禁用，仅允许在函数局部作用域或 `.cpp` 内使用 `using std::xxx;`

### CTR：容器与字符串

- **CTR-001**：动态数组 `std::vector`；无序键值 `std::unordered_map`；字符串 `std::string` / `string_view` 禁止 `char*`
  > 容器插入优先 `emplace_back` / `emplace` 原位构造，避免临时对象拷贝。

### MAGIC：魔法数字

- **MAGIC-001**：所有字面值必须是命名常量或枚举，禁止硬编码魔法数字

### INIT：初始化

- **INIT-001**：禁止全局裸变量/全局静态对象（规避静态初始化顺序问题）

### BUILD：编译

- **BUILD-001**：编译启用 `-Werror`，所有警告清零；合理使用 `constexpr` 将常量/计算下沉至编译期

---

## Warning 检查清单

### LOG：日志体系

- **LOG-001**：`LogLevel` 枚举（`Trace` / `Debug` / `Info` / `Warn` / `Error` / `Fatal` 六级）和 `LoggerCallback` 统一定义在单一中心位置，禁止自定义等级
- **LOG-002**：日志回调参数用 `std::string_view` 而非 `std::string`，减少拷贝
- **LOG-003**：基类应接受或可注入统一日志回调；内置空回调兜底防空指针崩溃；外部实现需自行保证线程安全

### PERF：性能

- **PERF-001**：只读成员函数必须标记 `const`
- **PERF-002**：优先 `emplace` / `emplace_back` 而非 `push_back`
- **PERF-003**：不继承的类、不重写的虚函数标记 `final`
- **PERF-004**：`#include` 分 5 组排序（对应头文件 → C 标准库 → C++ 标准库 → 第三方库 → 项目内部），组间空行

---

## 审查输出格式

```
## C++ 规范审查

### Blocker 检查
- [x] MEM：内存与指针 —— 通过
- [x] NAME：命名规范 —— 通过
- [ ] OOP：类设计 —— OOP-001：基类 `Parser` 有虚函数但析构函数非虚
- ...

### Warning 检查
- [x] LOG：日志 —— 通过
- [ ] PERF：性能 —— PERF-001：`getValue()` 未标记 const
- ...

### 总结
- Blocker：1 项违规（OOP-001）—— 必须修复
- Warning：1 项建议（PERF-001）
```

## 豁免

- 与 C 遗留库交互时，裸指针（MEM-003）和 C 风格强转（BAN-002）可例外，需在使用处注释说明 C 互操作需求及风险评估。
- 其余规则无一例外。
