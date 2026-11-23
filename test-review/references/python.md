# Python 测试审查参考（test-review / references）

> 由 test-review 在测试文件为 Python（`test_*.py`、`*_test.py`、`tests/`、`conftest.py`）时加载。通用判据见 `test-review/SKILL.md`；本文提供 **pytest 执行证据的获取方式**、跳过/假绿形态词表，以及 Python 项目中最容易造成误判的陷阱。工具行为引自 pytest 9.2.0 实测或官方文档；无法取得运行证据时记「未能判定（缺运行证据）」。

## 一、执行证据获取（EXEC-001 / EXEC-002 / EXEC-006）

### 1.1 配置与收集范围（EXEC-001；ORG-001/002/003）

- **配置文件优先级**（pytest 9.2 源码 `_pytest/config/findpaths.py` 的 `CONFIG_LOADERS_BY_NAME`，实测）：`pytest.toml` > `.pytest.toml` > `pytest.ini` > `.pytest.ini` > `pyproject.toml` > `tox.ini` > `setup.cfg`。
  > 实测：同一目录同时放 `pytest.toml` / `pytest.ini` / `pyproject.toml`，分别带不同 `addopts`；依次隐藏 `pytest.toml`、`pytest.ini` 后，选中的集合从 `only_toml` → `only_ini` → `only_pyproject`。**旧版 pytest 可能不识别 `pytest.toml`**，以项目实际版本核对。
  > `pyproject.toml` 里是 `[tool.pytest.ini_options]`；`pytest.toml` / `.pytest.toml` 用 `[pytest]` 表。`addopts` 在 `pytest.toml` / `.pytest.toml` 的 `[pytest]` 表里必须是 **list**（实测写成字符串会报 `config option 'addopts' expects a list for type 'args'`，退出码 4）；`pyproject.toml` 的 `[tool.pytest]` 表（pytest 9.x 的 TOML 原生模式）与 `pytest.toml` 相同，`addopts` 也必须是 list；只有 `[tool.pytest.ini_options]` 同时接受字符串与 list（实测）。
- **默认收集规则**（pytest 9.2 实测）：文件名 `test_*.py` / `*_test.py`；类名前缀 `Test` 且**不能有 `__init__`**；函数/方法名前缀 `test`。`python_files` / `python_classes` / `python_functions` 可覆盖。
  > 实测：`TestWithInit` 被静默跳过并给出 `PytestCollectionWarning: cannot collect test class ... because it has a __init__ constructor`；`NotATestClass` 与普通 `helper()` 不收集。收集数少于文件里「看起来像 test」的函数数——「文件在 `tests/` 下」不等于「用例会被执行」。
- **收集命令**：`pytest --collect-only -q`（或 `--co`）给出 `path::test[param]` 清单与总数；先跑收集、再跑执行，是对账的第一步。
  > 实测 httpx：安装 `httpcore/anyio/certifi/idna/chardet/zstandard` 等测试依赖后 `pytest tests --collect-only -q` 收集 **1418** 条；缺 `chardet`/`zstandard` 时分别为 1237/1378 条并带 collection error。**收集数随依赖是否可用变化**，报告必须写明环境。
- **`testpaths` / `norecursedirs` / `--ignore` / `--deselect` / `-k` / `-m`**：这些是**排除**，被排除的用例在报告里是 `deselected` 或不出现，**不是 skipped**。
  > 实测：`pytest discovery -m "not slow"` → `2 passed, 1 deselected`；`-k` 表达式把所有用例都排除时退出码为 **5**（`NO_TESTS_COLLECTED`），而不是 0。

### 1.2 退出码（EXEC-002）

pytest 9.2 的 `ExitCode`（源码 `_pytest/config/__init__.py`）：

| 码 | 含义 | 审查含义 |
| --- | --- | --- |
| 0 | 全部通过（含 skipped/xfailed） | 仍需看 skipped 计数 |
| 1 | 有用例失败 | 红灯 |
| 2 | 被中断；**collection error 也走 2** | 测试没跑全，不是通过 |
| 3 | pytest 内部错误 | 工具/插件问题，记「未能判定」 |
| 4 | 用法错误（配置/参数非法） | 配置没生效，不是通过 |
| 5 | **没有收集到测试**（`NO_TESTS_COLLECTED`） | 「零测试」不是「全绿」 |
| 6 | 警告数超过 `--max-warnings` 阈值 | 策略失败，按项目配置判定 |

> 实测：`pytest empty` → `no tests ran`，退出码 5；含 `def test_broken(:` 的目录 → `Interrupted: 1 error during collection`，退出码 2。

