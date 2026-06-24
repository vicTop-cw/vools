# vools.bridge.moonbit - MoonBit 语言桥接模块

## 1. 语言简介

MoonBit 是一款面向 WebAssembly 设计的现代编程语言，具有以下特点：

- **高性能**：编译为 WasmGC，高效运行
- **类型安全**：静态类型系统，编译时类型检查
- **内存安全**：无空指针、无缓冲区溢出
- **简洁语法**：类 Rust 语法，学习曲线平缓
- **快速编译**：超快的编译速度

MoonBit 桥接模块 (`vools.bridge.moonbit`) 继承自 `LangBridge` 抽象基类，提供将 Python 函数转换为 MoonBit 代码、通过 `moon run` 执行的能力。

## 2. Bridge 类名

```python
MoonBitBridge
```

- **模块路径**：`vools.bridge.moonbit`
- **全局实例**：`moonbit_bridge`（即 `_moonbit_bridge`）
- **装饰器函数**：`moonbit`

继承关系：
```
LangBridge (抽象基类，定义统一接口)
    └── MoonBitBridge (MoonBit 语言具体实现)
```

## 3. 支持的功能

### 核心功能

| 功能 | 说明 |
|------|------|
| 代码生成 | 将 Python 函数转换为 MoonBit 源码 |
| 编译执行 | 通过 `moon run` 执行 MoonBit 代码 |
| 子进程调用 | 通过 subprocess 执行，从 stdout 读取返回值 |
| 依赖支持 | 支持 deps 参数声明依赖函数 |
| 模块代码 | 支持 module_code 参数注入模块级代码 |
| 回退机制 | 编译器不可用时可指定 fallback 函数 |
| 缓存机制 | 基于函数定义缓存项目目录，同一函数复用 |

### 运行模式

| 模式 | 说明 |
|------|------|
| `only_code=True` | 仅生成 MoonBit 源码，不执行 |
| `output_file='path'` | 将生成的代码写入指定文件 |
| `fallback=fn` | 编译器不可用时使用回退函数 |

## 4. 运行环境要求

### 必需环境

- **MoonBit SDK**：最新稳定版
- **Python**：>= 3.6

### 安装 MoonBit

**Windows / macOS / Linux:
```bash
# 使用官方安装脚本
curl -fsSL https://cli.moonbitlang.com/install/unix.sh | bash
```

或参考：[MoonBit 官方安装指南](https://www.moonbitlang.com/download/)

### Windows WSL 支持

在 Windows 上，如果本地没有安装 `moon` 命令但安装了 WSL 且 WSL 中有 moon，会自动通过 WSL 调用。

### 验证安装

```python
from vools.bridge.moonbit import moonbit_compiler_available, get_moonbit_version

print(f"MoonBit 可用: {moonbit_compiler_available()}")
print(f"MoonBit 版本: {get_moonbit_version()}")
```

## 5. 类型映射

### Python ↔ MoonBit 类型映射表

| Python 类型 | MoonBit 类型 | 说明 |
|-------------|--------------|------|
| `int` | `Int` | 整数类型 |
| `float` | `Double` | 浮点数类型 |
| `str` | `String` | 字符串类型 |
| `bool` | `Bool` | 布尔类型 |
| `None` | `Unit` | 无返回值 |

### 类型获取函数

```python
from vools.bridge.moonbit.types import get_moonbit_type

# 获取 MoonBit 类型
moonbit_t = get_moonbit_type(int)   # -> 'Int'
moonbit_t = get_moonbit_type(str)   # -> 'String'
```

## 6. 快速使用示例

### 基础用法

```python
from vools.bridge.moonbit import moonbit, moonbit_compiler_available

if moonbit_compiler_available():
    @moonbit(ret_type=int)
    def add(a: int, b: int) -> int:
        return "a + b"

    @moonbit
    def greet(name: str) -> str:
        return '"Hello, " + name + "!"'

    print(add(2, 3))          # -> 5
    print(greet("MoonBit"))   # -> Hello, MoonBit!
```

### 布尔返回值

```python
@moonbit(ret_type=bool)
def is_even(n: int) -> bool:
    return "n % 2 == 0"

print(is_even(4))  # -> True
print(is_even(5))  # -> False
```

### 使用 compile_and_run

```python
from vools.bridge.moonbit import compile_and_run

moonbit_code = '''
fn add(a : Int, b : Int) -> Int {
  a + b
}
'''

result = compile_and_run(
    code=moonbit_code,
    func_name='add',
    args=(2, 3),
    ret_type=int
)
print(result)  # -> 5
```

## 7. only_code 模式示例

### 生成 MoonBit 源码到文件

```python
from vools.bridge.moonbit import moonbit

@moonbit(only_code=True, output_file='output/hello.mbt')
def hello(name: str) -> str:
    return '"Hello, " + name + "!"'

# 会在 output/hello.mbt 生成 MoonBit 源码
```

### 获取源码字符串

```python
from vools.bridge.moonbit import moonbit

@moonbit(only_code=True)
def add(a: int, b: int) -> int:
    return "a + b"

code = add(1, 2)  # code 是 MoonBit 源码字符串
print(code)
```

### 生成的代码示例

```moonbit
fn add(a : Int, b : Int) -> Int {
  a + b
}

fn main {
  let a = 1
  let b = 2
  let result = add(a, b)
  println(result)
}
```

## 8. 缓存机制

### 缓存策略

- **缓存目录**：系统临时目录下的 `vools_moonbit_cache`
- **缓存键**：基于函数定义（函数名、参数类型、函数体、模块代码）的 MD5 哈希
- **目录复用**：同一函数的不同参数调用复用同一个项目目录
- **动态更新**：每次调用时重写 `main.mbt` 更新参数值

### 缓存优势

1. 避免重复创建项目结构（moon.mod, moon.pkg 等）
2. 利用 moon 自身的构建缓存加速后续构建
3. 不会无限创建临时目录

## 9. 注意事项

### 执行限制

- 通过 `moon run` 执行，存在进程启动开销
- 每次调用都会重写 main.mbt 并重新运行
- 不适合极低延迟场景

### 类型限制

- 目前支持基础类型：Int, Double, Bool, String
- 复杂类型（数组、对象等）需要手动处理
- 字符串参数会进行转义处理，降低注入风险

### 参数传递

- 当前实现通过硬编码参数到 main 函数的方式传递参数
- 字符串参数会进行转义（\ " \n \r 等特殊字符）
- 未来版本计划改为环境变量/文件传递参数

### 错误处理

```python
from vools.bridge.moonbit import moonbit, moonbit_compiler_available

@moonbit(fallback=lambda x, y: x + y)  # 执行失败时使用 Python 回退
def add(a: int, b: int) -> int:
    return "a + b"

result = add(2, 3)  # 如果 MoonBit 不可用，返回 5 (回退结果)
```

### WSL 支持

- Windows 上自动检测 WSL 中的 moon 命令
- 路径自动转换为 WSL 路径格式
- 环境变量自动传递到 WSL 环境

### 与其他语言桥接对比

| 特性 | MoonBit | Dart | Swift | Kotlin |
|------|---------|------|-------|--------|
| 执行方式 | moon run | dart compile exe | swift run | kotlin |
| 调用方式 | subprocess | subprocess | subprocess | subprocess |
| 性能 | 中等 | 高 | 高 | 中等 |
| 缓存策略 | 项目目录复用 | 编译产物缓存 | 编译产物缓存 | 编译产物缓存 |
| 参数传递 | 硬编码（待改进） | stdin JSON | stdin JSON | stdin JSON |
| WSL 支持 | 支持 | 不支持 | 不支持 | 不支持 |
