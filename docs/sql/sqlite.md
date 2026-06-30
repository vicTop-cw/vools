# SQLite 数据库工具 {#026}

> **模块路径**：`vools.sql.sqlite`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#026
> **最后更新**：2026-06-30

## 概述

`vools.sql.sqlite` 模块提供 SQLite 数据库的完整支持，基于 Python 标准库 `sqlite3` 实现。SQLite 是一个轻量级的嵌入式数据库，无需独立的数据库服务器进程，适合本地数据存储和小型应用。

## 依赖说明

SQLite 支持通过 Python 标准库 `sqlite3` 实现，无需额外安装依赖：

```python
import sqlite3  # Python 3.6+ 内置
```

## 连接管理

### 基础连接

使用 `connect()` 函数创建内存数据库连接：

```python
from vools.sql.sqlite import connect

# 创建内存数据库连接
conn = connect(':memory:')

# 执行查询
result = conn.execute('SELECT 1 AS value')
print(result.first()['value'])  # 输出: 1

conn.close()
```

### 上下文管理器

推荐使用上下文管理器自动管理连接：

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    # 创建表
    conn.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT
        )
    ''')
    
    # 插入数据
    conn.execute(
        'INSERT INTO users (name, email) VALUES (?, ?)',
        ('Alice', 'alice@example.com')
    )
    conn.commit()
    
    # 查询数据
    result = conn.execute('SELECT * FROM users')
    for row in result:
        print(f"id={row.id}, name={row.name}, email={row.email}")
    # 输出: id=1, name=Alice, email=alice@example.com
```

### 文件数据库连接

```python
from vools.sql.sqlite import connect

# 连接文件数据库
conn = connect('test.db')

# 使用完毕后关闭
conn.close()
```

## 基本 CRUD 操作

### Create - 创建数据

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    # 创建表
    conn.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    
    # 单条插入
    conn.execute(
        'INSERT INTO products (name, price, stock) VALUES (?, ?, ?)',
        ('Apple', 3.99, 100)
    )
    conn.commit()
    
    # 批量插入
    products = [
        ('Banana', 1.99, 50),
        ('Orange', 2.49, 75),
        ('Grape', 4.99, 30),
    ]
    conn.executemany(
        'INSERT INTO products (name, price, stock) VALUES (?, ?, ?)',
        products
    )
    conn.commit()
    
    # 验证插入
    result = conn.execute('SELECT COUNT(*) FROM products')
    print(f"Total products: {result.scalar()}")
    # 输出: Total products: 4
```

### Read - 读取数据

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    # 创表并插入数据
    conn.execute('CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)')
    conn.executemany(
        'INSERT INTO users VALUES (?, ?, ?)',
        [(1, 'Alice', 25), (2, 'Bob', 30), (3, 'Charlie', 35)]
    )
    conn.commit()
    
    # 查询所有数据
    result = conn.execute('SELECT * FROM users')
    print("All users:")
    for row in result:
        print(f"  {row['name']}, age {row['age']}")
    # 输出:
    #   Alice, age 25
    #   Bob, age 30
    #   Charlie, age 35
    
    # 条件查询
    result = conn.execute(
        'SELECT * FROM users WHERE age > ?',
        (30,)
    )
    print("\nUsers older than 30:")
    for row in result:
        print(f"  {row.name} ({row.age})")
    # 输出:
    #   Charlie (35)
    
    # 聚合查询
    result = conn.execute('SELECT COUNT(*), AVG(age), MAX(age) FROM users')
    row = result.first()
    print(f"\nStatistics: count={row[0]}, avg_age={row[1]:.1f}, max_age={row[2]}")
    # 输出: Statistics: count=3, avg_age=30.0, max_age=35
```

### Update - 更新数据

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    # 创表并插入数据
    conn.execute('CREATE TABLE items (id INTEGER, name TEXT, value REAL)')
    conn.executemany(
        'INSERT INTO items VALUES (?, ?, ?)',
        [(1, 'A', 10.0), (2, 'B', 20.0), (3, 'C', 30.0)]
    )
    conn.commit()
    
    # 更新单条记录
    conn.execute(
        'UPDATE items SET value = ? WHERE name = ?',
        (15.0, 'A')
    )
    conn.commit()
    
    # 查询验证
    result = conn.execute('SELECT * FROM items WHERE name = ?', ('A',))
    print(f"Updated item A: value={result.first()['value']}")
    # 输出: Updated item A: value=15.0
    
    # 批量更新
    conn.execute('UPDATE items SET value = value * 1.1')
    conn.commit()
    
    result = conn.execute('SELECT * FROM items ORDER BY id')
    print("\nAfter 10% increase:")
    for row in result:
        print(f"  {row.name}: {row.value:.2f}")
    # 输出:
    #   A: 16.50
    #   B: 22.00
    #   C: 33.00
```

### Delete - 删除数据

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    # 创表并插入数据
    conn.execute('CREATE TABLE logs (id INTEGER, message TEXT)')
    conn.executemany(
        'INSERT INTO logs VALUES (?, ?)',
        [(1, 'Start'), (2, 'Process'), (3, 'Error'), (4, 'End')]
    )
    conn.commit()
    
    # 删除单条记录
    conn.execute('DELETE FROM logs WHERE id = ?', (3,))
    conn.commit()
    
    result = conn.execute('SELECT * FROM logs')
    print("After deleting id=3:")
    for row in result:
        print(f"  {row.id}: {row.message}")
    # 输出:
    #   1: Start
    #   2: Process
    #   4: End
    
    # 清空表
    conn.execute('DELETE FROM logs')
    conn.commit()
    
    result = conn.execute('SELECT COUNT(*) FROM logs')
    print(f"\nRemaining rows: {result.scalar()}")
    # 输出: Remaining rows: 0
```

## 事务处理

### 自动提交模式

```python
from vools.sql.sqlite import connect

# 默认关闭自动提交，需要手动 commit
with connect(':memory:') as conn:
    conn.execute('CREATE TABLE accounts (id INTEGER, balance REAL)')
    conn.execute('INSERT INTO accounts VALUES (1, 1000.0)')
    conn.execute('INSERT INTO accounts VALUES (2, 500.0)')
    
    # 注意：此时数据未提交，连接关闭后自动 rollback
```

### 手动提交与回滚

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    conn.execute('CREATE TABLE inventory (id INTEGER, quantity INTEGER)')
    conn.execute('INSERT INTO inventory VALUES (1, 100)')
    conn.execute('INSERT INTO inventory VALUES (2, 50)')
    
    # 正常提交
    conn.commit()
    
    # 执行一些操作
    conn.execute('UPDATE inventory SET quantity = quantity - 10 WHERE id = 1')
    
    # 手动回滚
    conn.rollback()
    
    # 验证数据未变化
    result = conn.execute('SELECT quantity FROM inventory WHERE id = 1')
    print(f"Quantity after rollback: {result.scalar()}")
    # 输出: Quantity after rollback: 100
```

### 原子性事务示例

```python
from vools.sql.sqlite import connect

def transfer_funds(conn, from_id, to_id, amount):
    """转账函数 - 展示事务的原子性"""
    try:
        # 扣除转出账户金额
        conn.execute(
            'UPDATE accounts SET balance = balance - ? WHERE id = ?',
            (amount, from_id)
        )
        
        # 增加转入账户金额
        conn.execute(
            'UPDATE accounts SET balance = balance + ? WHERE id = ?',
            (amount, to_id)
        )
        
        # 提交事务
        conn.commit()
        return True
    except Exception as e:
        # 发生错误时回滚
        conn.rollback()
        print(f"Transfer failed: {e}")
        return False

with connect(':memory:') as conn:
    # 创表并初始化账户
    conn.execute('''
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT,
            balance REAL
        )
    ''')
    conn.execute(
        'INSERT INTO accounts (name, balance) VALUES (?, ?)',
        ('Alice', 1000.0)
    )
    conn.execute(
        'INSERT INTO accounts (name, balance) VALUES (?, ?)',
        ('Bob', 500.0)
    )
    conn.commit()
    
    # 执行转账
    print("Before transfer:")
    result = conn.execute('SELECT name, balance FROM accounts ORDER BY id')
    for row in result:
        print(f"  {row.name}: ${row.balance:.2f}")
    # 输出:
    #   Before transfer:
    #   Alice: $1000.00
    #   Bob: $500.00
    
    # 转账 200 元
    success = transfer_funds(conn, from_id=1, to_id=2, amount=200.0)
    print(f"\nTransfer {'succeeded' if success else 'failed'}")
    
    print("\nAfter transfer:")
    result = conn.execute('SELECT name, balance FROM accounts ORDER BY id')
    for row in result:
        print(f"  {row.name}: ${row.balance:.2f}")
    # 输出:
    #   After transfer:
    #   Alice: $800.00
    #   Bob: $700.00
```

## ResultSet 操作

### 结果集遍历

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    conn.execute('CREATE TABLE data (x INTEGER, y INTEGER)')
    conn.executemany(
        'INSERT INTO data VALUES (?, ?)',
        [(1, 10), (2, 20), (3, 30)]
    )
    conn.commit()
    
    result = conn.execute('SELECT * FROM data')
    
    # 方式1: 迭代
    print("Using iterator:")
    for row in result:
        print(f"  x={row.x}, y={row.y}")
    # 输出:
    #   x=1, y=10
    #   x=2, y=20
    #   x=3, y=30
    
    # 方式2: 索引访问
    result.reset_cursor()
    print("\nUsing index:")
    print(f"  First row: {result[0]}")
    print(f"  Last row: {result[-1]}")
    # 输出:
    #   First row: Row(x=1, y=10)
    #   Last row: Row(x=3, y=30)
    
    # 方式3: fetch 方法
    result.reset_cursor()
    print("\nUsing fetch methods:")
    print(f"  fetchone: {result.fetchone()}")
    print(f"  fetchmany(2): {result.fetchmany(2)}")
    # 输出:
    #   fetchone: Row(x=1, y=10)
    #   fetchmany(2): [Row(x=2, y=20), Row(x=3, y=30)]
```

### 转换为其他格式

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    conn.execute('CREATE TABLE users (id INTEGER, name TEXT)')
    conn.executemany(
        'INSERT INTO users VALUES (?, ?)',
        [(1, 'Alice'), (2, 'Bob')]
    )
    conn.commit()
    
    result = conn.execute('SELECT * FROM users')
    
    # 转换为字典列表
    data_list = result.to_list()
    print(f"to_list(): {data_list}")
    # 输出: [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    
    # 获取标量值
    result = conn.execute('SELECT COUNT(*) FROM users')
    print(f"scalar(): {result.scalar()}")
    # 输出: 2
    
    # 转换为 pandas DataFrame（需要安装 pandas）
    try:
        df = result.to_dataframe()
        print(f"to_dataframe(): {type(df).__name__}")
    except ImportError:
        print("pandas not installed, skipping to_dataframe()")
```

## Row 对象访问

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    conn.execute('CREATE TABLE person (id INTEGER, name TEXT, age INTEGER)')
    conn.execute('INSERT INTO person VALUES (1, ?, ?)', ('Charlie', 28))
    conn.commit()
    
    result = conn.execute('SELECT * FROM person')
    row = result.first()
    
    # 列名访问
    print(f"By column name: name={row['name']}, age={row['age']}")
    # 输出: By column name: name=Charlie, age=28
    
    # 属性访问
    print(f"By attribute: name={row.name}, age={row.age}")
    # 输出: By attribute: name=Charlie, age=28
    
    # 索引访问
    print(f"By index: name={row[1]}, age={row[2]}")
    # 输出: By index: name=Charlie, age=28
    
    # 迭代
    print(f"Iteration: {list(row)}")
    # 输出: Iteration: [1, 'Charlie', 28]
    
    # 转换为字典
    print(f"as_dict(): {row.as_dict()}")
    # 输出: {'id': 1, 'name': 'Charlie', 'age': 28}
    
    # 检查列是否存在
    print(f"'name' in row: {'name' in row}")
    print(f"'email' in row: {'email' in row}")
    # 输出:
    #   'name' in row: True
    #   'email' in row: False
```

## 底层游标访问

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    conn.execute('CREATE TABLE test (value TEXT)')
    conn.execute('INSERT INTO test VALUES (?)', ('hello',))
    conn.commit()
    
    # 获取底层 sqlite3 游标
    cursor = conn.cursor()
    
    # 执行原生 sqlite3 操作
    cursor.execute('SELECT * FROM test')
    rows = cursor.fetchall()
    print(f"Raw cursor rows: {rows}")
    # 输出: Raw cursor rows: [('hello',)]
    
    cursor.close()
```

## 连接配置

### SQLite 特殊参数

```python
from vools.sql.sqlite import SqliteConnection

# 创建带特殊配置的连接
conn = SqliteConnection(
    database=':memory:',
    timeout=30.0,          # 等待锁的超时时间（秒）
    isolation_level=None,  # 自动提交模式（None 启用）
    check_same_thread=False  # 允许多线程访问
)
conn.connect()

# 执行操作
conn.execute('CREATE TABLE test (id INTEGER)')
conn.execute('INSERT INTO test VALUES (1)')
conn.commit()

print(f"Connection info: {conn}")
# 输出: Connection info: SqliteConnection(database=':memory:', status=connected)

conn.close()
```

## 错误处理

```python
from vools.sql.sqlite import connect

with connect(':memory:') as conn:
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
    
    try:
        # 违反唯一约束
        conn.execute('INSERT INTO users VALUES (1, ?)', ('Alice',))
        conn.commit()
        conn.execute('INSERT INTO users VALUES (1, ?)', ('Bob',))  # 重复主键
        conn.commit()
    except Exception as e:
        print(f"Error caught: {type(e).__name__}: {e}")
        conn.rollback()
        # 输出: Error caught: IntegrityError: UNIQUE constraint failed: users.id
    
    # 验证数据状态
    result = conn.execute('SELECT * FROM users')
    print(f"Users count: {len(result)}")
    # 输出: Users count: 1
```

## 完整示例

```python
from vools.sql.sqlite import connect

# 创建一个简单的任务追踪应用
with connect('tasks.db') as conn:
    # 创建任务表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    
    # 添加任务
    tasks = [
        ('Complete report', 'pending', 2),
        ('Send emails', 'in_progress', 1),
        ('Fix bugs', 'pending', 3),
    ]
    conn.executemany(
        'INSERT INTO tasks (title, status, priority) VALUES (?, ?, ?)',
        tasks
    )
    conn.commit()
    
    # 查询任务统计
    result = conn.execute('''
        SELECT status, COUNT(*) as count 
        FROM tasks 
        GROUP BY status
    ''')
    print("Task statistics:")
    for row in result:
        print(f"  {row.status}: {row.count}")
    # 输出:
    #   Task statistics:
    #   pending: 2
    #   in_progress: 1
    
    # 按优先级排序查询任务
    result = conn.execute('''
        SELECT * FROM tasks ORDER BY priority DESC
    ''')
    print("\nTasks by priority:")
    for row in result:
        print(f"  [{row.priority}] {row.title} ({row.status})")
    # 输出:
    #   Tasks by priority:
    #   [3] Fix bugs (pending)
    #   [2] Complete report (pending)
    #   [1] Send emails (in_progress)
    
    # 更新任务状态
    conn.execute(
        'UPDATE tasks SET status = ? WHERE title = ?',
        ('completed', 'Complete report')
    )
    conn.commit()
    
    # 删除已完成且低优先级的任务
    conn.execute(
        'DELETE FROM tasks WHERE status = ? AND priority < ?',
        ('completed', 2)
    )
    conn.commit()
    
    # 最终查询
    result = conn.execute('SELECT * FROM tasks')
    print("\nRemaining tasks:")
    for row in result:
        print(f"  {row.title} - {row.status}")
    # 输出:
    #   Remaining tasks:
    #   Fix bugs - pending
    #   Complete report - completed

print("Database operations completed successfully.")
# 输出: Database operations completed successfully.
```

## 相关模块

| 模块 | 说明 |
|------|------|
| [vools.sql](index.md) | SQL 工具概览 |
| [vools.sql.spark](spark.md) | Spark SQL 支持 |
| [vools.sql.postgres](../postgres/index.md) | PostgreSQL 支持 |
