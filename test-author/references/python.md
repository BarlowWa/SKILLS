# Python 测试设计参考（test-author / references）

> 由 test-author 在测试文件为 Python（`test_*.py`、`*_test.py`、`tests/`、`conftest.py`）时加载。通用规则见 `test-author/SKILL.md`；本文只补 **Python 独有的边界形态、惯用写法与语言约束**，不新增规则 ID。
> `实测` 表示 pytest 9.2.0 / Python 3.14.6 探针验证；`文档` 表示引自 CPython / pytest 官方文档；`核对` 表示按本机工具链版本核对。

## 测试框架与惯用写法

- **pytest 发现规则**（实测）：默认收集 `test_*.py` 与 `*_test.py` 文件、`Test` 前缀的类（类不能有 `__init__`）、`test_*` 函数/方法。实测 `TestWithInit` 被跳过并给出 `PytestCollectionWarning: cannot collect test class ... because it has a __init__ constructor`；`NotATestClass` 与普通函数 `helper()` 不被收集。项目可用 `python_files` / `python_classes` / `python_functions` 覆盖，审查时以配置为准。
- **fixture**：`@pytest.fixture` 的函数参数注入；常用内建：`tmp_path`（独立临时目录）、`monkeypatch`（环境变量/属性/字典修改并自动恢复）、`capsys`/`capfd`（stdout/stderr）、`caplog`（日志断言）。
  > fixture 内 `pytest.skip()` 记为 SKIPPED；fixture 直接抛异常记为 **ERROR**（实测），不是 skipped——别把「依赖没准备好」写成普通异常，否则执行链证据会变成错误而不是可解释的跳过。
- **参数化**：`@pytest.mark.parametrize` 每行参数是独立用例。实测 `3` 个单参数 + `2×2` 交叉 = 7 条收集；用 `ids=` 或 `pytest.param(..., id=...)` 给业务语义，便于对账。
- **异常断言**：`with pytest.raises(ValueError, match=r"invalid port: 'x'"):`；`match` 是 `re.search` 语义，不要拿它断言完整消息（除非用 `^...$`）。异常链断言 `exc_info.value.__cause__` / `__context__`。
- **警告断言**：`with pytest.warns(DeprecationWarning, match="..."):`；单纯「不发警告」用 `warnings.catch_warnings(record=True)` 或 `filterwarnings` 配置。
- **浮点断言**：`pytest.approx(expected, rel=..., abs=...)`；`Decimal` 用 `==` 或 `compare()`（注意 `Decimal("1.0") == Decimal("1.00")` 为 True，实测，与 Java `BigDecimal.equals` 不同）。
- **unittest 兼容**：`unittest.TestCase` 子类同样被 pytest 收集；`assertRaises`、`self.subTest(i=i)`、`@unittest.skip`、`@unittest.expectedFailure` 均可用（实测：1 passed / 1 skipped / 1 xfailed / 3 subtests passed）。
- **Mock**：`unittest.mock.patch` 的 target 写**使用处**（`patch("mymodule.dependency.call")`），不是定义处；优先 `autospec=True`（签名不匹配会报错），避免 `MagicMock` 自动创建任意属性造成假绿。`pytest-mock` 的 `mocker` fixture 是可选糖，不改变语义。
- **异步**：用 `pytest.mark.anyio`（anyio 插件）或 `pytest.mark.asyncio`（pytest-asyncio）运行 `async def` 测试；插件未安装时 `async def` 测试会 **FAILED**（实测：「async def functions are not natively supported」），不是 skipped。项目内不要混用两套 async 插件；`anyio_backend` / `asyncio_mode` 配置以项目为准。
- **可选依赖**：`pytest.importorskip("zstandard")` 在模块级跳过整文件；更适合「该 extras 未安装」的可解释跳过，优于在用例里 try/except 后 `return`（后者在报告里仍显示通过，属静默跳过）。

## BVA-001 / NUM 细化：数值边界

