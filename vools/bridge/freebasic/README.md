# FreeBASIC 语言桥接模块

## 1. 语言简介

FreeBASIC 是一款自由开源的 BASIC 语言编译器，完全兼容 QuickBASIC，并提供了现代编程语言的特性。`vools.bridge.freebasic` 模块提供了 FreeBASIC 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 FreeBASIC 代码为共享库（DLL/SO/DYLIB）
- 通过 ctypes 加载并调用编译后的函数
- 使用 `Export` 关键字导出函数，确保 C ABI 兼容
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 FreeBASIC 加速函数
- 列表/数组参数通过指针 + 长度传递，零拷贝
- Transport 抽象层，可注入自定义序列化策略

## 2. Bridge 类名

- **类名**: `FreeBasicBridge`
- **全局实例**: `_fb_bridge`
- **装饰器**: `@freebasic` 或 `@fb_bridge.decorator`
- **类型映射器**: 内置类型映射系统 `PY_TO_FB_TYPE`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@freebasic` 装饰器快速定义 FreeBASIC 加速函数 |
| only_code 模式 | ✅ 支持 | `mode='ONLY_CODE'`，仅生成 FreeBASIC 代码，不编译 |
| project 模式 | ⚠️ 部分 | 可通过 fbc 手动编译整个项目 |
| 异步模式 | ✅ 支持 | `async_mode=True`，返回 Future，可 await |
| 回退机制 | ✅ 支持 | fallback 参数，编译失败时回退 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |
| 免序列化数组 | ✅ 支持 | list 参数通过指针 + 长度传递，零拷贝 |
| Transport 抽象 | ✅ 支持 | 可注入自定义传输层 |

## 4. 编译器要求

`vools.bridge.freebasic` 模块**已内置 32/64 位 FreeBASIC 编译器**（fbc32.exe / fbc64.exe）以及完整的头文件库，开箱即用，无需手动安装。

> 内置编译器版本：FreeBASIC 1.x（详见 `compiler/VERSION` 或通过 `fbc --version` 查询）

### 自动检测

```python
from vools.bridge import freebasic

# 检查编译器是否可用（已内置，应返回 True）
if freebasic.fbc_compiler_available():
    print("FreeBASIC 编译器可用（内置）")
else:
    print("FreeBASIC 编译器不可用")
```

### 使用外部 FreeBASIC（可选）

如需使用系统安装的 FreeBASIC（覆盖内置版本），将 `fbc64.exe` / `fbc` 加入系统 PATH：
- **Windows**: 从 [FreeBASIC 官网](https://www.freebasic.net/) 下载并安装
- **Linux**: `sudo apt-get install freebasic`

### 验证内置编译器

```python
import os
from vools.bridge.freebasic import _get_fbc_path

fbc_path = _get_fbc_path()
print(f"使用的 fbc 路径: {fbc_path}")
print(f"存在: {os.path.exists(fbc_path)}")
```

## 5. 类型映射表

| Python 类型 | FreeBASIC 类型 | ctypes 类型 | 说明 |
|------------|---------------|------------|------|
| `int` | `Long` | `c_long` | 32 位有符号整数 |
| `float` | `Double` | `c_double` | 双精度浮点数 |
| `bool` | `Long` | `c_long` | 布尔值（0/1） |
| `str` / `bytes` | `ZString Ptr` | `c_char_p` | C 字符串指针 |
| `list[int]` | `Long Ptr` + `n As Long` | `POINTER(c_long)` + `c_long` | 整数数组指针 + 长度 |
| `list[float]` | `Double Ptr` + `n As Long` | `POINTER(c_double)` + `c_long` | 浮点数数组指针 + 长度 |
| `None` | `Sub` 或函数无返回值 | `restype = None` | 无返回值 |

> **注意**：`list` 类型的参数会自动展开为 `(指针, 长度)` 两个参数。例如 `arr: list` 在 FreeBASIC 端会变成 `arr As Long Ptr, n As Long`。

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.freebasic import freebasic

@freebasic
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "Return a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@freebasic
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return """
    If n <= 1 Then
        Return 1
    Else
        Return fib(n - 1) + fib(n - 2)
    End If
    """

result = fib(10)
print(result)  # 输出: 89
```

### 数组求和（免序列化）

```python
@freebasic
def sum_arr(arr: list) -> int:
    """
    数组求和（零拷贝）
    
    list 参数自动展开为 (ptr, n) 两个参数：
    - arr: Long Ptr（数组指针）
    - n: Long（数组长度，由参数名 + '_n' 后缀自动生成）
    """
    return """
    Dim As Long i, total
    total = 0
    For i = 0 To n - 1
        total += arr[i]
    Next
    Return total
    """

print(sum_arr([1, 2, 3, 4, 5]))  # 输出: 15
```

