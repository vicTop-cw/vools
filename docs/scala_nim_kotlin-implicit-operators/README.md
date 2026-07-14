# Scala / Kotlin / Nim 隐式双元操作符

本项目实现了一组隐式双元操作符，用于函数组合与数据管道处理，支持 Scala、Kotlin、Nim 三种语言。

## 项目结构

```
docs/scala_nim_kotlin-implicit-operators/
├── README.md                # 项目总览
├── 需求文档.md               # 操作符需求说明
├── 实现指南.md               # 各语言实现差异与使用指南
```

### Scala 模块

```
vools/bridge/scala/operators/
├── Operators.scala          # 源码（单文件）
├── vools-operators.jar      # 编译产物
├── build.bat                # 编译脚本
```

### Kotlin 模块

```
vools/bridge/kotlin/operators/
├── Operators.kt             # 源码（单文件）
├── vools-operators.jar      # 编译产物
├── build.bat                # 编译脚本
```

### Nim 模块

```
vools/bridge/nim/operators/
├── operators.nim            # 源码（单文件）
├── operators.dll            # 编译产物
├── build.bat                # 编译脚本
```

### 测试目录

```
tests/
├── scala/
│   ├── OperatorsTest.scala  # Scala 测试（45 个测试用例）
│   └── run_tests.bat        # 测试脚本
├── kotlin/
│   ├── OperatorsTest.kt     # Kotlin 测试（9 个测试用例）
│   └── run_tests.bat        # 测试脚本
└── nim/
    ├── operators_test.nim   # Nim 测试
    └── run_tests.bat        # 测试脚本
```

## 环境要求

### Scala
- Scala 2.11.x / 2.13.x（兼容 Spark 2.4.3 使用的 Scala 2.11.12）
- Java 运行时（JRE/JDK 8+）

### Kotlin
- Kotlin 1.9+
- Java 运行时（JRE/JDK 8+）

### Nim
- Nim 1.6+
- Windows 环境（生成 DLL）

## 操作符一览

### 函|函 操作符（18 个）

| 正向 | 反向 | 左侧 | 右侧 | 返回 | 说明 |
|------|------|------|------|------|------|
| `#>` | `<#` | `() => A` | `A => B` | `() => B` | 无参函数结果传入单参函数 |
| `#>>` | `<<#` | `() => A` | `(A, B) => C` | `B => C` | 无参函数结果作为双参函数首参 |
| `*#>` | `<#*` | `() => Seq[A]` / `() => TupleN[A]` | 至少 1 参函数 | 新函数 | 无参函数结果解包后预填充 |
| `~>` | `<~` | `D => A` | `A => B` | `D => B` | 单参函数复合 |
| `~>>` | `<<~` | `D => A` | `(A, B) => C` | `(D, B) => C` | 单参函数结果作为双参函数首参 |
| `*~>` | `<~*` | `D => Seq[A]` / `D => TupleN[A]` | 至少 1 参函数 | 新函数 | 单参函数结果解包后预填充 |
| `~~>` | `<~~` | `(D, F) => A` | `A => B` | `(D, F) => B` | 双参函数结果传入单参函数 |
| `*~~>` | `<~~*` | `(D, F) => Seq[A]` / `(D, F) => TupleN[A]` | 至少 1 参函数 | 新函数 | 双参函数结果解包后预填充 |
| `~~>>` | `<<~~` | `(D, F) => A` | `(A, B) => C` | `(D, F, B) => C` | 双参函数结果作为双参函数首参 |

> 命名说明：原需求中的 `o>` / `<o` / `o>>` / `<<o` / `*o>` / `<o*` 在 Scala 2 中无法作为单个方法名解析，因此统一替换为以 `#` 开头的等价形式。

### 数|函 操作符（12 个）

| 正向 | 反向 | 左侧 | 右侧 | 返回 | 说明 |
|------|------|------|------|------|------|
| `\|>` | `<\|` | 任意值 `A` | `A => B` | `B` | 函数应用 |
| `\|>>` | `<<\|` | `Iterable[A]` | `A => B` | `Iterable[B]` | map，保持集合类型 |
| `\|?>` | `<\|?` | `Iterable[A]` | `A => Boolean` | `Iterable[A]` | filter，保持集合类型 |
| `\|*>` | `<*\|` | `Iterable[Iterable[A]]` | `A => B` | `Iterable[B]` | 展平后 map，保持外层集合类型 |
| `\|&>` | `<&\|` | `Iterable[A]` | `(A, A) => A` | `A` | reduce |
| `\|@>` | `<@\|` | `Iterable[A]` | `G => (G, A) => G` | `G => G` | fold，返回接收初始值的函数 |

### 跨语言命名差异

| 语言 | 操作符名称形式 | 说明 |
|------|--------------|------|
| Scala | `#>`, `<#`, `~>`, `<~`, `|>`, `<\|` 等 | 原生支持特殊符号操作符 |
| Kotlin | `#gt`, `lt#`, `pipe`, `pipeMap` 等 | 使用 ASCII 命名，因 Kotlin 不支持 `<` 和 `>` 作为方法名开头 |
| Nim | `compose01`, `pipe`, `pipeMap` 等 | 使用 ASCII 命名，函数式风格 |

## 使用示例

### Scala

```scala
import com.example.operators.Operators._

def genA(): String = "Hello"
def genB(s: String): String = s"$s, World!"

val merged = genA _ #> genB _
merged() // "Hello, World!"

val doubled = List(1, 2, 3) |>> (_ * 2)
// List(2, 4, 6)
```

### Kotlin

```kotlin
import com.example.operators.Operators._

fun genA(): String = "Hello"
fun genB(s: String): String = "$s, World!"

val merged = genA `#gt` genB
println(merged()) // "Hello, World!"

val doubled = listOf(1, 2, 3).pipeMap { it * 2 }
// [2, 4, 6]
```

### Nim

```nim
import operators

proc genA(): string = "Hello"
proc genB(s: string): string = s & ", World!"

let merged = compose01(genA, genB)
echo merged() # "Hello, World!"

let doubled = pipeMap(@[1, 2, 3], proc(x: int): int = x * 2)
echo doubled # @[2, 4, 6]
```

## 运行测试

### Scala

```powershell
cd tests/scala
powershell -ExecutionPolicy Bypass -File run_tests.bat
```

### Kotlin

```powershell
cd tests/kotlin
powershell -ExecutionPolicy Bypass -File run_tests.bat
```

### Nim

```powershell
cd tests/nim
powershell -ExecutionPolicy Bypass -File run_tests.bat
```

## Scala 版本兼容性

本项目已移除 `scala.collection.BuildFrom` 依赖，可兼容：
- Scala 2.11.x（Spark 2.4.3 默认使用 2.11.12）
- Scala 2.12.x
- Scala 2.13.x

集合操作符（`|>>`、`|?>`、`|*>`）直接使用 `Iterable` 的原生方法实现。

## 设计说明

- 仅使用各语言标准库，不引入外部依赖。
- 通过扩展方法/隐式类为函数、值、可迭代对象添加中缀操作符。
- 解包操作符对 Tuple 返回类型做编译期全解包；对 Seq 返回类型取首元素。
- 反向操作符与正向操作符语义完全一致，仅操作数书写顺序镜像。
