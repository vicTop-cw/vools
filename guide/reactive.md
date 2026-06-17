# vools 响应式编程

vools.reactive 是一个功能完整的响应式编程框架，实现了 Rx 4.0 规范的所有 98 个操作符。

---

## 模块结构

vools.reactive 采用模块化设计，分为三个子包：

```
vools/reactive/
├── core/          # 基础核心：Observable、Subject、Scheduler、Connectable
├── monitoring/    # 监控类：键盘、鼠标、剪贴板、文件系统、目录监控
└── operators/     # 操作符：核心操作符、统计操作符、监控操作符
```

所有符号通过 `vools.reactive` 统一导出，保持 API 兼容性。

## reactive 模块

### 基本用法

```python
from vools.reactive import Observable, ops

# 创建 Observable
obs = Observable.from_iterable([1, 2, 3])

# 订阅
obs.subscribe(
    on_next=lambda x: print(f"Next: {x}"),
    on_error=lambda e: print(f"Error: {e}"),
    on_completed=lambda: print("Completed")
)

# 使用管道操作
obs.pipe(
    ops.filter(lambda x: x > 1),
    ops.map(lambda x: x * 2)
).subscribe(on_next=print)  # 4, 6
```

### 创建操作符

```python
from vools.reactive import Observable

# 从可迭代对象创建
obs = Observable.from_iterable([1, 2, 3])

# 创建单个值
obs = Observable.just(42)
obs = Observable.of(1, 2, 3)

# 创建空序列
obs = Observable.empty()

# 创建无限序列
obs = Observable.interval(1.0)  # 每秒发射一个值
obs = Observable.timer(0.5, 1.0)  # 0.5秒后开始，每秒发射

# 延迟创建
obs = Observable.defer(lambda: Observable.just(42))
```

### 转换操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable([1, 2, 3])

# map - 映射
obs.pipe(ops.map(lambda x: x * 2)).subscribe(print)  # 2, 4, 6

# flat_map - 扁平化映射
obs.pipe(
    ops.flat_map(lambda x: Observable.from_iterable([x, x*10]))
).subscribe(print)  # 1, 10, 2, 20, 3, 30

# scan - 累积扫描
obs.pipe(ops.scan(lambda acc, x: acc + x, 0)).subscribe(print)  # 1, 3, 6
```

### 过滤操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable(range(10))

# filter - 过滤
obs.pipe(ops.filter(lambda x: x % 2 == 0)).subscribe(print)  # 0, 2, 4, 6, 8

# take - 取前N个
obs.pipe(ops.take(3)).subscribe(print)  # 0, 1, 2

# skip - 跳过前N个
obs.pipe(ops.skip(5)).subscribe(print)  # 5, 6, 7, 8, 9

# distinct - 去重
obs = Observable.from_iterable([1, 2, 2, 3, 3, 3])
obs.pipe(ops.distinct()).subscribe(print)  # 1, 2, 3
```

### 组合操作符

```python
from vools.reactive import Observable, ops

obs1 = Observable.from_iterable([1, 2, 3])
obs2 = Observable.from_iterable(['a', 'b', 'c'])

# zip - 拉链组合
Observable.zip(obs1, obs2).subscribe(print)  # (1, 'a'), (2, 'b'), (3, 'c')

# combine_latest - 组合最新值
obs1.pipe(ops.combine_latest(obs2)).subscribe(print)

# merge - 合并
Observable.merge(obs1, obs2).subscribe(print)  # 1, 'a', 2, 'b', 3, 'c'
```

### Subject

```python
from vools.reactive import Subject, BehaviorSubject, ReplaySubject

# Subject - 基础主题
subject = Subject()
subject.subscribe(on_next=print)
subject.on_next(1)  # 1
subject.on_next(2)  # 2

# BehaviorSubject - 保留最新值
subject = BehaviorSubject(0)  # 默认值
subject.subscribe(on_next=print)  # 立即收到 0
subject.on_next(1)  # 1

# ReplaySubject - 重放历史值
subject = ReplaySubject(2)  # 保留最近2个值
subject.on_next(1)
subject.on_next(2)
subject.on_next(3)
subject.subscribe(on_next=print)  # 2, 3
```

