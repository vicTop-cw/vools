# vools.bridge.shell - Shell/Bash 语言桥接模块

Shell/Bash 是一种广泛使用的命令行解释器和脚本语言，常用于系统管理、自动化任务和管道操作。vools 桥接模块允许 Python 代码直接调用 Shell/Bash 脚本。

---

## 1. 语言简介

Bash（Bourne Again Shell）是 GNU 项目的一部分，是大多数 Linux 发行版和 macOS 的默认 Shell。Shell 脚本擅长系统管理、文件操作、管道处理和自动化任务。

**主要特点：**
- 解释型脚本语言，无需编译即可运行
- 强大的管道和重定向能力
- 丰富的系统命令和工具生态
- 跨平台支持（Linux、macOS、Windows via WSL/Git Bash）
- 适合快速编写自动化脚本

---

## 2. Bridge 类名

**类名：** `ShellBridge`

**模块路径：** `vools.bridge.shell`

**导入方式：**

```python
from vools.bridge.shell import ShellBridge, shell_bridge, shell

# 或使用别名
from vools.bridge.shell import sh, bash
```

**全局实例：** `shell_bridge` / `_shell_bridge`

**装饰器别名：** `shell` / `sh` / `bash`

---

## 3. 支持的功能

### 3.1 单函数装饰器模式

使用 `@shell` 装饰器装饰 Python 函数，函数体为 Shell 代码，首次调用自动解释执行。

### 3.2 依赖函数支持

通过 `deps` 参数声明依赖的辅助函数，自动解析依赖拓扑顺序。

```python
@shell(deps=[helper])
def main_func(x: int) -> int:
    return "echo $(( $(helper $x) + 1 ))"
```

### 3.3 模块级代码

通过 `module_code` 参数注入 Shell 模块级代码（如变量初始化、函数定义等）。

### 3.4 异步模式

通过 `async_mode=True` 启用异步执行，返回 `ShellFuture` 对象。

### 3.5 回退机制

通过 `fallback` 参数指定解释器不可用时的回退函数。

### 3.6 仅代码模式

通过 `only_code=True` 仅生成 Shell 代码，不执行。

### 3.7 项目模式

通过 `project_dir` 参数编译整个 Shell 项目目录。

### 3.8 多平台支持

- **Linux/macOS：** 直接使用系统 bash
- **Windows：** 自动检测 WSL 或 Git Bash

---

## 4. 运行环境要求

### 4.1 Shell 解释器

**必需：** Bash 或 sh 解释器

**Linux/macOS 搜索路径：**
- `/bin`
- `/usr/bin`
- `/usr/local/bin`
- `/opt/homebrew/bin`

**Windows 搜索路径：**
- `C:\Windows\System32` (WSL)
- `C:\Program Files\Git\bin`
- `C:\Program Files\Git\usr\bin`
- `~/AppData/Local/Programs/Git/bin`

### 4.2 Windows 环境

Windows 上的执行优先级：
1. 原生 bash（Git Bash 等）
2. WSL (Windows Subsystem for Linux)

### 4.3 缓存目录

默认缓存目录：`系统临时目录/vools_shell_cache`

可通过 `cache_dir` 参数自定义缓存位置。

---

## 5. 类型映射

### 5.1 Python → Shell 类型

| Python 类型 | Shell 类型 | 说明 |
|------------|-----------|------|
| `int` | `int` | 整数 |
| `float` | `float` | 浮点数 |
| `bool` | `bool` | 布尔值 |
| `str` | `string` | 字符串 |
| `list` | `array` | 数组 |
| `dict` | `assoc_array` | 关联数组 |
| `None` | `void` | 无返回值 |

### 5.2 Shell → ctypes 类型

| Shell 类型 | ctypes 类型 | 说明 |
|-----------|-------------|------|
| `int` | `c_int` | C 整数 |
| `float` | `c_double` | C 双精度浮点 |
| `string` | `c_char_p` | C 字符指针 |
| `bool` | `c_bool` | C 布尔值 |
| `void` | `None` | 无对应类型 |

### 5.3 类型推断

`infer_shell_argtypes()` 函数根据运行时参数值自动推断 Shell 类型。

---

## 6. 快速使用示例

### 6.1 基础用法

```python
from vools.bridge.shell import shell

@shell
def add(x: int, y: int) -> int:
    return "echo $(( $1 + $2 ))"

result = add(10, 20)
print(result)  # 30
```

### 6.2 使用别名

```python
from vools.bridge.shell import sh

@sh
def factorial(n: int) -> int:
    return """
    result=1
    for ((i=1; i<=$1; i++)); do
        result=$(( result * i ))
    done
    echo $result
    """

result = factorial(5)
print(result)  # 120
```

### 6.3 带依赖函数

```python
def helper(x: int) -> int:
    return "echo $(( $1 * 2 ))"

@shell(deps=[helper])
def compute(x: int) -> int:
    return "helper $1 | awk '{print $1 + 1}'"

result = compute(5)
print(result)  # 11
```

### 6.4 带模块级代码

```python
@shell(module_code="export PATH=/usr/local/bin:$PATH")
def which_cmd(cmd: str) -> str:
    return "which $1"

result = which_cmd("python")
print(result)
```

### 6.5 异步模式

