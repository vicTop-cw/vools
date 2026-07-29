# Vox 语言关键字分析报告

## 一、关键字总览

Vox 语言共定义了 **105 个关键字**（含大小写敏感变体），按功能分为 12 个类别。

### 1.1 关键字分类统计

| 类别 | 数量 | 关键字列表 |
|------|------|-----------|
| **声明类 (DECLARATION)** | 13 | val, var, const, def, struct, enum, class, trait, impl, extend, template, define, lazy |
| **控制流 (CONTROL_FLOW)** | 16 | if, elif, else, while, for, in, loop, match, when, where, break, continue, return, defer, guard |
| **异常处理 (EXCEPTION)** | 5 | try, catch, finally, raise, raises |
| **并发 (CONCURRENCY)** | 5 | async, await, go, spawn, yield |
| **操作符声明 (OPERATOR_DECL)** | 5 | prefix, infix, suffix, nthfix, pairfix |
| **元编程 (META)** | 6 | macro, comptime, transtime, external, include, is |
| **导入 (IMPORT)** | 4 | import, from, as, exclude |
| **测试 (TEST)** | 3 | test, suite, assert |
| **修饰符 (MODIFIER)** | 6 | pub, override, abstract, static, mut, owned |
| **字面量 (LITERAL)** | 5 | true, false, none, let, then |
| **类型引用 (TYPE_REF)** | 7 | Self, super, Type, Enum, Static, untyped, block |
| **其他 (OTHER)** | 4 | of, omit, ignore, with |

> **注**：keyword.py 定义了 12 类共 79 个；lexer 中实际识别 83 个（含 and, not, case, event 等），以 lexer 实际支持为准。

---

## 二、各关键字语法详解

### 2.1 声明类关键字

#### val / let（不可变绑定）
- **语法**：`val 名称[: 类型] = 表达式`
- **别名**：`let` 是 `val` 的别名（功能完全相同）
- **支持**：类型注解（可选）、初始化表达式（必选）
- **嵌套**：可在任意块级作用域内使用（函数内、if 内、循环内等）
- **多级**：不支持连续多级（每个 val 声明一个变量）

```vox
val x = 42
val name: str = "hello"
```

#### var（可变绑定）
- **语法**：`var 名称[: 类型] = 表达式`
- **支持**：类型注解（可选）、初始化表达式（必选）
- **嵌套**：同 val，任意块级作用域
- **多级**：不支持连续多级

```vox
var count = 0
var items: [int] = []
```

#### const（常量）
- **语法**：`const 名称[: 类型] = 常量表达式`
- **支持**：类型注解（可选）、常量表达式（必选）
- **嵌套**：只能在模块级或类/结构体的 static 区域
- **多级**：不支持连续多级

```vox
const PI = 3.14159
const MAX_SIZE: int = 1024
```

#### lazy（惰性求值）
- **语法**：`lazy [var/val] 名称[: 类型] = 表达式`
- **支持**：可选 var/val 修饰、类型注解（可选）
- **嵌套**：任意块级作用域
- **多级**：不支持连续多级

```vox
lazy val expensive = compute_expensive()
lazy var result = long_running_task()
```

#### def（函数定义）
- **语法**：
  ```
  def 名称[<泛型参数>]([参数列表])[-> 返回类型]:
      函数体
  ```
- **支持**：
  - 泛型参数：`<T, U>`
  - 参数：名称[:类型][=默认值]，支持 `*可变参数`
  - 返回类型：`-> 类型`（可选）
  - 文档注释：`///` 前缀
- **嵌套**：支持函数嵌套定义（函数内可再定义函数）
- **多级**：不支持连续多级 def（函数是独立的）
- **修饰符**：支持 `@decorator` 装饰器链

```vox
/// 这是一个示例函数
def add<T>(a: T, b: T) -> T:
    return a + b
```

#### struct（结构体）
- **语法**：
  ```
  struct 名称[<泛型参数>]:
      字段名: 类型
      ...
  ```
