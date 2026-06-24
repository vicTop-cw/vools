# vools.bridge.typescript — TypeScript/JavaScript 语言桥接

> Node.js 生态系统桥接，通过子进程执行 TypeScript/JavaScript 代码

## 语言简介

TypeScript 是 JavaScript 的超集，添加了静态类型检查，是现代 Web 后端开发的主流选择。
本模块提供 TypeScript/JS 代码执行能力，通过 Node.js 子进程运行编译后的 JS，
使用 JSON 序列化进行数据交换，适合 I/O 密集型任务（Web、Node.js 生态调用）。

**设计要点：**
- 通过 `node` 启动子进程执行编译后的 JS
- TypeScript 编译：去除类型注解降级为 JS（无需 tsc 依赖）
- 数据交换：JSON over stdin/stdout
- 异步支持：基于 Promise + 线程池的 async_mode
- 缓存机制：基于代码 MD5 哈希的缓存

## Bridge 类名

**`TypeScriptBridge`** — 继承自 `LangBridge` 抽象基类的 TypeScript 桥接实现

- 全局实例：`_ts_bridge`
- 装饰器：`@ts` / `@typescript`

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@ts` 装饰器，函数体 return 字符串或 docstring 方式 |
| only_code 模式 | ✅ | 只生成 TypeScript 源码，不编译/执行 |
| project 模式 | ✅ | 编译整个项目目录，打包成一个 JS 文件 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 返回可 await 的 Future |
| 回退机制 | ✅ | `fallback` 参数支持 Python 回退实现 |
| 类型转换 | ✅ | Python ↔ TypeScript 自动转换（JSON 序列化） |
| deps 依赖 | ✅ | 支持依赖函数列表 |
| module_code | ✅ | 支持模块级代码 |

## 运行环境要求

- **Node.js**: >= 14（必需）
- **TypeScript**: 可选，未安装时自动降级为 JS（去除类型注解）
- **安装方式**：
  - Windows: <https://nodejs.org/> 下载 LTS
  - Linux: `sudo apt install nodejs npm`
  - macOS: `brew install node`
- **验证方式**：`node --version`

## 类型映射

| Python | TypeScript | 说明 |
|--------|------------|------|
| `int` | `number` | 整数映射为 number |
| `float` | `number` | 浮点数映射为 number |
| `str` | `string` | 字符串 |
| `bool` | `boolean` | 布尔值 |
| `list` | `any[]` | 数组 |
| `dict` | `Record<string, any>` | 对象/字典 |
| `None` | `null` | 空值 |

## 快速使用示例

### 基础用法（return 字符串方式，推荐）

```python
from vools.bridge.typescript import ts, ts_compiler_available

if ts_compiler_available():
    @ts
    def add(a: int, b: int) -> int:
        return "return a + b;"

    print(add(2, 3))  # 5

    @ts
    def greet(name: str) -> str:
        return 'return `Hello, ${name}!`;'

    print(greet("World"))  # Hello, World!
```

### docstring 方式（旧版兼容）

```python
@ts
def multiply(a: int, b: int) -> int:
    """
    return a * b;
    """

print(multiply(3, 4))  # 12
```

### 斐波那契数列

```python
@ts
def fib(n: int) -> int:
    return """
    if (n <= 1) return 1;
    return fib(n - 1) + fib(n - 2);
    """

print(fib(10))  # 89
```

### 异步模式

```python
import asyncio

@ts(async_mode=True)
def fetch_data(url: str) -> dict:
    return """
    const response = await fetch(url);
    return await response.json();
    """

result = asyncio.run(fetch_data("https://api.example.com/data"))
```

### 回退机制

```python
@ts(fallback=lambda a, b: a + b)
def add(a, b):
    return "return a + b;"

# 当 Node.js 不可用时，自动使用 Python lambda
result = add(2, 3)  # 5
```

## only_code 模式示例

```python
@ts(only_code=True, output_file="output.ts")
def add(a: int, b: int) -> int:
    return "return a + b;"

code = add(1, 2)  # 返回生成的 TypeScript 源码
# output.ts 文件已写入
```

**4 种写入模式：**

```python
# 覆盖整个文件（默认）
@ts(only_code=True, output_file="out.ts", write_mode="overwrite")

# 追加到文件末尾
@ts(only_code=True, output_file="out.ts", write_mode="append")

# 插入到第 10 行之后
@ts(only_code=True, output_file="out.ts", write_mode="insert:10")

# 替换第 5 到 15 行
@ts(only_code=True, output_file="out.ts", write_mode="replace:5-15")
```

## project 模式示例

### 入口为 main（可执行脚本）

项目目录结构：
```
my_project/
  utils.ts
  main.ts
```

```python
@ts(project_dir="./my_project", entry="main")
def my_app():
    pass

# 调用时执行 main 函数
result = my_app()
```

### 入口为指定函数（库模式）

```python
from vools.bridge.typescript import TypeScriptBridge

ts_bridge = TypeScriptBridge()
js_path = ts_bridge.compile_project("./my_project", "add")
# 生成 index.js，导出 add 函数
```

**项目模式特点：**
- 自动扫描项目目录下所有 `.ts` 和 `.js` 文件
- 按文件名排序，合并为一个 JS 文件
- 基于文件内容哈希的缓存机制
- entry='main' 时生成带 CLI 入口的完整脚本
- entry=其他时生成 module.exports 导出的模块

## 注意事项

1. **函数体两种写法**：推荐使用 return 字符串方式（与其他语言一致），
   也支持 docstring 方式（向后兼容）

2. **数据交换限制**：通过 JSON 序列化交换数据，仅支持 JSON 可序列化类型
   （number、string、boolean、array、object、null）

3. **TS 编译降级**：默认使用内置的类型去除器将 TS 转为 JS，无需 tsc 依赖。
   如需完整 TS 编译，请确保安装了 `tsc` 或使用 `npx tsc`

4. **异步执行**：`async_mode=True` 时，返回 TSFuture 对象，支持 `.result()`
   和 `await` 两种使用方式

5. **回调函数**：由于是子进程执行，无法直接传递 Python 函数作为回调，
   需要在 JS 端自行实现回调逻辑

## API 速查

| 名称 | 类型 | 说明 |
|------|------|------|
| `ts` | 装饰器 | TypeScript 桥接装饰器（推荐） |
| `typescript` | 装饰器 | `ts` 的别名 |
| `ts_compiler_available()` | 函数 | 检查运行环境是否可用（需要 node） |
| `is_typescript_available()` | 函数 | 检查 tsc 是否可用 |
| `is_node_available()` | 函数 | 检查 node 是否可用 |
| `get_node_version()` | 函数 | 获取 Node.js 版本 |
| `get_tsc_version()` | 函数 | 获取 tsc 版本 |
| `TypeScriptBridge` | 类 | TypeScript 桥接类 |
| `_ts_bridge` | 实例 | 全局单例实例 |
| `compile_and_run()` | 函数 | 便捷入口：直接编译运行 |
| `TSFuture` | 类 | 异步执行 Future |
| `PY_TO_TS_TYPE` | dict | Python → TS 类型映射表 |
| `TS_TO_PY_TYPE` | dict | TS → Python 类型映射表 |
| `get_ts_type()` | 函数 | Python 类型 → TS 类型字符串 |