- **整数**：Python `int` 任意精度，没有溢出；边界来自**业务语义**与**协议/存储宽度**（`2**31-1`、`2**63-1`、JSON/数据库/序列化格式的上限），不是语言类型上限。用 `2**53` 邻域测整数转 float 的精度损失（实测 `float(2**53 + 1) == float(2**53)` 为 True，`int(float(2**53 + 1))` 得到 `2**53` 而非 `2**53+1`）。
- **浮点**：`0.0`、`-0.0`、`±inf`、`nan`、最小正次正规数；`nan != nan` 恒真（实测），需要 `math.isnan`；`0.1 + 0.2 != 0.3`（实测）；断言用 `pytest.approx` 或 `math.isclose`。
- **Decimal**：`Decimal("0.1") != 0.1`（float，实测）；`Decimal("1.0") == Decimal("1.00")` 为 True（scale 不参与 `==`，实测）；需要 scale 语义时断言 `as_tuple().exponent` 或 `quantize` 后的字符串。覆盖 `Decimal` 上下文精度/舍入模式（`getcontext().prec`、`ROUND_HALF_UP`）的边界。
- **`round`**：银行家舍入（实测 `round(2.5) == 2`、`round(3.5) == 4`）；「四舍五入」契约必须用 `Decimal.quantize(..., rounding=ROUND_HALF_UP)` 的用例，不能拿内建 `round` 当规格。
- **bool 混入**：`True == 1`、`True + True == 2`（实测）；参数是 `int` 的 API，用例应覆盖 `True` / `False` 输入，确认是否被拒绝或按 1/0 处理。

## BVA-002 / COLL 细化：容器

- **空/单元素/满容量/超容量**：`[]`、`[x]`、恰好达到上限、上限 + 1；`dict` 同样覆盖 `{}`、单键、重复键、超量键。
- **别名与拷贝**：输入列表被函数原地修改、返回内部列表被调用方修改、浅拷贝与 `deepcopy` 的差异（实测：浅拷贝后内层列表共享）。用例必须断言**原对象是否被修改**，不能只断言返回值。
- **迭代中修改**：`for k in d: d["new"] = ...` 抛 `RuntimeError: dictionary changed size during iteration`（实测）；契约要求「允许边遍历边改」时必须显式用例覆盖。
- **顺序**：`dict` 插入顺序稳定（3.7+），`set` 顺序不保证且随 `PYTHONHASHSEED` 变化（实测不同 seed 下顺序不同）；涉及输出的用例不要用 set 顺序做期望值，比较内容用 `set(...)` / 排序后比较。
- **`sort` 稳定性**：相同 key 的元素保持原相对顺序；多级排序用元组 key，覆盖「相等 key」的稳定性用例。
- **`None` 作为值**：`d.get(k)` 无法区分「键不存在」与「值为 None」；契约需要区分时用 sentinel，用例同时覆盖两种状态。

## BVA-003 / STR 细化：字符串与编码

- **`str` vs `bytes`**：同一语义的两种输入分别设计用例；`b"..."` 与 `"..."` 的类型错误必须在契约中定义为拒绝（`TypeError`）还是转换。
- **编码**：用 `tmp_path` 写非 UTF-8 字节（如 GBK/cp936）测 `UnicodeDecodeError`；`errors="ignore"` 会静默丢字节（实测 `b"a\xffb"` → `"ab"`），只在契约明确允许时断言该行为。
- **Unicode 边界**：`len("😀") == 1`（码点）但 UTF-8 为 4 字节；`len("👨‍👩‍👧") == 5`（含 ZWJ，实测）——长度上限、截断、显示宽度的用例必须明确口径；需要字素簇时用第三方库并注明版本。
- **大小写**：`casefold` 与 `lower` 不同（实测 `"ß".casefold() == "ss"`；`"İ".lower()` 为两个码点）；协议字段的规范化函数必须有覆盖这些字符的用例。
- **空白/切分**：`strip()` 去 Unicode 空白（含 `\xa0`）；`split()` 无参按任意空白折叠，`split(sep)` 保留空串；CSV/路径解析覆盖尾部空字段与连续分隔符。
- **换行**：文本模式读 `\r\n` 会转成 `\n`（实测，Windows）；需要精确往返时用 `newline=""` 或二进制，用例断言原始字节。
- **编码默认值**：`open()` 不传 `encoding=` 在 Windows 上走 locale（实测 `cp936`），测试必须显式编码或通过 `PYTHONUTF8=1`；不要用「本机能读」证明跨平台正确。

## BVA-005 细化：索引与迭代

