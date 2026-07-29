# Vox 实现优先级规划

## 目标

确定 Vox 编译器从当前状态到可用 MVP 的实现顺序，按优先级分阶段推进，确保每个阶段都能产出可运行的功能。

---

## 当前状态评估

### ✅ 已实现

| 类别 | 功能 | 状态 |
|------|------|------|
| 词法分析 | 完整关键字集、运算符、缩进敏感 | 完成 |
| 语法分析 | import/from/as, lazy, transtime/comptime, let-if/while | 完成 |
| 代码生成 | 基础类型、函数、struct/enum/class/trait/impl | 完成 |
| 自引用类型 | 自动 Box 包裹、@arc/@rc/@raw 装饰器 | 完成 |
| inspect | 编译期展开，完全透明 | 完成 |
| reflect | 运行时 VoxReflect trait | 完成 |
| tracker | source map + panic hook | 完成 |
| lazy | LazyLock 延迟求值 | 完成 |
| import | use 语句生成 | 完成 |

### ❌ 缺失核心功能

| 类别 | 缺失项 | 影响 |
|------|--------|------|
| Builtins | print/len/type/str/int/float/bool/None | 无法输出和基本类型转换 |
| std.io | 文件读写 | 无法处理文件 |
| std.collections | Vec/HashMap | 无法使用容器 |
| std.result | Result 类型 + `?` 操作符 | 无法优雅处理错误 |
| std.option | Option 类型 | 无法表达空值 |
| sys | 命令行参数、环境变量 | 无法交互 |
| os | 文件系统操作 | 无法操作文件系统 |
| CLI | 多文件编译 | import 无法跨文件 |

---

## 实现优先级总览

```
Phase 0: 基础设施（当前）
    └── 词法/语法/代码生成/自引用/inspect/reflect/tracker/lazy/import

Phase 1: 最小可用（MVP）
    ├── Builtins (print/len/type/str/int/float/bool)
    ├── std.option (Option 类型 + ? 后缀)
    ├── std.result (Result 类型 + ? 操作符)
    └── std.io (println/print)

Phase 2: 实用开发
    ├── std.collections (Vec/HashMap)
    ├── sys (命令行参数/环境变量)
    ├── std.convert (as/into/try_into)
    └── std.fmt (格式化)

Phase 3: 系统交互
    ├── os (文件系统操作)
    ├── std.fs (文件读写)
    ├── std.path (路径处理)
    └── CLI 多文件编译

Phase 4: 高级特性
    ├── async/await
    ├── go/spawn 并发
    ├── macro 系统
    ├── template 系统
    └── define 类型约束
```

---

## Phase 1: 最小可用（MVP）

### 优先级 1.1: Builtins

**理由**：没有 builtins 就无法做任何有意义的输出和类型转换。

| 函数 | 生成 Rust | 优先级 | 依赖 |
|------|-----------|--------|------|
| `print(expr)` | `print!("{}", expr)` | P0 | 基本类型 |
| `println(expr)` | `println!("{}", expr)` | P0 | 基本类型 |
| `len(x)` | `x.len()` | P0 | Vec/String/HashMap |
| `type(x)` | `reflect::type_name(x)` | P1 | reflect |
| `str(x)` | `x.to_string()` | P1 | Display trait |
| `int(x)` | `x as i64` | P1 | 类型转换 |
| `float(x)` | `x as f64` | P1 | 类型转换 |
| `bool(x)` | `x != 0` | P2 | 基本类型 |
| `None` | `None` | P0 | Option |

**实现要点**：
- `print`/`println` 支持可变参数：`print(a, b, c)` → `print!("{}{}{}", a, b, c)`
- `len` 为多态函数，支持 Vec/String/HashMap
- 所有 builtins 在代码生成时直接映射，不需要额外模块

### 优先级 1.2: std.option

