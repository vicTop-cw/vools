# vools.security

安全模块，提供安全评估、表达式处理和哈希计算功能。

## 主要功能

- **安全评估**: `safe_eval` - 安全的表达式求值
- **表达式处理**: `ExpressionHandler` - 表达式处理器
- **哈希计算**: 支持 SHA256、MD5、SHA1 等常用哈希算法（Nim 加速）

## 核心功能

### 安全评估

| 名称 | 说明 |
|------|------|
| `safe_eval` | 安全表达式求值（支持 Rust 加速） |
| `SafeEvalError` | 安全评估异常类 |
| `safe_compile_expression` | 安全编译表达式 |
| `safe_eval_expression` | 安全求值表达式 |
| `create_filter_func` | 创建过滤函数 |
| `create_map_func` | 创建映射函数 |
| `ExpressionSecurityError` | 表达式安全异常 |

### 哈希计算

| 名称 | 说明 |
|------|------|
| `sha256_hex` | SHA256 哈希 |
| `md5_hex` | MD5 哈希 |
| `sha1_hex` | SHA1 哈希 |
| `sha224_hex` | SHA224 哈希 |
| `sha384_hex` | SHA384 哈希 |
| `sha512_hex` | SHA512 哈希 |

## 使用示例

### 安全评估

```python
from vools.security import safe_eval, safe_eval_expression

# 安全求值
result = safe_eval('1 + 2')  # 3

# 支持变量
result = safe_eval('x + y', {'x': 1, 'y': 2})  # 3

# 表达式求值
result = safe_eval_expression('a > b', {'a': 5, 'b': 3})  # True
```

### 哈希计算

```python
from vools.security import sha256_hex, md5_hex

# SHA256 哈希
hash1 = sha256_hex('hello')  # 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
hash2 = sha256_hex(b'hello')  # bytes 输入

# MD5 哈希
md5 = md5_hex('hello')  # 5d41402abc4b2a76b9719d911017c592

# 支持大文件
hash_large = sha256_hex('/path/to/large/file', chunk_size=8192)
```

## 注意事项

- `safe_eval` 禁止执行危险操作（文件读写、系统命令等）
- 哈希函数优先使用 Nim/Rust 加速（若可用），否则回退到 Python 标准库