- `0`、`len-1`、`len`（越界首个）、负数索引（Python 负数索引合法：`lst[-1]` 是末元素；不要照 C++/Java 的「负数越界」预期）；`slice` 的 `start:stop:step` 边界、`stop` 超出长度、`step=-1` 反转。
- 迭代器耗尽后 `next()` 抛 `StopIteration`；生成器在异常/`return` 后的 `finally` 执行时机。
- `dict` 视图（`keys()`/`items()`）是动态视图，底层修改后再遍历可能抛 `RuntimeError`；用例断言契约要求的快照或视图语义。

## BRP-004 细化：None 与空值

`None`、空 `str`、空 `list`、空 `dict`、`0`、`False` 是六种不同输入，真值判断下前五个中的空容器/0 都会走 False 分支。按被测函数的契约分别设计：
- 参数缺失/`None` → 拒绝（`TypeError`/`ValueError`）还是默认值；
- 空集合是合法结果还是错误；
- 返回 `None` 与返回空集合的契约必须区分（`is None` vs `== []`）。
> 反例：`if not result:` 同时接受 `None` 与 `[]`，用例若只覆盖 `[]`，无法发现 `None` 分支。

## BRP-003 细化：异常路径与异常链

- 每个受检异常/自定义异常至少一条：`pytest.raises(T, match=...)`，并断言 `__cause__` / `__context__`（包装异常时）。
- 禁止 `try: ... except Exception: pass` 的「空断言」；`pytest.raises` 不应捕获过宽类型（`Exception` / `BaseException`）而不 `match`。
- `raise X from e` 与 `raise X from None` 是两个不同契约（是否暴露原因）；分别设计用例。
- `ExceptionGroup`（3.11+）与 `except*`：多错误场景断言 `exc.exceptions` 的类型/消息集合；不要只断言「抛了 ExceptionGroup」。
- `finally` 中清理失败：断言主异常保留、清理异常如何传播/聚合（按契约）。

## CONC-001 细化：线程与异步

- **线程**：用 `threading.Barrier` / `Event` / `Queue` 构造确定性交错；禁止 `time.sleep` 制造时序（`test-review` TPERF-002）。线程/线程池在用例内 `join` / `with ThreadPoolExecutor()` 关闭；断言的是「同步后的结果正确」，不是「未同步时必然失败」。
- **GIL**：不要用「有 GIL」作为不加锁的理由；`counter += 1` 的竞态用例很难稳定复现，允许标为「不可稳定判定」并注明，而不是写一个依赖调度概率的断言。
- **asyncio**：用 `pytest.mark.anyio`（或项目选定的插件）运行；`asyncio.wait_for` 覆盖超时；`TaskGroup`（3.11+）覆盖子任务失败传播；取消用例断言 `CancelledError` 被重新抛出、清理仍执行。
- **阻塞调用**：协程中调用同步 I/O/`time.sleep` 的缺陷，用「事件循环心跳被推迟」的探针（如并发心跳任务 + 超时）观测，不要用真实网络。
- **free-threaded**：3.13+ 可选无 GIL 构建；库若声称支持，需要在 free-threaded 解释器上单独跑并发用例，不能只靠默认构建。

## RLC-001 细化：资源与生命周期

- 上下文管理器的 `__exit__` 参数（异常类型/值/traceback）与返回 True 吞异常的行为；用例断言退出顺序（多个 `with` 逆序）与异常传播。
- `close()` 幂等性、关闭后使用（`ValueError: I/O operation on closed file`）、`__enter__` 失败时 `__exit__` 是否被调用。
- 异步资源：`async with` 的 `__aexit__` 在取消路径上是否执行；`aclose()` 后再次使用应失败。
- 临时文件/目录：用 `tmp_path`（函数级隔离）或 `tmp_path_factory`（会话级），不写系统固定路径；用例结束后的清理由 fixture 负责。

## CONTRACT-001 细化：Python 特有契约

- **相等/哈希**：`__eq__` 与 `__hash__` 成对；相等对象哈希相同、可放入 set/dict；`__eq__` 对无关类型返回 `NotImplemented`（实测返回字符串会污染真值判断）。
- **真值**：自定义对象的 `__bool__` / `__len__` 定义「空/非空」语义；契约必须说明 `if obj:` 的含义，用例覆盖空与非空。
- **可变默认参数/类属性**：作为被测 API 的一部分时，用例必须覆盖「两次调用之间状态是否隔离」（实测默认列表共享）。
- **迭代协议**：`__iter__` / `__next__` / `__len__` / 生成器的惰性求值与提前终止；`StopIteration` 契约。
- **`__repr__` / `__str__`**：日志/错误消息依赖时断言稳定格式；含敏感字段时断言脱敏。
- **上下文管理器**：`__enter__` 返回值、`__exit__` 吞异常行为属于契约，不是实现细节。

