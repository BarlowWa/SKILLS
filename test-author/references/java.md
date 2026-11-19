# Java 测试设计参考（test-author / references）

> 由 test-author 在测试文件为 Java（`src/test/**`、`src/testFixtures/**`、`*Test.java`、`*Tests.java`、`*IT.java`）时加载。通用规则见 `test-author/SKILL.md`；本文只补 **Java 独有的边界形态、惯用写法与语言约束**，不新增规则 ID。
> `实测` 表示 JDK 25 探针验证；`文档` 表示引自 JDK / JUnit / AssertJ / Mockito 官方文档。

## 测试框架与惯用写法

- **JUnit 5（Jupiter）**：`@Test` / `@BeforeEach` / `@ParameterizedTest` + `@ValueSource` / `@CsvSource` / `@MethodSource`；`@Nested` 表达分组（同一外层类的 `@Nested` 共享 `@BeforeEach`）；`@DisplayName` 写场景语义。
- **断言**：JUnit `Assertions.assertEquals` 的参数顺序是 **expected 在前、actual 在后**（文档：`org.junit.jupiter.api.Assertions`），失败消息才会反向显示；集合/异常断言可用 AssertJ（`assertThat(actual).isEqualTo(expected)`、`assertThatThrownBy(...).isInstanceOf(...).hasMessageContaining(...)`），AssertJ 的 actual/expected 顺序更不容易写反。
- **参数化（OGN-001）**：边界用例集中到 `@ParameterizedTest` + `@CsvSource({"下界, min-1", "上界, max+1"})`，每个参数组合是独立用例；`@MethodSource` 适合构造复杂对象。
  > `@CsvSource` 有解析语义，不能当成字面量串：默认单引号 `'` 是**引号字符**（`''` 转义为字面单引号），**未加引号的首尾空白会被裁剪**（官方文档：JUnit 5 `@CsvSource`「Except within a quoted string, leading and trailing whitespace … is trimmed by default」），**空值被解释为 `null`**，而 `'\r\n\t'` 这类 Java 转义**不会被二次反转义**。含空白、控制字符、引号或逗号的参数用 `@MethodSource`（或 `@CsvSource` 的 `textBlock` + 引号 + `ignoreLeadingAndTrailingWhitespace=false`）——否则用例会在错误的输入上断言，产生假红/假绿（实测踩坑：把 `\\r\\n\\t` 写进 `@CsvSource` 得到的是反斜杠字面量而非空白字符）。
- **命名（OGN-002）**：`returnsZeroWhenQueueEmpty()`、`divByZeroThrowsArithmeticException()`、`exactCapacityOk()`；断言异常用 `assertThrows` 而不是只 `try/catch`。
- **测私有逻辑前先问**：JUnit 同 package 的测试可访问 package-private 成员——这是 Java 的常规可见性约定，**不是后门**（`test-review` ASRT-006 的边界）；但反射访问 private 字段仍属后门，按 ASRT-006 判。

## BVA-001 / NUM 细化：数值边界

- `int` / `long` 覆盖 `0`、`1`、`-1`、`Integer.MAX_VALUE`、`Integer.MIN_VALUE`；**`Math.abs(Integer.MIN_VALUE)` 仍为负**（文档），取绝对值后判断正负的用例必须包含 MIN_VALUE。
- 除法：`-7 / 2 == -3`、`-7 % 2 == -1`（实测）——负数取模路径必须独立用例，数组下标场景断言异常或改用 `Math.floorMod`。
- 浮点：`Double.NaN`（`NaN != NaN` 恒真）、`-0.0`（`-0.0 == 0.0` 恒真，`Double.compare` 返回 -1，实测）、`Double.POSITIVE_INFINITY`、`Double.MIN_VALUE`（最小正 subnormal，最接近 0）与 `Double.MAX_VALUE` 各一条。
- `BigDecimal`：`1.0` vs `1.00` 的 `equals` 为 false 而 `compareTo == 0`（实测）；金额用例须同时覆盖 scale 与数值两种断言语义，并覆盖 `divide` 不整除时的 `ArithmeticException`（未指定 rounding mode）。
- `new BigDecimal(0.1)` 与 `BigDecimal.valueOf(0.1)` 的差异（实测）可作为「构造方式契约」的回归用例。

## BVA-002 / COLL 细化：集合

