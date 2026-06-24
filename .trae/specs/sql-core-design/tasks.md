# vools.sql.core - 实现计划（分解与优先级任务列表）

## 目录结构规划

参考 bridge 框架结构，sql 子包将采用以下结构：

```
vools/sql/
├── __init__.py              # 延迟加载 + 统一导出
├── core/                    # 核心抽象层
│   ├── __init__.py          # core 模块导出
│   ├── types.py             # 类型映射系统（SqlTypeMapper）
│   ├── builder.py           # SQL 构建器抽象基类
│   ├── connection.py        # 连接抽象基类
│   ├── result.py            # 结果集抽象
│   ├── decorators.py        # 装饰器工具
│   ├── dialect.py           # 方言基类与注册
│   └── config.py            # 配置数据类
├── manager.py               # 方言统一管理器（DialectManager）
├── mysql/                   # MySQL 方言（后续实现）
├── postgres/                # PostgreSQL 方言（后续实现）
├── sqlite/                  # SQLite 方言（后续实现）
└── ...
```

---

## [x] Task 1: 创建 sql 子包骨架与 core 模块入口

- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 `vools/sql/` 目录及 `__init__.py`
  - 创建 `vools/sql/core/` 目录及 `__init__.py`
  - 建立与 bridge 框架一致的模块文档风格
  - 预留延迟加载机制的位置（后续 Task 完善）
- **Acceptance Criteria Addressed**: [AC-7, AC-8]
- **Test Requirements**:
  - `programmatic` TR-1.1: 可以成功 `import vools.sql` 和 `import vools.sql.core` 且不报错
  - `programmatic` TR-1.2: `vools.sql.__doc__` 和 `vools.sql.core.__doc__` 包含正确的模块说明
  - `human-judgement` TR-1.3: 目录结构和文件命名与 bridge 框架风格一致
- **Notes**: 参考 `vools/bridge/__init__.py` 和 `vools/bridge/core/__init__.py` 的文档风格

---

## [/] Task 2: 实现类型映射系统 (types.py)

- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 参考 bridge/core/types.py 的 CTypeMapper 设计模式
  - 实现 `SqlTypeMapper` 静态类，提供 Python ↔ SQL 类型双向映射
  - 定义基础类型映射表（PY_TO_SQL, SQL_TO_PY）
  - 支持自定义类型注册 `register_type()`
  - 提供参数类型推断 `infer_arg_types()` 和返回类型推断 `infer_ret_type()`
  - 提供参数值转换 `convert_args()` 和结果值转换 `convert_result()`
  - 支持 datetime、Decimal、JSON 等常见 SQL 类型
- **Acceptance Criteria Addressed**: [AC-1, AC-8]
- **Test Requirements**:
  - `programmatic` TR-2.1: `SqlTypeMapper.get_sql_type(int)` 返回正确的 SQL 类型标识
  - `programmatic` TR-2.2: `SqlTypeMapper.get_py_type('VARCHAR')` 返回 str 类型
  - `programmatic` TR-2.3: `SqlTypeMapper.register_type(custom_type, sql_type)` 可以成功注册并查询
  - `programmatic` TR-2.4: `infer_arg_types([1, "hello", 3.14])` 返回正确的 SQL 类型列表
  - `programmatic` TR-2.5: `convert_args()` 可以正确转换 Python 值为 SQL 兼容格式
  - `human-judgement` TR-2.6: 类设计和方法命名与 CTypeMapper 风格一致
- **Notes**: 基础 SQL 类型包括：INTEGER, BIGINT, FLOAT, DOUBLE, VARCHAR, CHAR, TEXT, BOOLEAN, DATE, DATETIME, TIMESTAMP, BLOB, DECIMAL, JSON

---

## [/] Task 3: 实现配置数据类与方言基类 (config.py + dialect.py)

- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 参考 bridge/manager.py 的 LanguageConfig 数据类设计
  - 实现 `DialectConfig` dataclass，包含方言名称、驱动名称、默认端口、连接参数模板等
  - 实现 `Dialect` 抽象基类，定义方言必须实现的接口
  - 方言基类需提供：类型映射获取、SQL 构建器工厂、连接工厂、标识符引用方法等
  - 实现方言注册机制 `register_dialect()` / `get_dialect()`
- **Acceptance Criteria Addressed**: [AC-2, AC-8]
- **Test Requirements**:
  - `programmatic` TR-3.1: `DialectConfig` 可以正确实例化并包含所有必要字段
  - `programmatic` TR-3.2: `Dialect` 抽象基类定义了所有必要的抽象方法
  - `programmatic` TR-3.3: `register_dialect('mysql', MySQLDialect)` 后可以通过 `get_dialect('mysql')` 获取
  - `human-judgement` TR-3.4: 数据类设计风格与 LanguageConfig 一致
