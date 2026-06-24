# vools.bridge.scala — Scala 语言桥接

> JVM 生态函数式语言桥接，支持 scala-cli 编译和 Py4J 网关通信

## 语言简介

Scala 是一种运行在 JVM 上的多范式编程语言，融合了面向对象编程和函数式编程的特性。它以简洁的语法、强大的类型系统和与 Java 生态的无缝互操作而著称。

本模块提供 Scala 代码编译与跨语言桥接能力，采用装饰器模式，函数返回 Scala 代码字符串，装饰器自动编译并调用 Scala 方法。支持 scala-cli 编译工具和 scalac 编译器，以及通过 Py4J 网关与 JVM 通信。

## Bridge 类名

**`ScalaBridge`** — 继承自 `LangBridge` 抽象基类的 Scala 桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@scala` 装饰器，函数体返回 Scala 代码字符串 |
| only_code 模式 | ✅ | 只生成 Scala 源码，不编译/执行 |
| project 模式 | ✅ | 支持项目级编译和打包 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 支持异步执行 |
| 回退机制 | ✅ | `fallback` 参数支持 Python 回退实现 |
| 模块装饰器 | ✅ | `@scala_module` 装饰器，批量桥接类方法 |
| Py4J 网关 | ✅ | 支持 Py4J Gateway 与 JVM 通信 |
| scala-cli 支持 | ✅ | 优先使用 scala-cli，回退到 scalac |

## 运行环境要求

- **Scala 版本**：>= Scala 2.13 或 Scala 3.x
- **编译器选择**（满足其一即可）：
  - **scala-cli**（推荐）：Scala 官方命令行工具
  - **scalac + javac**：传统 Scala 编译器
- **JDK 版本**：>= Java 8（推荐 Java 11+）
- **安装方式**：
  - **scala-cli**：
    - macOS/Linux: `curl -fL https://github.com/VirtusLab/scala-cli/releases/latest/download/scala-cli-x86_64-pc-linux.gz | gzip -d > scala-cli && chmod +x scala-cli && sudo mv scala-cli /usr/local/bin/`
    - Windows: 从 [scala-cli 官网](https://scala-cli.virtuslab.org/install) 下载安装
  - **scalac**：
    - macOS: `brew install scala`
    - Linux: `sudo apt-get install scala`
    - Windows: 从 [Scala 官网](https://www.scala-lang.org/download/) 下载安装
- **PATH 配置**：确保 `scala-cli` 或 `scalac`、`scala`、`javac` 命令在系统 PATH 中
- **常用安装路径自动搜索**：
  - Windows: `C:\Program Files\Scala\bin`, `C:\scala\bin`, `C:\Users\<user>\AppData\Local\Coursier\data\bin`
  - Unix: `/usr/local/scala/bin`, `/opt/scala/bin`, `~/.local/share/coursier/bin`
- **可选依赖**：
  - Py4J（Python 端）：`pip install py4j`
  - py4j.jar（Java/Scala 端）：用于 Py4J 网关通信

验证安装：
```bash
# 推荐: scala-cli
scala-cli version

# 或传统方式
scalac -version
scala -version
```

## 类型映射表

| Python 类型 | Scala 类型 | Java 等价类型 | 说明 |
|------------|-----------|-------------|------|
| `int` | `Int` | `int` | 32 位整数 |
| `float` | `Double` | `double` | 64 位浮点数 |
| `bool` | `Boolean` | `boolean` | 布尔值 |
| `str` | `String` | `String` | 字符串类型 |
| `bytes` | `Array[Byte]` | `byte[]` | 字节数组 |
| `list` | `List` / `Array` | `ArrayList` | 列表/数组 |
| `dict` | `Map` | `HashMap` | 字典映射 |
| `tuple` | `Tuple` | `Product` | 元组 |
| `set` | `Set` | `HashSet` | 集合类型 |
| `None` | `null` / `None` | `null` | 空值 |

### Scala 数值类型

| Scala 类型 | 说明 | Java 类型 |
|-----------|------|----------|
| `Byte` | 8 位有符号整数 | `byte` |
| `Short` | 16 位有符号整数 | `short` |
| `Int` | 32 位有符号整数 | `int` |
| `Long` | 64 位有符号整数 | `long` |
| `Float` | 32 位浮点数 | `float` |
| `Double` | 64 位浮点数 | `double` |
| `Boolean` | 布尔值 | `boolean` |
| `Char` | 16 位无符号字符 | `char` |
| `Unit` | 无返回值 | `void` |
| `String` | 字符串 | `String` |

## 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.scala import scala, scala_compiler_available

if not scala_compiler_available():
    raise RuntimeError('请先安装 Scala 编译器（scala-cli 或 scalac）')

@scala
def add(a: int, b: int) -> int:
    """简单的加法函数"""
    return "a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@scala
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return '''
    if (n <= 1) 1
    else fib(n - 1) + fib(n - 2)
    '''

result = fib(10)
print(result)  # 输出: 89
```

### 字符串处理

```python
@scala
def greet(name: str) -> str:
    """字符串拼接"""
    return '"Hello, " + name + "!"'

result = greet("World")
print(result)  # 输出: Hello, World!
```

### 列表操作

```python
from typing import List

@scala
def sum_list(numbers: List[int]) -> int:
    """列表求和（Scala 风格）"""
    return 'numbers.sum'

result = sum_list([1, 2, 3, 4, 5])
print(result)  # 输出: 15
```

### 模式匹配

```python
@scala
def describe(x: int) -> str:
    """使用 Scala 模式匹配"""
    return '''
    x match {
        case 0 => "zero"
        case 1 => "one"
        case _ if x > 0 => "positive"
        case _ => "negative"
    }
    '''

print(describe(0))  # 输出: zero
print(describe(5))  # 输出: positive
print(describe(-3)) # 输出: negative
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * 2

@scala(fallback=python_fallback)
def double_it(x: int) -> int:
    """使用 Scala 实现，失败则回退到 Python"""
    return "x * 2"

result = double_it(5)
print(result)  # Scala 可用时输出 10，不可用时回退到 Python 也输出 10
```

### 异步模式

```python
import asyncio
from vools.bridge.scala import scala

@scala(async_mode=True)
async def heavy_compute(n: int) -> int:
    """异步执行计算密集型任务"""
    return '''
    if (n <= 1) 1
    else heavy_compute(n - 1) + heavy_compute(n - 2)
    '''

async def main():
    result = await heavy_compute(30)
    print(f"Result: {result}")

asyncio.run(main())
```

### 模块装饰器

```python
from vools.bridge.scala import scala_module

@scala_module(name='math_ops')
class MathOps:
    """数学运算模块"""
    
    def add(a: int, b: int) -> int:
        return "a + b"
    
    def multiply(a: float, b: float) -> float:
        return "a * b"

ops = MathOps()
print(ops.add(3, 5))       # 输出: 8
print(ops.multiply(3.0, 5.0))  # 输出: 15.0
```

## only_code 模式示例

使用 `mode='ONLY_CODE'` 只生成 Scala 源码，不编译或执行：

```python
@scala(mode='ONLY_CODE')
def generate_add(a: int, b: int) -> int:
    return "a + b"

code = generate_add(1, 2)
print(code)
# 输出 (使用 scalac 时):
# object VoolsAdd {
#   def add(a: Int, b: Int): Int = {
#     a + b
#   }
#   def main(args: Array[String]): Unit = {
#     println(add(args(0).toInt, args(1).toInt))
#   }
# }
#
# 或 (使用 scala-cli 时，带 @main 注解):
# @main def add(a: Int, b: Int): Int = {
#   a + b
# }
```

### 其他运行模式

| 模式 | 说明 |
|-----|------|
| `DEBUG` | 强制重新编译并执行 |
| `FORCE` | 只强制编译，不执行 |
| `NORMAL` | 命中缓存跳过编译；未命中则编译（默认） |
| `ONLY_RUN` | 只在有缓存时执行；没有则报错 |
| `ONLY_CODE` | 只生成 Scala 源码，不编译 |

## project 模式示例

### 项目结构

```
my_scala_project/
├── src/
│   ├── MathUtils.scala
│   └── Main.scala
└── lib/
    └── (可选: 第三方 JAR 包)
```

### MathUtils.scala

```scala
object MathUtils {
  def add(a: Int, b: Int): Int = a + b
  
  def multiply(a: Int, b: Int): Int = a * b
  
  def fib(n: Int): Int = 
    if (n <= 1) 1 else fib(n - 1) + fib(n - 2)
}
```

### Main.scala

```scala
object Main {
  def main(args: Array[String]): Unit = {
    println(MathUtils.add(3, 5))
    println(MathUtils.multiply(3, 5))
  }
}
```

### 使用 project 模式

```python
from vools.bridge.scala import ScalaBridge

bridge = ScalaBridge()

# 编译项目
project_dir = "./my_scala_project"
jar_path = bridge.compile_project(
    project_dir=project_dir,
    entry='Main',
    output_dir="./output"
)

print(f"输出 JAR: {jar_path}")

# entry='main' 或包含 main 方法：运行主类
returncode, stdout, stderr = bridge._run_executable(jar_path, args=())
print("退出码:", returncode)
print("输出:", stdout)

# entry!='main' 模式：调用入口对象方法
result = bridge.call_func(
    lib_path=jar_path,
    func_name='MathUtils.add',
    args=(3, 5),
    ret_type=int
)
print("结果:", result)  # 输出: 8
```

### 使用 LangBridge 统一接口

```python
from vools.bridge.scala import ScalaBridge
from vools.bridge._base import FunctionSpec

bridge = ScalaBridge()

spec = FunctionSpec(
    name='add',
    annotations={'a': int, 'b': int, 'return': int},
    args=(),
    defaults={},
    body='a + b'
)

code = bridge.generate_code(spec)
print(code)

jar_path = bridge.compile_code(code, 'add')

result = bridge.call_func(jar_path, 'add', (3, 5), int)
print(result)  # 输出: 8
```

## 注意事项

### 编译型语言的调用方式

1. **编译器选择**：优先使用 `scala-cli`，不可用时回退到 `scalac`
2. **源码编译**：Scala 代码编译为 JVM 字节码（.class 文件）
3. **打包 JAR**：编译后的 class 文件打包为 JAR 文件
4. **调用方式**：
   - **反射调用**：通过 Java 反射机制调用 Scala 对象方法
   - **Py4J 网关**：启动 JVM 网关服务器，通过 Py4J 协议通信
   - **subprocess**：通过 `scala` 或 `java` 命令执行主类
5. **缓存优化**：编译后的 JAR 文件会被缓存，避免重复编译
6. **Scala 单例对象**：Scala 的 `object` 是单例对象，方法通过伴生对象调用

### 特殊语法

1. **函数定义**：使用 `def` 关键字，类型注解使用 `: Type` 语法
2. **返回值类型**：返回类型在参数列表后，用 `: Type` 声明，`=` 连接函数体
3. **表达式导向**：Scala 是表达式导向语言，if/else、match 等都是表达式
4. **对象定义**：使用 `object` 定义单例对象（伴生对象），`class` 定义类
5. **模式匹配**：使用 `match` 表达式进行模式匹配
6. **类型推断**：Scala 有强大的类型推断，很多时候可以省略类型注解
7. **可变/不可变**：`val` 定义不可变变量，`var` 定义可变变量
8. **字符串插值**：支持 `s"Hello, $name"` 字符串插值
9. **隐式参数**：支持 `implicit` 隐式参数和隐式转换
10. **高阶函数**：函数是一等公民，支持高阶函数和闭包

### Scala 版本差异

1. **Scala 2 vs Scala 3**：
   - Scala 3 使用 `@main` 注解定义主方法
   - Scala 2 使用 `object Xxx extends App` 或 `def main(args: Array[String])`
   - scala-cli 自动检测并使用合适的版本
2. **scala-cli 特性**：
   - 自动下载依赖
   - 支持使用 directives 配置
   - 支持脚本和项目模式
3. **兼容性**：Scala 2.13 代码大多可以在 Scala 3 中编译运行

### Py4J 网关通信

1. **网关启动**：自动启动 Py4J 网关服务器，Python 端连接通信
2. **Scala 互操作**：Scala 对象和方法在 Java 端有对应的表示
3. **性能优势**：JVM 保持运行，避免每次调用启动新进程的开销
4. **对象传递**：支持 Scala/Java 对象在 Python 端的代理访问
5. **资源管理**：使用完后记得关闭网关连接

### 缓存机制

1. 缓存目录：`$TMPDIR/vools_scala_cache/`
2. 缓存键：基于源码 MD5 哈希的前 12 位
3. 缓存内容：编译后的 JAR 文件
4. 强制重编：使用 `mode='DEBUG'` 或 `mode='FORCE'`

### 类路径和依赖

1. **依赖管理**：
   - scala-cli：自动管理依赖，使用 `//> using dep` 指令
   - scalac：需要手动管理 classpath
2. **第三方库**：project 模式下 lib 目录下的 JAR 会自动加入 classpath
3. **常见问题**：
   - `ClassNotFoundException`：检查 classpath 和依赖
   - `NoSuchMethodError`：检查方法签名和 Scala 版本兼容性

### 错误处理

1. Scala 编译失败时会抛出 `RuntimeError`，包含编译错误信息
2. Scala 运行时异常会被捕获并转换为 Python 异常
3. 建议使用 `scala_compiler_available()` 先检查 Scala 环境是否可用
4. 仅代码模式（ONLY_CODE）不会检查 Scala 可用性
5. 可以使用 `fallback` 参数提供 Python 回退实现

### 性能考虑

1. **编译时间**：Scala 编译比 Java 慢，特别是首次编译
2. **JVM 预热**：JVM 有 JIT 预热过程，多次调用性能会提升
3. **批量调用**：多次调用建议使用 Py4J 网关模式
4. **scala-cli vs scalac**：
   - scala-cli：更现代，依赖管理方便，但启动稍慢
   - scalac：启动快，但需要手动管理依赖

## API 速查

```python
from vools.bridge.scala import (
    # 装饰器
    scala,                      # @scala 装饰器
    scala_module,               # @scala_module 模块装饰器
    
    # 类
    ScalaBridge,                # Scala 桥接实现类
    _scala_bridge,              # 全局 ScalaBridge 实例
    
    # 可用性检测
    scala_compiler_available,   # 检查 Scala 编译器是否可用
    is_scala_available,         # 检查 Scala 桥接是否可用
    is_scala_cli_available,     # 检查 scala-cli 是否可用
    is_scalac_available,        # 检查 scalac 是否可用
    
    # 便捷入口
    compile_and_run,            # 直接编译并运行 Scala 代码
    compile_and_run_async,      # 异步编译并运行 Scala 代码
    compile_scala,              # 编译 Scala 代码为 JAR
    
    # Py4J 网关
    GatewayServer,              # Py4J 网关服务器
    JavaGateway,                # Py4J Java 网关客户端
    
    # 类型映射
    ScalaTypeMapper,            # Scala 类型映射器类
    get_scala_type,             # 获取 Scala 类型字符串
    infer_scala_types,          # 根据值推断 Scala 类型列表
    
    # 代码生成
    generate_scala_function,    # 生成 Scala 函数
    generate_scala_object,      # 生成 Scala 单例对象
    
    # 编译/加载
    load_scala_jar,             # 加载 Scala JAR 包
    call_scala_method,          # 调用 Scala 方法
    is_scala_jar_available,     # 检查 JAR 方法是否可用
)
```
