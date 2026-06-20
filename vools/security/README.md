# vools.security

安全模块，提供安全评估和表达式处理功能。

## 主要功能

- **安全评估**: `safe_eval` - 安全的表达式求值
- **表达式处理**: `ExpressionHandler` - 表达式处理器

## 核心功能

| 名称 | 说明 |
|------|------|
| `safe_eval` | 安全表达式求值 |
| `ExpressionHandler` | 表达式处理器 |

## 使用示例

```python
from vools.security import safe_eval

# 安全求值
result = safe_eval('1 + 2')  # 3

# 支持变量
result = safe_eval('x + y', {'x': 1, 'y': 2})  # 3
```

## 注意事项

- 禁止执行危险操作（文件读写、系统命令等）