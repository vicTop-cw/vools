# vools.utils

工具模块，提供通用工具函数和类。

## 主要功能

- **工具类**: `Stuff`, `Hoder` - 通用工具类
- **工具函数**: `identity`, `const`, `compose`, `pipe`
- **数据结构**: `IndexedDict` - 可索引字典

## 核心功能

| 名称 | 说明 |
|------|------|
| `Stuff` | 通用工具类，包含多种便捷方法 |
| `Hoder` | 值持有器 |
| `identity` | 恒等函数 |
| `const` | 常量函数 |
| `compose` | 函数组合 |
| `pipe` | 管道函数 |
| `IndexedDict` | 可索引字典 |

## 使用示例

```python
from vools.utils import Stuff, identity, compose, pipe

# Stuff 工具类
stuff = Stuff()
result = stuff.is_number(42)

# 恒等函数
result = identity(42)  # 42

# 函数组合
f = compose(lambda x: x + 1, lambda x: x * 2)
result = f(3)  # 7

# 管道函数
result = pipe(3, lambda x: x * 2, lambda x: x + 1)  # 7
```

## 注意事项

- `Stuff` 包含大量便捷方法，按需使用