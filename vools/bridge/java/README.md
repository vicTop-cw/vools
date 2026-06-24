# vools.bridge.java — Java 语言桥接

> JVM 生态系统语言桥接，支持 Py4J 网关通信和 JAR 包编译加载

## 语言简介

Java 是一种广泛使用的面向对象编程语言，以其"一次编写，到处运行"的特性而闻名。它拥有庞大的生态系统和丰富的第三方库，是企业级应用开发的主流选择。

本模块提供 Java 代码编译与跨语言桥接能力，采用装饰器模式，函数返回 Java 代码字符串，装饰器自动编译并调用 Java 方法。支持通过 Py4J 网关与 JVM 通信，以及直接编译为 JAR 包通过反射调用。

## Bridge 类名

**`JavaBridge`** — 继承自 `LangBridge` 抽象基类的 Java 桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@java` 装饰器，函数体返回 Java 代码字符串 |
| only_code 模式 | ✅ | 只生成 Java 源码，不编译/执行 |
| project 模式 | ✅ | 支持项目级编译和打包 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 支持异步执行 |
| 回退机制 | ✅ | `fallback` 参数支持 Python 回退实现 |
| 模块装饰器 | ✅ | `@java_module` 装饰器，批量桥接类方法 |
| Py4J 网关 | ✅ | 支持 Py4J Gateway 与 JVM 通信 |

## 运行环境要求

- **JDK 版本**：>= Java 8（推荐 Java 11+）
- **安装方式**：
  - Windows：下载 [Oracle JDK](https://www.oracle.com/java/technologies/downloads/) 或 [OpenJDK](https://adoptium.net/) 安装
  - macOS：`brew install openjdk@17`
  - Linux：`sudo apt-get install openjdk-17-jdk`
- **PATH 配置**：确保 `javac`、`java`、`jar` 命令在系统 PATH 中
- **JAVA_HOME**：建议设置 `JAVA_HOME` 环境变量
- **常用安装路径自动搜索**：
  - Windows: `C:\Program Files\Java\jdk-17\bin`, `C:\Program Files\Eclipse Adoptium\jdk-17.*\bin`
  - Unix: `/usr/lib/jvm/java-17-openjdk-amd64/bin`, `/usr/java/latest/bin`, `/opt/java/bin`
- **可选依赖**：
  - Py4J（Python 端）：`pip install py4j`
  - py4j.jar（Java 端）：用于 Py4J 网关通信

验证安装：
```bash
javac -version
java -version
```

## 类型映射表

| Python 类型 | Java 类型 | 说明 |
|------------|----------|------|
| `int` | `int` | 整数类型 |
| `float` | `double` | 双精度浮点数 |
| `bool` | `boolean` | 布尔值 |
| `str` | `String` | 字符串类型 |
| `bytes` | `byte[]` | 字节数组 |
| `list` | `ArrayList` / `List` | 列表类型 |
| `dict` | `HashMap` / `Map` | 字典映射 |
| `tuple` | `Object[]` | 元组转换为对象数组 |
| `set` | `HashSet` / `Set` | 集合类型 |
| `None` | `null` | 空值 |

### 基本类型 vs 包装类型

| 基本类型 | 包装类型 | 说明 |
|---------|---------|------|
| `int` | `Integer` | 整型 |
| `double` | `Double` | 双精度浮点 |
| `boolean` | `Boolean` | 布尔 |
| `byte` | `Byte` | 字节 |
| `char` | `Character` | 字符 |
| `long` | `Long` | 长整型 |
| `float` | `Float` | 单精度浮点 |
| `short` | `Short` | 短整型 |

## 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.java import java, java_compiler_available

if not java_compiler_available():
    raise RuntimeError('请先安装 JDK 并加入 PATH')

@java
def add(a: int, b: int) -> int:
    """简单的加法函数"""
    return "return a + b;"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@java
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return '''
    if (n <= 1) {
        return 1;
    }
    return fib(n - 1) + fib(n - 2);
    '''

result = fib(10)
print(result)  # 输出: 89
```

### 字符串处理

```python
@java
def greet(name: str) -> str:
    """字符串拼接"""
    return 'return "Hello, " + name + "!";'

result = greet("World")
print(result)  # 输出: Hello, World!
```

### 列表操作

