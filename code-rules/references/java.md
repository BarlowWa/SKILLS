# Java 编码规范（code-rules / references）

> 本文件由 code-rules 按扩展名路由加载。工作流程、严重级别、审查输出格式、豁免与「冲突取更严者」见 `code-rules/SKILL.md`；与 G-xxx 同义时以本文 ID 为准（SKILL.md『G ↔ 语言文件去重表』）。
> 本文 ID 为 Java 专属命名空间（`JAVA-<CAT>-NNN`），被 `arch-review`、`test-author` **按 ID 引用**；不得改名。
> 行为结论标注了来源：`实测` 表示在 JDK 25（25+37-LTS-3491）上运行探针验证；`文档` 表示引自 JDK 官方 Javadoc / JLS；`核对` 表示按本机工具链版本核对后适用。未标注的条目按语言语义判定。

## 适用

- 扩展名：`.java`（含 `module-info.java`、`package-info.java`，后两者见『豁免』）。
- 构建/工具链：javac、Maven（`maven-compiler-plugin` / `maven-surefire-plugin`）、Gradle；静态检查：`javac -Xlint:all`、Error Prone、SpotBugs、PMD、Checkstyle。
- 版本：语言级别以构建配置的 `release`（推荐）或 `source`/`target` 为准；条目内标注最低版本（如「Java 11+」），低于该版本的项目不适用该条，但不得因版本低而跳过语义类 blocker。
- 不在本文件范围：模块依赖、分层、循环依赖、JPMS 可见性等架构级问题归 `arch-review`；测试/基准的设计与质量归 `test-author` / `test-review`；SQL 归 `db-rules`。

## RES：资源生命周期

> `AutoCloseable` 的存在意义就是让编译器替你配对关闭；手写 `finally` 只会漏。

- **JAVA-RES-001**（blocker）：实现 `AutoCloseable` 的资源必须用 try-with-resources 管理，禁止手写 `try { ... } finally { res.close(); }`。
  > 为什么：finally 中 `close()` 抛出的异常会覆盖 try 体的原始异常（JLS 14.20.2 的 suppress 机制只存在于 try-with-resources）；多个资源时关闭顺序也易写错（try-with-resources 按**声明逆序**关闭，JLS 14.20.3.2）。
  > 正例：`try (var in = Files.newInputStream(p); var out = Files.newOutputStream(q)) { ... }`。
  > 例外：资源变量在 try 之前已创建、且后续代码还要用时，用 Java 9+ 的「已有的 effectively final 变量作 resource」写法，不要为此回退到 finally。

- **JAVA-RES-002**（blocker）：禁止在 `finally` 中 `return` / `break` / `continue`——它们会吞掉 try 体正在传播的异常。
  > 为什么：Java 的 finally 在异常传播路径上仍会执行，其中的控制转移语句直接覆盖异常，调用方以为成功。`finally` 只做清理，不做控制流。

- **JAVA-RES-003**（blocker）：`ExecutorService` 必须显式关闭（`shutdown()` / `shutdownNow()`；Java 19+ 起 `ExecutorService extends AutoCloseable`，可直接放进 try-with-resources，按所用版本核对）；`ThreadPoolExecutor` 的自定义饱和策略与 `allowCoreThreadTimeOut` 不改变这一要求。
  > 为什么：未关闭的 executor 持有非 daemon 线程，JVM 无法退出、测试进程挂起；线程池线程还承载 `ThreadLocal`，不复用即泄漏。
  > 例外：生命周期与 JVM 等长的全局池（如虚拟线程 `Executors.newVirtualThreadPerTaskExecutor()` 之外的常驻池）须在注册处注明，并集中管理关闭钩子。

- **JAVA-RES-004**（blocker）：公开 API 接收 `InputStream` / `OutputStream` / `Reader` / `Writer` / `java.nio.channels.Channel` 并**在 Javadoc 中声明负责关闭**时，必须在**所有**退出路径关闭——包括解析/读取在包装对象构造完成之前就抛异常、或资源尚未被任何 `finally` 追踪字段持有的路径。
  > 为什么：把「关闭」挂在解析产物上（如 `finally { if (parsed != null) parsed.input.close(); }`）时，首步失败会让 `parsed` 仍为 null，流永久泄漏——调用方已按 Javadoc 放弃所有权，不会自己关（G-RELEASE 的 Java 落地形态）。
  > 实测反例：jsoup `DataUtil.java:224-250` 的 `load(InputStream)` Javadoc 写「The stream will be closed after reading」，但 `detectCharset` 在首步抛 `IOException` 时 `charsetDoc == null`、`finally` 不关；探针确认失败后流仍打开。
  > 做法：在方法入口立即把参数交给一个「由自己关闭」的持有者（如 `try (var in = input) { ... }`，Java 9+），或先捕获引用再在 finally 中无条件关闭；不得依赖后续步骤是否成功。

## NULL：空值与 Optional

> `null` 是 Java 的默认值，不是「没有值」的显式编码；`Optional` 只解决返回值一侧。

- **JAVA-NULL-001**（blocker）：`Optional` 只用于**方法返回类型**；禁止用作字段、方法参数、集合元素或 `Optional<Optional<T>>`。
  > 为什么：Optional 参数迫使所有调用方包装、字段 Optional 可被赋 null（反而多一层空值）、集合元素用 Optional 会让序列化与 `equals` 语义混乱。Optional 的设计意图见 `java.util.Optional` 类文档（「primarily intended for use as a method return type」）。
  > 例外：返回类型为 Optional 且可为空的 API 在 Java 8 之前已发布的，迁移期可保留字段形态，须注明。

