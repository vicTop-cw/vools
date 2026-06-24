# Kotlin 语言桥接模块

## 1. 语言简介

Kotlin 是一种现代静态类型编程语言，由 JetBrains 开发，与 Java 100% 互操作。`vools.bridge.kotlin` 模块提供了 Kotlin 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 Kotlin 代码为 JAR 或 native 可执行文件
- 通过 subprocess 调用 kotlin/kotlinc 进行编译和执行
- 使用 `fun` 关键字定义函数，确保 Kotlin 语法兼容
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 Kotlin 加速函数
- 列表/数组参数通过标准输入输出传递，JSON 序列化
- 支持异步模式和回退机制

## 2. Bridge 类名

- **类名**: `KotlinBridge`
- **全局实例**: `_kotlin_bridge`
- **装饰器**: `@kotlin` 或 `@kotlin_bridge.decorator`
- **别名**: `@kt` 与 `@kotlin` 等效
- **类型映射器**: 内置类型映射系统 `PY_TO_KOTLIN_TYPE`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@kotlin` 装饰器快速定义 Kotlin 加速函数 |
| only_code 模式 | ✅ 支持 | `mode='ONLY_CODE'`，仅生成 Kotlin 代码，不编译 |
| project 模式 | ✅ 支持 | 编译整个项目目录，支持 JAR 或 native 编译 |
| 异步模式 | ✅ 支持 | `async_mode=True`，返回 Future，可 await |
| 回退机制 | ✅ 支持 | `fallback` 参数，编译失败时回退 |

## 4. 运行环境要求

### 必需组件

| 组件 | 版本要求 | 安装方式 |
|------|---------|---------|
| Kotlin 编译器 (kotlinc) | >= 1.5 | [官方安装指南](https://kotlinlang.org/docs/command-line.html) |
| Java 运行时 (java) | >= 8 | Kotlin 依赖 JVM 运行 |

### 环境验证

```python
from vools.bridge.kotlin import kotlin_compiler_available

if kotlin_compiler_available():
    print("Kotlin 编译器可用")
else:
    print("请安装 kotlinc: https://kotlinlang.org/docs/command-line.html")
```

## 5. 类型映射

### Python → Kotlin 类型

| Python 类型 | Kotlin 类型 |
|------------|-------------|
| `int` | `Int` |
| `float` | `Double` |
| `str` | `String` |
| `bool` | `Boolean` |
| `list` | `List<Int>` |
| `dict` | `Map<String, Any>` |
| `None` | `Unit` |

### Kotlin → ctypes 类型

| Kotlin 类型 | ctypes 类型 |
|------------|------------|
| `Int` | `c_int` |
| `Long` | `c_long` |
| `Double` | `c_double` |
| `Float` | `c_float` |
| `Boolean` | `c_bool` |
| `String` | `c_char_p` |
| `Unit` | `None` |

## 6. 快速使用示例

### 基础装饰器模式

```python
from vools.bridge.kotlin import kotlin

@kotlin
def add(x: int, y: int) -> int:
    return "return x + y"

result = add(10, 20)
print(result)  # 输出: 30
```

### 带依赖函数

```python
@kotlin
def helper(x: int) -> int:
    return "return x * 2"

@kotlin(deps=[helper])
def compute(x: int) -> int:
    return "return helper(x) + 1"

result = compute(5)
print(result)  # 输出: 11
```

### 带模块级代码

```python
module_code = "fun square(x: Int) = x * x"

@kotlin(module_code=module_code)
def use_helper(x: int) -> int:
    return "return square(x) + 1"

result = use_helper(4)
print(result)  # 输出: 17
```

## 7. only_code 模式示例

### 仅生成代码

```python
@kotlin(only_code=True)
def my_func(x: Int, y: Int): Int:
    return "return x + y"

code = my_func()  # code 包含生成的 Kotlin 代码字符串
print(code)
```

### 写入文件

```python
@kotlin(only_code=True, output_file="./MyFunc.kt")
def my_func(x: Int): Int:
    return "return x * 2"
```

### 自定义前缀后缀

```python
@kotlin(only_code=True, prefix="package mypackage\n\n", suffix="\nfun main() = println(\"done\")")
def my_func(): Int:
    return "return 42"
```

## 8. project 模式示例

### 项目目录结构

```
my_kotlin_project/
├── src/
│   ├── main.kt
│   └── utils.kt
└── build.gradle.kts (可选)
```

### 编译项目

```python
from vools.bridge.kotlin import kotlin

@kotlin(project_dir="./my_kotlin_project", entry="main")
def build_project():
    pass

result = build_project()
print(f"编译产物: {result}")
```

## 9. 注意事项

### Kotlin 编译注意

1. **JVM 依赖**: Kotlin 编译器需要 Java 运行时，确保 `java` 命令可用
2. **kotlinc 安装**: 从 [Kotlin 官方](https://kotlinlang.org/docs/command-line.html) 下载安装
3. **编译方式**: 
   - 默认使用 `kotlinc -include-runtime -d output.jar Main.kt` 编译为 JAR
   - 可选 native 编译: `kotlinc -nativelib Main.kt`

### 参数传递注意

1. **JSON 序列化**: 参数通过标准输入输出传递，使用 JSON 序列化
2. **返回值**: 通过标准输出返回，支持 Int/Double/String/Boolean
3. **错误处理**: 异常信息以 `ERROR:` 前缀返回

### 缓存机制

1. **缓存目录**: 默认 `~/.vools_kotlin_cache/`
2. **缓存键**: 基于代码内容的 MD5 哈希
3. **手动缓存**: 可通过 `cache_dir` 参数指定缓存位置

### 异步模式

```python
import asyncio
from vools.bridge.kotlin import kotlin

@kotlin(async_mode=True)
def slow_func(x: int) -> int:
    return "return x * 2"

async def main():
    result = await slow_func(10)
    print(result)

asyncio.run(main())
```

### 回退机制

```python
def python_fallback(x: int) -> int:
    return x * 2

@kotlin(fallback=python_fallback)
def kotlin_func(x: int) -> int:
    return "return x * 2"

result = kotlin_func(5)  # 如果 Kotlin 编译失败，使用 Python 回退
```
