# vools.utils

工具模块，提供通用工具函数和类。

## 主要功能

- **工具类**: `Stuff` - 延迟调用执行框架；`StuffConfig` - 配置类；`Hoder` - 值持有器
- **工具函数**: `identity`, `const`, `compose`, `pipe`
- **数据结构**: `IndexedDict` - 可索引字典

## 核心功能

| 名称 | 说明 |
|------|------|
| `Stuff` | 延迟调用执行框架，基于柯里化实现参数依赖注入 |
| `StuffConfig` | Stuff 配置类（cache_duration / max_workers / debug / strict） |
| `IndexedDict` | 支持整数/字符串双索引的有序字典 |
| `Hoder` | 值持有器 |
| `identity` | 恒等函数 |
| `const` | 常量函数 |
| `compose` | 函数组合（从右到左） |
| `pipe` | 管道函数（从左到右） |

## Stuff API 文档

### 装饰器

```python
from vools import stuff

@stuff
def add(a, b, c):
    return a + b + c

# 逐步提供参数
result = add(1)(2)(3)()  # 6

# 一次性提供
result = add(1, 2, 3)()  # 6
```

### 配置类 StuffConfig

```python
from vools.utils.stuff import StuffConfig, stuff

config = StuffConfig(
    cache_duration=5,    # 提供者结果缓存秒数（默认 3）
    max_workers=4,       # 并行执行线程数（默认 None=自动）
    debug=True,          # 调试模式（默认 False）
    strict=False,        # 严格参数验证（默认 True）
)

@stuff(config=config)
def process(a, b, c):
    return a + b + c
```

### reset() — 重置绑定

```python
@stuff
def add(a, b, c):
    return a + b + c

add.provide(lambda: 1, for_param='a')
add.provide(lambda: 2, for_param='b')
print(add())  # TypeError: missing c

add.reset()  # 清空所有绑定
add(1, 2, 3)()  # 6
```

### provide — 注册参数提供者

```python
@stuff
def multiply(a, b, c):
    return a * b * c

@multiply.provide                    # 提供1个位置参数
def get_a():
    return 2

@multiply.provide(for_param='a')     # 提供关键字参数 a
def get_a_v2():
    return 2

@multiply.provide(for_param=['b','c'])  # 提供多个关键字参数
def get_bc():
    return 3, 4

@multiply.provide(for_param=2)       # 提供2个位置参数
def get_two():
    return 3, 4
```

### provide_with — 注册 + 内联参数

```python
@stuff
def greet(greeting, name, punctuation):
    return f"{greeting}, {name}{punctuation}"

@greet.provide_with(for_param='name')
def get_name():
    return "World"

greet.provide_with(lambda: "Hello", for_param='greeting')
greet.provide_with(lambda: "!", for_param='punctuation')
print(greet())  # "Hello, World!"
```

### provide_multi_params — 一个函数提供多个参数

```python
@stuff
def calculate(price, quantity, tax_rate):
    return price * quantity * (1 + tax_rate)

# 前 1 个返回值(before discount)是位置参数，后 2 个是关键字参数
calculate.provide_multi_params(
    lambda: (100, 2, 0.1),
    pos_count=1,
    for_params=['quantity', 'tax_rate'],
)
print(calculate())  # 100 * 2 * 1.1 = 220.0
```

### aggregate_providers — 多个函数聚合提供同一参数

```python
@stuff
def sum_all(numbers):
    return sum(numbers)

sum_all.aggregate_providers(
    lambda: 1,
    lambda: 2,
    lambda: 3,
    for_param='numbers',
)
print(sum_all())  # 6
```

## 使用示例

### 配置管理系统

```python
@stuff
def create_app(db_url, redis_url, debug_mode):
    return Application(db_url, redis_url, debug_mode)

create_app.fill_multi(get_db_config, get_redis_config, get_debug_config)
```

### 数据处理流水线

```python
@stuff
def data_pipeline(extract, transform, load):
    data = extract()
    transformed = transform(data)
    return load(transformed)

pipeline = data_pipeline(
    extract_func=read_csv,
    transform_func=clean_data,
    load_func=write_to_db,
)
```

## 注意事项

- `@stuff` 装饰的函数必须无参调用 `()` 触发最终执行
- 提供者函数必须是无参的，或所有参数都有默认值
- 不支持内置函数和 C 扩展函数（无法获取签名）
- 非线程安全，多线程环境需要额外同步
