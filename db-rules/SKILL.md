---
name: db-rules
description: 在编写、编辑、审查或调试数据库脚本（.sql、DDL、DML、存储过程、触发器、函数、schema、migration、table、index 等）时使用。提供跨数据库通用最佳实践规范，并在 references/ 存在对应数据库专属规则时一并应用。当用户创建、修改或要求审查数据库脚本时激活。
---

# 数据库脚本规范强制执行

对每个创建或修改的数据库脚本应用以下通用规范。此 skill 是**强制性关卡** —— 在认定工作完成之前，必须逐条检查每个脚本变更是否符合规则。

## 工作流程

处理数据库脚本时，遵循以下流程：

1. **识别目标数据库**：根据用户说明或脚本语法特征判断目标数据库类型（DB2、MySQL、PostgreSQL、Oracle、SQL Server、SQLite 等）。参考下列引擎特征判定表，结合脚本中的专有语法定位数据库：

   | 特征 | 数据库 | 特征强度 |
   | ---- | ------ | -------- |
   | `AUTO_INCREMENT`、`ON DUPLICATE KEY` | MySQL | 强 |
   | `` ` `` 反引号引用 | MySQL / SQLite | 弱（跨库通用） |
   | `LIMIT` | MySQL / PostgreSQL / SQLite | 弱（跨库通用） |
   | `@` 分隔符（`db2 -td@` 命令行约定） | DB2 | 强 |
   | `CALL` 语句级触发器（`FOR EACH STATEMENT`） | DB2 / PostgreSQL | 弱（跨库通用） |
   | `IDENTITY` + `FETCH FIRST` 同时出现 | DB2 | 强（组合特征；单独出现则记弱） |
   | `FETCH FIRST`、`IDENTITY` | DB2 / Oracle / SQL Server / 标准 SQL | 弱（跨库通用） |
   | `SERIAL`、`::` 类型转换 | PostgreSQL | 强 |
   | `RETURNING`、`ON CONFLICT` | PostgreSQL / SQLite | 弱（跨库通用） |
   | `NVL`、`ROWNUM`、`VARCHAR2`、`SYSDATE` | Oracle | 强 |
   | `TOP`、`sp_` 前缀 | SQL Server | 强 |
   | `[ ]` 方括号引用 | SQL Server / SQLite | 弱（跨库通用） |
   | `INTEGER PRIMARY KEY AUTOINCREMENT`、`STRICT` 建表关键字 | SQLite | 强 |

   **判定门槛**：只有**强特征**参与计数——命中 **≥2 条强特征**才可直接判定；**仅命中 1 条**强特征时必须向用户确认目标数据库，不得自行假定。**弱特征不参与 ≥2 条计数，只作提示**（弱特征在同一脚本里出现多条也不能据此判定）；若命中的特征**全部为弱特征**，即使 ≥2 条也须向用户确认。用户已明确说明目标数据库时，以用户说明为准。

2. **加载专属规则**：判定数据库后，用 `Glob` 查找 `references/` 目录下以数据库名为前缀的参考文件（如 `DB2_*`）。若存在，一并加载并应用；加载时按条目的**适用范围标签**筛选——标签共三种（见下方「条件适用」）：原生 DB2 适用「DB2 通用」与「DB2 写法」，「移植专用」仅限 Oracle→DB2 移植场景。**当前仅 DB2 有专属参考文件，其余数据库仅应用本文件的通用规则**。
3. **写脚本之前**：阅读本文件中的通用规则；若有数据库专属参考文件，一并阅读。
4. **写脚本过程中**：边写边应用每条适用规则，不要推迟到后续阶段再补。
5. **写脚本之后**：重新通读修改过的脚本，对照通用规则及专属规则逐条审查。发现违规立即修复。
6. **报告审查结果**：审查完成后，输出一份简要清单，标明哪些规则类别通过、哪些（如有）存在问题。

## 数据库专属规则

当识别出目标数据库后，用 `Glob` 查找 `references/` 目录下是否有对应的参考文件。文件命名规则为 `<数据库名>_<主题>.md`（如 `DB2_trigger_procedure.md`）。

当前已有参考文件：

| 数据库 | 参考文件 | 覆盖范围 |
| ------ | -------- | -------- |
| DB2 | `references/DB2_trigger_procedure.md` | 触发器、存储过程、临时表、类型/模式路径、编译执行顺序；含通用 blocker 的 DB2 等价写法（Oracle→DB2 移植为主，逐条标注「DB2 通用」/「DB2 写法」/「移植专用」） |

若未找到对应参考文件，仅应用本文件的通用规则。其余数据库（MySQL/PostgreSQL/Oracle/SQL Server/SQLite）暂无专属文件。

> **条件适用**：DB2 参考文件以 **Oracle→DB2 移植**为主。
>
> - 参考文件中的每条规则带有**与严重级别并列的适用范围标签**，格式为 `（<级别>，<标签>）`，如 `PROC-006（blocker，移植专用）`。标签共**三种**：
>   - **「DB2 通用」**：原生 DB2 直接适用；
>   - **「DB2 写法」**：通用规则（定义在本 `SKILL.md`）在 DB2 上的等价写法，**原生 DB2 同样适用**（位于参考文件「GEN：DB2 通用约束的等价写法」段，如 `IDEM-001` / `DML-004` / `TYPE-004` / `TXN-002`）；它与 `DB2 通用` 的区别只是「条文定义在本 SKILL.md、参考文件给等价写法」，在筛选上同属「原生适用」；
>   - **「移植专用」**：仅 Oracle→DB2 移植场景适用，原生 DB2 不适用（如移植替换表 `PROC-006`）。
> - **筛选方法**：编写**原生** DB2 脚本时用 `grep -v '移植专用'` 过滤，**保留「DB2 通用」与「DB2 写法」两类**——只留「DB2 通用」会漏掉 GEN 段的 4 条通用 blocker 等价写法；Oracle→DB2 移植场景三种标签全部适用。

## 严重级别

| 级别    | 含义                                                      |
| ------- | --------------------------------------------------------- |
| blocker | 必须修复。存在违规的脚本不得提交。                          |
| warning | 优化建议。应当处理但不阻塞提交。                            |

---

## 通用规则

### 1. 命名规范（blocker）

- **NAME-001**：表名、视图名、列名使用小写蛇形命名法（`snake_case`），如 `user_order`、`created_at`。
- **NAME-002**：禁止使用数据库保留字作为标识符。若无法避免，必须使用数据库对应的引用符号包裹（如 `"keyword"`、`` `keyword` ``、`[keyword]`）。
- **NAME-003**：主键统一命名为 `id` 或 `<表名>_id`，禁止无意义的系统生成名称。
- **NAME-004**：外键统一命名为 `fk_<从表>_<主表>_<列>`，如 `fk_order_user_user_id`。
- **NAME-005**：索引统一命名为 `idx_<表名>_<列>`（普通索引）或 `unq_<表名>_<列>`（唯一索引）。
- **NAME-006**：触发器统一命名为 `trg_<表名>_<时机>_<事件>`，如 `trg_order_after_insert`。
- **NAME-007**：存储过程/函数名应体现动作和对象，使用 `snake_case`，如 `calculate_order_total`。

### 2. 注释与文档（blocker）

- **DOC-001**：每个脚本文件头部必须包含注释块，说明：用途、作者、创建日期、修改记录。
- **DOC-002**：每张表须有列级注释说明业务含义。语法按库选择：Oracle/PostgreSQL/DB2 用 `COMMENT ON TABLE / COLUMN`；MySQL 用列定义内联 `COMMENT '...'` 或表级 `ALTER TABLE ... COMMENT=`；SQL Server 用 `sp_addextendedproperty`；SQLite **不支持** `COMMENT ON` / `sp_addextendedproperty`，且 `PRAGMA table_info` 只能读元数据、不能写注释——须在**文档侧维护**（如 migration 脚本内的注释、配套的 schema 文档或应用层注释），并在脚本中注明注释所在位置。
- **DOC-003**：每个存储过程/函数的参数、返回值、副作用须用注释说明。
- **DOC-004**：非显而易见的业务逻辑、魔法数字、临时方案必须附带行内注释。

### 3. 幂等性与可重入（blocker）

- **IDEM-001**：DDL 必须使用幂等语法。建表前检查是否存在，按库选择等价写法：
  - **MySQL / PostgreSQL / SQLite**：`CREATE TABLE IF NOT EXISTS`。
  - **SQL Server**：`IF OBJECT_ID(N'模式名.表名', N'U') IS NULL CREATE TABLE ...`。
  - **Oracle / DB2**：`CREATE TABLE ... IF NOT EXISTS` 的支持**随版本不同**（Oracle 23ai 起支持；DB2 LUW 自部分版本起支持——均**务必按所用版本核对**），未确认版本可用时不要在 `CREATE` 前缀写 `IF NOT EXISTS`。替代写法：在脚本中以字典视图判断后建表——Oracle 查 `ALL_TABLES` / `USER_TABLES`，DB2 查 `SYSCAT.TABLES`；或在存储过程/脚本中用 `CONTINUE` 处理器或 `SQLSTATE` 异常处理包装（对象已存在时忽略对应错误码）。
  - **兜底**：先 `DROP TABLE IF EXISTS` 再 `CREATE`，须评估数据丢失风险。无法使用幂等语法的数据库，必须用条件判断或异常处理包装。
- **IDEM-002**：`INSERT` 脚本须考虑重复执行场景，使用 `INSERT ... ON CONFLICT`（PostgreSQL）、`INSERT IGNORE`（MySQL）、`MERGE`（Oracle/DB2/SQL Server）或等价机制。
- **IDEM-003**：`ALTER TABLE` 添加列/约束前须检查是否已存在，添加失败不应导致整个脚本终止。
- **IDEM-004**：脚本应可安全地重复执行而不产生副作用或错误。

### 4. 事务与数据安全（blocker）

- **TXN-001**：涉及多表修改的 DML 操作必须包裹在事务中，执行后显式 `COMMIT` 或发生异常时 `ROLLBACK`。
- **TXN-002**：删除数据前必须确认过滤条件正确，但 `DELETE` 与 `TRUNCATE` 的判定方式不同：
  - **`DELETE`**：必须包含 `WHERE` 子句。`DELETE FROM table` 无条件删除全表是**严重违规**——除非操作意图确为清空整表，且已经 TXN-003 的 `SELECT` 影响行数确认 + TXN-004 的确认机制（备份 / 事务包裹）放行。`DELETE` 是可回滚的 DML，事务包裹在所有支持事务的库上都有效。
  - **TRUNCATE 没有 `WHERE` 语法**，不与 `DELETE` 适用同一套 `WHERE` 判据；只按 TXN-004 的确认机制判定，并要求注释写明清空整表的意图。
    - **事务包裹对 TRUNCATE 仅在 PostgreSQL / SQL Server 有效**（这两者的 TRUNCATE 可回滚）。
    - **MySQL / Oracle 的 TRUNCATE 会隐式提交、不可回滚**——事务包裹**不构成**确认机制，只能用备份 / 重命名过渡等机制。
    - **DB2 不能按「库」一刀切，要按 `IMMEDIATE` 子句判**：Db2 9.7–11.5 的 `TRUNCATE` **`IMMEDIATE` 关键字是必需的**，语义即「立即生效、不可回滚」——带 `IMMEDIATE` 时事务包裹不构成放行依据；Db2 11.5.2 起**列组织表**的 `IMMEDIATE` 变为可选（该增强的 IBM 发布说明标注面向单容器 Db2 Warehouse / IIAS 部署，其它部署按所用版本核对），省略时 `ROLLBACK` 能撤销 truncate（含其后其它 DML），此时事务包裹有效。脚本里看到裸 `TRUNCATE ... IMMEDIATE` 就按不可回滚处理。
- **TXN-003**：`UPDATE` 涉及关键业务列（金额、状态等）前，必须先 `SELECT` 确认影响行数，或用事务包装以便回滚（不得未经确认直接执行）。
- **TXN-004**：生产环境脚本禁止直接 `DROP TABLE / TRUNCATE TABLE` 而不经确认机制。确认机制：**备份、重命名过渡**；**事务包裹**只有在目标库对相应语句支持回滚时才构成放行依据——`TRUNCATE` 在 **PostgreSQL / SQL Server** 可回滚；**MySQL / Oracle 的 `TRUNCATE` 隐式提交、不可回滚**；**DB2 看 `IMMEDIATE` 子句**（Db2 9.7–11.5 的 `IMMEDIATE` 必需且即「不可回滚」；11.5.2+ 列组织表省略它才可回滚，见 TXN-002）。`DROP` 的隐式提交行为按所用库与版本核对（MySQL / Oracle 的 DDL 隐式提交，不得依赖回滚）。

### 5. 模式与权限（blocker）

- **SCHEMA-001**：脚本中所有数据库对象必须使用 `模式名.对象名` 的完全限定名，不得依赖默认搜索路径或当前模式。
- **SCHEMA-002**：`GRANT` / `REVOKE` 语句必须遵循最小权限原则，禁止对所有用户 `GRANT ALL`。
- **SCHEMA-003**：脚本开头应显式设置模式/搜索路径（如 `SET SCHEMA`、`SET search_path`、`USE database`）。

### 6. 数据类型与约束（blocker）

- **TYPE-001**：禁止使用已废弃的数据类型。废弃类型仅针对其标注的数据库：SQL Server 的 `TEXT`/`NTEXT`/`IMAGE`（改用 `VARCHAR(MAX)`/`NVARCHAR(MAX)`/`VARBINARY(MAX)`）、Oracle 的 `LONG`（改用 LOB）。注意：`TEXT` 在 PostgreSQL/MySQL 是合法且推荐类型，不适用本条的废弃判定。
- **TYPE-002**：主键列必须显式声明 `NOT NULL`。
- **TYPE-003**：所有表必须声明主键。除非是临时表、日志流水表等特殊场景并附注释说明原因。
- **TYPE-004**：金额字段禁止使用浮点类型（`FLOAT`/`DOUBLE`/`REAL` 及 Oracle 的 `BINARY_FLOAT`/`BINARY_DOUBLE` 等，避免精度丢失），改用精确数值类型：
  - **MySQL / PostgreSQL / DB2 / Oracle**：`DECIMAL(p, s)` / `NUMERIC(p, s)`。
  - **SQL Server**：`DECIMAL(p, s)`；无 `DOUBLE` 类型（用 `FLOAT(n)` / `REAL`，均属浮点、禁用）。需要货币语义时可用 `MONEY`，但精度与舍入受 `MONEY` 规则约束，有精确精度需求时明示 `DECIMAL`。
  - **SQLite**：无 `DOUBLE` 类型名（对应的是 `REAL`）；且**无真正的定点小数存储**——`NUMERIC` 亲和性在无法无损表示时会退化为 `REAL`，不保证精确。金额应用 `INTEGER` 存**最小货币单位**（如分）或在应用层以定点字符串/`TEXT` 处理并转换。
- **TYPE-005**：字符串字段选择 `VARCHAR`（可变长），禁止滥用 `CHAR`（定长）。仅在已知固定长度的场景使用 `CHAR`。
- **TYPE-006**：时间戳字段优先使用带时区的类型（`TIMESTAMP WITH TIME ZONE` 等），确保跨时区数据一致性。MySQL 等无时区感知类型的数据库，应显式约定统一按 UTC 存储并在应用层处理时区。

### 7. 查询与 DML 基础规范（blocker）

- **DML-001**：生产环境查询禁止 `SELECT *`，必须显式列出所需列名。
- **DML-002**：`INSERT` 语句必须显式指定列名列表：`INSERT INTO table (col1, col2) VALUES (v1, v2)`，不得依赖列的自然顺序。
- **DML-003**：能使用参数化查询或绑定变量的场景，禁止拼接 SQL 字符串（防范 SQL 注入）。
- **DML-004**：对可能返回大数据集的操作必须限制返回行数或加合理的 `WHERE` 过滤。限制行数按库选择等价写法：
  - **MySQL / PostgreSQL / SQLite**：`LIMIT n`。
  - **SQL Server**：`SELECT TOP (n) ...`，或 `ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY`。
  - **DB2 / Oracle**：`FETCH FIRST n ROWS ONLY`（Oracle 12c 起；更早版本用 `ROWNUM`）。
  - 无法可靠分页/限流的场景，用合理的 `WHERE` 过滤兜底。

### 8. 索引与性能（warning）

- **IDX-001**：外键列必须有对应索引，避免全表扫。
- **IDX-002**：索引列数不宜过多，复合索引列数一般不超过 5 列。
- **IDX-003**：`WHERE` 条件中禁止对索引列使用函数或表达式，这会导致索引失效（如 `WHERE UPPER(name) = 'A'`、`WHERE date_col + 1 > NOW()`）。
- **IDX-004**：大批量 DML（百万级+）执行后应检查索引碎片状态（Oracle 等需要 `REBUILD` 的库）；MySQL/PostgreSQL/SQL Server 索引随 DML 自动维护，无需事后重建，仅在实际观测到碎片/性能劣化时处理。

### 9. 脚本组织（warning）

- **ORG-001**：一个脚本文件应只包含一类操作（DDL 建表 / 数据迁移 / 存储过程创建 / 权限授予 分离）。
- **ORG-002**：DDL 对象创建顺序：基础表 → 临时表 → 视图 → 存储过程/函数 → 触发器。
- **ORG-003**：脚本中应明确标注语句分隔符（如 MySQL 的 `DELIMITER`），或使用数据库默认分隔符并在命令行参数中指定。
- **ORG-004**：每个语句块之间用空行分隔，相关语句用注释分组。

### 10. 错误处理（blocker）

- **ERR-001**：存储过程中必须声明异常处理器，捕获 `SQLEXCEPTION` 并记录错误信息后重新抛出或返回错误码。禁止静默吞掉异常。
- **ERR-002**：错误日志必须包含：错误码、错误消息、发生位置（过程名/脚本名）、时间戳。
- **ERR-003**：数据库连接/会话级脚本应启用严格模式以禁止静默截断数据——按库选择：MySQL 设置 `sql_mode` 包含 `STRICT_TRANS_TABLES`；PostgreSQL/SQL Server/Oracle 默认即严格，无需额外设置；SQLite 在建表时用 `STRICT` 关键字。

### 11. 迁移与版本兼容（warning）

- **MIG-001**：添加非空约束列时，必须提供默认值或先允许 NULL、填充数据、再改为 NOT NULL。
- **MIG-002**：删除/重命名列前须确认无其他对象（视图、过程、触发器）依赖该列。
- **MIG-003**：脚本中禁止硬编码环境相关信息（IP、端口、文件路径等），通过变量或配置注入。

---

## 审查输出格式

完成数据库脚本工作后，输出如下清单：

```
## 数据库脚本规范审查