### 字符串处理

```python
@freebasic
def greet(name: str) -> str:
    return """
    ' 字符串处理示例
    ' name 是 ZString Ptr 类型
    Return name
    """

message = greet("World")
print(message)
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * x

@freebasic(fallback=python_fallback)
def square(x: int) -> int:
    return "Return x * x"

result = square(5)
print(result)  # 输出: 25
```

### 异步模式

```python
import asyncio
from vools.bridge.freebasic import freebasic

@freebasic(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    Dim As Long i, total
    total = 0
    For i = 0 To n - 1
        total += i
    Next
    Return total
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

## 7. only_code 模式示例

仅生成 FreeBASIC 代码，不编译执行：

```python
@freebasic(mode='ONLY_CODE')
def generate_code(a: int, b: int) -> int:
    return "Return a + b"

code = generate_code(1, 2)
print(code)
# 输出完整的 FreeBASIC 源码，包括函数声明和 Export 关键字
```

### 使用 LangBridge 的 only_code 模式

```python
from vools.bridge.freebasic import FreeBasicBridge

fb_bridge = FreeBasicBridge()

@fb_bridge.decorator(only_code=True)
def add(a: int, b: int) -> int:
    return "Return a + b"

code = add(1, 2)
print(code)
```

### 输出到文件

```python
@fb_bridge.decorator(only_code=True, output_file='./output/add.bas')
def add(a: int, b: int) -> int:
    return "Return a + b"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

## 8. project 模式示例

### 手动编译 FreeBASIC 代码

```python
import subprocess

# 手动调用 fbc 编译
source_file = 'my_program.bas'
output_dll = 'my_program.dll'

result = subprocess.run(
    ['fbc', '-dll', source_file, '-o', output_dll],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print(f"编译成功: {output_dll}")
else:
    print(f"编译失败: {result.stderr}")
```

### 加载 DLL 并调用

```python
import ctypes
from vools.bridge.core.types import CTypeMapper

# 加载 DLL
lib = ctypes.CDLL('./my_program.dll')

# 设置函数签名
add_func = lib.add
add_func.argtypes = [CTypeMapper.get_ctype(int), CTypeMapper.get_ctype(int)]
add_func.restype = CTypeMapper.get_ctype(int)

# 调用函数
result = add_func(10, 20)
print(f"结果: {result}")
```

### 使用 FreeBASIC 模块

```python
from vools.bridge.freebasic import compile_freebasic_code, call_freebasic_function

# 手动编译
dll_path = compile_freebasic_code(
    code='''
    Function add Alias "add" (a As Long, b As Long) As Long Export
        Return a + b
    End Function
    ''',
    func_name='add'
)

# 调用
result = call_freebasic_function(dll_path, 'add', [5, 3], ret_type=int)
print(result)  # 输出: 8
```

## 9. 注意事项

### 函数签名
- FreeBASIC 导出函数必须使用 `Export` 关键字
- 使用 C 调用约定时需注意参数传递方式
- 自动签名生成模式下会自动处理这些细节

### 数组传递（免序列化）
- `list` 类型的参数会自动展开为 `(指针, 长度)` 两个参数
- 例如 `arr: list` → `arr As Long Ptr, n As Long`
- 长度参数名规则：原参数名 + `_n` 后缀
- 这种方式是零拷贝的，性能远高于序列化/反序列化

### 字符串处理
- 字符串通过 `ZString Ptr` 传递（以 null 结尾的 C 字符串）
- FreeBASIC 字符串与 C 字符串转换需注意编码
- 返回字符串时注意内存管理

### 编译缓存
- 缓存目录基于系统临时目录 + vools_freebasic_cache
- 命名：`<func_name>_<md5[:12]>.bas` 与 `<func_name>_<md5[:12]>.dll`
- 命中规则：相同源码 → 相同 md5 → 复用 DLL，不重新编译
- 强制重编：`mode='DEBUG'`

### Transport 扩展点
默认使用 ctypes 实现。如需注入自定义策略：

```python
from vools.bridge.freebasic import set_transport

# 自定义 transport 实现
class MyTransport:
    def prepare_arg(self, arg, fb_type): ...
    def prepare_ret(self, fb_type): ...
    def decode_result(self, value, fb_type): ...

set_transport(MyTransport())
```

### 运行模式

