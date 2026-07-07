# vools 数据与日期工具（v0.1.18）

vools 提供轻量级的数据容器（`Seq` / `VList` / `VText`）以及日期处理工具（`vDate` / `DateProcessor` / `EnhancedDateFormatter`），适合在数据处理和文本解析场景快速上手。

> Python 3.9+ 支持

---

## 1. Seq 序列

`Seq` 是 `list` 的子类，提供函数式风格的链式调用。

```python
from vools.data import Seq

s = Seq([1, 2, 3, 4, 5])
print(s)               # Seq([1, 2, 3, 4, 5])

# map / filter
doubled = s.map(lambda x: x * 2)
print(doubled)         # Seq([2, 4, 6, 8, 10])

evens = s.filter(lambda x: x % 2 == 0)
print(evens)           # Seq([2, 4])

# 链式调用
result = Seq([1, 2, 3, 4, 5]) \
    .filter(lambda x: x > 2) \
    .map(lambda x: x * 10)
print(result)          # Seq([30, 40, 50])

# reduce
total = s.reduce(lambda a, b: a + b, 0)
print(total)           # 15
```

因为 `Seq` 继承自 `list`，所有 Python 原生列表方法（`len`、`append`、切片、迭代等）都可用。

---

## 2. VList — 列表容器

`VList` 是 `Seq` 的一个别名，同样支持 `map` / `filter` 等方法：

```python
from vools.data import VList

v = VList([1, 2, 2, 3, 3, 3, 4, 5])

# unique 去重
print(v.unique())        # Seq([1, 2, 3, 4, 5])

# 集合运算
other = VList([3, 4, 5, 6, 7])
print(v & other)         # 交集
print(v | other)         # 并集
```

---

## 3. VText — 文本容器

`VText` 是 `str` 的子类，保留了字符串的全部方法：

```python
from vools.data import VText

text = VText("Hello, World!")

print(text.upper())      # "HELLO, WORLD!"
print(text.split(","))   # ['Hello', ' World!']
print(len(text))         # 13

# 正则替换
print(text.replace("World", "vools"))  # "Hello, vools!"
```

因为继承自 `str`，它可以作为字符串直接参与任何接受 `str` 的操作。

---

## 4. NONE 与 collect

`NONE` 是一个占位符空对象；`collect` 用于从迭代器/生成器收集结果：

```python
from vools.data import NONE, collect

gen = (x * 2 for x in range(5))
result = collect(gen)
print(result)             # [0, 2, 4, 6, 8]

# NONE 是单例空对象
print(NONE is NONE)       # True
```

---

## 5. vDate — 日期字符串工具

`vDate` 是一个便捷函数，接受日期字符串并规范化输出：

```python
from vools.datetime import vDate

# 接受常见日期字符串格式
print(vDate("2024-01-15"))      # "2024-01-15"
print(vDate("2024/1/15"))       # "2024-01-15"
print(vDate("20240115"))        # "2024-01-15"
```

返回值为字符串，可直接用于后续处理。

---

## 6. DateProcessor — 日期表达式处理器

`DateProcessor` 支持日期表达式解析，适合做日期范围计算：

```python
from vools.datetime import DateProcessor

dp = DateProcessor()

# 解析日期表达式（支持 today、昨天、days_ago_7 等）
result = dp.do("today")
print(result)

# 取日期列表
dates = dp.get_date_list("days_ago_7", "today")
print(dates)

# 月初 / 月末
print(dp.month_begin("2024-03-15"))
print(dp.month_end("2024-03-15"))

# 获取所有内置日期变量
variables = dp.get_all_date_variables()
print(list(variables.keys())[:10])
```

---

## 7. EnhancedDateFormatter — 增强型日期格式化

`EnhancedDateFormatter` 支持模板中的日期变量替换：

```python
from vools.datetime import EnhancedDateFormatter

formatter = EnhancedDateFormatter(template="报告日期：{today}")
output = formatter.do(today="2024-06-15")
print(output)  # "报告日期：2024-06-15"
```

---

## 8. 日期范围辅助函数

`vools.datetime` 还提供了一批常用的辅助函数：

```python
from vools.datetime import (
    get_week,
    get_month,
    days_gap,
    weeks_gap,
    months_gap,
    get_recently_months,
    get_recently_weeks,
    get_recently_days,
    get_dates,
    get_date_range,
    simplify_date_ranges,
)

# 最近 7 天
last_week = get_recently_days(7)
print(last_week)                         # ["2026-06-16", ..., "2026-06-22"]

# 最近 3 个月
last_3_months = get_recently_months(3)
print(last_3_months)

# 两个日期之间的天数
diff = days_gap("2024-01-01", "2024-01-15")
print(diff)                              # 14

# 获取日期区间列表
dr = get_date_range("2024-01-01", "2024-01-05")
print(dr)                                # ["2024-01-01", ..., "2024-01-05"]
```

---

## 9. 导入位置速查

| 类型 | 导入位置 | 说明 |
|------|----------|------|
| `Seq` | `from vools.data import Seq` | 带 `map`/`filter`/`reduce` 的列表容器 |
| `VList` | `from vools.data import VList` | `Seq` 的别名，支持集合运算 |
| `VText` | `from vools.data import VText` | 字符串子类 |
| `NONE` / `collect` | `from vools.data import NONE, collect` | 空对象 / 收集迭代器结果 |
| `vDate` | `from vools.datetime import vDate` | 日期字符串规范化 |
| `DateProcessor` | `from vools.datetime import DateProcessor` | 日期表达式解析 |
| `EnhancedDateFormatter` | `from vools.datetime import EnhancedDateFormatter` | 模板日期替换 |
| `get_recently_days / _weeks / _months` | `from vools.datetime import ...` | 日期范围辅助 |
| `days_gap / weeks_gap / months_gap` | `from vools.datetime import ...` | 日期间隔计算 |
| `get_date_range / simplify_date_ranges` | `from vools.datetime import ...` | 日期区间工具 |
