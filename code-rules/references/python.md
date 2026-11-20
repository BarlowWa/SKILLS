# Python 编码规范（code-rules / references）

> 本文件由 code-rules 按扩展名路由加载。工作流程、严重级别、审查输出格式、豁免与「冲突取更严者」见 `code-rules/SKILL.md`；与 G-xxx 同义时以本文 ID 为准（SKILL.md『G ↔ 语言文件去重表』）。
> 本文 ID 为 Python 专属命名空间（`PY-<CAT>-NNN`，warning 类可写成 `PY-<CAT>-WNNN`）；被 `arch-review`、`test-author` **按 ID 引用**，不得改名。
> 行为结论标注来源：`实测` = Python 3.14.6 探针（pytest 9.2.0 / ruff 0.17.6 / mypy 2.4.1）；`文档` = CPython / 标准库 / 工具官方文档；`核对` = 按本机版本核对后适用。未标注的按语言语义判定。

## 适用

- 扩展名：`.py`、`.pyi`；本文件同时适用于 `pyproject.toml` 中的构建/工具配置审查。
- 构建/工具链：pip、setuptools / hatchling / flit / poetry / pdm；静态检查：ruff、mypy / pyright；测试运行器 pytest（测试文件本身豁免，见『本语言专属豁免』）。
- 版本：以 `pyproject.toml` 的 `requires-python` 为准；条目内标注最低版本。实测环境为 CPython 3.14.6；3.10–3.13 的项目按版本核对，不能因版本低而跳过语义类 blocker。
- 不在本文件范围：模块依赖、分层、循环导入、包级公开面、类型发布面（`py.typed`）归 `arch-review`；测试/基准的设计与质量归 `test-author` / `test-review`；SQL 归 `db-rules`。

## RES：资源生命周期

> 上下文管理器把获取/释放写进协议；手写的 `try/finally` 容易在异常覆盖、清理顺序和部分初始化路径上出错。

- **PY-RES-001**（blocker）：支持上下文管理器的资源（文件、锁、连接、临时目录、线程池等）必须用 `with` 管理；禁止用 `try/finally` 替代本可使用的 `with`。
  > 为什么：`with` 在 `__exit__` 中统一处理异常路径；手写 `finally` 容易写错多资源的关闭顺序，或让 `close()` 的异常覆盖 try 体的原始异常。
  > 正例：`with open(p, encoding="utf-8") as fh, ThreadPoolExecutor() as pool: ...`。
  > 边界：对象不支持上下文管理器时，`try/finally` 或 `ExitStack.callback(res.close)` 均可，但必须覆盖所有退出路径；`@contextmanager` 的实现本身可以用 `try/finally`（它就是 `with` 的实现机制），不按本条判。
  > 例外：资源在 `with` 之前已创建且后续仍需使用时，用 `contextlib.ExitStack` 显式接管，不要回退到 finally。

- **PY-RES-002**（blocker）：禁止在 `finally` 中 `return` / `break` / `continue`——它们会吞掉 try 体正在传播的异常。
  > 为什么：Python 的 finally 在异常传播路径上仍会执行，其中的控制转移语句直接覆盖异常，调用方以为成功。

- **PY-RES-003**（blocker）：异步资源用 `async with` / `aclose()`；禁止依赖 `__del__` 或 GC 关闭文件、连接、任务。
  > 为什么：`__del__` 的执行时机不确定，解释器退出时甚至可能不执行；`async with` 的 `__aexit__` 才是可等待的配对点。
  > 实测：`asyncio.run()` 在已运行的事件循环内调用会抛 `RuntimeError: asyncio.run() cannot be called from a running event loop`——异步资源的生命周期必须由调用方的事件循环管理。

- **PY-RES-004**（warning）：大量动态资源用 `contextlib.ExitStack` 统一接管；`ExitStack.callback` 的注册顺序与执行顺序相反，需要正序清理时用 `push` 并显式管理。

## MUT：可变状态与别名

> Python 的函数默认参数、类属性和闭包都在**定义时**求值，不是在调用时。

- **PY-MUT-001**（blocker）：禁止把可变对象（`list` / `dict` / `set` / 自定义可变实例）用作函数或方法的默认参数；用 `None` + 函数体内 `if x is None: x = []`，或用不可变默认值。
  > 实测：`def f(x, acc=[]): acc.append(x)` 连续调用得到 `[1, 2]`——默认列表在函数对象上只创建一次，被所有调用共享。
  > 检测：ruff `B006`（flake8-bugbear 的 mutable-argument-default）。

