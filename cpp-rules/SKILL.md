---
name: cpp-rules
description: 在编写、编辑、审查或重构 C++ 代码（.h、.hpp、.cpp、.cc、.cxx、.hh、.hxx、.ipp、.inl、.tpp 文件）时使用。提供强制性编码规范，涵盖内存管理、安全、命名约定、OOP 设计、跨平台兼容性、头文件、多线程、现代 C++ 惯用法、代码复杂度、日志及禁用模式。当用户创建、修改或要求审查 C++ 源文件时激活。测试文件（tests/、*_test.*、*_unittest.*）不适用本技能，由 cpp-test-author / cpp-test-review 负责。
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
  > 裸 `new`/`delete` 需要手动配对，异常路径或提前 return 下极易漏配对导致泄漏/双重释放；`make_unique`/`make_shared`/容器在 RAII 下自动平衡。
- **MEM-003**：裸指针 `T*` 仅限非拥有型观测，所有权归智能指针
  > **非拥有型观测**：仅借用作读/写窗口，不管理 pointee 生命周期、不参与释放。裸指针不管理对象生命周期；所有权场景必须使用 `std::unique_ptr` / `std::shared_ptr` / `std::weak_ptr`。C 互操作例外见『豁免』章节。
- **MEM-004**：禁止函数返回裸指针 `T*` 作为结果——拥有型返回用 `std::unique_ptr` / `std::shared_ptr` / `std::optional`；非拥有非空返回用 `T&`；可空非拥有返回用 `std::optional<T*>`（C++17/20）或 `std::span<T>`（C++20+）；确需返回 `T*` 时必须注释说明生命周期归属（静态存储 / 成员 / 调用方传入缓冲）
  > 返回裸指针让调用者无法从签名判断结果是否悬垂，是 use-after-free 的主要来源；虚函数 override 必须遵守与基类相同的返回契约。C++17 项目无 `std::span`，非拥有序列返回回退 `const std::vector<T>&` / `std::string_view`。C 互操作例外见『豁免』章节。
- **MEM-005**：可空性编码进类型——不可空的观测参数用 `T&`（只读用 `const T&`，见 CONST-001），仅可空时才用 `T*`
  > 用 `T*` 表达不可空引用会导致空检查失效或被盲目加判，漏判 null 是高频 bug 源。
- **MEM-006**：类成员用裸指针 `T*` 作非拥有型观测时必须注释并指名生命周期所有者（持有 pointee 的具体对象/容器/智能指针），禁止指向可能先于宿主析构的临时对象
  > 不能指名所有者的裸指针成员是悬垂高发区，要求与 MODERN-001 的 `string_view` 生命周期约束一脉相承。

### NAME：命名规范

- **NAME-001**：成员 `m_`、静态 `s_`、全局 `g_`、编译期常量 `k` 前缀（枚举常量除外，见 NAME-003）；POD 结构体不加前缀
- **NAME-002**：标识符禁止以下划线开头或结尾
- **NAME-003**：函数 `camelCase`；类/结构体/枚举 `PascalCase`；宏/枚举常量 `UPPER_SNAKE_CASE`
  > 枚举常量（enumerator）本身就是编译期常量，走 `UPPER_SNAKE_CASE`，不叠加 `k` 前缀，避免与 NAME-001 的"编译期常量 k 前缀"判定冲突。
- **NAME-004**：纯虚抽象基类以 `I` 前缀命名（如 `IWorker`、`ILogSink`）
- **NAME-005**：模板参数命名 PascalCase，与普通类型可区分——类型参数用描述性名称（`Key`、`Value`、`Predicate`），非类型参数用短名（`N`、`Size`），避免单字母 `T`/`U` 在非泛型含义的模板中滥用

### PLAT：跨平台与第三方依赖