### 调度器

```python
from vools.reactive import Observable, schedulers, ops

# 使用调度器
obs = Observable.interval(0.1)

# 在不同线程执行
obs.pipe(
    ops.observe_on(schedulers.ThreadPoolScheduler())
).subscribe(on_next=print)

# 使用 asyncio 调度器
obs.pipe(
    ops.subscribe_on(schedulers.AsyncIOScheduler())
).subscribe(on_next=print)
```

### 错误处理

```python
from vools.reactive import Observable, ops

# catch - 捕获错误
Observable.throw(Exception("error")).pipe(
    ops.catch(lambda e: Observable.just("recovered"))
).subscribe(
    on_next=print,
    on_error=lambda e: print(f"Error: {e}")
)  # "recovered"

# retry - 重试
Observable.throw(Exception("error")).pipe(
    ops.retry(3)
).subscribe(
    on_next=print,
    on_error=lambda e: print(f"Failed after 3 retries")
)

# on_error_return - 错误时返回默认值
Observable.throw(Exception("error")).pipe(
    ops.on_error_return("default")
).subscribe(print)  # "default"
```

### 创新功能

vools.reactive 提供了一些独特的创新功能：

```python
from vools.reactive import Observable, ops

# placeholder 表达式支持
Observable.from_iterable([1, 2, 3]).pipe(
    ops.filter("_ > 1"),
    ops.map("x * 2")
).subscribe(print)  # 4, 6

# >> 管道操作符
result = Observable.from_iterable([1, 2, 3]) >> ops.filter(lambda x: x > 1) >> ops.map(lambda x: x * 2)

# p() 链式调用
Observable.from_iterable([1, 2, 3]).p() \
    .filter(lambda x: x > 1) \
    .map(lambda x: x * 2) \
    .subscribe(print)

# Subscription 上下文管理器
with Observable.from_iterable([1, 2, 3]).subscribe(on_next=print) as sub:
    # 自动清理
    pass

# retry_with_backoff - 带退避的重试
Observable.throw(Exception('err')).pipe(
    ops.retry_with_backoff(max_retries=5, initial_delay=1.0, multiplier=2.0)
).subscribe(on_error=lambda e: print(f'Failed: {e}'))

# circuit_breaker - 断路器模式
Observable.from_iterable(data).pipe(
    ops.circuit_breaker(threshold=5, reset_timeout=60.0)
).subscribe(on_next=process)
```

## 响应式统计算子

vools.reactive 提供了丰富的统计聚合扩展算子，支持数据分析场景。

### 统计聚合算子

```python
from vools.reactive import Observable

# 中位数
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().median().subscribe(on_next=result.append)
# result: [3.0]

# 方差和标准差
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().variance().subscribe(on_next=result.append)

# 分位数
result = []
Observable.from_iterable(range(1, 11)).p().quantile(0.5).subscribe(on_next=result.append)

# 最小/最大值索引
result = []
Observable.from_iterable([5, 3, 8, 1, 9]).p().arg_min().subscribe(on_next=result.append)  # [3]

# 唯一值计数
result = []
Observable.from_iterable([1, 2, 2, 3, 3, 3]).p().n_unique().subscribe(on_next=result.append)  # [3]
```

### 滚动窗口算子

```python
# 滚动求和（窗口大小为3）
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().rolling_sum(3).subscribe(on_next=result.append)
# result: [1, 3, 6, 9, 12]

# 滚动最小/最大值
result = []
Observable.from_iterable([5, 3, 8, 1, 9]).p().rolling_min(3).subscribe(on_next=result.append)
# result: [5, 3, 3, 1, 1]

# 滚动均值
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).p().rolling_mean(3).subscribe(on_next=result.append)
```

### 累积变换算子

```python
# 累积求和
result = []
Observable.from_iterable([1, 2, 3, 4]).p().cum_sum().subscribe(on_next=result.append)
# result: [1, 3, 6, 10]

# 累积最小/最大值
result = []
Observable.from_iterable([5, 3, 8, 1, 9]).p().cum_min().subscribe(on_next=result.append)
# result: [5, 3, 3, 1, 1]

# 累积均值
result = []
Observable.from_iterable([1, 2, 3, 4]).p().cum_mean().subscribe(on_next=result.append)
# result: [1.0, 1.5, 2.0, 2.5]

# 累积乘积
result = []
Observable.from_iterable([1, 2, 3, 4]).p().cum_prod().subscribe(on_next=result.append)
# result: [1, 2, 6, 24]
```

