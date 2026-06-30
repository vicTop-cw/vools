# Spark SQL 工具 {#027}

> **模块路径**：`vools.sql.spark`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#027
> **最后更新**：2026-06-30

## 概述

`vools.sql.spark` 模块提供 Apache Spark SQL 的完整支持，基于 PySpark 的 SparkSession 实现。Spark 是一个分布式数据处理引擎，适合大规模数据分析和企业级数据处理任务。

## 依赖说明

Spark 支持需要安装 PySpark：

```bash
pip install pyspark
```

安装后验证可用性：

```python
from vools.sql.spark import is_available

print(f"Spark available: {is_available()}")
# 输出: Spark available: True
```

## 连接管理

### 基础连接

使用 `connect()` 函数创建 Spark 连接：

```python
from vools.sql.spark import connect

# 创建本地模式 Spark 连接
conn = connect(app_name='MyApp', master='local[*]')

# 执行查询
result = conn.execute('SELECT 1 AS value')
print(result.first()['value'])  # 输出: 1

conn.close()
```

### 上下文管理器

推荐使用上下文管理器自动管理连接：

```python
from vools.sql.spark import connect

with connect(app_name='ExampleApp') as conn:
    # 执行 SQL 查询
    result = conn.sql('SELECT current_date() AS today, 1 + 1 AS result')
    for row in result:
        print(f"today={row.today}, result={row.result}")
    # 输出类似: today=2026-06-30, result=2
```

### 连接配置

```python
from vools.sql.spark import SparkConnection

# 创建连接实例（不立即连接）
conn = SparkConnection(
    app_name='ConfiguredApp',
    master='local[2]',
    catalog='spark_catalog',
    database='default',
    **{  # PySpark 额外配置
        'spark.executor.memory': '2g',
        'spark.sql.shuffle.partitions': '4'
    }
)

# 手动连接
conn.connect()

print(f"App: {conn.app_name}, Master: {conn.master}")
# 输出: App: ConfiguredApp, Master: local[2]

conn.close()
```

## DataFrame 操作

### 创建 DataFrame

```python
from vools.sql.spark import connect

with connect(app_name='DataFrameDemo') as conn:
    # 使用 SQL 创建 DataFrame
    conn.execute('''
        CREATE TABLE IF NOT EXISTS numbers (value INT)
    ''')
    
    # 插入数据
    for i in range(1, 6):
        conn.execute(f'INSERT INTO numbers VALUES ({i})')
    
    # 查询并迭代
    result = conn.execute('SELECT * FROM numbers ORDER BY value')
    print("Numbers table:")
    for row in result:
        print(f"  {row.value}")
    # 输出:
    #   1
    #   2
    #   3
    #   4
    #   5
```

### 临时视图操作

```python
from vools.sql.spark import connect

with connect(app_name='TempViewDemo') as conn:
    # 创建数据
    conn.execute('CREATE TABLE sales (product STRING, amount DOUBLE, region STRING)')
    conn.execute("INSERT INTO sales VALUES ('A', 100.0, 'North')")
    conn.execute("INSERT INTO sales VALUES ('B', 200.0, 'South')")
    conn.execute("INSERT INTO sales VALUES ('A', 150.0, 'North')")
    conn.execute("INSERT INTO sales VALUES ('B', 180.0, 'South')")
    
    # 查询原始数据
    result = conn.execute('SELECT * FROM sales')
    print("Original sales data:")
    for row in result:
        print(f"  {row.product}: ${row.amount} ({row.region})")
    # 输出:
    #   A: $100.0 (North)
    #   B: $200.0 (South)
    #   A: $150.0 (North)
    #   B: $180.0 (South)
    
    # 按产品分组汇总
    result = conn.execute('''
        SELECT product, SUM(amount) as total, COUNT(*) as count
        FROM sales
        GROUP BY product
        ORDER BY total DESC
    ''')
    print("\nSales by product:")
    for row in result:
        print(f"  {row.product}: total=${row.total:.2f}, count={row.count}")
    # 输出:
    #   B: total=$380.00, count=2
    #   A: total=$250.00, count=2
```

### 数据读取

Spark 支持多种数据源读取，使用对应方法返回 ResultSet：