- **Notes**: Dialect 抽象方法包括：get_type_mapper(), create_connection(), quote_identifier(), get_builder_class() 等

---

## [ ] Task 4: 实现 SQL 构建器抽象 (builder.py)

- **Priority**: high
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 定义 `SqlBuilder` 抽象基类
  - 定义链式调用接口：select(), from_(), where(), and_(), or_(), order_by(), group_by(), having(), limit(), offset()
  - 定义 DML 接口：insert_into(), values(), update(), set(), delete_from()
  - 定义 join 接口：join(), left_join(), right_join(), inner_join(), outer_join()
  - 定义 `build()` 方法返回 (sql_string, params) 元组
  - 提供参数占位符抽象（? / %s / $1 等不同方言风格）
  - 实现基础的 `BaseSqlBuilder` 提供通用逻辑，具体方言继承扩展
- **Acceptance Criteria Addressed**: [AC-3, AC-8]
- **Test Requirements**:
  - `programmatic` TR-4.1: `SqlBuilder` 抽象基类定义了所有核心方法
  - `programmatic` TR-4.2: 基础实现可以构建简单 SELECT 语句并返回 (sql, params)
  - `programmatic` TR-4.3: 链式调用不报错，每一步返回 builder 自身
  - `programmatic` TR-4.4: 参数化查询正确分离 SQL 字符串和参数列表
  - `human-judgement` TR-4.5: API 设计符合 Python 习惯，链式调用流畅
- **Notes**: 采用参数化查询，避免 SQL 注入；具体 SQL 生成由方言实现

---

## [x] Task 5: 实现连接抽象基类 (connection.py)

- **Priority**: high
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 参考 PEP 249 DB API 2.0 规范
  - 定义 `Connection` 抽象基类
  - 抽象方法：connect(), close(), execute(), executemany(), commit(), rollback(), cursor()
  - 定义上下文管理器支持（__enter__, __exit__）
  - 定义 `is_connected` 属性
  - 提供 execute 查询返回 ResultSet 的统一接口
- **Acceptance Criteria Addressed**: [AC-4, AC-8]
- **Test Requirements**:
  - `programmatic` TR-5.1: `Connection` 抽象基类定义了所有必要的抽象方法
  - `programmatic` TR-5.2: 可以用 with 语句使用连接（上下文管理器协议）
  - `programmatic` TR-5.3: Mock 实现可以正确调用 execute 并返回结果
  - `human-judgement` TR-5.4: 接口设计符合 PEP 249 规范且与 vools 风格一致
- **Notes**: 具体连接实现由各方言包提供，core 仅定义接口

---

## [x] Task 6: 实现结果集抽象 (result.py)

- **Priority**: high
- **Depends On**: Task 2, Task 5
- **Description**: 
  - 定义 `ResultSet` 类，封装查询结果
  - 支持迭代协议（__iter__），逐行返回
  - 支持索引访问（result[0] 获取第一行）
  - 支持列名访问（row['column_name'] 或 row.column_name）
  - 提供 `fetchone()`, `fetchall()`, `fetchmany(size)` 方法
  - 提供 `columns` 属性返回列名列表
  - 提供 `rowcount` 属性返回受影响行数
  - 集成类型映射，自动进行 SQL → Python 类型转换
- **Acceptance Criteria Addressed**: [AC-5, AC-8]
- **Test Requirements**:
  - `programmatic` TR-6.1: `ResultSet` 支持迭代，逐行返回数据
  - `programmatic` TR-6.2: 可以通过列名和索引访问行数据
  - `programmatic` TR-6.3: `fetchone()`, `fetchall()`, `fetchmany()` 行为正确
  - `programmatic` TR-6.4: `columns` 和 `rowcount` 属性正确
  - `human-judgement` TR-6.5: API 设计直观易用，符合 Python 习惯
- **Notes**: 行对象可以使用 namedtuple 或自定义 Row 类

---

## [/] Task 7: 实现装饰器工具 (decorators.py)

- **Priority**: medium
- **Depends On**: Task 2, Task 3, Task 5, Task 6
- **Description**: 
  - 参考 bridge/core/decorators.py 的 bridge_function 设计
  - 实现 `@sql_function` 装饰器，用于标记 SQL 操作函数
  - 支持从函数签名自动推断参数类型和返回类型
  - 支持自动参数转换（Python → SQL）
  - 支持自动结果转换（SQL → Python）
  - 支持指定方言 dialect 参数
  - 实现 `@sql_module` 类装饰器，批量处理类中的 SQL 方法
