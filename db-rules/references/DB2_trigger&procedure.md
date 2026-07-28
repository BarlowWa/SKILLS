DB2 LUW 触发器移植终极规则清单
（基于真实项目反复调试，v11.5+ 环境）

多事件触发器必须拆分

INSERT OR UPDATE OR DELETE → 拆成三个单事件触发器。

语句级触发器 (FOR EACH STATEMENT) 只允许 CALL

禁止变量、游标、条件、异常处理及任何 DML。

调用时必须使用完全限定名：CALL 模式名.存储过程名()。

行级触发器 (FOR EACH ROW) 严格受限

仅使用 AFTER 行级触发器执行数据修改；BEFORE 行级触发器禁止任何 INSERT/UPDATE/DELETE。

若需执行多条 SQL 语句，必须使用 BEGIN ATOMIC ... END;，禁止单独使用 BEGIN ... END（否则过渡变量 NEW/OLD 在内层失效，报 SQLCODE=-206）。

CALL 或 WHERE 条件中不能对过渡变量使用表达式/函数（如 TRIM(O.col)），只能直接传递 NEW.col / OLD.col。

WHEN 子句仅用于简单防重入条件或子查询，不用来替代业务逻辑。

复杂业务逻辑必须封装到存储过程，由语句级触发器调用；若行级触发器逻辑极简（如单表 UPDATE SET col = NEW.col WHERE col = OLD.col），可直接写在 BEGIN ATOMIC 中。

临时表使用规范

必须使用 CREATE GLOBAL TEMPORARY TABLE ... ON COMMIT PRESERVE ROWS NOT LOGGED。

不支持主键，只能建唯一/普通索引；若使用行级触发器直接插入可能产生重复，建议去掉唯一索引，在存储过程中用 SELECT DISTINCT。

Guard 表同样使用 CGTT，通过 guard_cnt 计数实现防重入。

存储过程编写规范

使用 CREATE OR REPLACE PROCEDURE ... LANGUAGE SQL main: BEGIN ... END main。

所有声明集中在头部（变量 → 游标 → 异常处理器）。

优先使用变量游标，避免参数游标导致 -206。

异常处理器：DECLARE EXIT HANDLER FOR SQLEXCEPTION，内部用 GET DIAGNOSTICS 获取信息后 RESIGNAL；处理器的 BEGIN...END 内部禁止声明变量（需提前在 main: 头部声明）。

循环控制避免直接使用 WHILE SQLCODE = 0，改用 LOOP + FETCH + SET v_sqlcode = SQLCODE 局部变量判断。

函数替换：NVL → COALESCE，SQL%ROWCOUNT → GET DIAGNOSTICS ROW_COUNT，TO_CHAR → CAST，保留字列名用双引号（如 "OFFSET"）。

类型与模式路径

存储过程参数类型必须与调用时传递的列类型精确一致。

触发器、存储过程、表尽量同一模式，或调用时使用完全限定名。

执行前设置：SET SCHEMA 模式名; SET PATH = 模式名, SYSTEM PATH;

编译与执行顺序

脚本以 @ 作为语句分隔符（db2 -td@ -f）。

创建顺序：基础表 → 临时表/日志表 → 存储过程 → 行级触发器 → 语句级触发器。

行级触发器创建后立即插入一行测试。

常见错误速查

错误码	原因	解决方案
-206 (参数无效)	参数游标、过渡变量上下文失效、缺少 BEGIN ATOMIC	改用变量游标；行级多语句必须 BEGIN ATOMIC
-440 (找不到过程)	路径未包含模式或类型不匹配	语句级触发器用完全限定过程名；行级触发器放弃过程调用
-797 (不支持触发语句)	BEFORE 触发器内修改数据、表达式违规	改为 AFTER，仅用直接列引用
-104 (语法错误)	LABEL main: 非法、CREATE OR REPLACE TRIGGER 不支持早期版本	使用 main: BEGIN ... END main;；CGTT 用 DROP TABLE IF EXISTS + CREATE
验证检查清单

✅ 所有多事件触发器已拆分

✅ 行级触发器为 AFTER，多语句时使用 BEGIN ATOMIC

✅ 行级触发器内无函数包裹过渡变量（如 TRIM(O.col) 改为直接比较或移入过程）

✅ 语句级触发器仅含 CALL 模式.过程

✅ 存储过程使用变量游标，异常消息变量在头部声明

✅ CGTT 使用 ON COMMIT PRESERVE ROWS，索引允许重复

✅ 完全限定模式名，参数类型严格一致

✅ 脚本用 @ 结束，顺序正确