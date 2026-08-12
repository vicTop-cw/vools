# vools.dll32 - 32 位 DLL 专用桥接包

通过嵌入式 Python 3.6 32 位进程，在 64 位 Python 环境中无缝调用 32 位 DLL、COM 组件和 .NET 程序集。

## 功能特点

- **跨位数调用**: 64 位 Python 调用 32 位 DLL/COM/.NET
- **统一装饰器接口**: 与 `vools.sys.dll` 风格一致的 `@dll32` 装饰器
- **内置 DLL 集合**: 预置常用 32 位 DLL，开箱即用
- **COM 组件支持**: 支持 RC6 (VBRichClient5) 等 COM 组件免注册调用
- **.NET 互操作**: 通过 pythonnet 调用 .NET 程序集
- **函数签名注册表**: 集中管理 DLL 函数签名，支持动态适配
- **跨进程通信**: 通过临时文件 + 子进程方式实现稳定通信

## 架构设计

```
vools/dll32/
├── __init__.py              # 主入口，导出核心 API
├── dll.py                   # @dll32 装饰器
├── vb6plus.py               # VB6Plus.dll 包装类
├── openssl.py               # VB6OpenSSL.dll 包装类
├── mqtt.py                  # VB6MQTT.dll 包装类
├── _core/                   # 核心通信层
│   ├── _spawn32.py          # 32 位 Python 进程管理
│   └── _pipe_comm.py        # 跨进程通信封装
├── _dlls/                   # 预置 32 位 DLL 文件
│   ├── VB6Plus.dll
│   ├── VB6OpenSSL.dll
│   ├── VB6MQTT.dll
│   ├── DirectCOM.dll
│   ├── RC6.dll
│   ├── RC6Widgets.dll
│   ├── vbRichClient5.dll
│   ├── cairo_sqlite.dll
│   └── WebView2Loader.dll
├── _lib/                    # 高层包装库
│   ├── com/                 # COM 组件支持
│   │   ├── _base.py         # COMObject 基类
│   │   ├── directcom.py     # DirectCOM 免注册加载
│   │   ├── rc6.py           # RC6 基础包装
│   │   └── rc6plus.py       # RC6Plus 增强包装
│   └── clr/                 # .NET 互操作支持
│       └── _base.py         # CLRAssembly / DotNetObject
├── _signatures/             # 函数签名注册表
│   ├── _registry.py         # 统一注册中心
│   ├── vb6plus.py           # VB6Plus.dll 签名
│   ├── openssl.py           # VB6OpenSSL.dll 签名
│   └── mqtt.py              # VB6MQTT.dll 签名
└── _python32/               # 嵌入式 Python 3.6 32 位
```

### 架构层次

| 层次 | 模块 | 职责 |
|------|------|------|
| 用户接口层 | `__init__.py`, `dll.py` | 提供装饰器和便捷 API |
| 包装层 | `vb6plus.py`, `openssl.py`, `mqtt.py`, `_lib/` | 高层封装，简化调用 |
| 签名层 | `_signatures/` | 函数元数据管理 |
| 通信层 | `_core/` | 32 位进程管理与通信 |
| 资源层 | `_dlls/`, `_python32/` | DLL 文件和 Python 运行时 |

## 支持的组件

### 标准 DLL

| DLL 文件 | 功能类别 | 函数数量 |
|----------|----------|----------|
| **VB6Plus.dll** | 编解码、加密、文件、网络、GUI | 57+ |
| **VB6OpenSSL.dll** | HTTPS GET/POST 请求 | 2 |
| **VB6MQTT.dll** | MQTT 客户端 | 4 |

### COM 组件

| 组件 | 说明 |
|------|------|
| **RC6 (VBRichClient5)** | 加密、文件、集合、网络、数据库、JSON 等 |
| **DirectCOM** | 免注册 COM 加载器 |

### .NET 程序集

通过 pythonnet 支持任意 .NET 程序集加载和调用。

## 安装

无需额外安装，Python 3.6 32 位嵌入式环境已内置在包中。

**要求**:
- Windows 平台
- Python 3.6+ (64 位)

## 使用方法

### 1. 使用 @dll32 装饰器调用标准 DLL