**目标数据库**：<数据库类型>
**已加载参考文件**：<文件列表 或 "无">

### Blocker 检查
- [x] NAME：命名规范 —— 通过
- [x] DOC：注释与文档 —— 通过
- [ ] IDEM：幂等性 —— IDEM-001：建表语句未使用本库可用的幂等写法
- [x] TXN：事务安全 —— 通过
- [x] SCHEMA：模式与权限 —— 通过
- [x] TYPE：数据类型 —— 通过
- [x] DML：查询与DML —— 通过
- [x] ERR：错误处理 —— 通过

### Warning 检查
- [x] IDX：索引 —— 通过
- [ ] ORG：脚本组织 —— ORG-001：脚本混合了 DDL 创建和 DML 测试数据
- [x] MIG：迁移与版本兼容 —— 通过

### 数据库专属 Blocker 检查（DB2：TRIG / TMP / PROC / SCH / EXE）
- [x] TRIG：触发器拆分 —— 通过
- [x] TMP：临时表 —— 通过
- [ ] PROC：存储过程 —— PROC-003（blocker）：使用了参数游标，应改用变量游标
- [x] SCH：类型与模式路径 —— 通过
- [x] EXE：编译与执行顺序 —— 通过

### 数据库专属 Warning 检查（DB2：TRIG / TMP / PROC / SCH / EXE）
- [x] TRIG：触发器 —— 通过
- [x] TMP：临时表 —— 通过
- [x] PROC：存储过程 —— 通过
- [x] SCH：类型与模式路径 —— 通过
- [ ] EXE：编译与执行顺序 —— EXE-003（warning）：行级触发器创建后未插入测试行

### 总结
- Blocker：1 项违规（IDEM-001）—— 提交前必须修复
- Warning：1 项建议（ORG-001）
- 专属规则 Blocker：1 项违规（PROC-003）—— 提交前必须修复
- 专属规则 Warning：1 项建议（EXE-003）
```

> 专属规则分组须**按实际加载的参考文件列出全部组**（当前 DB2 为 TRIG / TMP / PROC / SCH / EXE 五组），不要只示例其中两组。示例条目的级别必须与参考文件中的实际分级一致（如 `PROC-003` 为 blocker、`EXE-003` 为 warning）。

Blocker 必须在报告完成前全部修复。Warning 尽量修复，或说明推迟处理的原因。

## 参考

完整数据库专属规范见 `references/` 目录下的对应文件。当通用规则与专属规则**冲突**时，**取更严者**（专属规则更严则用专属规则，通用规则更严则用通用规则）——避免专属文件的较低级别把通用 blocker 静默降级。

专属文件**未覆盖**的通用 blocker 仍然适用，但须换成目标库语法（如 DB2 上的 IDEM-001 / DML-004 / TYPE-004 / TXN-002 见 `references/DB2_trigger_procedure.md` 的「GEN：DB2 通用约束的等价写法」）。