- **PLAT-001**：平台 API 必须隔离在 `Platform` 抽象层后，业务代码不得直接调用 OS 专有 API 或系统头文件
- **PLAT-002**：跨平台需定长语义时使用 `<cstdint>` 定长类型（`int32_t` / `uint64_t` 等）；禁止 `long`（Windows 32 位 / Linux 64 位位宽不一致）。`int` 用于索引、计数等通用场景可接受
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
- **HEADER-002**：头文件仅放声明，实现放 `.cpp`（模板、`inline`、`constexpr` 等必须放头文件定义的类型除外）；头文件作用域禁止 `using namespace` 与 `using std::xxx;` 声明。`using Foo = Bar;` 类型别名不受此限
- **HEADER-003**：头文件公开 API/类/枚举必须有 `/** @brief ... */` Doxygen，按需 `@param`、`@return`、`@note`；`.cpp` 实现文件仅用 `//` 行注释

### THREAD：多线程与 Lambda

- **THREAD-001**：Lambda 捕获必须显式书写，禁止 `[=]` / `[&]` 全隐式默认捕获（`[&]` 有引用悬垂风险，`[=]` 有隐式 `this` 悬垂风险）
- **THREAD-002**：线程创建统一用 `std::thread`，禁止 OS 原生线程 API
- **THREAD-003**：共享成员变量读写必须通过 `std::mutex` / `std::shared_mutex` 加锁保护；简单数值可用 `std::atomic` 替代
- **THREAD-004**：条件变量 `wait` 必须在 `while` 循环中检查条件，**禁止 `if`**——`if` 无法防御虚假唤醒（spurious wakeup），导致间歇性错误唤醒后继续执行
  > `cv.wait(lk, [&]{ return condition; });` 是等价的安全写法，等效于 while 循环 + 谓词。
- **THREAD-005**：多锁场景必须使用 `std::scoped_lock`（C++17）或 `std::lock` 同时获取多把锁以确保全局锁序一致，禁止分散 `lock_guard` 逐个加锁
  > 分散逐个 `lock_guard` 在不同线程的加锁顺序不一致时直接导致死锁。
- **THREAD-006**：`std::async` 调用必须显式指定 `std::launch` 策略（`async` / `deferred` / 两者），`std::future` 析构前必须调用 `get()` 或 `wait()` 确保任务完成
  > `std::async` 返回的 `std::future` 析构时会阻塞等待——这是 C++ 最反直觉的设计陷阱之一；未显式指定 launch 时行为不可预测。

### BAN：强制禁止项

- **BAN-001**：禁止 `goto`，分支跳转用状态机重构
- **BAN-002**：禁止 C 风格强转 `(Type)var`，用 `static_cast` / `const_cast` / `reinterpret_cast`（后者严格管控）
- **BAN-003**：禁止 `NULL` / `0` 表空指针，统一 `nullptr`
- **BAN-004**：业务接口禁止 `va_list` / `va_arg`，用 `std::format` / 模板参数包替代
- **BAN-005**：禁止函数式宏，常量用 `constexpr`，工具函数用 `inline` / 模板
- **BAN-006**：业务接口禁止 `void*`——内存原始操作使用 `std::byte*`；闭合类型集用 `std::variant`，开放类型集才谨慎用 `std::any`；模板参数为首选
  > `void*` 抹掉全部类型信息，绕过编译期检查；`std::byte*` 才是裸内存操作的正确类型。C 互操作例外见『豁免』章节。
- **BAN-007**：业务接口禁止多级指针 `T**` / `T***`——用 `std::span<T*>` / `std::vector<T*>` / 引用 / `std::optional<T*>` 替代
  > 多级指针用于 out-param 与二维数组，可空性与所有权含糊，是业务接口中高频 bug 源。

### SEC-A：内存安全

- **SEC-A001**：禁止不安全的 C 字符串函数——`strcpy` / `strcat` / `sprintf` / `gets` / `scanf` 系列。统一使用安全替代：`snprintf` 或直接使用 `std::string` / `std::format`
  > 缓冲区溢出是 CWE Top 1，此类函数无法限制目标缓冲区长度，是最高频安全漏洞来源。注意：`strcpy_s` / `strcat_s` 属 C11 Annex K 可选项、实际为 MSVC 专属，Linux/GCC 不提供，故不作为跨平台推荐。