- **JAVA-NULL-002**（blocker）：构造 `Optional` 时的空值必须经 `Optional.ofNullable`；`Optional.of(null)` 抛 NPE（实测），`map`/`filter` 返回的 Optional 也不得再 `get()` 而不判空。
  > 正例：`return Optional.ofNullable(map.get(key));`；反例：`Optional.of(list.get(0))`。
  > `orElse(fallback)` 的 fallback **总是求值**（实测），有副作用或昂贵构造时用 `orElseGet(() -> fallback())`。

- **JAVA-NULL-003**（blocker）：公开 API 的返回值禁止为 `null` 集合或数组——返回 `Collections.emptyList()` / `List.of()` / 空数组。
  > 为什么：调用方对「空」与「无」的判空分支几乎从未写全，返回 null 集合是把 NPE 推给每个调用方。
  > 边界：确实需要表达「没有结果」时返回 `Optional`（返回值侧）或抛出契约声明的异常，不要用 null。

- **JAVA-NULL-004**（warning）：公共方法的非空参数用 `Objects.requireNonNull(arg, "arg")` 在入口快速失败（Java 7+）；对**集合**批量校验用 `List.copyOf`（Java 10+，顺带复制与判空）；**数组不能直接交给 `List.copyOf`**——它的参数是 `Collection<? extends E>`，`List.copyOf(int[])` / `List.copyOf(String[])` 均编译失败（实测 JDK 25：`需要: Collection<? extends E>`）。数组按元素类型分开处理：
  - **基本类型数组**（`int[]` / `long[]` …）：`Arrays.stream(arr).boxed().toList()`（Java 16+；较早版本用 `.boxed().collect(Collectors.toList())`）——实测得到 `[1, 2]`。注意 `Arrays.asList(int[])` 不展开，见 JAVA-COLL-002。
  - **引用类型数组**（`String[]` …）：`List.of(arr)`（Java 9+，不可变，元素含 null 时抛 NPE）或 `Arrays.asList(arr)`（定长，可 `set` 不可增删）。
  > 为什么：失败点离错误源头越近，定位成本越低；`requireNonNull` 的消息会进入 NPE 的详细消息（JEP 358 起的 helpful NPE 对显式消息同样保留）。

## EQ：相等性与契约

> equals/hashCode 是 HashMap、Set、Stream.distinct 的基石；半套实现比没实现更危险。

- **JAVA-EQ-001**（blocker）：覆盖 `equals` 必须同时覆盖 `hashCode`，且 `equals` 必须标注 `@Override`、参数类型为 `Object`。
  > 为什么：只写 `boolean equals(MyType o)` 是**重载**不是覆盖（`Object.equals(Object)` 仍生效），编译器不报错，HashMap 全部键落入不同桶。
  > 检测：Error Prone `EqualsIncompatibleType` / `MissingOverride`（按所用版本核对）。

- **JAVA-EQ-002**（blocker）：禁止用 `==` 比较 `String`、装箱类型（`Integer` / `Long` / `Double` 等）、数组或任意不可保证同一实例的对象；引用比较只允许枚举常量与显式的对象同一性判断。
  > 为什么：`Integer` 的 `-128..127` 有缓存，实测 `Integer a = 127, b = 127; a == b` 为 true，`Integer a = 1000, b = 1000; a == b` 为 false——这类缺陷只在特定取值下复现。注意缓存只作用于**装箱类型**：两个 `int` 字面量比较恒为 true（`127 == 127`、`1000 == 1000` 都成立），引用比较的问题只在 `Integer` / `Long` 等上出现。
  > 做法：`Objects.equals(a, b)`（null 安全）/ `a.equals(b)`；枚举用 `==`；数组用 `Arrays.equals` / `Objects.deepEquals`。

- **JAVA-EQ-003**（blocker）：数组字段的 `equals` / `hashCode` 必须用 `Arrays.equals` / `Arrays.hashCode`（若按元素语义比较）；禁止用 `Objects.hash(基本类型数组)`（`int[]` / `long[]` 等不会被可变参数展开，走 `Object.hashCode` 的恒等哈希，实测与 `Arrays.hashCode` 结果不同）。
  > 引用类型数组（`Object[]` / `String[]`）会被可变参数展开，`Objects.hash(Object[])` 实测等价于 `Arrays.hashCode(Object[])`；但仍应按元素语义显式使用 `Arrays.hashCode`，不要依赖这条重载的隐式展开。
  > **哈希口径必须与 equals 口径一致**：`equals` 声明为顺序无关（按 key 查找的 Map/Set 语义）时，`hashCode` 也必须顺序无关——按**位置**求哈希的 `Arrays.hashCode(keys)` / `Arrays.hashCode(vals)` 在元素顺序不同但内容相同时给出不同哈希，违反 `Object#hashCode` 契约（实测 jsoup `Attributes.java:521-548`：`equals` 按键查找、`hashCode` 按数组位置，顺序互换后 `equals=true` 而哈希不同，`HashMap.get` 返回 null）。
  > **哈希约定**：顺序无关集合的哈希常用「元素与元素哈希之和/异或」这类交换律运算，且须覆盖键与值两侧。
  > 若用 record 且组件是数组，record 自动生成的 `equals`/`hashCode` 也按引用比较——必须显式覆盖（文档：`java.lang.Record` 类文档）。

