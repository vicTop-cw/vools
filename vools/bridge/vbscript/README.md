# vools.bridge.vbscript - VBScript 语言桥接模块

VBScript（Visual Basic Scripting Edition）是微软开发的一种轻量级脚本语言，基于 Visual Basic，主要用于 Windows 系统管理和 Web 客户端脚本。vools 桥接模块允许 Python 代码直接调用 VBScript 脚本。

---

## 1. 语言简介

VBScript 最初由 Microsoft 于 1996 年发布，是 Visual Basic 语言家族的成员。作为 Windows 系统原生脚本语言，VBScript 广泛用于系统管理任务、Active Server Pages (ASP) Web 开发、以及 Windows Script Host (WSH) 自动化脚本。

**主要特点：**
- Windows 系统原生支持，无需额外安装
- 基于 Visual Basic 语法，学习曲线平缓
- 强大的 COM 对象访问能力，可调用 Windows API
- 通过 WSH (Windows Script Host) 执行脚本
- 支持 Dictionary、FileSystemObject 等内置对象

---

## 2. Bridge 类名

**类名：** `VBScriptBridge`

**模块路径：** `vools.bridge.vbscript`

**导入方式：**

```python
from vools.bridge.vbscript import VBScriptBridge, vbscript_bridge, vbscript

# 或完整导入
from vools.bridge import vbscript
```

**全局实例：** `vbscript_bridge` / `_vbscript_bridge`

**装饰器别名：** `vbs = vbscript`

---

## 3. 支持的功能

### 3.1 单函数装饰器模式

使用 `@vbscript` 装饰器装饰 Python 函数，函数体为 VBScript 代码，首次调用自动解释执行。

### 3.2 依赖函数支持

通过 `deps` 参数声明依赖的辅助函数，自动解析依赖拓扑顺序。

```python
@vbscript(deps=[helper])
def main_func(x: int) -> int:
    return "main_func = helper(x) + 1"
```

### 3.3 模块级代码

通过 `module_code` 参数注入 VBScript 模块级代码（如常量定义、类声明等）。

### 3.4 异步模式

通过 `async_mode=True` 启用异步执行，返回 `VBScriptFuture` 对象。

### 3.5 回退机制

通过 `fallback` 参数指定解释器不可用时的回退函数。

### 3.6 仅代码模式

通过 `only_code=True` 仅生成 VBScript 代码，不执行。

### 3.7 项目模式

通过 `project_dir` 参数编译整个 VBScript 项目目录。

---

## 4. 运行环境要求

### 4.1 VBScript 解释器

**必需：** Windows 系统 + cscript.exe (Windows Script Host)

**Windows 搜索路径：**
- `C:\Windows\System32\cscript.exe`
- `C:\Windows\SysWOW64\cscript.exe`

> **注意：** VBScript 仅在 Windows 平台可用。非 Windows 平台 `vbscript_compiler_available()` 将返回 `False`。

### 4.2 执行方式

使用 `cscript.exe //Nologo //E:vbscript script.vbs` 执行脚本。

- `//Nologo` - 不显示启动版权标志
- `//E:vbscript` - 指定使用 VBScript 引擎

### 4.3 缓存目录

默认缓存目录：`系统临时目录/vools_vbscript_cache`

可通过 `cache_dir` 参数自定义缓存位置。

---

## 5. 类型映射

### 5.1 Python → VBScript 类型

| Python 类型 | VBScript 类型 | 说明 |
|------------|--------------|------|
| `int` | `Integer` | 整数 |
| `float` | `Double` | 双精度浮点数 |
| `bool` | `Boolean` | 布尔值 |
| `str` | `String` | 字符串 |
| `list` / `tuple` | `Variant()` | 变体数组 |
| `dict` | `Dictionary` | 字典对象 |
| `None` | `Variant` | 变体类型 |

### 5.2 VBScript → ctypes 类型

| VBScript 类型 | ctypes 类型 | 说明 |
|--------------|-------------|------|
| `Integer` | `c_int` | 16 位整数 |
| `Long` | `c_long` | 32 位整数 |
| `Double` | `c_double` | 双精度浮点 |
| `Single` | `c_float` | 单精度浮点 |
| `Boolean` | `c_bool` | 布尔值 |
| `String` | `c_char_p` | 字符指针 |
| `Variant` | `c_void_p` | 变体指针 |

### 5.3 类型推断

`infer_vbs_argtypes()` 函数根据运行时参数值自动推断 VBScript 类型：

```python
# Python 端
args = (10, 3.14, "hello", [1, 2, 3], {"key": "value"})

# 推断结果
['Integer', 'Double', 'String', 'Variant()', 'Dictionary']
```

---

## 6. 快速使用示例

### 6.1 基础用法

```python
from vools.bridge.vbscript import vbscript

@vbscript
def add(x: int, y: int) -> int:
    return "add = x + y"

result = add(10, 20)
print(result)  # 30
```

### 6.2 使用别名 vbs

```python
from vools.bridge.vbscript import vbs

@vbs
def factorial(n: int) -> int:
    return """
    Dim i, result
    result = 1
    For i = 1 To n
        result = result * i
    Next
    factorial = result
    """

result = factorial(5)
print(result)  # 120
```

### 6.3 带依赖函数

```python
def helper(x: int) -> int:
    return "helper = x * 2"

@vbscript(deps=[helper])
def compute(x: int) -> int:
    return "compute = helper(x) + 1"

result = compute(5)
print(result)  # 11
```

### 6.4 带模块级代码

```python
@vbscript(module_code="Const PI = 3.14159")
def circle_area(r: float) -> float:
    return "circle_area = PI * r * r"

result = circle_area(5.0)
print(result)  # 78.53975
```

### 6.5 异步模式

