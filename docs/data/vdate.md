# VDate 文档

> **模块路径**：`vools.datetime`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#019
> **最后更新**：2026-06-30

## 概述

VDate 是 vools 提供的日期时间类，继承自 `datetime.datetime`，提供丰富的日期处理方法。支持多种日期格式解析、日期计算、日期范围生成、周/月计算等链式调用功能。

## 创建 VDate

```python
from vools.datetime import VDate

# 从字符串创建（多种格式）
vd1 = VDate('2024-01-15')
print(vd1)  # 输出: 2024-01-15

vd2 = VDate('20240115')
print(vd2)  # 输出: 20240115

vd3 = VDate('2024-01-15 12:30:45')
print(vd3)  # 输出: 2024-01-15 12:30:45

vd4 = VDate('20240115123045')
print(vd4)  # 输出: 2024-01-15 12:30:45

# 从时间戳创建
vd5 = VDate(1705286400)  # 2024-01-15 00:00:00 UTC
print(vd5)  # 输出: 2024-01-15 00:00:00

# 从 datetime 对象创建
from datetime import datetime
vd6 = VDate(datetime(2024, 6, 30, 14, 30, 0))
print(vd6)  # 输出: 2024-06-30 14:30:00

# 使用当前时间（不传参数）
vd7 = VDate()
print(vd7)  # 输出: (当前日期时间，格式为 %Y-%m-%d %H:%M:%S)

# 指定格式创建
vd8 = VDate('15/06/2024', fmt='dd/MM/yyyy')
print(vd8)  # 输出: 2024-06-15
```

## 日期计算

### add_days / sub_days - 加减天数

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 加 5 天
result = vd.add_days(5)
print(result)  # 输出: 2024-01-20

# 减 10 天
result2 = vd.sub_days(10)
print(result2)  # 输出: 2024-01-05

# 支持负数（减法）
result3 = vd.add_days(-5)
print(result3)  # 输出: 2024-01-10
```

### add_months / sub_months - 加减月数

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 加 3 个月
result = vd.add_months(3)
print(result)  # 输出: 2024-04-15

# 减 6 个月
result2 = vd.sub_months(6)
print(result2)  # 输出: 2023-07-15

# 跨年计算
result3 = vd.add_months(15)
print(result3)  # 输出: 2025-04-15

# 月末日期处理（如 1月31日 + 1个月 = 2月29日/28日）
vd2 = VDate('2024-01-31')
result4 = vd2.add_months(1)
print(result4)  # 输出: 2024-02-29（2024是闰年）
```

### add_years / sub_years - 加减年数

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 加 1 年
result = vd.add_years(1)
print(result)  # 输出: 2025-01-15

# 减 2 年
result2 = vd.sub_years(2)
print(result2)  # 输出: 2022-01-15

# 闰年 2月29日处理
vd2 = VDate('2024-02-29')  # 闰年
result3 = vd2.add_years(1)
print(result3)  # 输出: 2025-02-28（非闰年，自动调整为2月28日）
```

## 日期范围生成

### getDateRange - 生成日期范围

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 指定结束日期，生成范围
result = vd.getDateRange(start='2024-01-01', end='2024-01-10')
print(result)  # 输出: ['2024-01-01', '2024-01-02', ..., '2024-01-10']

# 指定数量，向后生成
result2 = vd.getDateRange(start='2024-01-01', periods=5)
print(result2)  # 输出: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']

# 从当前日期向前推算
result3 = vd.getDateRange(end='2024-01-10', periods=7)
print(result3)  # 输出: ['2024-01-04', '2024-01-05', '2024-01-06', '2024-01-07', '2024-01-08', '2024-01-09', '2024-01-10']

# 按周生成
result4 = vd.getDateRange(start='2024-01-01', end='2024-01-31', freq='W')
print(result4)  # 输出: ['2024-01-01', '2024-01-08', '2024-01-15', '2024-01-22', '2024-01-29']

# 按月生成
result5 = vd.getDateRange(start='2024-01-15', end='2024-06-15', freq='M')
print(result5)  # 输出: ['2024-01-15', '2024-02-15', '2024-03-15', '2024-04-15', '2024-05-15', '2024-06-15']
```

### getDateRangeEx - 自动排序的日期范围

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 自动调整起止顺序（从早到晚）
result = vd.getDateRangeEx(start='2024-01-20', end='2024-01-10')
print(result)  # 输出: ['2024-01-10', '2024-01-11', ..., '2024-01-20']

# 其他用法同 getDateRange
result2 = vd.getDateRangeEx(start='2024-01-01', periods=5)
print(result2)  # 输出: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']
```

### get_date_range - 实例方法生成范围

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 从当前日期到指定日期
result = vd.get_date_range('2024-01-20')
print(result)  # 输出: ['2024-01-15', '2024-01-16', '2024-01-17', '2024-01-18', '2024-01-19', '2024-01-20']

# 按周生成
result2 = vd.get_date_range('2024-02-15', freq='W')
print(result2)  # 输出: ['2024-01-15', '2024-01-22', '2024-01-29', '2024-02-05', '2024-02-12']

# 指定输出格式
result3 = vd.get_date_range('2024-01-20', fmt='%Y%m%d')
print(result3)  # 输出: ['20240115', '20240116', ..., '20240120']
```

