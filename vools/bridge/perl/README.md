# vools.bridge.perl - Perl 语言桥接模块

Perl 是一种高级、解释型、动态编程语言，以其强大的文本处理能力而闻名。vools 桥接模块允许 Python 代码直接调用 Perl 脚本。

---

## 1. 语言简介

Perl 最初由 Larry Wall 于 1987 年设计，最初用于文本处理和系统管理任务。Perl 拥有强大的正则表达式支持和简洁的语法，在生物信息学、金融分析和 Web 开发等领域有广泛应用。

**主要特点：**
- 强大的正则表达式和文本处理能力
- 解释型语言，无需编译即可运行
- 灵活的语法，支持多种编程范式
- 丰富的 CPAN 模块生态系统

---

## 2. Bridge 类名

**类名：** `PerlBridge`

**模块路径：** `vools.bridge.perl`

**导入方式：**

```python
from vools.bridge.perl import PerlBridge, perl_bridge, perl

# 或完整导入
from vools.bridge import perl
```

**全局实例：** `perl_bridge` / `_perl_bridge`

---

## 3. 支持的功能

### 3.1 单函数装饰器模式

使用 `@perl` 装饰器装饰 Python 函数，函数体为 Perl 代码，首次调用自动编译执行。

### 3.2 依赖函数支持

通过 `deps` 参数声明依赖的辅助函数，自动解析依赖拓扑顺序。

```python
@perl(deps=[helper])
def main_func(x: int) -> int:
    return "return helper(x) + 1"
```

### 3.3 模块级代码

通过 `module_code` 参数注入 Perl 模块级代码（如 use 语句、变量初始化等）。

### 3.4 异步模式

通过 `async_mode=True` 启用异步执行，返回 `PerlFuture` 对象。

### 3.5 回退机制

通过 `fallback` 参数指定编译器不可用时的回退函数。

### 3.6 仅代码模式

通过 `only_code=True` 仅生成 Perl 代码，不执行编译。

### 3.7 项目模式

通过 `project_dir` 参数编译整个 Perl 项目目录。

---

## 4. 运行环境要求

### 4.1 Perl 解释器

**必需：** Perl 5.x 解释器

**Windows 搜索路径：**
- `C:\Perl\bin`
- `C:\Strawberry\perl\bin`
- `C:\ActivePerl\bin`
- `~/perl/bin`

**Unix/Linux/macOS 搜索路径：**
- `/usr/bin`
- `/usr/local/bin`
- `/opt/homebrew/bin`
- `~/.rbenv/shims` (不适用，仅作参考)

### 4.2 Perl 模块依赖

**必需模块：**
- `JSON::PP` - JSON 编解码（Perl 5.14+ 内置）

**可选模块（自动检测）：**
- `utf8` - UTF-8 编码支持

### 4.3 缓存目录

默认缓存目录：`系统临时目录/vools_perl_cache`

可通过 `cache_dir` 参数自定义缓存位置。

---

## 5. 类型映射

### 5.1 Python → Perl 类型

| Python 类型 | Perl 类型 | 说明 |
|------------|----------|------|
| `int` | `int` | 整数 |
| `float` | `num` | 浮点数 |
| `bool` | `bool` | 布尔值 |
| `str` | `str` | 字符串 |
| `bytes` | `str` | 字节串（作为字符串处理） |
| `list` / `tuple` | `array` | 数组 |
| `dict` | `hash` | 哈希表 |
| `None` | `undef` | 未定义值 |

### 5.2 Perl → ctypes 类型

| Perl 类型 | ctypes 类型 | 说明 |
|----------|-------------|------|
| `int` | `c_int` | C 整数 |
| `num` | `c_double` | C 双精度浮点 |
| `str` | `c_char_p` | C 字符指针 |
| `bool` | `c_bool` | C 布尔值 |
| `array` | `POINTER(c_int)` | 数组指针 |
| `hash` | `c_void_p` | void 指针 |
| `undef` | `None` | 无对应类型 |

### 5.3 类型推断

`infer_perl_argtypes()` 函数根据运行时参数值自动推断 Perl 类型：

```python
# Python 端
args = (10, 3.14, "hello", [1, 2, 3], {"key": "value"})

# 推断结果
['int', 'num', 'str', 'array', 'hash']
```

---

## 6. 快速使用示例

### 6.1 基础用法

```python
from vools.bridge.perl import perl

@perl
def add(x: int, y: int) -> int:
    return "return x + y"

result = add(10, 20)
print(result)  # 30
```

### 6.2 使用别名

```python
from vools.bridge.perl import pl

@pl
def factorial(n: int) -> int:
    return """
    my $result = 1;
    for (my $i = 1; $i <= $n; $i++) {
        $result *= $i;
    }
    return $result;
    """

result = factorial(5)
print(result)  # 120
```

### 6.3 带依赖函数

```python
def helper(x: int) -> int:
    return "return x * 2"

@perl(deps=[helper])
def compute(x: int) -> int:
    return "return helper(x) + 1"

result = compute(5)
print(result)  # 11
```

### 6.4 带模块级代码

```python
@perl(module_code="use List::Util qw(sum);")
def average(arr: list) -> float:
    return "return sum(@arr) / scalar(@arr)"

result = average([1, 2, 3, 4, 5])
print(result)  # 3.0
```

### 6.5 异步模式

