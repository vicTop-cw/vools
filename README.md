# vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。

## 项目结构

```
vools/
├── vools/
│   ├── core/             # 核心模块
│   │   ├── __init__.py
│   │   ├── base.py          # 基础类
│   │   ├── config.py         # 配置管理
│   │   └── exceptions.py     # 自定义异常
│   ├── data/            # 数据处理工具
│   │   ├── __init__.py
│   │   └── seq.py          # 序列操作工具
│   ├── datetime/        # 日期时间工具
│   │   ├── __init__.py
│   │   ├── dates_format.py
│   │   ├── range.py
│   │   └── utils.py
│   ├── decorators/      # 装饰器
│   │   ├── __init__.py
│   │   ├── cache.py
│   │   ├── control.py
│   │   ├── curry.py
│   │   ├── curry_core.py
│   │   ├── curry_delay.py
│   │   ├── extend.py
│   │   ├── lazy.py
│   │   ├── overload.py
│   │   ├── overcurry.py
│   │   ├── selector.py
│   │   ├── shotcut.py
│   │   └── trd.py
│   ├── functional/      # 函数式编程工具
│   │   ├── __init__.py
│   │   ├── arrow_func.py
│   │   ├── box.py
│   │   ├── funcs.py
│   │   ├── iif.py
│   │   └── placeholder.py
│   ├── oop/             # OOP 工具
│   │   ├── __init__.py
│   │   ├── calltype.py
│   │   ├── extend.py
│   │   └── selector.py
│   ├── security/         # 安全模块
│   │   ├── __init__.py
│   │   └── safe_eval.py     # 安全表达式求值
│   ├── utils/           # 通用工具
│   │   ├── __init__.py
│   │   ├── hoder.py
│   │   └── stuff.py
│   ├── vic/             # vic 工具类
│   │   ├── __init__.py
│   │   ├── vicdate.py
│   │   ├── viclist.py
│   │   ├── victext.py
│   │   └── victools.py
│   ├── __init__.py
│   ├── config.template.py
│   └── vools.py         # 核心功能（向后兼容）
├── changelog/           # 修改日志
├── tests/              # 测试文件
│   ├── __init__.py
│   ├── test_box.py
│   ├── test_curry_overload.py
│   ├── test_datetime.py
│   ├── test_decorators.py
│   ├── test_functional.py
│   ├── test_functional_simple.py
│   ├── test_g_function.py
│   ├── test_iif.py
│   ├── test_import.py
│   ├── test_oop.py
│   ├── test_overcurry_vic.py
│   ├── test_placeholder.py
│   ├── test_shotcut.py
│   ├── test_utils.py
│   ├── test_vicdate.py
│   └── test_vools.py
├── .gitignore
├── LICENSE
├── NOTICE
├── README.md
├── requirements.txt
├── setup.py
├── pyproject.toml
└── USER_GUIDE.md
```

## 安装指南

### 环境要求

- Python 3.6+
- 核心依赖：`wrapt`, `attrs`, `pandas`, `numpy`

### 安装方法

1. 克隆项目

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 安装包

```bash
pip install .
```

4. 配置设置（可选）

复制配置模板并填写相应的配置值：

```bash
cp vools/config.template.py vools/config.py
# 编辑 vools/config.py 文件，填写配置值
```

或者通过环境变量设置配置：

```bash
# 示例环境变量设置
# export DB_HOST=localhost
# export DB_PORT=5432
# export CACHE_DURATION=300
```

## 用法指南

### 快速开始

```python
from vools import _, _1, _2, overload, overcurry, stuff, persist, memoize

# 使用占位符
f = _ + 1
print(f(2))  # 输出: 3

# 使用重载
@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"一个参数: {x}"

print(process())     # 输出: 无参数
print(process(10))   # 输出: 一个参数: 10

# 使用 stuff（柯里化）
@stuff
def add(a, b, c):
    return a + b + c

result = add(1)(2)(3)()
print(result)  # 输出: 6

# 使用 persist（持久化缓存）
@persist(filepath='cache.pkl')
def expensive_computation(x):
    return x ** 2

result = expensive_computation(5)
print(result)  # 输出: 25
```

### 装饰器

```python
from vools import memorize, once, repeat, retry

# 缓存装饰器
@memorize(duration=60)  # 缓存 60 秒
def expensive_function(x):
    return x ** 2

# 只执行一次
@once
def initialize():
    print("初始化...")
    return 42

# 重复执行
@repeat(cnt=3, delay=0.1)
def hello(name):
    return f"Hello, {name}!"

# 重试装饰器
@retry(times=3, delay=1)
def risky_operation():
    # 可能失败的操作
    pass
```

### 函数式编程工具

