# vools.bridge.ruby — Ruby 语言桥接

> 通过 subprocess 调用 Ruby 解释器执行代码，基于 JSON 序列化进行数据交换

## 语言简介

Ruby 是一种动态、开源的编程语言，以简洁和高效著称。它具有优雅的语法，支持面向对象、函数式和命令式编程范式。

本模块提供 Ruby 动态执行与跨语言桥接能力，采用装饰器模式，函数返回 Ruby 代码字符串，装饰器自动调用 Ruby 解释器执行并返回结果。

## Bridge 类名

**`RubyBridge`** — 继承自 `LangBridge` 抽象基类的 Ruby 桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@ruby` 装饰器，函数体返回 Ruby 代码字符串 |
| only_code 模式 | ✅ | 只生成 Ruby 源码，不执行 |
| project 模式 | ✅ | 支持项目级编译和执行 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ❌ | 暂不支持 |
| 回退机制 | ❌ | 暂不支持 |

## 运行环境要求

- **Ruby 版本**：>= 2.0
- **安装方式**：
  - Windows：从 [Ruby 官网](https://www.ruby-lang.org/) 下载安装，或使用 RubyInstaller
  - macOS：`brew install ruby`
  - Linux：`sudo apt-get install ruby` 或 `sudo yum install ruby`
- **PATH 配置**：确保 `ruby` 命令在系统 PATH 中
- **常用安装路径自动搜索**：
  - Windows: `C:\Ruby\bin`, `C:\Ruby31\bin`, `C:\Ruby32\bin`
  - Unix: `/usr/bin`, `/usr/local/bin`, `/opt/homebrew/bin`, `~/.rbenv/shims`, `~/.rvm/rubies/default/bin`

验证安装：
```bash
ruby --version
```

## 类型映射表

| Python 类型 | Ruby 类型 | 说明 |
|------------|----------|------|
| `int` | `Integer` | 整数类型 |
| `float` | `Float` | 浮点数类型 |
| `bool` | `Boolean` | 布尔类型 |
| `str` | `String` | 字符串类型 |
| `bytes` | `String` | 字节串转换为字符串 |
| `list` | `Array` | 列表类型 |
| `dict` | `Hash` | 字典类型 |
| `None` | `nil` | 空值 |

## 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.ruby import ruby, ruby_compiler_available

if not ruby_compiler_available():
    raise RuntimeError('请先安装 Ruby 并加入 PATH')

@ruby
def add(a: int, b: int) -> int:
    """简单的加法函数"""
    return "a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@ruby
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return '''
    def fib(n)
      n <= 1 ? 1 : fib(n - 1) + fib(n - 2)
    end
    fib(n)
    '''

result = fib(10)
print(result)  # 输出: 89
```

### 字符串处理

```python
@ruby
def greet(name: str) -> str:
    """字符串拼接"""
    return '"Hello, " + name + "!"'

result = greet("World")
print(result)  # 输出: Hello, World!
```

### 数组操作

```python
@ruby
def sum_array(arr: list) -> int:
    """数组求和"""
    return '''
    arr.sum
    '''

result = sum_array([1, 2, 3, 4, 5])
print(result)  # 输出: 15
```

### 哈希操作

```python
@ruby
def get_value(hash: dict, key: str) -> str:
    """从哈希中获取值"""
    return '''
    hash[key]
    '''

result = get_value({"name": "Ruby", "version": "3.0"}, "name")
print(result)  # 输出: Ruby
```

## only_code 模式示例

使用 `mode='ONLY_CODE'` 只生成 Ruby 源码，不执行：

```python
@ruby(mode='ONLY_CODE')
def generate_add(a: int, b: int) -> int:
    return "a + b"

code = generate_add(1, 2)
print(code)
# 输出:
# # encoding: utf-8
# require 'json'
# 
# # 解析参数
# args_json = '[1, 2]'
# args = JSON.parse(args_json)
# 
# def generate_add(a, b)
#   a + b
# end
# 
# # 调用函数并输出结果
# result = generate_add(*args)
# ...
```

### 其他运行模式

| 模式 | 说明 |
|-----|------|
| `DEBUG` | 强制重新生成源码并执行 |
| `FORCE` | 只强制重新生成源码，不执行 |
| `NORMAL` | 命中缓存跳过生成；未命中则生成（默认） |
| `ONLY_RUN` | 只在有缓存时执行；没有则报错 |
| `ONLY_CODE` | 只生成 Ruby 源码，不执行 |

