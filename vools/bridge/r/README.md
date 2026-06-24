# vools.bridge.r — R 语言桥接

> 统计计算语言桥接，基于 JSON 序列化的进程间数据交换

## 语言简介

R 是一种广泛用于统计计算和数据分析的编程语言和软件环境。它提供了丰富的统计和图形技术，并且具有强大的包生态系统。

本模块提供 R 语言动态执行与跨语言桥接能力，采用装饰器模式，函数返回 R 代码字符串，装饰器自动调用 Rscript 执行并返回结果。支持 Windows 下通过 WSL 调用 R，以及 Linux 原生 R 环境。

## Bridge 类名

**`RBridge`** — 继承自 `LangBridge` 抽象基类的 R 语言桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@r` 装饰器，函数体返回 R 代码字符串 |
| only_code 模式 | ✅ | 只生成 R 源码，不执行 |
| project 模式 | ✅ | 支持项目级编译和执行 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 支持异步执行 |
| 回退机制 | ✅ | `fallback` 参数支持 Python 回退实现 |
| 模块装饰器 | ✅ | `@r_module` 装饰器，批量桥接类方法 |

## 运行环境要求

- **R 版本**：>= 3.6（推荐 4.0+）
- **安装方式**：
  - Windows（WSL）：在 WSL 中安装 R：`sudo apt-get install r-base`
  - Linux：`sudo apt-get install r-base` 或 `sudo yum install R`
  - macOS：`brew install r`
- **PATH 配置**：确保 `Rscript` 命令可用
- **推荐包**：`jsonlite`（用于高性能 JSON 序列化）
  ```R
  install.packages("jsonlite")
  ```
- **Windows 要求**：需安装 WSL 2，并在 WSL 中安装 R

验证安装：
```bash
# Linux/macOS
Rscript --version

# Windows (WSL)
wsl Rscript --version
```

## 类型映射表

| Python 类型 | R 类型 | 说明 |
|------------|--------|------|
| `int` | `integer` | 整数类型 |
| `float` | `numeric` | 数值类型（浮点数） |
| `bool` | `logical` | 逻辑类型（布尔值） |
| `str` | `character` | 字符类型（字符串） |
| `bytes` | `character` | 字节串转换为字符串 |
| `list` | `vector` / `list` | 列表/向量类型 |
| `dict` | `list` | 字典映射为 R 的 list（命名列表） |
| `tuple` | `vector` | 元组转换为向量 |
| `None` | `NULL` | 空值 |

### list 参数的类型推断

| Python 列表内容 | 推断的 R 类型 |
|----------------|-------------|
| 全为整数 | `integer` |
| 全为浮点数 | `numeric` |
| 全为字符串 | `character` |
| 全为布尔值 | `logical` |
| 混合类型 | `list` |

## 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.r import r, r_compiler_available

if not r_compiler_available():
    raise RuntimeError('请先安装 R 和 Rscript')

@r
def add(a: int, b: int) -> int:
    """简单的加法函数"""
    return "return(a + b)"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@r
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return '''
    if (n <= 1) {
        return(1)
    } else {
        return(fib(n - 1) + fib(n - 2))
    }
    '''

result = fib(10)
print(result)  # 输出: 89
```

### 字符串处理

```python
@r
def greet(name: str) -> str:
    """字符串拼接"""
    return 'return(paste0("Hello, ", name, "!"))'

result = greet("World")
print(result)  # 输出: Hello, World!
```

### 向量操作

```python
@r
def sum_vector(vec: list) -> float:
    """向量求和"""
    return '''
    return(sum(vec))
    '''

result = sum_vector([1.0, 2.0, 3.0, 4.0, 5.0])
print(result)  # 输出: 15.0
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * 2

@r(fallback=python_fallback)
def double_it(x: int) -> int:
    """使用 R 实现，失败则回退到 Python"""
    return "return(x * 2)"

result = double_it(5)
print(result)  # R 可用时输出 10，不可用时回退到 Python 也输出 10
```

### 异步模式

