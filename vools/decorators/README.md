# vools.decorators

装饰器模块，提供丰富的函数装饰器，包括缓存、重试、柯里化、重载等。

## 主要功能

- **缓存装饰器**: `memorize`, `once`, `persist`
- **控制装饰器**: `retry`, `repeat`, `rerun`, `lazy`
- **柯里化装饰器**: `curry`, `curry_class`, `delay_curry`
- **重载装饰器**: `overload`, `overcurry`
- **其他装饰器**: `rself`, `singleton`, `throttle`, `debounce`, `validate`

## 核心装饰器

| 名称 | 说明 | 示例 |
|------|------|------|
| `@curry` | 柯里化函数 | `@curry def add(a, b): return a + b` |
| `@overload` | 函数重载 | `@overload def fn(x: int): ...` |
| `@retry` | 失败重试 | `@retry(tries=3)` |
| `@memorize` | 结果缓存 | `@memorize(duration=300)` |
| `@throttle` | 节流 | `@throttle(seconds=1)` |
| `@debounce` | 防抖 | `@debounce(seconds=0.5)` |

## 使用示例

```python
from vools.decorators import curry, retry, memorize

@curry
def add(a, b):
    return a + b

@retry(tries=3, delay=1)
def fetch_data(url):
    return requests.get(url)

@memorize(duration=300)
def expensive_computation(x):
    return x ** 1000
```

## 注意事项

- 所有装饰器支持 `@decorator` 和 `@decorator(params)` 两种调用方式
- 弃用的装饰器（`overloads`, `curried`）会发出警告