# vools.data - 数据结构模块

轻量级数据结构，与 pandas DataFrame 互补。

## 数据结构

- **Seq/VList**: 链式序列
- **VText**: 文本处理
- **Table**: 二维表格 (新增)

## Table 二维表格

`Table` 是 vools.data 的核心二维数据结构，提供与 pandas DataFrame 类似的操作。

### 特点

- 轻量级，纯 Python 实现
- 链式操作风格 (类似 jQuery / LINQ)
- 内置 SQL 风格方法
- 与 vools.xl 深度集成
- 与 pandas DataFrame 互转便捷

### 快速开始

```python
from vools.data import Table

# 创建表格
data = [
    ['Alice', 25, 'NYC', 50000],
    ['Bob', 30, 'LA', 60000],
    ['Charlie', 35, 'NYC', 70000],
]
table = Table(data, columns=['name', 'age', 'city', 'salary'])

print(table.rows())  # 3
print(table.cols())  # 4
print(table.column('name'))  # ['Alice', 'Bob', 'Charlie']
```

### 链式操作

```python
result = table \
    .filter(lambda r: r['age'] > 25) \
    .select('name', 'age', 'salary') \
    .sort('salary', reverse=True)
```

### SQL 风格方法

```python
# WHERE
adults = table.where('age >= 30')

# ORDER BY
sorted_table = table.order_by('age', desc=True)

# SELECT + WHERE + ORDER BY
result = table.select('name', 'city') \
              .where('age > 25') \
              .order_by('age', desc=True)

# 聚合
summary = table.agg({'age': 'mean', 'salary': 'sum'})
# -> Table(1 rows x 2 cols, [31.6, 180000])

# GROUP BY + 手动聚合
groups = table.group_by('city')
for city, group in groups.items():
    print(city, group.rows(), '人, 平均工资:', group.avg('salary'))

# 一体化查询
top5 = table.query(where='age >= 30', order_by='age', desc=True, limit=5)
```

### 数据访问

```python
# 按行列访问
table.at(0, 0)           # 'Alice'
table.at(0, 'name')      # 'Alice'
table.row(0)             # {'name': 'Alice', 'age': 25, ...}
table.column('age')      # [25, 30, 35]
table['name']            # 同 column('name')
table[0]                 # 同 row(0)
table[0, 'name']         # 同 at(0, 'name')
```

### 与 pandas 互转

```python
import pandas as pd
from vools.data import Table

# Table -> DataFrame
df = table.to_dataframe()
print(df)

# DataFrame -> Table
t2 = Table.from_dataframe(df)
print(t2)
```

### Excel 读写

```python
# 写入 Excel
table.write_excel('output.xlsx')

# 读取 Excel
t2 = Table.read_excel('input.xlsx')
```

### 构造函数

```python
# 从二维列表
Table(data, columns=['a', 'b'])

# 从字典列表
Table.from_dicts([
    {'name': 'Alice', 'age': 25},
    {'name': 'Bob', 'age': 30},
])

# 从 pandas DataFrame
Table.from_dataframe(df)

# 从 Excel
Table.read_excel('file.xlsx')
```

## API 参考

### 属性

| 属性 | 说明 |
|------|------|
| `rows()` | 行数 |
| `cols()` | 列数 |
| `columns()` | 列名列表 |
| `is_empty()` | 是否为空 |

### 数据访问

| 方法 | 说明 |
|------|------|
| `at(row, col)` | 按行列访问元素 |
| `row(i)` | 获取一行 (字典) |
| `column(name)` | 获取一列 (列表) |
| `rowslice(start, end)` | 行切片 |
| `iter_rows()` | 行迭代器 |
| `iter_values()` | 值迭代器 |
| `iter_columns()` | 列迭代器 |

### 链式操作

