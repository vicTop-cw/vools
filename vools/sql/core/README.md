# vools.sql.core — SQL 核心基础设施

`vools.sql.core` 是 vools.sql 子包的核心基础设施模块，提供 SQL 方言框架的基础抽象和通用实现，包括类型映射、连接抽象、结果集封装、SQL 构建器、装饰器和方言基类等。

---

## 目录

- [模块概述](#模块概述)
- [核心组件](#核心组件)
- [类型映射系统](#类型映射系统)
- [连接抽象](#连接抽象)
- [结果集封装](#结果集封装)
- [SQL 构建器](#sql-构建器)
- [装饰器](#装饰器)
- [方言基类](#方言基类)
- [API 速查](#api-速查)

---

## 模块概述

`vools.sql.core` 包含以下核心模块：

| 模块 | 文件 | 功能简介 |
|------|------|----------|
| 类型映射 | `types.py` | Python ↔ SQL 类型映射与转换 |
| 方言配置 | `config.py` | 方言配置数据类 |
| 方言基类 | `dialect.py` | Dialect 抽象基类与全局注册表 |
| SQL 构建器 | `builder.py` | SqlBuilder 抽象基类与 BaseSqlBuilder 基础实现 |
| 连接抽象 | `connection.py` | Connection 数据库连接抽象基类 |
| 结果集封装 | `result.py` | ResultSet 和 Row 结果集封装 |
| 装饰器 | `decorators.py` | sql_function / sql_module 装饰器 |

---

## 核心组件

### 设计原则

- **抽象优先**：所有核心功能均通过抽象基类定义接口
- **方言无关**：核心实现不依赖特定数据库驱动
- **易于扩展**：通过继承抽象基类即可添加新方言支持
- **类型安全**：完整的类型注解，支持静态类型检查

---

## 类型映射系统

### SqlTypeMapper

`SqlTypeMapper` 提供 Python 类型与 SQL 类型之间的自动转换和推断能力。

**核心功能：**

- `PY_TO_SQL`：Python 类型到 SQL 类型的映射表
- `SQL_TO_PY`：SQL 类型到 Python 类型的映射表
- `infer_arg_types()`：根据参数值推断 SQL 类型
- `infer_ret_type()`：根据返回类型推断 SQL 类型
- `convert_args()`：转换参数为 SQL 兼容格式
- `convert_result()`：转换 SQL 结果为 Python 类型
- `register_type()`：注册自定义类型映射

**支持的默认类型映射：**

| Python 类型 | SQL 类型 |
|-------------|---------|
| `int` | `INTEGER` |
| `float` | `DOUBLE` |
| `bool` | `BOOLEAN` |
| `str` | `VARCHAR` |
| `bytes` | `BLOB` |
| `datetime.date` | `DATE` |
| `datetime.datetime` | `DATETIME` |
| `decimal.Decimal` | `DECIMAL` |
| `dict` / `list` | `JSON` |
| `None` | `NULL` |

**使用示例：**

```python
from vools.sql.core import SqlTypeMapper, PY_TO_SQL, SQL_TO_PY

# 获取类型映射
sql_type = SqlTypeMapper.get_sql_type(int)  # 'INTEGER'
py_type = SqlTypeMapper.get_py_type('VARCHAR')  # str

# 推断参数类型
arg_types = SqlTypeMapper.infer_arg_types([1, "hello", 3.14])

# 注册自定义类型
SqlTypeMapper.register_type(MyCustomType, 'CUSTOM_TYPE')
```

---

## 连接抽象

### Connection（抽象基类）

`Connection` 是数据库连接的抽象基类，遵循 PEP 249 DB API 2.0 规范，为不同数据库方言提供统一的连接管理接口。

**必须实现的抽象方法：**

| 方法 | 说明 |
|------|------|
| `connect(**kwargs)` | 建立数据库连接 |
| `close()` | 关闭数据库连接 |
| `execute(sql, params=None)` | 执行 SQL 查询，返回 ResultSet |
| `executemany(sql, seq_of_params)` | 批量执行 SQL |
| `commit()` | 提交事务 |
| `rollback()` | 回滚事务 |
| `cursor()` | 获取底层游标对象 |

**属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `is_connected` | `bool` | 连接是否已建立 |

**使用示例：**

```python
from vools.sql.core import Connection

class MyConnection(Connection):
    def connect(self, **kwargs):
        # 实现连接逻辑
        self._conn = my_driver.connect(**kwargs)
        self._connected = True

    def close(self):
        if self._conn:
            self._conn.close()
            self._connected = False

    def execute(self, sql, params=None):
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return self._wrap_result(cursor)
    # ... 实现其他方法
```

---

## 结果集封装

### Row

`Row` 表示单行数据，支持多种访问方式：

- **列名访问**：`row['column_name']`
- **属性访问**：`row.column_name`
- **索引访问**：`row[0]`
- **迭代支持**：`for value in row`

**特点：**
- 不可变对象（immutable）
- 使用 `__slots__` 优化内存
- 支持多种访问方式

### ResultSet

`ResultSet` 封装查询结果集，提供便捷的结果处理方法。

**常用方法：**

| 方法 | 说明 |
|------|------|
| `fetchone()` | 获取下一行 |
| `fetchmany(size)` | 获取多行 |
| `fetchall()` | 获取所有剩余行 |
| `first()` | 获取第一行 |
| `scalar()` | 获取第一行第一列的值 |
| `to_list()` | 转为字典列表 |
| `to_dataframe()` | 转为 pandas DataFrame |

**属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `columns` | `list` | 列名列表 |
| `rowcount` | `int` | 受影响行数 |

**使用示例：**

```python
from vools.sql.core import ResultSet, Row

# 遍历结果集
result = conn.execute('SELECT * FROM users')
for row in result:
    print(row.id, row.name, row.age)

# 获取单个值
count = conn.execute('SELECT COUNT(*) FROM users').scalar()

# 转为字典列表
users = conn.execute('SELECT * FROM users').to_list()
```

---

## SQL 构建器

### SqlBuilder（抽象基类）

`SqlBuilder` 定义了 SQL 构建器的链式调用接口。

**必须实现的抽象方法：**

| 方法 | 说明 |
|------|------|
| `select(*columns)` | 指定查询列 |
| `from_(*tables)` | 指定查询表 |
| `where(condition, *params)` | WHERE 条件 |
| `and_(condition, *params)` | 添加 AND 条件 |
| `or_(condition, *params)` | 添加 OR 条件 |
| `order_by(*columns)` | ORDER BY 排序 |
| `group_by(*columns)` | GROUP BY 分组 |
| `having(condition, *params)` | HAVING 条件 |
| `limit(count)` | LIMIT 限制行数 |
| `offset(count)` | OFFSET 偏移量 |
| `insert_into(table, **values)` | INSERT 语句 |
| `update(table)` | UPDATE 语句 |
| `set_(**values)` | SET 子句 |
| `delete_from(table)` | DELETE 语句 |
| `build()` | 构建 SQL 和参数 |

### BaseSqlBuilder

`BaseSqlBuilder` 是 SQL 构建器的基础实现，提供通用的 SQL 构建逻辑。

**使用示例：**

```python
from vools.sql.core import BaseSqlBuilder

builder = BaseSqlBuilder()
sql, params = builder.select('id', 'name') \
    .from_('users') \
    .where('age > ?', 18) \
    .order_by('name') \
    .limit(10) \
    .build()

# sql: SELECT id, name FROM users WHERE age > ? ORDER BY name LIMIT ?
# params: [18, 10]
```

---

## 装饰器

### sql_function

`@sql_function` 装饰器简化 SQL 操作函数定义，函数体返回 SQL 语句和参数。

**特性：**
- 自动从类型注解推断参数类型
- 自动转换参数和返回值格式
- 支持连接对象注入

### sql_module

`@sql_module` 装饰器用于类，自动将类中定义的 SQL 函数转换为方法。

### sql_func_name

`@sql_func_name` 装饰器用于指定 SQL 函数名（可选）。

**使用示例：**

```python
from vools.sql.core import sql_function, sql_module
from vools.sql.sqlite import connect

conn = connect(':memory:')

# 函数装饰器
@sql_function(connection=conn)
def get_user(user_id: int) -> dict:
    return "SELECT * FROM users WHERE id = ?", (user_id,)

# 模块装饰器
@sql_module(connection=conn)
class UserRepository:
    def add_user(self, name: str, age: int) -> int:
        return "INSERT INTO users (name, age) VALUES (?, ?)", (name, age)

    def list_users(self) -> list:
        return "SELECT * FROM users"
```

---

## 方言基类

### Dialect（抽象基类）

`Dialect` 是所有数据库方言实现的统一抽象基类，定义了标准接口规范。

**必须实现的抽象方法：**

| 方法 | 说明 |
|------|------|
| `get_type_mapper() -> SqlTypeMapper` | 获取方言的类型映射器 |
| `create_connection(**kwargs) -> Connection` | 创建数据库连接 |
| `quote_identifier(identifier) -> str` | 引用标识符（表名、列名等） |
| `quote_string(value) -> str` | 引用字符串值 |
| `get_builder_class() -> type` | 获取 SQL 构建器类 |
| `get_paramstyle() -> str` | 获取参数占位符风格 |

**可选重写的方法：**

| 方法 | 说明 | 默认值 |
|------|------|--------|
| `is_available() -> bool` | 检查驱动是否可用 | 尝试 import driver 模块 |
| `get_config() -> DialectConfig` | 获取方言配置 | 抛出 NotImplementedError |

### 方言注册表

核心提供全局方言注册表功能：

| 函数 | 说明 |
|------|------|
| `register_dialect(name, cls)` | 注册方言 |
| `get_dialect(name)` | 获取方言类 |
| `list_dialects()` | 列出所有已注册方言 |
| `has_dialect(name)` | 检查方言是否已注册 |

**使用示例：**

```python
from vools.sql.core import Dialect, register_dialect, get_dialect

# 定义方言
class MySqlDialect(Dialect):
    def get_type_mapper(self):
        return SqlTypeMapper()

    def create_connection(self, **kwargs):
        return MySqlConnection(**kwargs)
    # ... 实现其他方法

# 注册方言
register_dialect('mysql', MySqlDialect)

# 获取方言
dialect_cls = get_dialect('mysql')
```

---

## API 速查

### 顶层导出

```python
from vools.sql.core import (
    # 类型映射
    SqlTypeMapper,
    PY_TO_SQL,
    SQL_TO_PY,
    infer_arg_types,
    infer_ret_type,
    convert_args,
    convert_result,

    # 方言配置
    DialectConfig,

    # 方言基类与注册表
    Dialect,
    register_dialect,
    get_dialect,
    list_dialects,
    has_dialect,

    # SQL 构建器
    SqlBuilder,
    BaseSqlBuilder,

    # 连接抽象
    Connection,

    # 结果集封装
    ResultSet,
    Row,

    # 装饰器
    sql_function,
    sql_module,
    sql_func_name,
)
```
