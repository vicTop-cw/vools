# Go 语言桥接模块

## 1. 语言简介

Go（又称 Golang）是 Google 开发的一种静态类型、编译式的编程语言，以简洁高效和出色的并发支持著称。`vools.bridge.go` 模块提供了 Go 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 Go 代码为 c-shared 共享库（DLL/SO/DYLIB）
- 通过 cgo + ctypes 实现免序列化跨语言交互
- 列表/切片参数通过 `unsafe.Pointer + 长度` 传递，零拷贝
- 字符串参数通过 `*C.char` 传递，自动编码解码
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 Go 加速函数
- 异步执行模式，支持并发调用

## 2. Bridge 类名

- **类名**: `GoBridge`
- **全局实例**: `_go_bridge`
- **装饰器**: `@go` 或 `@go_bridge.decorator`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@go` 装饰器快速定义 Go 加速函数 |
| only_code 模式 | ✅ 支持 | 仅生成 Go 代码，不编译 |
| project 模式 | ✅ 支持 | 编译整个 Go 项目目录，可生成可执行文件或共享库 |
| 异步模式 | ✅ 支持 | `async_mode=True`，返回 `GoFuture`，可 await |
| 回退机制 | ✅ 支持 | 编译失败时可通过 fallback 回退 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |
| 免序列化数组 | ✅ 支持 | list 参数通过指针 + 长度传递，零拷贝 |

## 4. 编译器要求

使用 Go 语言桥接需要安装 Go 工具链：

### Windows
- 下载并安装 Go：https://go.dev/dl/
- 安装后确保 `go` 在系统 PATH 中
- 验证：打开命令提示符，输入 `go version`

### Linux
```bash
# Debian/Ubuntu
sudo apt-get install golang-go

# 或从官网下载最新版本
wget https://go.dev/dl/go1.22.0.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.22.0.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin
```

### macOS
```bash
# 使用 Homebrew
brew install go

# 或从官网下载
# https://go.dev/dl/
```

### 验证安装
```python
from vools.bridge.go import go_compiler_available, is_go_available

if go_compiler_available():
    print("Go 编译器可用")
else:
    print("Go 编译器不可用，请安装 Go 工具链（>= 1.18）")
```

## 5. 类型映射表

| Python 类型 | Go (cgo) 类型 | ctypes 类型 | 说明 |
|------------|--------------|------------|------|
| `int` | `C.longlong` | `c_int64` | 64 位有符号整数 |
| `float` | `C.double` | `c_double` | 双精度浮点数 |
| `bool` | `C.bool` | `c_bool` | 布尔值 |
| `str` | `*C.char` | `c_char_p` | UTF-8 字符串，自动编码/解码 |
| `bytes` | `unsafe.Pointer` | `c_void_p` | 字节数组指针（需配长度参数） |
| `list` | `unsafe.Pointer` | `c_void_p` | 数组指针（需配长度参数） |
| `None` | `C.void` | `None` | 无返回值 |

> **注意**：`list` 和 `bytes` 类型的参数会自动展开为 `(指针, 长度)` 两个参数。例如 `arr: list` 在 Go 端会变成 `arr unsafe.Pointer, arr_n C.longlong`。

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.go import go

@go
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "return int64(a) + int64(b)"

result = add(3, 5)
print(result)  # 输出: 8
```

### 字符串处理

```python
@go
def greet(name: str) -> str:
    return 'return C.CString("Hello, " + C.GoString(name) + "!")'

message = greet("World")
print(message)  # 输出: Hello, World!
```

### 数组（免序列化）

```python
@go
def sum_array(arr: list) -> int:
    """
    数组求和（零拷贝）
    
    list 参数自动展开为 (ptr, n) 两个参数：
    - arr: unsafe.Pointer（数组指针）
    - arr_n: C.longlong（数组长度）
    """
    return """
    ptr := (*[1 << 30]C.longlong)(arr)
    var total C.longlong = 0
    for i := C.longlong(0); i < arr_n; i++ {
        total += ptr[i]
    }
    return total
    """

result = sum_array([1, 2, 3, 4, 5])
print(result)  # 输出: 15
```

### 递归函数

```python
@go
def fib(n: int) -> int:
    return """
    if int64(n) <= 1 {
        return 1
    }
    return int64(fib(int64(n)-1)) + int64(fib(int64(n)-2))
    """

result = fib(10)
print(result)  # 输出: 89
```

### 异步模式

```python
import asyncio
from vools.bridge.go import go

@go(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    var total C.longlong = 0
    for i := C.longlong(0); i < C.longlong(n); i++ {
        total += i
    }
    return total
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

### 并发调用

```python
import asyncio
from vools.bridge.go import go

@go(async_mode=True)
async def compute(x: int) -> int:
    return "return int64(x) * int64(x)"