- **JAVA-EQ-004**（warning）：`Comparable.compareTo` 必须与 `equals` 一致（返回值 0 ⟺ equals 为 true），否则 `TreeSet` / `TreeMap` 会静默丢元素；`Comparator` 链中不允许 null 元素混入，需用 `Comparator.nullsFirst/nullsLast` 显式处理。
  > 为什么：有序集合以 compareTo 判等，与 equals 不一致时会出现「集合里明明加了两个不相等对象，size 却是 1」。
  > **同样的成对义务适用于 hashCode**：`equals` 一旦声明为顺序无关（按 key 查找的 Map/Set 语义），`hashCode` 就必须与 `equals` 所依赖的信息一一对应——按**索引顺序**计算的 `Arrays.hashCode(keys)` / `Arrays.hashCode(vals)` 会让两个相等的实例得到不同哈希（实测 jsoup `Attributes`：`equals` 按键查找、与顺序无关；`hashCode` 对 `keys`/`vals` 数组按位置求哈希，顺序敏感，违反 `Object#hashCode` 契约）。

- **JAVA-EQ-005**（warning）：`equals` 中参与比较的字段必须不可变，`hashCode` 才能稳定；把对象放入 `HashSet` / 作为 `HashMap` 键后再修改参与哈希的字段会导致「查不到自己」。
  > 做法：优先用 `record` / 不可变类作键；可变实体不要做键，或改用 ID 作为键。

- **JAVA-EQ-006**（warning）：同一类型的重载方法之间，方法名与 Javadoc 必须声明同一套语义——`put/remove/has/get` 若同时存在大小写敏感与 `*IgnoreCase` 两个版本，`put(String, boolean)` 这类便捷重载必须明确它走哪一套，且实现与 Javadoc 一致。
  > 反例（实测 jsoup `Attributes.java:237-243`）：`put(String key, boolean value)` 的 Javadoc 写 `@param key case insensitive`，`value=true` 分支用 `putIgnoreCase`、`value=false` 分支却调用大小写敏感的 `remove(key)`——`put("CHECKED", true)` 后再 `put("checked", false)` 删不掉属性。重载间的语义漂移不会触发任何 lint，只能人工核对；审查时对「同名重载 + 大小写/规范化的 IgnoreCase 变体」逐个比对实现分支。

## NUM：数值与精度

> 二进制浮点表示不了 0.1；`BigDecimal` 的构造器不是都一样。

- **JAVA-NUM-001**（blocker）：金额、税费等十进制定点值禁止 `float` / `double`，用 `BigDecimal`；构造 `BigDecimal` 必须用 `String` 构造器或 `BigDecimal.valueOf(double)`，禁止 `new BigDecimal(double)`。
  > 为什么：`new BigDecimal(0.1)` 得到 `0.1000000000000000055511151231257827…`（实测），`BigDecimal.valueOf(0.1)` 得到 `0.1`；前者会以 34 位精度参与后续运算。
  > 检测：SpotBugs `DMI_BIGDECIMAL_CONSTRUCTED_FROM_DOUBLE`（按所用版本核对）。

- **JAVA-NUM-002**（blocker）：`BigDecimal` 的相等判断用 `compareTo(...) == 0`，禁止 `equals`——`equals` 比较 scale（`1.0` 与 `1.00` 不相等，实测），`compareTo` 比较数值。
  > 例外：业务确实要求「表示形式相同才算相等」（如序列化字段对比）时用 equals，须注明。

- **JAVA-NUM-003**（blocker）：整数运算必须评估溢出——`int`/`long` 溢出**静默回绕**（实测 `Long.MAX_VALUE + 1 == Long.MIN_VALUE`），参与尺寸、索引、金额下游运算时用 `Math.addExact` / `subtractExact` / `multiplyExact` 或 `BigInteger`。
  > 为什么：`Math.abs(Integer.MIN_VALUE)` 仍是 `Integer.MIN_VALUE`（文档），取绝对值后判断正负是错误写法。
  > 边界：计数器、哈希扰动等明确接受回绕的场景可豁免，须在紧邻注释说明。

- **JAVA-NUM-004**（warning）：浮点比较禁止 `==` / `!=`——`NaN != NaN` 恒为 true、`-0.0 == 0.0` 恒为 true 而 `Double.compare(-0.0, 0.0)` 返回 -1（均实测）；用 `Double.compare` / `Float.compare`，或按业务容差 `Math.abs(a - b) <= eps`。
  > 为什么：直接比较会让 `NaN` 悄悄通过「不等于」分支；`-0.0` 与 `0.0` 在哈希容器与比较器中行为不一致。

- **JAVA-NUM-005**（warning）：整数除法向零截断（`-7 / 2 == -3`，实测）、`-7 % 2 == -1`；用于取模索引、分组、环状缓冲时须先处理负数（如 `Math.floorMod`）。
  > 为什么：负数取模仍为负，直接做数组下标会 `IndexOutOfBoundsException`。

## STR：字符串、编码与本地化

> 默认 Locale 与默认 Charset 是部署环境的属性，不是程序的属性。