```python
import asyncio
from vools.bridge.r import r

@r(async_mode=True)
async def heavy_compute(n: int) -> int:
    """异步执行计算密集型任务"""
    return '''
    if (n <= 1) {
        return(1)
    } else {
        return(heavy_compute(n - 1) + heavy_compute(n - 2))
    }
    '''

async def main():
    result = await heavy_compute(25)
    print(f"Result: {result}")

asyncio.run(main())
```

### 模块装饰器

```python
from vools.bridge.r import r_module

@r_module(name='math_ops')
class MathOps:
    """数学运算模块"""
    
    def add(a: int, b: int) -> int:
        return "return(a + b)"
    
    def multiply(a: float, b: float) -> float:
        return "return(a * b)"

ops = MathOps()
print(ops.add(3, 5))       # 输出: 8
print(ops.multiply(3.0, 5.0))  # 输出: 15.0
```

## only_code 模式示例

使用 `mode='ONLY_CODE'` 只生成 R 源码，不执行：

```python
@r(mode='ONLY_CODE')
def generate_add(a: int, b: int) -> int:
    return "return(a + b)"

code = generate_add(1, 2)
print(code)
# 输出:
# options(encoding = "UTF-8")
# 
# suppressPackageStartupMessages(library(jsonlite))
# 
# input_json <- readLines("stdin", warn = FALSE, encoding = "UTF-8")
# input_data <- fromJSON(paste(input_json, collapse = "\n"), simplifyVector = FALSE)
# 
# .args <- lapply(input_data$args, function(.x) {
#   if (is.list(.x) && length(.x) > 0 && !is.list(.x[[1]])) {
#     return(unlist(.x, recursive = FALSE))
#   }
#   return(unlist(.x))
# })
# 
# generate_add <- function(a, b) {
#     return(a + b)
# }
# 
# result <- do.call(generate_add, .args)
# 
# cat(toJSON(result, auto_unbox = TRUE, pretty = FALSE))
```

### 其他运行模式

| 模式 | 说明 |
|-----|------|
| `DEBUG` | 强制重新生成脚本并执行 |
| `FORCE` | 只生成脚本不执行 |
| `NORMAL` | 命中缓存跳过生成；未命中则生成（默认） |
| `ONLY_RUN` | 只在有缓存时执行；没有则报错 |
| `ONLY_CODE` | 只生成 R 代码，不执行 |

## project 模式示例

### 项目结构

```
my_r_project/
├── math_utils.R
└── main.R
```

### math_utils.R

```r
add <- function(a, b) {
    return(a + b)
}

multiply <- function(a, b) {
    return(a * b)
}
```

### main.R

```r
source("math_utils.R")

main <- function() {
    cat(add(3, 5), "\n")
    cat(multiply(3, 5), "\n")
}

main()
```

### 使用 project 模式

```python
from vools.bridge.r import RBridge

bridge = RBridge()

# 编译项目
project_dir = "./my_r_project"

# entry='main' 模式：执行主文件
returncode, stdout, stderr = bridge.run_project(
    project_dir,
    entry='main'
)
print("退出码:", returncode)
print("输出:", stdout)

# entry!='main' 模式：打包所有文件后调用入口函数
result = bridge.run_project(
    project_dir,
    entry='add',
    args=(3, 5)
)
print("结果:", result)  # 输出: 8
```

### 使用 LangBridge 统一接口

```python
from vools.bridge.r import RBridge

bridge = RBridge()

# 编译项目
artifact_path = bridge.compile_project(
    project_dir="./my_r_project",
    entry='add',
    output_dir="./output"
)

# 调用函数
result = bridge.call_func(
    lib_path=artifact_path,
    func_name='add',
    args=(3, 5),
    ret_type=int
)
print(result)  # 输出: 8
```

## 注意事项

### 解释型语言的调用方式

1. **subprocess 调用**：R 是解释型语言，本桥接通过 `subprocess` 调用 `Rscript` 命令执行脚本
2. **JSON 序列化**：参数通过标准输入以 JSON 格式传递，结果通过标准输出以 JSON 格式返回
3. **jsonlite 优化**：优先使用 `jsonlite` 包进行高性能 JSON 序列化，不可用时回退到 base R
4. **性能考虑**：每次调用都会启动新的 R 进程，适合计算密集型任务，不适合高频小调用
5. **WSL 支持**：Windows 上通过 WSL 调用 R，自动进行路径转换