- **SEC-A002**：数组/容器访问优先使用 `.at()`（带边界检查抛异常），使用 `operator[]` 时必须有前置边界验证（如 `if (index < vec.size())`）或通过上下文可证明索引安全
  > 越界访问在安全审计中占比极高，`.at()` 将未定义行为转为可捕获异常。
- **SEC-A003**：禁止 `alloca` / `_alloca` / VLA（变长数组）——栈空间不可控，恶意输入可导致栈溢出。用 `std::vector` 或 `std::make_unique<T[]>` 替代

### SEC-B：类型安全

- **SEC-B001**：禁止在数组索引、内存大小计算（如 `new[]` 参数）、循环边界条件中混合有符号/无符号整数运算；必须显式转换并验证非负
  > 有符号与无符号混合运算时，负数会被隐式转换为巨大正数，导致缓冲区溢出或死循环。
- **SEC-B002**：禁止对 `const` 对象使用 `std::move`——不会触发移动语义（实际调用拷贝构造/赋值），属于无效且有欺骗性的代码
  > `const T&&` 无法绑定到 `T&&` 移动构造函数，退化为 `const T&` 拷贝。
- **SEC-B003**：`reinterpret_cast` 使用处必须附带注释说明转换目的、安全保证及替代方案为何不可行。本条落实 BAN-002 中"严格管控"的要求

### SEC-C：输入安全

- **SEC-C001**：禁止格式化字符串来自用户输入或外部可控数据
  > `printf(userInput)` 或 `fprintf(fp, externalStr)` 是经典格式化字符串漏洞，可导致任意内存读写。仅允许 `printf("%s", userInput)` 形式。
- **SEC-C002**：禁止 `system()` / `popen()` / `exec*()` 系列函数接收外部可控字符串——命令注入风险。若必须调用外部命令，使用参数列表形式（如 `execv`）并白名单校验可执行文件路径
- **SEC-C003**：禁止密码、API 密钥、Token、私钥等敏感信息以明文字符串字面量写入源代码。使用环境变量、配置文件（不进入版本控制）或密钥管理服务

### ERR：错误处理与异常

- **ERR-001**：底层/工具类返回 `std::error_code`；业务逻辑可抛自定义异常；禁止无信息裸 `throw;`（`throw;` 重抛合法）
  > 自定义异常类必须携带完整描述信息。
- **ERR-002**：析构函数、移动构造/赋值、确定不抛异常的函数必须 `noexcept`
- **ERR-003**：所有资源（内存、文件句柄、锁、socket、数据库连接等）必须 RAII 自动释放，禁止依赖手写 `close`/`free`/`unlock` 配对
  > 判据：资源的获取与释放须绑定到同一对象生命周期（构造获取、析构释放）；任何在异常或提前 return 路径下可能漏释放的裸资源管理均属违规。

### CONST：常量、传参与类型转换

- **CONST-001**：大型只读参数用 `const&` / `string_view`；禁止按值传大对象
- **CONST-002**：`auto` 仅用于复杂模板/迭代器/`make_*` 返回值，基础类型不用
- **CONST-003**：优先范围 `for` 而非下标迭代

### NS：命名空间

- **NS-001**：所有业务代码归属项目顶层命名空间；`using namespace std` 全局禁用，仅允许在函数局部作用域或 `.cpp` 内使用 `using std::xxx;`

### CTR：容器与字符串

- **CTR-001**：动态数组 `std::vector`；无序键值 `std::unordered_map`；字符串 `std::string` / `string_view` 禁止 `char*`

### MAGIC：魔法数字

- **MAGIC-001**：禁止硬编码魔法数字——有业务/领域语义的字面值必须是命名常量或枚举。`0` / `1` / `-1` / `nullptr` / `true` / `false` / 空串及上下文自明的惯用值（如 `return 0;`、`for (int i = 0; ...)`、`x == 1`）不视为魔法数字