## 周/月计算

### get_week - 获取星期

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')  # 周一

# 获取本周周一（weekday=1）
monday = vd.get_week(weekday=1)
print(monday)  # 输出: 2024-01-15

# 获取本周周日（weekday=7）
sunday = vd.get_week(weekday=7)
print(sunday)  # 输出: 2024-01-21

# 获取上周周一（num=-1）
last_week_monday = vd.get_week(num=-1, weekday=1)
print(last_week_monday)  # 输出: 2024-01-08

# 获取下周周五（num=1, weekday=5）
next_week_friday = vd.get_week(num=1, weekday=5)
print(next_week_friday)  # 输出: 2024-01-19

# 验证：2024-01-15 是周一
vd2 = VDate('2024-01-15')
print(vd2.strftime('%u'))  # 输出: 1（周一）
```

### get_month - 获取月份

```python
from vools.datetime import VDate

vd = VDate('2024-01-31')

# 获取本月第一天
first = vd.get_month()
print(first)  # 输出: 2024-01-01

# 获取本月最后一天
last = vd.get_month(last_day=True)
print(last)  # 输出: 2024-01-31

# 获取下个月第一天
next_first = vd.get_month(num=1)
print(next_first)  # 输出: 2024-02-01

# 获取上个月最后一天
prev_last = vd.get_month(num=-1, last_day=True)
print(prev_last)  # 输出: 2023-12-31

# 获取3个月后的日期
future = vd.get_month(num=3)
print(future)  # 输出: 2024-04-01
```

## 日期简化

### simplify - 简化日期列表为范围

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 简化连续日期为范围
dates = ['20240101', '20240102', '20240103', '20240105', '20240106', '20240110']
result = vd.simplify(dates)
print(result)  # 输出: [spyDate(start='2024-01-01', end='2024-01-03', cnt=3), spyDate(start='2024-01-05', end='2024-01-06', cnt=2), spyDate(start='2024-01-10', end='2024-01-10', cnt=1)]

# 查看简化后的范围
for item in result:
    print(f"从 {item.start} 到 {item.end}，共 {item.cnt} 天")

# 输出:
# 从 2024-01-01 到 2024-01-03，共 3 天
# 从 2024-01-05 到 2024-01-06，共 2 天
# 从 2024-01-10 到 2024-01-10，共 1 天
```

### simplify_date_ranges - 静态方法简化日期

```python
from vools.datetime import VDate

# 直接使用静态方法
dates = ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-05', '2024-01-06', '2024-01-10']
result = VDate.simplify_date_ranges(dates)
print(result)  # 输出: [('2024-01-01', '2024-01-03'), ('2024-01-05', '2024-01-06'), ('2024-01-10', '2024-01-10')]
```

## 日期比较

```python
from vools.datetime import VDate

vd1 = VDate('2024-01-15')
vd2 = VDate('2024-01-20')
vd3 = VDate('2024-01-15')

# 相等比较
print(vd1 == vd3)  # 输出: True
print(vd1 == vd2)  # 输出: False

# 小于比较
print(vd1 < vd2)  # 输出: True
print(vd2 < vd1)  # 输出: False

# 大于比较
print(vd1 > vd2)  # 输出: False
print(vd2 > vd1)  # 输出: True

# 与字符串比较
print(vd1 == '2024-01-15')  # 输出: True
print(vd1 < '2024-01-20')  # 输出: True

# 与 datetime 比较
from datetime import datetime
dt = datetime(2024, 1, 15)
print(vd1 == dt)  # 输出: True
```

## 日期运算

```python
from vools.datetime import VDate
from datetime import timedelta

vd = VDate('2024-01-15')

# VDate + int = 加天数
result = vd + 5
print(result)  # 输出: 2024-01-20

# VDate - int = 减天数
result2 = vd - 5
print(result2)  # 输出: 2024-01-10

# VDate - VDate = 天数差
vd2 = VDate('2024-01-20')
diff = vd2 - vd
print(diff)  # 输出: 5.0（天）

# VDate + timedelta
result3 = vd + timedelta(weeks=2)
print(result3)  # 输出: 2024-01-29

# 负数天数
result4 = vd + (-10)
print(result4)  # 输出: 2024-01-05
```

## 格式化输出

### toString - 转换为字符串

```python
from vools.datetime import VDate

vd = VDate('2024-01-15 12:30:45')

# 默认格式（使用初始化时的格式）
print(vd.toString())  # 输出: 2024-01-15 12:30:45

# 指定格式
print(vd.toString('%Y%m%d'))  # 输出: 20240115
print(vd.toString('%d/%m/%Y'))  # 输出: 15/01/2024
print(vd.toString('%B %d, %Y'))  # 输出: January 15, 2024

# 使用自定义格式（yyyy/MM/dd）
print(vd.toString('yyyy/MM/dd'))  # 输出: 2024/01/15
```

