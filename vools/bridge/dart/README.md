# vools.bridge.dart - Dart 语言桥接模块

## 1. 语言简介

Dart 是 Google 开发的一种面向对象的编程语言，主要用于构建跨平台应用程序。Dart 语言具有以下特点：

- **类型安全**：支持静态类型检查和运行时类型检查
- **空安全**：内置空安全机制，避免空指针异常
- **异步支持**：完善的 async/await 异步编程模型
- **跨平台**：通过 Flutter 框架支持 iOS、Android、Web 等多平台开发
- **高性能**：支持 AOT 编译和 JIT 编译，生成高效的本地代码

Dart 桥接模块 (`vools.bridge.dart`) 继承自 `LangBridge` 抽象基类，提供将 Python 函数转换为 Dart 代码、编译为本地可执行文件并通过 subprocess 执行的能力。

## 2. Bridge 类名

```python
DartBridge
```

- **模块路径**：`vools.bridge.dart`
- **全局实例**：`dart_bridge`（即 `_dart_bridge`）
- **装饰器函数**：`dart`
- **别名**：`dartexe`

继承关系：
```
LangBridge (抽象基类，定义统一接口)
    └── DartBridge (Dart 语言具体实现)
```

## 3. 支持的功能

### 核心功能

| 功能 | 说明 |
|------|------|
| 代码生成 | 将 Python 函数转换为 Dart 源码 |
| 编译执行 | 通过 `dart compile exe` 编译为本地可执行文件 |
| 子进程调用 | 通过 subprocess 执行 Dart 程序，JSON 序列化传递参数 |
| 依赖支持 | 支持 deps 参数声明依赖函数 |
| 模块代码 | 支持 module_code 参数注入模块级代码 |
| 异步模式 | 支持 async_mode=True 返回 DartFuture |
| 回退机制 | 编译器不可用时可指定 fallback 函数 |
| 缓存机制 | 自动缓存编译产物，复用相同代码的编译结果 |

### 运行模式

| 模式 | 说明 |
|------|------|
| `only_code=True` | 仅生成 Dart 源码，不编译执行 |
| `output_file='path'` | 将生成的代码写入指定文件 |
| `async_mode=True` | 返回异步 Future，支持 await |

## 4. 运行环境要求

### 必需环境

- **Dart SDK**：>= 2.12.0（建议使用最新稳定版）
- **Python**：>= 3.8

### 安装 Dart

**Windows:**
```powershell
# 使用 winget
winget install Dart SDK

# 或下载安装包
# https://dart.dev/get-dart
```

**macOS:**
```bash
# 使用 Homebrew
brew install dart
```

**Linux:**
```bash
# 使用 apt
sudo apt-get install dart

# 或添加 Dart SDK 源
```

### 验证安装

```python
from vools.bridge.dart import dart_compiler_available, get_dart_version

print(f"Dart 可用: {dart_compiler_available()}")
print(f"Dart 版本: {get_dart_version()}")
```

## 5. 类型映射

### Python ↔ Dart 类型映射表

| Python 类型 | Dart 类型 | 说明 |
|-------------|-----------|------|
| `int` | `int` | 整数类型 |
| `float` | `double` | 浮点数类型 |
| `str` | `String` | 字符串类型 |
| `bool` | `bool` | 布尔类型 |
| `list` | `List<int>` | 列表类型（默认） |
| `dict` | `Map<String, dynamic>` | 字典类型 |
| `None` | `void` | 无返回值 |

### Dart ↔ ctypes 类型映射表

| Dart 类型 | ctypes 类型 |
|-----------|-------------|
| `int` | `ctypes.c_int` |
| `int32` | `ctypes.c_int32` |
| `int64` | `ctypes.c_int64` |
| `double` | `ctypes.c_double` |
| `float` | `ctypes.c_float` |
| `bool` | `ctypes.c_bool` |
| `String` | `ctypes.c_char_p` |
| `void` | `None` |

### 类型获取函数

```python
from vools.bridge.dart import get_dart_type, get_dart_ctype

# 获取 Dart 类型
dart_t = get_dart_type(int)  # -> 'int'
dart_t = get_dart_type(str)  # -> 'String'

# 获取 ctypes 类型
ct = get_dart_ctype('int')      # -> ctypes.c_int
ct = get_dart_ctype('double')   # -> ctypes.c_double
```

## 6. 快速使用示例

### 基础用法

```python
from vools.bridge.dart import dart, dart_compiler_available

if dart_compiler_available():
    @dart
    def add(a: int, b: int) -> int:
        return "return a + b"

    @dart
    def greet(name: str) -> str:
        return 'return "Hello, $name!"'

    print(add(2, 3))          # -> 5
    print(greet("Dart"))      # -> Hello, Dart!
```

### 异步模式