## project 模式示例

### 项目结构

```
my_ruby_project/
├── math_utils.rb
└── main.rb
```

### math_utils.rb

```ruby
def add(a, b)
  a + b
end

def multiply(a, b)
  a * b
end
```

### main.rb

```ruby
require_relative 'math_utils'

puts add(3, 5)
puts multiply(3, 5)
```

### 使用 project 模式

```python
from vools.bridge.ruby import _ruby_bridge

# 编译项目并执行
project_dir = "./my_ruby_project"

# entry='main' 模式：执行主文件
returncode, stdout, stderr = _ruby_bridge.run_project(
    project_dir,
    entry='main'
)
print("退出码:", returncode)
print("输出:", stdout)

# entry!='main' 模式：打包所有文件后调用入口函数
result = _ruby_bridge.run_project(
    project_dir,
    entry='add',
    args=(3, 5)
)
print("结果:", result)  # 输出: 8
```

### 使用 LangBridge 统一接口的 project 模式

```python
from vools.bridge.ruby import RubyBridge

bridge = RubyBridge()

# 编译项目
artifact_path = bridge.compile_project(
    project_dir="./my_ruby_project",
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

1. **subprocess 调用**：Ruby 是解释型语言，本桥接通过 `subprocess` 调用 `ruby` 命令执行脚本
2. **JSON 序列化**：参数通过 JSON 序列化传递给 Ruby，结果也通过 JSON 反序列化返回
3. **性能考虑**：每次调用都会启动新的 Ruby 进程，适合计算密集型任务，不适合高频小调用
4. **超时设置**：默认执行超时为 60 秒

### 特殊语法

1. **函数定义**：Ruby 使用 `def` 关键字定义函数，函数名后直接跟参数列表
2. **返回值**：Ruby 函数默认返回最后一个表达式的值，无需显式 `return`
3. **条件表达式**：三元运算符为 `condition ? true_val : false_val`
4. **字符串插值**：使用 `#{expression}` 进行字符串插值
5. **数组和哈希**：Ruby 的 Array 和 Hash 与 Python 的 list 和 dict 类似但语法不同

### 参数传递

1. 参数通过 JSON 格式传递，Ruby 端使用 `JSON.parse` 解析
2. 函数参数按位置传递，通过 `*args` 展开
3. 复杂对象（如自定义类）需要序列化为 JSON 兼容的格式

### 缓存机制

1. 缓存目录：`$TMPDIR/vools_ruby_cache/`
2. 缓存键：基于 Ruby 源码 MD5 哈希的前 12 位
3. 缓存命中：相同源码复用缓存文件，避免重复写入
4. 强制重编：使用 `mode='DEBUG'` 或 `mode='FORCE'`

### 错误处理

1. Ruby 执行失败时会抛出 `RuntimeError`，包含 stderr 和 stdout 信息
2. 建议使用 `ruby_compiler_available()` 先检查 Ruby 环境是否可用
3. 仅代码模式（ONLY_CODE）不会检查 Ruby 可用性

## API 速查

```python
from vools.bridge.ruby import (
    # 装饰器
    ruby,                       # @ruby 装饰器
    
    # 类
    RubyBridge,                 # Ruby 桥接实现类
    _ruby_bridge,               # 全局 RubyBridge 实例
    
    # 可用性检测
    ruby_compiler_available,    # 检查 Ruby 解释器是否可用
    is_ruby_available,          # 检查 Ruby 桥接是否可用
    
    # 便捷入口
    compile_and_run,            # 直接执行 Ruby 源码
    
    # 类型映射
    PY_TO_RUBY_TYPE,            # Python -> Ruby 类型映射字典
    get_ruby_type,              # 获取 Ruby 类型字符串
    infer_ruby_argtypes,        # 根据值推断 Ruby 类型列表
    
    # 内部工具
    _generate_ruby_source,      # 生成 Ruby 源码
    _execute_ruby_code,         # 执行 Ruby 代码
    _parse_ruby_output,         # 解析 Ruby 输出
    _RUBY_CACHE_DIR,            # 缓存目录路径
)
```
