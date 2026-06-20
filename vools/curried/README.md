# vools.curried

柯里化函数库，提供预柯里化的常用函数。

## 主要功能

- **集合操作**: `map`, `filter`, `reduce`, `flat_map`, `group_by`
- **数学运算**: `add`, `sub`, `mul`, `div`, `pow`, `sqrt`
- **字符串操作**: `upper`, `lower`, `strip`, `replace`, `split`
- **谓词函数**: `is_true`, `is_false`, `is_none`, `is_not_none`, `is_in`
- **迭代操作**: `take`, `drop`, `take_while`, `drop_while`

## 核心函数

| 名称 | 说明 | 示例 |
|------|------|------|
| `map(fn)` | 映射 | `map(_ + 1)` |
| `filter(pred)` | 过滤 | `filter(lambda x: x > 0)` |
| `reduce(fn)` | 归约 | `reduce(lambda a, b: a + b)` |
| `add(a)` | 加法 | `add(2)(3)` → 5 |
| `mul(a)` | 乘法 | `mul(2)(3)` → 6 |

## 使用示例

```python
from vools.curried import map, filter, reduce, add, mul

# 柯里化 map
double_all = map(lambda x: x * 2)
result = list(double_all([1, 2, 3]))  # [2, 4, 6]

# 柯里化 filter
evens = filter(lambda x: x % 2 == 0)
result = list(evens([1, 2, 3, 4]))  # [2, 4]

# 柯里化 reduce
sum_all = reduce(lambda a, b: a + b)
result = sum_all([1, 2, 3])  # 6

# 柯里化数学运算
add5 = add(5)
result = add5(3)  # 8

mul10 = mul(10)
result = mul10(5)  # 50
```

## 注意事项

- 所有函数均已柯里化，支持部分应用