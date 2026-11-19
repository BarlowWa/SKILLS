# Java 架构审查参考（arch-review / references）

> 由 arch-review 在识别为 Java（`.java` 源文件，或存在 `pom.xml` / `build.gradle` / `settings.gradle` 且含 Java 源码）时加载。
> 通用 ARCH 规则见 `arch-review/SKILL.md`；本文提供**证据采集方式**与 Java 专属规则。模块口径见 SKILL.md『模块定义』：首选 Maven/Gradle module，次选顶层 package。

## 一、证据采集

### 1.1 模块与依赖清单（Maven）

1. **模块清单**：直接读根 `pom.xml` 的 `<modules>`（权威且无插件依赖）；`mvn help:evaluate` 对列表型表达式（`project.modules`）的输出格式随插件版本变化，仅在 `<modules>` 由属性/父 POM 生成时作为补充。多模块 reactor 的构建顺序由 `<modules>` 声明与模块间依赖共同决定，**声明顺序不是拓扑序**——判依赖方向时以实际依赖为准。
2. **依赖图**：`mvn dependency:tree`（含版本与 scope）；只要构建期依赖时 `mvn dependency:tree -Dscope=runtime`（或 `-Dscope=compile`）。输出每行形如 `group:artifact:type:classifier:version:scope`，scope 列是判分层与隔离的关键证据。
3. **冲突与仲裁**：Maven 采用「最近的定义」仲裁（nearest definition）——同一构件多版本时取依赖树中最浅的版本，同深度取**先声明者**；`<dependencyManagement>` 的版本声明**优先于**传递依赖的仲裁结果。审查「某版本是否为预期版本」必须走 `dependencyManagement` 与树两处证据，不能只读某个子模块的 `<dependencies>`。（官方文档：Maven Guide — Introduction to the Dependency Mechanism「Dependency mediation」）
4. **未声明依赖**：`mvn dependency:analyze` 报告「Used undeclared」与「Unused declared」；默认同时覆盖 test scope（实测 jsoup 的输出即列出 `:test` 条目）。
   > `-DignoreNonCompile=true` **只影响 Unused declared**（官方文档：「Ignore runtime/provided/test/system scopes for unused dependency analysis. Non-test scoped list will be not affected.」）——它**不会**把 Used undeclared 收窄到编译面。需按 scope 区分 Used undeclared 时，回 `dependency:tree` 把该构件定位到声明处（`:test` 即测试面）。作为门禁时加 `-DfailOnWarning=true`。
   > 输出里 `Unused declared` 对聚合依赖（如 `junit-jupiter` 聚合包、`*-bom`、仅提供传递依赖的 POM 包装）有已知误报，判级前回查该依赖的包装性质。

### 1.2 模块与依赖清单（Gradle）

1. **模块清单**：`./gradlew projects`；依赖图：`./gradlew :<module>:dependencies --configuration runtimeClasspath`（或 `compileClasspath`、`apiElements`、`runtimeElements`）。
2. **api/implementation 隔离**：`java-library` 插件把依赖分为 `api`（进入消费者编译类路径）与 `implementation`（只在模块内可见）；对库模块这是 ARCH-003（适配层隔离）与 ARCH-007（接口暴露）的一手证据。（官方文档：Gradle User Guide — Java Library plugin「API and implementation separation」）
3. **配置解析差异**：`compileClasspath` 与 `runtimeClasspath` 解析结果不同是**正常**的（`compileOnly` 不在 runtime、`runtimeOnly` 不在 compile）；跨模块一致性审查须在同一配置下对比，不能混用两个配置的树。

### 1.3 类级依赖与 JPMS

