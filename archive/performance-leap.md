# 性能跃迁计划

## 概述

vools 已在 Python 3.6/3.13 双版本上稳定运行，但部分核心函数（如序列化和反序列化、哈希计算、JSON 处理、数据压缩）在纯 Python 实现下仍有显著的性能瓶颈。本计划通过桥接编译型语言（Nim/Rust/Go/Scala），为这些高频函数提供可选的高性能替代实现，在保持纯 Python 可用性的前提下，让有本地扩展的用户获得数量级的性能提升。

## 核心目标

1. **性能跃迁**：将高频核心函数的性能提升 3-10 倍
2. **零破坏性**：纯 Python 实现始终可用，桥接加速为可选增强
3. **统一接口**：通过 `@bridge` 装饰器体系透明注入
4. **跨平台分发**：预编译 .dll/.so，支持 Windows 和 Linux

## 优化模块

### Tier 1: 高频调用（性能差距 >10x 目标）

| 模块 | 函数 | 纯 Python | 桥接语言 | 预期提升 |
|------|------|----------|---------|---------|
| serialize.codec | pickle_encode | pickle.dumps | Nim | 5-10x |
| serialize.codec | pickle_decode | pickle.loads | Nim | 5-10x |
| security.hash | sha256_hex | hashlib | Nim | 3-5x |
| security.hash | md5_hex | hashlib | Nim | 3-5x |
| security.hash | sha1_hex | hashlib | Nim | 3-5x |
| data.seq | base64_encode | base64 | Nim | 3-5x |
| data.seq | base64_decode | base64 | Nim | 3-5x |

### Tier 2: 中频调用（性能差距 3-10x）

| 模块 | 函数 | 纯 Python | 桥接语言 | 预期提升 |
|------|------|----------|---------|---------|
| serialize | json_encode | json.dumps | Nim | 2-5x |
| serialize | json_decode | json.loads | Nim | 2-5x |
| cache.sigcache | hash_signature | str hash | Nim | 3-8x |

### Tier 3: 特定场景（性能差距 2-5x）

| 模块 | 函数 | 纯 Python | 桥接语言 | 预期提升 |
|------|------|----------|---------|---------|
| data.seq | zlib_compress | zlib | Nim | 3-5x |
| data.seq | zlib_decompress | zlib | Nim | 3-5x |
| data.seq | gzip_compress | gzip | Nim | 2-3x |
| data.seq | gzip_decompress | gzip | Nim | 2-3x |

## 桥接语言选型策略

| 语言 | 适用场景 | 理由 |
|------|---------|------|
| **Nim** | 通用高速（序列化、哈希、JSON、Base64） | 编译产物小（~50KB），与 C 无缝互调 |
| **Rust** | 安全关键（路径验证、正则、超时控制） | 内存安全，无 GC 停顿 |
| **Go** | 异步并行、网络 IO、进程管理 | goroutine 轻量并发 |
| **Scala** | 高吞吐数据流（批量序列化） | JVM 高吞吐，适合批处理 |

## @bridge 装饰器

### bridge_function

`@bridge_function` 装饰器用于声明一个函数由桥接库实现。当桥接库可用时替换原实现，否则回退到纯 Python 实现。

```python
from vools.bridge.core.decorators import bridge_function

@bridge_function("nim", fallback=_py_md5, lib_name="vools_crypto", func_name="md5_hash")
def md5_hex(data: bytes) -> str:
    """MD5 哈希计算，优先使用 Nim 加速"""
    import hashlib
    return hashlib.md5(data).hexdigest()
```

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| language | str | 目标语言名称（如 "nim"、"rust"） |
| fallback | callable | 回退函数，桥接库不可用时调用 |
| lib_name | str | 共享库名称（默认根据函数名自动推导） |
| func_name | str | 库中的函数名称（默认与 Python 函数名相同） |
| serializer | callable | 参数序列化函数（可选） |
| deserializer | callable | 返回值反序列化函数（可选） |

### bridge_module

`@bridge_module` 装饰器将一个类标记为桥接模块，类中的所有公共方法自动使用对应语言的实现。

```python
from vools.bridge.core.decorators import bridge_module, bridge_func_name

@bridge_module("nim", lib_name="vools_crypto")
class CryptoModule:
    def md5_hash(self, data: bytes) -> bytes:
        pass  # 实现将由底层 Nim 库提供

    @bridge_func_name("sha1_hash")
    def sha1(self, data: bytes) -> bytes:
        pass  # 指定底层函数名为 sha1_hash
```

### 自动降级机制

当桥接库不可用或执行出错时，系统会自动回退到纯 Python 实现：