**理由**：`T?` 类型语法已经实现，但需要运行时 `Option` 类型支持。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| Option 类型 | `T?` | `Option<T>` | P0 |
| Some | `Some(x)` | `Some(x)` | P0 |
| None | `None` | `None` | P0 |
| 解包 | `x?` (后缀) | `x.expect("...")` | P0 |
| 匹配 | `match opt: Some(x) => ...` | Rust match | P0 |
| 空合并 | `a ?? b` | `a.unwrap_or(b)` | P1 |
| 安全导航 | `a?.b` | `a.as_ref().map(|x| &x.b)` | P1 |

**实现要点**：
- `T?` → `Option<T>`（已部分实现，需完善）
- `expr?` 后缀操作符生成 `.expect()` 或 `?`（需根据上下文决定）
- `a?.b` → `.and_then(|x| x.b)` 链式调用

### 优先级 1.3: std.result

**理由**：错误处理是编程语言的核心，`?` 操作符依赖 Result。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| Result 类型 | `Result<T, E>` | `Result<T, E>` | P0 |
| Ok | `Ok(x)` | `Ok(x)` | P0 |
| Err | `Err(e)` | `Err(e)` | P0 |
| `?` 操作符 | `expr?` | `expr?` | P0 |
| raises 声明 | `def foo() -> int raises IOError:` | 返回 Result | P1 |
| try-catch | `try: ... catch IOError: ...` | `match result { Ok(v) => ..., Err(e) => ... }` | P1 |

**实现要点**：
- `def foo() -> int raises IOError:` → 返回 `Result<i64, IOError>`
- `try { ... } catch e { ... }` → `match` 语句
- `expr?` 在函数返回 Result 时生成 `expr?`，否则生成 `.unwrap()`

### 优先级 1.4: std.io

**理由**：与用户交互的基础。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 标准输出 | `print("hello")` | `print!("hello")` | P0 |
| 标准输出换行 | `println("hello")` | `println!("hello")` | P0 |
| 标准输入 | `input()` | `io::stdin().read_line(...)` | P1 |
| 文件写入 | `File.write("path", content)` | `std::fs::write(...)` | P1 |
| 文件读取 | `File.read("path")` | `std::fs::read_to_string(...)` | P1 |

**实现要点**：
- `print`/`println` 作为 builtins 实现
- `File` 类提供静态方法

---

## Phase 2: 实用开发

### 优先级 2.1: std.collections

**理由**：没有容器类型，程序无法处理复杂数据。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| Vec | `[1, 2, 3]` 或 `Vec<int>()` | `Vec<i64>` | P0 |
| Vec.push | `vec.push(x)` | `vec.push(x)` | P0 |
| Vec.pop | `vec.pop()` | `vec.pop()` | P0 |
| Vec.len | `len(vec)` | `vec.len()` | P0 |
| Vec.get | `vec[i]` | `vec[i]` | P0 |
| HashMap | `{: a: 1, b: 2}` 或 `HashMap<str, int>()` | `HashMap<String, i64>` | P0 |
| HashMap.get | `map["key"]` | `map.get("key").unwrap()` | P0 |
| HashMap.set | `map["key"] = value` | `map.insert("key".to_string(), value)` | P0 |
| HashSet | `{1, 2, 3}` | `HashSet<i64>` | P2 |

**实现要点**：
- `{:}` 表示空字典，`{}` 表示空集合（与 Python 相反）
- `[1, 2, 3]` → `vec![1, 2, 3]`
- `{: a: 1}` → `HashMap::from([("a", 1)])`

### 优先级 2.2: sys 模块

**理由**：命令行参数和环境变量是 CLI 程序的基础。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 命令行参数 | `sys.args` | `std::env::args()` | P0 |
| 环境变量 | `sys.env["KEY"]` | `std::env::var("KEY")` | P1 |
| 程序名 | `sys.prog_name` | `std::env::current_exe()` | P2 |
| 退出码 | `sys.exit(code)` | `std::process::exit(code)` | P1 |

### 优先级 2.3: std.convert