1. **类级依赖**：对构建产物执行 `jdeps --multi-release 9 -s -filter:package --class-path <cp> target/classes`（或对 jar 执行）。输出 `A -> B` 行即包级依赖边；`--multi-release` 让 `META-INF/versions/*` 中的类按目标版本并入分析（多版本 jar 必须带，否则漏掉版本化类）。
   > ⚠️ **选项名是 `--class-path`，不是 `--classpath`**：JDK 17 的 jdeps 对 `--classpath` 直接报「未知选项」（实测），旧版文档的写法不要照抄。
   > 实测：jsoup 1.18.3 的 `jdeps --multi-release 9 -filter:package` 输出 `org.jsoup -> java.base / java.xml`，以及一个 `-> 找不到` 行——后者是**签名表不认识的类**（该 jar 的 `module-info.class` 是编译期产物，jdeps 在无模块路径时无法解析 `requires static` 依赖 `org.jspecify`）。把 `找不到` 当作真实依赖缺失前，先用 `--class-path` 补全依赖；仍找不到的记「未能判定」。
2. **JPMS 导出面**：读 `module-info.java` 的 `exports` / `opens` / `requires`（含 `requires transitive`、`requires static`）。`exports` 的子包集合就是模块的公开面；`exports ... to <module>` 是限定导出，不进入公开面。
   > 注意 `src/main/java9/module-info.java` 这类 **multi-release 布局**：`module-info` 只在 Java 9+ 的产物中生效，分析时以 jar 内 `META-INF/versions/9/module-info.class`（或源目录）为准，不要因 `src/main/java` 下没有 module-info 就判「非模块化」。
3. **split package**：同一个包名出现在两个模块 / 两个 jar 中是 JPMS 下的硬错误（无法放入同一模块图）；classpath 下它会造成「哪份在类路径就加载哪份」的隐式覆盖。证据：`jdeps` 包级输出 + `jar --describe-module`（或 `unzip -l` 包路径统计）交叉核对。

### 1.4 构建产物

1. **jar 内容**：`unzip -l target/<artifact>.jar` 看 `module-info.class`、`META-INF/versions/*`、`META-INF/MANIFEST.MF` 的 `Multi-Release: true` 与 `Automatic-Module-Name`。
2. **OSGi 元数据**（若项目用 maven-bundle-plugin）：manifest 的 `Export-Package` / `Import-Package` 是该产物对 OSGi 消费者的公开面，与 `module-info` 的 `exports` 可能不一致——两者都需核对。
3. **构建期强制项**：审查构建结构时优先读这些插件的实际配置（有则必须生效、无则记录缺失）：
   - `maven-enforcer-plugin`：`bannedDependencies` / `dependencyConvergence` / `requireUpperBoundDeps` 是依赖约束的机器门禁（官方文档：Enforcer Built-In Rules）。
   - `maven-dependency-plugin:analyze` 的 `failOnWarning`（见 1.1）。
   - `maven-shade-plugin` 的 relocation：重定位把某依赖的类改写到插件私有的包前缀下，用于隔离第三方；未配置 relocation 的 shade 只是把依赖烘进产物，**不构成隔离**。（官方文档：Shade Plugin「Relocating Classes」）
   - `maven-jar-plugin` / `maven-compiler-plugin` 的 `<release>` 与 `<modulePath>`。

## 二、Java 专属规则

### ARCH-JAVA-001：依赖 scope 与 API/实现的隔离（major）

