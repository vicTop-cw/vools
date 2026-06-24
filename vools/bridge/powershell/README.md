# vools.bridge.powershell - PowerShell 语言桥接模块

PowerShell 是微软开发的跨平台任务自动化和配置管理框架，由命令行 shell 和脚本语言组成。vools 桥接模块允许 Python 代码直接调用 PowerShell 脚本。

---

## 1. 语言简介

PowerShell 最初由 Microsoft 于 2006 年发布，最初是 Windows 专用的命令行 shell 和脚本语言。PowerShell 7 及以后版本基于 .NET Core 实现，成为跨平台脚本语言，支持 Windows、Linux 和 macOS。

**主要特点：**
- 面向对象的脚本语言，支持 .NET 对象直接操作
- 强大的管道（Pipeline）机制，支持对象传递
- 丰富的 cmdlet 生态系统
- 跨平台支持（PowerShell 7+）
- 与 Windows 系统深度集成

---

## 2. Bridge 类名

**类名：** `PowerShellBridge`

**模块路径：** `vools.bridge.powershell`

**导入方式：**

```python
from vools.bridge.powershell import PowerShellBridge, powershell_bridge, powershell

# 或完整导入
from vools.bridge import powershell
```

**全局实例：** `powershell_bridge` / `_powershell_bridge`

**装饰器别名：** `powershell` / `ps`

---

## 3. 支持的功能

### 3.1 单函数装饰器模式

使用 `@powershell` 装饰器装饰 Python 函数，函数体为 PowerShell 代码，首次调用自动解释执行。

### 3.2 依赖函数支持

通过 `deps` 参数声明依赖的辅助函数，自动解析依赖拓扑顺序。

```python
@powershell(deps=[helper])
def main_func(x: int) -> int:
    return "return helper($x) + 1"
```

### 3.3 模块级代码

通过 `module_code` 参数注入 PowerShell 模块级代码（如变量初始化、函数定义等）。

### 3.4 异步模式

通过 `async_mode=True` 启用异步执行，返回 `PowerShellFuture` 对象。

### 3.5 回退机制

通过 `fallback` 参数指定解释器不可用时的回退函数。

### 3.6 仅代码模式

通过 `only_code=True` 仅生成 PowerShell 代码，不执行。

### 3.7 项目模式

通过 `project_dir` 参数处理整个 PowerShell 项目目录。

---

## 4. 运行环境要求

### 4.1 PowerShell 解释器

**必需：** PowerShell 5.x (Windows) 或 PowerShell 7.x (跨平台)

**可执行文件候选：**
- `pwsh` - PowerShell 7.x（跨平台）
- `pwsh-preview` - PowerShell 预览版
- `powershell.exe` - Windows PowerShell 5.x

**Windows 搜索路径：**
- `C:\Windows\System32\WindowsPowerShell\v1.0`
- `C:\Program Files\PowerShell\7`
- `~\AppData\Local\Microsoft\WindowsApps`

**Unix/Linux/macOS 搜索路径：**
- `/usr/bin`
- `/usr/local/bin`
- `/opt/microsoft/powershell/7`
- `/snap/bin`
- `/opt/homebrew/bin`

### 4.2 缓存目录

默认缓存目录：`系统临时目录/vools_powershell_cache`

可通过 `cache_dir` 参数自定义缓存位置。

---

## 5. 类型映射

### 5.1 Python → PowerShell 类型

| Python 类型 | PowerShell 类型 | 说明 |
|------------|----------------|------|
| `int` | `int` | 整数 |
| `float` | `double` | 双精度浮点数 |
| `bool` | `bool` | 布尔值 |
| `str` | `string` | 字符串 |
| `bytes` | `string` | 字节串（作为字符串处理） |
| `list` / `tuple` | `object[]` | 对象数组 |
| `dict` | `hashtable` | 哈希表 |
| `None` | `void` | 无返回值 |

### 5.2 PowerShell → ctypes 类型

| PowerShell 类型 | ctypes 类型 | 说明 |
|----------------|-------------|------|
| `int` | `c_int` | C 整数 |
| `long` | `c_long` | C 长整数 |
| `double` | `c_double` | C 双精度浮点 |
| `float` | `c_float` | C 单精度浮点 |
| `bool` | `c_bool` | C 布尔值 |
| `string` | `c_char_p` | C 字符指针 |
| `void` | `None` | 无对应类型 |

### 5.3 类型推断

`infer_ps_argtypes()` 函数根据运行时参数值自动推断 PowerShell 类型：

```python
# Python 端
args = (10, 3.14, "hello", [1, 2, 3], {"key": "value"})

# 推断结果
['int', 'double', 'string', 'object[]', 'hashtable']
```

---

## 6. 快速使用示例

### 6.1 基础用法

```python
from vools.bridge.powershell import powershell

@powershell
def add(x: int, y: int) -> int:
    return "return $x + $y"

result = add(10, 20)
print(result)  # 30
```

### 6.2 使用别名

```python
from vools.bridge.powershell import ps

@ps
def factorial(n: int) -> int:
    return """
    $result = 1
    for ($i = 1; $i -le $n; $i++) {
        $result *= $i
    }
    return $result
    """

result = factorial(5)
print(result)  # 120
```

### 6.3 带依赖函数

```python
def helper(x: int) -> int:
    return "return $x * 2"

@powershell(deps=[helper])
def compute(x: int) -> int:
    return "return helper($x) + 1"

result = compute(5)
print(result)  # 11
```

### 6.4 带模块级代码