### 排序 Top-N 算子

```python
# 排序
result = []
Observable.from_iterable([3, 1, 4, 2]).p().sort().subscribe(on_next=result.append)
# result: [1, 2, 3, 4]

# 降序排序
result = []
Observable.from_iterable([3, 1, 4, 2]).p().sort(reverse=True).subscribe(on_next=result.append)

# Top-K
result = []
Observable.from_iterable([5, 3, 8, 1, 9, 2]).p().top_k(3).subscribe(on_next=result.append)
# result: [9, 8, 5]

# Bottom-K
result = []
Observable.from_iterable([5, 3, 8, 1, 9, 2]).p().bottom_k(3).subscribe(on_next=result.append)
# result: [1, 2, 3]
```

### None 值处理与数学工具

```python
# 过滤 None 值
result = []
Observable.from_iterable([1, None, 2, None, 3]).p().drop_none().subscribe(on_next=result.append)
# result: [1, 2, 3]

# 填充 None 值
result = []
Observable.from_iterable([1, None, 2, None, 3]).p().fill_none(0).subscribe(on_next=result.append)
# result: [1, 0, 2, 0, 3]

# 绝对值
result = []
Observable.from_iterable([-1, 2, -3, 4]).p().abs().subscribe(on_next=result.append)
# result: [1.0, 2.0, 3.0, 4.0]

# 值域限制
result = []
Observable.from_iterable([-1, 2, 5, 8]).p().clamp(0, 5).subscribe(on_next=result.append)
# result: [0.0, 2.0, 5.0, 5.0]
```

### 嵌套流展开算子

```python
# 展开嵌套列表
result = []
Observable.from_iterable([[1, 2], [3, 4], [5]]).p().explode().subscribe(on_next=result.append)
# result: [1, 2, 3, 4, 5]

# flatten 与 explode 同语义
result = []
Observable.from_iterable([[1, 2], [3, 4], [5]]).p().flatten().subscribe(on_next=result.append)
```

## 编码模块

vools 提供统一的编码/解码接口，支持多种格式和自定义扩展。

### 基本用法

```python
from vools import (
    Encoder, Decoder, CodecRegistry,
    b64encode, b64decode,
    urlencode, urldecode,
    json_dumps, json_loads,
    gzip_compress, gzip_decompress,
    serialize, deserialize
)

# Base64 编码
encoded = b64encode('hello')
print(encoded)  # base64 编码结果
assert b64decode(encoded) == 'hello'

# URL 编码
encoded_url = urlencode('hello world')
assert urldecode(encoded_url) == 'hello world'

# JSON 序列化
data = {'key': 'value', 'number': 42}
json_str = json_dumps(data)
assert json_loads(json_str) == data

# 链式调用
result = Encoder('hello').base64().json().data
```

### 自定义编码器

```python
# 注册自定义编码器
from vools import encodable, decodable

@encodable('yaml')
def mock_yaml_encode(data):
    if isinstance(data, dict):
        return '\n'.join(f"{k}: {v}" for k, v in data.items())
    return str(data)

@decodable('yaml')  
def mock_yaml_decode(data):
    result = {}
    for line in data.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip()
    return result

# 使用自定义编码器
yaml_result = Encoder({'key': 'value'}).encode('yaml').data
print(yaml_result)  # 'key: value'

yaml_decoded = Decoder('key: value').decode('yaml').data
print(yaml_decoded)  # {'key': 'value'}

# 通用接口
serialized = serialize({'a': 1}, format='yaml')
deserialized = deserialize('a: 1', format='yaml')
```

### CodecRegistry 功能

```python
# 检查支持的格式
print(CodecRegistry.supported_formats())

# 格式检查
assert CodecRegistry.is_format_supported('json') == True
assert CodecRegistry.is_format_supported('yaml') == True
assert CodecRegistry.is_format_supported('unknown') == False

# 注销格式
CodecRegistry.unregister_format('yaml')
assert CodecRegistry.is_format_supported('yaml') == False

# 重新注册
CodecRegistry.register_codec('yaml', mock_yaml_encode, mock_yaml_decode)
```

