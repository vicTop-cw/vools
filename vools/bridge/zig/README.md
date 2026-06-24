# Zig 语言桥接模块

## 1. 语言简介

Zig 是一门专注于性能、安全和互操作性的系统编程语言。它提供精确的类型控制、编译时计算和零成本抽象，被视为 C 语言的现代替代品。

**特点**：
- 性能优异，接近 C 的执行效率
- 编译时求值和类型检查
- 无隐藏控制流和内存分配
- 简洁的语法和强大的 comptime

## 2. Bridge 类名

```python
from vools.bridge.zig import ZigBridge

bridge = ZigBridge()
```

## 3. 支持的功能

- ✅ **代码生成**：根据 Python 函数生成 Zig 代码
- ✅ **动态库编译**：使用 `zig build-lib` 编译为 .so/.dll
- ✅ **函数调用**：通过 ctypes 调用编译后的动态库
- ✅ **项目编译**：编译整个 Zig 项目目录
- ✅ **异步模式**：支持 async_mode 异步装饰器
- ✅ **回退机制**：编译器不可用时自动调用回退函数
- ✅ **依赖解析**：支持 deps 参数处理函数依赖
- ✅ **模块代码**：支持 module_code 添加模块级代码

## 4. 运行环境要求

- **Zig 编译器**：必须安装 Zig 并配置好 PATH 环境变量
- **最低版本**：Zig 0.11.0 或更高版本
- **操作系统**：支持 Windows、Linux、macOS

### 检查 Zig 是否可用

```python
from vools.bridge.zig import zig_compiler_available

if zig_compiler_available():
    print("Zig 编译器可用")
else:
    print("Zig 编译器不可用，请安装")
```

## 5. 类型映射

### Python → Zig 类型

| Python 类型 | Zig 类型 | 说明 |
|------------|---------|------|
| `int` | `i64` | 64位整数 |
| `float` | `f64` | 64位浮点数 |
| `str` | `[*:0]const u8` | C 风格字符串 |
| `bool` | `bool` | 布尔值 |
| `list` | `[]i64` | 整数切片 |
| `dict` | `std.StringHashMap(i64)` | 字符串哈希表 |
| `None` | `void` | 无返回值 |

### Zig 类型 → ctypes 类型

| Zig 类型 | ctypes 类型 |
|---------|------------|
| `i8` | `c_int8` |
| `i16` | `c_int16` |
| `i32` | `c_int` |
| `i64` | `c_int64` |
| `u8` | `c_uint8` |
| `u16` | `c_uint16` |
| `u32` | `c_uint32` |
| `u64` | `c_uint64` |
| `f32` | `c_float` |
| `f64` | `c_double` |
| `bool` | `c_bool` |
| `*:const u8` | `c_char_p` |
| `void` | `None` |

## 6. 快速使用示例

### 基础装饰器用法

```python
from vools.bridge.zig import zig, zig_bridge

@zig
def add(x: int, y: int) -> int:
    return "return x + y"

result = add(1, 2)
print(result)  # 输出: 3
```

### 带依赖的函数

```python
@zig
def helper(a: int) -> int:
    return "return a * 2"

@zig(deps=[helper])
def complex_calc(x: int, y: int) -> int:
    return "return helper(x) + y"

result = complex_calc(3, 4)  # 输出: 10
```

### 模块级代码

```python
module_code = '''
const std = @import("std");
var gpa = std.heap.GeneralPurposeAllocator(.{}){};
'''

@zig(module_code=module_code)
def with_module(x: int) -> int:
    return "return x + 1"
```

## 7. only_code 模式示例

仅生成 Zig 代码，不编译：

```python
from vools.bridge.zig import zig

@zig(only_code=True)
def generate_code(x: int) -> int:
    return "return x * x"

# 获取生成的代码
code = generate_code(5)
print(code)
# 输出:
# const std = @import("std");
#
# export fn vools_generate_code(x: i64) i64 {
# return x * x
# return ;
# }
```

### 保存代码到文件

```python
@zig(only_code=True, output_file="output.zig")
def save_code(x: int) -> int:
    return "return x + x"

# 代码会自动保存到 output.zig
result = save_code(10)
print(result)  # 输出: output.zig
```

## 8. project 模式示例

编译整个 Zig 项目：

```python
from vools.bridge.zig import zig

@zig(project_dir="./my_zig_project", entry="main")
def build_project():
    pass

# 编译项目
result = build_project()
print(result)  # 输出: (0, stdout, stderr) 或编译产物路径
```

### 指定入口函数

```python
@zig(project_dir="./my_zig_project", entry="my_func")
def call_library():
    pass

# 调用库中的函数
result = call_library()
```

## 9. 注意事项

### Zig 编译器要求

- 必须安装 Zig 编译器并确保 `zig` 命令在 PATH 中可用
- 建议使用 Zig 0.11.0 或更高版本
- 可通过 `zig version` 命令验证安装

### 函数命名

- Zig 导出的函数会自动添加 `vools_` 前缀
- 原始函数名可通过 `zig_bridge.call_func(lib_path, "func_name", args)` 调用

### 异步模式

```python
@zig(async_mode=True)
async def async_func(x: int) -> int:
    return "return x * 2"

result = await async_func(5)  # 输出: 10
```

### 回退机制

```python
def python_fallback(x: int) -> int:
    return x * 2

@zig(fallback=python_fallback)
def may_fail(x: int) -> int:
    return "return x * x"

# 当 Zig 编译器不可用时，自动使用 Python 回退
result = may_fail(5)  # 输出: 10
```

### 字符串处理

- Zig 中的字符串使用 `[*:0]const u8` 类型
- ctypes 调用时会自动处理 Python str 和 bytes 之间的转换

### 编译产物

- Windows: `.dll` 文件
- Linux/macOS: `.so` 文件
- 编译产物缓存在系统临时目录中