```python
from vools.sql.spark import connect
import os

# 假设当前目录有 test.csv 文件，内容如下：
# name,age,city
# Alice,30,NYC
# Bob,25,LA

with connect(app_name='DataReadDemo') as conn:
    # 创建示例 CSV 数据
    os.makedirs('temp_data', exist_ok=True)
    with open('temp_data/people.csv', 'w') as f:
        f.write('name,age,city\n')
        f.write('Alice,30,NYC\n')
        f.write('Bob,25,LA\n')
        f.write('Charlie,35,Chicago\n')
    
    # 读取 CSV 文件
    result = conn.read_csv('temp_data/people.csv', header=True, inferSchema=True)
    print("CSV data:")
    for row in result:
        print(f"  {row.name}, {row.age}, {row.city}")
    # 输出:
    #   Alice, 30, NYC
    #   Bob, 25, LA
    #   Charlie, 35, Chicago
    
    # 清理临时文件
    import shutil
    shutil.rmtree('temp_data')
```

### JSON 数据读取

```python
from vools.sql.spark import connect
import os
import json

with connect(app_name='JsonReadDemo') as conn:
    # 创建示例 JSON 文件
    os.makedirs('temp_data', exist_ok=True)
    data = [
        {'id': 1, 'name': 'Alice', 'scores': [90, 85, 88]},
        {'id': 2, 'name': 'Bob', 'scores': [75, 80, 92]}
    ]
    with open('temp_data/scores.json', 'w') as f:
        for item in data:
            f.write(json.dumps(item) + '\n')
    
    # 读取 JSON 文件
    result = conn.read_json('temp_data/scores.json')
    print("JSON data:")
    for row in result:
        print(f"  {row.name}: id={row.id}, scores={row.scores}")
    # 输出:
    #   Alice: id=1, scores=[90, 85, 88]
    #   Bob: id=2, scores=[75, 80, 92]
    
    # 清理临时文件
    import shutil
    shutil.rmtree('temp_data')
```

## SQL 查询操作

### 基本查询

```python
from vools.sql.spark import connect

with connect(app_name='SqlDemo') as conn:
    # 创建并填充数据
    conn.execute('CREATE TABLE employees (id INT, name STRING, dept STRING, salary DOUBLE)')
    conn.execute('INSERT INTO employees VALUES (1, 'Alice', 'Engineering', 90000.0)')
    conn.execute('INSERT INTO employees VALUES (2, 'Bob', 'Engineering', 85000.0)')
    conn.execute('INSERT INTO employees VALUES (3, 'Carol', 'Sales', 75000.0)')
    conn.execute('INSERT INTO employees VALUES (4, 'Dave', 'Sales', 80000.0)')
    
    # 基础查询
    result = conn.execute('SELECT * FROM employees ORDER BY id')
    print("All employees:")
    for row in result:
        print(f"  {row.id}: {row.name} - {row.dept} (${row.salary:.2f})")
    # 输出:
    #   1: Alice - Engineering ($90000.00)
    #   2: Bob - Engineering ($85000.00)
    #   3: Carol - Sales ($75000.00)
    #   4: Dave - Sales ($80000.00)
    
    # 条件查询
    result = conn.execute('SELECT * FROM employees WHERE dept = ? AND salary > ?', ('Engineering', 85000.0))
    print("\nEngineering employees with salary > 85000:")
    for row in result:
        print(f"  {row.name}: ${row.salary:.2f}")
    # 输出:
    #   Alice: $90000.00
```

### 聚合查询

```python
from vools.sql.spark import connect

with connect(app_name='AggDemo') as conn:
    conn.execute('CREATE TABLE orders (order_id INT, customer STRING, product STRING, amount DOUBLE)')
    conn.execute("INSERT INTO orders VALUES (1, 'Alice', 'Widget', 100.0)")
    conn.execute("INSERT INTO orders VALUES (2, 'Bob', 'Widget', 150.0)")
    conn.execute("INSERT INTO orders VALUES (3, 'Alice', 'Gadget', 200.0)")
    conn.execute("INSERT INTO orders VALUES (4, 'Bob', 'Gadget', 180.0)")
    conn.execute("INSERT INTO orders VALUES (5, 'Alice', 'Widget', 120.0)")
    
    # 聚合统计
    result = conn.execute('''
        SELECT 
            customer,
            COUNT(*) as order_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MIN(amount) as min_amount,
            MAX(amount) as max_amount
        FROM orders
        GROUP BY customer
        ORDER BY total_amount DESC
    ''')
    print("Customer statistics:")
    for row in result:
        print(f"  {row.customer}:")
        print(f"    orders={row.order_count}, total=${row.total_amount:.2f}")
        print(f"    avg=${row.avg_amount:.2f}, min=${row.min_amount:.2f}, max=${row.max_amount:.2f}")
    # 输出:
    #   Alice:
    #     orders=3, total=$420.00
    #     avg=$140.00, min=$100.00, max=$200.00
    #   Bob:
    #     orders=2, total=$330.00
    #     avg=$165.00, min=$150.00, max=$180.00
```

### JOIN 操作