### strftime - 标准格式化

```python
from vools.datetime import VDate

vd = VDate('2024-01-15')

# 常用格式
print(vd.strftime('%Y'))  # 输出: 2024
print(vd.strftime('%m'))  # 输出: 01
print(vd.strftime('%d'))  # 输出: 15
print(vd.strftime('%Y-%m-%d'))  # 输出: 2024-01-15
print(vd.strftime('%H:%M:%S'))  # 输出: 00:00:00
print(vd.strftime('%A'))  # 输出: Monday
print(vd.strftime('%B'))  # 输出: January
```

## 访问日期组件

```python
from vools.datetime import VDate

vd = VDate('2024-01-15 12:30:45')

# 访问年、月、日
print(vd.year)  # 输出: 2024
print(vd.month)  # 输出: 1
print(vd.day)  # 输出: 15

# 访问时、分、秒
print(vd.hour)  # 输出: 12
print(vd.minute)  # 输出: 30
print(vd.second)  # 输出: 45

# 访问星期（1=周一，7=周日）
print(vd.weekday())  # 输出: 0（周一）
print(vd.isoweekday())  # 输出: 1（周一）

# 日期时间戳
print(vd.timestamp())  # 输出: 1705312245.0
```

## 链式调用示例

```python
from vools.datetime import VDate

# 链式计算示例：计算三个月后的周五
result = (
    VDate('2024-01-15')
    .add_months(3)                    # 2024-04-15
    .add_days(5 - 1)                  # 调整到周五（假设4月15是周一）
    .get_week(weekday=5)              # 获取当周周五
)
print(result)  # 输出: 2024-04-19

# 链式生成日期范围
dates = (
    VDate('2024-01-01')
    .getDateRange(start='2024-01-01', periods=10)
)
print(dates)  # 输出: ['2024-01-01', '2024-01-02', ..., '2024-01-10']

# 链式处理日期列表
vd = VDate('2024-01-15')
simplified = vd.simplify(['20240110', '20240111', '20240112', '20240120', '20240121'])
for item in simplified:
    print(f"{item.start} ~ {item.end}: {item.cnt}天")

# 输出:
# 2024-01-10 ~ 2024-01-12: 3天
# 2024-01-20 ~ 2024-01-21: 2天
```

## 与 datetime 的互相转换

```python
from vools.datetime import VDate
from datetime import datetime, date

# VDate 转 datetime
vd = VDate('2024-01-15 12:30:45')
dt = datetime(vd.year, vd.month, vd.day, vd.hour, vd.minute, vd.second)
print(dt)  # 输出: 2024-01-15 12:30:45

# VDate 转 date
d = vd.date()
print(d)  # 输出: 2024-01-15

# datetime 转 VDate
dt2 = datetime(2024, 6, 30, 14, 30, 0)
vd2 = VDate(dt2)
print(vd2)  # 输出: 2024-06-30 14:30:00

# date 转 VDate
d2 = date(2024, 6, 30)
vd3 = VDate(d2)
print(vd3)  # 输出: 2024-06-30
```

## 实用示例

### 计算工作日

```python
from vools.datetime import VDate

def add_business_days(start_date, days):
    """加工作日（跳过周末）"""
    current = VDate(start_date)
    added = 0
    while added < days:
        current = current.add_days(1)
        if current.weekday() < 5:  # 周一到周五
            added += 1
    return current

# 从周一加5个工作日
result = add_business_days('2024-01-15', 5)  # 周一
print(result)  # 输出: 2024-01-22（周一 + 5个工作日 = 下下周一）

# 从周五加2个工作日
result2 = add_business_days('2024-01-19', 2)  # 周五
print(result2)  # 输出: 2024-01-23（周二）
```

### 日期范围交集

```python
from vools.datetime import VDate

def date_ranges_overlap(start1, end1, start2, end2):
    """判断两个日期范围是否有交集"""
    s1, e1 = VDate(start1), VDate(end1)
    s2, e2 = VDate(start2), VDate(end2)
    
    return not (e1 < s2 or e2 < s1)

# 有交集
print(date_ranges_overlap('2024-01-01', '2024-01-15', '2024-01-10', '2024-01-20'))  # True

# 无交集
print(date_ranges_overlap('2024-01-01', '2024-01-10', '2024-01-15', '2024-01-20'))  # False
```

### 计算年龄

```python
from vools.datetime import VDate

def calculate_age(birth_date, today=None):
    """计算年龄"""
    birth = VDate(birth_date)
    if today is None:
        today = VDate()
    else:
        today = VDate(today)
    
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age

# 计算年龄
print(calculate_age('1990-06-15'))  # 输出: 34（假设当前是2024年）
print(calculate_age('2000-01-01'))  # 输出: 24
```