- **PY-MUT-002**（blocker）：可变类属性会被所有实例共享；实例状态必须在 `__init__` 中创建，`dataclass` 的可变字段用 `field(default_factory=list)`。
  > 实测：`class C: items = []` 在实例 A 上 `append` 后，实例 B 的 `items` 同样被修改。
  > 为什么：`dataclass` 对可变默认值会直接抛 `ValueError`，但普通类属性不会——后者是静默共享。

- **PY-MUT-003**（blocker）：循环内创建的闭包会延迟绑定循环变量；需要捕获当前值时用默认参数（`lambda i=i: ...`）、`functools.partial` 或工厂函数。
  > 实测：`[lambda: i for i in range(3)]` 调用结果为 `[2, 2, 2]`。
  > 检测：ruff `B023`（function-uses-loop-variable）。

## NULL：None、空值与真值

> `None` 是「没有值」的唯一惯用表示；`if x:` 表达的是真值，不是「x 非 None」。

- **PY-NULL-001**（blocker）：与 `None` 比较必须用 `is None` / `is not None`；禁止 `x == None`、`x != None`。
  > 为什么：`==` 可被 `__eq__` 重载，返回非布尔值或对 `None` 产生非预期匹配；`is` 是身份比较，语义明确。
  > 检测：ruff `E711`（comparison-to-none）。

- **PY-NULL-002**（blocker）：判断「有值」时用 `x is not None`，不要用 `if x:`——`0`、`""`、`[]`、`{}`、`False` 都是合法值。
  > 反例：`if not value: return default` 会把合法的 `0` / 空字符串当成缺失。
  > 边界：当契约明确把空值视为「无」时（如空列表表示无结果），`if not x:` 可接受，但契约必须写明。

- **PY-NULL-003**（warning）：需要区分「缺失」与「显式 None」时用专用 sentinel（`_MISSING = object()`），不要复用 None；`dict.get(k)` 在 None 是合法值时不能表达「键不存在」。

- **PY-NULL-004**（warning）：`bool` 是 `int` 的子类——`True == 1`、`True + True == 2`（实测）；API 不要用 `bool` 与 `int` 混用的重载，判断类型时注意 `isinstance(True, int)` 为真。

## EQ：相等、身份与哈希

> `is` 问「是不是同一个对象」，`==` 问「值是否相等」；两者在 Python 里都可能被重载。

- **PY-EQ-001**（blocker）：`is` 只用于 `None` / `True` / `False` / 模块级单例 / 显式身份判断；值比较用 `==`。禁止用 `is` 比较数字、字符串、容器。
  > 实测：运行时构造的 `int("1000") is int("1000")` 为 False；但同一代码对象里的字符串字面量可能被驻留，`"hello" is "hello"` 为 True——`is` 的通过与否取决于解释器缓存，不能作为值语义。
  > 检测：ruff `F632`（is-literal，`x is "s"` / `x is 1`）；`E712` 管的是 `x == True`，不覆盖 `is` 值比较。

- **PY-EQ-002**（blocker）：定义 `__eq__` 时必须同时定义 `__hash__`（或显式设 `__hash__ = None` 声明不可哈希）；相等对象必须有相同哈希。
  > 实测：只定义 `__eq__` 的类实例执行 `hash()` 抛 `TypeError: unhashable type`——Python 会自动把 `__hash__` 置为 None，放入 `set` / 作 `dict` 键时才发现。
  > 为什么：哈希容器的查找先按哈希定位再按 `==` 比较；二者不一致会导致「明明相等的键查不到」。

- **PY-EQ-003**（warning）：`__eq__` 对不支持的类型必须返回 `NotImplemented`（让 Python 尝试反向比较），不得返回 `False` 或任意值。
  > 实测：`__eq__` 返回字符串时，`a == b` 的结果就是该字符串——调用方 `if a == b:` 的真值判断被静默污染。

- **PY-EQ-004**（warning）：浮点相等用 `math.isclose(a, b, rel_tol=..., abs_tol=...)`；`NaN != NaN` 恒真（实测），涉及 NaN 的分支必须显式处理。`Decimal` 的比较用 `compare()` 或 `==` 时注意 `Decimal("1.0") == Decimal("1.00")` 为 True（实测）——与 Java `BigDecimal.equals` 的 scale 语义相反，不要照搬。

## NUM：数值与精度

> Python 的 `int` 是任意精度，`float` 是 IEEE-754 双精度；金额与定点数用 `Decimal`。