```python
from vools.dll32 import dll32

# 装饰器模式
@dll32('VB6Plus.dll::Base64Encode_UTF8')
def base64_encode(input_str: str) -> str:
    pass

result = base64_encode('Hello, World!')
print(result)  # SGVsbG8sIFdvcmxkIQ==
```

### 2. 使用内置包装类

#### VB6Plus - 多功能工具库

```python
from vools.dll32 import vb6plus

# Base64 编解码
encoded = vb6plus.base64_encode_utf8('Hello')
decoded = vb6plus.base64_decode_utf8(encoded)

# MD5 哈希
md5_32 = vb6plus.md5_32_utf8('test')
md5_16 = vb6plus.md5_16_utf8('test')

# HTML 编解码
html_encoded = vb6plus.html_encode('<div>test</div>')
html_decoded = vb6plus.html_decode(html_encoded)

# URL 编解码
url_encoded = vb6plus.url_encode_utf8('hello world')
url_decoded = vb6plus.url_decode_utf8(url_encoded)

# 字符串相似度
similarity = vb6plus.str_compare('hello', 'hallo')

# INI 文件操作
value = vb6plus.read_ini_value('Section', 'Key', 'default', 'config.ini')
vb6plus.write_ini_value('Section', 'Key', 'value', 'config.ini')

# AES 加解密
encrypted = vb6plus.aes_encrypt_utf8('data', 'password')
decrypted = vb6plus.aes_decrypt_utf8(encrypted, 'password')

# 二维码生成
vb6plus.make_qrcode('https://example.com', 'qrcode.jpg', size=5)
```

#### OpenSSL - HTTPS 请求

```python
from vools.dll32 import openssl

# GET 请求
response = openssl.get('https://api.example.com/data')

# POST 请求
response = openssl.post(
    'https://api.example.com/submit',
    data='{"key": "value"}',
    content_type='application/json'
)
```

#### MQTT - 消息队列

```python
from vools.dll32 import mqtt

# 连接 MQTT 服务器
mqtt.open('broker.example.com', 1883, 'client_id', 'user', 'password')

# 订阅主题
mqtt.subscribe('test/topic', qos=1)

# 发布消息
mqtt.publish('test/topic', 'Hello MQTT!', qos=1)

# 断开连接
mqtt.close()
```

### 3. 使用 RC6 (VBRichClient5) COM 组件

#### 方式一：全局实例

```python
from vools.dll32 import get_rc6

rc6 = get_rc6()

# 加密解密
encoded = rc6.base64_encode('Hello')
decoded = rc6.base64_decode(encoded)

md5 = rc6.md5('test')
sha256 = rc6.sha256('test')

encrypted = rc6.aes_encrypt('data', 'password')
decrypted = rc6.aes_decrypt(encrypted, 'password')

# 文件操作
content = rc6.read_text('test.txt')
rc6.write_text('output.txt', 'Hello World')

# 使用子对象
crypt = rc6.crypt           # cCrypt - 加密解密
fso = rc6.fso               # cFSO - 文件系统
collection = rc6.collection # cCollection - 集合
json = rc6.json             # cJSON - JSON 处理
timer = rc6.timer           # cTimer - 定时器
memdb = rc6.memdb           # cMemDB - 内存数据库
tcp_client = rc6.tcp_client # cTCPClient - TCP 客户端
```

#### 方式二：直接使用 RC6Plus 类

```python
from vools.dll32._lib.com import RC6Plus

rc6 = RC6Plus(dll_dir=r'path/to/dlls')
result = rc6.base64_encode('Hello')
```

### 4. 使用 .NET 程序集

```python
from vools.dll32._lib.clr import CLRAssembly

# 加载 .NET 程序集
clr = CLRAssembly.load_assembly('System.Data')

# 使用 .NET 类型
import System
table = System.Data.DataTable()
```

### 5. 函数签名注册表

```python
from vools.dll32 import list_dlls, list_functions, get_signature

# 列出所有已注册的 DLL
dlls = list_dlls()
# ['VB6Plus.dll', 'VB6OpenSSL.dll', 'VB6MQTT.dll']

# 列出指定 DLL 的所有函数
funcs = list_functions('VB6Plus.dll')

# 获取函数签名
sig = get_signature('VB6Plus.dll', 'Base64Encode_UTF8')
```