```python
from vools.bridge.perl import perl, PerlFuture

@perl(async_mode=True)
def slow_operation(n: int) -> int:
    return "return $n ** 2"

future = slow_operation(100)
result = future.result()
print(result)  # 10000
```

### 6.6 带回退函数

```python
@perl(fallback=lambda x, y: x + y)
def add(x: int, y: int) -> int:
    return "return x + y"

result = add(10, 20)
print(result)  # 30
```

---

## 7. only_code 模式示例

`only_code` 模式仅生成 Perl 代码，不执行编译，适用于代码生成和调试场景。

### 7.1 生成代码到标准输出

```python
from vools.bridge.perl import perl

@perl(only_code=True)
def hello(name: str) -> str:
    return 'print "Hello, $name!\\n";'

# 输出生成的 Perl 代码
```

### 7.2 生成代码到文件

```python
from vools.bridge.perl import perl

@perl(only_code=True, output_file="output/hello.pl")
def hello(name: str) -> str:
    return 'print "Hello, $name!\\n";'
```

### 7.3 追加模式

```python
@perl(only_code=True, output_file="utils.pl", write_mode="append")
def util1(x: int) -> int:
    return "return $x * 2"

@perl(only_code=True, output_file="utils.pl", write_mode="append")
def util2(x: int) -> int:
    return "return $x ** 2"
```

### 7.4 自定义前后缀

```python
@perl(only_code=True, output_file="script.pl",
      prefix="#!/usr/bin/env perl\\nuse strict;\\nuse warnings;\\n",
      suffix="\\nprint \"Done!\\n\";")
def main():
    return 'print "Hello World!\\n";'
```

---

## 8. project 模式示例

`project` 模式用于编译整个 Perl 项目目录，支持批量处理多个 .pl 文件。

### 8.1 项目结构示例

```
my_perl_project/
├── main.pl          # 入口文件
├── utils.pl         # 工具函数
└── math.pl          # 数学函数
```

### 8.2 入口文件 (main.pl)

```perl
#!/usr/bin/env perl
use strict;
use warnings;
use JSON::PP;

sub process_data {
    my ($data) = @_;
    # 处理数据
    return $data * 2;
}

1;
```

### 8.3 使用项目模式

```python
from vools.bridge.perl import perl

@perl(project_dir="./my_perl_project", entry="process_data")
def process(x: int) -> int:
    pass

result = process(42)
print(result)  # 84
```

### 8.4 执行 main.pl

```python
from vools.bridge.perl import perl_bridge

# 返回 (returncode, stdout, stderr)
result = perl_bridge.run_project("./my_perl_project", entry="main", args=())
print(result)
```

### 8.5 项目模式打包

当 `entry != 'main'` 时，项目模式会：
1. 扫描项目目录下所有 `.pl` 文件
2. 按文件名排序拼接所有文件内容
3. 在末尾添加入口函数调用代码
4. 输出打包后的 `.pl` 文件路径

```python
# 打包项目中所有 .pl 文件，入口函数为 compute
artifact_path = perl_bridge.compile_project(
    "./my_perl_project",
    entry="compute",
    output_dir="./output"
)
print(f"打包文件: {artifact_path}")
```

---

## 9. 注意事项

### 9.1 Perl 代码限制

- **返回值格式：** 函数体中应使用 `return` 语句返回值，裸表达式会自动返回最后一条语句的结果
- **标点符号：** Perl 语句必须以分号 `;` 结尾
- **变量声明：** 使用 `my` 声明变量，Perl 5 及以上版本强制使用 `strict`
- **特殊变量：** Perl 的特殊变量如 `$_`、`@_`、`%_` 可直接使用，但需注意上下文

### 9.2 性能考虑

- Perl 是解释型语言，每次调用都会启动 `perl` 进程
- 对于高频调用场景，建议使用项目模式预编译
- 大量数据传递建议使用 JSON 序列化

### 9.3 路径问题

- Windows 路径使用反斜杠 `\` 或正斜杠 `/`
- Unix/Linux/macOS 路径使用正斜杠 `/`
- 建议使用 `os.path` 处理跨平台路径

### 9.4 编码问题

- 源代码默认以 UTF-8 编码读写
- Perl 脚本开头自动添加 `use strict; use warnings;`
- 字符串处理时注意编码一致性

### 9.5 JSON 依赖

- 参数传递使用 JSON::PP 模块（Perl 5.14+ 内置）
- 老版本 Perl 用户需安装 JSON::PP 或 JSON::XS

### 9.6 错误处理

- Perl 脚本执行失败时抛出 `RuntimeError`
- 错误信息包含 stderr、stdout 和源代码
- 建议使用 `try-except` 捕获执行异常

### 9.7 缓存管理

- 缓存键基于代码内容的 MD5 哈希
- 缓存目录位于系统临时目录
- 长时间运行建议定期清理缓存

---

## 附录：API 参考

### 函数

| 函数 | 说明 |
|------|------|
| `perl_compiler_available()` | 检查 Perl 解释器是否可用 |
| `compile_and_run(code, func_name, args, ret_type, cache_dir)` | 编译并运行代码 |
| `get_perl_type(py_type)` | 获取 Perl 类型字符串 |
| `get_perl_ctype(perl_type)` | 获取 ctypes 类型 |

### 类

| 类 | 说明 |
|---|------|
| `PerlBridge` | Perl 桥接实现类 |
| `PerlFuture` | 异步执行结果封装 |
