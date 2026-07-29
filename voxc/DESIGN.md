# Vox 语言设计文档

## 1. 关键字分类

### 1.1 声明关键字
| 关键字 | 用途 | 示例 |
|--------|------|------|
| `val` | 不可变变量声明 | `val x = 10` |
| `var` | 可变变量声明 | `var x = 10` |
| `const` | 编译期常量 | `const PI = 3.14` |
| `def` | 函数定义 | `def add(a: int, b: int) -> int:` |
| `struct` | 结构体定义 | `struct Point: x: int, y: int` |
| `enum` | 枚举定义 | `enum Color: Red, Green, Blue` |
| `class` | 类定义 | `class Animal: name: str` |
| `trait` | 特性定义 | `trait Show: def show(self) -> void` |
| `impl` | 实现块 | `impl Show for Point:` |
| `extend` | 扩展类型 | `extend Debug for Point:` |
| `template` | 模板声明 | `template Vec(T): ...` |
| `define` | 类型约束 | `define Number = int | float` |

### 1.2 流程控制关键字
| 关键字 | 用途 | 示例 |
|--------|------|------|
| `if` / `elif` / `else` | 条件分支 | `if x > 0: ...` |
| `while` | 循环 | `while x > 0: ...` |
| `for` / `in` | 迭代 | `for x in list:` |
| `loop` | 无限循环 | `loop: ...` |
| `match` | 模式匹配 | `match c: Red => ...` |
| `when` / `where` | 守卫子句 | |
| `break` / `continue` | 循环控制 | |
| `return` | 返回 | `return x` |
| `defer` | 延迟执行 | `defer file.close()` |
| `guard` | 提前返回 | `guard let Some(x) = opt else: return` |

### 1.3 限定关键字（不能单独使用）
| 关键字 | 配合使用 | 语义 |
|--------|----------|------|
| `let` | `if` / `while` | 条件绑定：`let Some(x) = opt if condition` |
| `mut` | 参数修饰 | 可变参数：`def foo(mut x: int)` |
| `owned` | 参数修饰 | 获取所有权：`def foo(owned x: String)` |
| `then` | `if` 表达式 | `x if cond then y else z` |

#### `let` 绑定语义
```
// let-if: 条件绑定（类似 Swift 的 if-let）
let Some(x) = opt:
    print(x)       // x 已解包
else:
    print("none")

// let-while: 循环绑定（类似 Rust 的 while-let）
let Some(line) = reader.next():
    process(line)
```

### 1.4 编译期关键字
| 关键字 | 执行层 | 用途 |
|--------|--------|------|
| `comptime` | Rust 编译层 | 生成 `const` 代码，由 rustc 评估 |
| `transtime` | Vox 转译层 | 修改 Cargo.toml、生成文件、配置构建 |

### 1.5 元编程关键字
| 关键字 | 用途 |
|--------|------|
| `macro` | 宏定义 |
| `Include` | 编译期包含 |
| `is` | 类型检查 `x is Type` |

### 1.6 测试关键字
| 关键字 | 用途 |
|--------|------|
| `test` | 单元测试函数 |
| `suite` | 测试模块 |
| `assert` | 断言 |

### 1.7 并发关键字
| 关键字 | 用途 |
|--------|------|
| `async` / `await` | 异步 |
| `go` | goroutine 式并发 |
| `spawn` | 线程生成 |

### 1.8 操作符声明关键字
| 关键字 | 用途 |
|--------|------|
| `prefix` / `infix` / `suffix` | 操作符位置 |
| `nthfix` / `pairfix` | 特殊操作符 |

---

## 2. 自引用类型设计

### 2.1 问题

Rust 中链表节点需要 `Option<Box<Node>>`：
```rust
struct Node {
    value: i64,
    next: Option<Box<Node>>,  // 必须套 Box 因为大小不确定
}
```

### 2.2 Vox 方案：自动推断

Vox 端直接写类型名，编译器自动检测自引用并包裹：

```vox
struct Node:
    value: int
    next: Node?       // 自动生成 Option<Box<Node>>

// 使用时直接操作
var head = Node(1, Node(2, Node(3, None)))
print(head.next.value)     // 自动解引用
```

### 2.3 智能指针选择：字段装饰器

默认 `Box`，通过装饰器选择其他智能指针：

```vox
struct TreeNode:
    value: int
    left: TreeNode?           // 默认 → Option<Box<TreeNode>>（独占所有权）
    @arc right: TreeNode?     // → Option<Arc<Mutex<TreeNode>>>（多线程共享）
    @rc parent: TreeNode?    // → Option<Rc<RefCell<TreeNode>>>（单线程共享）
```

### 2.4 装饰器列表

| 装饰器 | 生成类型 | 场景 |
|--------|----------|------|
| (默认) | `Box<T>` | 独占所有权，树结构 |
| `@arc` | `Arc<Mutex<T>>` | 多线程共享，图结构 |
| `@rc` | `Rc<RefCell<T>>` | 单线程共享，双向链表 |
| `@raw` | `*mut T` | 不安全指针，FFI |

### 2.5 代码生成规则

1. 检测结构体字段是否引用自身（或形成循环引用）
2. 自引用字段自动包裹 `Box<T>`
3. 可选字段 `T?` 生成 `Option<Box<T>>`
4. 字段访问自动解包：`node.next` → `node.next.as_ref().unwrap().deref()`
5. 字段赋值自动包裹：`node.next = Node(...)` → `node.next = Some(Box::new(Node(...)))`

---

## 3. inspect 模块

### 3.1 API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `inspect.source(fn)` | 函数名 | `str` | 获取函数源代码 |
| `inspect.signature(fn)` | 函数名 | `str` | 获取函数签名 |
| `inspect.getfile(fn)` | 函数名 | `str` | 获取定义文件路径 |
| `inspect.getsourcelines(fn)` | 函数名 | `[str]` | 获取源代码行列表 |
| `inspect.lineno(fn)` | 函数名 | `int` | 获取起始行号 |

### 3.2 编译期展开

所有 `inspect.*` 调用在 Vox→Rust 转译期展开为字符串字面量。

---

## 4. reflect 模块

### 4.1 API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `reflect.type_name(T)` | 类型名 | `str` | 获取类型名 |
| `reflect.fields(T)` | 类型名 | `[str]` | 获取字段名列表 |
| `reflect.field_types(T)` | 类型名 | `[(str, str)]` | 获取字段名+类型对 |
| `reflect.methods(T)` | 类型名 | `[str]` | 获取方法名列表 |
| `reflect.variants(E)` | 枚举名 | `[str]` | 获取枚举变体列表 |
| `reflect.is_struct(T)` | 类型名 | `bool` | 是否为结构体 |
| `reflect.is_enum(E)` | 枚举名 | `bool` | 是否为枚举 |
| `reflect.is_class(T)` | 类型名 | `bool` | 是否为类 |
| `reflect.is_trait(T)` | 类型名 | `bool` | 是否为 trait |
| `reflect.has_trait(T, Trait)` | 类型名, trait名 | `bool` | 是否实现了某 trait |

### 4.2 编译期展开

所有 `reflect.*` 调用在 Vox→Rust 转译期展开为对应值。
