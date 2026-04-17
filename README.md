# vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。

## 项目结构

```
vools/
├── vools/
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
│   │   └── trd.py
│   ├── functional/      # 函数式编程工具
│   │   ├── __init__.py
│   │   ├── arrow_func.py
│   │   ├── box.py
│   │   └── placeholder.py
│   ├── oop/             # OOP 工具
│   │   ├── __init__.py
│   │   ├── calltype.py
│   │   ├── extend.py
│   │   └── selector.py
│   ├── utils/           # 通用工具
│   │   ├── __init__.py
│   │   └── stuff.py
│   ├── __init__.py
│   └── vools.py         # 核心功能
├── tests/              # 测试文件
│   ├── __init__.py
│   ├── test_curried.py
│   ├── test_curry_overload.py
│   ├── test_data.py
│   ├── test_datetime.py
│   ├── test_decorators.py
│   ├── test_functional.py
│   ├── test_functional_simple.py
│   ├── test_oop.py
│   ├── test_overcurry_vic.py
│   ├── test_placeholder.py
│   ├── test_shotcut.py
│   ├── test_utils.py
│   └── test_vools.py
├── .gitignore
├── LICENSE
├── NOTICE
├── README.md
├── requirements.txt
├── setup.py
└── USER_GUIDE.md
```

## 安装指南

### 环境要求

- Python 3.6+

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

3. 配置设置

复制配置模板并填写相应的配置值：

```bash
cp vools/config.template.py vools/config.py
# 编辑 vools/config.py 文件，填写配置值
```

或者通过环境变量设置配置：

```bash
# 示例环境变量设置
# export CACHE_DURATION=300
```

## 用法指南

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
from vools import Pipe, Ops, Seq, P

# 使用 Pipe
result = range(10) | Pipe(lambda x: [i * 2 for i in x]) | Pipe(list)

# 使用 Ops
result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()

# 使用 Seq
result = Seq(range(10)).map(lambda x: x * 2).filter(lambda x: x > 5).collect()

# 使用 P
result = [1, 2, 3] | P(sum)
```

### 数据处理工具

```python
from vools import Seq

# 创建序列并进行操作
result = Seq(range(10))\
    .map(lambda x: x * 2)\
    .filter(lambda x: x > 5)\
    .map(lambda x: x + 1)\
    .collect()

print(result)  # 输出: [7, 9, 11, 13, 15, 17, 19]

# 链式操作
result = Seq([1, 2, 3, 4, 5])\
    .map(lambda x: x ** 2)\
    .filter(lambda x: x > 10)\
    .collect()

print(result)  # 输出: [16, 25]
```

### 配置管理

```python
from vools import config

# 获取配置
cache_duration = config.get('OTHER_CONFIG.cache_duration', 5)  # 默认值 5

# 设置配置
config.set('OTHER_CONFIG.max_workers', 20)

# 验证配置
config.validate()
```

## API 文档

### 装饰器模块

- `memorize(duration=300)`: 缓存函数结果
- `once()`: 函数只执行一次
- `lazy()`: 延迟执行函数
- `repeat(cnt=1, delay=0)`: 重复执行函数
- `retry(times=3, delay=1)`: 失败时重试
- `rerun(interval=1, times=-1)`: 定时重复执行
- `trd()`: 线程执行
- `proc()`: 进程执行
- `extend()`: 函数扩展
- `curry()`: 柯里化
- `delay_curry()`: 延迟柯里化
- `overload()`: 函数重载

### 函数式编程模块

- `Pipe(func)`: 管道操作
- `Ops`: 操作符集合（filter, map, sum, all, any, min, max, take, drop, distinct, count, as_list, do）
- `Seq(iterable)`: 序列操作（map, filter, collect）
- `P(func)`: 可管道化函数包装器
- `NONE`: 空值标记

### 数据处理模块

- `box(obj)`: 将对象包装为 Box 对象，提供链式操作
- `Box(obj)`: Box 类，用于包装对象并提供链式操作

### 配置管理

- `config.get(key, default=None)`: 获取配置值
- `config.set(key, value)`: 设置配置值
- `config.get_all()`: 获取所有配置
- `config.validate()`: 验证配置

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

### v0.1.0
- 初始版本
- 实现装饰器模块
- 实现函数式编程工具
- 实现数据处理工具
- 实现配置管理
- 添加基本测试