### 6. 内置 DLL 管理

```python
from vools.dll32._dlls import get_dll_path, list_builtin_dlls, dll_exists

# 获取内置 DLL 路径
path = get_dll_path('VB6Plus.dll')

# 列出所有内置 DLL
dlls = list_builtin_dlls()

# 检查 DLL 是否存在
exists = dll_exists('VB6Plus.dll')
```

## API 参考

### @dll32 装饰器

```python
@dll32(dll_spec, *, async_mode=False, fallback=None)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `dll_spec` | `str` | DLL 规格，格式: `"path/to/dll::func_name"` |
| `async_mode` | `bool` | 是否启用异步模式 (默认 False) |
| `fallback` | `Callable` | 调用失败时的回退函数 |

**说明**:
- 如果 `dll_spec` 是相对路径，会自动在 `_dlls/` 目录中查找
- 函数参数类型会自动适配（str、int、float、bytes 等）
- 支持可选参数和默认值

### VB6Plus 类

#### 编解码

| 方法 | 说明 |
|------|------|
| `base64_encode_gb(input_str)` | Base64 编码 (GB) |
| `base64_decode_gb(input_str)` | Base64 解码 (GB) |
| `base64_encode_utf8(input_str)` | Base64 编码 (UTF-8) |
| `base64_decode_utf8(input_str)` | Base64 解码 (UTF-8) |
| `html_encode(input_str)` | HTML 编码 |
| `html_decode(input_str)` | HTML 解码 |
| `url_encode_gb(input_str)` | URL 编码 (GB) |
| `url_decode_gb(input_str)` | URL 解码 (GB) |
| `url_encode_utf8(input_str)` | URL 编码 (UTF-8) |
| `url_decode_utf8(input_str)` | URL 解码 (UTF-8) |
| `unicode_encode(input_str)` | Unicode 编码 (\uXXXX) |
| `unicode_decode(input_str)` | Unicode 解码 |
| `str_to_hex_gb(input_str, is_upper=1)` | 字符串转十六进制 (GB) |
| `str_to_hex_utf8(input_str, is_upper=1)` | 字符串转十六进制 (UTF-8) |
| `hex_to_str_gb(input_str)` | 十六进制转字符串 (GB) |
| `hex_to_str_utf8(input_str)` | 十六进制转字符串 (UTF-8) |

#### 哈希

| 方法 | 说明 |
|------|------|
| `md5_16_gb(input_str)` | MD5 16 位 (GB) |
| `md5_32_gb(input_str)` | MD5 32 位 (GB) |
| `md5_16_utf8(input_str)` | MD5 16 位 (UTF-8) |
| `md5_32_utf8(input_str)` | MD5 32 位 (UTF-8) |

#### 加密

| 方法 | 说明 |
|------|------|
| `aes_encrypt_gb(input_str, password, iv, mode, padding, out_type)` | AES 加密 (GB) |
| `aes_decrypt_gb(input_str, password, iv, mode, padding, in_type)` | AES 解密 (GB) |
| `aes_encrypt_utf8(input_str, password, iv, mode, padding, out_type)` | AES 加密 (UTF-8) |
| `aes_decrypt_utf8(input_str, password, iv, mode, padding, in_type)` | AES 解密 (UTF-8) |

#### 字符串

| 方法 | 说明 |
|------|------|
| `no_html(input_str, no_html_more=0)` | 去除 HTML 标签 |
| `str_compare(str_a, str_b)` | 字符串相似度比较 (0-1) |
| `permutation(input_str, separator=',', result_total=0)` | 字符串全排列 |
| `combination(input_str, separator=',', result_total=0)` | 字符串组合 |
| `explode_data(input_str, start_str, end_str)` | 提取中间文本 |
| `regex_replace(input_str, pattern, replacement)` | 正则替换 |

#### 文件操作

| 方法 | 说明 |
|------|------|
| `read_ini_value(section, key, default='', ini_file='Config.ini')` | 读取 INI 值 |
| `write_ini_value(section, key, value, ini_file='Config.ini')` | 写入 INI 值 |

#### 网络

| 方法 | 说明 |
|------|------|
| `xmlhttp_get(url, headers='', ...)` | XMLHTTP GET 请求 |
| `xmlhttp_post(url, data, headers='', ...)` | XMLHTTP POST 请求 |

#### 图片处理

| 方法 | 说明 |
|------|------|
| `image_to_jpg(src, dst, quality=95)` | 图片转 JPG |
| `image_to_bmp(src, dst)` | 图片转 BMP |
| `make_qrcode(text, path, size=0, ...)` | 生成二维码 |
| `scan_qr_image(path, ...)` | 扫描二维码 |

#### 对话框

| 方法 | 说明 |
|------|------|
| `show_open_file(hwnd=0, filter='', ...)` | 打开文件对话框 |
| `show_save_file(hwnd=0, filter='', ...)` | 保存文件对话框 |
| `show_browser_folder(hwnd=0, ...)` | 浏览文件夹对话框 |

#### 数据库

| 方法 | 说明 |
|------|------|
| `sqlite_open(db_file='DB.DB')` | 打开 SQLite 数据库 |
| `sqlite_close(db_handle)` | 关闭 SQLite 数据库 |
| `sqlite_execute(db_handle, sql)` | 执行 SQL 语句 |

#### 系统工具

| 方法 | 说明 |
|------|------|
| `win_copy_file_to_clipboard(file_or_dir)` | 复制文件到剪贴板 |
| `run_vbscript(vbscript, error_msg)` | 执行 VBScript |

### RC6Plus 类

#### 便捷方法

| 方法 | 说明 |
|------|------|
| `base64_encode(text)` | Base64 编码 |
| `base64_decode(text)` | Base64 解码 |
| `md5(text)` | MD5 哈希 |
| `sha256(text)` | SHA256 哈希 |
| `aes_encrypt(data, password, mode=0, padding=0)` | AES 加密 |
| `aes_decrypt(encrypted, password, mode=0, padding=0)` | AES 解密 |
| `read_text(file_path, encoding='utf-8')` | 读取文本文件 |
| `write_text(file_path, content, encoding='utf-8')` | 写入文本文件 |

#### 子对象

| 属性 | 类型 | 说明 |
|------|------|------|
| `constructor` | cConstructor | RC6 构造器 |
| `crypt` | cCrypt | 加密解密 |
| `fso` | cFSO | 文件系统 |
| `collection` | cCollection | 集合 |
| `sorted_dict` | cSortedDictionary | 有序字典 |
| `json` | cJSON | JSON 处理 |
| `stream` | cStream | 数据流 |
| `timer` | cTimer | 定时器 |
| `tcp_client` | cTCPClient | TCP 客户端 |
| `tcp_server` | cTCPServer | TCP 服务器 |
| `memdb` | cMemDB | 内存数据库 |
| `simple_dom` | cSimpleDOM | XML/HTML 解析 |
| `formula` | cFormula | 公式计算 |

## 注意事项

1. **仅支持 Windows 平台**：32 位 DLL 是 Windows 特有技术
2. **进程间通信开销**：每次调用都会启动 32 位 Python 进程，频繁调用建议批量处理
3. **数据类型限制**：跨进程传输仅支持 JSON 可序列化类型（str、int、float、bool、list、dict、None）
4. **COM 组件注册**：部分 COM 组件可能需要先注册才能使用
5. **线程安全**：当前实现不是线程安全的，多线程环境需自行加锁

## 常见问题

### Q: 调用 DLL 时提示找不到文件？

A: 请确保 DLL 文件存在。如果使用相对路径，会在 `_dlls/` 目录中查找。可以使用绝对路径。

### Q: 如何添加新的 DLL 支持？

A: 
1. 将 DLL 文件放入 `_dlls/` 目录
2. 在 `_signatures/` 中创建对应的签名文件
3. 在 `_signatures/_registry.py` 中注册
4. 可选：创建包装类提供便捷 API

### Q: 性能如何？

A: 由于每次调用都需要启动 32 位 Python 进程，单次调用约有 50-100ms 的开销。适合调用频率不高但需要 32 位 DLL 功能的场景。

### Q: 可以调用自定义的 32 位 DLL 吗？

A: 可以。使用 `@dll32('path/to/your.dll::FunctionName')` 装饰器即可，不需要修改框架代码。