```python
from vools import Pipe, Ops, Seq, P, g, iif

# 使用 Pipe
result = range(10) | Pipe(lambda x: [i * 2 for i in x]) | Pipe(list)

# 使用 Ops
result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()

# 使用 Seq
result = Seq(range(10)).map(lambda x: x * 2).filter(lambda x: x > 5).collect()

# 使用 g 函数（箭头函数）
f = g("x, y => x + y")
print(f(3, 4))  # 输出: 7

# 使用 iif 函数（条件表达式）
result = iif(True, "yes", "no")
print(result)  # 输出: yes
```

### vic 工具类

```python
from vools import vicTools, vicDate, vicText, vicList

# vicDate - 日期处理
date = vicDate("2024-01-15")
print(date.strftime('%Y/%m/%d'))  # 输出: 2024/01/15

# vicText - 文本处理
txt = vicText("Hello, World!")
print(txt.upper())  # 输出: HELLO, WORLD!

# vicList - 列表处理
lst = vicList([1, 2, 3, 4, 5])
result = lst.map(lambda x: x * 2).collect()  # 输出: [2, 4, 6, 8, 10]
```

### 配置管理

```python
from vools.core import ConfigManager

# 创建配置管理器
config = ConfigManager()

# 获取数据库配置
print(config.database.host)     # 输出: localhost
print(config.database.port)     # 输出: 5432

# 获取缓存配置
print(config.cache.duration)    # 输出: 3
print(config.cache.max_size)    # 输出: 1000

# 获取应用配置
print(config.app.environment)   # 输出: development
print(config.app.debug)        # 输出: False
```

## API 文档

### 装饰器模块

| 装饰器 | 说明 |
|--------|------|
| `memorize(duration=300)` | 缓存函数结果 |
| `once()` | 函数只执行一次 |
| `lazy()` | 延迟执行函数 |
| `repeat(cnt=1, delay=0)` | 重复执行函数 |
| `retry(times=3, delay=1)` | 失败时重试 |
| `rerun(interval=1, times=-1)` | 定时重复执行 |
| `trd()` | 线程执行 |
| `proc()` | 进程执行 |
| `extend()` | 函数扩展 |
| `curry()` | 柯里化 |
| `delay_curry()` | 延迟柯里化 |
| `overload()` | 函数重载 |
| `overcurry()` | 柯里化与重载结合 |
| `overloads()` | 同名方法重载 |

### 函数式编程模块

| 工具 | 说明 |
|------|------|
| `_`, `_1`, `_2`, `_3` | 占位符，用于创建匿名函数 |
| `Pipe(func)` | 管道操作 |
| `Ops` | 操作符集合 |
| `Seq(iterable)` | 序列操作 |
| `P(func)` | 可管道化函数包装器 |
| `g(expr)` | 箭头函数生成器 |
| `iif(cond, true, false)` | 条件表达式 |
| `Box(obj)` | 对象包装器 |

### 数据处理模块

| 工具 | 说明 |
|------|------|
| `box(func)` | 将函数返回值包装为 Box 对象 |
| `Box(obj)` | 包装对象并提供链式操作 |
| `setattr_box(func, name)` | 动态添加方法到 Box 类 |

### vic 工具类

| 类 | 说明 |
|------|------|
| `vicTools` | 通用工具类 |
| `vicDate` | 日期处理类 |
| `vicText` | 文本处理类 |
| `vicList` | 列表处理类 |

### 配置管理

| 方法 | 说明 |
|------|------|
| `ConfigManager()` | 创建配置管理器 |
| `config.database` | 数据库配置 |
| `config.cache` | 缓存配置 |
| `config.app` | 应用配置 |
| `config.load_from_file(path)` | 从文件加载配置 |

## 修改日志

详细的版本更新记录请查看 [changelog](changelog/) 目录。

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

### 代码规范

- 遵循 PEP 8 代码风格
- 使用 Black 进行代码格式化
- 使用 isort 进行导入排序
- 为所有公共函数添加文档字符串
- 为新功能添加测试

## 许可证

本项目采用 Apache 2.0 许可证 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- 作者: Victor
- 邮箱: victortop921129@gmail.com
- 项目链接: https://github.com/vicTop-cw/vools

## 更新日志

### v0.1.6
- 重构项目结构，拆分 vools.py 为独立模块
- 创建 core 模块（base.py, config.py, exceptions.py）
- 创建 vic 模块（victools.py, vicdate.py, victext.py, viclist.py）
- 创建 security 模块（safe_eval.py）
- 修复多个安全漏洞（代码注入、路径遍历、并发写入竞争）
- 修复性能问题（重复I/O、内存泄漏）
- 添加 Box 类的数字索引和切片支持
- 添加 attrs 依赖以支持 Python 3.6
- 更新所有配置文件

### v0.1.0
- 初始版本
- 实现基本装饰器功能
- 实现函数式编程工具