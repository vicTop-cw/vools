# vools 用户指南

本指南将帮助您快速上手 vools 库，了解其核心功能和使用方法。

## 项目信息

- **当前版本**：v0.1.3
- **GitHub 仓库**：[https://github.com/vicTop-cw/vools](https://github.com/vicTop-cw/vools)
- **联系邮箱**：victortop921129@gmail.com
- **PyPI 主页**：[https://pypi.org/project/vools/](https://pypi.org/project/vools/)

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [核心功能](#核心功能)
  - [装饰器](#装饰器)
  - [函数式编程工具](#函数式编程工具)
  - [数据处理工具](#数据处理工具)
  - [配置管理](#配置管理)
- [高级用法](#高级用法)
- [常见问题](#常见问题)

## 安装

### 环境要求

- Python 3.6 或更高版本

### 安装步骤

1. **安装 vools**

   ```bash
   # 从 PyPI 安装
   pip install vools

   # 或从源码安装
   git clone https://github.com/vicTop-cw/vools.git
   cd vools
   pip install -e .
   ```

2. **安装依赖**

   ```bash
   pip install -r requirements.txt
   ```

3. **配置设置**

   vools 使用配置文件和环境变量来管理设置。您可以：

   - **使用配置文件**：复制配置模板并填写相应的值
     ```bash
     cp vools/config.template.py vools/config.py
     # 编辑 vools/config.py 文件
     ```

   - **使用环境变量**：设置环境变量来覆盖默认配置
     ```bash
     # 示例环境变量设置
     # export CACHE_DURATION=300
     ```

## 快速开始

以下是一个简单的示例，展示了 vools 的核心功能：

```python
from vools import memorize, Pipe, Ops, config

# 使用缓存装饰器
@memorize(duration=60)  # 缓存 60 秒
def calculate(x):
    print(f"计算 {x}...")
    return x * 2

# 第一次计算
result1 = calculate(5)  # 输出: 计算 5...
print(f"结果: {result1}")  # 输出: 结果: 10

# 第二次计算（使用缓存）
result2 = calculate(5)  # 无输出，使用缓存
print(f"结果: {result2}")  # 输出: 结果: 10

# 使用函数式编程工具
numbers = range(10)
result = numbers | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
print(f"偶数的两倍之和: {result}")  # 输出: 偶数的两倍之和: 40

# 使用配置管理
cache_duration = config.get('OTHER_CONFIG.cache_duration')
print(f"默认缓存时间: {cache_duration} 秒")
```

## 核心功能

### 装饰器

vools 提供了多种实用的装饰器，简化常见的编程模式：

#### 1. 缓存装饰器

```python
from vools import memorize, once

# 缓存函数结果，指定缓存时间
@memorize(duration=300)  # 缓存 5 分钟
def get_data(user_id):
    # 模拟耗时操作
    return f"用户 {user_id} 的数据"

# 函数只执行一次，后续调用返回缓存结果
@once
def initialize_app():
    print("应用初始化...")
    return "初始化完成"
```

#### 2. 控制流装饰器

```python
from vools import repeat, retry, rerun

# 重复执行函数指定次数
@repeat(cnt=3, delay=0.5)  # 执行 3 次，每次间隔 0.5 秒
def send_notification(message):
    print(f"发送通知: {message}")
    return f"已发送: {message}"

# 失败时自动重试
@retry(times=3, delay=1)  # 最多重试 3 次，每次间隔 1 秒
def fetch_data(url):
    # 可能失败的网络请求
    if random.random() < 0.5:
        raise Exception("网络错误")
    return "数据获取成功"

# 定时重复执行
@rerun(interval=5, times=10)  # 每 5 秒执行一次，共执行 10 次
def check_status():
    print(f"检查状态: {datetime.now()}")
```

#### 3. 并发装饰器

```python
from vools import trd, proc

# 在新线程中执行
@trd
def heavy_computation():
    # 耗时计算
    return "计算完成"

# 在新进程中执行
@proc
def cpu_intensive_task():
    # CPU 密集型任务
    return "任务完成"
```

#### 4. 函数式装饰器

```python
from vools import curry, delay_curry, overload

# 柯里化装饰器
@curry
def add(a, b, c):
    return a + b + c

# 使用方式
add_5 = add(5)        # 返回一个接受 b 和 c 的函数
add_5_10 = add_5(10)  # 返回一个接受 c 的函数
result = add_5_10(15) # 返回 30

# 函数重载
@overload
def process(x: int):
    return f"处理整数: {x}"

@overload
def process(x: str):
    return f"处理字符串: {x}"

# 使用方式
print(process(42))    # 输出: 处理整数: 42
print(process("hello"))  # 输出: 处理字符串: hello
```

### 函数式编程工具

vools 提供了丰富的函数式编程工具，使代码更加简洁和表达力强：

#### 1. Pipe 管道操作

```python
from vools import Pipe

# 创建管道
result = range(10) | Pipe(lambda x: [i * 2 for i in x]) | Pipe(filter, lambda x: x > 10) | Pipe(list)
print(result)  # 输出: [12, 14, 16, 18]

# 带参数的管道
result = "hello" | Pipe(str.upper) | Pipe(str.split, "")
print(result)  # 输出: ['H', 'E', 'L', 'L', 'O']
```

#### 2. Ops 操作符集合

```python
from vools import Ops

# 链式操作
numbers = range(1, 11)

# 过滤偶数，乘以 2，然后求和
result = numbers | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
print(f"偶数的两倍之和: {result}")  # 输出: 偶数的两倍之和: 60

# 其他操作
result = numbers | Ops.max()
print(f"最大值: {result}")  # 输出: 最大值: 10

result = numbers | Ops.distinct() | Ops.as_list()
print(f"去重后: {result}")  # 输出: 去重后: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

#### 3. Seq 序列操作

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

#### 4. P 可管道化函数

```python
from vools import P

# 使用 P 包装函数
result = [1, 2, 3, 4, 5] | P(sum)
print(f"总和: {result}")  # 输出: 总和: 15

# 指定参数位置
result = "hello" | P(str.replace, "h", "H", ix=1)
print(result)  # 输出: Hello

# 带多个参数
result = [1, 2, 3] | P(max, 10, ix=1)  # 比较列表和 10
print(result)  # 输出: 10
```

### 数据处理工具

vools 提供了数据处理工具，方便处理表格数据：

#### 1. 序列操作

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

vools 提供了灵活的配置管理系统，支持从文件和环境变量加载配置：

```python
from vools import config

# 获取配置
cache_duration = config.get('OTHER_CONFIG.cache_duration', 300)  # 默认值 300 秒

# 设置配置
config.set('OTHER_CONFIG.max_workers', 20)

# 获取所有配置
all_config = config.get_all()
print(all_config)

# 验证配置
config.validate()  # 检查必需的配置项
```

### 自定义数据类型

vools 提供了四个核心自定义数据类型，增强了 Python 原生类型的功能：

#### 1. vicTools - 工具类

vicTools 提供了各种实用的工具方法，包括日期处理、字符串处理、正则表达式操作等：

```python
from vools import vicTools

# 日期处理
date_seq = vicTools.get_date_seq(nums=7, date_type='day', fmt='yyyyMMdd')
print(f"最近7天日期: {date_seq}")

# 字符串处理
trimmed = vicTools.trim("  hello world  ")
print(f"修剪后: '{trimmed}'")

# 正则表达式操作
matches = vicTools.regexp_findall(r'\d+', 'abc123def456')
print(f"匹配的数字: {matches}")

# 生成随机字段名
field_name = vicTools.generate_random_field_name()
print(f"随机字段名: {field_name}")
```

#### 2. vicDate - 日期类

vicDate 继承自 datetime，提供了更多日期处理方法：

```python
from vools import vicDate

# 创建日期对象
now = vicDate()
print(f"当前日期: {now}")

# 解析日期字符串
date = vicDate('20230101', fmt='yyyyMMdd')
print(f"解析的日期: {date}")

# 获取指定周的日期
week_date = date.get_week(num=1, weekday=1)  # 上周周一
print(f"上周周一: {week_date}")

# 获取指定月的日期
month_date = date.get_month(num=1, last_day=True)  # 上月末
print(f"上月末: {month_date}")

# 日期运算
tomorrow = now + 1
print(f"明天: {tomorrow}")
yesterday = now - 1
print(f"昨天: {yesterday}")
```

#### 3. vicText - 文本类

vicText 继承自 str，提供了更多文本处理方法：

```python
from vools import vicText

# 创建文本对象
txt = vicText("Hello, World!")
print(f"原始文本: {txt}")

# 文本操作
upper_txt = txt.upper()
print(f"大写: {upper_txt}")

# 正则表达式操作
replaced = txt.regexp_replace(r'World', 'vools')
print(f"替换后: {replaced}")

# 分割文本
parts = txt.splitEx(',')
print(f"分割后: {parts}")

# 写入文件
txt.write('output.txt')

# 从文件读取
read_txt = vicText.get_content_fromfile('output.txt')
print(f"从文件读取: {read_txt}")
```

#### 4. vicList - 列表类

vicList 继承自 Seq，提供了更多列表处理方法：

```python
from vools import vicList

# 创建列表对象
lst = vicList(1, 2, 3, 4, 5)
print(f"原始列表: {lst}")

# 列表操作
slice_lst = lst.islice(1, 4)
print(f"切片后: {slice_lst}")

# 集合操作
other_lst = vicList(3, 4, 5, 6, 7)
intersection = lst & other_lst  # 交集
print(f"交集: {intersection}")
union = lst | other_lst  # 并集
print(f"并集: {union}")

# 唯一元素
unique_lst = vicList(1, 2, 2, 3, 3, 3).unique
print(f"唯一元素: {unique_lst}")
```

## 高级用法

### 组合使用装饰器

```python
import requests
from vools import memorize, trd, retry

# 组合装饰器
@memorize(duration=600)  # 缓存 10 分钟
@trd  # 在新线程中执行
@retry(times=3)  # 失败时重试

def fetch_external_data(url):
    # 从外部 API 获取数据
    response = requests.get(url)
    response.raise_for_status()
    return response.json()
```

### 自定义配置源

```python
from vools import ConfigManager

# 创建自定义配置管理器
class CustomConfigManager(ConfigManager):
    def _load_config(self):
        # 从自定义源加载配置
        super()._load_config()
        # 添加额外的配置加载逻辑

# 使用自定义配置管理器
custom_config = CustomConfigManager()
```

### 扩展 Ops

```python
from vools.functional import Ops

# 添加自定义操作
@staticmethod
@Pipe
def custom_operation(it):
    """自定义操作"""
    return [x * 3 for x in it]

# 添加到 Ops
Ops.custom = custom_operation

# 使用自定义操作
result = range(5) | Ops.custom() | Ops.sum()
print(result)  # 输出: 30
```

## 常见问题

### 1. 安装问题

**Q: 安装时出现依赖错误？**
A: 确保使用 Python 3.6+ 版本，并按照 requirements.txt 安装所有依赖。

### 2. 配置问题

**Q: 配置文件不生效？**
A: 确保配置文件路径正确，并且环境变量优先级高于配置文件。

**Q: 敏感信息如何处理？**
A: 使用环境变量存储敏感信息，避免在配置文件中硬编码密码等敏感数据。

### 3. 性能问题

**Q: 缓存装饰器导致内存占用过高？**
A: 合理设置缓存时间和缓存大小，避免缓存过大的对象。

**Q: 并发装饰器导致资源消耗过高？**
A: 控制并发数量，避免同时启动过多线程或进程。

### 4. 其他问题

**Q: 函数重载不生效？**
A: 确保使用了正确的类型注解，并且函数签名不同。

**Q: 管道操作出错？**
A: 确保管道中的函数接受正确的参数类型，并且返回值可以被下一个函数处理。

## 故障排除

1. **检查日志**：查看控制台输出的错误信息
2. **验证配置**：运行 `config.validate()` 检查配置是否正确
3. **测试基本功能**：运行 `python -m vools` 测试基本功能
4. **查看文档**：参考本指南和 API 文档
5. **提交问题**：如果问题持续存在，请在 GitHub 上提交 issue

## 示例项目

查看 `examples` 目录中的示例代码，了解如何在实际项目中使用 vools。

---

希望本指南能帮助您快速上手 vools 库。如有任何问题，请参考文档或提交 issue。