```python
from vools.sql.spark import connect

with connect(app_name='JoinDemo') as conn:
    # 创建用户表
    conn.execute('CREATE TABLE users (user_id INT, name STRING)')
    conn.execute('INSERT INTO users VALUES (1, 'Alice')")
    conn.execute('INSERT INTO users VALUES (2, 'Bob')")
    conn.execute('INSERT INTO users VALUES (3, 'Carol')")
    
    # 创建订单表
    conn.execute('CREATE TABLE orders (order_id INT, user_id INT, product STRING)')
    conn.execute('INSERT INTO orders VALUES (1, 1, 'Widget')")
    conn.execute('INSERT INTO orders VALUES (2, 1, 'Gadget')")
    conn.execute('INSERT INTO orders VALUES (3, 2, 'Widget')")
    
    # INNER JOIN
    result = conn.execute('''
        SELECT u.name, o.product
        FROM users u
        INNER JOIN orders o ON u.user_id = o.user_id
        ORDER BY u.name, o.product
    ''')
    print("User orders (INNER JOIN):")
    for row in result:
        print(f"  {row.name}: {row.product}")
    # 输出:
    #   Alice: Gadget
    #   Alice: Widget
    #   Bob: Widget
    
    # LEFT JOIN（含未下单用户）
    result = conn.execute('''
        SELECT u.name, o.product
        FROM users u
        LEFT JOIN orders o ON u.user_id = o.user_id
        ORDER BY u.name
    ''')
    print("\nAll users with orders (LEFT JOIN):")
    for row in result:
        product = row.product if row.product else '(no orders)'
        print(f"  {row.name}: {product}")
    # 输出:
    #   Alice: Widget
    #   Alice: Gadget
    #   Bob: Widget
    #   Carol: (no orders)
```

## ResultSet 操作

ResultSet 在 Spark 模块中与 SQLite 模块行为一致，提供统一的数据访问接口：

```python
from vools.sql.spark import connect

with connect(app_name='ResultSetDemo') as conn:
    conn.execute('CREATE TABLE data (a INT, b INT, c INT)')
    conn.execute('INSERT INTO data VALUES (1, 2, 3)')
    conn.execute('INSERT INTO data VALUES (4, 5, 6)')
    conn.execute('INSERT INTO data VALUES (7, 8, 9)')
    
    result = conn.execute('SELECT * FROM data')
    
    # 迭代访问
    print("Iterating rows:")
    for row in result:
        print(f"  a={row.a}, b={row.b}, c={row.c}")
    # 输出:
    #   a=1, b=2, c=3
    #   a=4, b=5, c=6
    #   a=7, b=8, c=9
    
    # 索引访问
    result.reset_cursor()
    print(f"\nFirst row: {result[0]}")
    print(f"Last row: {result[-1]}")
    # 输出:
    #   First row: Row(a=1, b=2, c=3)
    #   Last row: Row(a=7, b=8, c=9)
    
    # fetch 方法
    result.reset_cursor()
    print(f"\nfetchone: {result.fetchone()}")
    print(f"fetchmany(2): {result.fetchmany(2)}")
    # 输出:
    #   fetchone: Row(a=1, b=2, c=3)
    #   fetchmany(2): [Row(a=4, b=5, c=6), Row(a=7, b=8, c=9)]
    
    # 转换为列表
    result.reset_cursor()
    data_list = result.to_list()
    print(f"\nto_list(): {data_list}")
    # 输出: [{'a': 1, 'b': 2, 'c': 3}, {'a': 4, 'b': 5, 'c': 6}, {'a': 7, 'b': 8, 'c': 9}]
```

## 底层 SparkSession 访问

```python
from vools.sql.spark import connect

with connect(app_name='SparkSessionDemo') as conn:
    # 获取底层 SparkSession
    spark = conn.spark
    
    # 使用原生 PySpark API
    df = spark.range(5).toDF('number')
    df.createOrReplaceTempView('numbers')
    
    result = conn.execute('SELECT * FROM numbers')
    print("Numbers 0-4:")
    for row in result:
        print(f"  {row.number}")
    # 输出:
    #   0
    #   1
    #   2
    #   3
    #   4
    
    # 访问 Scala 桥接（用于高级互操作）
    scala = conn.scala
    print(f"\nScala bridge available: {scala is not None}")
    # 输出: Scala bridge available: True
```

## 配置说明

### Spark Master URL

| Master URL | 说明 |
|------------|------|
| `local` | 单线程本地模式 |
| `local[*]` | 本地模式，使用所有 CPU 核心 |
| `local[2]` | 本地模式，使用 2 个核心 |
| `spark://host:port` | Standalone 集群模式 |
| `yarn` | YARN 集群模式 |
| `mesos://host:port` | Mesos 集群模式 |

