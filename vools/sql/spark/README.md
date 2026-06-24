# vools.sql.spark — Spark SQL 方言

`vools.sql.spark` 是 vools SQL 框架的 Spark SQL 方言实现，基于 PySpark 的 `SparkSession`，提供分布式大数据处理与 SQL 查询能力。

---

## 目录

- [特性](#特性)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [类型映射](#类型映射)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [注意事项](#注意事项)

---

## 特性

- **PySpark 支持**：基于 PySpark SparkSession，完整的 Spark SQL 能力
- **多数据源**：支持 CSV、Parquet、JSON 等多种数据源读取
- **DataFrame API**：可与 Spark DataFrame 无缝互操作
- **临时视图**：支持创建和替换临时视图，方便 SQL 查询
- **SQL 查询**：完整的 Spark SQL 语法支持
- **分布式计算**：Spark 原生的分布式数据处理能力
- **反引号标识符**：使用反引号引用标识符，与 Hive 兼容
- **Catalog & Database**：支持 Spark Catalog 和多数据库切换

---

## 环境要求

- **Python**：3.7+
- **PySpark**：3.0+
- **Java**：JDK 8 / JDK 11（Spark 运行依赖）
- **Scala**：2.12+（由 Spark 自带）

安装 PySpark：

```bash
pip install pyspark
```

---

## 快速开始

### 基本使用

```python
from vools.sql.spark import connect

# 创建 SparkSession 并连接
conn = connect(app_name='my_app', master='local[*]')

# 执行 SQL 查询
result = conn.execute('SELECT 1 AS id, "hello" AS name')

# 遍历结果
for row in result:
    print(f"ID: {row.id}, Name: {row.name}")

# 获取第一行
first_row = result.first()
print(f"第一条记录: {first_row}")

# 获取标量值
value = conn.execute('SELECT 1 + 1').scalar()
print(f"计算结果: {value}")

# 转为字典列表
data_list = result.to_list()
print(f"字典列表: {data_list}")

# 关闭连接
conn.close()
```

### 读取文件数据

```python
from vools.sql.spark import connect

conn = connect(app_name='file_demo')

# 读取 CSV 文件
csv_result = conn.read_csv('data.csv', header=True, inferSchema=True)
print(f"CSV 记录数: {len(csv_result)}")

# 读取 Parquet 文件
parquet_result = conn.read_parquet('data.parquet')
print(f"Parquet 记录数: {len(parquet_result)}")

# 读取 JSON 文件
json_result = conn.read_json('data.json')
print(f"JSON 记录数: {len(json_result)}")

conn.close()
```

### 使用临时视图

```python
from vools.sql.spark import connect

conn = connect(app_name='view_demo')

# 读取 CSV 并创建临时视图
csv_df = conn.spark.read.csv('users.csv', header=True, inferSchema=True)
conn.create_or_replace_temp_view('users', csv_df)

# 使用 SQL 查询临时视图
result = conn.execute('''
    SELECT name, age
    FROM users
    WHERE age > 20
    ORDER BY name
    LIMIT 10
''')

for row in result:
    print(f"{row.name}: {row.age}")

conn.close()
```

### 使用上下文管理器

```python
from vools.sql.spark import SparkConnection

# with 语句自动管理 SparkSession 生命周期
with SparkConnection(app_name='context_demo') as conn:
    result = conn.sql('SELECT 1 + 1 AS sum')
    print(f"结果: {result.scalar()}")
    # 退出 with 块时自动停止 SparkSession
```

### 使用方言类

```python
from vools.sql.spark import SparkSqlDialect

# 创建方言实例
dialect = SparkSqlDialect()

# 检查驱动可用性
print(f"可用: {dialect.is_available()}")

# 获取类型映射器
type_mapper = dialect.get_type_mapper()
print(f"int 对应 SQL 类型: {type_mapper.get_sql_type(int)}")

# 标识符引用
print(dialect.quote_identifier('user name'))  # `user name`
print(dialect.quote_string("it's"))           # 'it''s'

# 创建连接
conn = dialect.create_connection(app_name='dialect_demo')
conn.connect()
result = conn.execute('SELECT 1 + 1')
print(result.scalar())  # 2
conn.close()
```

### 结合 SQL 构建器使用

```python
from vools.sql.spark import connect
from vools.sql import BaseSqlBuilder

conn = connect(app_name='builder_demo')

# 创建测试数据
conn.spark.createDataFrame([
    (1, 'Alice', 25),
    (2, 'Bob', 30),
    (3, 'Charlie', 35),
], ['id', 'name', 'age']).createOrReplaceTempView('users')

# 使用构建器构建 SELECT
builder = BaseSqlBuilder()
builder._paramstyle = 'pyformat'  # Spark 使用 pyformat 风格
sql, params = builder.select('id', 'name') \
    .from_('users') \
    .where('age > %s', 20) \
    .order_by('name') \
    .limit(10) \
    .build()

result = conn.execute(sql, params)
print(f"查询到 {len(result)} 条记录")

conn.close()
```

---

## 类型映射

### Python → Spark SQL 类型映射

| Python 类型 | Spark SQL 类型 | 说明 |
|-------------|---------------|------|
| `str` | STRING | 字符串类型 |
| `int` | INTEGER | 整数类型 |
| `float` | DOUBLE | 双精度浮点数 |
| `bool` | BOOLEAN | 布尔类型 |
| `bytes` | BINARY | 二进制类型 |
| `datetime.date` | DATE | 日期类型 |
| `datetime.datetime` | TIMESTAMP | 时间戳类型 |
| `decimal.Decimal` | DECIMAL | 十进制数 |
| `list` | ARRAY | 数组类型 |
| `dict` | MAP | 映射类型 |
| `None` | NULL | 空值 |

### Spark SQL → Python 类型映射

| Spark SQL 类型 | Python 类型 | 说明 |
|---------------|-------------|------|
| STRING / VARCHAR / CHAR | `str` | 字符串 |
| INTEGER / INT | `int` | 整数 |
| BIGINT / LONG | `int` | 长整数 |
| DOUBLE | `float` | 双精度浮点数 |
| FLOAT / REAL | `float` | 单精度浮点数 |
| BOOLEAN / BOOL | `bool` | 布尔值 |
| BINARY | `bytes` | 二进制 |
| DATE | `datetime.date` | 日期 |
| TIMESTAMP | `datetime.datetime` | 时间戳 |
| DECIMAL / NUMERIC | `decimal.Decimal` | 十进制数 |
| ARRAY | `list` | 数组 |
| MAP | `dict` | 映射 |
| STRUCT | `dict` | 结构体 |

> 实际类型转换由 PySpark 驱动处理。以上映射用于类型推断和文档参考。

---

## 配置说明

### DialectConfig 字段

`SparkSqlDialect` 使用的 `DialectConfig` 配置：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | `'spark'` | 方言名称 |
| `driver` | `str` | `'pyspark'` | 驱动模块名 |
| `default_port` | `int` | `0` | 默认端口（非传统数据库连接） |
| `default_host` | `str` | `''` | 默认主机（空） |
| `default_user` | `str` | `''` | 默认用户名（空） |
| `default_database` | `str` | `'default'` | 默认数据库 |
| `paramstyle` | `str` | `'pyformat'` | 参数占位符风格（%s） |
| `identifier_quote` | `str` | `` '`' `` | 标识符引用符（反引号） |
| `string_quote` | `str` | `"'"` | 字符串引用符（单引号） |
| `connection_params` | `dict` | `{}` | 额外连接参数 |
| `extra_config` | `dict` | `{}` | 额外配置 |

### SparkConnection 连接参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `app_name` | `str` | `'vools_spark'` | Spark 应用名称 |
| `master` | `str` | `'local[*]'` | Spark master URL |
| `catalog` | `str` | `'spark_catalog'` | 默认 catalog 名称 |
| `database` | `str` | `'default'` | 默认数据库名称 |
| `**kwargs` | - | - | 额外 Spark 配置项 |

**常用 master URL：**

| 值 | 说明 |
|----|------|
| `local` | 本地模式，1 个线程 |
| `local[*]` | 本地模式，使用所有 CPU 核心 |
| `local[N]` | 本地模式，使用 N 个线程 |
| `spark://host:7077` | Standalone 集群模式 |
| `yarn` | YARN 集群模式 |
| `k8s://...` | Kubernetes 集群模式 |

**常用 Spark 配置项：**

| 配置键 | 说明 |
|--------|------|
| `spark.executor.memory` | Executor 内存大小，如 `2g` |
| `spark.driver.memory` | Driver 内存大小，如 `1g` |
| `spark.executor.cores` | 每个 Executor 的核心数 |
| `spark.sql.shuffle.partitions` | Shuffle 分区数，默认 200 |
| `spark.sql.warehouse.dir` | Warehouse 目录路径 |

---

## API 参考

### 模块导出

| 名称 | 类型 | 说明 |
|------|------|------|
| `connect()` | 函数 | 便捷连接函数，创建并自动连接 |
| `is_available()` | 函数 | 检查 PySpark 是否可用 |
| `SparkSqlDialect` | 类 | Spark SQL 方言实现类 |
| `SparkConnection` | 类 | Spark 连接实现类 |

### SparkSqlDialect 方法

| 方法 | 说明 |
|------|------|
| `get_config() -> DialectConfig` | 获取方言配置 |
| `get_type_mapper() -> SqlTypeMapper` | 获取类型映射器 |
| `create_connection(**kwargs) -> SparkConnection` | 创建连接实例 |
| `quote_identifier(identifier: str) -> str` | 引用标识符（反引号） |
| `quote_string(value: str) -> str` | 引用字符串值（单引号） |
| `get_builder_class() -> type` | 获取 SQL 构建器类 |
| `get_paramstyle() -> str` | 获取参数风格（`'pyformat'`） |
| `is_available() -> bool` | 检查 PySpark 可用性 |

### SparkConnection 方法

| 方法/属性 | 说明 |
|----------|------|
| `connect(**kwargs)` | 创建或获取 SparkSession |
| `close()` | 停止 SparkSession |
| `execute(sql, params=None) -> ResultSet` | 执行 SQL |
| `executemany(sql, seq_of_params) -> int` | 批量执行 SQL |
| `commit()` | 提交事务（空操作） |
| `rollback()` | 回滚事务（空操作） |
| `cursor() -> SparkSession` | 获取底层 SparkSession |
| `sql(sql_str) -> ResultSet` | 执行 SQL（别名） |
| `read_csv(path, **kwargs) -> ResultSet` | 读取 CSV 文件 |
| `read_parquet(path, **kwargs) -> ResultSet` | 读取 Parquet 文件 |
| `read_json(path, **kwargs) -> ResultSet` | 读取 JSON 文件 |
| `create_temp_view(view_name, df_or_rs)` | 创建临时视图 |
| `create_or_replace_temp_view(view_name, df_or_rs)` | 创建或替换临时视图 |
| `spark` | property，获取底层 SparkSession |
| `app_name` | property，应用名称 |
| `master` | property，master URL |
| `catalog` | property，当前 catalog |
| `database` | property，当前数据库 |
| `is_connected` | property，连接状态 |
| `with conn:` | 上下文管理器 |

---

## 注意事项

1. **参数占位符**：Spark SQL 本身不支持参数化查询，使用 `%s` 作为占位符（pyformat 风格），通过字符串格式化执行，请注意 SQL 注入风险
2. **Java 环境**：Spark 依赖 Java 运行环境，请确保已安装 JDK 并正确配置 `JAVA_HOME` 环境变量
3. **内存配置**：处理大数据时请合理配置 `spark.driver.memory` 和 `spark.executor.memory`
4. **数据收集**：`execute()` 方法会调用 `collect()` 将所有数据拉取到 Driver 端，大数据集请谨慎使用
5. **事务支持**：Spark SQL 不支持传统数据库事务，`commit()` 和 `rollback()` 为空操作
6. **临时视图**：临时视图仅在当前 SparkSession 生命周期内有效，Session 关闭后自动消失
7. **本地模式**：`local[*]` 模式适合开发和测试，生产环境请使用集群模式（YARN / Standalone / K8s）
8. **Hive 集成**：如需使用 Hive 元存储，请启用 Hive 支持并配置 `spark.sql.warehouse.dir`
9. **分区数**：Spark SQL 默认 shuffle 分区数为 200，可通过 `spark.sql.shuffle.partitions` 调整
10. **依赖管理**：生产环境建议使用 `spark-submit` 提交应用，管理依赖更方便