| 方法 | 说明 |
|------|------|
| `select(*cols)` | 选择列 |
| `filter(predicate)` | 过滤行 |
| `map(func)` | 映射行 |
| `sort(col, reverse)` | 排序 |
| `distinct()` | 去重 |
| `limit(n, offset)` | 限制行数 |
| `foreach(func)` | 遍历 |

### SQL 风格方法

| 方法 | 说明 |
|------|------|
| `where(expr)` | 条件过滤 (字符串/函数) |
| `order_by(col, desc)` | 排序 |
| `having(predicate)` | 分组后过滤 |
| `agg(funcs)` | 聚合 |
| `query(**kwargs)` | 一体化查询 |

### 聚合

| 方法 | 说明 |
|------|------|
| `group_by(col)` | 分组 |
| `sum(col)` | 求和 |
| `avg(col)` | 平均值 |
| `min(col)` | 最小值 |
| `max(col)` | 最大值 |
| `count()` | 行数 |

### 转换

| 方法 | 说明 |
|------|------|
| `to_dicts()` | 转为字典列表 |
| `to_list()` | 转为二维列表 |
| `to_dataframe()` | 转为 pandas DataFrame |
| `from_dicts(dicts)` | 从字典列表创建 |
| `from_dataframe(df)` | 从 DataFrame 创建 |

### Excel IO

| 方法 | 说明 |
|------|------|
| `read_excel(filename, sheet_index)` | 从 Excel 读取 |
| `write_excel(filename, sheet_name)` | 写入 Excel |

## Row 行对象

`Row` 是 Table 的一行对象，继承自 Seq，支持行级链式操作。

### 特点

- 继承 Seq，20+ 链式操作方法（map、filter、where、select、take、skip 等）
- 支持按列名或索引访问单元格
- 使用 @rself 装饰器，方法调用后返回自身实例

### 使用示例

```python
from vools.data import Table

table = Table([
    ['Alice', 25, 'NYC'],
    ['Bob', 30, 'LA'],
], columns=['name', 'age', 'city'])

# 获取行对象
row = table.get_row(0)

# 按列名访问
print(row['name'])  # 'Alice'
print(row['age'])   # 25

# 按索引访问
print(row[0])  # 'Alice'
print(row[1])  # 25

# 修改单元格
row['age'] = 26

# 链式操作
result = row.map(str).filter(lambda x: x)
```

### API 参考

| 方法 | 说明 |
|------|------|
| `row['col_name']` / `row[index]` | 访问单元格 |
| `row['col_name'] = value` | 修改单元格 |
| `row.map(func)` | 映射（返回 Row） |
| `row.filter(predicate)` | 过滤（返回 Row） |
| `row.where(expr)` | 条件过滤（返回 Row） |
| `row.select(*cols)` | 选择列（返回 Row） |
| `row.take(n)` | 取前 n 个（返回 Row） |
| `row.skip(n)` | 跳过 n 个（返回 Row） |
| `len(row)` | 行长度 |
| `list(row)` | 转为列表 |

## Column 列对象

`Column` 是 Table 的一列对象，继承自 Seq，支持列级链式操作和聚合计算。

### 特点

- 继承 Seq，20+ 链式操作方法
- 内置聚合方法（sum、avg、min、max、count、distinct 等）
- 使用 @rself 装饰器，方法调用后返回自身实例

### 使用示例

```python
from vools.data import Table

table = Table([
    ['Alice', 25, 'NYC'],
    ['Bob', 30, 'LA'],
], columns=['name', 'age', 'city'])

# 获取列对象
col_age = table.get_col('age')

# 基本访问
print(col_age[0])  # 25
print(len(col_age))  # 2

# 聚合计算
print(col_age.sum())   # 55
print(col_age.avg())   # 27.5
print(col_age.min())   # 25
print(col_age.max())   # 30
print(col_age.count())  # 2

# 去重
print(col_age.distinct())  # [25, 30]
```

### API 参考