库模块的公开 API（公开类的方法签名、超类、泛型实参、注解）**不得**依赖只在 `runtime` / `provided` 中存在的类型；API 中出现的第三方类型必须声明为 `compile`（Gradle 为 `api`）。业务实现对第三方库的直接依赖必须经适配层收口（ARCH-003 在 Java 的落地形态）。
**证据**：`dependency:tree` 的 scope 列 + `jdeps --multi-release 9 --class-path <cp>` 的包级边；有 `module-info.java` 时 `requires static` 修饰的依赖若出现在 `exports` 包的公开签名中，即为源码级兼容但运行时缺失的坑。
**判级**：公开 API 引用了 `provided`/`optional` 类型 → major；`runtime` 依赖被公开签名引用 → critical（消费者编译即失败）。
**边界（注解 vs 类型引用）**：`requires static` 的**注解**出现在公开签名中（实测 jsoup 在 `Connection.proxy(@Nullable Proxy)` 等方法上使用 `org.jspecify.annotations.Nullable`，该注解为 `@Retention(RUNTIME)` + `@Target(TYPE_USE)`）**不构成运行时依赖缺失**——注解在运行时缺失时被 JVM 静默忽略，不触发 `NoClassDefFoundError`。判级前区分「签名中的类型引用」（参数/返回/字段/泛型实参/异常）与「签名中的注解元素」：后者按 minor 记录或不记，不得套用本条的 major/critical。

### ARCH-JAVA-002：`requires transitive` 与 API 泄漏（major）

JPMS 模块中，导出包的公开签名若含某依赖类型，则该依赖必须 `requires transitive`；反之，非 API 依赖不得 `requires transitive`（它会把模块的消费者绑到你的实现选择上）。`opens X to Y` 是给反射消费者（框架、序列化）的知情通道，不属于公开 API 面；对**所有模块** `opens`（无 `to`）视为接口暴露问题记 minor。
**证据**：`module-info.java` 的 `requires` 修饰符 × `exports` 包的公开签名；`jdeps --jdk-internals` 可补充检查内部 API 使用。
**依据**：JDK 官方 Module System 文档（`requires transitive` 的「implied readability」语义）。

### ARCH-JAVA-003：多模块 reactor 的依赖方向（major）

Maven/Gradle 多模块工程中，模块依赖必须单向：上层（应用/装配）依赖下层（领域/基础），禁止底层模块依赖上层；构建顺序由依赖决定，若为让构建通过而在 `<modules>` 顺序或 Gradle `dependencies` 上制造反向边，按 ARCH-002 的 major 判。
**证据**：每层的 `dependency:tree -Dincludes=group:artifact` 是否出现上层模块；父 POM 的 `<modules>` 声明顺序与 reactor 构建顺序（`mvn -B validate` 的 reactor 摘要）。
**边界**：测试模块依赖被测模块是层级正当（ARCH-002 的测试豁免）；`provided` 的容器 API（如 `javax.servlet-api`）反向不构成倒置。

### ARCH-JAVA-004：构建期依赖不得进入运行期（major）

`maven-dependency-plugin:analyze` 的「Used undeclared」指出源码用了未声明依赖（依赖通过传递引入，版本不受控）；「Unused declared」指出声明了但未用。两者同时出现在业务模块时，说明依赖声明与真实使用已脱节，按 major 记录；聚合依赖（`*-bom`、`junit-jupiter` 聚合包）的 Unused 为已知误报，不据此判级。
**证据**：`mvn dependency:analyze`（实测 jsoup 输出含 `Used undeclared` 与 `Unused declared` 两类 `:test` 条目）。
**判级**：非 test scope 的 Used undeclared → major；仅测试面（`:test`）→ minor。

### ARCH-JAVA-005：依赖仲裁与收敛（major）

同一构件在依赖树中出现多个版本、且由 Maven「最近定义」仲裁决定实际版本时，必须用 `<dependencyManagement>` 显式收敛到单一版本；`dependencyConvergence` 规则失败或在树中出现同一 artifact 的多个版本节点，即为维护漂移。
**证据**：`mvn dependency:tree -Dverbose`（多版本节点会标出被省略的版本与仲裁理由）；`mvn enforcer:dependency-convergence`。
**边界**：第三方传递依赖的版本差异在 `dependencyManagement` 未覆盖时是常态，单独一条不算缺陷；**本模块公开依赖**的版本漂移才按本条判。

### ARCH-JAVA-006：JDK 版本与 `--release` 面（critical）