- **支持**：泛型参数、字段定义
- **嵌套**：不支持嵌套 struct 定义（仅模块级）
- **多级**：不支持连续多级
- **字段**：仅支持名称: 类型，不支持默认值

```vox
struct Point<T>:
    x: T
    y: T
```

#### class（类）
- **语法**：
  ```
  class 名称[(父类)]:
      字段名: 类型[= 默认值]
      def 方法名(): ...
  ```
- **支持**：
  - 单继承：`class Dog(Animal):`
  - 字段（含默认值）
  - 方法定义（def 开头）
- **嵌套**：不支持嵌套 class 定义
- **多级**：不支持连续多级

```vox
class Animal:
    name: str = ""
    def speak(self) -> str:
        return "..."
```

#### enum（枚举）
- **语法**：
  ```
  enum 名称[<泛型参数>]:
      变体名[([数据类型])]
      ...
  ```
- **支持**：泛型参数、变体数据（可选单类型）
- **嵌套**：不支持嵌套 enum 定义
- **多级**：不支持连续多级

```vox
enum Option<T>:
    None
    Some(T)
```

#### trait（特征/接口）
- **语法**：
  ```
  trait 名称[<泛型参数>]:
      def 方法名([参数])[-> 返回类型][: 默认实现]
      ...
  ```
- **支持**：泛型参数、方法签名、默认实现（可选）
- **嵌套**：不支持嵌套 trait 定义
- **多级**：不支持连续多级

```vox
trait Show:
    def show(self) -> str
    def describe(self) -> str:
        return "object"
```

#### impl（实现块）
- **语法**：
  ```
  impl [特征名 for] 类型名:
      方法定义
      ...
  ```
- **两种形式**：
  1. 固有实现：`impl TypeName:`
  2. 特征实现：`impl TraitName for TypeName:`
- **嵌套**：不支持嵌套 impl
- **多级**：不支持连续多级 impl

```vox
impl Show for Point:
    def show(self) -> str:
        return "({}, {})".format(self.x, self.y)
```

#### extend（扩展）
- **语法**：
  ```
  extend 扩展目标 for 类型:
      方法定义
      ...
  ```
- **功能**：为已有类型添加扩展方法
- **嵌套**：不支持嵌套 extend
- **多级**：不支持连续多级

```vox
extend MathUtils for int:
    def squared(self) -> int:
        return self * self
```

#### template（模板宏）
- **语法**：
  ```
  template 名称[<泛型>]([参数]):
      模板体
  ```
- **功能**：编译期文本替换宏，使用 `__参数名__` 引用参数
- **嵌套**：不支持嵌套 template
- **多级**：不支持连续多级

```vox
template double(x):
    __x__ + __x__
```

#### define（类型约束）
- **语法**：
  ```
  define 名称[<泛型>]:
      props:
          字段: 类型
      statics:
          静态方法
      typemethods:
          类型方法
      instancemethods:
          实例方法
      check:
          验证代码
  ```
- **支持 5 个区块**：props, statics, typemethods, instancemethods, check
- **嵌套**：不支持嵌套 define
- **多级**：不支持连续多级

```vox
define Sortable<T>:
    props:
        cmp: (T, T) -> int
    instancemethods:
        sort: (self) -> void
```

---

### 2.2 控制流关键字

#### if / elif / else（条件语句）
- **语法**：
  ```
  if 条件:
      then 体
  [elif 条件:
      elif 体]*
  [else:
      else 体]
  ```
- **支持**：任意多级 elif 链（无数量限制）
- **嵌套**：完全支持任意深度嵌套
- **三元表达式**：支持 `值 if 条件 else 另一个值`（表达式形式）

```vox
// 语句形式
if x > 10:
    print("big")
elif x > 5:
    print("medium")
else:
    print("small")

// 表达式形式（三元）
val size = "big" if x > 10 else "small"
```

#### for / in（for 循环）
- **语法**：
  ```
  for 变量 in 可迭代对象 [if 守卫条件]:
      循环体
  [else:
      else 体]
  ```