- `List.of` / `Set.of` / `Map.of`：空、单元素、**含 null 输入必须断言 NPE**（实测 `List.of("a", null)`），以及尝试修改时的 `UnsupportedOperationException`。
- `Arrays.asList(new int[]{1,2})` 的 `size() == 1`（实测）——基本类型数组不被展开，是 Java 集合的高频陷阱，必须有回归用例。
- `HashMap` / `HashSet` 迭代顺序：断言不得依赖 `keySet()` / `values()` 的顺序（`文档`：`HashMap` 不保证顺序）；比较集合内容用 `assertEquals(Set.of(...), x)` 或排序后比较。
- `subList` 视图：底层 `add`/`remove` 后访问视图的未定义行为（文档）不适合作为普通用例断言「必然抛 CME」——改为断言契约要求的防御性拷贝行为。
- `collect(Collectors.groupingBy)` 默认返回 `HashMap`，需要顺序时用四参数重载指定 `LinkedHashMap`。
- 有序容器（`ArrayList`、`LinkedHashMap`）的扩容/复制用例除内容外还须断言**保序**不变式；只断言 `equals` 不足以暴露顺序丢失（`List.equals` 虽顺序敏感，但换了容器类型或经 `Set` 中转后会漏检）。

## BVA-003 / STR 细化：字符串与编码

- `String.length()` 与 `codePointCount` 在 emoji 上不同（实测 `"😀".length() == 2`）——长度上限、截断、定长校验的用例必须覆盖代理对。
- `split`：`"a,b,,".split(",")` 得 `[a, b]`（实测丢尾部空串），`split(",", -1)` 保留——CSV/路径解析的用例两种形态都要覆盖；`split(".")` 是正则点号，需断言转义后的行为。
- `replaceAll` 的替换串含 `$` / `\` 时 `IllegalArgumentException`（实测）——用户可控替换内容须走 `Matcher.quoteReplacement` 的用例。
- 默认编码：以 `new String(bytes)` / `getBytes()` 无参形式构造的路径，契约必须写明编码；用例显式使用 `StandardCharsets.UTF_8`，并覆盖非法 UTF-8 字节序列（Java 的 `new String(bytes, UTF_8)` 会替换为 U+FFFD 而不抛异常——断言的是替换行为，不是异常）。
  > 编码路径是 package-private 时（常见：工具类的 `load(InputStream)` 内部默认 `UTF_8`），把测试类放在**同 package** 的 `src/test/java` 下即可观测，或改走公开的带 `Charset` 重载做对照——不要为可测性加 `public` 后门（`test-review` ASRT-006）。
- `toLowerCase` / `String.format` 的 Locale 依赖：断言必须显式 `Locale.ROOT`；若要测本地化行为，用 `Locale.setDefault` 的用例必须恢复原值（见『确定性』）。

## BVA-005 细化：索引与迭代

- `0`、`size() - 1`、`size()`（越界首个）、负数索引（`list.get(-1)` → `IndexOutOfBoundsException`）。
- `List.remove(int)` 与 `List.remove(Object)` 的重载歧义：`list.remove(1)` 删下标——`List<Integer>` 的删除用例必须显式装箱 `remove(Integer.valueOf(1))` 并断言删的是元素而非下标。
- `Iterator` 的 `next()` 在耗尽后抛 `NoSuchElementException`（文档）；`for-each` 中修改原集合 → `ConcurrentModificationException`（文档）。
- 数组：`length == 0`、`length == 1`、`copyOf` 扩展到 `length + n` 时的补零行为。

## BRP-004 细化：Java 空值形态

`null`、`Optional.empty()`、空集合、空字符串、`Optional.ofNullable(null)` 语义不同，须分别设计：
- `Optional.of(null)` 抛 NPE（实测）；`Optional.empty().get()` 抛 `NoSuchElementException`。
- `orElse(fallback)` 的 fallback 总是求值（实测），`orElseGet` 惰性——有副作用/昂贵构造的 fallback 必须有用例断言求值次数。
- `map` / `filter` 遇空值的行为：`Optional.map` 对 null 结果返回 empty（文档）。

## BRP-003 细化：异常路径

- 每个受检异常 / 自定义异常类型至少一个用例：`assertThrows(XxxException.class, () -> ...)`，并断言消息或 cause（`hasCauseInstanceOf` / `assertThat(e.getCause())`）。
- 禁止只 `try { ...; fail("should throw"); } catch (Exception e) { }` 的空 catch 断言——任何异常（包括断言失败）都会通过。
- `finally` 与异常叠加：在契约允许的范围内验证 `try-with-resources` 的 suppressed 机制（主异常保留、close 异常挂 suppressed），不要用「finally 中 return」写用例——那是缺陷形态而非契约。
- `InterruptedException` 路径：用例线程收到中断后断言中断标志被恢复（`Thread.currentThread().isInterrupted()`）。

## CONC-001 细化：线程与并发

- 测试内创建的线程/线程池必须 `join` / `shutdown`；`ExecutorService` 在 `@AfterEach` 中关闭（Java 19+ 可 try-with-resources）。
- 竞态用例用 `CountDownLatch` / `CyclicBarrier` / `Phaser` 构造确定性交错，禁止 `Thread.sleep` 制造时序（`test-review` TPERF-002）。
- `volatile` 可见性用例无法稳定复现——断言的是「同步原语使用后结果正确」，不是「未同步时必然失败」；后者属不可判定，标注为未覆盖。
- JDK 21+ 虚拟线程：行为与平台线程一致，但阻塞点语义按 JDK 版本核对；用例写死在某一版本的表现前先确认项目 toolchain。

## RLC-001 细化：资源与生命周期

- `AutoCloseable` 的关闭顺序：try-with-resources 按声明**逆序**关闭（JLS 14.20.3.2），用可观测的关闭日志检验。
- `close()` 幂等性：契约允许则测二次关闭；不允许则断言第二次抛异常。
- 对象池 / 缓存：`close` 后使用（`IllegalStateException`）、并发关闭（至少一个线程成功、其余得到一致结果）。
- `ThreadLocal`：任务结束后 `remove()`，用同一线程连续执行两个任务并断言无残留。

## CONTRACT-001 细化：Java 特有契约

- `equals` / `hashCode` / `compareTo` 的一致性契约（自反、对称、传递、与 hashCode 联动、与 compareTo 一致）——用 EqualsVerifier（可选库）或手写对称性/传递性用例固定。
  > **成对设计**：类型的 `equals` 一旦声明为**顺序无关**（Map/Set 语义，如基于按键查找的实现），`hashCode` 与 `equals` 的一致性用例就是强制项——`Array.hashCode`、`Arrays.hashCode(keys)` 这类按索引计算的实现会在此暴露（实测 jsoup `Attributes.equals` 顺序无关、`hashCode` 顺序敏感，违反 `Object#hashCode` 契约，且其自带测试无覆盖）。反过来，`compareTo` 与 `equals` 不一致的用例同理。
