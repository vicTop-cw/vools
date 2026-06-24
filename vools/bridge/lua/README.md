# Lua 语言桥接模块 (vools.bridge.lua)

## 1. 语言简介

Lua 是一种轻量级、高效的脚本语言，由巴西里约热内卢天主教大学于 1993 年开发设计。Lua 以其简洁的语法、强大的表格（table）数据结构、优秀的嵌入能力著称，广泛应用于游戏开发、嵌入式系统、Web 服务器配置（如 Nginx 的 OpenResty）、工业自动化等领域。

**Lua 语言特点：**
- 轻量级：核心解释器仅约 200KB
- 高效：执行速度极快，内存占用低
- 可嵌入：易于与 C/C++ 代码集成
- 动态类型：无需声明变量类型
- 表格（Table）：唯一复合数据结构，可用于数组、字典、对象等

**官方资源：**
- 官网：https://www.lua.org/
- 文档：https://www.lua.org/docs.html
- 下载：https://www.lua.org/download.html

## 2. Bridge 类名

```
LuaBridge
```

**类定义位置：** `vools.bridge.lua.compiler.LuaBridge`

**模块导入：**
```python
from vools.bridge.lua import LuaBridge, lua_bridge

# 使用全局实例
from vools.bridge.lua import lua, lua_compiler_available, compile_and_run
```

## 3. 支持的功能

| 功能 | 支持状态 | 说明 |
|------|----------|------|
| 装饰器模式 `@lua` | ✅ | 将 Python 函数转换为 Lua 代码执行 |
| 依赖函数 `deps` | ✅ | 支持依赖函数的生成和引用 |
| 模块代码 `module_code` | ✅ | 支持模块级代码生成 |
| 异步模式 `async_mode` | ✅ | 返回 async 包装器 |
| 回退机制 `fallback` | ✅ | 编译器不可用时调用回退函数 |
| 缓存机制 | ✅ | 自动缓存编译产物 |
| 仅代码模式 `only_code` | ✅ | 只生成 Lua 源码，不执行 |
| 项目模式 `project_dir` | ✅ | 编译并运行整个 Lua 项目 |
| 入口函数 `entry` | ✅ | 指定项目入口函数名 |
| 类型映射 | ✅ | Python ↔ Lua 类型自动转换 |
| JSON 数据交换 | ✅ | 通过 JSON 进行参数和结果序列化 |
| subprocess 调用 | ✅ | 通过 lua 解释器执行代码 |

## 4. 运行环境要求

### 必需环境

1. **Lua 解释器**（任选其一）：
   - Lua 5.3+（推荐）
   - Lua 5.2
   - Lua 5.1
   - LuaJIT 2.0+

2. **环境变量配置**：
   - 将 lua 可执行文件所在目录加入 PATH

### Windows 环境

```
推荐安装路径：
- C:\Program Files\Lua
- C:\lua

或使用 LuaDist、LuaForWindows 等发行版
```

### Unix/Linux/macOS 环境

```bash
# Debian/Ubuntu
sudo apt-get install lua5.3

# macOS (Homebrew)
brew install lua

# 或使用 LuaJIT（高性能）
brew install luajit
```

### 验证安装

```python
from vools.bridge.lua import lua_compiler_available

if lua_compiler_available():
    print("Lua 解释器可用")
else:
    print("请安装 Lua 并将其加入 PATH")
```

## 5. 类型映射

### Python → Lua 类型

| Python 类型 | Lua 类型 | 说明 |
|-------------|----------|------|
| `int` | `integer` | 整数 |
| `float` | `number` | 浮点数 |
| `str` | `string` | 字符串 |
| `bool` | `boolean` | 布尔值 |
| `list` | `table` | 列表/数组 |
| `tuple` | `table` | 元组 |
| `dict` | `table` | 字典/哈希表 |
| `None` | `nil` | 空值 |

### Lua → Python 类型

| Lua 类型 | Python 类型 | 说明 |
|----------|-------------|------|
| `integer` | `int` | 整数 |
| `number` | `float` | 浮点数 |
| `string` | `str` | 字符串 |
| `boolean` | `bool` | 布尔值 |
| `table` | `dict` / `list` | 根据内容自动选择 |
| `nil` | `None` | 空值 |

### ctypes 类型映射

| Lua 类型 | ctypes 类型 |
|----------|-------------|
| `integer` | `ctypes.c_int` |
| `number` | `ctypes.c_double` |
| `string` | `ctypes.c_char_p` |
| `boolean` | `ctypes.c_bool` |
| `table` | `ctypes.c_void_p` |
| `nil` | `None` |

## 6. 快速使用示例

### 基础用法

```python
from vools.bridge.lua import lua, lua_compiler_available

if lua_compiler_available():
    @lua
    def add(a: int, b: int) -> int:
        return "return a + b"

    @lua
    def fib(n: int) -> int:
        return """
        function fib(n)
          if n <= 1 then return 1 end
          return fib(n-1) + fib(n-2)
        end
        return fib(n)
        """

    print(add(1, 2))        # → 3
    print(fib(10))          # → 89
```

### 带依赖函数

