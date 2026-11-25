# Java 测试审查参考（test-review / references）

> 由 test-review 在测试文件为 Java（`src/test/**`、`src/testFixtures/**`、`*Test.java`、`*Tests.java`、`*IT.java`）时加载。通用判据见 `test-review/SKILL.md`；本文提供 **Maven Surefire/Failsafe 与 Gradle Test 的执行证据获取方式**、JUnit 5 / Mockito 的跳过与假绿形态词表，以及 Java 项目中最容易造成误判的陷阱。工具行为引自官方文档或实测；无法取得构建/运行证据时记「未能判定（缺构建/运行证据）」。

## 一、执行证据获取（EXEC-001 / EXEC-002 / EXEC-006）

### 1.1 构建配置与目标清单（EXEC-001；ORG-001/002/003）

- **Maven 测试源目录**：默认 `src/test/java`（`maven-compiler-plugin` 的 `testCompile` 编译面），测试资源在 `src/test/resources`。改过 `<testSourceDirectory>` 的项目以 POM 为准。
- **测试文件是否被运行**由运行器的 **include 模式**决定，而不是文件是否存在。默认模式（官方文档：Surefire `test` mojo「includes」/ Failsafe `integration-test` mojo「includes」）：
  - Surefire（`mvn test`）：`**/Test*.java`、`**/*Test.java`、`**/*Tests.java`、`**/*TestCase.java`；默认排除 `**/*$*`（内部类）。
  - Failsafe（`mvn verify`）：`**/IT*.java`、`**/*IT.java`、`**/*ITCase.java`。
  > 由此产生的两个高频盲区：①放在 `src/test/java` 的 `*IT.java` **不会被 `mvn test` 执行**，且执行它的前提是 failsafe 插件**真的绑定了** `integration-test`/`verify` goal——绑定位置有两个（实测 jsoup 1.18.3 两处都有）：主 `<build><plugins>` 里（`mvn verify` 默认执行 IT，execution id 为 `default`）或仅在某个 `<profile>` 里（不激活该 profile 就永不执行）。**不要假设「IT 一定靠 profile 触发」**，以 `mvn help:effective-pom` 或实际 `mvn verify` 输出中的 execution id 为准；②`IntegrationFoo.java`、`*IntegrationTest` 之外的任意命名（如 `FooChecks.java`）都不匹配默认模式。判 EXEC-001/002 必须把**源码文件清单与模式集合做匹配**，再看实际运行输出，不要默认「在 `src/test/java` 就等于会跑」。
- **匹配模式 ≠ 类里有测试**（实测 jsoup）：`AuthenticationHandlerTest.java` 命名匹配 Surefire，但类里**一个 `@Test` 都没有**（是给隔壁测试类可见性用的辅助类），不会生成任何报告条目；同理 `TestServer.java` 被 `**/Test*.java` 模式命中但只是辅助类。差集时按「匹配但无报告」逐项回读源码确认是辅助类还是漏跑，不要一律报「未执行」。
- **内部类测试不会被 Surefire 默认发现**：默认排除 `**/*$*`。JUnit 5 的 `@Nested` 只有嵌在同类里才随外层类执行；把测试写在顶层类的 static 嵌套类里、而该类自身不匹配命名模式时，整个内层用例静默不跑。
- **构建跳过开关**（整块缺席，最容易误判为「全绿」）：
  - `-DskipTests`：仍编译测试源，只是不执行；`-Dmaven.test.skip=true`：测试源连编译都跳过（插件文档：Surefire `skipTests`/`maven.test.skip`）。
  - POM 中 `<skipTests>true</skipTests>`、profile 里给 surefire 配 `<skip>`、Gradle `test.enabled = false`。
  - 判据：先读 POM/CI 脚本中这些开关的实际取值，再看运行报告；报告不存在或为空不等于「通过」。

### 1.2 注册与执行范围（EXEC-002）