## 确定性（BVA-006 / `test-review` DET）

- **随机**：`random.Random(seed)` 或无状态 `secrets` 仅用于非断言场景；禁止无种子 `random` / `numpy.random` 作为期望值来源（`test-review` DET-001）。
- **时间**：把 `now()` 作为依赖注入；用例用固定时刻（`datetime(..., tzinfo=UTC)`），或用 `freezegun` / `time-machine`（第三方，注明版本）。禁止用真实 `datetime.now()` / `time.time()` 作为断言基准；时长断言用 `time.monotonic()` 的假实现。
- **环境变量**：`monkeypatch.setenv` / `delenv` 自动恢复；不要在用例里直接改 `os.environ` 不恢复（会污染后续用例）。Windows 上 `urllib.request.getproxies()` 还会读系统注册表，`os.environ` 清理不足以隔离代理（实测 httpx 用例在本机因注册表代理失败）。
- **Locale / 时区**：`locale.setlocale` 与 `os.environ["TZ"]` / `time.tzset` 是进程全局态；需要时用 fixture 保存/恢复，并标记不可并行。优先显式传 `encoding` / `tzinfo` / `Locale` 参数，不做全局设置。
- **哈希随机化**：`PYTHONHASHSEED` 影响 `hash()` 与 set 顺序；不要写依赖 set 迭代顺序的期望值；需要复现时在 CI 固定种子（但这不是修复顺序依赖的正当理由）。
- **临时目录**：`tmp_path` / `tmp_path_factory`，不依赖 CWD 或 `%TEMP%` 固定名；用 `pathlib.Path` 拼接。
- **网络**：单测禁止真实外网；用 `httpx.MockTransport` / `responses` / `respx` 或项目内的 WSGI/ASGI 测试客户端。标 `@pytest.mark.network` 的集成测试必须可被 `-m "not network"` 排除，并在 CI 默认排除。
- **文件系统大小写/路径分隔符**：Windows 大小写不敏感、`\` 分隔；跨平台用例用 `pathlib`，避免写死 `/` 或 `C:\`。

## OGN-001 / OGN-002 细化：组织与命名

- 源文件与测试文件对应：`module.py` → `test_module.py`（或项目既有 `module_test.py`，二选一，不混用）；测试函数名 `test_<行为>_<场景>`，如 `test_parse_port_rejects_non_numeric`。
- 参数化集中边界用例；`pytest.param(..., id="min-1")` 让报告直接可读；不要用 for 循环生成参数（首个失败会中止剩余行，`test-review` COV-003）。
- 共享 fixture 放 `conftest.py`（按目录作用域），避免每个文件复制；fixture 的作用域（function/class/module/session）与可变状态必须匹配——session 级 fixture 返回可变对象时，用例之间会互相污染。
- `tests/` 目录加 `__init__.py` 或依赖 rootdir 的 import mode，按项目既有配置；不要在测试里 `sys.path` 修改来导入源码（`test-review` ORG-002）。

## 本语言特有豁免

- **基准**：`benchmarks/`、`asv.conf.json`、pytest-benchmark 的 `benchmark` fixture 不适用本文与父技能全部规则。
- **属性测试 / fuzz**：Hypothesis 等第三方能力不在本技能范围；引用时注明库与版本，未覆盖的场景显式标注「未覆盖」。
- **网络/浏览器集成测试**：标 `@pytest.mark.network` 或项目既有标记，按集成测试放宽确定性要求，但必须可默认排除并有理由。
- **`conftest.py`**：作为测试基础设施审查，不作为产品代码；其中的 hook/fixture 仍须遵守确定性要求（不要全局改环境不恢复）。
- **第三方测试工具**（pytest-mock、responses、respx、freezegun、time-machine、Hypothesis）：均为可选能力，引用其行为时注明库与版本，不得写成 pytest 内置能力。