- **JAVA-STR-001**（blocker）：文件、网络、压缩流等 I/O 的编解码必须显式指定 `Charset`（优先 `StandardCharsets.UTF_8`）；禁止依赖默认平台编码的 API：`new String(byte[])`、`String.getBytes()`、`new InputStreamReader(in)`、`new FileReader(file)`。
  > 为什么：默认编码随平台/JVM 启动参数变化（本机为 UTF-8，Windows 默认区域设置下常见 GBK），同一份数据在不同环境产生乱码或替换字符。
  > 边界：`Files.readAllLines(Path)`、`Files.newBufferedReader(Path)`、`Files.lines(Path)` 等 NIO 便捷方法**固定使用 UTF-8**（JDK 文档），不属于「平台默认编码」清单，不按本条判；需要非 UTF-8 时仍应显式传 `Charset`。实测（JDK 25，`-Dfile.encoding=GBK`）用 `Files.readAllLines(Path)` 读 GBK 字节会抛 `MalformedInputException`，证明它并未走平台默认 GBK。
  > 检测：SpotBugs `DM_DEFAULT_ENCODING`、Error Prone `DefaultCharset`（按所用版本核对）。

- **JAVA-STR-002**（blocker）：面向用户的格式化、大小写转换、排序必须显式传 `Locale`；格式化用 `String.format(Locale.ROOT, ...)`，大小写用 `toLowerCase(Locale.ROOT)` / `toUpperCase(Locale.ROOT)`，比较用 `equalsIgnoreCase`。
  > 为什么：`String.format("%.2f", 1234.5)` 在德语默认 Locale 下输出 `1234,50`；`String.format("%d", n)` 在 `ar-EG` 下输出阿拉伯-印度数字（如 U+0662），生成的字符串回灌解析器/选择器直接失败（实测 jsoup `Element.java:949` 的 cssSelector 生成 `:nth-child(%d)`，ar-EG 下产出 `p:nth-child(?)` 并抛 `SelectorParseException`）；土耳其语 Locale 下 `"I".toLowerCase()` 得到 `ı` 而非 `i`，协议字段比较必坏。
  > **例外（不判）**：①仅用于「大小写**分类**」的 `toLowerCase().equals(toUpperCase())` 形态（判断字符是否可大小写，不依赖转换结果本身）不受 Locale 影响——实测 `tr`/`lt`/`az` 在 BMP 全字符上该比较的布尔值一致（jsoup `TokenQueue.java:163` 即此用法）；②确实要按用户所在区域展示时显式传用户 Locale，不要「不传」碰运气。

- **JAVA-STR-003**（blocker）：`String.length()` 与 `charAt` 以 UTF-16 code unit 计，不是「字符数」；含 emoji / 增补平面字符的输入按 code point 处理（`codePointCount` / `codePoints()` / `Character.*` 的 int 重载），截断、定长校验、长度上限都必须先明确口径。
  > 实测：`"😀".length() == 2` 而 `codePointCount == 1`。按 length 截断可能切断代理对，产生非法字符串。