| 方法 | 说明 |
|------|------|
| `col[index]` | 按索引访问元素 |
| `len(col)` | 列长度 |
| `list(col)` | 转为列表 |
| `col.sum()` | 求和 |
| `col.avg()` | 平均值 |
| `col.min()` | 最小值 |
| `col.max()` | 最大值 |
| `col.count()` | 元素个数 |
| `col.distinct()` | 去重 |
| `col.map(func)` | 映射（返回 Column） |
| `col.filter(predicate)` | 过滤（返回 Column） |
| `col.first()` | 第一个元素 |
| `col.last()` | 最后一个元素 |

## Qax 表格对象

`Qax` 继承自 Table，提供 SqlCel QAX 风格的 API，60+ 便捷方法。

### 特点

- 完全兼容 SqlCel QAX 命名风格（PascalCase）
- 行列索引从 1 开始（QAX 风格）
- 底层复用 Table 实现
- 使用 @rself 装饰器，支持链式调用
- Python 3.6 兼容

### 使用场景

- 从 SqlCel/VB 迁移的代码
- 习惯 QAX 风格 API 的开发者

### 使用示例

```python
from vools.data import Qax

# 创建表格
qax = Qax([
    ['Alice', 25, 'New York'],
    ['Bob', 30, 'Los Angeles'],
], columns=['name', 'age', 'city'], name='users')

# QAX 风格访问（索引从1开始）
print(qax.GetCell(1, 1))   # 'Alice'
print(qax.GetCell2('name', 2))  # 'Bob'

# 链式操作
qax.QAXFilter(lambda r: r['age'] > 25) \
   .QAXSelect('name', 'city') \
   .showQax()

# 行列信息
print(qax.QAXRows())   # 2
print(qax.QAXCols())   # 3
print(qax.QAXColNames())  # ['name', 'age', 'city']
```

### API 参考

#### 信息类

| 方法 | 说明 |
|------|------|
| `QAXRows()` | 返回行数 |
| `QAXCols()` | 返回列数 |
| `QAXColNames()` | 返回列名列表 |
| `QAXRowNum()` | 当前行号 |
| `QAXColNum()` | 当前列号 |

#### 创建类

| 方法 | 说明 |
|------|------|
| `ArrayToQax(data, columns, name)` | 从数组创建 |
| `NewArray(row, col)` | 创建空白数组 |

#### 访问类

| 方法 | 说明 |
|------|------|
| `GetCell(row, col)` | 获取单元格（1基索引） |
| `GetCell2(col_name, row)` | 按列名和行号获取 |
| `GetRow(row)` | 获取整行 |
| `GetCol(col)` | 获取整列 |
| `GetRowNum()` | 获取行号 |
| `GetColNum()` | 获取列号 |
| `GetValue(row, col)` | 获取值 |

#### 修改类

| 方法 | 说明 |
|------|------|
| `SetCell(row, col, value)` | 设置单元格 |
| `AddRow(row)` | 添加行 |
| `AddCol(col)` | 添加列 |
| `DelRow(row)` | 删除行 |
| `DelCol(col)` | 删除列 |
| `Update()` | 更新表格 |

#### 数据操作类

| 方法 | 说明 |
|------|------|
| `QAXFilter(predicate)` | 过滤行 |
| `QAXSelect(*cols)` | 选择列 |
| `QAXOrderBy(col, desc)` | 排序 |
| `QAXJoin(other, on)` | 连接 |
| `QAXMerge(other)` | 合并 |

#### 聚合类

| 方法 | 说明 |
|------|------|
| `Sum(col)` | 求和 |
| `Avg(col)` | 平均值 |
| `Min(col)` | 最小值 |
| `Max(col)` | 最大值 |
| `Count()` | 计数 |
| `CountIf(condition)` | 条件计数 |
| `SumIf(col, condition)` | 条件求和 |

#### 显示类

| 方法 | 说明 |
|------|------|
| `showQax()` | 打印表格（1基索引） |
| `show()` | 打印表格 |
| `printQax()` | 打印表格 |
| `Print()` | 打印表格 |