- **支持**：
  - `in` 关键字（必选）
  - 守卫条件 `if`（可选，过滤迭代）
  - `else` 子句（可选，循环正常结束时执行）
- **嵌套**：完全支持任意深度嵌套
- **多级**：不支持连续多级 for（每个 for 独立）

```vox
for i in range(10):
    print(i)

for x in items if x > 0:
    print(x)
```

#### while（while 循环）
- **语法**：
  ```
  while 条件:
      循环体
  [else:
      else 体]
  ```
- **支持**：else 子句（可选）
- **嵌套**：完全支持任意深度嵌套
- **多级**：不支持连续多级 while

```vox
while x > 0:
    x = x - 1
```

#### loop（无限循环）
- **语法**：
  ```
  loop:
      循环体
  ```
- **功能**：等价于 `while true`
- **嵌套**：完全支持任意深度嵌套
- **退出**：使用 `break`

```vox
loop:
    if done:
        break
    do_work()
```

#### break / continue
- **语法**：`break` / `continue`
- **作用**：跳出/继续当前循环
- **嵌套**：只影响当前最内层循环
- **多级**：不支持带标签的 break/continue（无 `break label`）

#### return（返回）
- **语法**：`return [表达式]`
- **支持**：有值返回、无值返回（返回 void/none）
- **嵌套**：在函数内任意位置可用
- **多级**：不支持多级 return

#### match（模式匹配）
- **语法**：
  ```
  match 表达式:
      模式 [if 守卫] => 体
      ...
  ```
- **支持的模式**：
  - 标识符模式：`name`
  - 字面量模式：`42`, `"hello"`
  - 通配符模式：`_`
- **守卫**：支持 `if 条件` 守卫
- **分支体**：单行表达式 或 多行缩进块
- **嵌套**：支持嵌套 match（模式内暂不支持嵌套结构）
- **多级**：不支持连续多级 match

```vox
match c:
    Red => print("red")
    Green if bright => print("bright green")
    _ => print("other")
```

#### when / where / guard / defer
- **when**：用在 match 分支（但当前实现用的是 `if` 守卫，不是 `when`）
- **where**：keyword.py 定义但 parser 中未实现
- **guard**：keyword.py 定义但 parser 中未实现
- **defer**：keyword.py 定义但 parser 中未实现

---

### 2.3 异常处理关键字

#### try / catch / finally / raise / raises
- **状态**：keyword.py 中定义，lexer 中识别，但 parser 中**未实现**解析逻辑
- **当前支持情况**：仅作为关键字保留，无法使用

---

### 2.4 并发关键字

#### async / await / go / spawn / yield
- **状态**：keyword.py 中定义，lexer 中识别 `async`、`await`、`go`、`spawn`、`yield`
- **当前支持情况**：parser 中**未实现**这些关键字的解析逻辑
- **注意**：`yield` 在 lexer 中是关键字，但 parser 不支持

---

### 2.5 操作符声明关键字

#### prefix / infix / suffix / nthfix / pairfix
- **语法**：
  ```
  [prefix|infix|suffix|nthfix|pairfix] 符号 函数名([参数])[-> 返回类型]:
      函数体
  ```
- **5 种操作符类型**：
  - `prefix`：前缀操作符（如 `!x`）
  - `infix`：中缀操作符（如 `a + b`）
  - `suffix`：后缀操作符（如 `x++`）
  - `nthfix`：混合固定（不常用）
  - `pairfix`：配对固定（如 `QQxQQ`）
- **支持**：泛型参数、多参数、返回类型
- **嵌套**：不支持嵌套操作符声明
- **多级**：不支持连续多级声明

```vox
prefix ! not_op(x: bool) -> bool:
    return not x

infix + add_op(a: int, b: int) -> int:
    return a + b

suffix ++ inc_op(x: int) -> int:
    return x + 1
```

---

### 2.6 元编程关键字

#### comptime（编译期执行块）
- **语法**：
  ```
  comptime:
      编译期代码
  ```
- **功能**：在 Rust 编译期执行（生成 const 等）
- **嵌套**：不支持嵌套 comptime
- **多级**：不支持连续多级