- **JAVA-STR-004**（blocker）：`String.replaceAll` / `replaceFirst` / `Pattern.compile` 的替换字符串中 `$` 与 `\` 有特殊含义，外部可控的替换内容必须先经 `Matcher.quoteReplacement`。
  > 实测：`"abc".replaceAll("b", "$")` 抛 `IllegalArgumentException: Illegal group reference`；`\` 则把用户文本变成转义序列。
  > 同理，外部可控的**正则**本身就是注入面：字面量匹配用 `Pattern.quote`。

- **JAVA-STR-005**（warning）：`String.split(regex)` 会丢弃尾部空串（实测 `"a,b,,".split(",")` 得到 `[a, b]`）；需要保留时用 `split(regex, -1)`。`split(".")` 按字符而非点号切分，需转义为 `"\\."`（Java 字符串字面量里再转义一次；直接写 `"\."` 编译失败，实测 JDK 25 报 `非法转义符`）。
  > 为什么：CSV 字段、路径分段等场景丢尾部空列会造成解析错位。

- **JAVA-STR-006**（warning）：循环内拼接字符串必须用 `StringBuilder`（或 `String.join` / `Collectors.joining`）；`+` 只允许用于非循环的少量拼接与常量表达式。
  > 为什么：`s += x` 在循环内每次创建新 String，复杂度 O(n²)；JDK 9+ 只把**单个表达式**内的 `+` 编译为 `invokedynamic`，跨迭代的累加不在此列。

- **JAVA-STR-007**（warning）：`trim()` 只去掉 `<= U+0020`，`strip()`（Java 11+）按 `Character.isWhitespace` 去空白；处理用户输入的空白裁剪用 `strip()`，`isEmpty()` 判空之外还应考虑 `isBlank()`（Java 11+）。

## COLL：集合与容器

> 不可变集合是默认选择；每次可变都换来一份「谁能改」的审计负担。

- **JAVA-COLL-001**（blocker）：`List.of` / `Set.of` / `Map.of` / `List.copyOf` 等不可变工厂**不接受 null 元素与 null 键值**（实测 `List.of("a", null)` 抛 NPE）；从可能含 null 的数据构造时先过滤或用允许 null 的构造方式，且不要把它们的返回值再交给会调用 `add`/`put` 的代码。
  > 为什么：不可变集合的 `add` 抛 `UnsupportedOperationException`（实测 `List.copyOf`）；`Arrays.asList` 则相反——可 `set`、不可增删，两者容易混淆。

- **JAVA-COLL-002**（blocker）：`Arrays.asList(array)` 对**基本类型数组**不展开，`Arrays.asList(new int[]{1,2}).size() == 1`（实测），元素是 `int[]` 本身；需要元素列表时用包装类型数组或 `Arrays.stream(ints).boxed().collect(...)`。
  > `List.of(intArray)` 同理（单个元素）。`Objects.hash(intArray)` 的陷阱同源，见 JAVA-EQ-003。

- **JAVA-COLL-003**（blocker）：`List<Integer>` 等装箱列表的 `remove` 有两组重载：`remove(int)` 删**下标**、`remove(Object)` 删**元素**（`list.remove(1)` 删的是下标 1）。删元素时显式装箱（`remove(Integer.valueOf(v))`）或改用 `removeIf` / `Iterator.remove`。
  > 为什么：编译期按重载解析选 `remove(int)`，不报警告，删除的对象与预期完全不同。

- **JAVA-COLL-004**（blocker）：遍历集合时禁止结构性修改（`add`/`remove`）原集合；需要条件删除用 `Collection.removeIf` 或 `Iterator.remove`，否则抛 `ConcurrentModificationException`（仅尽力检测，文档）。
  > 边界：单线程的 `CopyOnWriteArrayList` / `ConcurrentHashMap` 有各自语义，按类文档判定，不属本条豁免的自动理由。

- **JAVA-COLL-005**（blocker）：`Collectors.toMap` 遇到重复键抛 `IllegalStateException`（实测），必须提供 merge 函数或改用 `groupingBy`；从不可信输入归集时不允许默认行为。
  > 正例：`Collectors.toMap(k, v, (a, b) -> b)`。

- **JAVA-COLL-006**（warning）：`HashMap` / `HashSet` 的迭代顺序未定义，断言、序列化输出、日志排序不得依赖其顺序；需要顺序时用 `LinkedHashMap` / `TreeMap`（显式比较器）或对结果排序。`Collectors.groupingBy` 默认返回 `HashMap`，需要顺序时用四参数重载指定 `LinkedHashMap`。
  > 为什么：同一 JVM 版本下顺序看似稳定，升级 JDK 或改变容量即变化，测试与快照最先崩。

- **JAVA-COLL-007**（warning）：`subList` / `keySet` / `values` / `Arrays.asList` 返回的是**视图**，底层结构修改后其行为未定义（文档：`List.subList`「undefined behavior」）；跨方法传递视图须立即 `List.copyOf` / `new ArrayList<>(...)` 固化。
  > 为什么：视图被持有后底层增删，读视图得到 `ConcurrentModificationException` 或陈旧数据。

- **JAVA-COLL-008**（warning）：以枚举为键/元素时用 `EnumMap` / `EnumSet`（紧凑、按序号顺序迭代）；禁止用 `ordinal()` 作为持久化值或索引（`Enum` 文档明确 discourages），需要稳定编码时显式定义 `code` 字段并映射。

## EXC：异常

> 异常是契约的一部分；吞掉异常等于把故障变成静默数据损坏。

- **JAVA-EXC-001**（blocker）：禁止吞异常——空 `catch`、只 `e.printStackTrace()`、`catch (Exception e) {}` 后继续执行（G-SWALLOW）。要么传播（可包装，但保留 cause），要么在紧邻处注释「有意忽略及理由」。
  > 反例：`try { ... } catch (IOException e) { log.error("failed"); }` 后返回值仍被当作成功。
  > `printStackTrace()` 写 stderr、不经日志框架、丢失上下文，不能替代记录。

- **JAVA-EXC-002**（blocker）：包装异常必须用带 cause 的构造器（`new ServiceException("msg", e)`），禁止 `new RuntimeException(e.getMessage())` 之类丢失原始栈与类型。
  > 为什么：只剩字符串的异常无法 `instanceof` 区分、无法看到根本原因帧；排查时只能猜。

- **JAVA-EXC-003**（blocker）：捕获 `InterruptedException` 后必须传播或恢复中断标志（`Thread.currentThread().interrupt()`）；禁止吞掉后继续阻塞运算。
  > 为什么：中断标志被清除后，上层无法得知应停止，任务可能无限运行；这是线程池 shutdown 失灵的常见根因。

- **JAVA-EXC-004**（blocker）：禁止 `catch (Throwable)` / `catch (Error)`——除 main、线程入口、框架边界层（并须重新抛出 `Error`）。`OutOfMemoryError`、`StackOverflowError` 被吞后程序处于未定义状态。
  > 允许形态：`catch (Throwable t) { try { handle(t); } finally { throw t; } }` 或等价的结构化写法，目的是清理而非恢复。

- **JAVA-EXC-005**（warning）：不要用异常表达可预期的控制流（循环退出、存在性判断）；`NoSuchElementException`、`NumberFormatException` 作为正常分支处理会污染性能剖析并掩盖真实错误。先查 `containsKey` / 用 `Optional` / 用返回值。

- **JAVA-EXC-006**（warning）：自定义受检异常应继承 `Exception`，不可恢复的契约违反继承 `RuntimeException`；禁止继承 `Throwable` / `Error`。受检异常跨模块泄漏前评估是否应包装为本模块异常（避免上层依赖下层实现）。

## CONC：并发

> Java 的内存模型默认不给你可见性保证；`volatile` 给可见性，不给原子性。

- **JAVA-CONC-001**（blocker）：共享可变状态必须用 `java.util.concurrent` 的同步原语（`synchronized` / `ReentrantLock` / `Atomic*` / 并发集合）保护；`volatile` 只保证可见性与禁止重排，`count++` 等复合操作仍必须用 `AtomicInteger` 或锁。
  > 为什么：`volatile int count; count++;` 是读-改-写三步，两线程并发丢更新。

- **JAVA-CONC-002**（blocker）：`Object.wait()` 必须在 `while` 循环中检查条件（或等价的 `Condition.await` 循环），禁止 `if`——虚假唤醒（spurious wakeup）会让条件不成立时继续执行。
  > `wait(timeout)` 的返回值也要在同一循环中重新判断；超时后未满足条件不得当成功处理。

- **JAVA-CONC-003**（blocker）：禁止直接 `new Thread(...)` 运行业务任务；用 `ExecutorService` / `ForkJoinPool` / 虚拟线程执行器统一管理生命周期与背压。
  > 为什么：裸线程无上限、无监控、无关闭语义；`Thread.stop()` 是废弃且不安全的终止方式（无法保证对象一致性），禁止用作「关闭」手段。

- **JAVA-CONC-004**（blocker）：多锁场景必须固定全局加锁顺序并在代码中声明；禁止在持锁期间调用外部回调 / 执行 I/O（可能长时间持锁或反向获取锁）。
  > 为什么：加锁顺序不一致即死锁；持锁 I/O 把锁的持有时间交给网络与磁盘。

- **JAVA-CONC-005**（warning）：线程池中的 `ThreadLocal` 在任务结束前 `remove()`（`finally` 中）；静态 `ThreadLocal` + 复用线程 = 上一次请求的数据泄漏给下一次请求。
  > `SimpleDateFormat` / `DecimalFormat` 不是线程安全的（文档：`DateFormat`「Date formats are not synchronized」），禁止作为静态共享字段，改用线程安全的 `DateTimeFormatter`（文档：immutable and thread-safe）或每线程实例。

- **JAVA-CONC-006**（warning）：懒加载的双重检查锁定必须用 `volatile` 修饰被发布字段；`CompletableFuture` 的异常必须经 `exceptionally` / `handle` / `whenComplete` 处理，`thenApply` 链上的异常会静默停留在 future 内。
  > 为什么：非 volatile 版本的 DCL 在 JMM 下允许看到「部分构造」对象；未处理异常的 future 无人感知，等价于丢弃任务结果（G-SWALLOW）。

- **JAVA-CONC-007**（warning）：JDK 21+ 虚拟线程上的阻塞调用须按版本核对：JDK 24 起（JEP 491）`synchronized` 块不再 pin 载体线程，但 native / JNI 阻塞调用仍会占用载体线程；不要在虚拟线程中做长时间 native 阻塞，改用可中断的替代实现。

## TIME：时间

> `Date` 与 `Calendar` 是可变的、非线程安全的遗留类型；新代码一律 `java.time`。

- **JAVA-TIME-001**（blocker）：新代码禁止 `java.util.Date` / `Calendar` / `SimpleDateFormat`；用 `java.time`（`Instant` / `ZonedDateTime` / `LocalDate` / `Duration` / `Period` / `DateTimeFormatter`）。与外部 API 交互必须转换时，在边界层转换并注释。
  > 检测：Error Prone `JdkObsolete`（覆盖 `Date` / `Calendar` / `SimpleDateFormat` 等，按所用版本核对）。

- **JAVA-TIME-002**（blocker）：跨时区的时刻必须用 `Instant` 或 `ZonedDateTime`；`LocalDateTime` 只表示「墙上时间」，禁止用于存储绝对时刻、参与跨时区比较或计算时间差。
  > 为什么：`LocalDateTime` 没有偏移量，夏令时切换日的两段「1:30」无法区分，跨时区调度会算错。

- **JAVA-TIME-003**（warning）：`LocalDateTime.atZone(zone)` 在夏令时**间隙**会把 02:30 静默顺延到 03:30、在**重叠**段取较早的偏移（实测，2026-03-08 / 2026-11-01 America/New_York）；涉及定时调度、营业时间计算的逻辑必须显式定义这两类边界的行为。
  > 实测值：gap → `2026-03-08T03:30-04:00`；overlap → `2026-11-01T01:30-04:00`（较早偏移）。

- **JAVA-TIME-004**（warning）：`Period` 表示日历日期差、`Duration` 表示精确时间差，不可互换；`ChronoUnit.MONTHS.between` 按整月截断（实测 `2026-01-31 → 2026-03-01` 为 1 个月），业务要求「自然月」时须定义口径（`Period` / 业务规则），不要默认按天数除 30。

- **JAVA-TIME-005**（warning）：时间来源必须可注入——直接调用 `Instant.now()` / `LocalDate.now()` / `System.currentTimeMillis()` 的代码不可测；把 `Clock` 作为依赖传入（`Instant.now(clock)`），生产注入 `Clock.systemUTC()`。

## SEC：安全

> Java 生态的默认值是「功能优先」，安全项几乎都要显式打开。

- **JAVA-SEC-001**（blocker）：密码、API 密钥、Token、私钥禁止以字符串字面量写入源码；用环境变量、外部配置或密钥管理服务。日志与异常消息中同样禁止输出（含 `toString()` 泄露字段的 DTO）。（G-SECRET）
  > 含密字段的 `toString` / `equals` / 序列化须脱敏；打印对象整体前先确认其字段。

- **JAVA-SEC-002**（blocker）：外部命令必须用 `ProcessBuilder` 的参数列表形式，禁止拼接字符串交给 `sh -c` / `cmd /C` / `bash -c`；可执行文件路径须白名单校验，用户输入不得进入可执行路径或解释器参数。（G-CMDINJ）
  > `ProcessBuilder` 本身不经 shell 解析，但传入的**第一个参数**若是 shell，用户输入会重新变成命令。

- **JAVA-SEC-003**（blocker）：处理用户可控路径拼接必须防穿越：`base.resolve(user).normalize()` 后校验 `startsWith(base.normalize())`，且拒绝 `user` 为绝对路径（`resolve` 遇绝对路径直接替换基路径）；目标存在时用 `toRealPath()` 解析符号链接再校验。
  > 为什么：仅 `normalize()` 不解析符号链接，也不阻止 `resolve` 被绝对路径替换；字符串拼接（`base + "/" + user`）在 Windows 下还会被 `\` 与盘符绕过。

- **JAVA-SEC-004**（blocker）：解析不可信 XML 必须禁用 DTD 与外部实体：`DocumentBuilderFactory` / `SAXParserFactory` 设 `disallow-doctype-decl` 为 **true**，`external-general-entities` / `external-parameter-entities` 为 **false**，并设 `XMLConstants.ACCESS_EXTERNAL_DTD` / `ACCESS_EXTERNAL_SCHEMA` 为空；`TransformerFactory` 同理。
  > 极性必须核对：`http://apache.org/xml/features/disallow-doctype-decl` 为 **true** 才表示「禁止 DOCTYPE」，写成 false 等于允许 DTD 声明。OWASP XXE 防护速查表的基准配置即 `dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)`；后两项 external-entities 才是 false。
  > 为什么：XXE 可读取本地文件、发起 SSRF；仅设 `setExpandEntityReferences(false)` 不够。
  > **触发条件按实际解析入口判定，不按是否 `newInstance`**：只有存在 `builder.parse(...)`（或等价的 SAX `XMLReader.parse`）时才需要本组加固；仅用 `newDocumentBuilder().newDocument()` 构造 DOM、或用 `TransformerFactory` 从**内部已构建**的 DOM 序列化为字符串，不涉及外部 XML 解析，不适用本条（实测 jsoup `W3CDom.java:204-206` 只用 `newDocument()`、`:128` 的 `TransformerFactory` 只做序列化——按「见到 factory 即报」会误报）。

