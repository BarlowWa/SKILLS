# Python 架构审查参考（arch-review / references）

> 由 arch-review 在识别为 Python（`.py` / `.pyi`，或存在 `pyproject.toml` / `setup.py` / `setup.cfg` 且含 Python 源码）时加载。
> 通用 ARCH 规则见 `arch-review/SKILL.md`；本文提供 **Python 的证据采集方式**与 Python 专属规则。模块口径见 SKILL.md『模块定义』：首选发行包（pyproject 的 packages），次选顶层目录。
> 结论标注：`实测` = 本机 Python 3.14.6 + httpx 样本（`encode/httpx`，浅克隆）；`文档` = 官方文档；`核对` = 按本机工具链版本核对。样本未触达的条目在 SKILL.md 状态表单列。

## 一、证据采集

### 1.1 打包事实（模块口径与发布面）

1. **构建后端**：读 `pyproject.toml` 的 `[build-system]`（`setuptools` / `hatchling` / `flit_core` / `poetry-core` / `pdm-backend`）与 `[tool.*]` 的包发现配置。模块口径优先取构建配置实际打包的顶层包，不是目录树里的所有目录。
2. **布局**：`src/` 布局（`src/<pkg>/`）与 flat 布局（`<pkg>/` 直接在仓库根）都合法。**flat 布局本身不是缺陷**；只有出现「从仓库根导入的是未安装的源码、遮蔽了已安装版本」或「测试依赖 CWD 而非可安装产物」时才按 ARCH-PY-001 判。
3. **发布元数据**：`requires-python`、`dependencies`、`[project.optional-dependencies]`（extras）、`[project.scripts]` / `entry-points`、`py.typed`。`pyproject.toml` 是主证据；`setup.py` / `setup.cfg` 仅在项目未迁移时作为补充，两者冲突以实际构建后端读取的配置为准。
4. **实测样本**：httpx 用 hatchling，flat 布局（`httpx/`），`requires-python = ">=3.10"`，核心依赖 `certifi/httpcore/anyio/idna`，extras 为 `brotli/cli/http2/socks/zstd`，`[project.scripts] httpx = "httpx:main"`，`httpx/py.typed` 存在。

### 1.2 依赖清单

1. **声明面**：`pyproject.toml` 的 `dependencies` / `optional-dependencies`；这是发布契约，优先于任何本地环境。
2. **安装面**：`importlib.metadata.requires("<dist>")`（已安装时）或 `pip show <dist>`；能反映 extras 与 marker（如 `platform_python_implementation`）。
3. **锁文件**：`poetry.lock` / `uv.lock` / `Pipfile.lock` / `pdm.lock`。**应用**需要锁文件保证可复现；**库**通常只声明兼容范围、不锁死运行时依赖——不要因「库没有锁文件」直接判缺陷。
4. **工具链**：`requirements.txt` 常只用于开发/CI 工具 pin（httpx 的 requirements 只 pin pytest/ruff/mypy 等），不等于运行时依赖清单。

### 1.3 模块依赖图（AST）

标准库即可完成一次可用的静态依赖图：

1. 递归扫描包内 `*.py`，把文件映射为模块名（`pkg/sub/mod.py` → `pkg.sub.mod`，`__init__.py` → 包名）。
2. 解析 `ast.Import` / `ast.ImportFrom`：
   - 绝对导入：`import pkg.sub` / `from pkg.sub import X` → 目标模块 `pkg.sub`；
   - 相对导入：按当前模块所在的包与 `node.level` 上溯，拼出目标模块；
   - 只保留解析到包内已有模块的边，外部包/标准库另列。
3. **盲区必须声明**：`importlib.import_module(字符串)`、`__import__`、条件导入、`try/except ImportError`、类型检查专用导入、插件/entry point 动态加载，静态扫描都看不到；报告中写「源码推导，未覆盖动态导入」。
4. 可选第三方工具：`grimp` / `pydeps` / `import-linter`（本文未安装，引用其输出须注明工具与版本）。用它们时同样要说明对动态导入的覆盖范围。
5. **实测样本**：httpx 包内 23 个模块。按**模块顶层、不含 `TYPE_CHECKING` 与函数内延迟导入**的 import-time 边为 80 条、**无 SCC**；把 `TYPE_CHECKING` 边也算入为 87 条、2 个 SCC（11 与 6）；把函数内延迟导入也算入为 81 条、1 个 SCC（`_urls ↔ _utils`）。同一份源码的图会随口径变化，报告必须声明「是否计入 TYPE_CHECKING/延迟导入」。

### 1.4 循环依赖与公开面