- **PY-NUM-001**（blocker）：金额、税费、利率等十进制定点值禁止用 `float`；用 `decimal.Decimal`，并从字符串构造（`Decimal("0.1")`）。
  > 实测：`0.1 + 0.2` 为 `0.30000000000000004`；`Decimal("0.1") == 0.1` 为 False（float 的 0.1 不是精确的 0.1）；`Decimal(0.1)` 得到 55 位二进制展开的精确值。
  > 例外：仅用于统计/采样且明确接受误差的场景可用 float，须在契约中注明容差。

- **PY-NUM-002**（warning）：`round()` 使用银行家舍入（round-half-to-even）；实测 `round(2.5) == 2`、`round(3.5) == 4`。业务要求「四舍五入」时用 `Decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`，不要假设 `round` 是四舍五入。
  > 检测：无专门的静态规则能发现舍入口径错误，须按业务契约人工核对。

- **PY-NUM-003**（warning）：`int` 无溢出，但转换为 `float` 会在超过 2^53 后丢失精度（实测：`float(2**53 + 1) == float(2**53)` 为 True，`int(float(2**53 + 1))` 得到 `2**53` 而非 `2**53+1`）；用整数做 ID/哈希时不要中途经过 float。

- **PY-NUM-004**（warning）：浮点比较禁止 `==` / `!=` 直接判定相等；需要容差时显式 `math.isclose`。`bool` 参与算术（`True + True == 2`，实测），不要把布尔标志当计数器（与 `PY-NULL-004` 同源）。

## STR：字符串、字节与编码

> Python 3 的 `str` 是 Unicode 码点序列，`bytes` 是字节序列；两者在边界处显式转换。

- **PY-STR-001**（blocker）：所有文本 I/O 必须显式指定 `encoding`（优先 `"utf-8"`）；禁止依赖 `open()` 的默认编码，`Path.read_text()` / `write_text()` 同样要传 `encoding=`。
  > 实测：本机 `sys.getdefaultencoding()` 为 `utf-8`，但 `locale.getpreferredencoding(False)` 为 `cp936`，`sys.flags.utf8_mode` 为 0，`io.text_encoding(None)` 返回 `"locale"`——`open()` 走的是 locale，不是 `sys.getdefaultencoding()`。
  > 为什么：同一份文件在不同 Windows/Linux 环境读出不同字符或直接 `UnicodeDecodeError`。
  > 检测：ruff `PLW1514`（unspecified-encoding，pylint 规则集；preview 规则，需 `--preview`）。

- **PY-STR-002**（blocker）：`str` 与 `bytes` 不得混用；在 I/O/协议边界显式 `encode()` / `decode()`。禁止对用户数据使用 `errors="ignore"` / `"replace"` 来「让它跑通」。
  > 实测：`b"a\xffb".decode("utf-8", "ignore")` 得到 `"ab"`——非法字节被静默丢弃，数据损坏不可见。
  > 边界：读取已知损坏的历史数据时可用 `errors="replace"` 并记录替换数；必须显式注明。

- **PY-STR-003**（warning）：`len(s)` 计的是 Unicode 码点，不是用户感知字符（字素簇）。实测 `len("😀") == 1`，而 `len("👨‍👩‍👧") == 5`（含 ZWJ）；截断、定长校验、显示宽度必须明确口径，需要字素簇时用第三方库（如 `regex` / `grapheme`）并注明依赖。
  > 边界：`str.encode("utf-8")` 的字节数与 `len(s)` 不相等（"😀" 为 4 字节，实测）。

- **PY-STR-004**（warning）：大小写比较用 `casefold()`（如 `"ß".casefold() == "ss"`），不是 `lower()`；实测 `"İ".lower()` 得到两个码点。Python 的 `lower/casefold` 不依赖 locale（与 Java 不同），但按语言做本地化排序/大小写仍需 ICU 类库并注明。
  > 边界：协议字段、枚举键、字典键的大小写规范化必须使用同一函数（`casefold` 或显式 `upper/lower`），不能混用。

- **PY-STR-005**（warning）：`strip()` 去除的是 Unicode 空白（含 `\xa0` 等），不是「空格」；`split()` 无参时按任意空白折叠并丢弃空串，`split(sep)` 保留空串语义——CSV/路径解析必须显式选择分隔符并覆盖尾部空字段。
  > 实测：`" \t\nx\xa0 ".strip()` 得到 `"x"`；`"a,,b".split(",")` 得到 `["a", "", "b"]`（与 Java 的 `split` 不同）。

- **PY-STR-006**（warning）：文本模式会做换行转换（实测 Windows 上读 `b"a\r\nb\r\n"` 得到 `"a\nb\n"`）；需要精确往返或哈希原文时用 `newline=""` 或二进制模式。

## COLL：容器与拷贝

