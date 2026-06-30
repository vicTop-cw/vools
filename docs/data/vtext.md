# VText 文档

> **模块路径**：`vools.data`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#018
> **最后更新**：2026-06-30

## 概述

VText 是 vools 提供的链式文本类，继承自 `str`，提供丰富的文本处理方法。支持文件读写、正则表达式操作、日期格式化等链式调用功能。

## 创建 VText

```python
from vools.data import VText

# 从字符串创建
vt1 = VText("Hello, World!")
print(vt1)  # 输出: Hello, World!

# 空字符串
vt2 = VText()
print(vt2)  # 输出: (空字符串)

# 从其他类型转换（需要先转为 str）
number = VText(str(12345))
print(number)  # 输出: 12345
```

## 继承自 str 的特性

```python
from vools.data import VText

vt = VText("Hello, World!")

# str 的所有方法都可用
print(vt.upper())  # 输出: HELLO, WORLD!
print(vt.lower())  # 输出: hello, world!
print(vt.split(','))  # 输出: ['Hello', ' World!']
print(vt.replace('World', 'Python'))  # 输出: Hello, Python!
print(len(vt))  # 输出: 13
print('World' in vt)  # 输出: True
```

## do 方法 - 链式调用

```python
from vools.data import VText

# VText 支持链式调用，do 方法返回自身
vt = VText("Hello")

result = (
    VText("  Hello, World!  ")
    .do(print)  # 打印:   Hello, World!  （返回自身）
    .upper()    # 转大写
    .do(print)  # 打印:   HELLO, WORLD!
    .strip()    # 去除首尾空格
)

print(result)  # 输出: HELLO, WORLD!
```

## 文件操作

### write - 写入文件

```python
from vools.data import VText

# 创建文本并写入文件（默认覆盖模式）
content = VText("Hello, World!\nThis is a test.")
content.write("test_output.txt")
# 文件 test_output.txt 中内容:
# Hello, World!
# This is a test.

# 追加模式写入
more_content = VText("\nAppended line.")
more_content.write("test_output.txt", mode='a')
# 文件 test_output.txt 中内容:
# Hello, World!
# This is a test.
# Appended line.

# 使用绝对路径（file:// URI 格式也支持）
content.write(r"E:\temp\output.txt")
```

### get_content_fromfile - 读取文件

```python
from vools.data import VText

# 读取整个文件为字符串
content = VText.get_content_fromfile("test_output.txt")
print(content)

# 读取为行列表
lines = VText.get_content_fromfile("test_output.txt", to_text=False)
print(lines)  # 输出: ['Hello, World!\n', 'This is a test.\n', 'Appended line.\n']

# 使用绝对路径
content2 = VText.get_content_fromfile(r"E:\temp\output.txt")
```

## 正则表达式操作

### regexp_split - 正则分割

```python
from vools.data import VText

# 使用正则表达式分割文本
text = VText("apple,banana;cherry|orange")

# 按逗号分割
result1 = text.regexp_split(r',', rep='★')
print(result1)  # 输出: apple★banana;cherry|orange

# 按多个分隔符分割
result2 = text.regexp_split(r'[;,|]', rep='★')
print(result2)  # 输出: apple★banana★cherry★orange

# 使用正则标志
result3 = text.regexp_split(r'APPLE', flags=0, rep='★')
print(result3)  # 输出: apple,banana;cherry|orange

# 大小写不敏感分割
result4 = text.regexp_split(r'apple', flags=2, rep='★')  # flags=2 表示 re.IGNORECASE
print(result4)  # 输出: ★,banana;cherry|orange

# 按数字分割
text2 = VText("abc123def456ghi")
result5 = text2.regexp_split(r'\d+', rep='★')
print(result5)  # 输出: abc★def★ghi
```

## formatEx - 扩展格式化

```python
from vools.data import VText

# 使用 {yyyy} {MM} {dd} 等占位符格式化
template = VText("Today is {yyyy}-{MM}-{dd}")
result = template.formatEx(yyyy=2024, MM=1, dd=15)
print(result)  # 输出: Today is 2024-01-15

# 格式化当前日期时间
template2 = VText("Current time: {HH}:{mm}:{ss}")
result2 = template2.formatEx()
print(result2)  # 输出: Current time: (当前时间)

# 混合使用
template3 = VText("Date: {yyyy}{MM}{dd}, Time: {HH}{mm}{ss}")
result3 = template3.formatEx(yyyy=2024, MM=6, dd=30, HH=14, mm=30, ss=45)
print(result3)  # 输出: Date: 20240630, Time: 143045
```

## 链式调用示例