| mode | 行为 |
|------|------|
| `DEBUG` | 强制重编译 + 执行 |
| `FORCE` | 只强制重编译，不执行（返回 DLL 路径） |
| `NORMAL` | 命中缓存跳过编译；未命中则编译（默认） |
| `ONLY_RUN` | 缓存未命中抛异常 |
| `ONLY_CODE` | 只返回生成的 FreeBASIC 源码字符串，不编译 |

## 10. 内置扩展 DLL 库

`vools.bridge.freebasic` 模块**内置了 9 个常用第三方 DLL 库**，按类别组织在 `libs/win64/` 目录下：

| 类别 | 库 | 说明 |
|------|-----|------|
| **database** | sqlite3.dll | SQLite3 数据库引擎 |
| **database** | libmysql.dll | MySQL/MariaDB 客户端库 |
| **graphics** | cairo.dll | Cairo 2D 图形渲染库 |
| **multimedia** | SDL3.dll | SDL3 多媒体库（窗口/渲染/事件） |
| **multimedia** | SDL3_image.dll | SDL3 图像加载扩展 |
| **multimedia** | SDL3_mixer.dll | SDL3 音频混音扩展 |
| **multimedia** | SDL3_ttf.dll | SDL3 字体渲染扩展 |
| **gui** | Scintilla.dll | Scintilla 代码编辑控件 |
| **gui** | mCtrl.dll | mCtrl Windows 控件库 |

### 库清单查询

```python
from vools.bridge import freebasic

# 列出所有可用的第三方 DLL 库
print(freebasic.list_fb_libs())
# ['sqlite3', 'libmysql', 'cairo', 'SDL3', 'SDL3_image', ...]

# 按类别过滤
print(freebasic.list_fb_libs('database'))
# ['sqlite3', 'libmysql']
```

### 通过 ctypes 直接调用

```python
from vools.bridge import freebasic

# 加载 SQLite3 DLL（自动加载依赖）
lib = freebasic.get_fb_lib('sqlite3', category='database')
print(lib.sqlite3_libversion())  # b'3.50.4'
```

### Python 端 SQLite3 shim 层

模块内置 SQLite3 兼容层，当标准库 sqlite3 不可用时自动 fallback：

```python
from vools.bridge import freebasic

# 检查可用性
if freebasic.is_sqlite3_available():
    print(f"SQLite3 可用，版本: {freebasic.sqlite3_version()}")

# 连接数据库（标准 sqlite3 接口）
conn = freebasic.connect(':memory:')
cursor = conn.cursor()
cursor.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)')
cursor.execute("INSERT INTO t (name) VALUES (?)", ('Alice',))
conn.commit()
```

## 11. .bas 封装模块（简化 @fbc 调用）

`vools.bridge.freebasic.modules` 提供对第三方 DLL 的 FreeBASIC 端**简化封装层**，
统一以 `fb_` 前缀命名，避免直接使用复杂的 C API。

### 可用模块

| 模块名 | 头文件依赖 | 库文件 | 典型场景 |
|--------|-----------|--------|----------|
| `sqlite3_wrapper` | `database/inc/sqlite3.bi` | `database/sqlite3.dll` | 嵌入式数据库 |
| `cairo_wrapper` | `graphics/inc/cairo/cairo.bi` | `graphics/cairo.dll` | 2D 图形渲染 |
| `sdl3_wrapper` | `multimedia/inc/SDL3.bi` | `multimedia/SDL3.dll` | 窗口/输入/音频 |

### 查询模块信息

```python
from vools.bridge import freebasic

# 列出所有可用模块
print(freebasic.list_fb_modules())
# ['cairo_wrapper', 'sdl3_wrapper', 'sqlite3_wrapper']

# 读取模块源码
code = freebasic.get_fb_module('sqlite3_wrapper')

# 获取头文件搜索路径
inc_paths = freebasic.get_fb_inc_paths('sqlite3_wrapper')

# 获取库搜索路径
lib_paths = freebasic.get_fb_lib_paths('sqlite3_wrapper')
```

### 使用示例：SQLite3 查询

```python
from vools.bridge import freebasic
from vools.bridge.freebasic import compile_and_run

sqlite_code = freebasic.get_fb_module('sqlite3_wrapper')

result = compile_and_run(
    '''
    Dim As ZString Ptr v = fb_sqlite3_libversion()
    Return v
    ''',
    func_name='test_sqlite',
    ret_type='ZString Ptr',
    extra_includes=[sqlite_code],
    inc_paths=freebasic.get_fb_inc_paths('sqlite3_wrapper'),
    lib_paths=freebasic.get_fb_lib_paths('sqlite3_wrapper'),
)
print(result)  # '3.50.4'
```