- **JAVA-SEC-005**（blocker）：不可信数据禁止走 Java 原生反序列化（`ObjectInputStream.readObject`），用 JSON 等数据格式并配合白名单过滤器（`ObjectInputFilter`，JEP 290）；`Serializable` 类型不得暴露可变内部状态。
  > 为什么：原生反序列化可在反序列化阶段执行 gadget 链代码，早于任何业务校验。

- **JAVA-SEC-006**（blocker）：安全场景（密码哈希、令牌、签名）禁止 MD5 / SHA-1；密码用 PBKDF2（`PBEKeySpec`）/ bcrypt / argon2，随机数用 `SecureRandom` 而非 `java.util.Random` / `Math.random()`。
  > 为什么：`Random` 是可预测的线性同余序列；`Math.random()` 内部就是它的单例。

- **JAVA-SEC-007**（blocker）：SQL 必须用 `PreparedStatement` 参数绑定，禁止字符串拼接用户输入；动态表名/列名无法参数化时须白名单校验。
  > 违反即 SQL 注入；ORM 的字符串拼接查询（如 JPA `createQuery("... " + input)`）同属违规。

- **JAVA-SEC-008**（warning）：TLS 连接禁止关闭证书链或主机名校验（自定义 `TrustManager` 全接受、`HostnameVerifier` 恒 true）；`URLConnection` 默认连接/读取超时均为 0（无限等待，实测），对外请求必须显式设置超时。