### 1.3 报告与对账（EXEC-002 / EXEC-006）

- **终端摘要**：`-ra` 列 skipped/xfailed 原因；`-rxX` 列 xfail/xpass。`addopts = "-rxXs"` 常见于项目配置，审查时先看实际 `addopts`。
- **JUnit XML**：`--junitxml=report.xml`；根元素 `<testsuites name="pytest tests">`，其下 `<testsuite name="pytest" errors="..." failures="..." skipped="..." tests="..." time="..." timestamp="..." hostname="...">`，每个用例是 `<testcase>`（参数化用例带 `[id]` 后缀）。
  > 实测：3 个单参数 + 2×2 交叉共 7 条，XML 中 `<testcase>` 为 7；`tests` 属性为 7。用 `grep -o '<testcase' | wc -l` 计数，不要用 `grep -c`（XML 可能压成一行）。
- **计数对账**：源码中的 `@pytest.mark.parametrize` 行数 × 组合数、fixture 参数化、`unittest` 的 `subTest`（实测 1 条用例内 3 个 subtest 通过）都会让「声明数 ≠ 收集数」。先按参数/子测试展开规则归一化，再对差集逐条回读源码。
- **产物是活文件**：`--lf/--ff`、`-k`、`--junitxml` 和 CI 的重复运行会覆盖报告；审查前记时间戳，确认全量证据来自哪次运行。`--lf` 在无失败缓存时可能跑全量，`--ff` 总会跑但把失败排前；二者都是**子集/重排证据**，不能当全量套件。
  > 实测：先跑失败用例，再 `pytest fail -q --lf` 只重跑该失败用例。

### 1.4 构建/运行环境（EXEC-001）

- 测试是否被安装为可导入包：`pip install -e .` / `pip install .` 后从**非仓库目录**执行 `import pkg`；flat 布局下从仓库根运行会导入本地源码，不能证明发布产物可用。
- 依赖：`pip show -f <dist>`、`importlib.metadata.requires`；缺失的可选测试依赖会让 collection 直接失败（见第四节）。
- 插件：`pytest --trace-config` 列出已加载插件；`-p no:<plugin>` 可排除。插件版本与项目 pin 不一致是执行结果变化的常见根因。

## 二、跳过与假绿形态词表（EXEC-003 / EXEC-004 / EXEC-005）

### 2.1 显式跳过/预期失败（EXEC-003）

- `@pytest.mark.skip(reason=...)`：无条件跳过；`@pytest.mark.skipif(condition, reason=...)`：条件跳过。
  > 实测：`skipif(True)` 记 SKIPPED，exit 0；`-ra` 摘要给出原因。httpx 的 `@pytest.mark.skipif(sys.version_info >= (3, 11), reason=...)` 在 3.14 上记 `SKIPPED`（1 skipped）。
- `pytest.importorskip("mod")`：模块缺失时跳过**整个测试模块或用例**；比 try/except 后 `return` 好——报告留痕。
- `@pytest.mark.xfail(reason=...)`：**非 strict** 时，用例失败记 XFAIL；用例意外通过记 **XPASS**，默认**不算失败**（exit 0）。`strict=True` 时 XPASS 记失败（实测：`1 failed, ... 1 xpassed`，exit 1）。
  > 审查要点：项目未开 `xfail_strict = true` 时，一个「本该失败」的用例变绿会静默变成 XPASS；关键回归用例应显式 `strict=True`，或在配置里开 `xfail_strict = true`。
- `pytest.xfail("...")`：运行期在用例内部触发 XFAIL（实测记 XFAIL）。
- `@pytest.mark.skip` / `skipif` 作用在类上会跳过整个类；`pytest.skip()` 在 fixture 内跳过使用该 fixture 的用例（实测 SKIPPED），直接抛异常则是 ERROR。
- **marker 排除**：`-m "not slow"` / `-m "not network"` 排除的用例在报告里是 `deselected`，**不是 skipped**；必须读配置/CI 命令，不能只看报告。
- **unittest**：`@unittest.skip(...)` → SKIPPED；`@unittest.expectedFailure` → XFAIL（实测）；`self.skipTest()` 运行期跳过；`subTest` 的失败不会中止其余子测试，但父用例记失败。
- **静默跳过**：用例内 guard + `return`（无 marker）在报告中仍显示通过；依赖外部资源的用例必须用 `skipif` / `importorskip` / `pytest.skip` 留痕，否则属 EXEC-003 的静默形态。