### 特殊语法

1. **函数定义**：R 使用 `name <- function(params) { ... }` 语法定义函数
2. **返回值**：使用 `return()` 函数显式返回值，或默认返回最后一个表达式的值
3. **向量运算**：R 是向量化语言，许多操作可以直接对向量进行
4. **赋值运算符**：R 中 `<-` 是标准赋值运算符，也可以使用 `=`
5. **字符串拼接**：使用 `paste()` 或 `paste0()` 函数，不是 `+`
6. **索引从 1 开始**：R 的向量/列表索引从 1 开始，不是 0
7. **缺失值**：R 有特殊的 `NA` 值表示缺失数据

### 参数传递

1. 参数通过标准输入以 JSON 格式传递，R 端从 stdin 读取
2. 函数参数通过 `do.call` 动态调用，支持可变参数
3. 列表参数会根据内容自动判断是简化为向量还是保持为 list
4. 复杂对象（如自定义类）需要序列化为 JSON 兼容的格式

### 缓存机制

1. 缓存目录：`$TMPDIR/vools_r_cache/`
2. 缓存键：基于 R 脚本 MD5 哈希的前 12 位
3. 缓存命中：相同脚本复用缓存文件，避免重复写入
4. 强制重编：使用 `mode='DEBUG'` 或 `mode='FORCE'`

### jsonlite 包

1. **自动检测**：启动时自动检测 jsonlite 是否可用
2. **性能优势**：jsonlite 比 base R 的 JSON 处理快得多
3. **安装建议**：强烈建议安装 jsonlite 包以获得最佳性能
4. **回退机制**：jsonlite 不可用时自动回退到 base R 方案

### 错误处理

1. R 脚本执行失败时会抛出 `RuntimeError`，包含 stderr 和 stdout 信息
2. 建议使用 `r_compiler_available()` 先检查 R 环境是否可用
3. 仅代码模式（ONLY_CODE）不会检查 R 可用性
4. 可以使用 `fallback` 参数提供 Python 回退实现

### WSL 相关注意事项

1. **路径转换**：Windows 路径自动转换为 WSL 路径（`C:\...` → `/mnt/c/...`）
2. **文件访问**：确保 WSL 可以访问项目文件（建议在 WSL 文件系统中）
3. **编码处理**：使用二进制模式读取输出，避免编码问题
4. **性能影响**：WSL 调用比原生 Linux 略慢，但功能完全一致

## API 速查

```python
from vools.bridge.r import (
    # 装饰器
    r,                          # @r 装饰器
    r_module,                   # @r_module 模块装饰器
    
    # 类
    RBridge,                    # R 语言桥接实现类
    _r_bridge,                  # 全局 RBridge 实例
    
    # 可用性检测
    r_compiler_available,       # 检查 R 环境是否可用
    is_r_available,             # 检查 R 是否可用
    get_r_version,              # 获取 R 版本
    is_jsonlite_available,      # 检查 jsonlite 包是否可用
    
    # 便捷入口
    compile_and_run,            # 直接生成并运行 R 代码
    compile_and_run_async,      # 异步生成并运行 R 代码
    
    # 类型映射
    PY_TO_R_TYPE,               # Python -> R 类型映射字典
    RTypeMapper,                # R 类型映射器类
    get_r_type,                 # 获取 R 类型字符串
    infer_r_types,              # 根据值推断 R 类型列表
    serialize_args,             # 序列化参数为 JSON
    deserialize_result,         # 反序列化 JSON 结果
    
    # 代码生成
    RCodeGenerator,             # R 代码生成器类
    generate_function_signature, # 生成函数签名
    generate_script_code,       # 生成完整脚本代码
    generate_from_python_func,   # 从 Python 函数生成 R 代码
    
    # 加载器
    is_r_available,             # 检查 R 是否可用
    get_r_version,              # 获取 R 版本
    is_jsonlite_available,      # 检查 jsonlite 是否可用
)
```