**理由**：类型转换是语言流畅性的关键。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 类型转换 | `x as int` | `x as i64` | P0 |
| 显式转换 | `int(x)` | `x as i64` | P0 |
| Into trait | `x.into()` | `Into::into(x)` | P1 |
| TryInto | `x.try_into()` | `TryInto::try_into(x)` | P2 |

### 优先级 2.4: std.fmt

**理由**：格式化输出是调试和用户交互的基础。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 格式化字符串 | `f"hello {name}"` | `format!("hello {}", name)` | P0 |
| Debug 输出 | `print("{:?}", x)` | `print!("{:?}", x)` | P1 |
| Display | 自动生成 `Display` impl | `#[derive(Debug)]` | P0 |

---

## Phase 3: 系统交互

### 优先级 3.1: os 模块

**理由**：文件系统操作是实际应用的必需功能。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 当前目录 | `os.cwd()` | `std::env::current_dir()` | P0 |
| 改变目录 | `os.chdir(path)` | `std::env::set_current_dir(path)` | P1 |
| 环境变量 | `os.getenv(key)` | `std::env::var(key)` | P1 |
| 环境变量设置 | `os.setenv(key, value)` | `std::env::set_var(key, value)` | P2 |
| 执行命令 | `os.system(cmd)` | `std::process::Command::new(...)` | P2 |

### 优先级 3.2: std.fs

**理由**：文件读写是数据处理的基础。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 读取文件 | `fs.read(path)` | `std::fs::read_to_string(path)` | P0 |
| 写入文件 | `fs.write(path, content)` | `std::fs::write(path, content)` | P0 |
| 创建目录 | `fs.mkdir(path)` | `std::fs::create_dir(path)` | P1 |
| 删除文件 | `fs.remove(path)` | `std::fs::remove_file(path)` | P1 |
| 列出目录 | `fs.list(path)` | `std::fs::read_dir(path)` | P1 |
| 文件存在 | `fs.exists(path)` | `std::path::Path::new(path).exists()` | P0 |

### 优先级 3.3: std.path

**理由**：路径处理是文件操作的基础。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 路径连接 | `path.join("a", "b")` | `Path::new("a").join("b")` | P0 |
| 文件名 | `path.file_name(path)` | `Path::new(path).file_name()` | P1 |
| 扩展名 | `path.extension(path)` | `Path::new(path).extension()` | P1 |
| 绝对路径 | `path.abs(path)` | `fs::canonicalize(path)` | P1 |

### 优先级 3.4: CLI 多文件编译

**理由**：当前 import 只生成 use 语句，不会编译依赖的 .vox 文件。

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 依赖图解析 | 解析 import 语句，构建依赖树 | P0 |
| 多文件转译 | 按依赖顺序转译所有 .vox 文件 | P0 |
| 模块组织 | 生成 Rust mod 结构 | P0 |
| 增量编译 | 仅重新编译修改的文件 | P2 |

---

## Phase 4: 高级特性

### 优先级 4.1: async/await

**理由**：异步编程是现代语言的必备特性。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| async 函数 | `async def foo(): ...` | `async fn foo() { ... }` | P1 |
| await | `await expr` | `await expr` | P1 |
| async main | `async def main(): ...` | `#[tokio::main]` | P2 |

### 优先级 4.2: go/spawn 并发

**理由**：并行执行是高性能程序的基础。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| go 协程 | `go foo()` | `std::thread::spawn(|| foo())` | P2 |
| spawn 线程 | `spawn foo()` | `std::thread::spawn(|| foo())` | P2 |
| 通道 | `chan = Channel<int>()` | `std::sync::mpsc::channel()` | P2 |

### 优先级 4.3: macro 系统

**理由**：宏是元编程的核心。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 宏定义 | `macro foo($x): ...` | Rust macro_rules | P3 |
| 宏调用 | `foo!(arg)` | `foo!(arg)` | P3 |
| 过程宏 | 编译期函数 | Rust proc macro | P4 |

### 优先级 4.4: template 系统