### INIT：初始化

- **INIT-001**：禁止全局裸变量/全局静态对象（规避静态初始化顺序问题）；`constexpr` 全局常量（常量初始化、无 SIOF 风险）不受此限

### BUILD：编译

- **BUILD-001**：编译启用 `-Werror`，所有警告清零；合理使用 `constexpr` 将常量/计算下沉至编译期

### MODERN：现代 C++ 惯用法

- **MODERN-001**：`std::string_view` 禁止绑定到已析构的临时 `std::string` 或超出生命周期的局部对象；禁止从函数返回指向局部变量的 `string_view`；跨函数传递时必须明确底层所有者的生命周期
  > `string_view` 是非拥有型引用，引用对象析构后继续使用会导致 use-after-free。常见陷阱：`return s + suffix;` 返回 `string_view`（临时 `std::string` 被析构）。

### TPL：模板与泛型

> 以下规则按 C++ 版本条件适用。标注"C++20 项目"的规则对 C++17 及以下项目不强制。

- **TPL-001**：每个约束模板的 `static_assert` 必须携带对使用者有意义的诊断消息，说明"什么条件未满足"和"应如何修复"——裸 `static_assert` 仅显示表达式文本，对调用者无帮助
  > `static_assert(std::is_integral_v<T>, "T must be an integral type, e.g., int, int64_t, or size_t");` 是合格的消息。
- **TPL-002**：C++20 项目禁止使用 `std::enable_if` / `std::void_t` / tag dispatch 做模板约束，统一使用 `requires` clause 或 `concept`。C++17 项目不受此限
  > `requires` 和 `concept` 将约束从晦涩的模板错误消息中提升到接口声明层，大幅改善编译错误体验和代码可读性。
- **TPL-003**：模板特化（全特化/偏特化）与主模板应放在同一头文件中，特化后仍有独立 ODR 使用的场景需显式声明实例化点（`extern template`）防止隐式实例化膨胀

---

## Warning 检查清单

### LOG：日志体系

- **LOG-001**：`LogLevel` 枚举（`Trace` / `Debug` / `Info` / `Warn` / `Error` / `Fatal` 六级）和 `LoggerCallback` 统一定义在单一中心位置，禁止自定义等级
- **LOG-002**：日志回调参数用 `std::string_view` 而非 `std::string`，减少拷贝
- **LOG-003**：基类应接受或可注入统一日志回调；内置空回调兜底防空指针崩溃；外部实现需自行保证线程安全

### THREAD-W：多线程进阶（warning）

- **THREAD-007**：C++20 项目优先 `std::jthread` 替代 `std::thread`——`jthread` 析构时自动 join（防止 `std::terminate`），并支持 `stop_token` 协作式中断
- **THREAD-008**：`std::atomic` 非 `std::memory_order_seq_cst` 的内存序必须注释说明选择理由；默认 `seq_cst` 对绝大多数场景足够且正确
- **THREAD-009**：自建线程池/任务队列必须有明确的 shutdown 生命周期：析构函数等待所有已提交任务完成、拒绝新任务、正确 join 所有工作线程

### MODERN-W：现代 C++ 惯用法（warning）

- **MODERN-002**：优先 `std::optional` / `std::variant` / `std::expected`（C++23）替代哨兵值（`-1`/`nullptr`/空状态）和输出参数——类型系统直接编码"有/无"语义，消除遗漏检查的风险
- **MODERN-003**：C++20 项目优先使用 `std::span<T>` 替代 `T* + size_t` 参数对——`span` 自带边界信息，消除缓冲区越界这类 bug 的根源
  > `std::span` 同样是非拥有型观察视图，不管理底层数据生命周期。
