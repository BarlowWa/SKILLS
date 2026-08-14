# DB2 LUW 触发器/存储过程规则清单
（基于 Oracle→DB2 移植真实项目反复调试，v11.5+ 环境）

> 本文件主体为 **Oracle→DB2 移植**场景的规则与经验。编写**原生** DB2 脚本时，仅适用其中标注为 DB2 通用约束的条目（如 TRIG-001、TRIG-003、PROC-001 等），移植替换表（PROC-006）等 Oracle 迁移专用条目不适用。

## 严重级别约定

| 级别 | 含义 |
| ---- | ---- |
| blocker | 必须修复，否则触发器/存储过程无法通过编译或运行时报错 |
| warning | 建议项，改善可维护性/性能 |

## TRIG：触发器

- **TRIG-001**（blocker）：多事件触发器必须拆分——`INSERT OR UPDATE OR DELETE` 拆成三个单事件触发器。
- **TRIG-002**（blocker）：语句级触发器（`FOR EACH STATEMENT`）只允许 `CALL`；禁止变量、游标、条件、异常处理及任何 DML；调用必须用完全限定名 `CALL 模式名.存储过程名()`。
- **TRIG-003**（blocker）：行级触发器（`FOR EACH ROW`）严格受限——仅用 AFTER 行级触发器执行数据修改；BEFORE 行级触发器禁止任何 INSERT/UPDATE/DELETE。
- **TRIG-004**（blocker）：行级触发器若需执行多条 SQL，必须用 `BEGIN ATOMIC ... END;`，禁止单独 `BEGIN ... END`（否则过渡变量 NEW/OLD 在内层失效，报 SQLCODE=-206）。
- **TRIG-005**（blocker）：`CALL` 或 `WHERE` 条件中不能对过渡变量使用表达式/函数（如 `TRIM(O.col)`），只能直接传递 `NEW.col` / `OLD.col`。（本项目约束；个别 DB2 版本允许部分表达式，但为兼容性统一禁止）
- **TRIG-006**（warning）：`WHEN` 子句仅用于简单防重入条件或子查询，不用来替代业务逻辑。
- **TRIG-007**（warning）：复杂业务逻辑封装到存储过程，由语句级触发器调用；行级触发器逻辑极简（如单表 `UPDATE SET col = NEW.col WHERE col = OLD.col`）时才可直接写在 `BEGIN ATOMIC` 中。

## TMP：临时表

- **TMP-001**（blocker）：必须使用 `CREATE GLOBAL TEMPORARY TABLE ... ON COMMIT PRESERVE ROWS NOT LOGGED`。
- **TMP-002**（blocker）：CGTT 不支持主键，只能建唯一/普通索引；行级触发器直接插入可能产生重复，建议去掉唯一索引，在存储过程中用 `SELECT DISTINCT`。
- **TMP-003**（warning）：Guard 表同样使用 CGTT，通过 `guard_cnt` 计数实现防重入。

## PROC：存储过程

- **PROC-001**（blocker）：使用 `CREATE OR REPLACE PROCEDURE ... LANGUAGE SQL main: BEGIN ... END main`。
- **PROC-002**（warning）：所有声明集中在头部（变量 → 游标 → 异常处理器）。
- **PROC-003**（blocker）：优先使用变量游标，避免参数游标导致 -206。
- **PROC-004**（blocker）：异常处理器 `DECLARE EXIT HANDLER FOR SQLEXCEPTION`，内部用 `GET DIAGNOSTICS` 获取信息后 `RESIGNAL`；处理器的 BEGIN...END 内部禁止声明变量（需提前在 main: 头部声明）。
- **PROC-005**（warning）：循环控制避免直接使用 `WHILE SQLCODE = 0`，改用 `LOOP + FETCH + SET v_sqlcode = SQLCODE` 局部变量判断。
- **PROC-006**（移植专用，blocker）：函数替换（仅 Oracle→DB2 移植适用）：`NVL` → `COALESCE`，`SQL%ROWCOUNT` → `GET DIAGNOSTICS ROW_COUNT`，`TO_CHAR` → `CAST`，保留字列名用双引号（如 `"OFFSET"`）。

## SCH：类型与模式路径

- **SCH-001**（blocker）：存储过程参数类型必须与调用时传递的列类型精确一致。
- **SCH-002**（warning）：触发器、存储过程、表尽量同一模式，或调用时使用完全限定名。
- **SCH-003**（warning）：执行前设置 `SET SCHEMA 模式名; SET PATH = 模式名, SYSTEM PATH;`。

## EXE：编译与执行顺序

- **EXE-001**（blocker）：脚本以 `@` 作为语句分隔符（`db2 -td@ -f`）。
- **EXE-002**（blocker）：创建顺序——基础表 → 临时表/日志表 → 存储过程 → 行级触发器 → 语句级触发器。
- **EXE-003**（warning）：行级触发器创建后立即插入一行测试。

## 常见错误速查

| 错误码 | 原因 | 解决方案 |
| ------ | ---- | -------- |
| -206 (参数无效) | 参数游标、过渡变量上下文失效、缺少 BEGIN ATOMIC | 改用变量游标；行级多语句必须 BEGIN ATOMIC |
| -440 (找不到过程) | 路径未包含模式或类型不匹配 | 语句级触发器用完全限定过程名；行级触发器放弃过程调用 |
| -797 (不支持触发语句) | BEFORE 触发器内修改数据、表达式违规 | 改为 AFTER，仅用直接列引用 |
| -104 (语法错误) | LABEL main: 非法、CREATE OR REPLACE TRIGGER 不支持早期版本 | 使用 main: BEGIN ... END main;；CGTT 用 DROP TABLE IF EXISTS + CREATE |

## 验证检查清单

- [ ] 所有多事件触发器已拆分（TRIG-001）
- [ ] 行级触发器为 AFTER，多语句时使用 BEGIN ATOMIC（TRIG-003/004）
- [ ] 行级触发器内无函数包裹过渡变量（TRIG-005）
- [ ] 语句级触发器仅含 CALL 模式.过程（TRIG-002）
- [ ] 存储过程使用变量游标，异常消息变量在头部声明（PROC-003/004）
- [ ] CGTT 使用 ON COMMIT PRESERVE ROWS，索引允许重复（TMP-001/002）
- [ ] 完全限定模式名，参数类型严格一致（SCH-001）
- [ ] 脚本用 @ 结束，顺序正确（EXE-001/002）
