# vools.sql.core - 验证清单

## 包结构与入口

- [x] `vools/sql/` 目录存在且包含 `__init__.py`
- [x] `vools/sql/core/` 目录存在且包含 `__init__.py`
- [x] `vools/sql/manager.py` 文件存在
- [x] `import vools.sql` 可以成功执行且不报错
- [x] `import vools.sql.core` 可以成功执行且不报错

## 类型映射系统 (types.py)

- [x] `SqlTypeMapper` 类存在且为静态工具类风格（与 CTypeMapper 一致）
- [x] 定义了 `PY_TO_SQL` 基础类型映射表（int, float, str, bool, datetime 等）
- [x] 定义了 `SQL_TO_PY` 反向类型映射表
- [x] `register_type(py_type, sql_type)` 方法可用
- [x] `get_sql_type(py_type)` 方法可用
- [x] `get_py_type(sql_type)` 方法可用
- [x] `infer_arg_types(args)` 方法可用，返回 SQL 类型列表
- [x] `infer_ret_type(ret_type)` 方法可用
- [x] `convert_args(args, sql_types)` 方法可用，转换参数值
- [x] `convert_result(result, py_type)` 方法可用，转换结果值
- [x] 支持 datetime、Decimal、JSON 等常见 SQL 类型
- [x] 代码风格与 `bridge/core/types.py` 保持一致

## 配置与方言基类 (config.py + dialect.py)

- [x] `DialectConfig` dataclass 存在，包含必要配置字段
- [x] 字段包括：name, driver, default_port, connection_params 等
- [x] `Dialect` 抽象基类存在
- [x] 定义了抽象方法：`get_type_mapper()`, `create_connection()`, `quote_identifier()`, `get_builder_class()` 等
- [x] `register_dialect(name, dialect_class)` 函数可用
- [x] `get_dialect(name)` 函数可用
- [x] 方言注册表支持动态增删查
- [x] 数据类设计风格与 `LanguageConfig` 一致

## SQL 构建器抽象 (builder.py)

- [x] `SqlBuilder` 抽象基类存在
- [x] 定义了 SELECT 相关方法：`select()`, `from_()`, `where()`, `and_()`, `or_()`, `order_by()`, `group_by()`, `having()`, `limit()`, `offset()`
- [x] 定义了 DML 方法：`insert_into()`, `values()`, `update()`, `set_()`, `delete_from()`
- [x] 定义了 JOIN 方法：`join()`, `left_join()`, `right_join()`, `inner_join()`
- [x] `build()` 方法返回 `(sql_string, params)` 元组
- [x] 所有链式方法返回 builder 自身（支持链式调用）
- [x] 参数占位符抽象正确（支持不同方言风格）
- [x] 提供 `BaseSqlBuilder` 基础实现类

## 连接抽象 (connection.py)

- [x] `Connection` 抽象基类存在
- [x] 定义了抽象方法：`connect()`, `close()`, `execute()`, `executemany()`, `commit()`, `rollback()`, `cursor()`
- [x] 支持上下文管理器协议（`__enter__`, `__exit__`）
- [x] `is_connected` 属性可用
- [x] `execute()` 返回 `ResultSet` 对象
- [x] 接口设计符合 PEP 249 DB API 2.0 规范
- [x] 代码风格与 vools 其他抽象类一致

## 结果集抽象 (result.py)

- [x] `ResultSet` 类存在
- [x] 支持迭代协议（`__iter__`），逐行返回
- [x] 支持索引访问（`result[0]`）
- [x] 行支持列名访问（`row['column']` 或 `row.column`）
- [x] `fetchone()` 方法可用
- [x] `fetchall()` 方法可用
- [x] `fetchmany(size)` 方法可用
- [x] `columns` 属性返回列名列表
- [x] `rowcount` 属性返回受影响行数
- [x] 自动进行 SQL → Python 类型转换

## 装饰器工具 (decorators.py)

- [x] `sql_function` 装饰器可用
- [x] 支持从函数签名类型注解推断参数和返回类型
- [x] 支持自动参数转换（Python → SQL）
- [x] 支持自动结果转换（SQL → Python）
- [x] 支持指定 dialect 参数
- [x] `sql_module` 类装饰器可用
- [x] 装饰器使用风格与 `@bridge_function` 一致

## 方言管理器 (manager.py)

- [x] `DialectManager` 类存在
- [x] 单例模式实现
- [x] `register_dialect(name, config, dialect_class)` 方法
- [x] `get_dialect(name)` 方法
- [x] `is_available(name)` 方法
- [x] `list_dialects()` 方法
- [x] `save_config()` / `load_config()` 配置持久化
- [x] 全局 `manager` 实例可用
- [x] 提供模块级便捷函数
- [x] API 风格与 `BridgeManager` 高度一致

## 延迟加载机制 (sql/__init__.py)

- [x] 采用 `__getattr__` 动态导入机制
- [x] `__dir__` 方法返回所有可用导出名称
- [x] 导入 `vools.sql` 时不会加载具体方言模块
- [x] 预留 mysql、postgres、sqlite 等方言的延迟加载位置
- [x] 导出 core 模块的所有公共 API
- [x] 导出 manager 的便捷函数
- [x] 延迟加载逻辑与 `bridge/__init__.py` 风格一致

## 代码风格与一致性

- [x] 所有模块都有清晰的文档字符串（docstring）
- [x] 命名规范与 bridge 框架保持一致
- [x] 类设计模式（静态工具类、抽象基类）与 bridge 一致
- [x] 使用类型注解（type hints）
- [x] `__all__` 导出列表完整准确
- [x] 代码组织方式与 bridge/core 对应模块一一对应
- [x] 不引入不必要的第三方依赖