- **Acceptance Criteria Addressed**: [AC-6, AC-8]
- **Test Requirements**:
  - `programmatic` TR-7.1: `@sql_function` 装饰器可以正确包装函数
  - `programmatic` TR-7.2: 类型注解可以被正确解析并用于类型转换
  - `programmatic` TR-7.3: 装饰后的函数可以正常执行并返回正确类型的结果
  - `human-judgement` TR-7.4: 装饰器使用方式与 @bridge_function 风格一致
- **Notes**: 装饰器主要提供类型转换辅助，实际执行逻辑由连接对象完成

---

## [/] Task 8: 实现方言统一管理器 (manager.py)

- **Priority**: high
- **Depends On**: Task 3
- **Description**: 
  - 参考 bridge/manager.py 的 BridgeManager 设计
  - 实现 `DialectManager` 单例类
  - 功能：注册方言、查询方言状态、获取方言配置、创建连接
  - 支持配置持久化（save_config / load_config）
  - 提供全局便捷函数：register_dialect(), get_dialect(), list_dialects(), is_available()
  - 提供全局 `manager` 实例
- **Acceptance Criteria Addressed**: [AC-2, AC-8]
- **Test Requirements**:
  - `programmatic` TR-8.1: `DialectManager` 可以注册和查询方言
  - `programmatic` TR-8.2: 全局 `manager` 实例可用
  - `programmatic` TR-8.3: 便捷函数（register_dialect, get_dialect 等）正常工作
  - `human-judgement` TR-8.4: API 风格与 BridgeManager 高度一致
- **Notes**: 配置持久化格式与 bridge.manager 保持一致（JSON 文件）

---

## [ ] Task 9: 完善 sql/__init__.py 延迟加载机制

- **Priority**: medium
- **Depends On**: Task 1, Task 8
- **Description**: 
  - 参考 bridge/__init__.py 的延迟加载实现
  - 实现 `__getattr__` 动态导入各方言模块
  - 实现 `__dir__` 返回所有可用导出名称
  - 导出 core 模块的所有公共 API
  - 导出 manager 的所有便捷函数
  - 预留 mysql、postgres、sqlite 等方言的延迟加载位置
- **Acceptance Criteria Addressed**: [AC-7, AC-8]
- **Test Requirements**:
  - `programmatic` TR-9.1: `import vools.sql` 不会导入任何具体方言模块
  - `programmatic` TR-9.2: 访问 `vools.sql.manager` 等 core 功能正常
  - `programmatic` TR-9.3: `dir(vools.sql)` 列出所有预期的导出名称
  - `human-judgement` TR-9.4: 延迟加载逻辑与 bridge/__init__.py 风格一致
- **Notes**: 具体方言的延迟加载函数预留但实际加载逻辑在方言包实现后完善

---

## [x] Task 10: 完善 core/__init__.py 导出与文档

- **Priority**: medium
- **Depends On**: Task 2-7
- **Description**: 
  - 汇总 core 模块所有公共 API 到 __init__.py
  - 编写清晰的模块文档字符串
  - 确保 __all__ 列表完整准确
  - 检查所有导出名称的一致性
- **Acceptance Criteria Addressed**: [AC-7, AC-8]
- **Test Requirements**:
  - `programmatic` TR-10.1: `from vools.sql.core import *` 可以导入所有公共 API
  - `programmatic` TR-10.2: 所有导出的类和函数都可以正常访问
  - `human-judgement` TR-10.3: 导出列表和文档风格与 bridge/core/__init__.py 一致
- **Notes**: 保持与 bridge/core/__init__.py 相同的组织方式

---

## 任务依赖关系图

```
Task 1 (骨架)
   ├──> Task 2 (类型映射) ──┐
   ├──> Task 3 (配置+方言基类) ─┤
   │                         ├──> Task 4 (构建器)
   │                         ├──> Task 5 (连接抽象) ──> Task 6 (结果集)
   │                         └──> Task 7 (装饰器)
   ├──> Task 8 (管理器) ──> Task 9 (延迟加载)
   └──> Task 10 (core 导出)
```

并行执行建议：
- Task 2 和 Task 3 可以并行
- Task 4、Task 5 可以在 Task 2+3 完成后并行
- Task 8 可以在 Task 3 完成后与 Task 4/5 并行
