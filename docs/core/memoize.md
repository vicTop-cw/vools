# 缓存装饰器

> **模块路径**：`vools.cache`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#008
> **最后更新**：2026-06-30

## 概述

vools 提供多种缓存装饰器，支持内存缓存和持久化缓存，满足不同的缓存需求。

## 导入方式

```python
from vools import memorize, once, persist
from vools.cache import TimedCache, _CACHE
```

## @memorize - 函数结果内存缓存

### 基本用法

```python
# test_memorize_basic.py
from vools import memorize
import time

@memorize(duration=5)
def expensive_computation(n):
    """模拟耗时计算"""
    print(f"正在计算 {n}...")
    return n * n

# 第一次调用 - 会执行计算
start = time.time()
result1 = expensive_computation(4)
elapsed1 = time.time() - start
print(f"第一次调用: 结果={result1}, 耗时={elapsed1:.4f}秒")

# 第二次调用 - 使用缓存，立即返回
start = time.time()
result2 = expensive_computation(4)
elapsed2 = time.time() - start
print(f"第二次调用: 结果={result2}, 耗时={elapsed2:.4f}秒")

# 第三次调用 - 不同参数，执行计算
result3 = expensive_computation(5)
print(f"第三次调用: 结果={result3}")
```

**输出示例**：
```
正在计算 4...
第一次调用: 结果=16, 耗时=0.0001234秒
第二次调用: 结果=16, 耗时=0.0000012秒
正在计算 5...
第三次调用: 结果=25, 耗时=0.0001100秒
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `func` | Callable | None | 要缓存的函数 |
| `duration` | float | 3 | 缓存有效期（秒） |

### 使用场景

```python
# test_memorize_scenario.py
from vools import memorize
import requests

@memorize(duration=60)  # 缓存1分钟
def fetch_user_data(user_id):
    """获取用户数据 - 假设是耗时操作"""
    print(f"请求用户 {user_id} 数据...")
    return {"id": user_id, "name": f"User{user_id}"}

# 第一次调用
data1 = fetch_user_data(123)
print(f"获取用户: {data1}")

# 第二次调用 - 使用缓存
data2 = fetch_user_data(123)
print(f"获取用户: {data2}")
```

## @persist - 函数结果持久化缓存

将函数执行结果缓存到本地 JSON 文件。

### 基本用法

```python
# test_persist_basic.py
from vools import persist
import os

@persist
def get_config():
    """获取配置 - 假设是耗时操作"""
    print("加载配置...")
    return {"debug": True, "port": 8080}

# 第一次调用 - 执行函数并保存缓存
result1 = get_config()
print(f"配置: {result1}")

# 第二次调用 - 从缓存读取
result2 = get_config()
print(f"配置: {result2}")

# 查看缓存文件
print(f"缓存目录: {os.path.join(os.path.dirname(os.path.abspath(__file__)), '__persist__')}")
```

### 自定义缓存文件名

```python
# test_persist_filename.py
from vools import persist

@persist(file_key="my_custom_cache")
def fetch_data():
    """使用自定义缓存文件名"""
    print("执行 fetch_data...")
    return {"data": "value", "count": 42}

result = fetch_data()
print(f"结果: {result}")
# 缓存文件保存为: __persist__/my_custom_cache.json
```

### 指定缓存目录

```python
# test_persist_folder.py
from vools import persist
import os
import tempfile

# 使用临时目录作为缓存
cache_dir = tempfile.mkdtemp()

@persist(file_key="temp_data", target_folder=cache_dir)
def compute_once():
    """在指定目录缓存"""
    print("执行 compute_once...")
    return {"computed": True}

result = compute_once()
print(f"结果: {result}")
print(f"缓存路径: {os.path.join(cache_dir, 'temp_data.json')}")
```

### 强制刷新

```python
# test_persist_force.py
from vools import persist

counter = 0

@persist
def get_counter():
    """带计数器的函数"""
    global counter
    counter += 1
    return {"counter": counter, "time": __import__('time').time()}

# 第一次调用
result1 = get_counter()
print(f"第一次: {result1}")

# 第二次调用 - 使用缓存
result2 = get_counter()
print(f"第二次: {result2}")

# 强制刷新 - 忽略缓存
result3 = get_counter(force=True)
print(f"强制刷新: {result3}")
```

### 条件刷新 (force_when)

```python
# test_persist_force_when.py
from vools import persist
import time

@persist(force_when=lambda result, start, end: time.time() - end > 2)
def get_time_data():
    """缓存超过2秒则刷新"""
    return {"timestamp": time.time(), "value": "data"}

# 第一次调用
result1 = get_time_data()
print(f"结果1: {result1}")

# 等待3秒
print("等待3秒...")
time.sleep(3)