- **Surefire 的注册证据是运行报告，不是 POM 文本**：执行后 `target/surefire-reports/` 下有每个测试类的 `TEST-<FQCN>.xml`（机器可读）与 `.txt`（摘要）。`tests` / `failures` / `errors` / `skipped` 是 XML 根属性；每个用例是 `<testcase>`，其下的 `<failure>` / `<error>` / `<skipped>` 子元素给出状态。**没有报告目录 = 没跑或跑了 0 条**，两种都要查明原因。
- **Maven 多模块**：在聚合根执行 `mvn test` 会逐模块执行并各自生成 `<module>/target/surefire-reports`；只查根目录会漏掉全部子模块报告。`mvn -pl <module> test` 只跑单模块，不能作为全量证据。
- **`failIfNoTests` 默认 false**（Surefire 文档）：一个模块如果没有匹配任何测试，构建照样成功且**不生成报告**。"BUILD SUCCESS 但零报告"是「测试静默缺席」的典型形态，按 EXEC-001/002 记录，不要当通过。
- **`-Dtest=...` 过滤**（Surefire `test` 参数）：默认 `surefire.failIfNoSpecifiedTests=true`，过滤没匹配到会失败——这是好事；但若项目把该属性调成 false，过滤拼错也会静默全跳过。**不要用过滤运行作为「套件全跑」的证据**。
- **JUnit 4 需要 Vintage 引擎**：JUnit 5 平台只发现 Jupiter 注解；`org.junit.Test` 用例必须把 `junit-vintage-engine`（JUnit 6 起已弃用）放进测试类路径才会执行（官方文档：JUnit User Guide「JUnit Vintage」）。同时存在 JUnit 4 与 5 注解的项目，先确认引擎齐全，再按名字对账。
- **Gradle**：`java` 插件的 `test` 任务用 JUnit Platform 时必须配 `useJUnitPlatform()`，否则 JUnit 5 用例**不被发现**、任务绿着通过；自定义 source set（如 `src/integrationTest/java`）只有显式创建 `integrationTest` 任务并挂到 `check` 才会执行，否则连编译都可能不发生。报告：`build/test-results/test/TEST-*.xml`（含 `skipped` 状态）与 `build/reports/tests/test/index.html`。

### 1.3 计数与对账（EXEC-006）

- **按用例 FQCN + 方法名对账**：源码中的 `@Test` 方法数 ↔ 报告的 `<testcase name>` 集合做双向差集；名字用 `classname` + `name` 两列归一化（方法名可能带参数化后缀 `[1]`、`[2]`）。
- **`@ParameterizedTest` 一条声明展开为多条用例**（每行参数一条），`@TestFactory` 动态生成用例名——声明数 ≠ 运行数属**正常**，差额必须能由参数行数/动态生成逻辑解释。
- **`@RepeatedTest`** 展开为 `repetition 1 of N` 多条；源码计 1、报告计 N。
- 不要用「报告总数 − 源码声明数」直接判红，先按上述展开规则归一化，再对差异逐条回读源码。

## 二、跳过形态词表（EXEC-003 / EXEC-005）

- `@Disabled` / `@Disabled("理由")`：方法级或类级；**类级 `@Disabled` 会连带跳过整个类**。实测报告形态：类级无理由时 `<skipped message="class org.jsoup.integration.UrlConnectTest is @Disabled"/>`；方法级无理由时 message 只含方法签名（实测 `public void ...XmlTreeBuilderTest.testSupplyPa...`）。message 里没有业务理由 ≠ 不需要理由——实测 jsoup 5 处 `@Disabled` 中 **4 处**有行尾注释说明、**1 处完全裸写**（`XmlTreeBuilderTest.java:65`，上下 5 行无任何注释）。**不要假设 `@Disabled` 都有解释可读**：裸 `@Disabled` 按「无理由跳过」处理并回读用例体判断其依赖（样本中该用例访问外部 URL，理由可从代码推断，但注释机制上仍属缺失）。
- `@DisabledIf` / `@EnabledIf`（JUnit 5.7+ 内置的 `@EnabledIfSystemProperty`、`@EnabledIfEnvironmentVariable`、`@EnabledOnOs`、`@EnabledOnJre`、`@EnabledForJreRange`，以及后续版本追加的 `@EnabledInNativeImage` 等）：条件不满足时静默跳过；跳过原因在报告 `<skipped message>` 中给出表达式，但**业务理由仍需人工核对**。
  > **不存在 `@EnabledIfBuildTool`**——`org.junit.jupiter.api.condition` 包里没有任何按构建工具判定的注解（按 JUnit 6.1.3 包文档核对）。要按 Maven/Gradle 区分，只能自己用 `@EnabledIf("<全限定的静态判定方法>")` 或实现 `ExecutionCondition`，此时跳过原因由自研逻辑决定，更需人工核对。
