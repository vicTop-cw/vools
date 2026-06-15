# vools vic 工具类

vic 类提供日期处理（vicDate）、文本处理（vicText）、列表处理（vicList）和通用工具（vicTools）。

---

### 基本用法

`vicDate` 是一个日期处理工具类，提供日期格式化、计算和比较功能。

```python
from vools.datetime.utils import vicDate

# 使用默认日期（今天）
date = vicDate()
print(date.strftime('%Y-%m-%d'))  # 当前日期

# 使用字符串初始化
date = vicDate("2024-01-15")

# 使用 date 对象初始化
from datetime import date as dt_date
date = vicDate(dt_date(2024, 1, 15))
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `value` | Any | 日期值，可以是字符串、date 对象或 None |
| `fmt` | str | 输入日期格式，默认 `'%Y-%m-%d'` |

### 核心属性

| 属性 | 说明 |
|------|------|
| `year` | 年份 |
| `month` | 月份 |
| `day` | 日期 |
| `weekday` | 星期几（0-6） |
| `run_date` | 当前的 date 对象 |

### 核心方法

#### `strftime(fmt='%Y-%m-%d')`

格式化日期为字符串。

```python
date = vicDate("2024-01-15")
print(date.strftime("%Y/%m/%d"))  # "2024/01/15"
print(date.strftime("%d-%b-%Y"))  # "15-Jan-2024"
```

#### `add_days(n)`

添加天数。

```python
date = vicDate("2024-01-15")
new_date = date.add_days(5)
print(new_date.strftime('%Y%m%d'))  # "20240120"
```

#### `sub_days(n)`

减去天数。

```python
date = vicDate("2024-01-15")
new_date = date.sub_days(5)
print(new_date.strftime('%Y%m%d'))  # "20240110"
```

#### `add_months(n)`

添加月份。

```python
date = vicDate("2024-01-15")
new_date = date.add_months(1)
print(new_date.strftime('%Y%m%d'))  # "20240215"
```

#### `week_range()`

获取本周的起始和结束日期。

```python
date = vicDate("2024-01-15")
start, end = date._date_processor._get_week_range(date.date_obj.date())
print(start, end)  # 本周一和本周日
```

#### `month_range()`

获取本月的起始和结束日期。

```python
date = vicDate("2024-01-15")
start, end = date._date_processor._get_month_range(date.date_obj.date())
print(start, end)  # 本月1日和本月最后一天
```

### 日期比较

```python
date1 = vicDate("2024-01-15")
date2 = vicDate("2024-01-20")

print(date1.date_obj < date2.date_obj)   # True
print(date1.date_obj > date2.date_obj)   # False
print(date1.date_obj == date2.date_obj)  # False
```

### 边界情况处理

```python
# 闰年处理
date = vicDate("2024-02-29")
print(date.strftime('%Y%m%d'))  # "20240229"

# 月末处理
date = vicDate("2024-01-31")
new_date = date.add_days(1)
print(new_date.strftime('%Y%m%d'))  # "20240201"

# 年末处理
date = vicDate("2024-12-31")
new_date = date.add_days(1)
print(new_date.strftime('%Y%m%d'))  # "20250101"
```

### 示例代码

```python
from vools.datetime.utils import vicDate

# 创建日期对象
date = vicDate("2024-06-15")

# 获取属性
print(f"Year: {date.date_obj.year}")      # 2024
print(f"Month: {date.date_obj.month}")    # 6
print(f"Day: {date.date_obj.day}")        # 15
print(f"Weekday: {date.date_obj.weekday()}") # 5 (星期六)

# 日期计算
next_week = date.add_days(7)
last_month = date.add_months(-1)

# 格式化输出
print(date.strftime("%Y年%m月%d日"))  # "2024年06月15日"
```

## 核心类

vools 提供四个核心自定义数据类型：

### vicTools

```python
from vools import vicTools

# 日期处理
date_seq = vicTools.get_date_seq(nums=7, date_type='day', fmt='yyyyMMdd')

# 字符串处理
trimmed = vicTools.trim("  hello world  ")

# 正则表达式操作
matches = vicTools.regexp_findall(r'\d+', 'abc123def456')

# 生成随机字段名
field_name = vicTools.generate_random_field_name()
```

### vicText

```python
from vools import vicText

# 创建文本对象
txt = vicText("Hello, World!")

# 文本操作
upper_txt = txt.upper()

# 正则表达式操作
replaced = txt.regexp_replace(r'World', 'vools')

# 分割文本
parts = txt.splitEx(',')

# 写入文件
txt.write('output.txt')

# 从文件读取
read_txt = vicText.get_content_fromfile('output.txt')
```

### vicList

```python
from vools import vicList

# 创建列表对象
lst = vicList([1, 2, 3, 4, 5])

# 列表操作
slice_lst = lst.islice(1, 4)

# 集合操作
other_lst = vicList([3, 4, 5, 6, 7])
intersection = lst & other_lst  # 交集
union = lst | other_lst  # 并集

# 唯一元素
unique_lst = vicList(1, 2, 2, 3, 3, 3).unique

# 映射和过滤
result = lst.map(lambda x: x * 2).collect()
result = lst.filter(lambda x: x > 2).collect()
```