# 第三次调用 - 缓存已过期，强制刷新
result2 = get_time_data()
print(f"结果2: {result2}")
```

### persist 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `func` | Callable | None | 要缓存的函数 |
| `file_key` | str | 函数名 | 缓存文件名（不含扩展名） |
| `force` | bool | False | 是否强制重新执行 |
| `force_when` | Callable | 每天刷新 | 条件刷新函数 |
| `target_folder` | str | `__persist__` | 缓存文件目录 |

### force_when 函数签名

```python
def force_when(result: Any, start_time: float, end_time: float) -> bool:
    """
    参数:
        result: 缓存的函数返回值
        start_time: 上次执行的开始时间戳
        end_time: 上次执行的结束时间戳
    
    返回:
        True - 需要刷新缓存
        False - 使用现有缓存
    """
```

## @once - 单次执行装饰器

确保函数在整个程序生命周期内只执行一次。

### 基本用法

```python
# test_once_basic.py
from vools import once

call_count = 0

@once
def initialize():
    """初始化函数 - 只执行一次"""
    global call_count
    call_count += 1
    print("执行初始化...")
    return True

# 多次调用
result1 = initialize()
print(f"结果1: {result1}")

result2 = initialize()
print(f"结果2: {result2}")

result3 = initialize()
print(f"结果3: {result3}")

print(f"实际调用次数: {call_count}")
```

**输出**：
```
执行初始化...
结果1: True
结果2: True
结果3: True
实际调用次数: 1
```

### 使用场景

```python
# test_once_scenario.py
from vools import once
import threading

_connection = None

@once
def get_database_connection():
    """获取数据库连接 - 只建立一次"""
    print("建立数据库连接...")
    return {"connected": True, "pool_size": 10}

def query(sql):
    """查询函数"""
    conn = get_database_connection()
    print(f"执行查询: {sql}")
    return f"结果: {sql}"

# 多线程环境
threads = []
for i in range(5):
    t = threading.Thread(target=query, args=(f"SELECT {i}",))
    threads.append(t)

for t in threads:
    t.start()

for t in threads:
    t.join()
```

## TimedCache - 线程安全缓存类

### 基本用法

```python
# test_timed_cache.py
from vools.cache import TimedCache
import time

cache = TimedCache(max_size=100)

# 设置缓存
cache.set("key1", "value1")
cache.set("key2", "value2")

# 获取缓存
result = cache.get("key1", duration=5)  # 5秒内有效
print(f"获取 key1: {result}")  # 输出: 获取 key1: value1

# 等待过期
time.sleep(6)

# 获取过期缓存
result = cache.get("key1", duration=5)
print(f"获取过期 key1: {result}")  # 输出: 获取过期 key1: None

# 清空缓存
cache.clear()
print(f"缓存条目数: {len(cache)}")  # 输出: 缓存条目数: 0
```

### TimedCache 方法

| 方法 | 说明 |
|------|------|
| `get(key, duration)` | 获取缓存值，过期返回 None |
| `set(key, value)` | 设置缓存值 |
| `clear()` | 清空所有缓存 |
| `__len__()` | 返回缓存条目数 |

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_size` | int | 1000 | 缓存最大条目数 |

## 全局缓存实例

```python
# test_global_cache.py
from vools.cache import _CACHE

# 直接操作全局缓存
_CACHE.set("global_key", {"data": "value"})

result = _CACHE.get("global_key", duration=60)
print(f"全局缓存: {result}")

print(f"全局缓存大小: {len(_CACHE)}")
```

## 缓存最佳实践

### 1. 选择合适的缓存时长

```python
# 选择缓存时长
@memorize(duration=60)      # 快速变化的数据 - 1分钟
@memorize(duration=300)     # 中等变化 - 5分钟
@memorize(duration=3600)    # 缓慢变化 - 1小时
@memorize(duration=-1)      # 永久缓存（需要其他机制清理）
```

### 2. 缓存键设计

```python
# 使用函数签名作为缓存键
@memorize
def complex_operation(a, b, c):
    """参数自动作为缓存键的一部分"""
    return (a + b) * c
```

### 3. 缓存与刷新策略

```python
# 组合使用缓存和强制刷新
@persist(file_key="important_data", force_when=lambda r, s, e: is_stale(r))
def get_important_data():
    return fetch_data()
```

## 注意事项

1. **线程安全**：`TimedCache` 是线程安全的
2. **JSON 序列化**：`persist` 要求返回值可 JSON 序列化
3. **缓存失效**：时间过期或达到最大容量时自动失效
4. **文件锁**：`persist` 使用跨平台文件锁防止并发写入冲突

## 相关文档

- [装饰器总览](./decorators.md)
- [TimedCache 详细API](../api/timed_cache.md)
