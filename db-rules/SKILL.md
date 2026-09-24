---
name: db-rules
description: 在编写、编辑、审查或调试数据库脚本（.sql、DDL、DML、存储过程、触发器、函数、schema、migration、table、index 等）时使用。提供跨数据库通用最佳实践规范，并在 references/ 存在对应数据库专属规则时一并应用。当用户创建、修改或要求审查数据库脚本时激活。
---

# 数据库脚本规范强制执行

对每个创建或修改的数据库脚本应用以下通用规范。此 skill 是**强制性关卡** —— 在认定工作完成之前，必须逐条检查每个脚本变更是否符合规则。

## 工作流程

处理数据库脚本时，遵循以下流程：

1. **识别目标数据库**：根据用户说明或脚本语法特征判断目标数据库类型（DB2、MySQL、PostgreSQL、Oracle、SQL Server、SQLite 等）。参考下列引擎特征判定表，结合脚本中的专有语法定位数据库：

   | 特征 | 数据库 |
   | ---- | ------ |
   | `LIMIT`、`AUTO_INCREMENT`、`ON DUPLICATE KEY`、`` ` `` 反引号引用 | MySQL |
   | `FETCH FIRST`、`IDENTITY`、`CALL` 语句级触发器、`@` 分隔符 | DB2 |
   | `SERIAL`、`::` 类型转换、`RETURNING`、`ON CONFLICT` | PostgreSQL |
   | `NVL`、`ROWNUM`、`VARCHAR2`、`SYSDATE` | Oracle |
   | `TOP`、`[ ]` 方括号引用、`sp_` 前缀 | SQL Server |
   | `INTEGER PRIMARY KEY AUTOINCREMENT`、`STRICT` 建表关键字 | SQLite |

2. **加载专属规则**：判定数据库后，用 `Glob` 查找 `references/` 目录下以数据库名为前缀的参考文件（如 `DB2_*`）。若存在，一并加载并应用；**当前仅 DB2 有专属参考文件，其余数据库仅应用本文件的通用规则**。
3. **写脚本之前**：阅读本文件中的通用规则；若有数据库专属参考文件，一并阅读。
4. **写脚本过程中**：边写边应用每条适用规则，不要推迟到后续阶段再补。
5. **写脚本之后**：重新通读修改过的脚本，对照通用规则及专属规则逐条审查。发现违规立即修复。
6. **报告审查结果**：审查完成后，输出一份简要清单，标明哪些规则类别通过、哪些（如有）存在问题。

## 数据库专属规则

当识别出目标数据库后，用 `Glob` 查找 `references/` 目录下是否有对应的参考文件。文件命名规则为 `<数据库名>_<主题>.md`（如 `DB2_trigger_procedure.md`）。

当前已有参考文件：

| 数据库 | 参考文件 | 覆盖范围 |
| ------ | -------- | -------- |
| DB2 | `references/DB2_trigger_procedure.md` | 触发器、存储过程、临时表（Oracle→DB2 移植场景，含 DB2 通用约束） |

若未找到对应参考文件，仅应用本文件的通用规则。其余数据库（MySQL/PostgreSQL/Oracle/SQL Server/SQLite）暂无专属文件。

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
- **DOC-002**：每张表须有列级注释说明业务含义。语法按库选择：Oracle/PostgreSQL/DB2 用 `COMMENT ON TABLE / COLUMN`；MySQL 用列定义内联 `COMMENT '...'` 或表级 `ALTER TABLE ... COMMENT=`；SQL Server 用 `sp_addextendedproperty`。
- **DOC-003**：每个存储过程/函数的参数、返回值、副作用须用注释说明。
- **DOC-004**：非显而易见的业务逻辑、魔法数字、临时方案必须附带行内注释。

### 3. 幂等性与可重入（blocker）

- **IDEM-001**：DDL 必须使用幂等语法。建表前检查是否存在：`CREATE TABLE IF NOT EXISTS`（或等价的先 DROP 再 CREATE，需谨慎评估数据丢失风险）。无法使用 `IF NOT EXISTS` 的数据库，应使用条件判断或异常处理包装。
- **IDEM-002**：`INSERT` 脚本须考虑重复执行场景，使用 `INSERT ... ON CONFLICT`（PostgreSQL）、`INSERT IGNORE`（MySQL）、`MERGE`（Oracle/DB2/SQL Server）或等价机制。
- **IDEM-003**：`ALTER TABLE` 添加列/约束前须检查是否已存在，添加失败不应导致整个脚本终止。
- **IDEM-004**：脚本应可安全地重复执行而不产生副作用或错误。

### 4. 事务与数据安全（blocker）

- **TXN-001**：涉及多表修改的 DML 操作必须包裹在事务中，执行后显式 `COMMIT` 或发生异常时 `ROLLBACK`。
- **TXN-002**：`DELETE` / `TRUNCATE` 前必须确认过滤条件正确。`DELETE FROM table` 无条件删除全表是**严重违规**，必须包含 `WHERE` 子句。
- **TXN-003**：`UPDATE` 涉及关键业务列（金额、状态等）前，建议先 `SELECT` 确认影响行数或使用事务包装，以便回滚。
- **TXN-004**：生产环境脚本禁止直接 `DROP TABLE / TRUNCATE TABLE` 而不经确认机制（备份、重命名过渡等）。

### 5. 模式与权限（blocker）

- **SCHEMA-001**：脚本中所有数据库对象必须使用 `模式名.对象名` 的完全限定名，不得依赖默认搜索路径或当前模式。
- **SCHEMA-002**：`GRANT` / `REVOKE` 语句必须遵循最小权限原则，禁止对所有用户 `GRANT ALL`。
- **SCHEMA-003**：脚本开头应显式设置模式/搜索路径（如 `SET SCHEMA`、`SET search_path`、`USE database`）。

### 6. 数据类型与约束（blocker）

- **TYPE-001**：禁止使用已废弃的数据类型。废弃类型仅针对其标注的数据库：SQL Server 的 `TEXT`/`NTEXT`/`IMAGE`（改用 `VARCHAR(MAX)`/`NVARCHAR(MAX)`/`VARBINARY(MAX)`）、Oracle 的 `LONG`（改用 LOB）。注意：`TEXT` 在 PostgreSQL/MySQL 是合法且推荐类型，不适用本条的废弃判定。
- **TYPE-002**：主键列必须显式声明 `NOT NULL`。
- **TYPE-003**：所有表必须声明主键。除非是临时表、日志流水表等特殊场景并附注释说明原因。
- **TYPE-004**：金额字段使用 `DECIMAL`/`NUMERIC`，禁止使用 `FLOAT`/`DOUBLE`（避免精度丢失）。
- **TYPE-005**：字符串字段选择 `VARCHAR`（可变长），禁止滥用 `CHAR`（定长）。仅在已知固定长度的场景使用 `CHAR`。
- **TYPE-006**：时间戳字段优先使用带时区的类型（`TIMESTAMP WITH TIME ZONE` 等），确保跨时区数据一致性。MySQL 等无时区感知类型的数据库，应显式约定统一按 UTC 存储并在应用层处理时区。

### 7. 查询与 DML 基础规范（blocker）

- **DML-001**：生产环境查询禁止 `SELECT *`，必须显式列出所需列名。
- **DML-002**：`INSERT` 语句必须显式指定列名列表：`INSERT INTO table (col1, col2) VALUES (v1, v2)`，不得依赖列的自然顺序。
- **DML-003**：能使用参数化查询或绑定变量的场景，禁止拼接 SQL 字符串（防范 SQL 注入）。
- **DML-004**：对可能返回大数据集的操作必须加 `LIMIT` / `FETCH FIRST` 或合理的 `WHERE` 过滤。

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
- [ ] IDEM：幂等性 —— IDEM-001：建表语句缺少 IF NOT EXISTS
- [x] TXN：事务安全 —— 通过
- [x] SCHEMA：模式与权限 —— 通过
- [x] TYPE：数据类型 —— 通过
- [x] DML：查询与DML —— 通过
- [x] ERR：错误处理 —— 通过

### Warning 检查
- [x] IDX：索引 —— 通过
- [ ] ORG：脚本组织 —— ORG-001：脚本混合了 DDL 创建和 DML 测试数据
- [x] MIG：迁移与版本兼容 —— 通过

### 数据库专属检查（DB2）
- [x] TRIG：触发器拆分 —— 通过
- [ ] PROC：存储过程 —— PROC-003：使用了参数游标，应改用变量游标

### 总结
- Blocker：1 项违规（IDEM-001）—— 提交前必须修复
- Warning：1 项建议（ORG-001）
- 专属规则 Blocker：1 项违规（PROC-003）—— 提交前必须修复
```

Blocker 必须在报告完成前全部修复。Warning 尽量修复，或说明推迟处理的原因。

## 参考

完整数据库专属规范见 `references/` 目录下的对应文件。当通用规则与专属规则冲突时，以专属规则为准。
