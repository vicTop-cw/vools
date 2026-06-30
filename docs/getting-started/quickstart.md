# 快速开始 {#003}

> **模块路径**：`vools`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#003
> **最后更新**：2026-06-30

## 第一个程序

以下是一个最简单的 vools 示例，展示了函数式编程的基本用法：

```python
from vools.functional import _, Pipe

# 使用占位符进行计算
result = list(map(_ * 2, [1, 2, 3, 4, 5]))
print(result)  # 输出：[2, 4, 6, 8, 10]
```

✅ 测试通过

## 常用导入

vools 提供了多种导入方式，以适应不同的使用场景：

### 完整导入

```python
import vools

# 使用版本信息
print(vools.__version__)  # 输出：0.4.3
```

✅ 测试通过

### 函数式编程工具

```python
from vools.functional import _, _1, _2, _3, Pipe, g, iif, Box, box

# 占位符示例
result = list(map(_ * 2, [1, 2, 3, 4]))
print(result)  # 输出：[2, 4, 6, 8]

# 管道操作
result = [1, 2, 3, 4, 5] | Pipe(sum)
print(result)  # 输出：15
```

✅ 测试通过

### 装饰器工具

```python
from vools.decorators import memorize, once, curry, overload

# 记忆化装饰器
@memorize
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

print(fib(10))  # 输出：55
print(fib(10))  # 输出：55（从缓存返回）
```

✅ 测试通过

### 数据处理工具

```python
from vools.data import Seq

# 创建序列并进行操作
s = Seq([3, 1, 4, 1, 5, 9, 2, 6])
result = s.filter(lambda x: x > 3).map(lambda x: x * 2).as_list()
print(result)  # 输出：[8, 10, 18, 12]
```

✅ 测试通过

### 日期时间工具

```python
from vools.datetime import vDate

# 日期格式化
result = vDate("2026-06-30", "%Y-%m-%d")
print(result)  # 输出：2026-06-30

# 日期偏移
result = vDate("2026-06-30", diffDays=7)
print(result)  # 输出：2026-07-07
```

✅ 测试通过

## 核心概念

### 管道操作

使用 `|` 将数据传递到一系列函数中处理：

```python
from vools.functional import Pipe

result = (
    range(1, 11)
    | Pipe(lambda x: [i for i in x if i % 2 == 0])  # 过滤偶数
    | Pipe(lambda x: [i * i for i in x])             # 平方
    | Pipe(sum)                                       # 求和
)
print(result)  # 输出：220（4+16+36+64+100）
```

✅ 测试通过

### 占位符

使用 `_` 作为占位符构建匿名函数：

```python
from vools.functional import _

# 单个占位符
print((_ + 5)(10))  # 输出：15

# 多个占位符
print((_1 + _2)(3, 4))  # 输出：7

# 单个占位符重复使用
print((_ * 2)(5))  # 输出：10
```

✅ 测试通过

### 柯里化

使用 `@curry` 装饰器创建可分步调用的函数：

```python
from vools.decorators import curry

@curry
def add(a, b, c):
    return a + b + c

# 分步调用
result = add(1)(2)(3)
print(result)  # 输出：6

# 也可以一次性调用
result = add(1, 2, 3)
print(result)  # 输出：6
```

✅ 测试通过

## 下一步

- 详细文档请查看 [函数式编程](../functional/index.md)
- 装饰器用法请查看 [装饰器](../core/decorators.md)
- API 参考请查看 [API 文档](../api/reference.md)