**理由**：模板是代码复用的高级形式。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| 模板定义 | `template Vec(T): ...` | Rust generic struct | P3 |
| 模板实例化 | `Vec<int>()` | `Vec<i64>::new()` | P3 |

### 优先级 4.5: define 类型约束

**理由**：define 是结构类型约束的核心。

| 功能 | Vox 语法 | 生成 Rust | 优先级 |
|------|----------|-----------|--------|
| define 声明 | `define Number = int | float` | Rust trait | P3 |
| define 约束 | `def foo(x: Number)` | Trait bound | P3 |

---

## 关键字实现优先级

### 已实现（✅）

| 关键字 | 类别 | 状态 |
|--------|------|------|
| val, var, const | 声明 | ✅ |
| def, struct, enum, class, trait, impl | 声明 | ✅ |
| if, elif, else, while, for, in, loop | 控制 | ✅ |
| match, break, continue, return | 控制 | ✅ |
| defer, guard, let | 控制 | ✅ |
| mut, owned | 参数修饰 | ✅ |
| comptime, transtime | 编译期 | ✅ |
| lazy, import, from, as | 其他 | ✅ |
| test, suite, assert | 测试 | ✅ |

### 待实现（按优先级）

| 关键字 | 类别 | 优先级 | 依赖 |
|--------|------|--------|------|
| Some, None | 标准库 | P0 | std.option |
| Ok, Err | 标准库 | P0 | std.result |
| async, await | 并发 | P1 | Phase 4.1 |
| go, spawn | 并发 | P2 | Phase 4.2 |
| macro | 元编程 | P3 | Phase 4.3 |
| template | 元编程 | P3 | Phase 4.4 |
| define | 类型约束 | P3 | Phase 4.5 |
| Include | 编译期 | P3 | 文件系统 |
| external | FFI | P4 | Rust FFI |

---

## 语句实现优先级

### 已实现（✅）

| 语句 | 状态 |
|------|------|
| VarDecl, ConstDecl, LazyDecl | ✅ |
| FnDef, StructDef, EnumDef, ClassDef, TraitDef | ✅ |
| ImplBlock, ExtendDecl | ✅ |
| IfStmt, WhileLoop, ForLoop, LoopStmt | ✅ |
| MatchStmt, ReturnStmt, BreakStmt, ContinueStmt | ✅ |
| TryBlock, RaiseStmt, DeferStmt, GuardStmt | ✅ |
| ImportStmt, FromImport | ✅ |
| ExprStmt, AssignStmt | ✅ |
| ComptimeBlock, TranstimeBlock | ✅ |

### 待实现（按优先级）

| 语句 | 语法 | 优先级 | 依赖 |
|------|------|--------|------|
| TryExpr | `expr?` 后缀 | P0 | std.result |
| SafeNav | `a?.b` | P1 | std.option |
| NullCoalesce | `a ?? b` | P1 | std.option |
| MacroExpr | `foo!(args)` | P3 | macro 系统 |
| TemplateInvoke | `Vec<int>(...)` | P3 | template 系统 |
| EventDecl/EventFire | `event Foo(...)` | P4 | 事件系统 |

---

## 依赖关系图

```
                    ┌──────────────────────────────┐
                    │     Phase 1: MVP             │
                    │  Builtins + Option + Result  │
                    │        + std.io              │
                    └─────────────┬────────────────┘
                                  │
                    ┌─────────────▼────────────────┐
                    │     Phase 2: 实用开发          │
                    │  std.collections + sys        │
                    │  + std.convert + std.fmt     │
                    └─────────────┬────────────────┘
                                  │
                    ┌─────────────▼────────────────┐
                    │     Phase 3: 系统交互          │
                    │  os + std.fs + std.path       │
                    │  + CLI 多文件编译             │
                    └─────────────┬────────────────┘
                                  │
                    ┌─────────────▼────────────────┐
                    │     Phase 4: 高级特性          │
                    │  async/await + go/spawn       │
                    │  + macro + template + define │
                    └──────────────────────────────┘
```