## LOG：日志

- **JAVA-LOG-W001**（warning）：库代码不得用 `System.out` / `System.err` 当日志，也不得只 `printStackTrace()`；用 SLF4J 或 `System.Logger` 门面，由应用决定实现与级别（G-LOG）。
  > 为什么：库直接写 stdout 污染调用方输出，无法统一关闭或分级；`printStackTrace()` 绕过日志框架的采集与脱敏。

- **JAVA-LOG-W002**（warning）：日志占位符用参数化形式（`log.info("user={}", id)`），禁止先拼接字符串再打日志；参数含敏感字段时显式脱敏。
  > 为什么：参数化只在级别启用时才格式化；拼接则会无条件求值并在字符串里留下可被采集的敏感值。

## NAME：命名

- **JAVA-NAME-001**（warning）：遵循 Java 约定——包名全小写（无下划线）、类/接口/枚举/record 用 `UpperCamelCase`、方法与变量用 `lowerCamelCase`、常量（`static final`）用 `UPPER_SNAKE_CASE`；禁止 C 风格的 `m_` / `s_` / `g_` 成员前缀与匈牙利命名。
  > 泛型类型参数单字母（`T`、`E`、`K`、`V`）属约定用法，不受本条约束。
  > **噪声控制**：常量命名只约束 `public` / `protected`（即对外契约面）的 `static final`；`private` / 包内常量不做逐条报——实测 jsoup 188 个 `static final` 中 170 个非 `UPPER_SNAKE`，逐条报会淹没真 blocker。同一文件内**混用**两种风格仍须记 warning（局部一致性）。
  > 检测：Checkstyle `TypeName` / `MethodName` / `ConstantName` / `MemberName`（按所用版本核对）。

