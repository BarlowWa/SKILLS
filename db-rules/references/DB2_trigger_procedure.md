# DB2 LUW 触发器/存储过程规则清单
（基于 Oracle→DB2 移植真实项目反复调试，v11.5+ 环境）

> 本文件主体为 **Oracle→DB2 移植**场景的规则与经验。每条规则在严重级别之后带有**适用范围标签**，用于机械筛选：
> - `DB2 通用`：原生 DB2 与 Oracle→DB2 移植场景均适用（依据可能是 DB2 语法限制，也可能是本项目约定）。
> - `DB2 写法`：`SKILL.md` 中通用规则在 DB2 上的等价写法（见下文「GEN」段），**原生 DB2 同样适用**；它只标明该条对应哪条通用规则。
> - `移植专用`：仅 Oracle→DB2 移植场景适用，原生 DB2 不适用。
>
> 编写**原生** DB2 脚本时，用 `grep -v '移植专用'` 过滤本文件，**保留 `DB2 通用` 与 `DB2 写法` 两类**（只留 `DB2 通用` 会漏掉 GEN 段 4 条通用 blocker 的等价写法）；编写 Oracle→DB2 移植脚本时全部适用。

## 严重级别与适用范围

| 维度 | 取值 | 含义 |
| ---- | ---- | ---- |
| 严重级别 | blocker | 必须修复，否则触发器/存储过程无法通过编译或运行时报错（或违反本项目硬约束） |
| | warning | 建议项，改善可维护性/性能 |
| 适用范围 | DB2 通用 | 原生 DB2 与 Oracle→DB2 移植均适用 |
| | DB2 写法 | 通用规则（定义在 `SKILL.md`）在 DB2 上的等价写法，原生 DB2 同样适用 |
| | 移植专用 | 仅 Oracle→DB2 移植适用 |

条目格式：`- **ID**（<严重级别>，<适用范围>）：…`。括号内的「本项目约束」「按版本核对」等说明描述依据或版本边界，**不改变**适用范围。

## TRIG：触发器

- **TRIG-001**（blocker，DB2 通用）：多事件触发器必须拆分——`INSERT OR UPDATE OR DELETE` 拆成三个单事件触发器。
- **TRIG-002**（blocker，DB2 通用）：语句级触发器（`FOR EACH STATEMENT`）只允许 `CALL`；禁止变量、游标、条件、异常处理及任何 DML；调用必须用完全限定名 `CALL 模式名.存储过程名()`。
- **TRIG-003**（blocker，DB2 通用）：行级触发器（`FOR EACH ROW`）严格受限——仅用 AFTER 行级触发器执行数据修改；BEFORE 行级触发器禁止任何 INSERT/UPDATE/DELETE。（本项目约束）
- **TRIG-004**（blocker，DB2 通用）：行级触发器若需执行多条 SQL，必须用 `BEGIN ATOMIC ... END;`，禁止单独 `BEGIN ... END`（否则过渡变量 NEW/OLD 在内层失效，报 SQLCODE=-206）。
- **TRIG-005**（blocker，DB2 通用）：`CALL` 或 `WHERE` 条件中不能对过渡变量使用表达式/函数（如 `TRIM(O.col)`），只能直接传递 `NEW.col` / `OLD.col`。（本项目约束；个别 DB2 版本允许部分表达式，但为兼容性统一禁止）
- **TRIG-006**（warning，DB2 通用）：`WHEN` 子句仅用于简单防重入条件或子查询，不用来替代业务逻辑。
- **TRIG-007**（warning，DB2 通用）：复杂业务逻辑封装到存储过程，由语句级触发器调用；行级触发器逻辑极简（如单表 `UPDATE SET col = NEW.col WHERE col = OLD.col`）时才可直接写在 `BEGIN ATOMIC` 中。

## TMP：临时表

- **TMP-001**（blocker，DB2 通用）：必须使用 `CREATE GLOBAL TEMPORARY TABLE ... ON COMMIT PRESERVE ROWS NOT LOGGED`。
- **TMP-002**（blocker，DB2 通用）：CGTT **不能声明主键/外键约束**（约束不会随建表隐含创建）；**可建普通/唯一索引**（须与表同表空间；DB2 LUW 9.7+ 支持，REORG INDEX / RENAME INDEX / index extension 等操作受限——按 DB2 LUW 版本核对）。
- **TMP-003**（warning，DB2 通用）：Guard 表同样使用 CGTT，通过 `guard_cnt` 计数实现防重入。
- **TMP-004**（warning，DB2 通用）：行级触发器直接插入大批数据时可能产生重复行，**建议**不要依赖唯一索引去重，而在存储过程中用 `SELECT DISTINCT`；该项仅为建议，不阻塞提交。

## PROC：存储过程

- **PROC-001**（blocker，DB2 通用）：使用 `CREATE OR REPLACE PROCEDURE ... LANGUAGE SQL main: BEGIN ... END main`。
- **PROC-002**（warning，DB2 通用）：所有声明集中在头部（变量 → 游标 → 异常处理器）。
- **PROC-003**（blocker，DB2 通用）：优先使用变量游标，避免参数游标导致 -206。
- **PROC-004**（blocker，DB2 通用）：异常处理器 `DECLARE EXIT HANDLER FOR SQLEXCEPTION`，内部用 `GET DIAGNOSTICS` 获取信息后 `RESIGNAL`；处理器的 BEGIN...END 内部禁止声明变量（需提前在 main: 头部声明）。
- **PROC-005**（warning，DB2 通用）：循环控制避免直接使用 `WHILE SQLCODE = 0`，改用 `LOOP + FETCH + SET v_sqlcode = SQLCODE` 局部变量判断。
- **PROC-006**（blocker，移植专用）：函数替换（仅 Oracle→DB2 移植适用）：`NVL` → `COALESCE`，`SQL%ROWCOUNT` → `GET DIAGNOSTICS ROW_COUNT`，`TO_CHAR` → `CAST`，保留字列名用双引号（如 `"OFFSET"`）。