## 加密模块

vools 提供统一的加密接口，支持多种哈希算法和自定义扩展。

### Hash 函数

```python
from vools import md5, sha1, sha256, sha512

test_data = 'hello world'

print(md5(test_data))    # 32 位十六进制
print(sha1(test_data))   # 40 位十六进制
print(sha256(test_data)) # 64 位十六进制
print(sha512(test_data)) # 128 位十六进制
```

### HMAC 函数

```python
from vools import hmac_md5, hmac_sha256

key = 'my_secret_key'

result = hmac_md5(test_data, key)
print(result)  # HMAC-MD5 结果

result = hmac_sha256(test_data, key)
print(result)  # HMAC-SHA256 结果
```

### Encryptor 类

```python
from vools import Encryptor

# 链式调用
result = Encryptor('hello').sha256().data
print(result)

# HMAC
result = Encryptor('data').hmac_sha256(key='secret').data
print(result)
```

### 密钥和令牌生成

```python
from vools import generate_key, generate_token

# 生成密钥
key_32 = generate_key(32)  # 32 字节 = 64 个十六进制字符
print(key_32)

key_16 = generate_key(16)  # 16 字节 = 32 个十六进制字符
print(key_16)

# 生成令牌（URL-safe base64）
token = generate_token(32)
print(token)  # 43 个字符
```

### 自定义加密器

```python
from vools import encryptable, decryptable, CryptoRegistry

@encryptable('custom_xor')
def xor_encrypt(data, key='secret'):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    result = bytearray()
    for i, byte in enumerate(data):
        result.append(byte ^ key[i % len(key)])
    return bytes(result).hex()

@decryptable('custom_xor')
def xor_decrypt(data, key='secret'):
    if isinstance(key, str):
        key = key.encode('utf-8')
    data_bytes = bytes.fromhex(data)
    result = bytearray()
    for i, byte in enumerate(data_bytes):
        result.append(byte ^ key[i % len(key)])
    return result.decode('utf-8')

# 使用自定义加密器
encrypted = xor_encrypt('hello world', key='key')
decrypted = xor_decrypt(encrypted, key='key')
assert decrypted == 'hello world'

# 使用 Encryptor 类
result = Encryptor('test').encrypt('custom_xor', key='key').data
print(result)
```

### CryptoRegistry 功能

```python
# 检查支持的算法
print(CryptoRegistry.supported_algorithms())

# 算法检查
assert CryptoRegistry.is_algorithm_supported('sha256') == True
assert CryptoRegistry.is_algorithm_supported('custom_xor') == True

# 注销算法
CryptoRegistry.unregister_algorithm('custom_xor')

# 重新注册
CryptoRegistry.register_crypto('custom_xor', xor_encrypt, xor_decrypt)
```

## Result 类型与 safe 装饰器

vools 提供函数式编程的错误处理支持。

### Result 类型

```python
from vools.functional import Result, Success, Failure, success, failure

# 创建 Result
r1 = Result.success(42)
r2 = Result.failure(ValueError('test error'))

# 检查状态
print(r1.is_success)  # True
print(r2.is_failure)  # True

# 映射操作
result = r1.map(lambda x: x * 2)
print(result)  # Success(84)

# 获取值
print(r1.unwrap())      # 42
print(r2.unwrap_or(0))  # 0
```

### safe 装饰器

```python
from vools.functional import safe

@safe
def divide(a, b):
    return a / b

# 成功情况
result = divide(10, 2)
print(result)  # Success(5.0)

# 失败情况
result = divide(10, 0)
print(result)  # Failure(ZeroDivisionError(...))
```

## 响应式监控模块

vools.reactive 提供了完整的系统监控能力，支持键盘、鼠标、剪贴板、文件系统和目录监控。

### 键盘监控