> 容器默认可变、按引用传递；「看起来像值」的对象往往共享底层数据。

- **PY-COLL-001**（blocker）：遍历容器时禁止增删元素；需要条件删除时遍历副本（`for k in list(d):`）或用推导式构造新容器。
  > 实测：遍历 `dict` 时插入新键抛 `RuntimeError: dictionary changed size during iteration`；`list` 的增删虽不立即报错，但会跳过元素。

- **PY-COLL-002**（blocker）：函数接收可变参数时不得**意外**原地修改；契约明确声明就地修改的 API（`list.sort`、`random.shuffle`、`heapq` 等）是正当的。返回内部可变状态前必须拷贝（浅拷贝或 `deepcopy`，按嵌套深度选择，见 PY-COLL-003）。
  > 为什么：调用方的列表/字典被意外修改后，问题往往在很远的地方才暴露。

- **PY-COLL-003**（warning）：区分浅拷贝与深拷贝；嵌套结构用 `copy.deepcopy`，扁平结构用 `copy.copy` / `list(x)` / `dict(x)`，按实际深度选择，不要默认 deepcopy 大对象。
  > 实测：`copy.copy` 后修改内层列表，原对象同步变化。

- **PY-COLL-004**（warning）：`dict` 从 3.7 起保证插入顺序；`set` 的迭代顺序**不保证**，实测不同 `PYTHONHASHSEED` 下顺序不同。禁止依赖 set 顺序做输出、分页、快照或断言。
  > 检测：无专门的静态规则能可靠发现顺序依赖，需人工核对输出/断言是否依赖 set 迭代序。

- **PY-COLL-005**（warning）：`list.sort` / `sorted` 是稳定排序；key 函数必须返回可比较的同类值，混合类型（`int` 与 `str`）在 Python 3 直接抛 `TypeError`。需要多级排序时用元组 key，不要依赖调用顺序的副作用。

- **PY-COLL-006**（warning）：`d[k]` 在键缺失时抛 `KeyError`；`d.get(k)` 返回 None；`d.setdefault(k, []).append(...)` 有副作用；`defaultdict` 读取不存在的键会插入默认值。按「缺失是否合法」「是否允许副作用」选择，不要一律用 `get`。

## EXC：异常

> Python 的异常是控制流的一部分；`except` 的范围就是你能处理的故障范围。

- **PY-EXC-001**（blocker）：禁止裸 `except:`；捕获具体异常类型。`except Exception` 原则上只允许出现在进程/线程/框架边界，且必须记录并重新抛出或转换为契约异常。
  > 实测：裸 `except:` 会捕获 `KeyboardInterrupt` / `SystemExit`（二者继承 `BaseException`），使 Ctrl-C 与退出信号失效。
  > 边界：探测/兼容函数需要把解析失败转成 `False`/`None` 时，必须收窄到具体异常（如 `ipaddress.AddressValueError`）并紧邻注释；无注释地宽捕 `Exception` 仍按 blocker 记，因为它会把 `AttributeError`/`TypeError` 等程序性错误隐藏成正常结果。
  > 检测：ruff `E722`（bare-except）、`BLE001`（blind-except）。

- **PY-EXC-002**（blocker）：禁止吞异常——`except ...: pass`、只 `print` 后继续、或记录后返回值仍被当作成功（G-SWALLOW）。要么传播（可包装，但保留原始信息），要么在紧邻处注释「有意忽略及理由」。
  > 反例：`try: ... except OSError: pass` 后继续写文件，调用方无从知道数据未落盘。

- **PY-EXC-003**（blocker）：包装异常必须保留原因：`raise ServiceError("...") from exc`；明确要隐藏内部异常时用 `from None` 并注释理由。禁止 `raise RuntimeError(str(exc))` 丢失类型与 traceback。
  > 实测：`raise ... from exc` 后 `__cause__` 为原始异常类型，`__context__` 也保留；`from None` 会清空 `__cause__` 并抑制上下文显示。
  > 检测：ruff `B904`（raise-without-from-inside-except）。

- **PY-EXC-004**（blocker）：禁止用 `assert` 校验外部输入或公共 API 参数——`python -O` / `PYTHONOPTIMIZE` 会剥离 assert（实测：`python -O` 下库函数中的 `assert x > 0` 不再抛异常）。用 `if not ...: raise ValueError(...)`。
  > 边界：按**数据来源**判断——外部/不可信输入或公共 API 参数校验用 assert → blocker（`-O` 下失效）；内部不变式（程序内部状态的前置/后置条件，不依赖外部输入）可以用 assert，即使它是该处的唯一检查，也属开发期自检；一旦该 assert 同时承担对外部输入的校验，按前者判。
  > 检测：ruff `S101`（assert）。