```python
from vools.bridge.lua import lua

@lua
def helper(x: int) -> int:
    return "return x * 2"

@lua(deps=[helper])
def compute(a: int, b: int) -> int:
    return "return helper(a) + helper(b)"

print(compute(3, 4))  # → 14
```

### 带模块级代码

```python
@lua(module_code="local math = math or {}\nmath.pi = 3.14159")
def circle_area(r: float) -> float:
    return "return math.pi * r * r"

print(circle_area(2.0))  # → 12.56636
```

### 仅代码模式

```python
@lua(only_code=True, output_file="output.lua")
def my_func(x: int) -> int:
    return "return x * 2"

# 代码将被写入 output.lua 文件
```

### 使用回退函数

```python
def python_fallback(x: int) -> int:
    """纯 Python 实现作为回退"""
    return x * 2

@lua(fallback=python_fallback)
def my_func(x: int) -> int:
    # 如果 Lua 不可用，将调用 python_fallback
    return "return x * 2"
```

## 7. only_code 模式示例

### 生成 Lua 源文件

```python
from vools.bridge.lua import lua

@lua(only_code=True)
def factorial(n: int) -> int:
    return """
    function factorial(n)
      if n == 0 then return 1 end
      return n * factorial(n - 1)
    end
    return factorial(n)
    """

# 获取生成的代码
code = factorial(5)
print(code)
```

### 输出到指定文件

```python
@lua(only_code=True, output_file="factorial.lua")
def factorial(n: int) -> int:
    return """
    function factorial(n)
      if n == 0 then return 1 end
      return n * factorial(n - 1)
    end
    return factorial(n)
    """

factorial(5)  # 代码已写入 factorial.lua
```

### 自定义代码前缀和后缀

```python
@lua(only_code=True, prefix="#!/usr/bin/env lua\n-- My Lua Script\n",
     suffix="\n-- End of script")
def my_script():
    return "print('Hello, Lua!')"
```

## 8. project 模式示例

### 项目目录结构

```
my_lua_project/
├── main.lua          # 入口文件
├── utils.lua          # 工具函数
└── math_helper.lua    # 数学辅助函数
```

### main.lua 示例

```lua
-- main.lua
local utils = require("utils")
local math_helper = require("math_helper")

local result = math_helper.fibonacci(10)
print("Fibonacci(10) = " .. result)
utils.print_result(result)
```

### 使用装饰器运行项目

```python
from vools.bridge.lua import lua

@lua(project_dir="./my_lua_project", entry="main")
def run_my_app():
    pass

run_my_app()  # 执行 lua main.lua
```

### 调用非 main 入口函数

```python
from vools.bridge.lua import lua

@lua(project_dir="./my_lua_project", entry="fibonacci")
def calc_fib(n: int) -> int:
    pass

result = calc_fib(20)  # 调用项目中定义的 fibonacci 函数
print(result)
```

### 项目编译缓存

```python
# 首次运行会编译项目，后续运行直接使用缓存
for i in range(10):
    result = calc_fib(i)
    print(f"fib({i}) = {result}")
```

## 9. 注意事项

### 1. Lua 版本兼容性

- 推荐使用 **Lua 5.3+**，因为它原生支持整数（`integer`）和位运算
- Lua 5.1 和 LuaJIT 使用相同的语法，兼容性良好
- 代码中使用 `function name() ... end` 而非 `function name() then ... end`

### 2. JSON 序列化限制

- Lua 端的 JSON 解析采用内置实现，复杂对象可能无法完美还原
- 如需复杂数据交互，建议在 Lua 端使用 cjson 库（如果有）

### 3. 参数传递方式

- 参数通过 JSON 序列化后传递给 Lua
- 返回值通过 Lua 的 `print()` 输出，由 Python 捕获并反序列化
- 避免返回过大的数据结构

### 4. 缓存目录

- 默认缓存目录：`系统临时目录/vools_lua_cache/`
- 可通过 `cache_dir` 参数自定义缓存位置
- 缓存键基于代码内容的 MD5 哈希，相同代码不会重复编译

### 5. 错误处理

- Lua 执行失败时会抛出 `RuntimeError`，包含 stderr 输出
- 建议使用 `fallback` 参数提供 Python 回退实现
- 异步模式下的错误处理需要使用 `try/except`

### 6. Windows 路径问题

- Windows 环境下注意路径分隔符使用反斜杠 `\` 或使用原始字符串
- Lua 解释器路径中不应包含空格（如果可能）

### 7. 性能考虑

- 每次调用都会启动新的 Lua 解释器进程
- 频繁调用场景建议使用项目模式预编译
- LuaJIT 比标准 Lua 5.3 执行速度更快

### 8. 函数体格式

```python
# 正确：Lua 函数体
@lua
def add(a: int, b: int) -> int:
    return "return a + b"

# 正确：多行函数体
@lua
def fib(n: int) -> int:
    return """
    function fib(n)
      if n <= 1 then return 1 end
      return fib(n-1) + fib(n-2)
    end
    return fib(n)
    """
```

### 9. 模块系统

- Lua 的 `require()` 在 subprocess 模式下无法直接使用
- 如需模块功能，请使用 `project_dir` 模式
- `module_code` 可用于注入简单的模块级代码