```python
from typing import List

@java
def sum_list(numbers: List[int]) -> int:
    """列表求和"""
    return '''
    int sum = 0;
    for (int num : numbers) {
        sum += num;
    }
    return sum;
    '''

result = sum_list([1, 2, 3, 4, 5])
print(result)  # 输出: 15
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * 2

@java(fallback=python_fallback)
def double_it(x: int) -> int:
    """使用 Java 实现，失败则回退到 Python"""
    return "return x * 2;"

result = double_it(5)
print(result)  # Java 可用时输出 10，不可用时回退到 Python 也输出 10
```

### 异步模式

```python
import asyncio
from vools.bridge.java import java

@java(async_mode=True)
async def heavy_compute(n: int) -> int:
    """异步执行计算密集型任务"""
    return '''
    if (n <= 1) {
        return 1;
    }
    return heavy_compute(n - 1) + heavy_compute(n - 2);
    '''

async def main():
    result = await heavy_compute(30)
    print(f"Result: {result}")

asyncio.run(main())
```

### 模块装饰器

```python
from vools.bridge.java import java_module

@java_module(name='math_ops')
class MathOps:
    """数学运算模块"""
    
    def add(a: int, b: int) -> int:
        return "return a + b;"
    
    def multiply(a: float, b: float) -> float:
        return "return a * b;"

ops = MathOps()
print(ops.add(3, 5))       # 输出: 8
print(ops.multiply(3.0, 5.0))  # 输出: 15.0
```

## only_code 模式示例

使用 `mode='ONLY_CODE'` 只生成 Java 源码，不编译或执行：

```python
@java(mode='ONLY_CODE')
def generate_add(a: int, b: int) -> int:
    return "return a + b;"

code = generate_add(1, 2)
print(code)
# 输出:
# public class VoolsAdd {
#     public static int add(int a, int b) {
#         return a + b;
#     }
# }
```

### 其他运行模式

| 模式 | 说明 |
|-----|------|
| `DEBUG` | 强制重新编译并执行 |
| `FORCE` | 只强制编译，不执行 |
| `NORMAL` | 命中缓存跳过编译；未命中则编译（默认） |
| `ONLY_RUN` | 只在有缓存时执行；没有则报错 |
| `ONLY_CODE` | 只生成 Java 源码，不编译 |

## project 模式示例

### 项目结构

```
my_java_project/
├── src/
│   ├── MathUtils.java
│   └── Main.java
└── lib/
    └── (可选: 第三方 JAR 包)
```

### MathUtils.java

```java
public class MathUtils {
    public static int add(int a, int b) {
        return a + b;
    }
    
    public static int multiply(int a, int b) {
        return a * b;
    }
}
```

### Main.java

```java
public class Main {
    public static void main(String[] args) {
        System.out.println(MathUtils.add(3, 5));
        System.out.println(MathUtils.multiply(3, 5));
    }
}
```

### 使用 project 模式

```python
from vools.bridge.java import JavaBridge

bridge = JavaBridge()

# 编译项目
project_dir = "./my_java_project"
jar_path = bridge.compile_project(
    project_dir=project_dir,
    entry='Main',
    output_dir="./output",
    class_path=None  # 可添加第三方 JAR 依赖路径
)

print(f"输出 JAR: {jar_path}")

# entry='main' 或包含 main 方法：运行主类
returncode, stdout, stderr = bridge._run_executable(jar_path, args=())
print("退出码:", returncode)
print("输出:", stdout)

# entry!='main' 模式：调用入口静态方法
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
from vools.bridge.java import JavaBridge
from vools.bridge._base import FunctionSpec

bridge = JavaBridge()

spec = FunctionSpec(
    name='add',
    annotations={'a': int, 'b': int, 'return': int},
    args=(),
    defaults={},
    body='return a + b;'
)

code = bridge.generate_code(spec)
print(code)

jar_path = bridge.compile_code(code, 'add')

result = bridge.call_func(jar_path, 'add', (3, 5), int)
print(result)  # 输出: 8
```

## 注意事项

### 编译型语言的调用方式

1. **源码编译**：Java 代码首先通过 `javac` 编译为 `.class` 字节码文件
2. **打包 JAR**：编译后的 class 文件会被打包为 JAR 文件便于管理和调用
3. **调用方式**：
   - **反射调用**：通过 Java 反射机制调用静态方法
   - **Py4J 网关**：启动 JVM 网关服务器，通过 Py4J 协议通信
   - **subprocess**：通过 `java` 命令执行主类