1. **成环检测**：对模块图做强连通分量（Tarjan/DFS）。报告每个 SCC 的成员、入度/出度，并**实际执行一次 `import <top_package>`** 区分「导入即失败」与「导入成功但初始化顺序脆弱」。
2. **公开面**：读顶层包 `__init__.py` 的 `__all__` 与重导出（`from .x import *` / `from .x import Y`）；用 `vars(pkg)` 与 `__all__` 对账。`__all__` 是**声明**，实际公开面还包含未列入 `__all__` 的公有名字（`from pkg import X` 仍可用）。
3. **入口点**：`[project.scripts]` / `[project.entry-points]`、`__main__.py`、`python -m pkg` 的行为。入口点调用的 `main()` 属于公开面的一部分。
4. **实测样本**：httpx `__all__` 70 项，`tests/test_exported_members.py` 断言 `__all__` 与模块非私有成员一致；import-time 图无 SCC。把 `TYPE_CHECKING` 边算入才出现 2 个 SCC（11 与 6）——`_transports/default.py` 的 `if typing.TYPE_CHECKING: import httpx` 与 `_utils` 的 `if typing.TYPE_CHECKING: from ._urls import URL` 都是类型检查边。`import httpx` 成功，不能把这类 SCC 当成运行时环。

## 二、Python 专属规则

### ARCH-PY-001：布局与可导入性（major）

`src/` 与 flat 布局都可接受；判据是**导入来源是否唯一且与发布产物一致**。以下形态按 major 记：
- 仓库根存在与已安装包同名的顶层目录，开发/CI 在不同 CWD 下导入到不同副本（`python -c "import pkg; print(pkg.__file__)"` 落在仓库根而不是 site-packages）；
- 测试或脚本通过 `sys.path.insert` / `sys.path.append`「找到」包，安装后该路径不存在；
- 打包配置发现多个意料之外的同名顶层包（`packages = find:` 的宽匹配）。
**证据**：`python -c "import pkg; print(pkg.__file__)"`、`pip show -f <dist>`、构建配置的 `packages` / `include`。
**边界**：flat 布局的单包项目（httpx 即此形态）不判；可编辑安装（`pip install -e .`）出现的仓库路径导入属正常开发形态。

### ARCH-PY-002：可选依赖与 extras 隔离（major；核心导入失败 critical）

extras（`[project.optional-dependencies]`）里的依赖不得成为核心模块导入的硬前提。核心 `import pkg` 在未安装任何 extras 时必须成功；需要 extras 的功能在模块内延迟导入、明确报错或在入口层隔离。
**证据**：在干净 venv 中 `pip install <dist>`（不带 extras）后 `python -c "import pkg"`；读 `try/except ImportError` 与函数内延迟导入；核对 extras 声明与代码实际引用。
**判级**：核心导入因缺 extras 失败 → critical；仅可选功能在调用时失败且报错清晰 → major；有清晰的 `pip install pkg[extra]` 提示 → minor。
**实测样本**：httpx 的 `__init__.py` 在 `try/except ImportError` 中导入 `_main`（依赖 `click/rich/pygments` 的 CLI extras），缺失时回退为一个打印安装提示的 `main`；核心导入正常。

### ARCH-PY-003：循环导入（critical / major / 不判）

**判级必须结合「导入期是否失败」与「延迟导入是否有理由」**：
- `import <top>` 即抛 `ImportError` / `AttributeError`（部分初始化的模块被使用）→ **critical**；
- 导入成功、但环内模块依赖初始化顺序（换入口、换 Python 版本、改导入顺序即可能失败）→ **major**；
- 纯 `if TYPE_CHECKING:` 的类型导入 → **不判**（运行期不存在该边）；
- 函数内延迟导入且紧邻注释说明为打破循环/隔离可选依赖 → **minor**（可以接受，记录技术债）；
- 函数内延迟导入但无理由/注释 → **major**（隐藏依赖关系）。
**证据**：SCC 列表 + 实际导入执行 + 逐条读延迟导入的注释；不要只凭 AST 图报 critical。
**实测样本**：httpx 按 import-time 边无 SCC；把 `TYPE_CHECKING` 边算入才有 11 模块与 6 模块两个 SCC（`_transports/default.py` 的 `import httpx`、`_utils` 的 `from ._urls import URL` 均在 `if typing.TYPE_CHECKING` 内），按本条「纯 TYPE_CHECKING 导入不判」处理。另有一条无注释的函数内延迟导入（`_utils.py:163` 的 `from ._urls import URL`），与 `_urls -> _utils` 的顶层边构成 2 模块环，按「无理由的函数内延迟导入 → major」记录技术债；它不是 import-time 失败。

### ARCH-PY-004：包 `__init__` 重导出与公开面（minor；膨胀 major）

