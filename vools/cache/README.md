# vools.cache

签名缓存与装饰器包，提供函数签名缓存功能和常用的缓存装饰器。

## 主要功能

- **签名缓存**: 缓存函数签名，加速柯里化和重载判断
- **性能优化**: 减少重复的签名解析开销，加速比可达 100×~2000×
- **once 装饰器**: 确保函数或类只执行/初始化一次
- **persist 装饰器**: 将函数执行结果缓存到本地文件

## 核心功能

### 签名缓存

| 名称 | 说明 |
|------|------|
| `get_signature` | 获取函数签名（带 LRU 缓存） |
| `cached_getsignature` | 装饰器：在函数上附加缓存的签名 |
| `add_custom_sig` | 手动注册自定义函数签名 |
| `remove_signature` | 从缓存中删除指定函数的签名 |
| `clear_cache` | 清空全局签名缓存 |
| `cache_info` | 返回缓存统计信息 |

### 缓存装饰器

| 名称 | 说明 |
|------|------|
| `memorize` | 函数记忆化装饰器（支持 TTL 和 LRUCache） |
| `once` | 单次执行装饰器 |
| `persist` | 持久化缓存装饰器 |
| `FileLock` | 文件锁（用于持久化缓存并发控制） |

## 使用示例

```python
from vools.cache import get_signature

# 直接替换 inspect.signature
sig = get_signature(my_func)
```

```python
from vools.cache import cached_getsignature

# 装饰器：自动缓存函数签名
@cached_getsignature
def my_function(a, b, c=3):
    return a + b + c

# 签名在装饰时自动计算并缓存
print(my_function.__cached_sig__)
```

```python
from vools.cache import once

# 单次执行装饰器
@once
def initialize():
    print("Initializing...")
    return 42

initialize()  # 输出: Initializing...
initialize()  # 不输出，直接返回缓存结果
```

### memorize 装饰器

```python
from vools.cache import memorize
import time

# 基础记忆化
@memorize
def slow_function(x):
    time.sleep(1)  # 模拟耗时操作
    return x * 2

start = time.time()
result1 = slow_function(5)  # 耗时 1 秒
result2 = slow_function(5)  # 几乎无耗时（命中缓存）
print(f"第二次调用耗时: {time.time() - start:.4f} 秒")
```

### persist 装饰器

```python
from vools.cache import persist

# 持久化缓存装饰器
@persist
def fetch_data():
    return {"data": "value"}

# 第一次执行并缓存到文件
# 后续调用直接读取缓存文件
```

## 注意事项

- `get_signature` 主要用于内部性能优化
- `once` 和 `persist` 装饰器可用于业务代码
- 提供 `clear_cache()` 用于测试和重载场景