async def parallel():
    # 并发调用 10 次
    tasks = [compute(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    print(results)  # 输出: [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

asyncio.run(parallel())
```

## 7. only_code 模式示例

仅生成 Go 代码，不编译执行：

```python
@go(mode='ONLY_CODE')
def generate_code(a: int, b: int) -> int:
    return "return int64(a) + int64(b)"

code = generate_code(1, 2)
print(code)
# 输出:
# package main
# 
# import "C"
# import "unsafe"
# 
# //export generate_code
# func generate_code(a C.longlong, b C.longlong) C.longlong {
#     return int64(a) + int64(b)
# }
# 
# func main() {}
```

### 使用 LangBridge 的 only_code 模式

```python
from vools.bridge.go import GoBridge

go_bridge = GoBridge()

@go_bridge.decorator(only_code=True)
def add(a: int, b: int) -> int:
    return "return int64(a) + int64(b)"

code = add(1, 2)
print(code)
```

### 输出到文件

```python
@go_bridge.decorator(only_code=True, output_file='./output/add.go')
def add(a: int, b: int) -> int:
    return "return int64(a) + int64(b)"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

## 8. project 模式示例

### 编译 Go 项目为可执行文件

```python
from vools.bridge.go import GoBridge

go_bridge = GoBridge()

# 项目目录结构:
# my_go_project/
#   go.mod
#   main.go
#   utils/
#     utils.go

returncode, stdout, stderr = go_bridge.decorator(
    project_dir='./my_go_project',
    entry='main'
)(lambda: None)()

print(f"返回码: {returncode}")
print(f"标准输出: {stdout}")
```

### 编译 Go 项目为共享库

```python
# 编译为 c-shared 共享库
@go_bridge.decorator(project_dir='./my_go_project', entry='MyFunction')
def my_function(a: int, b: int) -> int:
    pass

result = my_function(10, 20)
print(result)
```

### 手动调用 project 编译

```python
bridge = GoBridge()

# 编译为可执行文件
exe_path = bridge.compile_project('./my_go_project', entry='main')
print(f"可执行文件: {exe_path}")

# 编译为共享库
dll_path = bridge.compile_project('./my_go_project', entry='MyFunc')
print(f"共享库: {dll_path}")
```

## 9. 注意事项

### cgo 导出
- 所有导出函数必须使用 `//export 函数名` 注释标记
- 函数签名中使用 C 类型（`C.longlong`、`C.double`、`C.bool`、`*C.char` 等）
- `package main` 和空的 `func main() {}` 是 c-shared 编译的必需项

### 数组传递（免序列化）
- `list` 和 `bytes` 类型的参数会自动展开为 `(指针, 长度)` 两个参数
- 例如 `arr: list` → `arr unsafe.Pointer, arr_n C.longlong`
- 在 Go 端通过 `(*[1 << 30]C.longlong)(arr)` 将指针转换为切片
- 这种方式是零拷贝的，性能远高于序列化/反序列化

### 字符串处理
- `str` 类型会自动以 UTF-8 编码传递为 `*C.char`
- Go 端使用 `C.GoString()` 将 C 字符串转换为 Go 字符串
- 返回字符串时使用 `C.CString()` 创建 C 字符串（注意内存管理）
- ⚠️ 注意：`C.CString()` 分配的内存需要手动释放，可能导致内存泄漏

### 编译缓存
- 缓存目录默认为系统临时目录下的 `vools_go_cache`
- 相同代码内容只会编译一次，后续调用直接使用缓存
- 可通过 `cache_dir` 参数自定义缓存目录
- 使用 `mode='DEBUG'` 可以强制重新编译

### 运行模式
- **NORMAL** (默认): 缓存命中则使用缓存，否则编译并执行
- **DEBUG**: 强制重新编译并执行
- **FORCE**: 只强制编译，不执行（返回 .so 路径）
- **ONLY_RUN**: 只在有缓存时执行，没有则报错
- **ONLY_CODE**: 只生成 Go 源码，不编译

### 异步与并发
- `async_mode=True` 时返回 `GoFuture` 对象
- `GoFuture` 支持 `.result()` 阻塞等待，也支持 `await`
- 多个 `GoFuture` 可以通过 `asyncio.gather` 并发执行
- ctypes 调用会释放 GIL，因此多个 Go 函数调用可以真正并行

### 内存安全
- Go 有自己的垃圾回收器，跨语言调用时需注意内存所有权
- 不要在 Python 侧释放 Go 分配的内存
- 数组传递时，Python 端必须确保数组在调用期间不被回收
- 返回字符串时建议使用调用者提供的缓冲区，避免内存泄漏

### 平台差异
- Windows 下生成 `.dll`，Linux 下生成 `.so`，macOS 下生成 `.dylib`
- Windows 上需要将 DLL 所在目录加入 DLL 搜索路径（已自动处理）
- Go 1.18+ 支持泛型，但 cgo 边界不支持泛型

### 性能提示
- 首次调用需要编译 Go 代码（约 1-3 秒），后续调用使用缓存，性能接近原生
- 数组使用免序列化传递，性能远高于 JSON/CSV 等序列化方式
- 计算密集型任务建议使用 Go 实现，IO 密集型任务意义不大
- 小函数调用开销主要来自 ctypes 边界，复杂计算收益更高

### 相关资源
- [Go 官方文档](https://go.dev/doc/)
- [cgo 文档](https://pkg.go.dev/cmd/cgo)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
- [Go 下载地址](https://go.dev/dl/)
