# vools.sql.postgres — PostgreSQL 方言

`vools.sql.postgres` 是 vools SQL 框架的 PostgreSQL 方言实现，基于 `psycopg2` 或 `psycopg` 驱动，提供完整的 PostgreSQL 数据库访问能力。

---

## 目录

- [特性](#特性)
- [依赖安装](#依赖安装)
- [快速开始](#快速开始)
- [类型映射](#类型映射)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [注意事项](#注意事项)

---

## 特性

- **双驱动支持**：优先使用 `psycopg2`，不可用时自动回退到 `psycopg`
- **完整事务支持**：支持 ACID 事务，包括保存点（SAVEPOINT）
- **高级类型支持**：支持 JSONB、UUID、数组、BYTEA 等 PostgreSQL 特有类型
- **参数化查询**：使用 `%s` 占位符的参数化查询，防止 SQL 注入
- **上下文管理器**：支持 `with` 语句，自动管理连接和事务
- **连接参数灵活**：支持 host / port / user / password / database 等标准参数
- **驱动自动检测**：自动检测可用的 PostgreSQL 驱动

---

## 依赖安装

`vools.sql.postgres` 需要安装 PostgreSQL 驱动，推荐使用 `psycopg2-binary`：

```bash
# 推荐：安装 psycopg2-binary（预编译二进制版本）
pip install psycopg2-binary

# 或者：安装 psycopg2（需要编译，依赖系统库）
pip install psycopg2

# 或者：安装 psycopg3（新一代驱动）
pip install psycopg[binary]
```

> 框架会自动检测可用的驱动，优先使用 psycopg2。

---

## 快速开始

### 基本使用

```python
from vools.sql.postgres import connect, is_available

# 检查驱动是否可用
if not is_available():
    print("请先安装 psycopg2 或 psycopg")
    exit(1)

# 创建并连接数据库
conn = connect(
    host='localhost',
    port=5432,
    user='postgres',
    password='your_password',
    database='testdb'
)

# 建表
conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        age INTEGER,
        email VARCHAR(255) UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# 插入数据
conn.execute(
    "INSERT INTO users (name, age, email) VALUES (%s, %s, %s)",
    ('Alice', 25, 'alice@example.com')
)

# 批量插入
conn.executemany(
    "INSERT INTO users (name, age, email) VALUES (%s, %s, %s)",
    [
        ('Bob', 30, 'bob@example.com'),
        ('Charlie', 35, 'charlie@example.com'),
    ]
)

# 提交事务
conn.commit()

# 查询数据
result = conn.execute(
    "SELECT * FROM users WHERE age > %s ORDER BY name",
    (20,)
)

# 遍历结果
for row in result:
    print(f"ID: {row.id}, Name: {row.name}, Age: {row.age}")

# 获取第一行
first_row = result.first()
print(f"第一条记录: {first_row}")

# 获取标量值
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
from vools.sql.postgres import PostgresConnection

# with 语句自动管理事务和连接
# 无异常时自动 commit，有异常时自动 rollback
with PostgresConnection(
    host='localhost',
    user='postgres',
    password='your_password',
    database='testdb'
) as conn:
    conn.connect()
    conn.execute("CREATE TABLE IF NOT EXISTS products (id SERIAL PRIMARY KEY, name VARCHAR(100), price NUMERIC)")
    conn.execute("INSERT INTO products (name, price) VALUES (%s, %s)", ('Apple', 5.99))
    # 退出 with 块时自动提交并关闭连接
```

### 使用方言类

```python
from vools.sql.postgres import PostgresDialect

# 创建方言实例
dialect = PostgresDialect()

# 检查驱动可用性
print(f"可用: {dialect.is_available()}")

# 获取配置
config = dialect.get_config()
print(f"驱动: {config.driver}")
print(f"默认端口: {config.default_port}")

# 获取类型映射器
type_mapper = dialect.get_type_mapper()
print(f"UUID 对应 Python 类型: {type_mapper.get_py_type('UUID')}")

# 标识符引用（PostgreSQL 对大小写敏感）
print(dialect.quote_identifier('UserTable'))  # "UserTable"
print(dialect.quote_string("it's"))            # 'it''s'

# 参数风格
print(f"参数风格: {dialect.get_paramstyle()}")  # pyformat

# 创建连接
conn = dialect.create_connection(
    host='localhost',
    user='postgres',
    password='your_password',
    database='testdb'
)
conn.connect()
result = conn.execute('SELECT 1 + 1')
print(result.scalar())  # 2
conn.close()
```

### 使用 JSONB 和 UUID 类型

```python
import uuid
import json
from vools.sql.postgres import connect

conn = connect(
    host='localhost',
    user='postgres',
    password='your_password',
    database='testdb'
)

# 建表（使用 JSONB 和 UUID）
conn.execute('''
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        metadata JSONB,
        tags TEXT[]
    )
''')

# 插入数据
doc_id = uuid.uuid4()
metadata = {"author": "Alice", "version": 1, "tags": ["python", "sql"]}
tags = ['python', 'postgresql', 'tutorial']

# psycopg2 支持自动适配 UUID 和 JSON
conn.execute(
    "INSERT INTO documents (id, title, metadata, tags) VALUES (%s, %s, %s, %s)",
    (doc_id, 'PostgreSQL Guide', json.dumps(metadata), tags)
)
conn.commit()

# 查询
result = conn.execute(
    "SELECT * FROM documents WHERE id = %s",
    (doc_id,)
)
row = result.first()
if row:
    print(f"ID: {row.id}")
    print(f"Title: {row.title}")
    print(f"Metadata: {row.metadata}")
    print(f"Tags: {row.tags}")

conn.close()
```

### 结合 SQL 构建器使用

```python
from vools.sql.postgres import connect
from vools.sql import BaseSqlBuilder

conn = connect(
    host='localhost',
    user='postgres',
    password='your_password',
    database='testdb'
)

conn.execute('CREATE TABLE IF NOT EXISTS users (id SERIAL, name VARCHAR(100), age INTEGER)')
conn.execute("INSERT INTO users (name, age) VALUES (%s, %s)", ('Alice', 25))
conn.execute("INSERT INTO users (name, age) VALUES (%s, %s)", ('Bob', 30))
conn.commit()

# 使用构建器构建 SELECT（PostgreSQL 使用 pyformat 风格）
builder = BaseSqlBuilder()
sql, params = builder.select('id', 'name') \
    .from_('users') \
    .where('age > %s', 20) \
    .order_by('name') \
    .limit(10) \
    .build()

result = conn.execute(sql, params)
print(f"查询到 {len(result)} 条记录")

# 使用构建器构建 INSERT
builder2 = BaseSqlBuilder()
sql2, params2 = builder2.insert_into('users') \
    .values(name='Charlie', age=35) \
    .build()

conn.execute(sql2, params2)
conn.commit()
print(f"插入后总数: {conn.execute('SELECT COUNT(*) FROM users').scalar()}")

conn.close()
```

---

## 类型映射

### Python → PostgreSQL 类型映射

| Python 类型 | PostgreSQL 类型 | 说明 |
|-------------|----------------|------|
| `int` | INTEGER | 整数类型 |
| `float` | DOUBLE | 双精度浮点数 |
| `str` | VARCHAR | 可变长度字符串 |
| `bytes` | BYTEA | 二进制数据 |
| `bool` | BOOLEAN | 布尔值 |
| `datetime.date` | DATE | 日期 |
| `datetime.datetime` | DATETIME | 日期时间 |
| `decimal.Decimal` | DECIMAL | 十进制数 |
| `dict` | JSON | JSON 对象 |
| `list` | JSON | JSON 数组 |
| `uuid.UUID` | UUID | 通用唯一标识符 |
| `None` | NULL | 空值 |

### PostgreSQL → Python 类型映射

| PostgreSQL 类型 | Python 类型 | 说明 |
|-----------------|-------------|------|
| INTEGER / INT / BIGINT / SMALLINT / TINYINT | `int` | 整数 |
| SERIAL / BIGSERIAL | `int` | 自增整数 |
| FLOAT / DOUBLE / REAL | `float` | 浮点数 |
| BOOLEAN / BOOL | `bool` | 布尔值 |
| VARCHAR / CHAR / TEXT / STRING / CLOB | `str` | 文本 |
| BYTEA / BINARY / VARBINARY | `bytes` | 二进制数据 |
| DATE | `datetime.date` | 日期 |
| DATETIME / TIMESTAMP / TIMESTAMPTZ | `datetime.datetime` | 日期时间 |
| DECIMAL / NUMERIC | `decimal.Decimal` | 十进制数 |
| JSON / JSONB | `dict` | JSON 对象 |
| UUID | `uuid.UUID` | 通用唯一标识符 |
| ARRAY | `list` | 数组 |

> 实际类型转换由 psycopg2 / psycopg 驱动处理。以上映射用于类型推断和文档参考。

---

## 配置说明

### DialectConfig 字段

`PostgresDialect` 使用的 `DialectConfig` 配置：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | `'postgres'` | 方言名称 |
| `driver` | `str` | `'psycopg2'` | 驱动模块名（优先 psycopg2） |
| `default_port` | `int` | `5432` | 默认端口 |
| `default_host` | `str` | `'localhost'` | 默认主机 |
| `default_user` | `str` | `'postgres'` | 默认用户名 |
| `default_database` | `str` | `'postgres'` | 默认数据库 |
| `paramstyle` | `str` | `'pyformat'` | 参数占位符风格（%s） |
| `identifier_quote` | `str` | `'"'` | 标识符引用符（双引号） |
| `string_quote` | `str` | `"'"` | 字符串引用符（单引号） |
| `connection_params` | `dict` | `{}` | 额外连接参数 |
| `extra_config` | `dict` | `{}` | 额外配置 |

### PostgresConnection 连接参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | `str` | `'localhost'` | 数据库主机地址 |
| `port` | `int` | `5432` | 数据库端口 |
| `user` | `str` | `'postgres'` | 用户名 |
| `password` | `str` | `''` | 密码 |
| `database` | `str` | `'postgres'` | 数据库名 |
| `**kwargs` | - | - | 额外参数传递给驱动的 connect() |

**常用 psycopg2 额外参数：**

| 参数 | 说明 |
|------|------|
| `connect_timeout` | 连接超时时间（秒） |
| `sslmode` | SSL 模式：`disable` / `allow` / `prefer` / `require` / `verify-ca` / `verify-full` |
| `sslcert` | 客户端证书路径 |
| `sslkey` | 客户端私钥路径 |
| `sslrootcert` | 根证书路径 |
| `options` | 命令行选项 |
| `application_name` | 应用名称 |
| `keepalives` | 是否启用 TCP keepalive（1=启用，0=禁用） |
| `keepalives_idle` | 空闲多久后发送 keepalive（秒） |
| `keepalives_interval` | keepalive 重传间隔（秒） |
| `keepalives_count` | keepalive 最大重试次数 |

---

## API 参考

### 模块导出

| 名称 | 类型 | 说明 |
|------|------|------|
| `connect()` | 函数 | 便捷连接函数，创建并自动连接 |
| `is_available()` | 函数 | 检查 PostgreSQL 驱动是否可用 |
| `PostgresDialect` | 类 | PostgreSQL 方言实现类 |
| `PostgresConnection` | 类 | PostgreSQL 连接实现类 |
| `dialect` | 代理 | 全局方言实例（延迟初始化） |

### PostgresDialect 方法

| 方法 | 说明 |
|------|------|
| `get_config() -> DialectConfig` | 获取方言配置 |
| `get_type_mapper() -> SqlTypeMapper` | 获取类型映射器 |
| `create_connection(**kwargs) -> PostgresConnection` | 创建连接实例 |
| `quote_identifier(identifier: str) -> str` | 引用标识符 |
| `quote_string(value: str) -> str` | 引用字符串值 |
| `get_builder_class() -> type` | 获取 SQL 构建器类 |
| `get_paramstyle() -> str` | 获取参数风格（`'pyformat'`） |
| `is_available() -> bool` | 检查驱动可用性 |

### PostgresConnection 方法

| 方法/属性 | 说明 |
|----------|------|
| `connect(**kwargs)` | 建立连接 |
| `close()` | 关闭连接 |
| `execute(sql, params=None) -> ResultSet` | 执行 SQL |
| `executemany(sql, seq_of_params) -> int` | 批量执行 SQL |
| `commit()` | 提交事务 |
| `rollback()` | 回滚事务 |
| `cursor()` | 获取底层游标 |
| `is_connected` | 连接状态属性 |
| `driver_name` | 当前使用的驱动名称（`'psycopg2'` 或 `'psycopg'`） |
| `with conn:` | 上下文管理器 |

---

## 注意事项

1. **驱动依赖**：需要单独安装 `psycopg2-binary` 或 `psycopg`，框架会自动检测可用驱动
2. **参数占位符**：PostgreSQL 使用 `%s` 作为参数占位符（pyformat 风格），不要使用 `?`
3. **标识符大小写**：PostgreSQL 对未加引号的标识符自动转为小写；如需保留大小写，使用双引号引用
4. **事务默认行为**：psycopg2 默认开启事务，需要显式 `commit()` 才能持久化修改；自动提交需设置 `autocommit=True`
5. **JSONB 操作**：使用 JSONB 类型时，建议使用 `json.dumps()` 将 dict 转为字符串后传入
6. **UUID 类型**：psycopg2 支持 UUID 类型的自动适配，可直接传入 `uuid.UUID` 对象
7. **数组类型**：PostgreSQL 数组类型对应 Python list，psycopg2 会自动进行双向转换
8. **连接池**：对于生产环境，建议使用连接池（如 `psycopg2.pool`）以提高性能
9. **SSL 连接**：连接远程数据库时，建议启用 SSL 加密以保障数据安全
10. **错误处理**：建议使用 try-except 捕获数据库异常，并在 finally 中确保连接关闭