- **PY-EXC-005**（warning）：库代码禁止 `sys.exit()` / `SystemExit`；抛出领域异常，由 CLI 入口转换为退出码。`sys.exit()` 在库中被调用会直接终止宿主进程。

- **PY-EXC-006**（warning）：多个并发/批量子失败用 `ExceptionGroup`（3.11+）与 `except*` 表达；不要静默压平成「第一条异常」，除非契约明确只保留第一条。

- **PY-EXC-007**（warning）：`finally` 中只做清理，不做控制流；需要有意忽略某类异常时用 `contextlib.suppress(SpecificError)` 并在紧邻注释理由，不用裸 `except: pass`。

## CONC：并发与异步

> GIL 是 CPython 的实现细节，不是内存模型；`x += 1` 仍是读-改-写三步。

- **PY-CONC-001**（blocker）：共享可变状态的复合操作必须用 `threading.Lock` / `Queue` / 原子数据结构保护；不要因为「有 GIL」就省略同步。
  > 为什么：GIL 只保证单条字节码不并行执行，`counter += 1` 由多条字节码组成，线程切换可发生在中间；在线程池、回调、信号处理器之间共享计数/缓存时尤其危险。
  > 边界：只读的不可变数据、每线程独立对象无需加锁。

- **PY-CONC-002**（blocker）：`asyncio` 协程中禁止调用阻塞 I/O、`time.sleep()`、同步数据库/HTTP 客户端；用 `async` 版本或 `asyncio.to_thread()`。`asyncio.run()` 不得在已运行的事件循环内调用（实测抛 `RuntimeError`）；同一进程顺序多次调用是允许的，但每次都会新建/关闭事件循环，库代码不应自行管理事件循环。
  > 为什么：阻塞调用会占住事件循环线程，所有协程一起卡死。

- **PY-CONC-003**（blocker）：`asyncio.create_task()` 的返回值必须保存强引用（集合/列表/`TaskGroup`），否则事件循环只持有弱引用，任务可能在完成前被 GC 回收、永远不会完成（事件循环会打印 `Task was destroyed but it is pending!`），但不会自动取消；任务异常必须被 await 或通过回调处理。
  > 文档：Python 文档明确要求保存任务引用，事件循环只持有弱引用。
  > 优先用 3.11+ 的 `asyncio.TaskGroup`（结构化并发，自动传播异常）。

- **PY-CONC-004**（warning）：取消是协作式的；捕获 `asyncio.CancelledError` 后必须重新抛出（除非在做清理）。实测 `asyncio.CancelledError` 在 3.8+ 继承 `BaseException` 而非 `Exception`，所以 `except Exception` 抓不到它——不要用裸 `except:` / `except BaseException:` 把它吞掉。需要「不可取消」的清理时用 `asyncio.shield`，并注意 shield 只保护被包裹的 await。

- **PY-CONC-005**（warning）：异步请求上下文用 `contextvars`，不要用 `threading.local`——协程可在同一线程内切换，thread-local 会把 A 请求的值泄漏给 B 请求。

- **PY-CONC-006**（warning）：Python 3.13+ 提供可选 free-threaded 构建（无 GIL）；依赖 GIL 的隐式原子性在 free-threaded 下不成立。库代码不得把「当前默认构建有 GIL」写进契约。

## TIME：时间与时区

> 朴素（naive）datetime 没有时区，不能表示绝对时刻。

- **PY-TIME-001**（blocker）：跨时区/持久化的时刻必须使用带时区的 `datetime`（`datetime.now(datetime.UTC)` / `ZoneInfo`）；禁止用朴素 `datetime.now()` / `datetime.utcnow()` 作为绝对时间。
  > 实测：`datetime.utcnow()` 在 3.14 发出 `DeprecationWarning`，建议改用 `datetime.now(datetime.UTC)`；朴素值参与比较/序列化会丢失偏移。

- **PY-TIME-002**（warning）：测量时长用 `time.monotonic()` / `time.perf_counter()`，不要用 `time.time()`（墙上时钟可被 NTP/夏令时/手动调整回拨）。

- **PY-TIME-003**（warning）：`zoneinfo` 下 DST 间隙/重叠的行为必须显式定义：实测 `2026-03-08 02:30 America/New_York`（不存在的墙钟时间）得到 `-05:00`；`2026-11-01 01:30` 的 `fold=0` 为 `-04:00`、`fold=1` 为 `-05:00`。定时调度、营业时间计算必须覆盖这两类边界。
  > 依赖：Windows 上 `zoneinfo` 需要 `tzdata` 包；缺失时抛 `ZoneInfoNotFoundError`（实测）。