- `@Tag("slow")` + POM 中 `<excludedGroups>` / `<groups>` 或 Gradle `useJUnitPlatform { excludeTags("slow") }`：被排除的标签在报告里**完全不出现**（不是 skipped），与「用例不存在」无法区分——必须读 POM 的标签过滤配置。
- `Assumptions.assumeTrue(...)` / `assumeFalse` / `assumingThat`：不满足时抛 `TestAbortedException`，JUnit 5 将其记为 **aborted/skipped**（官方文档：Assumptions），比 guard+return 好——它在报告里留痕。判据：只要出现在报告 `skipped` 计数里，属于「机器可见的跳过」，按 EXEC-003 核对理由与另一环境的覆盖；不满足条件就 `return` 的 guard 才是静默形态。
- JUnit 4：`@Ignore`（可带理由）、`assumeTrue`（org.junit.Assume）、`@Test(expected=...)` 不是跳过但会掩盖错误（见第三节）。
- 空用例体 / 只有 `// TODO` 的 `@Test`：编译通过、运行报绿，断言为零（ASRT-001）。
- 前置 guard + `return`（无标记、运行时报通过）：
  ```java
  @Test
  void parsesFixture() {
      Path p = Path.of(System.getProperty("fixture.path", ""));
      if (!Files.exists(p)) return;   // ← 无标记的静默跳过
      assertEquals(expected, parse(p));
  }
  ```
  判定同父技能：依赖外部资源的 guard 需能与「真的测过了」区分（显式 `assumeTrue` 或跳过标记）；只在运行时留「通过」的，按 blocker，至少记 warning。
- Profile 级整块跳过：`<profile>` 里的 surefire `<skipTests>`、`<excludes>`、CI 脚本的 `-DskipTests`。

## 三、断言可达性与假绿（EXEC-004；ASRT-001/002）

- `assertThrows(Type.class, () -> ...)` 只执行 lambda 一次；**lambda 之后的断言若不在同一用例中，抛异常后的语句永不执行**——把后续验证写在 `assertThrows` 返回值之外要确认顺序。
- 反模式：`try { ...; fail("should throw"); } catch (Exception e) { }` —— JUnit 5 的 `AssertionFailedError` 继承 `AssertionError`（`org.opentest4j.AssertionFailedError`，文档），`catch (Exception)` 吞不掉它，所以这条**看似**安全；真正的陷阱是空 `catch (Throwable)` / `catch (AssertionError)`，它把断言失败吞成通过。
- **标志位恒真的假绿（实测 jsoup `ValidateTest.java:38-45`）**：`boolean threw = true; try { ... } catch (X e) { ... } assertTrue(threw);` —— 初始值写成 `true`、catch 里又不再置位，断言恒真；被测方法**不再抛异常时用例照样绿**。正确形态是初始 `false`、在 catch 中置 `true`（同文件 `:12-19`、`:22` 的 `testNotNull` / `stacktraceFiltersOutValidateClass` 就是正确写法，可直接对照），或改用 `assertThrows`。这一形态断言存在、语法正确、覆盖率全过——只有检查「标志位的初始值与置位点」才能发现，审查时逐个核对 `boolean xxxThrown/threw/failed` 标志位。
- JUnit 4 `@Test(expected = Exception.class)`：只校验异常类型，宽类型（`Exception.class`、`Throwable.class`）几乎不具区分度；异常来源（哪一行抛的）无法验证——新用例用 `assertThrows` + `assertThrowsExactly` 并断言消息。
- Mockito `verify` 写在断言之后、或断言写在 `verify` 之前被异常中断——先确认失败时后续断言是否可达。
- 参数化用例中某行失败时，后续参数行仍会执行（每行独立用例）；但 **for 循环写成的表驱动测试一次失败即中止剩余行**——关键边界拆成参数化（`test-review` COV-003）。
- `@TestFactory` 动态测试：`DynamicTest` 的 `executable` 无断言时同样算通过（ASRT-001）；生成逻辑本身要断言非空（生成 0 条用例也会报绿）。
- Mockito 假绿：`when(...)` 对未调用的方法 stub 不报错；`verify` 未加 `times` 时默认 `times(1)`，但 `verifyNoInteractions`/`verifyNoMoreInteractions` 缺失时无法发现多余交互；`@Mock` 字段恒非 null，与其空逻辑断言混淆。