```python
from vools.reactive import KeySubject, KeyObserver, from_keyboard

# 创建键盘监控
obs, disp = from_keyboard(backend="polling")

# 或使用 KeySubject
with KeySubject(backend="polling") as ks:
    received = []
    ks.subscribe(on_next=lambda kd: received.append(kd))
    # 监控开始...

# 使用 KeyObserver 按事件类型路由
ko = KeyObserver(
    on_press=lambda kd: print(f"Press: {kd.key_name}"),
    on_release=lambda kd: print(f"Release: {kd.key_name}"),
)
ko.attach(ks)
```

### 鼠标监控

```python
from vools.reactive import MouseSubject, MouseObserver, from_mouse

# 创建鼠标监控
obs, disp = from_mouse(backend="polling")

# 使用 MouseSubject
with MouseSubject(backend="polling") as ms:
    ms.subscribe(on_next=lambda md: print(f"Mouse: {md.x}, {md.y}"))

# 使用 MouseObserver 路由
mo = MouseObserver(
    on_move=lambda md: print(f"Move: {md.x}, {md.y}"),
    on_click=lambda md: print(f"Click: {md.button}"),
    on_scroll=lambda md: print(f"Scroll: {md.delta}"),
)
mo.attach(ms)
```

### 剪贴板监控

```python
from vools.reactive import ClipSubject, ClipObserver, from_clipboard

# 创建剪贴板监控
obs, disp = from_clipboard()

# 使用 ClipSubject
with ClipSubject(backend="polling") as cs:
    cs.subscribe(on_next=lambda cd: print(f"Clipboard: {cd.content}"))

# 使用 ClipObserver 按内容类型路由
co = ClipObserver(
    on_text=lambda cd: print(f"Text: {cd.content}"),
    on_files=lambda cd: print(f"Files: {cd.files}"),
    on_image=lambda cd: print(f"Image: {len(cd.content)} bytes"),
)
co.attach(cs)

# 写入剪贴板
cs.set_text("Hello World")
```

### 文件系统监控

```python
from vools.reactive import FileSubject, FileObserver, from_filesystem

# 创建文件监控
obs, disp = from_filesystem(paths=["/path/to/watch"], backend="polling")

# 使用 FileSubject
with FileSubject(paths=["/path"], backend="polling") as fs:
    fs.subscribe(on_next=lambda fd: print(f"File: {fd.path} {fd.change_type}"))

# 使用 FileObserver 按变更类型路由
fo = FileObserver(
    on_created=lambda fd: print(f"Created: {fd.path}"),
    on_modified=lambda fd: print(f"Modified: {fd.path}"),
    on_deleted=lambda fd: print(f"Deleted: {fd.path}"),
    on_renamed=lambda fd: print(f"Renamed: {fd.old_path} -> {fd.path}"),
)
fo.attach(fs)
```

### 目录监控

```python
from vools.reactive import FolderSubject, FolderObserver, from_foldersystem

# 创建目录监控
obs, disp = from_foldersystem(paths=["/path/to/watch"], backend="polling")

# 使用 FolderSubject
with FolderSubject(paths=["/path"], backend="polling") as fs:
    fs.subscribe(on_next=lambda fd: print(f"Folder: {fd.path}"))

# 使用 FolderObserver 路由
fo = FolderObserver(
    on_folder_created=lambda fd: print(f"Folder created: {fd.path}"),
    on_folder_deleted=lambda fd: print(f"Folder deleted: {fd.path}"),
)
fo.attach(fs)
```

### 监控后端

每个监控模块支持多种后端：

| 模块 | Windows | macOS | Linux | 通用 |
|------|---------|-------|-------|------|
| 键盘 | WH_KEYBOARD_LL | polling | polling | polling |
| 鼠标 | WH_MOUSE_LL | polling | polling | polling |
| 剪贴板 | AddClipboardFormatListener | polling | polling | polling |
| 文件 | ReadDirectoryChangesW | FSEvents | inotify | polling |
| 目录 | ReadDirectoryChangesW | FSEvents | inotify | polling |

### 自我过滤机制

所有监控模块支持自我过滤，避免循环触发：

```python
from vools.reactive import ClipSubject, write_to_clipboard

# 过滤自身写入的事件
cs = ClipSubject(filter_self=True)

# 写入操作会自动登记签名，不会触发自己的监控
cs.set_text("test")
```

