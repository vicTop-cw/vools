# 类融合器 (Class Fusion) 使用指南

## 概述

`class_fusion.py` 提供了一个类级别的融合功能，可以将多个类融合生成新类，并支持方法重写、方法包装和返回类型自动转换。

## 核心功能

1. **多类融合**：融合任意多个类生成新类
2. **方法重写**：通过 `method_overrides` 参数重写指定方法
3. **方法包装**：通过 `method_wrappers` 参数包装指定方法（添加 `before`/`after` 逻辑）
4. **返回类型自动转换**：当方法返回父类实例时，自动转换为融合类实例（可选）
5. **面向对象接口**：通过 `ClassFusion` 类提供更灵活的融合功能

## 快速开始

### 示例 1：基本融合

```python
from Temp.class_fusion import fuse_classes

class A:
    def __init__(self, x=0, **kwargs):
        self.x = x
    
    def foo(self):
        return f"A.foo (x={self.x})"

class B:
    def __init__(self, y=0, **kwargs):
        self.y = y
    
    def bar(self):
        return f"B.bar (y={self.y})"

# 融合 A 和 B
AB = fuse_classes(A, B, name="AB")

# 创建实例
obj = AB(x=10, y=20)

# 调用方法
print(obj.foo())  # 输出: A.foo (x=10)
print(obj.bar())  # 输出: B.bar (y=20)
```

### 示例 2：方法重写

```python
def new_foo(self):
    return f"overridden foo (x={self.x})"

AB_override = fuse_classes(
    A, B,
    name="ABOverride",
    method_overrides={'foo': new_foo}
)

obj = AB_override(x=100, y=200)
print(obj.foo())  # 输出: overridden foo (x=100)
```

### 示例 3：方法包装器

```python
def before_foo(self, *args, **kwargs):
    print(f"  [before] x={self.x}")

def after_foo(self, result):
    return f"[wrapped] {result}"

AB_wrapped = fuse_classes(
    A, B,
    name="ABWrapped",
    method_wrappers={'foo': {'before': before_foo, 'after': after_foo}}
)

obj = AB_wrapped(x=50, y=60)
print(obj.foo())  # 输出:
                      #   [before] x=50
                      #   [wrapped] A.foo (x=50)
```

### 示例 4：使用 ClassFusion（面向对象接口）

```python
from Temp.class_fusion import ClassFusion

fusion = ClassFusion(A, B)

# 重写方法
def my_foo(self):
    return f"my_foo (x={self.x}, y={self.y})"
fusion.override_method('foo', my_foo)

# 包装方法
def before_bar(self, *args, **kwargs):
    print(f"  [before_bar] y={self.y}")

fusion.wrap_method('bar', before=before_bar)

# 执行融合
AB_fusion = fusion.fuse()

# 创建实例
obj = AB_fusion(x=11, y=22)
print(obj.foo())  # 输出: my_foo (x=11, y=22)
print(obj.bar())  # 输出:
                      #   [before_bar] y=22
                      #   B.bar (y=22)
```

## 高级功能

### 返回类型自动转换

当启用 `auto_wrap_return=True` 时，如果方法返回值是任何父类的实例，则自动转换为融合类实例。

```python
class Parent:
    def get_parent(self):
        return Parent()

class Child:
    def __init__(self):
        self.name = "Child"

ParentChild = fuse_classes(
    Parent, Child,
    name="ParentChild",
    auto_wrap_return=True
)

obj = ParentChild()
result = obj.get_parent()

print(type(result))  # 输出: <class '__main__.ParentChild'>
print(isinstance(result, ParentChild))  # 输出: True
```

## 限制和注意事项

1. **不可变类型支持有限**：当前版本对 `str`、`int`、`tuple` 等不可变类型的支持有限。实例属性可能会丢失。
2. **`@rself` 装饰器暂时禁用**：`@rself` 装饰器可能有 bug，暂时被禁用。
3. **方法优先级**：如果多个父类有同名方法，后面类的方法会覆盖前面类的方法（类似 MRO）。
4. **参数传递**：所有父类的 `__init__` 会依次被调用，并传递相同的 `*args, **kwargs`。如果参数不匹配，会尝试无参调用。

## API 参考

### `fuse_classes(*classes, name=None, method_overrides=None, method_wrappers=None, auto_wrap_return=False) -> Type`

融合多个类生成新类。

**参数：**
- `*classes`：要融合的类（至少一个）
- `name`：新类的名称（可选，默认为 `Fused` + 所有类名拼接）
- `method_overrides`：方法重写字典 `{方法名: 新方法}`
- `method_wrappers`：方法包装器字典 `{方法名: {'before': fn, 'after': fn, 'replace': fn}}`
- `auto_wrap_return`：是否自动包装返回类型（默认 `False`）

**返回：**
- 融合后的新类

### `ClassFusion(*classes) -> ClassFusion`

类融合器（面向对象接口）。

**方法：**
- `add_class(cls)`：添加要融合的类
- `override_method(name, impl)`：重写方法
- `wrap_method(name, before=None, after=None, replace=None)`：包装方法
- `set_name(name)`：设置融合类的名称
- `set_auto_wrap_return(enabled)`：设置是否自动包装返回类型
- `fuse()`：执行融合，返回融合后的类
- `__call__(*args, **kwargs)`：创建融合类的实例（语法糖）

## 测试

运行测试脚本：

```bash
cd E:\IDEProjects\AI\vools
python Temp/test_class_fusion.py
```

## 实现细节

### 设计思路

1. **基类选择**：使用 `object` 作为融合类的基类，避免 MRO 冲突
2. **方法复制**：将所有父类的方法复制到融合类中（而不是通过 `__getattr__` 委托）
3. **`__init__` 调用**：依次调用所有父类的 `__init__`，并传递相同的参数
4. **闭包处理**：使用 `create_wrapper` 函数创建包装方法，避免闭包捕获循环变量

### 关键函数

- `_copy_methods_from_parents`：将所有父类的方法复制到融合类
- `_apply_method_wrapper`：为指定方法应用包装器
- `_wrap_methods_for_return_type`：包装类的方法，自动转换返回类型
- `_apply_rself_if_available`：尝试为类应用 `@rself` 装饰器（暂时禁用）

## 后续改进

1. **正确处理不可变类型**：在 `__new__` 中存储额外属性
2. **启用 `@rself` 装饰器**：修复 `@rself` 的 bug
3. **更好的错误处理**：当参数不匹配时，提供更清晰的错误消息
4. **性能优化**：缓存融合结果，避免重复创建相同的融合类

## 作者

Victo（吴八哥）

## 日期

2026-06-19