```python
from vools.bridge.shell import shell, ShellFuture

@shell(async_mode=True)
def slow_operation(n: int) -> int:
    return "sleep 1; echo $(( $1 * $1 ))"

future = slow_operation(100)
result = future.result()
print(result)  # 10000
```

### 6.6 带回退函数

```python
@shell(fallback=lambda x, y: x + y)
def add(x: int, y: int) -> int:
    return "echo $(( $1 + $2 ))"

result = add(10, 20)
print(result)  # 30
```

---

## 7. only_code 模式示例

`only_code` 模式仅生成 Shell 代码，不执行，适用于代码生成和调试场景。

### 7.1 生成代码到标准输出

```python
from vools.bridge.shell import shell

@shell(only_code=True)
def hello(name: str) -> str:
    return 'echo "Hello, $1!"'

# 返回生成的 Shell 代码字符串
code = hello("World")
print(code)
```

### 7.2 生成代码到文件

```python
from vools.bridge.shell import shell

@shell(only_code=True, output_file="output/hello.sh")
def hello(name: str) -> str:
    return 'echo "Hello, $1!"'
```

### 7.3 追加模式

```python
@shell(only_code=True, output_file="utils.sh", write_mode="append")
def util1(x: int) -> int:
    return "echo $(( $1 * 2 ))"

@shell(only_code=True, output_file="utils.sh", write_mode="append")
def util2(x: int) -> int:
    return "echo $(( $1 * $1 ))"
```

### 7.4 自定义前后缀

```python
@shell(only_code=True, output_file="script.sh",
      prefix="#!/usr/bin/env bash\nset -euo pipefail\n",
      suffix='\necho "Done!"')
def main():
    return 'echo "Hello World!"'
```

---

## 8. project 模式示例

`project` 模式用于处理整个 Shell 项目目录，支持批量处理多个 .sh 文件。

### 8.1 项目结构示例

```
my_shell_project/
├── main.sh          # 入口文件
├── utils.sh         # 工具函数
└── math.sh          # 数学函数
```

### 8.2 入口文件 (main.sh)

```bash
#!/usr/bin/env bash
set -euo pipefail

process_data() {
    local data="$1"
    echo $(( data * 2 ))
}
```

### 8.3 使用项目模式

```python
from vools.bridge.shell import shell

@shell(project_dir="./my_shell_project", entry="process_data")
def process(x: int) -> int:
    pass

result = process(42)
print(result)  # 84
```

### 8.4 执行 main.sh

```python
from vools.bridge.shell import shell_bridge

# 返回 (returncode, stdout, stderr)
result = shell_bridge.run_project("./my_shell_project", entry="main", args=())
print(result)
```

### 8.5 项目模式打包

当 `entry != 'main'` 时，项目模式会：
1. 扫描项目目录下所有 `.sh` 文件
2. 按文件名排序拼接所有文件内容
3. 在末尾添加入口函数调用
4. 输出打包后的 `.sh` 文件路径

```python
artifact_path = shell_bridge.compile_project(
    "./my_shell_project",
    entry="compute",
    output_dir="./output"
)
print(f"打包文件: {artifact_path}")
```

---

## 9. 注意事项

### 9.1 Shell 代码限制

- **参数访问：** 使用 `$1`, `$2`, ... 访问位置参数，`$@` 访问所有参数
- **返回值：** Shell 函数通过 stdout 输出返回值，使用 `echo` 或 `printf`
- **退出码：** 使用 `return` 设置函数退出码（0-255），不能用于返回数据
- **引号：** 字符串处理注意单引号和双引号的区别

### 9.2 性能考虑

- Shell 是解释型语言，每次调用都会启动新的 bash 进程
- 对于高频调用场景，建议使用项目模式或 Python 原生实现
- 大量数据传递建议使用文件或管道

### 9.3 路径问题

- Windows 上 WSL 会自动转换路径格式
- 建议使用 `os.path` 处理跨平台路径
- 注意 Windows 路径和 WSL 路径的区别

### 9.4 编码问题

- 源代码默认以 UTF-8 编码读写
- Shell 脚本默认添加 `#!/usr/bin/env bash` shebang
- 处理中文等非 ASCII 字符时注意终端编码设置

### 9.5 错误处理

- Shell 脚本执行失败时抛出 `RuntimeError`
- 错误信息包含 stderr、stdout 和退出码
- 建议使用 `try-except` 捕获执行异常
- 可在脚本中使用 `set -euo pipefail` 增强错误检测

### 9.6 缓存管理

- 缓存键基于代码内容的 MD5 哈希
- 缓存目录位于系统临时目录
- 长时间运行建议定期清理缓存

### 9.7 安全注意

- 避免在 Shell 脚本中直接拼接用户输入
- 使用参数传递代替字符串拼接防止注入攻击
- 执行外部命令时注意路径和权限

---

## 附录：API 参考

### 函数

| 函数 | 说明 |
|------|------|
| `shell_compiler_available()` | 检查 Shell 解释器是否可用 |
| `bash_compiler_available()` | 检查 Bash 解释器是否可用（别名） |
| `compile_and_run(code, func_name, args, ret_type, cache_dir)` | 编译并运行代码 |
| `get_shell_type(py_type)` | 获取 Shell 类型字符串 |
| `get_shell_ctype(shell_type)` | 获取 ctypes 类型 |

### 类

| 类 | 说明 |
|---|------|
| `ShellBridge` | Shell 桥接实现类 |
| `ShellFuture` | 异步执行结果封装 |