```
桥接函数调用流程：
1. 检查桥接库是否可用
   ├── 可用 → 调用桥接实现 → 返回结果
   └── 不可用 → 继续步骤 2
2. 检查是否有 fallback 函数
   ├── 有 → 调用 fallback → 返回结果
   └── 无 → 抛出 RuntimeError
```

**异常处理：** 如果桥接库函数抛出异常，系统会捕获异常、记录警告，并回退到纯 Python 实现。

## 使用示例

### 序列化/反序列化

```python
from vools.serialize.codec import pickle_encode, pickle_decode

# 自动使用 Nim 加速（如可用）
data = {"key": "value", "numbers": list(range(1000))}
encoded = pickle_encode(data)
decoded = pickle_decode(encoded)
```

### 哈希计算

```python
from vools.security.hash import sha256_hex, md5_hex

# 自动使用 Nim 加速
result = sha256_hex(b"hello world")
result = md5_hex(b"hello world")
```

### Base64 编解码

```python
from vools.bridge.nim.encoding import base64_encode, base64_decode

# 自动使用 Nim 加速
encoded = base64_encode("hello world")
decoded = base64_decode(encoded)
```

### JSON 处理

```python
from vools.bridge.nim import nim_json_encode, nim_json_decode

# 自动使用 Nim/orjson 加速
data = {"users": [{"id": i, "name": f"user_{i}"} for i in range(100)]}
encoded = nim_json_encode(data)
decoded = nim_json_decode(encoded)
```

## 编译桥接库

### Nim 桥接库编译步骤

1. **安装 Nim 编译器**

   ```bash
   # Linux/macOS
   curl https://nim-lang.org/install/install.sh | sh
   
   # Windows
   # 下载并安装 choosenim 或 Nim for Windows
   ```

2. **编译桥接库**

   ```bash
   # 序列化库
   cd vools/nim_core
   nim c -d=release --app=lib --out:vools_serialize.dll vools_serialize.nim
   
   # 加密库
   nim c -d=release --app=lib --out:vools_crypto.dll vools_crypto.nim
   
   # 编码库
   nim c -d=release --app=lib --out:vools_encoding.dll vools_encoding.nim
   ```

3. **验证编译结果**

   ```python
   from vools.bridge.nim import is_nim_available
   
   print(f"Nim 桥接可用: {is_nim_available()}")
   ```

### Rust 桥接库编译步骤

1. **安装 Rust 编译器**

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

2. **编译桥接库**

   ```bash
   cd vools/rust/safe_eval
   cargo build --release
   ```

## 性能基准测试

详细的基准测试使用方法请参见 [benchmark.md](benchmark.md)。

运行基准测试：

```bash
# 运行所有基准测试
python benchmark/bridge_benchmark.py

# 只测试特定函数
python benchmark/bridge_benchmark.py --func pickle_encode

# JSON 输出
python benchmark/bridge_benchmark.py --json

# 详细输出
python benchmark/bridge_benchmark.py --verbose
```

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                     Python 层                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ serialize   │  │ security    │  │ data.seq    │   │
│  │ .codec      │  │ .hash       │  │ .base64     │   │
│  │ .json       │  │             │  │ .compress   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│         │                │                │           │
│         └────────────────┼────────────────┘           │
│                          ▼                              │
│              ┌─────────────────────┐                  │
│              │   @bridge_function   │                  │
│              │   装饰器体系         │                  │
│              └──────────┬────────────┘                  │
└─────────────────────────┼───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   桥接加载层                             │
│  ┌─────────────────────────────────────────────────┐   │
│  │ vools.bridge.core.loader                        │   │
│  │ - load_library(language, lib_name)             │   │
│  │ - is_available(language)                        │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   本地库层                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │  Nim    │  │  Rust   │  │   Go    │  │  Scala  │  │
│  │ .dll    │  │ .dll    │  │ .dll    │  │ .jar    │  │
│  │ .so     │  │ .so     │  │ .so     │  │         │  │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 兼容性说明

- **Python 3.6+**：所有桥接库分发物须在 Python 3.6 环境下可用
- **零破坏性**：未安装桥接库时，纯 Python 实现须完全正常工作
- **循环导入防护**：桥接库不得直接 import vools 子包，须通过 shim 中转

## 常见问题

**Q: 如何检查桥接库是否可用？**

```python
from vools.bridge.nim import is_nim_available

if is_nim_available():
    print("Nim 加速已启用")
else:
    print("使用纯 Python 实现")
```

**Q: 如果桥接库加载失败会怎样？**

系统会自动回退到纯 Python 实现，不影响程序正常运行。可以通过日志查看警告信息。

**Q: 如何强制使用纯 Python 实现？**

目前不支持强制禁用桥接库。如有需要，可以在导入前设置环境变量或修改源码中的桥接函数。