- **PY-TIME-004**（warning）：`timedelta(days=30)` 不是「一个月」；自然月/工作日计算用 `dateutil.relativedelta` 或显式业务规则，并写清口径。

- **PY-TIME-005**（warning）：业务代码不要直接调用 `datetime.now()` / `time.time()`；把「当前时间」作为可注入依赖（函数参数或 Clock 对象），否则无法稳定测试。

## SEC：安全

> Python 标准库的默认值偏「方便」，安全项通常要显式加固。

- **PY-SEC-001**（blocker）：密码、API 密钥、Token、私钥禁止以字面量写入源码；用环境变量、不入库的配置或密钥管理服务。日志与异常消息同样禁止输出（含对象 `repr`/`__dict__` 泄露）。
  > 检测：ruff `S105` / `S106`（hardcoded-password，按版本核对）只覆盖明显形态；含密字段的 `__repr__` / `__str__` 须人工核对。

- **PY-SEC-002**（blocker）：外部命令必须用 `subprocess.run([...], shell=False)` 的参数列表形式；禁止 `shell=True`、`os.system`、`os.popen` 拼接用户输入；可执行路径须白名单校验（G-CMDINJ）。
  > 为什么：`shell=True` 把参数重新交给 shell 解析，引号/分号/管道即注入面。

- **PY-SEC-003**（blocker）：禁止 `eval()` / `exec()` 处理不可信输入；解析字面量用 `ast.literal_eval()`，模板/规则表达式用受限解释器。
  > 检测：ruff `S307`（suspicious-eval-usage）。

- **PY-SEC-004**（blocker）：不可信数据禁止 `pickle.load` / `pickle.loads` / `shelve`；用 JSON 等数据格式。YAML 用 `yaml.safe_load`，禁止 `yaml.load` 配 `UnsafeLoader`/`FullLoader`。
  > 检测：ruff `S301`（suspicious-pickle-usage）、`S506`（unsafe-yaml-load）。

- **PY-SEC-005**（blocker）：SQL 必须用驱动/ORM 的参数绑定（`cursor.execute("... WHERE id = ?", (id,))`），禁止 f-string / `%` / `format` 拼接；动态表名/列名无法绑定时须白名单校验。
  > 检测：ruff `S608`（hardcoded-sql-expression）只覆盖部分形态。

- **PY-SEC-006**（blocker）：安全场景（令牌、密码重置码、盐）用 `secrets` / `os.urandom`，禁止 `random` / `numpy.random`；密码哈希用 PBKDF2/scrypt/argon2/bcrypt，禁止裸 MD5/SHA-1。
  > 实测：`random.random()` 与 `secrets.token_hex(4)` 均可用，但前者是 Mersenne Twister，可预测。
  > 检测：ruff `S311`（suspicious-non-cryptographic-random-usage）。

- **PY-SEC-007**（blocker）：对外 HTTP 请求必须处于有超时状态：`requests` 的 `timeout` 默认 `None`（无限等待，实测签名默认值），必须显式设置；`httpx` 默认 5 秒（实测 `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)`），不得显式改为 `timeout=None` 关闭超时。TLS 校验不得关闭（`verify=False` / `verify=ssl.CERT_NONE`）。
  > 检测：ruff `S501`（request-with-no-cert-validation）覆盖 `verify=False`，不覆盖超时缺失。

- **PY-SEC-008**（blocker）：不可信 XML 用 `defusedxml`（或显式禁用外部实体/DTD）；标准库 `xml.etree.ElementTree` 的实体处理限制随版本变化，不能默认视为安全。
  > 文档：Python 官方文档在 XML 安全章节明确建议使用 `defusedxml`。

## PATH：路径与归档

> `os.path.join` 遇到绝对路径会**丢弃**前面的基路径；这不是「拼错」，是注入。

- **PY-PATH-001**（blocker）：用户可控路径必须做穿越校验：`(base / user).resolve()` 后断言 `is_relative_to(base.resolve())`；拒绝绝对路径与 `..` 段，符号链接按 `resolve()` 结果判定。
  > 实测：`os.path.join(r"C:\base", r"C:\Windows")` 得到 `C:\Windows`；`Path(r"C:\base") / Path(r"C:\Windows")` 同样替换基路径；`C:\base\..\etc` 解析为 `C:\etc`，`is_relative_to(base)` 为 False。
  > 为什么：仅字符串拼接或只 `normalize()` 不解析符号链接，仍可被绕过。