```python
from vools.bridge.dart import dart
import asyncio

@dart(async_mode=True)
def fib(n: int) -> int:
    return '''
    if (n <= 1) return 1;
    return fib(n - 1) + fib(n - 2);
    '''

async def main():
    result = await fib(10)
    print(result)  # -> 89

asyncio.run(main())
```

### 使用 compile_and_run

```python
from vools.bridge.dart import compile_and_run

dart_code = '''
String add(int a, int b) {
    return (a + b).toString();
}
'''

result = compile_and_run(
    dart_code=dart_code,
    func_name='add',
    args=(2, 3),
    ret_type='String'
)
print(result)  # -> 5
```

## 7. only_code 模式示例

### 生成 Dart 源码到文件

```python
from vools.bridge.dart import dart

@dart(only_code=True, output_file='output/hello.dart')
def hello(name: str) -> str:
    return 'print("Hello, $name!");'

# 会在 output/hello.dart 生成 Dart 源码
```

### 获取源码字符串

```python
from vools.bridge.dart import dart

@dart(only_code=True)
def add(a: int, b: int) -> int:
    return "return a + b;"

code = add(1, 2)  # code 是 Dart 源码字符串
print(code)
```

### 生成的代码示例

```dart
import 'dart:convert';
import 'dart:io';

String add(int a, int b) {
    return (a + b).toString();
}

void main() {
    final stdin = stdinLineStream();
    stdin.listen((line) {
        if (line.trim().isEmpty) return;
        try {
            final data = jsonDecode(line);
            final args = List<dynamic>.from(data['args']);
            final funcName = data['func'] as String;

            dynamic result;
            switch (funcName) {
                case 'add':
                    result = add(args[0] as int, args[1] as int);
                    break;
                default:
                    throw Exception('Unknown function: $funcName');
            }
            stdout.writeln(jsonEncode({'result': result}));
        } catch (e) {
            stderr.writeln('ERROR: $e');
        }
    });
}

Stream<String> stdinLineStream() {
    final controller = StreamController<String>();
    List<int> currentLine = [];
    stdin.listen((data) {
        for (var byte in data) {
            if (byte == 10) {
                controller.add(String.fromCharCodes(currentLine));
                currentLine = [];
            } else if (byte != 13) {
                currentLine.add(byte);
            }
        }
    });
    return controller.stream;
}
```

## 8. project 模式示例

### 项目结构

```
my_dart_project/
├── pubspec.yaml
├── bin/
│   └── main.dart
└── lib/
    └── utils.dart
```

### 使用 project_dir 编译项目

```python
from vools.bridge.dart import dart_bridge

# 编译整个 Dart 项目
result = dart_bridge._run_project_sync(
    func=lambda: None,
    args=(),
    kwargs={},
    project_dir='./my_dart_project',
    entry='main',
    fallback=None,
    cache_dir=None,
    ret_type=None
)

returncode, stdout, stderr = result
print(f"Exit code: {returncode}")
print(f"Output: {stdout}")
print(f"Errors: {stderr}")
```

### 项目模式流程

1. 扫描项目目录下所有 `.dart` 文件
2. 调用 `dart compile exe -o output_path [files]` 编译
3. 执行生成的可执行文件
4. 通过 stdin/stdout JSON 协议与进程交互

## 9. 注意事项

### 编译限制

- Dart 仅支持 `entry='main'` 模式的完整项目编译
- 编译产物为本地可执行文件，非共享库
- 编译超时时间为 120 秒（单函数）、180 秒（项目）

### 执行限制

- 通过 subprocess 调用，存在进程启动开销
- 每次调用都会启动新进程，不适合极低延迟场景
- Windows 下可执行文件扩展名为 `.exe`，其他平台无扩展名

### 类型限制

- Dart 的 `int` 类型为有符号 64 位整数
- `float` 和 `double` 都是双精度浮点数
- 复杂类型（如嵌套 List、自定义类）需要自行序列化

### 缓存机制

- 缓存目录：系统临时目录下的 `vools_dart_cache`
- 缓存键：基于源码 MD5 哈希
- 强制重编译：修改代码后会自动重新编译

### 错误处理

```python
from vools.bridge.dart import dart, dart_compiler_available

@dart(fallback=lambda x, y: x + y)  # 编译失败时使用 Python 回退
def add(a: int, b: int) -> int:
    return "return a + b"

result = add(2, 3)  # 如果 Dart 不可用，返回 5 (回退结果)
```

### 与其他语言桥接对比

| 特性 | Dart | Go | Rust | Java |
|------|------|-----|------|------|
| 编译产物 | exe | so/dll/dylib | so/dll | jar |
| 调用方式 | subprocess | ctypes | ctypes | subprocess |
| 性能 | 中等 | 高 | 高 | 中等 |
| 依赖 | 无 | 无 | 无 | 无 |
| 空安全 | 支持 | 不支持 | 支持 | 不支持 |