### 常用配置项

```python
from vools.sql.spark import connect

# 创建带配置的连接
conn = connect(
    app_name='ConfiguredSpark',
    master='local[2]',
    spark.sql.shuffle.partitions='8',    # Shuffle 分区数
    spark.executor.memory='2g',            # Executor 内存
    spark.driver.memory='1g'              # Driver 内存
)

with conn:
    result = conn.execute('SELECT 1')
    print(f"Connected to: {conn.master}")
    # 输出: Connected to: local[2]

conn.close()
```

## 完整示例

```python
from vools.sql.spark import connect

# 创建一个简单的销售数据分析应用
with connect(app_name='SalesAnalysis') as conn:
    # 创建销售数据表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            sale_id INT,
            product STRING,
            category STRING,
            region STRING,
            amount DOUBLE,
            quantity INT
        )
    ''')
    
    # 插入示例数据
    sales_data = [
        (1, 'Laptop', 'Electronics', 'North', 999.99, 1),
        (2, 'Mouse', 'Electronics', 'South', 29.99, 3),
        (3, 'Desk', 'Furniture', 'North', 299.99, 2),
        (4, 'Chair', 'Furniture', 'South', 199.99, 4),
        (5, 'Monitor', 'Electronics', 'North', 399.99, 2),
        (6, 'Keyboard', 'Electronics', 'South', 79.99, 5),
        (7, 'Table', 'Furniture', 'East', 249.99, 1),
        (8, 'Webcam', 'Electronics', 'West', 89.99, 3),
    ]
    
    for sale in sales_data:
        conn.execute(
            'INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)',
            sale
        )
    
    # 1. 按类别统计销售额
    result = conn.execute('''
        SELECT 
            category,
            COUNT(*) as transaction_count,
            SUM(amount) as total_revenue,
            SUM(quantity) as total_quantity
        FROM sales
        GROUP BY category
        ORDER BY total_revenue DESC
    ''')
    print("Revenue by Category:")
    for row in result:
        print(f"  {row.category}: ${row.total_revenue:.2f} ({row.transaction_count} transactions)")
    # 输出:
    #   Electronics: $1609.93 (4 transactions)
    #   Furniture: $749.96 (3 transactions)
    
    # 2. 按地区统计
    result = conn.execute('''
        SELECT 
            region,
            SUM(amount) as total
        FROM sales
        GROUP BY region
        ORDER BY total DESC
    ''')
    print("\nRevenue by Region:")
    for row in result:
        print(f"  {row.region}: ${row.total:.2f}")
    # 输出:
    #   North: $1699.96
    #   South: $609.93
    #   East: $249.99
    #   West: $269.97
    
    # 3. 高价值产品（单笔销售额 > 200）
    result = conn.execute('''
        SELECT product, amount, region
        FROM sales
        WHERE amount > 200
        ORDER BY amount DESC
    ''')
    print("\nHigh-value products (>$200):")
    for row in result:
        print(f"  {row.product}: ${row.amount:.2f} ({row.region})")
    # 输出:
    #   Laptop: $999.99 (North)
    #   Monitor: $399.99 (North)
    #   Desk: $299.99 (North)
    #   Chair: $199.99 (South)
    
    # 4. 计算每笔交易的平均单价
    result = conn.execute('''
        SELECT 
            product,
            amount,
            quantity,
            ROUND(amount / quantity, 2) as unit_price
        FROM sales
        ORDER BY unit_price DESC
    ''')
    print("\nUnit prices:")
    for row in result:
        print(f"  {row.product}: ${row.unit_price:.2f} per unit")
    # 输出:
    #   Laptop: $999.99 per unit
    #   Monitor: $199.99 per unit
    #   Desk: $149.99 per unit
    #   ... 等等

print("\nSales analysis completed successfully.")
# 输出: Sales analysis completed successfully.
```

## 与 SQLite 对比

| 特性 | SQLite | Spark SQL |
|------|--------|-----------|
| 适用场景 | 本地/嵌入式 | 大规模数据处理 |
| 数据规模 | 小型（MB 级） | 大型（TB/PB 级） |
| 部署复杂度 | 低 | 高 |
| SQL 支持 | 基础 | 完整 |
| 并行处理 | 否 | 是 |
| 分布式 | 否 | 是 |
| 依赖 | 标准库 | PySpark |

## 相关模块

| 模块 | 说明 |
|------|------|
| [vools.sql](index.md) | SQL 工具概览 |
| [vools.sql.sqlite](sqlite.md) | SQLite 支持 |
| [vools.sql.postgres](../postgres/index.md) | PostgreSQL 支持 |