```python
from vools.bridge.vbscript import vbscript, VBScriptFuture

@vbscript(async_mode=True)
def slow_operation(n: int) -> int:
    return "slow_operation = n * n"

future = slow_operation(100)
result = future.result()
print(result)  # 10000
```

### 6.6 带回退函数

```python
@vbscript(fallback=lambda x, y: x + y)
def add(x: int, y: int) -> int:
    return "add = x + y"

result = add(10, 20)
print(result)  # 30
```

---

## 7. only_code 模式示例

`only_code` 模式仅生成 VBScript 代码，不执行，适用于代码生成和调试场景。

### 7.1 生成代码到标准输出

```python
from vools.bridge.vbscript import vbscript

@vbscript(only_code=True)
def hello(name: str) -> str:
    return 'hello = "Hello, " & name & "!"'

# 输出生成的 VBScript 代码
code = hello("World")
print(code)
```

### 7.2 生成代码到文件

```python
from vools.bridge.vbscript import vbscript

@vbscript(only_code=True, output_file="output/hello.vbs")
def hello(name: str) -> str:
    return 'hello = "Hello, " & name & "!"'
```

### 7.3 追加模式

```python
@vbscript(only_code=True, output_file="utils.vbs", write_mode="append")
def util1(x: int) -> int:
    return "util1 = x * 2"

@vbscript(only_code=True, output_file="utils.vbs", write_mode="append")
def util2(x: int) -> int:
    return "util2 = x * x"
```

### 7.4 自定义前后缀

```python
@vbscript(only_code=True, output_file="script.vbs",
      prefix="Option Explicit\n' Script header\n",
      suffix="\n' End of script\n")
def main():
    return 'WScript.Echo "Hello World!"'
```

---

## 8. project 模式示例

`project` 模式用于编译整个 VBScript 项目目录，支持批量处理多个 .vbs 文件。

### 8.1 项目结构示例

```
my_vbscript_project/
├── main.vbs          # 入口文件
├── utils.vbs         # 工具函数
└── math.vbs          # 数学函数
```

### 8.2 入口文件 (main.vbs)

```vbscript
Option Explicit

Dim fso
Set fso = CreateObject("Scripting.FileSystemObject")

Function ProcessData(data)
    ProcessData = data * 2
End Function
```

### 8.3 使用项目模式

```python
from vools.bridge.vbscript import vbscript

@vbscript(project_dir="./my_vbscript_project", entry="ProcessData")
def process(x: int) -> int:
    pass

result = process(42)
print(result)  # 84
```

### 8.4 执行 main.vbs

```python
from vools.bridge.vbscript import vbscript_bridge

# 返回 (returncode, stdout, stderr)
result = vbscript_bridge.run_project("./my_vbscript_project", entry="main", args=())
print(result)
```

### 8.5 项目模式打包

当 `entry != 'main'` 时，项目模式会：
1. 扫描项目目录下所有 `.vbs` 文件
2. 按文件名排序拼接所有文件内容
3. 在末尾添加入口函数调用代码
4. 输出打包后的 `.vbs` 文件路径

```python
# 打包项目中所有 .vbs 文件，入口函数为 compute
artifact_path = vbscript_bridge.compile_project(
    "./my_vbscript_project",
    entry="compute",
    output_dir="./output"
)
print(f"打包文件: {artifact_path}")
```

---

## 9. 注意事项

### 9.1 VBScript 代码限制

- **返回值格式：** VBScript 函数通过 `函数名 = 值` 形式返回值
- **不区分大小写：** VBScript 不区分大小写，但建议保持一致风格
- **变量声明：** 自动生成的脚本包含 `Option Explicit`，需显式声明变量
- **数组索引：** VBScript 数组默认从 0 开始，使用 `LBound/UBound` 遍历

### 9.2 性能考虑

- VBScript 是解释型语言，每次调用都会启动 `cscript.exe` 进程
- 对于高频调用场景，建议使用项目模式或减少调用次数
- 大量数据传递建议使用 JSON 序列化（内置支持）

### 9.3 路径问题

- 仅支持 Windows 平台
- 路径使用反斜杠 `\` 或正斜杠 `/` 均可
- 建议使用 `os.path` 处理跨平台路径

### 9.4 编码问题

- 源代码默认以 UTF-8 编码读写
- 字符串传递支持 Unicode 字符
- 注意 VBScript 内部使用 UTF-16 编码

### 9.5 JSON 依赖

- 参数传递使用内置 JSON 解析/序列化函数
- 支持字符串、数字、布尔值、数组、字典的序列化
- 复杂对象建议转换为基础类型后传递

### 9.6 错误处理

- VBScript 脚本执行失败时抛出 `RuntimeError`
- 错误信息包含 stderr、stdout 和源代码
- 建议使用 `try-except` 捕获执行异常

### 9.7 缓存管理

- 缓存键基于代码内容的 MD5 哈希
- 缓存目录位于系统临时目录
- 长时间运行建议定期清理缓存

### 9.8 安全注意

- VBScript 可访问 Windows 系统资源
- 执行不受信任的脚本前请进行安全审查
- 避免在脚本中执行敏感操作

---

## 附录：API 参考

### 函数

| 函数 | 说明 |
|------|------|
| `vbscript_compiler_available()` | 检查 VBScript 解释器是否可用 |
| `compile_and_run(code, func_name, args, ret_type, cache_dir)` | 编译并运行代码 |
| `get_vbs_type(py_type)` | 获取 VBScript 类型字符串 |
| `get_vbs_ctype(vbs_type)` | 获取 ctypes 类型 |

### 类

| 类 | 说明 |
|---|------|
| `VBScriptBridge` | VBScript 桥接实现类 |
| `VBScriptFuture` | 异步执行结果封装 |
