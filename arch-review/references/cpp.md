# C++ 架构审查参考（arch-review / references）

> 由 arch-review 在识别为 C++（`.h/.hpp/.cpp/.cc/.cxx` 或存在 CMakeLists.txt/Makefile）时加载。
> 通用 ARCH 规则见 `arch-review/SKILL.md`；本文提供**证据采集方式**与 C++ 专属规则。

## 一、证据采集

### 1.1 依赖图（首选构建产物，源码推导为兜底）

1. **CMake target 图**：`cmake --graphviz=targets.dot <build-dir>`，或读 `build/CMakeFiles/TargetDirectories.txt`、`link.txt` 中的库依赖。
2. **include 图**：从源码提取 `#include "..."`（仅项目内头文件）构建有向图；用 DFS/Tarjan 检测强连通分量。
3. **target 级环**：检查 `CMakeLists.txt` / `Makefile` 的 `target_link_libraries` 是否成环。注意 `PUBLIC` 依赖会传递，`PRIVATE` / `INTERFACE` 不会——判环时按可见性展开。
4. **构建产物反查**：`build/<config>/` 下的库/可执行文件与 target 清单做双向差集，可发现"声明了但没进构建"的模块。

> ⚠️ **多配置生成器**下各配置产物目录内容不同且新旧不一，先确认当前构建的 config，否则会大面积误判。
> ⚠️ **`ctest -N` 必须在构建目录执行**，在仓库根执行可能静默返回 0 条（见 `test-review` EXEC 组的同类实测）。

### 1.2 模块边界

首选 CMake target；无 target 划分时用顶层目录；命名空间仅作辅助。报告中声明口径。

## 二、C++ 专属规则

### ARCH-005 补充：头文件包含环

源文件按约定不被 `#include`，循环包含实际发生在**头文件之间**。用前向声明 + 指针/引用成员打破；PIMPL 用于彻底隐藏实现依赖。

### ARCH-017 补充：静态初始化顺序（SIOF）

不同编译单元之间的全局/静态对象互相引用属于 critical——初始化顺序跨 TU 未定义。`constexpr` 常量初始化（无动态初始化）不受影响。

### ARCH-018：构建链接可见性

- **ARCH-018**（minor）：`target_link_libraries` 的 `PUBLIC` / `PRIVATE` / `INTERFACE` 使用是否合理：
  - 内部依赖用 `PRIVATE` 却标成 `PUBLIC` → 污染下游包含路径与链接面；
  - 接口必需的依赖标成 `PRIVATE` → 下游链接失败或隐式依赖。

### ARCH-019：纯头文件库

- **ARCH-019**（minor）：header-only 库应有明确理由（模板库、单头工具）；无理由的大型 header-only 库会放大编译时间与二进制膨胀。

### ARCH-020…023：API/ABI 兼容性

> 仅适用于对外发布共享库（.so/.dll）或公开 API 的项目；纯内部单体应用跳过本组。ABI 精确差异建议搭配 `abidiff`（libabigail），本组是源码级**启发式**检查。

- **ARCH-020**（major）：公开头文件的函数签名变更（返回类型、参数增删、默认参数值）必须评估向后兼容并记录；首选「新增重载 + 保留旧签名」。
  > **增默认参数仅源码级兼容**：对已发布共享库是 ABI 破坏（mangled name 改变、旧符号消失），必须与「新增重载」区分。
- **ARCH-021**（critical）：已发布类中新增虚函数（vtable 布局）、重排成员变量（内存布局）、修改内联函数体（调用方可能已内联旧版本）。
- **ARCH-022**（major）：对外二进制库必须显式控制符号导出——Windows `__declspec(dllexport/dllimport)`，Linux/macOS `__attribute__((visibility("default")))` + 默认隐藏。禁止默认全导出（放大攻击面与 ABI 约束面）；同时检查该导出的公开 API 是否遗漏。
- **ARCH-023**（minor）：对外发布 SDK 建议规划版本化接口（`inline namespace v1`/`v2`、版本化头文件目录），使不同版本可并存。

## 三、C++ 场景下的证据注意事项

- 纯头文件库（如 Catch2、nlohmann/json）依赖分析时易把 `detail/` 内部头算成公开接口——按 ARCH-007 判定前先确认该头是否被安装/导出。
- `include/` 与 `src/` 分离的项目：模块边界以 target 为准；目录镜像差异按 ARCH-011 记为 minor，不据此判分层倒置。
- 宏、模板实例化、`extern "C"` 边界都会让静态 include 图偏离真实依赖（模板在头文件中实例化 → 依赖集中在头文件），报告中须注明依赖图的推导局限。
