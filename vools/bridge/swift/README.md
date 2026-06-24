# Swift 语言桥接模块

## 1. 语言简介

Swift 是 Apple 推出的现代化编程语言，设计目标是安全、快速和表达力强。Swift 结合了 C 和 Objective-C 的优点，支持高级语言特性如泛型、闭包和协议扩展，同时保持接近 C 的性能。

本模块通过继承 `LangBridge` 抽象基类，实现 Swift 语言的动态编译和调用能力，支持代码生成、编译缓存、依赖管理和异步执行等特性。

## 2. Bridge 类名

```python
SwiftBridge
```

桥接实例名称：`swift_bridge`

## 3. 支持的功能

- **动态编译**：将 Python 函数体转换为 Swift 代码并编译为动态库
- **代码生成**：支持 `module_code` 模块级代码和 `deps` 依赖函数
- **编译缓存**：自动缓存编译产物，复用相同代码的编译结果
- **项目编译**：编译整个 Swift 项目目录，支持入口函数模式
- **异步执行**：支持 `async_mode=True` 异步调用模式
- **回退机制**：编译器不可用时可自动调用回退函数
- **only_code 模式**：仅生成代码，不执行编译
- **类型映射**：Python 类型自动转换为 Swift 类型

## 4. 运行环境要求

### 必要条件

- **Swift 编译器 (swiftc)**：必须已安装并添加到系统 PATH
  - macOS：Xcode 自带 Swift
  - Linux：从 swift.org 下载安装
  - Windows：从 swift.org 下载 Windows 版本

### 检查编译器可用性

```python
from vools.bridge.swift import swift_compiler_available

if swift_compiler_available():
    print("Swift 编译器可用")
else:
    print("Swift 编译器未安装或未配置到 PATH")
```

## 5. 类型映射

### Python → Swift

| Python 类型 | Swift 类型 |
|------------|------------|
| int        | Int        |
| float      | Double     |
| str        | String     |
| bool       | Bool       |
| list       | [Int]      |
| dict       | [String: Any] |
| None       | Void       |

### Swift → ctypes

| Swift 类型 | ctypes 类型 |
|-----------|-------------|
| Int       | c_int       |
| Int32     | c_int32     |
| Int64     | c_int64     |
| UInt      | c_uint      |
| Double    | c_double    |
| Float     | c_float     |
| Bool      | c_bool      |
| String    | c_char_p    |
| Void      | None        |

## 6. 快速使用示例

### 基础用法

```python
from vools.bridge.swift import swift, swift_bridge

@swift
def add(x: int, y: int) -> int:
    return "return x + y"

result = add(1, 2)  # 返回 3
```

### 带依赖函数

```python
@swift
def helper(n: int) -> int:
    return "return n * 2"

@swift(deps=[helper])
def compute(x: int, y: int) -> int:
    return "return helper(x) + helper(y)"

result = compute(3, 4)  # 返回 14
```

### 带模块级代码

```python
@swift(module_code="let pi = 3.14159")
def circle_area(r: float) -> float:
    return "return pi * Double(r) * Double(r)"

result = circle_area(2.0)  # 返回约 12.566
```

### 异步模式

```python
@swift(async_mode=True)
def async_compute(n: int) -> int:
    return "return n * n"

result = await async_compute(5)
```

### 回退函数

```python
def python_add(x: int, y: int) -> int:
    return x + y

@swift(fallback=python_add)
def swift_add(x: int, y: int) -> int:
    return "return x + y"

result = swift_add(1, 2)  # Swift 不可用时回退到 Python 实现
```

## 7. only_code 模式示例

### 仅生成代码

```python
@swift(only_code=True)
def add(x: int, y: int) -> int:
    return "return x + y"

code = add(1, 2)
print(code)
```

输出：
```swift
import Foundation

func add(x: Int, y: Int) -> Int {
return x + y
}
```

### 输出到文件

```python
@swift(only_code=True, output_file="output.swift")
def add(x: int, y: int) -> int:
    return "return x + y"

add(1, 2)  # 代码写入 output.swift 文件
```

### 自定义前缀后缀

```python
@swift(only_code=True, prefix="import SwiftUI\n\n", suffix="\n// End of code")
def view_builder(name: str) -> str:
    return 'return "Text(\\\(name))"'

code = view_builder("Hello")
```

## 8. project 模式示例

### 项目目录结构

```
my_swift_project/
├── main.swift
├── helper.swift
└── utils.swift
```

### 编译为可执行文件

```python
@swift(project_dir="./my_swift_project", entry="main")
def run_app():
    pass

returncode, stdout, stderr = run_app()
```

### 编译为动态库

```python
@swift(project_dir="./my_swift_project", entry="myFunction")
def call_lib():
    pass

result = call_lib()
```

## 9. 注意事项

### 编译器要求

- 必须安装 Swift 编译器 (`swiftc`) 并配置到系统 PATH
- 建议使用最新稳定版本以获得最佳兼容性

### 函数体格式

- 函数体应返回目标语言代码字符串
- 使用 `return "return x + y"` 而非 `return x + y`
- 保留原始缩进，使用 `textwrap.dedent` 保持格式

### 缓存管理

- 编译缓存默认位于系统临时目录 `vools_swift_cache`
- 可通过 `cache_dir` 参数指定自定义缓存目录
- 缓存键基于代码内容哈希，相同代码不会重复编译

### 跨平台差异

- Windows: 编译为 `.dll`
- macOS: 编译为 `.dylib`
- Linux: 编译为 `.so`

### 动态库调用限制

- Swift 动态库调用需要通过 `dlopen`/`dlsym`
- 本模块使用 subprocess 执行 Swift 脚本方式调用
- 复杂返回值类型建议使用 JSON 序列化

### 异步执行

- 异步模式通过线程池实现
- 长时间运行的任务建议设置超时
- 回退函数在异步模式下也会异步执行
