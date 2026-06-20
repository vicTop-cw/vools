# vools.oop

面向对象工具模块，提供 Mixin、Selector 和类型处理功能。

## 主要功能

- **Mixin**: `Mixer` - 动态 Mixin 组合
- **Selector**: 属性选择器
- **类型处理**: `calltype` - 调用类型检测
- **扩展**: `extend` - 类扩展

## 核心类

| 名称 | 说明 |
|------|------|
| `Mixer` | Mixin 组合器 |
| `Selector` | 属性选择器 |
| `calltype` | 调用类型检测 |

## 使用示例

```python
from vools.oop import Mixer, Selector, calltype

# Mixin
class HasName:
    def get_name(self):
        return self.name

class HasAge:
    def get_age(self):
        return self.age

class Person(Mixer(HasName, HasAge)):
    def __init__(self, name, age):
        self.name = name
        self.age = age

# Selector
selector = Selector('name')
result = selector({'name': 'Alice', 'age': 30})  # 'Alice'

# calltype
result = calltype(lambda x: x)  # 返回调用类型
```

## 注意事项

- `Mixer` 支持多个 Mixin 类的组合