## 四、假阳性陷阱（定性前必读）

- **网络依赖失败不是代码缺陷**：分清两种形态——①真的访问外部网络/远程站点（用例依赖外部服务，属环境限制）；②**本地测试服务 + 过紧超时**（实测 jsoup `ConnectTest.handlesLargerContentLengthParseRead` 用进程内 jetty 的 `InterruptedServlet` + `.timeout(400)`，跨跑次在 `Premature EOF`(:478) 与 `SocketTimeout`(:476) 之间漂移，错误文本每次不同）——后者是**时序 flake**（DET-004 / TPERF-002 方向），属测试设计缺陷记 warning，**不是**外部环境问题；且它会让默认 `mvn test` 整体为红（样本实测 `Errors: 1, BUILD FAILURE`），报告须如实写明「默认套件本机为红」及其原因，不得当作「全绿通过」。
- **产物是活文件（实测踩坑）**：surefire/failsafe 报告会**按次运行覆盖**——`-Dtest=Foo#bar` 这类过滤运行会重写同一 `TEST-Foo.xml`（`tests` 从 N 变为 1），`mvn verify` 会刷新 failsafe 报告。审查前先记 `target/*-reports/` 的时间戳，确认全量证据来自哪次运行；拿过滤运行的报告做全量对账会得出「N-1 条用例消失」的假结论。需要全量证据时重跑 `mvn test`（不是过滤运行）并核对 `Tests run` 总数。
- **`@Disabled` 类仍会生成报告条目**：类级跳过的每个用例在 XML 中都有一条 `<skipped>`；「报告里有用例名」≠「执行过」。看 `skipped` 计数，不要看 `<testcase>` 数量。
- **Surefire 与 Failsafe 报告目录不同**：`surefire-reports` 与 `failsafe-reports` 分开；只查前者会漏评估 IT 层。`mvn test` 不触达 failsafe，`mvn verify` 才触达——但**触达的前提是 failsafe 在生效的 build 段里绑定了 goal**：绑定可在主 `<build>`（`mvn verify` 默认执行，execution id `default`）或只在 `<profile>`（须激活）。实测 jsoup 两处都有绑定，`mvn verify` 输出 `failsafe:3.5.2:integration-test (default)`；IT 共 6 个类、25 条用例（failsafe 报告与 `failsafe-summary.xml`）。
- **`*IT` 报告可能落在大杂烩目录**：实测 jsoup 的 `SelectorIT` 报告出现在 `target/surefire-reports/` 下而非 `failsafe-reports/`（surefire 目录残留/工具行为），只按目录收集会重复或漏算——收集测试报告时按 **`TEST-*.xml` 文件清单 + 时间戳**归集，再按类名去重，不要假定「目录 = 执行阶段」。
- **JVM 崩溃 / `System.exit`**：测试进程直接退出时 Surefire 生成 `*.dumpstream` / `*.dump` 文件并报 `The forked VM terminated without properly saying goodbye`；这时的「0 失败」是没跑完，不是通过。
- **并行执行**：JUnit 5 开 `junit.jupiter.execution.parallel.enabled=true`（POM/system property）后，静态可变状态、共享临时目录、端口冲突会让测试时绿时红；先看并行配置再判 DET。
- **`@TempDir` 与工作目录**：`user.dir` 随 IDE/构建器变化；用相对路径写死的用例是环境依赖，不判逻辑缺陷但记 warning。`@TempDir` 的清理时机（JUnit 5 默认 `cleanup = ALWAYS`）会影响「测试后文件还在」的断言。
- **XXE 审计看解析入口，不看 `newInstance`**（Java 参考 JAVA-SEC-004）：审计 `test-review` 所覆盖代码的 XXE 面时，看有没有 `builder.parse(...)` / `XMLReader.parse(...)`（真正解析外部 XML 的入口），而不是看有没有 `DocumentBuilderFactory.newInstance()`——只 `newDocument()` 构造 DOM、或 `TransformerFactory` 从内部 DOM 序列化，不涉及外部解析（实测 jsoup `W3CDom.java:204-206` 只用 `newDocument()`）。
- **命名与重载语义的盲区（建议以 `code-rules` JAVA-EQ-006 为准）**：Javadoc 声明的大小写/规范化语义与实现不一致（实测 jsoup `Attributes.put(String,boolean)` 声明 case-insensitive、`false` 分支却走大小写敏感的 `remove`）不会被任何 lint 发现；测试审查侧可补充判据：「同一 API 有 `×IgnoreCase` 变体时，测试是否覆盖了两个变体之间的一致性」——缺这组用例不按 blocker 判，记 warning 提示补设计（`test-author` 侧已在 CONTRACT 细化里覆盖）。
- **Locale / TimeZone / Charset 进程全局态**：测试修改 `Locale.setDefault` 不恢复导致后续用例失败——先确认是否顺序依赖，再判 DET-003 还是环境问题。
- **端口冲突**：集成测试用固定端口起服务器（实测 jsoup 用 jetty）时并行运行必冲突；固定端口是测试缺陷（应随机/注入），但「构建机器上端口被占」是环境问题。
- **JUnit 5 `@Nested` 与报告名**：嵌套用例在 XML 中 `classname` 是嵌套类（`Outer$Inner`），对账时按 `$` 拆分还原，避免误报缺用例。
- **`mvn -o` 离线构建**：依赖缺失导致的测试压缩为 0 条属环境限制，记「未能判定」。
- **JUnit 4 方法可见性**：JUnit 4 要求 `@Test` 方法 `public`，非 public 方法被静默忽略；JUnit 5 要求非 private。可见性不合规的用例在报告里「不存在」，需回读源码核对可见性。

