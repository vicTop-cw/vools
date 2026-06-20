# vools.datetime

日期时间工具模块，提供日期处理和计算功能。

## 主要功能

- **日期类**: `vDate` - 日期对象封装
- **日期计算**: `days_gap`, `weeks_gap`, `months_gap`
- **日期生成**: `get_date_range`, `get_recently_days`, `get_recently_months`
- **日期格式化**: `parse_date_string`, `get_week`, `get_month`

## 核心功能

| 名称 | 说明 | 示例 |
|------|------|------|
| `vDate` | 日期对象 | `vDate('2024-01-01')` |
| `days_gap` | 计算天数差 | `days_gap(date1, date2)` |
| `get_date_range` | 生成日期范围 | `get_date_range(start, end)` |
| `parse_date_string` | 解析日期字符串 | `parse_date_string('20240101')` |

## 使用示例

```python
from vools.datetime import vDate, days_gap, get_date_range

# 创建日期对象
d = vDate('2024-01-01')

# 计算天数差
gap = days_gap('2024-01-01', '2024-12-31')

# 生成日期范围
dates = get_date_range('2024-01-01', '2024-01-31')
```

## 注意事项

- 支持多种日期格式，自动识别