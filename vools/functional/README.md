# vools.functional

函数式编程工具模块，提供占位符、箭头函数、管道操作等工具。

## 主要功能

- **占位符**: `_`, `_1`, `_2`, `_3` - 用于匿名函数
- **箭头函数**: `g()` - 将字符串表达式转换为函数
- **管道操作**: `Pipe`, `Ops`, `P` - 链式函数组合
- **条件表达式**: `iif` - 函数式条件判断
- **工具箱**: `Box`, `result` - 数据包装与处理

## 核心工具

| 名称 | 说明 | 示例 |
|------|------|------|
| `_`, `_1`, `_2` | 占位符 | `map(_ + 1, [1, 2, 3])` |
| `g()` | 箭头函数 | `g("_ * 2")` |
| `iif()` | 条件表达式 | `iif(cond, true_fn, false_fn)` |
| `Pipe` | 管道类 | `Pipe(5).map(_ * 2)` |

## 使用示例

```python
from vools.functional import _, _1, g, iif, Pipe

# 占位符
result = list(map(_ + 1, [1, 2, 3]))  # [2, 3, 4]

# 箭头函数
double = g("_ * 2")
result = double(5)  # 10

# 条件表达式
value = iif(x > 0, lambda: "positive", lambda: "negative")

# 管道操作
result = Pipe(5).map(_ * 2).map(_ + 1)  # 11
```

## 注意事项

- 占位符 `_` 与 Python 内置 `_` 可能冲突，注意使用场景