```python
@powershell(module_code="$multiplier = 3;")
def multiply(arr: list) -> list:
    return "return $arr | ForEach-Object { $_ * $multiplier }"

result = multiply([1, 2, 3, 4, 5])
print(result)  # [3, 6, 9, 12, 15]
```

### 6.5 异步模式

```python
from vools.bridge.powershell import powershell, PowerShellFuture

@powershell(async_mode=True)
def slow_operation(n: int) -> int:
    return "return $n * $n"

future = slow_operation(100)
result = future.result()
print(result)  # 10000
```

### 6.6 带回退函数

```python
@powershell(fallback=lambda x, y: x + y)
def add(x: int, y: int) -> int:
    return "return $x + $y"

result = add(10, 20)
print(result)  # 30
```

---

## 7. only_code 模式示例

`only_code` 模式仅生成 PowerShell 代码，不执行编译，适用于代码生成和调试场景。

### 7.1 生成代码到标准输出

```python
from vools.bridge.powershell import powershell

@powershell(only_code=True)
def hello(name: str) -> str:
    return 'Write-Host "Hello, $name!"'

# 返回生成的 PowerShell 代码字符串
```

### 7.2 生成代码到文件

```python
from vools.bridge.powershell import powershell

@powershell(only_code=True, output_file="output/hello.ps1")
def hello(name: str) -> str:
    return 'Write-Host "Hello, $name!"'
```

### 7.3 追加模式

```python
@powershell(only_code=True, output_file="utils.ps1", write_mode="append")
def util1(x: int) -> int:
    return "return $x * 2"

@powershell(only_code=True, output_file="utils.ps1", write_mode="append")
def util2(x: int) -> int:
    return "return $x * $x"
```

### 7.4 自定义前后缀

```python
@powershell(only_code=True, output_file="script.ps1",
      prefix="#!/usr/bin/env pwsh\n$ErrorActionPreference = 'Stop'\n",
      suffix="\nWrite-Host 'Done!'")
def main():
    return 'Write-Host "Hello World!"'
```

---

## 8. project 模式示例

`project` 模式用于处理整个 PowerShell 项目目录，支持批量处理多个 .ps1 文件。

### 8.1 项目结构示例

```
my_ps_project/
├── main.ps1          # 入口文件
├── utils.ps1         # 工具函数
└── math.ps1          # 数学函数
```

### 8.2 入口文件 (main.ps1)

```powershell
$ErrorActionPreference = "Stop"

function Process-Data {
    param([int]$data)
    return $data * 2
}

Export-ModuleMember -Function *
```

### 8.3 使用项目模式

```python
from vools.bridge.powershell import powershell

@powershell(project_dir="./my_ps_project", entry="Process-Data")
def process(x: int) -> int:
    pass

result = process(42)
print(result)  # 84
```

### 8.4 执行 main.ps1

```python
from vools.bridge.powershell import powershell_bridge

# 返回 (returncode, stdout, stderr)
result = powershell_bridge.run_project("./my_ps_project", entry="main", args=())
print(result)
```

### 8.5 项目模式打包

当 `entry != 'main'` 时，项目模式会：
1. 扫描项目目录下所有 `.ps1` 文件
2. 按文件名排序拼接所有文件内容
3. 在末尾添加入口函数调用代码
4. 输出打包后的 `.ps1` 文件路径

```python
# 打包项目中所有 .ps1 文件，入口函数为 Compute
artifact_path = powershell_bridge.compile_project(
    "./my_ps_project",
    entry="Compute",
    output_dir="./output"
)
print(f"打包文件: {artifact_path}")
```

---

## 9. 注意事项

### 9.1 PowerShell 代码限制

- **返回值格式：** 函数体中应使用 `return` 语句返回值
- **变量语法：** PowerShell 变量以 `$` 开头，如 `$x`、`$result`
- **比较运算符：** 使用 `-eq`、`-ne`、`-gt`、`-lt` 等，而非 `==`、`!=`
- **布尔值：** PowerShell 中使用 `$true` 和 `$false`
- **注释：** 使用 `#` 单行注释，`<# ... #>` 多行注释

### 9.2 性能考虑

- PowerShell 是解释型语言，每次调用都会启动新的 PowerShell 进程
- 对于高频调用场景，建议使用项目模式减少启动开销
- 大量数据传递建议使用 JSON 序列化

### 9.3 路径问题

- Windows 路径使用反斜杠 `\` 或正斜杠 `/`
- Unix/Linux/macOS 路径使用正斜杠 `/`
- 建议使用 `os.path` 处理跨平台路径

### 9.4 编码问题

- 源代码默认以 UTF-8 编码读写
- PowerShell 脚本开头自动设置 `$ErrorActionPreference = "Stop"`
- 字符串处理时注意编码一致性

### 9.5 JSON 依赖

- 参数传递使用 PowerShell 内置的 `ConvertFrom-Json` / `ConvertTo-Json`
- JSON 序列化深度默认 10 层

### 9.6 错误处理

- PowerShell 脚本执行失败时抛出 `RuntimeError`
- 错误信息包含 stderr、stdout 和源代码
- 建议使用 `try-except` 捕获执行异常

### 9.7 缓存管理

- 缓存键基于代码内容的 MD5 哈希
- 缓存目录位于系统临时目录
- 长时间运行建议定期清理缓存

### 9.8 执行策略

- Windows 上可能需要调整 PowerShell 执行策略
- 建议当前用户设置：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- 桥接模块使用 `-File` 参数执行脚本，不受执行策略严格限制