### 2.2 断言的执行与假绿（EXEC-004；ASRT-001/002）

- **`python -O` 与 assert**：pytest 会重写**测试模块**的 assert（替换为显式 `if + raise`），所以 `-O` 下测试模块的 assert **仍然执行**；未被 pytest 重写的辅助模块/插件/被测库中的 assert 才会被剥离。
  > 实测：`python -O -m pytest` 下 `test_o.py::test_assert_alive` 仍 FAILED；测试导入的 `helper.py` 中的 `assert` 被剥离，对应用例 **PASSED**，并输出 `PytestConfigWarning: assertions not in test modules or plugins will be ignored ... (are you using python -O?)`。
  > 审查要点：①被测代码/辅助函数中的 assert 在 `-O` 下是空断言；②测试本身若依赖 helper 的 assert 做校验，会变成假绿；③CI 不应在 `-O` 下跑测试，除非明确处理了该差异。
- **`pytest.raises` 类型过宽或缺少 `match`**：类型写成 `Exception` / `BaseException` 会接受任何异常（包括被测代码的错误 bug）；使用具体类型但不带 `match` 时，无法区分同类异常的不同来源。关键用例要断言具体类型 + `match`，异常链用 `exc_info.value.__cause__` 核对。
- **Mock 假绿**：`MagicMock` 会自动创建任意属性/返回值，`mock.foo.bar().baz` 永远可用；未加 `autospec` 的 patch 对签名错误不敏感。`assert_called_once_with` 只证明「按这个参数调用过」，不证明返回值被正确处理。
- **标志位/空断言**：`try/except` 中置标志位的反模式（初始值写错、catch 后不再置位）在 pytest 中同样存在；`assert` 被 `-O` 剥离时，标志位断言也可能失效。审查时逐个核对「标志位初始值 + 置位点 + 断言」。
- **参数化失败**：每个参数行是独立用例，一行失败不影响其余行（实测 7 条参数化用例各自独立）；但 for 循环写成的表驱动测试一次失败即中止剩余行（`test-review` COV-003）。
- **fixture 错误不是跳过**：fixture 抛异常记 ERROR（实测），不是 SKIPPED；报告里的 `errors` 属性要单独看，不能只看 `failures`。
- **`filterwarnings = error` 与插件**：配置把警告变错误时，插件自身的 `DeprecationWarning` 会让 pytest 在 configure 阶段就 **INTERNALERROR**（实测：装了 `pytest-asyncio` 但未设置 `asyncio_default_fixture_loop_scope`，httpx 的 `filterwarnings = ["error", ...]` 触发 INTERNALERROR）。这是环境/插件问题，不是测试逻辑通过。
- **`unittest` 断言**：`assertEqual(1, 2, "msg")` 的消息不会被 `pytest.raises` 的 `match` 覆盖；`assertRaises` 的宽类型与 `pytest.raises` 同样有区分度问题。

### 2.3 覆盖率与「跑过」（EXEC-005）

- 覆盖率工具（coverage.py / pytest-cov）只证明行被执行，不证明断言存在或断言有区分度；`coverage` 100% 仍可能是空断言/镜像实现。覆盖率报告必须与 ASRT/COST 判据结合看。
- `--lf` / `--ff` / `-k` 的通过不能证明全量套件通过；报告必须写明本次运行的选择器。

## 三、对账（EXEC-006）

- **参数化展开**：`@pytest.mark.parametrize` 的每个参数行是独立用例；多个 `parametrize` 叠乘（实测 2×2 = 4，另有 3 个单参数，共 7）。源码声明数 ≠ 收集数是**正常**，差额必须能由参数行数/组合数解释。
- **fixture 参数化**：`@pytest.fixture(params=[...])` 会让依赖它的每个用例按参数展开；对账时把 fixture 的参数维度乘进去。
- **测试 id**：默认 id 是参数值的字符串化，重复值会带 `0/1` 后缀（实测 `[x-1]`、`[y-1]` 等）；不要用 id 直接推断参数值，回读源码或 `--collect-only` 的完整路径。
- **类/方法**：`TestClass::test_method` 是一级；类被 `__init__` 拦截时不收集（实测），文件存在≠用例存在。
- **模块级跳过**：`pytest.importorskip` 在模块顶层会让整个文件的用例消失/记 skip；对账时必须与「文件本来就没有用例」区分。
- **subTest**：一条 `TestCase` 用例下多个 subTest 在 JUnit XML 中仍是一条 `<testcase>`，但在终端汇总里可能单独计数（实测 `3 subtests passed`）；不要把「subtest 数」加到 tests 总数上。