- **MODERN-004**：优先使用 Ranges（`std::ranges::sort(v)`、`v | filter | transform`）替代原始迭代器对——意图表达更清晰，减少迭代器失效风险
- **MODERN-005**：编译期条件分支：C++17 优先使用 `if constexpr` 替代 SFINAE / `std::enable_if` / tag dispatch；C++20 优先使用 concepts 替代 SFINAE——代码更直观，错误消息更友好
- **MODERN-006**：禁止用指针算术推进迭代（`p += n` 循环、`ptr - q`）；取单元素地址 `&arr[i]` 合法。优先 `std::span` / 迭代器 / 范围 `for`（见 SEC-A002、CONST-003、MODERN-003）
- **MODERN-007**：智能指针 `.get()` 仅限 C 互操作或短暂借用，不得流入业务接口；禁止 `.release()`
  > `.release()` 把所有权直接转成裸指针，与 MEM-001/002 冲突；`.get()` 泄漏非拥有型裸指针，破坏生命周期契约。

### CPLX：代码复杂度与可维护性（warning）

> 本类别不替代 SonarQube / clang-tidy 等工具的定量指标检测，专注于工具难以完成的语义判断。

- **CPLX-001**：逻辑重复检测——识别不同位置（可能不同变量名/类型）但语义等价或高度相似的代码块，建议提取公共函数。工具只能检测文本重复，LLM 可发现结构性重复
- **CPLX-002**：参数簇识别——若一组参数（如 `x1, y1, x2, y2` 坐标、`host, port, timeout` 连接配置）在多个函数签名中成组出现，应封装为结构体，减少接口复杂度并降低传参顺序错误风险
- **CPLX-003**：函数职责单一性——识别"做了多件不相关事情"的函数（如一个函数内同时包含数据解析、业务计算和文件 I/O），建议拆分以提升可测试性
- **CPLX-004**：嵌套深度 >4 层时建议早返回（early return）或提取子函数重构——不机械报警（状态机等场景合理性由审查者判断），而是针对可简化场景提出具体重构建议

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
- [x] PLAT：跨平台 —— 通过
- [x] OOP：类设计 —— 通过
- [x] HEADER：头文件 —— 通过
- [x] THREAD：多线程 —— 通过
- [x] BAN：禁用项 —— 通过
- [x] SEC-A：内存安全 —— 通过
- [x] SEC-B：类型安全 —— 通过
- [x] SEC-C：输入安全 —— 通过
- [x] ERR：错误处理 —— 通过
- [x] CONST：常量/传参 —— 通过
- [x] NS：命名空间 —— 通过
- [x] CTR：容器/字符串 —— 通过
- [x] MAGIC：魔法数字 —— 通过
- [x] INIT：初始化 —— 通过
- [x] BUILD：编译 —— 通过
- [x] MODERN：现代 C++ —— 通过
- [x] TPL：模板与泛型 —— 通过
- [ ] <类别>：<问题> —— ...
- ...

### Warning 检查
- [x] LOG：日志 —— 通过
- [x] THREAD-W：多线程进阶 —— 通过
- [x] MODERN-W：现代 C++ 进阶 —— 通过
- [x] CPLX：代码复杂度 —— 通过
- [x] PERF：性能 —— 通过
- [ ] <类别>：<问题> —— ...
- ...

### 总结
- Blocker：1 项违规（OOP-001）—— 必须修复
- Warning：1 项建议（PERF-001）
```

## 豁免

- 与 C 遗留库交互时，裸指针（MEM-003）、返回裸指针（MEM-004）、观测参数裸指针（MEM-005）、`void*`（BAN-006）和 C 风格强转（BAN-002）可例外，需在使用处注释说明 C 互操作需求及风险评估。
- **测试文件不适用本技能**：测试代码（`tests/`、`*_test.*`、`*_unittest.*`）的用例设计使用 `cpp-test-author` 技能、质量审查使用 `cpp-test-review` 技能。测试文件中的 `new`（测试框架宏内部）、断言字面量、全局注册宏等在本技能规则下会误报，不应应用本技能的所有规则。
- 性能基准测试（`*_bench.cpp`、`bench/`）豁免本技能全部规则；对测试审查技能的豁免范围见 `cpp-test-review` 的豁免章节（以该技能的声明为准）。
- 其余规则无一例外。