`maven-compiler-plugin` / Gradle `java.toolchain` 的目标版本必须与 `--release` 一致（Maven 用 `<release>`，避免 `-source/-target` 与旧 JDK API 混用）；发布库的 `Automatic-Module-Name` / `module-info` / `Multi-Release` 声明必须与产物实际内容一致（jar 含 `META-INF/versions/9/module-info.class` 时 manifest 必须有 `Multi-Release: true`，否则 Java 9+ 运行时**忽略**版本化类）。
**证据**：`unzip -p target/<jar> META-INF/MANIFEST.MF` 的 `Multi-Release` 与 `Automatic-Module-Name`；`unzip -l` 中 `META-INF/versions/` 的内容；`pom.xml` / `build.gradle` 的 `<release>` / toolchain。
**判级**：`Multi-Release: true` 缺失而 jar 内含版本化类 → critical（版本化类在运行时不可见）；新旧 API 混用（`--release` 未使用）→ major（运行时 `NoSuchMethodError` 风险）。

### ARCH-JAVA-007：shade / relocation 的隔离语义（major）

`maven-shade-plugin` 只把依赖打进产物时，被 shade 的第三方类仍在原包名下，消费者会与自己的同名依赖冲突（classpath 下类加载顺序决定用哪份）；真正的隔离要求 `<relocations>` 把第三方类重定位到插件私有前缀，并确认消费面不暴露原包名类型。
**证据**：`shade` 配置的 `<relocations>` / `<filters>`；产物 jar 中第三方包的路径（`unzip -l`）。
**边界**：可执行 fat jar（应用装配层）不需要 relocation，按层判定——重定位要求只对**库**模块成立。

### ARCH-JAVA-008：分布式边界的 RMI / 序列化形态（minor）

以 `ObjectOutputStream` / RMI / `Serializable` 作为跨模块或跨进程接口的模块，其类布局即协议的一部分——布局变更（字段增删、serialVersionUID 改动）就是协议破坏；仅 `Serializable` 而无可控 `serialVersionUID` 的类会在重构后不兼容。
**证据**：`implements Serializable` 且未声明 `serialVersionUID` 的公开类型；`ObjectInputStream` 的使用点。
**边界**：仅在进程内使用的序列化缓存（如 ORM 的序列化列、临时文件）按 minor 记录；JDK 近期版本已把原生序列化列入默认禁用路径（JEP 290 过滤器），安全面由 `code-rules` JAVA-SEC-005 负责，本条只判协议稳定性。

### ARCH-JAVA-009：OSGi / JPMS 双导出面的一致性（minor）

同时发布 OSGi 元数据（`Export-Package`）与 JPMS `module-info` 的产物，两者的导出集合应一致；OSGi 导出内部包（如 `*.internal`）会扩大公开面并锁死内部重构。
**证据**：manifest 的 `Export-Package` 与 `module-info` 的 `exports` 做集合差；再对每个导出包做「jar 内是否真有该类」的核对（`unzip -l` 计数）。
**实测样本（两种形态）**：jsoup 1.18.3 的 manifest 导出 **8** 个包，`module-info` 只 `exports` **6** 个，差集为 `{org.jsoup.internal, org.jsoup.examples}`：
- `org.jsoup.internal`——导出内部包，扩大公开面；
- `org.jsoup.examples`——**幽灵导出**：`pom.xml:169-171` 的 `maven-jar-plugin` `<excludes>` 已把 `org/jsoup/examples/**` 从 jar 剔除（jar 内该类 0 个），但 `maven-bundle-plugin` 生成 manifest 的时机早于 jar 组装，`Export-Package` 仍列出它。消费者按导出面解析该包时无类可加载。
判级：幽灵导出与内部包导出均按 minor 记，但须在报告中明确指出——它是「构建配置不一致」而非单纯的风格问题。

### ARCH-JAVA-010：测试与产品代码的依赖隔离（minor）