```vox
comptime:
    const PI = 3.14159
```

#### transtime（转译期执行块）
- **语法**：
  ```
  transtime:
      转译期代码
  ```
- **功能**：在 Vox 转译阶段执行（可修改 Cargo.toml、生成文件等）
- **嵌套**：不支持嵌套 transtime
- **多级**：不支持连续多级

```vox
transtime:
    toml.dependency("serde", "1.0")
    config.set("edition", "2021")
```

#### macro / external / include / is
- **macro**：keyword.py 定义，lexer 中未找到实现
- **external**：keyword.py 定义，lexer 识别，parser 未实现
- **include**：keyword.py 定义，lexer 识别，parser 未实现
- **is**：keyword.py 定义，lexer 识别，当前未作为操作符使用（用 `==` 代替）

---

### 2.7 导入关键字

#### import（导入模块）
- **语法**：
  ```
  import 模块路径[.子模块...][:: { 项1, 项2 }]
  import 模块路径 as 别名
  ```
- **支持**：
  - 多级模块路径：`std.collections`
  - 选择性导入：`:: { item1, item2 }`
  - 别名导入：`as alias`
- **嵌套**：不支持嵌套 import（仅模块级）
- **多级路径**：支持任意多级点分隔路径

```vox
import std.math
import std.collections::{ HashMap, HashSet }
import std.io as io
```

#### from（从...导入）
- **语法**：
  ```
  from 模块路径 import 项1[, 项2, ...]
  ```
- **支持**：多级模块路径、多导入项
- **嵌套**：不支持嵌套
- **多级路径**：支持任意多级点分隔路径

```vox
from math import sin, cos
from std.collections import HashMap
```

#### as（别名）
- **用法**：
  - `import module as alias`（模块别名）
  - 其他场景暂不支持（如 import 项别名）

#### exclude（排除导入）
- **语法**：
  ```
  exclude 模块路径 { 项1, 项2 }
  exclude 模块路径:
      项1
      项2
  ```
- **两种形式**：大括号形式、缩进块形式
- **功能**：导入模块中除列出项外的所有内容
- **支持**：多级模块路径（`.` 或 `::` 分隔）
- **嵌套**：不支持嵌套
- **多级路径**：支持

```vox
exclude std.collections { HashMap, HashSet }

exclude std.math:
    sin
    cos
```

---

### 2.8 测试关键字

#### test（测试用例）
- **语法**：
  ```
  test 测试名:
      测试体
  ```
- **嵌套**：不支持嵌套 test
- **多级**：不支持连续多级

```vox
test addition:
    val r = add(2, 3)
    assert(r == 5)
```

#### suite（测试套件）
- **语法**：
  ```
  suite 套件名:
      测试定义/代码
  ```
- **功能**：组织一组相关测试
- **嵌套**：不支持嵌套 suite
- **多级**：不支持连续多级

#### assert（断言）
- **状态**：keyword.py 定义，lexer 识别
- **当前实现**：parser 中未单独解析，作为函数调用处理

---

### 2.9 修饰符关键字

#### pub / override / abstract / static / mut / owned
- **状态**：keyword.py 中定义，lexer 中部分识别（`mut`, `owned`）
- **当前支持情况**：parser 中**未实现**修饰符语法
- **注意**：这些是关键字保留字，但暂不可用

---

### 2.10 字面量关键字

#### true / false（布尔值）
- **语法**：`true` / `false`
- **类型**：Bool
- **嵌套**：可在任意表达式中使用
- **支持**：完全支持

#### none（空值）
- **语法**：`none`
- **类型**：None / Option 类型的空值
- **注意**：Vox 中同时存在 `None`（首字母大写，构造函数）和 `none`（小写，关键字字面量）

#### let（val 的别名）
- 同 `val`，不可变绑定

#### then
- **状态**：keyword.py 定义，lexer 识别
- **当前用法**：未在 parser 中作为独立关键字使用，主要用于 `if ... then ...` 相关概念

---

### 2.11 类型引用关键字