### 使用示例：Cairo 绘图

```python
from vools.bridge import freebasic
from vools.bridge.freebasic import compile_and_run

cairo_code = freebasic.get_fb_module('cairo_wrapper')

result = compile_and_run(
    '''
    '' 创建一个 200x200 的 ARGB32 surface
    Dim As FB_CAIRO_SURFACE Ptr surf = fb_cairo_image_surface_create(0, 200, 200)
    '' 错误检测
    If surf = 0 OrElse surf->handle = 0 Then Return -1
    '' 销毁
    fb_cairo_surface_destroy(surf)
    Return 0
    ''',
    func_name='cairo_test',
    ret_type='Long',
    extra_includes=[cairo_code],
    inc_paths=freebasic.get_fb_inc_paths('cairo_wrapper'),
    lib_paths=freebasic.get_fb_lib_paths('cairo_wrapper'),
)
```

### 使用示例：SDL3 初始化

```python
from vools.bridge import freebasic
from vools.bridge.freebasic import compile_and_run

sdl_code = freebasic.get_fb_module('sdl3_wrapper')

result = compile_and_run(
    '''
    Return fb_sdl3_init(0)
    ''',
    func_name='sdl_test',
    ret_type='Long',
    extra_includes=[sdl_code],
    inc_paths=freebasic.get_fb_inc_paths('sdl3_wrapper'),
    lib_paths=freebasic.get_fb_lib_paths('sdl3_wrapper'),
)
print(f"SDL3 初始化返回: {result}")
```

## 12. 编译参数注入

`compile_and_run` / `compile_and_run_async` 接受以下与 fbc 编译相关的参数：

| 参数 | 作用 | 示例 |
|------|------|------|
| `extra_includes` | 额外注入的源码片段（字符串列表），会拼接到主代码前 | `[freebasic.get_fb_module('sqlite3_wrapper')]` |
| `inc_paths` | 头文件搜索路径（通过 `-i` 传给 fbc） | `freebasic.get_fb_inc_paths('sqlite3_wrapper')` |
| `lib_paths` | 库搜索路径（通过 `-p` 传给 fbc） | `freebasic.get_fb_lib_paths('sqlite3_wrapper')` |
| `cache_dir` | 编译缓存目录，默认 `%TEMP%/vools_fbc_cache` | `None` |

`lib_paths` 同时会被 `_load_fbc_dll` 用于 `os.add_dll_directory`（Python 3.8+），
确保运行时能找到所有依赖 DLL。

## 13. 链接器 .a 导入库生成

对于未提供 .a 导入库的第三方 DLL（如 `sqlite3.dll`），需要先用 `dlltool` 生成：

```python
import subprocess
import pefile
import os

def gen_a(dll_path, a_path):
    pe = pefile.PE(dll_path)
    symbols = [e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name]
    dll_name = os.path.basename(dll_path)
    def_content = f'LIBRARY {dll_name}\nEXPORTS\n' + '\n'.join(f'  {s}' for s in symbols)
    def_path = a_path + '.def'
    with open(def_path, 'w', encoding='utf-8') as f:
        f.write(def_content)
    subprocess.run(['dlltool.exe', '-D', dll_name, '-d', def_path, '-l', a_path], check=True)
    os.remove(def_path)

gen_a('libs/win64/database/sqlite3.dll', 'libs/win64/database/libsqlite3.a')
```

> vools 已为所有内置 DLL 预生成 `lib<name>.a` 导入库，开箱即用。

### FreeBASIC 语法特点
- 不区分大小写（`Function` 和 `function` 相同）
- 行尾不需要分号
- 注释使用 `'` 单引号
- 数组下标默认从 0 开始
- 字符串操作使用 `+` 连接

### 性能提示
- 首次调用需要编译 FreeBASIC 代码，后续调用使用缓存
- 数组使用免序列化传递，性能远高于序列化方式
- FreeBASIC 编译为原生机器码，性能接近 C
- 小函数调用开销主要来自 ctypes 边界

### 平台支持
- Windows 支持最好（官方主要平台）
- Linux 支持（需安装 freebasic 包）
- macOS 理论支持（可能需要自行编译）
- 自动检测平台并生成对应格式的共享库

### 相关资源
- [FreeBASIC 官方网站](https://www.freebasic.net/)
- [FreeBASIC 文档](https://www.freebasic.net/wiki/DocToc)
- [FreeBASIC 论坛](https://www.freebasic.net/forum/)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