## BUILD：构建与工具链

- **JAVA-BUILD-001**（blocker）：编译必须开启 lint 且警告清零：`javac -Xlint:all -Werror`（Maven 通过 `maven-compiler-plugin` 的 `<compilerArgs>` 配置）；使用新 JDK 编译旧目标字节码时必须用 `--release` 而不是 `-source`/`-target`。
  > 为什么：`-source 8 -target 8` 在新 JDK 上仍可链接新的 JDK API（如 `List.of`），运行时在 Java 8 上抛 `NoSuchMethodError`；`--release 8` 用对应版本的 `ct.sym` 签名表校验 API 可用性。
  > **生效位置陷阱（实测）**：`<release>` 必须写在**会实际执行的 execution** 里。写在未绑定 phase/goal 的 `<execution>` 中会被 Maven 忽略，最终退化为 `-source 1.8 -target 1.8`——实测 jsoup `pom.xml:55-62` 的 `compile-java-8` execution 只配了 `source`/`target`、其 `<release>8</release>` 放在 `compile-multi-release` profile（`:316-324`）的同 id execution 里，`mvn -X` 显示 `default-compile` 的生效参数为 `source=1.8, target=1.8`、**无 release**。判定必须读 `mvn -X` 的 `(f) source` / `(s) release` 等生效参数，不得复制 POM 文本。判断「是否漏 API 校验」可用对照：`javac --release 8` 对该源码产生的 `-Xlint:all` 警告数与 `-source/-target` 相同（实测 jsoup 主源 33 条警告），但 `--release` 会额外拒绝不存在的 JDK API——样本近期的 API 已在 `--release 8` 下可编译，因此该缺陷的实际后果限于「lint 未开启 + API 校验退化」。
  > 检测：Error Prone / SpotBugs / PMD 可作为补充门禁，但必须配置在构建文件中并作为 CI 必过项，不能只写在文档里。

- **JAVA-BUILD-002**（warning）：不要使用 `@Deprecated(forRemoval = true)` 的 API，也不要依赖已被标记为「removal」的运行时设施（如 `Object.finalize()`，JEP 421 起 deprecated for removal）；需要确定性清理时用 try-with-resources，需要兜底清理时用 `java.lang.ref.Cleaner`。
  > 为什么：for-removal 的 API 在未来的 JDK 中会直接消失，升级即编译失败；`finalize` 的执行时机与是否执行都没有保证。

- **JAVA-BUILD-003**（warning）：生成的源码（`target/generated-sources`、注解处理器、JPA 元模型、ANTLR 产物）不得手改；风格类问题（NAME / LOG / MAGIC）对生成代码不阻塞，安全类 blocker（SEC / RES / EXC）仍须在生成配置或调用边界修复。

## MAGIC：魔法值

- **JAVA-MAGIC-001**（blocker）：有业务/领域语义的字面值必须是 `static final` 常量、`enum` 或配置项；`0` / `1` / `-1` / 空串 / 布尔及上下文自明的惯用值除外（G-MAGIC）。
  > 反例：`if (status == 3)`、`Thread.sleep(86400000)` 散落在业务代码中。
  > **上下文自明豁免（不判）**：协议/规范定义的标准状态码与常量（HTTP `200` / `404` / `500` 等其余四项在 `HttpURLConnection` 已有具名常量可优先改用，但裸写本身不判）、字符与编码边界（`0x7F`、`0xFF`、`0x10000`、`0x10FFFF`、UTF-8 多字节长度 `2`/`3`/`4`）、位运算掩码（`0x0F`、`0xFF`）——这些值本身就是语义（协议/编码规格的一部分），命名常量不会带来更多信息。

## 本语言专属豁免

通用豁免（测试/基准/SQL/架构，按语言）见 `code-rules/SKILL.md`『豁免』。以下是 Java 特有条目：

- **测试/基准**：`src/test/`、`src/testFixtures/`、`*Test.java`、`*Tests.java`、`*IT.java` 用例设计使用 `test-author`、质量审查使用 `test-review`；JMH（`src/jmh/`、`@Benchmark`）只豁免本文的**语言规则**，`G-SECRET` / `G-CMDINJ` 仍适用。
- **`module-info.java`**：只声明模块导出与依赖，不应用本文件的编码规则；其导出面归 `arch-review` 判定。
- **`package-info.java`**：只放包级 Javadoc 与包级注解，不适用编码规则。
- **Lombok / 注解处理器生成的代码**：规则作用于源文件（注解、字段、getter 是否该生成的判断按源码），生成产物本身不在审查面；但 `@Data` 会生成 `equals`/`hashCode`，用于可变实体或含数组字段的类型时按 JAVA-EQ-003/005 在源文件层判定。
- **record / 不可变值类**：自动生成的 `equals`/`hashCode`/`toString` 不按 JAVA-EQ-001 的「必须手写」判定；数组组件的例外见 JAVA-EQ-003。
- **迁移期 `Date`/`Calendar`**：已有代码边界层可保留，新代码与新增字段仍按 JAVA-TIME-001 判定；不得因「整个模块都没迁」而整体豁免。
- 其余规则无一例外。