**关键依赖链**：
1. Builtins → std.option → std.result → std.io
2. std.result → `?` 操作符 → std.fs
3. std.collections → std.convert → 类型推导
4. CLI 多文件编译 → import → 所有模块

---

## 推荐执行顺序（按周计划）

### Week 1: Phase 1 MVP

- Day 1-2: Builtins（print/println/len/type/str/int/float）
- Day 3-4: std.option（Option 类型 + ? 后缀 + ?? + ?.）
- Day 5: std.result（Result 类型 + ? 操作符 + raises）
- Day 6: std.io（文件读写基础）
- Day 7: 集成测试

### Week 2: Phase 2 实用开发

- Day 1-3: std.collections（Vec/HashMap/HashSet）
- Day 4: sys 模块（args/env/exit）
- Day 5: std.convert（as/into/try_into）
- Day 6: std.fmt（格式化字符串）
- Day 7: 集成测试

### Week 3: Phase 3 系统交互

- Day 1-2: os 模块（cwd/chdir/getenv/setenv）
- Day 3-4: std.fs（read/write/mkdir/remove/list/exists）
- Day 5: std.path（join/file_name/extension/abs）
- Day 6-7: CLI 多文件编译（依赖图 + 增量编译）

### Week 4: Phase 4 高级特性

- Day 1-2: async/await
- Day 3: go/spawn 并发
- Day 4-5: macro 系统
- Day 6: template 系统
- Day 7: define 类型约束

---

## 成功标准

### Phase 1 MVP 成功标准

- ✅ 能运行 `hello.vox` 输出 "Hello World"
- ✅ 能运行 `print(1 + 2)` 输出 "3"
- ✅ 能运行 `let Some(x) = opt: print(x)` 条件绑定
- ✅ 能运行 `def foo() -> int raises Error:` 返回 Result
- ✅ 能运行 `std.io.File.write("test.txt", "hello")`

### Phase 2 成功标准

- ✅ 能运行 `vec = [1, 2, 3]; vec.push(4); print(len(vec))`
- ✅ 能运行 `map = {: a: 1}; map["b"] = 2; print(map["a"])`
- ✅ 能运行 `print(sys.args)` 输出命令行参数
- ✅ 能运行 `print(f"hello {name}")` 格式化字符串

### Phase 3 成功标准

- ✅ 能运行 `os.chdir("/tmp"); print(os.cwd())`
- ✅ 能运行 `fs.write("data.txt", "content"); print(fs.read("data.txt"))`
- ✅ 能运行多文件项目：`import utils; utils.foo()`

### Phase 4 成功标准

- ✅ 能运行 `async def fetch(): await http.get(...)`
- ✅ 能运行 `go background_task()` 并发执行
- ✅ 能运行 `macro repeat($n, $body): ...` 宏
- ✅ 能运行 `template Vec(T): ...` 模板
- ✅ 能运行 `define Number = int | float` 类型约束

---

## 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| `?` 操作符上下文依赖 | 需要知道函数返回类型是否为 Result | 在代码生成前做类型推断 |
| 多文件编译复杂度高 | import 依赖图解析困难 | 从简单的线性依赖开始 |
| async 需要运行时 | tokio 依赖增加编译时间 | 可选启用，默认不引入 |
| macro 系统复杂 | 完整宏系统实现量大 | 先实现简单的声明宏 |
| 类型推导不完整 | 影响 builtins 多态 | 先做基础类型推导 |

---

## 结论

**推荐立即开始 Phase 1，按以下顺序实现**：

1. **Builtins**（print/println/len）— 最基础的输出能力
2. **std.option**（Option + ? 后缀 + ??）— 空值处理基础
3. **std.result**（Result + ? 操作符 + raises）— 错误处理基础
4. **std.io**（文件读写）— 数据持久化基础

完成 Phase 1 后，Vox 将具备编写实用 CLI 工具的能力。