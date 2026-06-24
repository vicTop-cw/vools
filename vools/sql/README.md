# vools.sql — SQL 方言框架

`vools.sql` 是 vools 库的 SQL 方言子包，提供统一的 SQL 方言抽象与构建能力，支持多种数据库的 SQL 生成、连接管理与结果封装。通过一致的接口，你可以在不同数据库间无缝切换，降低多数据库适配的开发成本。

---

## 目录

- [支持的方言](#支持的方言)
- [核心特性](#核心特性)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [API 概览](#api-概览)
- [各方言统一接口](#各方言统一接口)
- [子模块结构](#子模块结构)

---

## 支持的方言

`vools.sql` 目前支持以下数据库方言：

| 数据库     | 模块名       | 驱动库              | 状态   |
|------------|--------------|---------------------|--------|
| SQLite     | `sqlite`     | sqlite3（标准库）   | ✅ 完整 |
| PostgreSQL | `postgres`   | psycopg2 / psycopg  | ✅ 完整 |
| MySQL      | `mysql`      | pymysql / mysql-connector | ⏳ 计划中 |
| Oracle     | `oracle`     | cx_Oracle / oracledb | ⏳ 计划中 |
| SQL Server | `mssql`      | pymssql / pyodbc    | ⏳ 计划中 |

> 所有方言均接入 `Dialect` 抽象基类和统一连接接口。

---

## 核心特性

- **统一连接接口**：所有数据库使用相同的 `Connection` 抽象，包括连接管理、SQL 执行、事务控制
- **SQL 构建器**：链式调用的 SQL 构建器，支持 SELECT/INSERT/UPDATE/DELETE 四种语句
- **类型映射**：Python 类型与 SQL 类型之间的自动转换和推断，支持方言特有类型
- **参数化查询**：内置参数化查询支持，避免 SQL 注入风险
- **结果集封装**：`ResultSet` 和 `Row` 封装查询结果，支持多种访问方式
- **方言管理器**：`DialectManager` 统一管理方言注册、配置和实例化
- **延迟加载**：方言模块采用延迟导入，缺少驱动时不影响整体使用
- **装饰器支持**：`@sql_function` 和 `@sql_module` 装饰器简化 SQL 操作函数定义

---

## 架构设计

### 整体架构图

```
                    ┌──────────────────────────────────┐
                    │       Python 应用代码             │
                    │  (直接调用 / 装饰器 / 构建器)     │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │        Dialect (ABC)             │
                    │   所有方言的统一抽象基类           │
                    │  - get_type_mapper() 类型映射     │
                    │  - create_connection() 创建连接   │
                    │  - quote_identifier() 标识符引用  │
                    │  - get_builder_class() 构建器     │
                    │  - get_paramstyle() 参数风格      │
                    └───────────────┬──────────────────┘
                                    │
         ┌──────────────┬───────────┴──────────┬──────────────┐
         │              │                      │              │
    ┌────▼────┐   ┌────▼────┐           ┌────▼────┐   ┌────▼────┐
    │ SQLite  │   │PostgreSQL│  ...     │  MySQL  │   │ Oracle  │
    │         │   │          │ (计划中)  │         │   │ SQL Svr │
    └────┬────┘   └────┬────┘           └────┬────┘   └────┬────┘
         │              │                      │              │
    ┌────▼──────────────▼──────────────────────▼──────────────▼────┐
    │                   共享核心基础设施 (core/)                     │
    │  TypeMapper | Connection | ResultSet | Builder | Decorators   │
    └───────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │   DialectManager (manager.py)     │
                    │  方言注册 / 配置管理 / 实例缓存    │
                    │  可用性检测 / 配置持久化           │
                    └──────────────────────────────────┘
```

### Dialect 抽象基类

`Dialect` 是所有数据库方言实现的统一抽象基类（定义在 `core/dialect.py`），定义了标准接口规范：

**子类必须实现的抽象方法：**

| 方法 | 说明 |
|------|------|
| `get_type_mapper() -> SqlTypeMapper` | 获取方言的类型映射器 |
| `create_connection(**kwargs) -> Connection` | 创建数据库连接 |
| `quote_identifier(identifier: str) -> str` | 引用标识符（表名、列名等） |
| `quote_string(value: str) -> str` | 引用字符串值 |
| `get_builder_class() -> type` | 获取 SQL 构建器类 |
| `get_paramstyle() -> str` | 获取参数占位符风格 |

**子类可以重写的方法：**

| 方法 | 说明 | 默认值 |
|------|------|--------|
| `is_available() -> bool` | 检查驱动是否可用 | 尝试 import driver 模块 |
| `get_config() -> DialectConfig` | 获取方言配置 | 抛出 NotImplementedError |

---

## 快速开始

### 示例：SQLite 内存数据库

```python
from vools.sql.sqlite import connect

# 创建并连接内存数据库
conn = connect(':memory:')

# 建表
conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)')

# 插入数据
conn.execute("INSERT INTO users (name, age) VALUES (?, ?)", ('Alice', 25))
conn.execute("INSERT INTO users (name, age) VALUES (?, ?)", ('Bob', 30))

# 查询数据
result = conn.execute('SELECT * FROM users WHERE age > ?', (20,))
for row in result:
    print(row.id, row.name, row.age)

# 关闭连接
conn.close()
```

### 示例：PostgreSQL 查询

```python
from vools.sql.postgres import connect, is_available

# 检查驱动是否可用
if is_available():
    # 创建连接
    conn = connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='your_password',
        database='testdb'
    )

    # 使用构建器构建 SQL
    from vools.sql import SqlBuilder
    builder = SqlBuilder()
    sql, params = builder.select('id', 'name') \
        .from_('users') \
        .where('age > %s', 20) \
        .order_by('name') \
        .build()

    # 执行查询
    result = conn.execute(sql, params)
    print(f"找到 {len(result)} 条记录")

    conn.close()
```

### 示例：使用方言管理器

```python
from vools.sql import list_available, get_dialect, create_dialect

# 列出所有可用方言
available = list_available()
print(f"可用方言: {available}")

# 获取方言类
dialect_cls = get_dialect('sqlite')
print(f"SQLite 方言类: {dialect_cls}")

# 创建方言实例
dialect = create_dialect('sqlite')
conn = dialect.create_connection(database=':memory:')
conn.connect()
result = conn.execute('SELECT 1')
print(result.scalar())
conn.close()
```

### 示例：使用装饰器

```python
from vools.sql import sql_function, sql_module
from vools.sql.sqlite import connect

conn = connect(':memory:')
conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)')

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

# 使用
repo = UserRepository()
repo.add_user('Alice', 25)
users = repo.list_users()
print(f"用户列表: {users}")

conn.close()
```

---

## API 概览

### 顶层导出 (`vools.sql`)

**核心基础设施：**

| 名称 | 类型 | 说明 |
|------|------|------|
| `SqlTypeMapper` | 类 | SQL 类型映射器 |
| `PY_TO_SQL` | 字典 | Python 类型到 SQL 类型映射表 |
| `SQL_TO_PY` | 字典 | SQL 类型到 Python 类型映射表 |
| `infer_arg_types()` | 函数 | 根据参数值推断 SQL 类型 |
| `infer_ret_type()` | 函数 | 根据返回类型推断 SQL 类型 |
| `convert_args()` | 函数 | 转换参数为 SQL 兼容格式 |
| `convert_result()` | 函数 | 转换 SQL 结果为 Python 类型 |
| `SqlBuilder` | 类 | SQL 构建器抽象基类 |
| `BaseSqlBuilder` | 类 | SQL 构建器基础实现 |
| `Connection` | 类 | 数据库连接抽象基类 |
| `ResultSet` | 类 | 查询结果集封装 |
| `Row` | 类 | 单行数据封装 |
| `sql_function` | 装饰器 | SQL 函数装饰器 |
| `sql_module` | 装饰器 | SQL 模块（类）装饰器 |
| `sql_func_name` | 装饰器 | 指定 SQL 函数名 |
| `Dialect` | 类 | SQL 方言抽象基类 |
| `DialectConfig` | 数据类 | 方言配置 |
| `has_dialect()` | 函数 | 检查方言是否已注册 |

**管理器 API：**

| 名称 | 类型 | 说明 |
|------|------|------|
| `manager` | 单例 | DialectManager 全局实例 |
| `DialectManager` | 类 | SQL 方言统一管理器 |
| `register_dialect()` | 函数 | 注册方言 |
| `get_dialect()` | 函数 | 获取方言类 |
| `create_dialect()` | 函数 | 创建方言实例 |
| `is_available()` | 函数 | 检查方言是否可用 |
| `list_dialects()` | 函数 | 列出所有已注册方言 |
| `list_available()` | 函数 | 列出所有可用方言 |
| `get_config()` | 函数 | 获取方言配置 |
| `set_config()` | 函数 | 设置方言配置 |
| `save_config()` | 函数 | 保存配置到文件 |
| `load_config()` | 函数 | 从文件加载配置 |
| `get_config_file_path()` | 函数 | 获取配置文件路径 |
| `clear_instance_cache()` | 函数 | 清除方言实例缓存 |

**方言模块（延迟加载）：**

| 名称 | 说明 |
|------|------|
| `sqlite` | SQLite 方言模块 |
| `postgres` | PostgreSQL 方言模块 |
| `mysql` | MySQL 方言模块（计划中） |
| `oracle` | Oracle 方言模块（计划中） |
| `mssql` | SQL Server 方言模块（计划中） |

---

## 各方言统一接口

每个方言模块都提供一致的便捷接口：

```python
# 便捷连接函数
conn = dialect_module.connect(**connection_params)

# 检查驱动可用性
available = dialect_module.is_available()

# 方言类
DialectClass = dialect_module.SqliteDialect  # 或 PostgresDialect 等

# 连接类
ConnectionClass = dialect_module.SqliteConnection  # 或 PostgresConnection 等
```

**Connection 统一接口（所有方言共享）：**

| 方法/属性 | 说明 |
|----------|------|
| `connect(**kwargs)` | 建立数据库连接 |
| `close()` | 关闭数据库连接 |
| `execute(sql, params=None) -> ResultSet` | 执行 SQL 查询 |
| `executemany(sql, seq_of_params) -> int` | 批量执行 SQL |
| `commit()` | 提交事务 |
| `rollback()` | 回滚事务 |
| `cursor()` | 获取底层游标对象 |
| `is_connected` | 连接是否已建立（属性） |
| `with conn:` | 上下文管理器支持 |

**ResultSet 常用方法：**

| 方法/属性 | 说明 |
|----------|------|
| `fetchone() -> Row` | 获取下一行 |
| `fetchmany(size) -> List[Row]` | 获取多行 |
| `fetchall() -> List[Row]` | 获取所有剩余行 |
| `first() -> Row` | 获取第一行 |
| `scalar() -> Any` | 获取第一行第一列的值 |
| `to_list() -> List[dict]` | 转为字典列表 |
| `to_dataframe() -> DataFrame` | 转为 pandas DataFrame |
| `columns` | 列名列表（属性） |
| `rowcount` | 受影响行数（属性） |
| `len(result)` | 行数 |
| `for row in result:` | 迭代支持 |
| `result[0]` | 索引访问 |

---

## 子模块结构

```
vools/sql/
├── __init__.py            # 包入口，延迟导入各方言模块
├── README.md              # 本文件
├── manager.py             # DialectManager 统一管理器
│   ├── DialectManager     # 管理器主类
│   └── manager            # 全局单例
├── core/                  # 核心基础设施
│   ├── __init__.py
│   ├── types.py           # 类型映射 (SqlTypeMapper)
│   ├── config.py          # 方言配置 (DialectConfig)
│   ├── dialect.py         # 方言抽象基类 (Dialect)
│   ├── builder.py         # SQL 构建器 (SqlBuilder / BaseSqlBuilder)
│   ├── connection.py      # 连接抽象基类 (Connection)
│   ├── result.py          # 结果集封装 (ResultSet / Row)
│   └── decorators.py      # SQL 装饰器 (sql_function / sql_module)
├── sqlite/                # SQLite 方言
│   ├── __init__.py
│   ├── dialect.py         # SqliteDialect 实现
│   └── connection.py      # SqliteConnection 实现
├── postgres/              # PostgreSQL 方言
│   ├── __init__.py
│   ├── dialect.py         # PostgresDialect 实现
│   └── connection.py      # PostgresConnection 实现
├── mysql/                 # MySQL 方言（计划中）
├── oracle/                # Oracle 方言（计划中）
└── mssql/                 # SQL Server 方言（计划中）
```

### 各方言模块典型结构

每个方言模块通常包含以下文件：

| 文件 | 说明 |
|------|------|
| `__init__.py` | 模块入口，导出公共 API，提供 connect() / is_available() |
| `dialect.py` | 方言类实现（继承 Dialect 抽象基类） |
| `connection.py` | 连接类实现（继承 Connection 抽象基类） |

> **注意**：不同方言模块的内部结构可能略有差异，但对外暴露的接口是统一的。