## 五、本语言特有豁免

- **JMH 基准**（`src/jmh/`、`@Benchmark`）：豁免本技能的**形态类与覆盖类判据**（ORG/MOCK/DET/ASRT/COV/THR/TPERF），仅保留 EXEC-001/EXEC-002 的工程性判据——基准必须真的被构建并注册（以项目实际的 JMH 运行任务为准：JMH 通常只在显式 profile/插件下编译，未被 CI 触发的 profile 需记录为「未验证」）。
- 属性测试 / fuzz（jqwik、jqf、fuzz4all 等）不在本技能范围；如需覆盖，显式标注「未覆盖」而非记通过。
- JUnit 4（Vintage）遗留项目：按所用引擎与版本核对执行面；`@Ignore` 的正当理由判定同 `@Disabled`。
- 可选工具（JaCoCo、PIT、Testcontainers、Mockito inline）均为第三方能力；引用其输出时注明工具与版本。Testcontainers 依赖本机 Docker，Docker 不可用时记「未能判定（缺运行环境）」。
- 浮点相等断言：`0.1 + 0.2 != 0.3`，整数值超出 `double` 精确尾数（`|n| > 2^53`）后同样不可靠——须用容差；`BigDecimal` 的 `equals` 比较 scale（父技能 ASRT-003 的语言落地）。