顶层 `__init__.py` 应表达**有意的公开面**：显式 `__all__`、受控重导出、不把内部模块名无意暴露。以下形态按 major 记：
- 无 `__all__` 的大量 `from ._internal import *`，公开面随内部重构漂移；
- 重导出把实现细节类型（内部 `_xxx` 模块、第三方具象类型）带进公开面；
- `__all__` 与 `vars(pkg)` 的公有名字不一致，且无测试对账。
**证据**：读 `__init__.py`；`python -c "import pkg; print(pkg.__all__)"`；对账测试（如 httpx 的 `tests/test_exported_members.py`）。
**边界**：有显式 `__all__` 且由测试核对的通配重导出是**受控形态**，不判（httpx 70 项 `__all__` + 对账测试）。

### ARCH-PY-005：跨模块 import 期副作用与全局状态（major；初始化顺序 critical）

模块顶层执行网络/磁盘 I/O、连接池创建、线程/进程启动、`logging.basicConfig()`、读环境变量写全局配置，或暴露可变单例并被多个模块依赖，属于跨模块架构问题。
**证据**：扫描各模块顶层语句（非 `def`/`class`/常量赋值）；查找模块级可变全局与 `global` 使用；`grep -rn "basicConfig\|global "`。
**判级**：模块间初始化顺序依赖且无显式顺序保证 → critical；跨模块共享可变全局 → major；仅单模块顶层副作用（如一个模块在导入时读配置）→ 交 `code-rules` PY-IMPORT-002，不在此重复。
**边界**：`logging.getLogger(__name__)` 是模块级 logger 的惯用写法，不判；不可变常量表不判。

### ARCH-PY-006：分层与框架耦合（major）

领域/业务模块不得直接依赖 Web 框架、ORM、CLI、序列化库的具象类型；第三方能力应经适配层收口（ARCH-003 在 Python 的落地）。
**证据**：`from django.* import` / `from flask.* import` / `from sqlalchemy.* import` 在 domain 模块的命中；`conftest.py` 与测试目录不参与产品分层。
**边界**：应用层（`views/`、`handlers/`、`cli/`）直接使用框架是正当的；单包库（如 httpx）没有显式分层时按单层处理，跳过本条的「跨层」判定，但「可选依赖隔离」仍按 ARCH-PY-002 查。

### ARCH-PY-007：命名空间包 / split package / 同名顶层包（major）

两个发行包提供同一个顶层包名（split package）时，安装顺序决定谁覆盖谁；隐式命名空间包（PEP 420，无 `__init__.py`）是合法的分发模式，但同一命名空间下的子包版本不一致会导致导入结果随环境漂移。
**证据**：`pip show -f` 的顶层包清单；`importlib.util.find_spec(pkg).submodule_search_locations`；构建配置的 `packages`；`find <site-packages> -maxdepth 1 -name '<pkg>*'`。
**判级**：同名顶层包被两个分发提供 → major；命名空间包子包版本/来源不一致 → major；单发行包单顶层包 → 不判。
**实测样本**：httpx 为单个常规包，未触达本条的 split/namespace 形态。

### ARCH-PY-008：入口点与 `__main__` 的组织（minor）

`[project.scripts]` / `[project.entry-points]` 与 `__main__.py` 应指向稳定的公开入口；入口函数不得在导入时执行主流程（`if __name__ == "__main__"` 守卫，或把主流程放在 `main()` 内）。多个入口共享逻辑时抽公共函数，不要在入口脚本里复制业务逻辑。
**证据**：`pyproject.toml` 的入口点；`python -m pkg --help`；读入口模块的顶层语句。
**实测样本**：httpx 用 `httpx = "httpx:main"`，`httpx/__init__.py` 暴露 `main`；未使用 `__main__.py`。

### ARCH-PY-009：依赖声明与可复现性（major；仅本地开发 minor）

**应用**（服务/CLI）必须有可复现的依赖锁定；**库**必须有准确的 `requires-python`、运行时依赖与 extras 声明，不把开发工具混进运行时依赖。判据：
- 应用无锁文件、依赖只有宽范围 → major（构建不可复现）；
- 库把测试/构建工具写进 `dependencies`（而非 dev/test extras）→ major；
- `requires-python` 与代码实际使用的语法/标准库 API 不一致（如用 3.10 的 `X | Y` 却声明 `>=3.8`）→ major；
- 仅本地开发脚本缺锁 → minor。
**证据**：`pyproject.toml`、锁文件、`importlib.metadata.requires`、CI 安装命令。
**边界**：库不锁运行时依赖是正常做法，不判；httpx 的 `requirements.txt` 只 pin 工具链，运行时依赖在 `pyproject.toml` 用兼容范围，符合库的发布形态。

### ARCH-PY-010：公开 API 兼容性与弃用（minor；无告警的破坏性变更 major）