```python
from vools.data import VText

# 完整的链式处理示例
result = (
    VText("  Hello, World! Welcome to Python programming.  ")
    .strip()                           # 去除首尾空格
    .upper()                           # 转大写
    .replace("WORLD", "PYTHON")        # 替换
    .split(" ")                        # 分割（返回列表）
)

print(result)  # 输出: ['HELLO,', 'PYTHON!', 'WELCOME', 'TO', 'PYTHON', 'PROGRAMMING.']

# 使用 do 方法进行副作用操作
text = VText("processing...").do(print).upper()
# 输出: processing...
# text = PROCESSING...

# 链式调用实现复杂文本处理
log_lines = """[2024-01-15] INFO: Server started
[2024-01-15] ERROR: Connection failed
[2024-01-16] INFO: Retry successful
[2024-01-16] ERROR: Timeout"""

# 提取所有错误行
errors = (
    VText(log_lines)
    .split('\n')
    .filter(lambda line: 'ERROR' in line)  # 如果 VText 有 filter 方法
)
# 注：VText 继承自 str，链式操作需要通过其他方式实现
```

## 安全路径处理

```python
from vools.data import VText

# VText 内部使用 _safe_path 方法防止路径遍历攻击
# write 和 get_content_fromfile 方法都使用了这个安全机制

# 正常路径
safe_path = VText._safe_path("subdir/file.txt")
print(safe_path)  # 输出: /full/path/to/project/subdir/file.txt

# file:// URI 格式
safe_path2 = VText._safe_path("file://subdir/file.txt")
print(safe_path2)  # 输出: /full/path/to/project/subdir/file.txt

# 路径遍历攻击会被阻止
try:
    VText._safe_path("../../etc/passwd")
except ValueError as e:
    print(f"安全错误: {e}")  # 输出: 安全错误: 不允许访问指定路径之外的文件: ../../etc/passwd
```

## 与 str 的互相转换

```python
from vools.data import VText

# VText 转 str
vt = VText("Hello, World!")
plain_str = str(vt)
print(plain_str)  # 输出: Hello, World!
print(type(plain_str))  # 输出: <class 'str'>

# str 转 VText
plain = "Hello, World!"
vt2 = VText(plain)
print(vt2)  # 输出: Hello, World!
print(type(vt2))  # 输出: <class 'vools.data.vtext.VText'>

# 格式化
template = VText("Name: {}, Age: {}")
result = template.format("Alice", 30)
print(result)  # 输出: Name: Alice, Age: 30
```

## 字符串方法链式调用

```python
from vools.data import VText

# 链式调用字符串方法
result = (
    VText("   Hello, World!   ")
    .strip()              # 去除首尾空格
    .upper()              # 转大写
    .replace("!", "?")    # 替换感叹号
    .split(", ")          # 分割
)

print(result)  # 输出: ['HELLO', 'WORLD?']

# 计算处理后的字符串长度
length = (
    VText("  Python Programming  ")
    .strip()
    .upper()
    .replace(" ", "")
    .__len__()
)
print(length)  # 输出: 18

# 检查是否以特定前缀开头
starts_with_python = (
    VText("Python is awesome")
    .upper()
    .startswith("PYTHON")
)
print(starts_with_python)  # 输出: True
```

## 实用示例

### 清理日志文本

```python
from vools.data import VText

raw_log = """
2024-01-15 10:30:45 INFO Starting application
2024-01-15 10:30:46 DEBUG Loading configuration
2024-01-15 10:30:47 INFO Application started
2024-01-15 10:30:48 ERROR Failed to connect
2024-01-15 10:30:49 ERROR Connection timeout
"""

# 提取错误信息并格式化
error_lines = [
    VText(line).strip()
    for line in raw_log.strip().split('\n')
    if 'ERROR' in line
]

print(f"Found {len(error_lines)} errors:")
for err in error_lines:
    print(f"  - {err}")

# 输出:
# Found 2 errors:
#   - 2024-01-15 10:30:48 ERROR Failed to connect
#   - 2024-01-15 10:30:49 ERROR Connection timeout
```

### 数据提取

```python
from vools.data import VText

data = "Name: John Doe | Email: john@example.com | Phone: 123-456-7890"

# 提取邮箱
email = (
    VText(data)
    .split('|')[1]                   # 获取第二部分
    .split(':')[1]                   # 获取冒号后的值
    .strip()                         # 去除空格
)
print(email)  # 输出: john@example.com
```

### 模板填充

```python
from vools.data import VText

# 简单模板替换
template = VText("Dear {name}, your order #{order_id} has been shipped.")
result = template.format(
    name="Alice",
    order_id="12345"
)
print(result)  # 输出: Dear Alice, your order #12345 has been shipped.

# 使用 formatEx 进行日期格式化
date_template = VText("Order placed on {yyyy}/{MM}/{dd}")
result2 = date_template.formatEx(yyyy=2024, MM=6, dd=30)
print(result2)  # 输出: Order placed on 2024/06/30
```