#### Self / super / Type / Enum / Static / untyped / block
- **Self**：指代当前类型（lexer 识别，parser 中未特殊处理）
- **super**：父类/父模块（lexer 识别，未实现）
- **Type**：类型元类型（lexer 识别，未实现）
- **Enum**：枚举元类型（lexer 识别，未实现）
- **Static**：静态元类型（lexer 识别，未实现）
- **untyped**：无类型标记（lexer 识别，未实现）
- **block**：块类型（lexer 识别，未实现）

---

### 2.12 其他关键字

#### ignore（忽略测试）
- **语法**：
  ```
  ignore test 测试名:
      测试体
  ignore test "字符串名":
      测试体
  ```
- **功能**：标记测试为忽略（不执行）
- **支持**：名称可用标识符或字符串字面量
- **嵌套**：不支持嵌套
- **多级**：不支持连续多级

```vox
ignore test slow_test:
    long_running()

ignore test "flaky test":
    flaky()
```

#### of / omit / with
- **of**：keyword.py 定义，未实现
- **omit**：keyword.py 定义，未实现
- **with**：keyword.py 定义，lexer 识别，未实现

---

## 三、嵌套支持情况总结

### 3.1 支持任意深度嵌套的结构

| 结构 | 嵌套支持 | 说明 |
|------|---------|------|
| **if / elif / else** | ✅ 完全支持 | if 内可再嵌套 if、for、while 等 |
| **for 循环** | ✅ 完全支持 | for 内可嵌套 for、if、while 等 |
| **while 循环** | ✅ 完全支持 | while 内可嵌套任意控制结构 |
| **loop 循环** | ✅ 完全支持 | loop 内可嵌套任意控制结构 |
| **match** | ✅ 支持（语句级） | match 内可嵌套其他语句 |
| **函数 def** | ✅ 支持 | 函数内可定义嵌套函数 |
| **val / var / const** | ✅ 支持 | 任意块级作用域内可声明变量 |
| **结构体/类方法** | ✅ 支持 | 方法体内可嵌套任意结构 |

### 3.2 不支持嵌套的结构

| 结构 | 嵌套支持 | 说明 |
|------|---------|------|
| **struct** | ❌ 不支持 | 不能在 struct 内定义 struct/class/enum |
| **class** | ❌ 不支持 | 不能在 class 内定义 class/struct/enum |
| **enum** | ❌ 不支持 | 不能在 enum 内定义其他类型 |
| **trait** | ❌ 不支持 | 不能在 trait 内定义其他 trait |
| **impl** | ❌ 不支持 | 不能嵌套 impl 块 |
| **extend** | ❌ 不支持 | 不能嵌套 extend 块 |
| **template** | ❌ 不支持 | 不能嵌套 template |
| **define** | ❌ 不支持 | 不能嵌套 define |
| **comptime** | ❌ 不支持 | 不能嵌套 comptime |
| **transtime** | ❌ 不支持 | 不能嵌套 transtime |
| **test / suite** | ❌ 不支持 | 不能嵌套 test/suite |

---

## 四、连续多级支持情况总结

### 4.1 支持连续多级的结构

| 结构 | 多级支持 | 说明 |
|------|---------|------|
| **模块路径（import）** | ✅ 任意多级 | `import a.b.c.d` |
| **模块路径（from import）** | ✅ 任意多级 | `from a.b.c import x` |
| **elif 链** | ✅ 任意多级 | `if ... elif ... elif ... else ...` |
| **方法调用链** | ✅ 任意多级 | `obj.method1().method2().method3()` |
| **属性访问链** | ✅ 任意多级 | `obj.field1.field2.field3` |
| **泛型嵌套** | ✅ 任意多级 | `List<Map<str, int>>` |
| **类型嵌套** | ✅ 任意多级 | `[int?]??`（多重可选） |
| **装饰器链** | ✅ 任意多级 | `@a @b @c def f():` |

### 4.2 不支持连续多级的结构