公开名字的删除/重命名、必填参数新增、关键字参数语义变化、异常类型变化属于破坏性变更；库应在弃用期发 `DeprecationWarning`（或 `typing_extensions.deprecated`，按版本核对），并在 CHANGELOG 说明。
**证据**：`__all__` / 公开签名（`inspect.signature`）跨版本对比；`warnings.warn(..., DeprecationWarning)` 的使用；`git diff` 公开模块。
**判级**：无弃用告警直接移除/改签名 → major；有弃用期与迁移说明 → minor/记录。
**边界**：`_private` 名字、`__all__` 之外的内部实现不在兼容面；单仓库内部包无外部消费者时按 minor。

### ARCH-PY-011：类型发布面（minor；公开 API 全面无类型 major）

带类型注解的库必须发布 `py.typed`（PEP 561），否则消费者的 mypy 会静默忽略库内注解；`py.typed` 与公开注解、stub（`.pyi`）应一致。
**证据**：包内是否存在 `py.typed`；`[tool.mypy]` 配置；构建产物是否包含该文件（`pip show -f`）；在干净消费者项目中 `mypy` 对 `import pkg` 的解析结果。
**判级**：有注解但缺 `py.typed` → minor；公开 API 全面无注解且无 stub → major；`py.typed` 存在但注解大量 `Any` → minor。
**实测样本**：httpx 有 `py.typed`，`mypy strict = true` 配置生效；mypy 2.4.1 在**未装 `zstandard`** 的样本环境报 2 处 `unused-ignore`（`_decoders.py:33`、`_content.py:127`），装 `zstandard` 后只报 1 处（`_content.py:127`）——数字随可选依赖是否安装变化，引用时须写明环境。**消费者侧 mypy 核对未在本轮执行**，按「文档/核对」记录，SKILL.md 状态表单列。

## 三、先看这些再判级（Python 证据注意事项）

- **AST 依赖图有盲区**：动态 `importlib.import_module`、`__import__`、条件导入、插件/entry point 都不可见；报告必须写「源码推导，未覆盖动态导入」，不能把「图里没边」当成「没有依赖」。
- **能导入 ≠ 没有环**：Python 的部分初始化允许很多环「看起来正常」，但在不同入口、不同 Python 版本或调整导入顺序时会失败；按 ARCH-PY-003 的 major 记录，不要因为 `import` 成功就判没环。
- **`__all__` 不是访问控制**：它只影响 `from pkg import *`；未列入的公有名字仍可直接导入。公开面判定要同时看 `__all__` 与模块命名约定。
- **flat 布局不是缺陷**：只有导入来源不唯一/依赖 CWD 时才是 ARCH-PY-001；不要拿 `src/` 布局当唯一正确形态。
- **库没有锁文件不是缺陷**：区分应用与库；库的 `requires-python` / 依赖范围 / extras 才是发布契约。
- **extras 的 `try/except ImportError` 是隔离手段，不是吞异常**：只要核心路径可用、错误信息指向安装 extras，就按 ARCH-PY-002 的正当形态处理。
- **Windows 路径与编码**：路径/编码证据在 Windows 与 Linux 上可能不同（`os.path.join` 的绝对路径覆盖、locale 编码 `cp936`）；跨平台项目须分别核对，不要把某一平台的通过当全平台证据。
- **`py.typed` 的消费者证据**：仅看到文件存在不等于消费者 mypy 真的启用了它；需要「安装后由外部项目 import」的核对，缺此证据时记「未能判定」。

## 四、与其他技能协同

- `code-rules`（PY-*）负责**单模块内**的 import 形态、单模块顶层副作用、单文件类型注解、路径安全与安全写法；本技能负责**模块/包级**的依赖图、循环、公开面、extras/分层/入口点。
- **循环导入**只由本技能 ARCH-PY-003 判；`code-rules` 不设循环导入条目（其 PY-IMPORT-003 只判函数内延迟导入的写法与注释）。
- **import 期副作用**：单模块顶层副作用归 `code-rules` PY-IMPORT-002；跨模块全局状态/初始化顺序归本技能 ARCH-PY-005。
- **公开面**：单模块注解/命名归 `code-rules` TYPE/NAME；包级 `__all__`/重导出归 ARCH-PY-004；`py.typed`/类型发布面归 ARCH-PY-011；入口点归 ARCH-PY-008。
- **依赖/构建**：单包 pyproject 正确性归 `code-rules` PY-BUILD-001/002；extras 隔离与可复现依赖面归 ARCH-PY-002/009。
- `test-author` / `test-review`：测试目录按 SKILL.md『注意事项』放宽；测试设计/质量归对应技能，本技能不审查测试代码。