`test` scope 依赖（JUnit、Mockito、测试容器）不得被 `main` 源码 import；mapper 生成器、注解处理器等构建期工具应声明为 `provided` / `annotationProcessor`，不得作为 `compile` 依赖传递给消费者。
**证据**：`src/main/java` 中对 `org.junit.*` / `org.mockito.*` 的 import（实测 jsoup 主源码 0 命中）；`dependency:tree -Dincludes=org.junit:*` 的 scope 是否为 `test`。

### ARCH-JAVA-011：包级依赖环的分级（包口径）

未声明分层、且模块口径降级为「包」的项目（如单模块 Maven 库），包间依赖环按通用 ARCH-004 会落 **critical**——但一个内聚的库被切分成若干互相引用的包（`nodes ↔ helper`、`parser ↔ nodes` 等）是 Java 库的常态，环不构成链接危害，危害集中在「无法独立理解/测试单个包」。
**判级（替代 ARCH-004 对包口径的默认判级）**：
- 环中每一个包都是**公开导出包**、且环内无 `internal`/`impl` 边界 → minor（内聚库常态，仅记录）；
- 环跨越了「内部包 ↔ 公开包」边界（公开包的实现依赖内部包、内部包又反向引用公开包）→ major（收口失败）；
- 环跨越了模块的对外 API 边界（如 `api` 包 ↔ `spi` 包的环）→ 按 ARCH-JAVA-003 的 major 判。

**证据**：`jdeps -s -filter:package` 的包级边做 SCC（Tarjan）；实测 jsoup 有 8 个包、35 条包级边，SCC 为 `{org.jsoup, org.jsoup.helper, org.jsoup.internal, org.jsoup.nodes, org.jsoup.parser, org.jsoup.safety, org.jsoup.select}` 七包一环（`org.jsoup.examples` 叶子，入度 0）——按本条判 minor，而不是 ARCH-004 的 critical。
> 包口径下 ARCH-013（被 8+ 模块依赖）与 ARCH-014（依赖 10+ 模块）阈值通常不可达（jsoup 最大入度 7：`helper`），不要机械套用模块级阈值；包口径的耦合度量改用「入度/出度相对分布」描述，达到模块级阈值时才报。

## 三、Java 场景下的证据注意事项

- **`dependency:tree` 只显示仲裁后结果**：默认不显示被省略的节点；判冲突用 `-Dverbose`。
- **`jdeps` 的「找不到」不一定是缺依赖**：签名表解析失败的类（`requires static` / module-path 缺失）也会出现，先补 `--class-path` 再判定。
- **多版本 jar 必须带 `--multi-release`**：否则 `META-INF/versions/9` 下的类不参与分析，导出面会被低估。
- **聚合依赖不等于直接使用**：`junit-jupiter`、`*-bom` 的「未使用」是结构性的，不按 ARCH-JAVA-004 判级。
- **Gradle 配置混用**：`compileClasspath` 与 `runtimeClasspath` 的差异是设计而不是缺陷；对比同一配置。
- **`<modules>` 顺序不证明依赖方向**：以 `dependency:tree` 与 reactor 实际构建顺序为准。
- **测试源码的位置**：`src/test/java` 与 `src/main/java` 是不同 source set，测试间依赖不进入产品依赖图；测试目录的架构审查放宽（SKILL.md『注意事项』）。
- **`provided` 容器 API**：`provided` scope 的平台 API（servlet、JDBC 驱动接口）被公开签名引用是容器设计惯例，按分层合理性判断，不要机械按 ARCH-JAVA-001 判 critical——先确认它是 SPI/宿主提供类型还是普通第三方库。
- **`Automatic-Module-Name` 与 `module-info` 并存**：manifest 的 Automatic-Module-Name 在显式 `module-info` 存在时被忽略（多 release 场景下 9+ 用 module-info、8 用 Automatic-Module-Name）；不要把两者不一致直接判缺陷。