| 结构 | 多级支持 | 说明 |
|------|---------|------|
| **val / var** | ❌ 不支持 | 每个变量独立声明（无 `val a, b = 1, 2`） |
| **for 循环** | ❌ 不支持 | 每个 for 独立（无 `for x in a for y in b`） |
| **def 函数** | ❌ 不支持 | 每个函数独立定义 |
| **struct / class / enum** | ❌ 不支持 | 每个类型独立定义 |
| **impl / extend** | ❌ 不支持 | 每个实现块独立 |
| **match** | ❌ 不支持 | 每个 match 独立 |
| **break / continue** | ❌ 不支持 | 无标签 break/continue（不能跳出多层循环） |

---

## 五、已实现 vs 未实现关键字清单

### 5.1 已完全实现（Parser 中可解析）

共 **47 个**关键字：

1. **声明类**：val, var, const, def, struct, class, enum, trait, impl, extend, template, define, lazy, let
2. **控制流**：if, elif, else, for, in, while, loop, break, continue, return, match
3. **操作符声明**：prefix, infix, suffix, nthfix, pairfix
4. **元编程**：comptime, transtime
5. **导入**：import, from, as, exclude
6. **测试**：test, suite, ignore
7. **字面量**：true, false, none
8. **其他**：not（操作符，非关键字但识别）

### 5.2 仅 lexer 识别，未实现解析

共 **36 个**关键字：

1. **异常处理**：try, catch, finally, raise, raises
2. **并发**：async, await, go, spawn, yield
3. **元编程**：macro, external, include, is
4. **修饰符**：pub, override, abstract, static, mut, owned
5. **类型引用**：Self, super, Type, Enum, Static, untyped, block
6. **控制流**：when, where, guard, defer
7. **字面量**：then
8. **测试**：assert
9. **其他**：of, omit, with

### 5.3 keyword.py 有但 lexer 没有的

共 **0 个**（lexer 是 keyword.py 的超集）

### 5.4 lexer 有但 keyword.py 没有的

共 **4 个**：
- `and`：逻辑与操作符（当前用 `&&`，但 lexer 也识别 and）
- `not`：逻辑非操作符（关键字）
- `case`：可能是 match 的 case（未实现）
- `event`：事件声明（未实现）

---

## 六、语法特性亮点

### 6.1 类型系统
- 泛型：`<T, U>` 语法，支持 struct、enum、trait、函数、template
- 可选类型：`T?` 语法（等价于 `Option<T>`），支持 `T??` 多重可选
- 列表类型：`[T]` 简写语法
- 字典类型：`{: K: V}` 字面值 + `Dict<K,V>` 泛型
- 元组类型：`(T1, T2, T3)`
- 函数类型：`(T1, T2) -> R`
- 多级路径类型：`module.SubType`

### 6.2 表达式系统
- 三元表达式：`a if cond else b`（Python 风格）
- Lambda：`|params| body` 语法
- 方法链：连续 `.method()` 调用
- 属性链：连续 `.field` 访问
- 索引：`expr[index]`

### 6.3 模块系统
- 多级点路径：`a.b.c`
- 双冒号导入项：`module::{item1, item2}`
- from import：`from module import item1, item2`
- exclude 排除导入
- 别名导入：`import mod as alias`

### 6.4 元编程
- template 模板宏（文本替换）
- comptime 编译期块
- transtime 转译期块
- define 类型约束

### 6.5 测试框架
- test 测试用例
- suite 测试套件
- ignore 忽略测试
- 字符串命名测试

---

## 七、参考文件

- 关键字定义：[keyword.py](file:///e:/IDEProjects/AI/vools/voxc/voxc-py/voxc/libs/keyword.py)
- 词法分析：[lexer/__init__.py](file:///e:/IDEProjects/AI/vools/voxc/voxc-py/voxc/lexer/__init__.py)
- 语法解析：[parser/__init__.py](file:///e:/IDEProjects/AI/vools/voxc/voxc-py/voxc/parser/__init__.py)
- AST 节点：[ast_nodes.py](file:///e:/IDEProjects/AI/vools/voxc/voxc-py/voxc/ast_nodes.py)