- **PY-PATH-002**（blocker）：解压不可信归档前必须防 Zip Slip / Tar Slip：逐个成员校验解析后的目标路径仍在目标目录内；`tarfile.extractall` 在 3.12+ 用 `filter="data"`（或等效白名单），`zipfile` 按成员名校验。
  > 文档：Python 3.12 起 `tarfile` 提供 extraction filters；默认行为随版本收紧，不能假设旧版本的默认值安全。

## TYPE：类型注解

> 注解是公开 API 的一部分；mypy strict 是把契约写进 CI 的最低成本方式。

- **PY-TYPE-001**（warning）：公开函数/方法/类属性必须有完整注解；库项目的 CI 应启用 mypy（或 pyright）并作为必过项。前向引用用 `from __future__ import annotations` 或字符串注解。
  > 文档：`py.typed` 的发布面归 `arch-review` ARCH-PY-011，本条目只管单文件注解质量。

- **PY-TYPE-002**（warning）：公开 API 边界禁止裸 `Any`（含隐式 Any）；用 `Protocol` / `TypeVar` / 具体类型表达契约；确实无法表达时显式注释理由。

- **PY-TYPE-003**（warning）：`# type: ignore` 必须带错误码并尽量缩小行范围（`# type: ignore[arg-type]`）；禁止全文件/无码忽略。定期清理 mypy 的 `unused-ignore`。
  > 实测：ruff `PGH003`（blanket-type-ignore）在 httpx 样本命中 11 处；mypy strict 另报 `unused-ignore`（未装 `zstandard` 时 2 处，装后 1 处，见 `arch-review/references/python.md` ARCH-PY-011 的实测记录）。
  > 检测：mypy `--warn-unused-ignores`（strict 已含）。

- **PY-TYPE-004**（warning）：仅为类型检查需要的导入放在 `if TYPE_CHECKING:` 块内；但运行时仍需要的依赖不得只写在 TYPE_CHECKING 里，否则会在运行期 `NameError`。

- **PY-TYPE-005**（warning）：运行期类型判断优先 `isinstance(x, (A, B))` / `isinstance(x, A | B)`（3.10+）；避免 `type(x) is int`——它不匹配 `bool` 子类（实测 `isinstance(True, int)` 为真，`type(True) is int` 为假）。

## IMPORT：导入形态

> 导入期执行的代码就是程序启动的一部分；副作用应当有明确归属。

- **PY-IMPORT-001**（warning）：禁止通配导入 `from x import *`；包 `__init__.py` 的集中重导出是例外，但必须有显式 `__all__` 并由测试核对（包级公开面归 `arch-review`）。
  > 检测：ruff `F403` / `F405`；httpx 样本在 `__init__.py` 用 `from ._client import *` 并由 `test_exported_members.py` 断言 `__all__` 与模块成员一致——这是受控形态。

- **PY-IMPORT-002**（blocker）：模块顶层不得执行有副作用的初始化：网络/磁盘 I/O、启动线程、读取环境变量并写全局配置、连接数据库（日志配置见 PY-LOG-W001）。初始化放到显式的工厂/入口函数。
  > 边界：库代码按 blocker；应用入口/配置模块在模块加载时读环境变量并构造配置对象，若集中、显式且无 I/O，可按 warning 记录。常量表、纯函数、类型定义不受限；跨模块全局状态与初始化顺序归 `arch-review` ARCH-PY-005。

- **PY-IMPORT-003**（warning）：函数内延迟导入只用于打破循环依赖或隔离可选依赖，且必须紧邻注释说明原因；不得用延迟导入隐藏真实的 `ModuleNotFoundError`。

- **PY-IMPORT-004**（warning）：同一包内相对导入与绝对导入不要混用；包内引用优先相对导入（`from ._utils import ...`），跨包引用用绝对导入。`__main__` 守卫与入口点组织归 `arch-review` ARCH-PY-008。

## LOG：日志

- **PY-LOG-W001**（warning）：库代码只 `logger = logging.getLogger(__name__)`，禁止调用 `logging.basicConfig()` / 给 root logger 加 handler；日志实现与级别由应用配置（G-LOG）。
  > 实测：`logging.getLogger(__name__)` 在 `__main__` 下名称为 `"__main__"`；`basicConfig()` 会修改全局 root handler 列表。

- **PY-LOG-W002**（warning）：日志用惰性参数化（`logger.info("user=%s", uid)`），禁止在调用点先 f-string 拼接；参数含密码/令牌时显式脱敏。

