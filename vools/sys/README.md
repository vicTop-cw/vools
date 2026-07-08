# vools.sys — 外部系统资源轻量桥接

`vools.sys` 是 vools 库的系统集成子包，提供外部可执行文件（exe）和动态链接库（dll/so）的轻量桥接能力。通过装饰器模式，你可以用 Python 函数签名定义接口，框架自动完成参数映射、类型转换、同步/异步调用和回退机制。

---

## 目录

- [子包概述](#子包概述)
- [模块说明](#模块说明)
- [@exe 装饰器](#exe-装饰器)
  - [功能说明](#功能说明)
  - [参数映射规则](#参数映射规则)
  - [全部参数列表](#全部参数列表)
  - [使用示例](#使用示例)
  - [返回值说明](#返回值说明)
- [@cmd 装饰器](#cmd-装饰器)
  - [功能说明](#功能说明-2)
  - [支持的 shell 类型](#支持的-shell-类型)
  - [参数映射规则](#参数映射规则-1)
  - [全部参数列表](#全部参数列表-2)
  - [使用示例](#使用示例-2)
- [@dll 装饰器](#dll-装饰器)
  - [功能说明](#功能说明-1)
  - [自动类型映射表](#自动类型映射表)
  - [全部参数列表](#全部参数列表-1)
  - [使用示例](#使用示例-1)
- [函数体自动 fallback 机制](#函数体自动-fallback-机制)
- [与 LangBridge 的区别和适用场景](#与-langbridge-的区别和适用场景)
- [API 速查](#api-速查)

---

## 子包概述

`vools.sys` 提供三种核心桥接装饰器：

- **`@exe`** — 将 Python 函数映射为外部可执行文件调用，自动处理命令行参数构建
- **`@cmd`** — 将 Python 函数映射为 shell 命令调用，支持选择不同的 shell（bash/cmd/powershell）
- **`@dll`** — 将 Python 函数映射为 DLL/共享库函数调用，自动处理 ctypes 类型映射

三者共享一致的设计理念：
- **声明式接口**：用 Python 函数签名定义接口，函数体可选
- **自动映射**：参数名 → 命令行选项 / Python 类型 → ctypes 类型
- **同步异步**：支持同步调用和 `async/await` 异步模式
- **回退机制**：外部资源不可用时自动回退到 Python 实现
- **零依赖**：仅使用 Python 标准库（subprocess, ctypes, asyncio）

---

## 模块说明

| 模块 | 文件 | 功能简介 |
|------|------|----------|
| exe 装饰器 | `exe.py` | `@exe` 装饰器，调用外部可执行文件 |
| cmd 装饰器 | `cmd.py` | `@cmd` 装饰器，调用 shell 命令（支持 bash/cmd/powershell） |
| dll 装饰器 | `dll.py` | `@dll` 装饰器，调用外部 DLL/共享库 |
| DLL 管理命令 | `dll_cmd.py` | CLI 子命令：列出、调用内置 Nim DLL |
| 编译命令 | `compile_cmd.py` | CLI 子命令：编译 Nim/C/C++ 源文件 |
| 运行命令 | `run_cmd.py` | CLI 子命令：执行 Python 脚本或 shell 命令 |
| 环境探测 | `env_cmd.py` | CLI 子命令：探测 PATH/Python/Nim 环境 |
| Fire CLI 应用 | `fire_app.py` | 基于 Python Fire 的 CLI 入口 `SysCLI` |

---

## @exe 装饰器

### 功能说明

`@exe` 装饰器将一个 Python 函数映射为外部可执行文件的调用。函数参数名通过命名约定自动转换为命令行选项，函数体可作为 fallback 实现。

### 参数映射规则

函数参数名通过前缀约定映射为命令行参数：

| 参数名格式 | 映射为 | 示例 | 说明 |
|-----------|--------|------|------|
| `_f` | 短选项 | `_f="file.txt"` → `-f file.txt` | 单下划线前缀 |
| `_f=None` | 短标志 | `_f=None` → `-f` | 值为 None 时只传标志 |
| `__path` | 长选项 | `__path="/tmp"` → `--path /tmp` | 双下划线前缀 |
| `__verbose=None` | 长标志 | `__verbose=None` → `--verbose` | 值为 None 时只传标志 |
| `name` (无前缀) | 位置参数 | `name="hello"` → 追加到命令末尾 | 按参数定义顺序排列 |

> **注意**：`*args` 可变位置参数也会按顺序追加到命令末尾。

### 全部参数列表

```python
@exe(
    exe_path,           # 可执行文件路径
    *,
    async_mode=False,   # 是否启用异步模式
    fallback=None,      # 显式回退函数
)
def my_func(...):
    pass
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `exe_path` | `str` | 必填 | 可执行文件的路径（绝对路径或 PATH 中的命令名） |
| `async_mode` | `bool` | `False` | 是否返回异步函数，异步模式在线程池中执行 |
| `fallback` | `Callable` | `None` | 显式指定回退函数，优先级高于函数体 fallback |

### 使用示例

#### 示例 1：简单命令调用

```python
from vools.sys import exe

@exe("echo")
def echo(msg: str):
    pass

returncode, stdout, stderr = echo("hello world")
print(stdout)  # hello world
```

#### 示例 2：带选项参数

```python
from vools.sys import exe
import sys

@exe(sys.executable)
def python_cmd(_c=None, _O=None, __verbose=None):
    pass

# 执行 python -c "print(123)" -O --verbose
returncode, stdout, stderr = python_cmd(
    _c="print(123)",
    _O=None,
    __verbose=None,
)
```

#### 示例 3：异步模式

```python
import asyncio
from vools.sys import exe

@exe("ping", async_mode=True)
async def ping(_c=None, host=None, count=None):
    pass

async def main():
    # 异步调用，不阻塞事件循环
    result = await ping(host="127.0.0.1", count=4)
    print(result[1])

asyncio.run(main())
```

#### 示例 4：fallback 回退

```python
from vools.sys import exe

# 方式一：函数体作为 fallback
@exe("/path/to/may_not_exist.exe")
def compute(x: int, y: int) -> tuple:
    """exe 不存在或失败时，执行函数体作为兜底"""
    return (0, str(x + y), "")

# 方式二：显式指定 fallback 函数
def py_compute(x, y):
    return (0, str(x * y), "")

@exe("/path/to/may_not_exist.exe", fallback=py_compute)
def compute2(x: int, y: int):
    pass
```

### 返回值说明

返回一个三元组 `(returncode, stdout, stderr)`：

| 元素 | 类型 | 说明 |
|------|------|------|
| `returncode` | `int` | 进程退出码，0 表示成功 |
| `stdout` | `str` | 标准输出（已解码为字符串） |
| `stderr` | `str` | 标准错误（已解码为字符串） |

> 异常情况：如果可执行文件不存在且没有 fallback，抛出 `FileNotFoundError`。

---

## @cmd 装饰器

### 功能说明

`@cmd` 装饰器将一个 Python 函数映射为 shell 命令调用，支持选择不同的 shell（bash/cmd/powershell）。与 `@exe` 的区别在于：`@exe` 直接调用可执行文件，而 `@cmd` 通过 shell 解释器执行命令，因此可以使用 shell 的内置命令和管道等功能。

### 支持的 shell 类型

| shell 参数 | 说明 | 可执行文件 |
|-----------|------|-----------|
| `cmd` | Windows cmd.exe | `cmd.exe /c` |
| `powershell` / `ps` | Windows PowerShell | `powershell.exe -Command` |
| `bash` | Bash shell | `bash -c` |
| `sh` | POSIX shell | `sh -c` |
| `wsl` | WSL bash | `wsl bash -c` |
| `pwsh` | PowerShell Core | `pwsh -Command` |

### 参数映射规则

与 `@exe` 相同，函数参数名通过前缀约定映射为命令行参数：

| 参数名格式 | 映射为 | 示例 | 说明 |
|-----------|--------|------|------|
| `_f` | 短选项 | `_f="file.txt"` → `-f file.txt` | 单下划线前缀 |
| `_f=None` | 短标志 | `_f=None` → `-f` | 值为 None 时只传标志 |
| `__path` | 长选项 | `__path="/tmp"` → `--path /tmp` | 双下划线前缀 |
| `__verbose=None` | 长标志 | `__verbose=None` → `--verbose` | 值为 None 时只传标志 |
| `name` (无前缀) | 位置参数 | `name="hello"` → 追加到命令末尾 | 按参数定义顺序排列 |

### 全部参数列表

```python
@cmd(
    cmd_str,            # 命令字符串
    *,
    shell='powershell', # 使用的 shell 类型
    async_mode=False,   # 是否启用异步模式
    fallback=None,      # 显式回退函数
)
def my_func(...):
    pass
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cmd_str` | `str` / `None` | 自动推断 | 基础命令字符串。省略或传 `None` 时使用函数名作为命令 |
| `shell` | `str` | `powershell` | shell 类型，支持：`cmd`, `powershell/ps`, `bash`, `sh`, `wsl`, `pwsh` |
| `async_mode` | `bool` | `False` | 是否返回异步函数，异步模式在线程池中执行 |
| `fallback` | `Callable` | `None` | 显式指定回退函数，优先级高于函数体 fallback |

### 命令名自动推断

当 `cmd_str` 省略或传 `None` 时，自动使用被装饰函数的名称作为命令名：

```python
# 无括号形式，函数名即命令名
@cmd
def echo(msg: str):
    pass

echo("hello")  # 执行: echo hello

# 带括号 + None，同样使用函数名
@cmd(None)
def echo(msg: str):
    pass
```

### PowerShell 命令名自动转换

当 `shell` 为 `powershell`、`ps` 或 `pwsh`，且命令名从函数名推断时，**snake_case** 自动转换为 PowerShell 风格的 **Verb-Noun**（PascalCase 加连字符）：

| 函数名 | 转换为 |
|--------|--------|
| `get_child_item` | `Get-ChildItem` |
| `get_process` | `Get-Process` |
| `write_output` | `Write-Output` |
| `new_item` | `New-Item` |
| `invoke_expression` | `Invoke-Expression` |

> **注意**：显式传入命令名（如 `@cmd("Get-ChildItem")`）时不会自动转换，保持原样。

### 使用示例

#### 示例 1：使用函数名作为命令

```python
from vools.sys import cmd

# 函数名即命令名
@cmd
def echo(msg: str):
    pass

returncode, stdout, stderr = echo("hello world")
```

#### 示例 2：PowerShell snake_case 自动转换

```python
from vools.sys import cmd

# get_child_item -> Get-ChildItem
@cmd
def get_child_item(_recurse=None):
    pass

result = get_child_item()
print(result[1])  # 文件列表
```

#### 示例 3：指定不同的 shell

```python
from vools.sys import cmd

# 使用 cmd.exe
@cmd("dir", shell="cmd")
def dir_cmd():
    pass

# 使用 PowerShell
@cmd("Get-ChildItem", shell="powershell")
def ps_ls():
    pass

# 使用 Bash（Linux/WSL）
@cmd("ls -la", shell="bash")
def bash_ls():
    pass
```

#### 示例 3：带参数的命令

```python
from vools.sys import cmd

@cmd("echo", shell="cmd")
def cmd_echo(msg: str):
    pass

returncode, stdout, stderr = cmd_echo("你好世界")
```

#### 示例 4：异步模式

```python
import asyncio
from vools.sys import cmd

@cmd("ping", shell="cmd", async_mode=True)
async def ping(host: str, _n: int = 4):
    pass

async def main():
    result = await ping("127.0.0.1")
    print(result[1])

asyncio.run(main())
```

#### 示例 5：函数体 fallback

```python
from vools.sys import cmd

@cmd("nonexistent_cmd")
def my_cmd(arg1: str):
    """命令不存在或执行失败时，执行函数体作为兜底"""
    return (0, f"fallback result: {arg1}", "")

result = my_cmd("test")
```

### 返回值说明

返回一个三元组 `(returncode, stdout, stderr)`：

| 元素 | 类型 | 说明 |
|------|------|------|
| `returncode` | `int` | 进程退出码，0 表示成功 |
| `stdout` | `str` | 标准输出（UTF-8 解码） |
| `stderr` | `str` | 标准错误（UTF-8 解码） |

> **编码说明**：`@cmd` 内部自动处理编码，Windows cmd 会先执行 `chcp 65001` 切换到 UTF-8 代码页，输出统一使用 UTF-8 解码。

---

## @dll 装饰器

### 功能说明

`@dll` 装饰器将一个 Python 函数映射为 DLL/共享库中的函数调用。根据函数的类型注解自动映射 ctypes 类型，自动处理字符串编码解码，支持同步/异步模式和 fallback 回退。

### 自动类型映射表

根据 Python 类型注解自动映射到对应的 ctypes 类型：

| Python 类型 | ctypes 类型 | 自动转换 |
|-------------|-------------|----------|
| `int` | `c_int` | — |
| `float` | `c_double` | — |
| `str` | `c_char_p` | 传入时自动编码为 UTF-8 bytes；返回时自动从 bytes 解码为 str |
| `bytes` | `c_char_p` | — |
| `bool` | `c_bool` | — |
| 无注解 / `None` | `c_int` | 默认类型 |

### 全部参数列表

```python
@dll(
    dll_spec,           # DLL 路径和函数名
    *,
    async_mode=False,   # 是否启用异步模式
    fallback=None,      # 显式回退函数
)
def my_func(...) -> ...:
    pass
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dll_spec` | `str` | 必填 | DLL 规格，格式为 `"path/to/dll::func_name"`；只传路径时函数名从被装饰函数名推断 |
| `async_mode` | `bool` | `False` | 是否返回异步函数，异步模式在线程池中执行 |
| `fallback` | `Callable` | `None` | 显式指定回退函数，优先级高于函数体 fallback |

**dll_spec 格式示例：**

```python
# 指定 DLL 路径和函数名
@dll("mylib.dll::add")
def add(a: int, b: int) -> int:
    pass

# 只指定 DLL 路径，函数名从函数名推断
@dll("mylib.dll")
def add(a: int, b: int) -> int:
    pass  # 自动调用 mylib.dll 中的 add 函数
```

### 使用示例

#### 示例 1：简单数值函数

```python
from vools.sys import dll

@dll("mathlib.dll::add")
def add(a: int, b: int) -> int:
    pass

result = add(3, 5)
print(result)  # 8
```

#### 示例 2：字符串参数和返回值

```python
from vools.sys import dll

@dll("greet.dll::hello")
def hello(name: str) -> str:
    pass

result = hello("World")
print(result)  # Hello, World!
# str 自动编码为 bytes 传入，返回 bytes 自动解码为 str
```

#### 示例 3：fallback 回退

```python
from vools.sys import dll

# 函数体作为 fallback
@dll("nonexistent.dll::add")
def add(a: int, b: int) -> int:
    """DLL 不存在或调用失败时，执行 Python 实现兜底"""
    return a + b

result = add(3, 5)
print(result)  # 8（使用 Python fallback）
```

#### 示例 4：异步模式

```python
import asyncio
from vools.sys import dll

@dll("heavy.dll::compute", async_mode=True)
async def compute(n: int) -> int:
    pass

async def main():
    result = await compute(1000000)
    print(result)

asyncio.run(main())
```

#### 示例 5：多种类型组合

```python
from vools.sys import dll

@dll("utils.dll::process")
def process(
    data: bytes,
    length: int,
    flag: bool,
    ratio: float,
) -> int:
    pass

result = process(b"hello", 5, True, 0.8)
```

---

## 函数体自动 fallback 机制

`@exe`、`@cmd` 和 `@dll` 都支持智能的 fallback 机制，规则如下：

### fallback 优先级

1. **显式 `fallback` 参数** — 优先级最高，通过装饰器参数传入的回退函数
2. **函数体实现** — 如果函数体不是 `pass`（或 `None`），函数体本身作为 fallback
3. **无 fallback** — 函数体是 `pass` 且无显式 fallback，失败则抛出异常

### 函数体检测规则

框架通过 AST 解析自动判断函数体是否为"空"：

| 函数体 | 判定为 | 行为 |
|--------|--------|------|
| `pass` | 空 | 纯外部调用，失败则报错 |
| `None` (单个表达式) | 空 | 同上 |
| 空函数体 | 空 | 同上 |
| 有实际代码 | 非空 | 外部调用失败时执行函数体兜底 |

### fallback 触发时机

- **@exe**：可执行文件不存在、进程调用异常
- **@cmd**：shell 执行异常、命令不存在或执行失败
- **@dll**：DLL 文件不存在、DLL 加载失败、函数不存在、调用异常

### 示例对比

```python
# 纯外部调用 - 失败则报错
@exe("ls")
def ls(_l=None):
    pass

# 带函数体 fallback - 失败时用 Python 实现兜底
@exe("ls")
def ls(_l=None):
    import os
    files = os.listdir('.')
    return (0, '\n'.join(files), '')

# 显式 fallback - 优先级最高
def my_ls(_l=None):
    import os
    return (0, '\n'.join(os.listdir('.')), '')

@exe("ls", fallback=my_ls)
def ls(_l=None):
    pass
```

---

## 与 LangBridge 的区别和适用场景

`vools.sys` 和 `vools.bridge`（LangBridge）都是桥接工具，但定位不同：

| 维度 | vools.sys (@exe/@cmd/@dll) | vools.bridge (LangBridge) |
|------|----------------------|---------------------------|
| **桥接对象** | 已编译的 exe/dll 二进制文件、shell 命令 | 源代码字符串，自动编译 |
| **适用场景** | 调用现成的外部工具、第三方库、系统命令 | 性能优化、用其他语言重写函数 |
| **编译器依赖** | 不需要编译器 | 需要对应语言的编译器 |
| **代码位置** | 外部二进制文件中 / shell 命令 | Python 函数体中（代码字符串） |
| **类型系统** | @dll 基于类型注解自动映射 | 各语言独立的类型映射规则 |
| **参数映射** | @exe/@cmd 基于命名约定映射命令行选项 | 函数参数直接映射 |
| **缓存机制** | 无（直接调用） | 基于内容哈希的编译缓存 |
| **依赖关系** | 无 deps 概念 | 支持 deps 依赖、拓扑排序 |
| **支持语言** | 任何能生成 exe/dll 的语言 | 27 种语言内置支持（Nim/Rust/Go/C/C++/Cangjie/Mojo/MoonBit/C#/Java/Scala/Ruby/Julia/R/TypeScript/VB.NET/Perl/Lua/Zig/Kotlin/Swift/PHP/Dart/PowerShell/VBScript/Shell/FreeBASIC） |

### 选型建议

**使用 vools.sys 当：**
- 需要调用系统命令或第三方 CLI 工具
- 需要调用已编译好的 DLL/共享库
- 需要通过不同 shell（cmd/powershell/bash）执行命令
- 不想引入编译器依赖
- 只是简单封装外部程序

**使用 vools.bridge 当：**
- 想用其他语言重写热点函数加速
- 需要即时代码编译和缓存
- 需要多语言代码生成能力
- 需要 deps 依赖管理和项目模式

---

## API 速查

### 顶层导出

```python
from vools.sys import exe, cmd, dll, SysCLI
```

### @exe 装饰器

```python
@exe(exe_path, *, async_mode=False, fallback=None)
def func(_short=None, __long=None, positional=None, *args):
    """
    参数映射:
        _f -> -f value / _f=None -> -f
        __path -> --path value / __path=None -> --path
        无前缀 -> 位置参数（按顺序追加）
    
    返回: (returncode: int, stdout: str, stderr: str)
    """
    pass
```

### @cmd 装饰器

```python
@cmd                     # 无括号：函数名即命令
@cmd(None)               # 传 None：函数名即命令
@cmd(cmd_str)            # 显式指定命令名
@cmd(*, shell='powershell', async_mode=False, fallback=None)
def func(_short=None, __long=None, positional=None, *args):
    """
    shell: cmd, powershell/ps, bash, sh, wsl, pwsh
    参数映射:
        _f -> -f value / _f=None -> -f
        __path -> --path value / __path=None -> --path
        无前缀 -> 位置参数（按顺序追加）
    PowerShell (ps/pwsh): 函数名 snake_case 自动转 Verb-Noun
        get_child_item -> Get-ChildItem
    
    返回: (returncode: int, stdout: str, stderr: str)
    """
    pass
```

### @dll 装饰器

```python
@dll(dll_spec, *, async_mode=False, fallback=None)
def func(a: int, b: str) -> float:
    """
    dll_spec: "path/to/dll" 或 "path/to/dll::func_name"
    类型映射: int->c_int, float->c_double, str->c_char_p, 
              bytes->c_char_p, bool->c_bool, 无注解->c_int
    str 自动编码/解码为 UTF-8
    """
    pass
```

### 共享特性

| 特性 | @exe | @cmd | @dll |
|------|------|------|------|
| 同步调用 | ✅ | ✅ | ✅ |
| 异步模式 (async_mode) | ✅ | ✅ | ✅ |
| 显式 fallback 参数 | ✅ | ✅ | ✅ |
| 函数体自动 fallback | ✅ | ✅ | ✅ |
| 线程池执行 (异步) | ✅ (默认4线程) | ✅ (默认4线程) | ✅ (默认4线程) |
| 仅标准库依赖 | ✅ | ✅ | ✅ |
| shell 选择 | ❌ | ✅ | ❌ |