## 四、假阳性陷阱（定性前必读）

- **网络标记不是自动跳过**：httpx 用 `@pytest.mark.network` 标记外网用例，但**没有默认 skip**；不显式 `-m "not network"` 就会真的访问网络。报告须写明是否排除。
- **系统代理/注册表污染**（实测）：Windows 上 `urllib.request.getproxies()` 会读系统注册表；即使 `os.environ` 已清空，httpx 的 `get_environment_proxies()` 仍返回 `http://127.0.0.1:7897` 等代理，导致 `test_get_environment_proxies[environment0-proxies0]` 失败。`conftest.py` 的 `clean_environ` 只清环境变量，清不掉注册表——这一条是**环境问题**，不是被测代码缺陷。
  > 但不要把所有失败都归给同一个环境因素：同一子集的另外 2 条失败（`test_logging_request`、`test_logging_redirect_chain`）的 JUnit failure message 显示 caplog 里多出 `('uvicorn.access', ...)` 记录，期望的 `httpx` 日志实际存在，属于日志隔离/运行器差异（实测 pytest 9.2.0 下出现；用 httpx pin 的 pytest 8.4.1 跑同一子集为 `1 failed, 51 passed`）。报告必须**按 failure message 逐条归因**，并如实写「该次运行整体为红」。
  > 实测汇总：httpx 子集 `tests/test_utils.py tests/test_api.py` 为 `3 failed, 49 passed`——1 条注册表代理 + 2 条 caplog/运行器差异。
- **缺失可选依赖导致 collection error**：httpx 缺 `chardet` / `zstandard` 时分别收集 1237 / 1378 条并报 collection error；补齐后 1418 条。审查前先确认依赖完整性，否则会把「没收集到」误读为「用例不存在」。
- **插件与版本**：`pytest-asyncio` 未设置 `asyncio_default_fixture_loop_scope` 会在 `filterwarnings=error` 下 INTERNALERROR（实测）；`pytest-randomly` / `xdist` 会改变顺序与并行行为；插件版本必须记录。
- **异步测试的失败形态**：`async def` 测试在没有 async 插件时是 **FAILED**（“async def functions are not natively supported”，实测），不是 skipped；报告里看到 FAILED 先确认插件，不要当业务缺陷。
- **哈希随机化**：`set` / `frozenset` 的迭代顺序随 `PYTHONHASHSEED` 变化（实测不同 seed 顺序不同）；同一测试在不同 CI 跑次结果不同，先查是否依赖 set 顺序，再判 flake。
- **CWD 与路径**：测试从项目根/测试目录/IDE 运行时 CWD 不同；用相对路径写死的用例属环境依赖。Windows 路径大小写不敏感、`os.path.join` 遇绝对路径替换基路径（实测），跨平台用例要用 `pathlib`。
- **`filterwarnings=error`**：项目配置把警告变错误时，被测代码的 `DeprecationWarning`（如 `datetime.utcnow()`，实测 3.14 已废弃）会让用例失败；这是测试在设计上暴露问题，不是 flake，也不能用 `-W ignore` 掩盖。
- **缓存**：`.pytest_cache` 的 lastfailed/nodeids 会影响 `--lf` / `--ff`；跨分支切换后缓存可能过期，必要时 `--cache-clear` 后重跑。
- **`--max-warnings` 的退出码 6**：警告数超阈值时所有测试可能都通过，但退出码是 6；CI 若只看 exit 0 会漏判，需按项目策略核对。

## 五、本语言特有豁免

- **基准**：`benchmarks/`、`asv.conf.json`、pytest-benchmark 的 benchmark 用例豁免本技能全部规则，仅保留 EXEC-001/002 的工程性判据（基准必须真的被收集/执行）。
- **属性测试 / fuzz**：Hypothesis 等不在本技能范围；未覆盖时显式标注「未覆盖」，不记通过。
- **网络/浏览器集成测试**：`@pytest.mark.network` 或项目既有标记的用例按集成测试放宽确定性要求，但必须可默认排除，并在报告中说明是否排除。
- **`conftest.py`**：作为测试基础设施审查；其 hook/fixture 的全局副作用按 DET/EXEC 判，不按产品代码 ORG 规则判。
- **第三方工具**（pytest-cov、pytest-xdist、pytest-randomly、pytest-mock、responses、respx、freezegun、time-machine）：引用其输出/行为时注明工具与版本；Docker/浏览器不可用时记「未能判定（缺运行环境）」。