- **PY-LOG-W003**（warning）：库代码禁止用 `print()` 当日志；CLI 的 stdout 输出是产品行为，不属于日志。异常路径用 `logger.exception()` 保留 traceback。
  > 检测：ruff `T201`（print）；httpx 样本命中 1 处（CLI 输出，需按上下文判定）。

## NAME：命名

- **PY-NAME-001**（warning）：遵循 PEP 8——模块/函数/变量 `snake_case`、类 `PascalCase`、常量 `UPPER_SNAKE_CASE`、内部实现以单下划线开头；禁止 `m_` / `s_` 匈牙利前缀。
  > 边界：`__dunder__` 只用于语言协议（`__init__` / `__eq__` / `__all__`），不得自定义 `__my__thing__`。
  > 检测：ruff `N`（pep8-naming 规则集，需显式启用）。

## BUILD：构建与工具链

> 构建配置是代码的一部分；默认值不可依赖，显式声明才可复现。

- **PY-BUILD-001**（blocker）：新项目必须用 `pyproject.toml` 声明 `build-system`、`requires-python`、运行时依赖与包发现方式；禁止 `sys.path.insert/append` 之类的运行期路径 hack 来「找到自己的包」。
  > 为什么：路径 hack 让开发环境能跑、安装后失败；`requires-python` 缺失会让 pip 在不兼容解释器上安装。
  > 边界：遗留 `setup.py` / `setup.cfg` 项目不强制迁移，但必须有等价的元数据（`python_requires`、`install_requires`、包发现）；依赖 extras、锁文件与可复现安装面归 `arch-review` ARCH-PY-002/009，本条目只判单包构建配置。

- **PY-BUILD-002**（warning）：ruff / mypy 的配置写入 `pyproject.toml` 并纳入 CI；允许的忽略项必须逐条列出（如 `ignore = ["B904"]` 必须能说明理由），不能用「全量 noqa」代替修复。
  > 实测：httpx 的 `[tool.ruff.lint] ignore = ["B904", "B028"]` 会让项目配置下的 `ruff check` 不报 B904，但 `--isolated --select B904` 仍能扫出 5 处——审查时不能只看项目配置的绿灯。

- **PY-BUILD-003**（warning）：生成的代码（迁移脚本、protobuf、ORM 自动生成、供应商代码）不得手改；风格规则（NAME / LOG / MAGIC）对生成代码放宽，安全类 blocker（SEC / PATH / EXC）仍须在生成配置或调用边界修复。

## MAGIC：魔法值

- **PY-MAGIC-001**（blocker）：有业务/领域语义的字面值必须是命名常量、`Enum` / `IntEnum` 或配置项；`0` / `1` / `-1` / 空串 / `True` / `False` 及上下文自明的惯用值除外（G-MAGIC）。
  > 上下文自明豁免：协议/编码常量（UTF-8 多字节长度 `2/3/4`、`0x7F`、`0x10FFFF`）、位运算掩码、HTTP 状态码在语义明确处可直接使用。
  > 检测：ruff `PLR2004`（magic-value-comparison）可作线索，但会误报协议常量，须人工判断。

## 本语言专属豁免

通用豁免（测试/基准/SQL/架构）见 `code-rules/SKILL.md`『豁免』。以下是 Python 特有条目：

- **测试/基准**：`tests/`、`test_*.py`、`*_test.py`、`conftest.py` 的用例设计使用 `test-author`、质量审查使用 `test-review`；`benchmarks/`、`asv.conf.json` 基准豁免本文全部规则。
- **`__init__.py` 的受控重导出**：有显式 `__all__` 且由测试核对的通配重导出，不按 `PY-IMPORT-001` 判；包级公开面本身归 `arch-review` ARCH-PY-004。
- **`.pyi` 存根**：只应用 TYPE / NAME 规则；RES / EXC / CONC / LOG 等运行时规则不适用（存根不执行）。
- **`if TYPE_CHECKING:` 块内导入**：不受 `PY-IMPORT-003` 的「延迟导入需注释」约束（仅类型检查，无运行期语义）。
- **`assert` 的内部不变式**：仅用于内部状态自检、不承担外部输入校验时不按 `PY-EXC-004` 判（即使它是该处的唯一检查）；公共 API 的参数/输入校验仍按 blocker。
- **生成代码与迁移脚本**：按 `PY-BUILD-003` 放宽风格规则；安全类 blocker 不豁免。
- **第三方库的 `Any` 边界**：无类型标注的第三方 API 返回值转成 `Any` 后必须在最近边界收口（`cast` / 校验），不得让 `Any` 扩散到公开 API；不因「第三方没类型」整体豁免 TYPE。
