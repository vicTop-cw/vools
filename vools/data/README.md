# vools.data

数据处理模块，提供序列处理工具 `Seq`。

## 主要功能

- **Seq**: 链式序列处理类，支持惰性求值
- 支持 map、filter、reduce、group_by 等操作
- 支持与 Python 内置类型互操作

## 核心类

| 名称 | 说明 |
|------|------|
| `Seq` | 链式序列处理类 |

## 使用示例

```python
from vools.data import Seq

# 基本用法
result = (Seq([1, 2, 3, 4, 5])
          .filter(lambda x: x % 2 == 0)
          .map(lambda x: x * 2)
          .to_list())  # [4, 8]

# 分组
result = Seq([1, 2, 3, 4, 5]).group_by(lambda x: x % 2)

# 聚合
result = Seq([1, 2, 3]).sum()  # 6
```

## 注意事项

- Seq 支持惰性求值，只有调用终端方法时才执行
- 支持 NONE 占位符处理（通过配置 `NONE_is_None`）