## SCH：类型与模式路径

- **SCH-001**（blocker，DB2 通用）：存储过程参数类型必须与调用时传递的列类型精确一致。
- **SCH-002**（warning，DB2 通用）：触发器、存储过程、表尽量同一模式，或调用时使用完全限定名。
- **SCH-003**（warning，DB2 通用）：执行前设置 `SET SCHEMA 模式名; SET PATH = 模式名, SYSTEM PATH;`。

## EXE：编译与执行顺序

- **EXE-001**（blocker，DB2 通用）：脚本以 `@` 作为语句分隔符（`db2 -td@ -f`）。
- **EXE-002**（blocker，DB2 通用）：创建顺序——基础表 → 临时表/日志表 → 存储过程 → 行级触发器 → 语句级触发器。
- **EXE-003**（warning，DB2 通用）：行级触发器创建后立即插入一行测试。

## GEN：DB2 通用约束的等价写法

以下为通用 blocker（定义在 `SKILL.md`，编号不改，此处不复述原条文）在 DB2 上的等价写法（本段每条标注 `DB2 写法`，即上表「适用范围」的第三个取值：原生 DB2 同样适用）：

- `IDEM-001`（blocker，DB2 写法）：`CREATE TABLE ... IF NOT EXISTS` 在 DB2 LUW 的支持**随版本不同**（自部分版本起支持，**务必按所用版本核对**，不要默认可直接使用）。等价幂等写法：先查 `SYSCAT.TABLES`（如 `SELECT COUNT(*) FROM SYSCAT.TABLES WHERE TABSCHEMA = '模式名' AND TABNAME = '表名'`）判断后再 `CREATE`；或在存储过程/脚本中用 `DECLARE CONTINUE HANDLER FOR SQLSTATE '42710'`（对象已存在）等异常处理器包装。
- `DML-004`（blocker，DB2 写法）：限制返回行数用 `FETCH FIRST n ROWS ONLY`（`LIMIT` 在 DB2 不适用）。
- `TYPE-004`（blocker，DB2 写法）：金额字段用 `DECIMAL(p, s)` / `NUMERIC(p, s)`，禁用 `FLOAT` / `DOUBLE` / `REAL`。
- `TXN-002`（blocker，DB2 写法）：`DELETE` 必须带 `WHERE`（整体删除须经 TXN-003 行数确认 + TXN-004 确认机制放行；`DELETE` 可由事务回滚）。`TRUNCATE` 无 `WHERE` 语法，只按 TXN-004 的确认机制判定（备份 / 重命名过渡）——**DB2 的 `TRUNCATE` 隐式提交、不可回滚，事务包裹不构成放行依据**（事务性 TRUNCATE 仅在 PostgreSQL / SQL Server 有效）。

## 常见错误速查

| 错误码 | 原因 | 解决方案 |
| ------ | ---- | -------- |
| -206 (参数无效) | 参数游标、过渡变量上下文失效、缺少 BEGIN ATOMIC | 改用变量游标；行级多语句必须 BEGIN ATOMIC |
| -440 (找不到过程) | 路径未包含模式或类型不匹配 | 语句级触发器用完全限定过程名；行级触发器放弃过程调用 |
| -797 (不支持触发语句) | BEFORE 触发器内修改数据、表达式违规 | 改为 AFTER，仅用直接列引用 |
| -104 (语法错误) | LABEL main: 非法、CREATE OR REPLACE TRIGGER 不支持早期版本 | 使用 main: BEGIN ... END main;；可改用普通 `DROP TABLE` + `CREATE` 重建（注意：`DROP TABLE IF EXISTS` 对 CGTT 的适用性按 DB2 版本核对） |

## 验证检查清单

- [ ] 所有多事件触发器已拆分（TRIG-001）
- [ ] 行级触发器为 AFTER，多语句时使用 BEGIN ATOMIC（TRIG-003/004）
- [ ] 行级触发器内无函数包裹过渡变量（TRIG-005）
- [ ] 语句级触发器仅含 CALL 模式.过程（TRIG-002）
- [ ] 存储过程使用变量游标，异常消息变量在头部声明（PROC-003/004）
- [ ] CGTT 使用 ON COMMIT PRESERVE ROWS；不声明主键/外键约束，索引允许重复（TMP-001/002/004）
- [ ] 完全限定模式名，参数类型严格一致（SCH-001）
- [ ] 脚本用 @ 结束，顺序正确（EXE-001/002）
- [ ] 建表幂等写法已按所用 DB2 版本核对 `IF NOT EXISTS` 支持，或改用字典视图 / 异常处理器（IDEM-001）
- [ ] 限定行数用 `FETCH FIRST n ROWS ONLY`（DML-004）
- [ ] 金额字段用 `DECIMAL`，未用浮点类型（TYPE-004）
- [ ] `DELETE` 带 `WHERE`；`TRUNCATE` 经 TXN-004 确认机制（备份 / 重命名过渡；DB2 上事务包裹无效）（TXN-002）
- [ ] Oracle→DB2 移植场景才勾选 PROC-006 等「移植专用」条目
