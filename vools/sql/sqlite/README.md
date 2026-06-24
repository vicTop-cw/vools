# vools.sql.sqlite — SQLite 方言

`vools.sql.sqlite` 是 vools SQL 框架的 SQLite 方言实现，基于 Python 标准库 `sqlite3`，提供零依赖的 SQLite 数据库访问能力。

---

## 目录

- [特性](#特性)
- [快速开始](#快速开始)
- [类型映射](#类型映射)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [注意事项](#注意事项)

---

## 特性

- **零依赖**：基于 Python 标准库 `sqlite3`，无需额外安装
- **内存数据库支持**：支持 `:memory:` 内存数据库，适合测试和临时数据
- **文件数据库支持**：支持本地文件数据库，持久化存储
- **事务支持**：完整的事务支持（commit / rollback）
- **参数化查询**：使用 `?` 占位符的参数化查询，防止 SQL 注入
- **上下文管理器**：支持 `with` 语句，自动管理连接和事务
- **类型亲和性**：遵循 SQLite 的类型亲和性规则（INTEGER / REAL / TEXT / BLOB / NUMERIC）

---

## 快速开始

### 基本使用

```python
from vools.sql.sqlite import connect

# 创建并连接内存数据库
conn = connect(':memory:')

# 建表
conn.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        email TEXT
    )
''')

# 插入数据（单条）
conn.execute(
    "INSERT INTO users (name, age, email) VALUES (?, ?, ?)",
    ('Alice', 25, 'alice@example.com')
)

# 批量插入
conn.executemany(
    "INSERT INTO users (name, age, email) VALUES (?, ?, ?)",
    [
        ('Bob', 30, 'bob@example.com'),
        ('Charlie', 35, 'charlie@example.com'),
    ]
)

# 查询数据
result = conn.execute(
    "SELECT * FROM users WHERE age > ?",
    (20,)
)

# 遍历结果
for row in result:
    print(f"ID: {row.id}, Name: {row.name}, Age: {row.age}")

# 获取第一行
first_row = result.first()
print(f"第一条记录: {first_row}")

# 获取标量值（第一行第一列）
count = conn.execute("SELECT COUNT(*) FROM users").scalar()
print(f"总记录数: {count}")

# 转为字典列表
users_list = result.to_list()
print(f"字典列表: {users_list}")

# 关闭连接
conn.close()
```

### 使用上下文管理器

```python
from vools.sql.sqlite import SqliteConnection

# with 语句自动管理事务和连接
# 无异常时自动 commit，有异常时自动 rollback
with SqliteConnection(database='test.db') as conn:
    conn.connect()
    conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
    conn.execute("INSERT INTO products (name, price) VALUES (?, ?)", ('Apple', 5.99))
    # 退出 with 块时自动提交并关闭连接
```

### 使用方言类

```python
from vools.sql.sqlite import SqliteDialect

# 创建方言实例
dialect = SqliteDialect()

# 检查驱动可用性（sqlite3 总是可用）
print(f"可用: {dialect.is_available()}")

# 获取类型映射器
type_mapper = dialect.get_type_mapper()
print(f"int 对应 SQL 类型: {type_mapper.get_sql_type(int)}")

# 标识符引用
print(dialect.quote_identifier('user name'))  # "user name"
print(dialect.quote_string("it's"))           # 'it''s'

# 创建连接
conn = dialect.create_connection(database=':memory:')
conn.connect()
result = conn.execute('SELECT 1 + 1')
print(result.scalar())  # 2
conn.close()
```

### 结合 SQL 构建器使用

```python
from vools.sql.sqlite import connect
from vools.sql import BaseSqlBuilder

conn = connect(':memory:')
conn.execute('CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)')
conn.execute("INSERT INTO users VALUES (1, 'Alice', 25)")
conn.execute("INSERT INTO users VALUES (2, 'Bob', 30)")

# 使用构建器构建 SELECT
builder = BaseSqlBuilder()
builder._paramstyle = 'qmark'  # SQLite 使用 qmark 风格
sql, params = builder.select('id', 'name') \
    .from_('users') \
    .where('age > ?', 20) \
    .order_by('name') \
    .limit(10) \
    .build()

result = conn.execute(sql, params)
print(f"查询到 {len(result)} 条记录")

# 使用构建器构建 INSERT
builder2 = BaseSqlBuilder()
builder2._paramstyle = 'qmark'
sql2, params2 = builder2.insert_into('users') \
    .values(id=3, name='Charlie', age=35) \
    .build()

conn.execute(sql2, params2)
print(f"插入后总数: {conn.execute('SELECT COUNT(*) FROM users').scalar()}")

conn.close()
```

---

## 类型映射

### Python → SQLite 类型映射

| Python 类型 | SQLite 类型亲和性 | 说明 |
|-------------|------------------|------|
| `int` | INTEGER | 整数类型 |
| `float` | REAL | 浮点数类型 |
| `str` | TEXT | 文本类型 |
| `bytes` | BLOB | 二进制大对象 |
| `bool` | INTEGER | 布尔值存储为 0/1 |
| `datetime.date` | TEXT | 日期存储为文本 |
| `datetime.datetime` | TEXT | 日期时间存储为文本 |
| `decimal.Decimal` | NUMERIC | 十进制数 |
| `None` | NULL | 空值 |

### SQLite → Python 类型映射

| SQLite 类型 | Python 类型 | 说明 |
|-------------|-------------|------|
| INTEGER / INT / BIGINT / SMALLINT / TINYINT | `int` | 整数 |
| FLOAT / DOUBLE / REAL | `float` | 浮点数 |
| BOOLEAN / BOOL | `bool` | 布尔值 |
| VARCHAR / CHAR / TEXT / STRING / CLOB | `str` | 文本 |
| BLOB / BINARY / VARBINARY | `bytes` | 二进制 |
| DATE | `datetime.date` | 日期 |
| DATETIME / TIMESTAMP | `datetime.datetime` | 日期时间 |
| DECIMAL / NUMERIC | `decimal.Decimal` | 十进制数 |
| JSON | `dict` | JSON 对象 |

> SQLite 使用动态类型系统，实际类型转换由 `sqlite3` 驱动处理。以上映射用于类型推断和文档参考。

---

## 配置说明

### DialectConfig 字段

`SqliteDialect` 使用的 `DialectConfig` 配置：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | `'sqlite'` | 方言名称 |
| `driver` | `str` | `'sqlite3'` | 驱动模块名 |
| `default_port` | `int` | `0` | 默认端口（文件数据库为 0） |
| `default_host` | `str` | `''` | 默认主机（空） |
| `default_user` | `str` | `''` | 默认用户名（空） |
| `default_database` | `str` | `':memory:'` | 默认数据库 |
| `paramstyle` | `str` | `'qmark'` | 参数占位符风格（?） |
| `identifier_quote` | `str` | `'"'` | 标识符引用符（双引号） |
| `string_quote` | `str` | `"'"` | 字符串引用符（单引号） |
| `connection_params` | `dict` | `{}` | 额外连接参数 |
| `extra_config` | `dict` | `{}` | 额外配置 |

### SqliteConnection 连接参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `database` | `str` | `':memory:'` | 数据库文件路径，或 `':memory:'` 表示内存数据库 |
| `**kwargs` | - | - | 额外参数传递给 `sqlite3.connect()` |

**常用 sqlite3.connect() 参数：**

| 参数 | 说明 |
|------|------|
| `timeout` | 数据库锁超时时间（秒），默认 5.0 |
| `detect_types` | 类型检测标志，可组合使用 `sqlite3.PARSE_DECLTYPES` 和 `sqlite3.PARSE_COLNAMES` |
| `isolation_level` | 隔离级别，None 为自动提交模式，`'DEFERRED'` / `'IMMEDIATE'` / `'EXCLUSIVE'` |
| `check_same_thread` | 是否检查同一线程，默认 True |
| `factory` | 自定义 Connection 工厂 |
| `cached_statements` | 缓存的语句数量，默认 100 |
| `uri` | 是否将 database 视为 URI，默认 False |

---

## API 参考

### 模块导出

| 名称 | 类型 | 说明 |
|------|------|------|
| `connect()` | 函数 | 便捷连接函数，创建并自动连接 |
| `is_available()` | 函数 | 检查 SQLite 驱动是否可用（总是返回 True） |
| `SqliteDialect` | 类 | SQLite 方言实现类 |
| `SqliteConnection` | 类 | SQLite 连接实现类 |

### SqliteDialect 方法

| 方法 | 说明 |
|------|------|
| `get_config() -> DialectConfig` | 获取方言配置 |
| `get_type_mapper() -> SqlTypeMapper` | 获取类型映射器 |
| `create_connection(**kwargs) -> SqliteConnection` | 创建连接实例 |
| `quote_identifier(identifier: str) -> str` | 引用标识符 |
| `quote_string(value: str) -> str` | 引用字符串值 |
| `get_builder_class() -> type` | 获取 SQL 构建器类 |
| `get_paramstyle() -> str` | 获取参数风格（`'qmark'`） |
| `is_available() -> bool` | 检查驱动可用性 |

### SqliteConnection 方法

| 方法/属性 | 说明 |
|----------|------|
| `connect(**kwargs)` | 建立连接 |
| `close()` | 关闭连接 |
| `execute(sql, params=None) -> ResultSet` | 执行 SQL |
| `executemany(sql, seq_of_params) -> int` | 批量执行 SQL |
| `commit()` | 提交事务 |
| `rollback()` | 回滚事务 |
| `cursor() -> sqlite3.Cursor` | 获取底层游标 |
| `is_connected` | 连接状态属性 |
| `database` | 数据库路径属性 |
| `with conn:` | 上下文管理器 |

---

## 注意事项

1. **参数占位符**：SQLite 使用 `?` 作为参数占位符（qmark 风格），不要使用 `%s` 或其他格式
2. **内存数据库**：使用 `:memory:` 创建的内存数据库在连接关闭后数据会丢失，适合测试和临时计算
3. **线程安全**：默认情况下 `check_same_thread=True`，连接对象不能跨线程使用；如需跨线程，设置 `check_same_thread=False`
4. **自动提交**：默认处于事务模式，需要显式调用 `commit()` 才能持久化修改；设置 `isolation_level=None` 可启用自动提交
5. **布尔值**：SQLite 没有原生布尔类型，布尔值存储为 INTEGER（0 或 1）
6. **日期时间**：SQLite 没有原生日期时间类型，默认存储为 TEXT 格式；可通过 `detect_types` 参数启用类型检测
7. **并发访问**：SQLite 支持多进程读，但同一时间只能有一个写操作；写操作期间会锁库
8. **WAL 模式**：如需更好的并发性能，可启用 WAL（Write-Ahead Logging）模式：
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   ```