- `record` 的自动 `equals`：数组组件按引用比较（`文档`：`java.lang.Record`），契约需要值语义时必须有覆盖该差异的用例。
- `Serializable`：`serialVersionUID` 未显式声明时，任何字段/方法签名的重构都会让序列化失败——契约要求跨版本兼容时，用例须固定序列化字节并断言反序列化。
- 注解处理器 / Lombok 生成的 API：以**编译成功**作为契约证据（缺失的实现/多余的 API 会让调用方编译失败）；需要固定「应当编译失败」的契约时用 Google 的 compile-testing 库（第三方，可选）。

## 确定性（BVA-006 / `test-review` DET）

- **随机数据**：用 `new Random(seed)` 或 `SplittableRandom(seed)`；禁止 `new Random()` 无参、`Math.random()`、`ThreadLocalRandom`（无法播种，`文档`）。
- **时间**：被测代码须通过注入 `Clock` 获取时间；用例用 `Clock.fixed(Instant.parse("..."), ZoneOffset.UTC)`（文档）。禁止直接 `Instant.now()` 作为断言的基准。
- **Locale / TimeZone / default Charset**：均为进程全局可变状态（DET-003）——需要修改时用 `@BeforeEach` 保存、`@AfterEach` 恢复原值，并标注不可并行；优先改为显式传参。
- **JUnit 5 默认并行关闭**：开启 `junit.jupiter.execution.parallel.enabled=true` 后，静态可变状态与共享临时目录会竞态；并行用例须 `@ResourceLock` 或独立资源。
- **临时文件**：`@TempDir`（JUnit 5）注入，不依赖系统临时目录的固定路径；工作目录（`user.dir`）随 IDE/构建器变化，不能作为断言路径。
- **网络**：真实网络请求只允许出现在集成测试（`*IT`），且必须可跳过并标注理由；单测用 HTTP 桩（如 `com.sun.net.httpserver.HttpServer` 或项目现有的测试服务器）。

## OGN-001 / OGN-002 细化：组织与命名

- 命名：`<被测方法>_<场景>_<期望>` 或 `shouldXxxWhenYyy` 由项目既有风格统一，不要同文件混用。
- `@Nested` 分组 + `@DisplayName` 让测试报告即用例矩阵；嵌套类不能是 `private`（JUnit 5 要求非 private，否则不执行）。
- `@ParameterizedTest` 的 `@CsvSource` 每个参数行是独立用例；表驱动 `for` 循环整体算一个用例，首个失败即中止——关键边界要拆成参数化行（`test-review` COV-003 同理适用）。

## 本语言特有豁免

- JMH 基准（`@Benchmark`、`src/jmh/`）不适用本文与父技能全部规则。
- 属性测试 / fuzz（jqwik、fast-check 的 Java 端）不在本技能范围（父技能已定）。
- JUnit 4（Vintage 引擎）项目：`@Test(expected=...)` 与 `@Rule` 的形态按项目既有框架判定，不要求迁移；新用例优先 Jupiter。
- 可选库（Mockito、AssertJ、jqwik、EqualsVerifier、Awaitility、Testcontainers）均为第三方能力，引用其行为时须注明库与版本；不得写成 JDK/JUnit 内置能力。