4. **缓存优化**：编译后的 JAR 文件会被缓存，避免重复编译
5. **类路径管理**：支持添加第三方 JAR 依赖到 classpath

### 特殊语法

1. **函数定义**：Java 方法需要指定返回类型、参数类型和方法体
2. **返回值**：使用 `return` 关键字返回值，方法必须声明返回类型
3. **类型声明**：所有变量和参数都需要显式声明类型
4. **分号结尾**：每条语句以分号 `;` 结尾
5. **主方法**：可执行程序需要 `public static void main(String[] args)` 方法
6. **类封装**：所有方法必须定义在类中，静态方法通过类名调用
7. **访问修饰符**：支持 `public`、`private`、`protected` 等访问控制
8. **异常处理**：使用 `try-catch-finally` 进行异常处理

### Py4J 网关通信

1. **网关启动**：自动启动 Py4J 网关服务器，Python 端连接通信
2. **性能优势**：JVM 保持运行，避免每次调用启动新进程的开销
3. **对象传递**：支持 Java 对象在 Python 端的代理访问
4. **回调支持**：Java 代码可以回调 Python 函数
5. **资源管理**：使用完后记得关闭网关连接

### 缓存机制

1. 缓存目录：`$TMPDIR/vools_java_cache/`
2. 缓存键：基于源码 MD5 哈希的前 12 位
3. 缓存内容：编译后的 JAR 文件
4. 强制重编：使用 `mode='DEBUG'` 或 `mode='FORCE'`

### 类路径和依赖

1. **class_path 参数**：可通过 `class_path` 添加第三方 JAR 依赖
2. **多个依赖**：多个 JAR 文件使用系统路径分隔符分隔
   - Windows: `;`
   - Unix: `:`
3. **项目依赖**：project 模式下自动扫描 lib 目录下的 JAR 文件
4. **常见问题**：
   - `ClassNotFoundException`：检查 classpath 是否包含所需依赖
   - `NoSuchMethodError`：检查方法签名是否匹配

### 错误处理

1. Java 编译失败时会抛出 `RuntimeError`，包含编译错误信息
2. Java 运行时异常会被捕获并转换为 Python 异常
3. 建议使用 `java_compiler_available()` 先检查 Java 环境是否可用
4. 仅代码模式（ONLY_CODE）不会检查 Java 可用性
5. 可以使用 `fallback` 参数提供 Python 回退实现

### 内存和性能

1. **JVM 内存**：Py4J 模式下 JVM 保持运行，注意内存使用
2. **编译开销**：首次编译较慢，后续使用缓存
3. **反射开销**：反射调用比直接调用慢，适合计算密集型任务
4. **批量调用**：多次调用建议使用 Py4J 网关模式，避免反复启动 JVM

## API 速查

```python
from vools.bridge.java import (
    # 装饰器
    java,                       # @java 装饰器
    java_module,                # @java_module 模块装饰器
    
    # 类
    JavaBridge,                 # Java 桥接实现类
    _java_bridge,               # 全局 JavaBridge 实例
    
    # 可用性检测
    java_compiler_available,    # 检查 Java 编译器是否可用
    is_java_available,          # 检查 Java 桥接是否可用
    
    # 便捷入口
    compile_and_run,            # 直接编译并运行 Java 代码
    compile_and_run_async,      # 异步编译并运行 Java 代码
    compile_java,               # 编译 Java 代码为 JAR
    
    # Py4J 网关
    GatewayServer,              # Py4J 网关服务器
    JavaGateway,                # Py4J Java 网关客户端
    
    # 类型映射
    JavaTypeMapper,             # Java 类型映射器类
    get_java_type,              # 获取 Java 类型字符串
    infer_java_types,           # 根据值推断 Java 类型列表
    
    # 代码生成
    generate_java_function,     # 生成 Java 函数
    generate_java_class,        # 生成 Java 类
    
    # 编译/加载
    load_java_jar,              # 加载 Java JAR 包
    call_java_method,           # 调用 Java 方法
    is_java_jar_available,      # 检查 JAR 方法是否可用
)
```
