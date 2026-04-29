# vools 项目安全审计报告

## 报告概述

本报告对 vools 项目进行了全面的安全漏洞检查，涵盖代码注入、路径遍历、并发安全、敏感数据处理等多个安全维度。

---

## 一、高危漏洞

### 1.1 代码注入漏洞（Code Injection）

#### 1.1.1 直接使用 eval/exec 执行用户输入

**风险等级：严重**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/vic/viclist.py` | 195 | `eval(func)(s)` - 直接执行字符串函数 |
| `vools/vic/viclist.py` | 213 | `eval(func)(s)` - 直接执行字符串过滤函数 |
| `vools/vic/viclist.py` | 250 | `eval(func)` - 直接执行字符串函数 |
| `vools/vic/viclist.py` | 299 | `eval(func)` - 直接执行 starmap 函数 |
| `vools/vic/viclist.py` | 363 | `eval(func)(self)` - 直接执行字符串函数 |
| `vools/vic/viclist.py` | 401 | `eval(func)(self)` - 直接执行字符串函数 |
| `vools/vic/viclist.py` | 489 | `eval(pred)` - 直接执行字符串谓词 |
| `vools/vic/viclist.py` | 517 | `eval(pred)` - 直接执行字符串谓词 |
| `vools/vic/viclist.py` | 539 | `eval(pred)` - 直接执行字符串谓词 |
| `vools/vic/victext.py` | 147 | `exec(self._text)` - 直接执行文本内容 |
| `vools/vic/victext.py` | 149 | `eval(self._text)` - 直接执行文本内容 |
| `vools/vic/victools.py` | 123 | `eval(ex, globals(), locals())` - 直接执行表达式 |

**漏洞分析：**
- 用户可以传入任意 Python 代码字符串
- `eval(func)(s)` 模式允许执行任意函数调用
- 攻击者可执行 `__import__('os').system('rm -rf /')` 等恶意代码
- 包含完整的 globals() 和 locals() 上下文，风险极高

**修复建议：**
```python
# 使用安全表达式求值替代
from vools.security.safe_eval import safe_eval, SafeEvalError

# 替换 eval(func)
try:
    func = safe_eval(func, allowed_vars={})
except SafeEvalError as e:
    raise ValueError(f"无效的函数表达式: {e}")
```

---

### 1.2 路径遍历漏洞（Path Traversal）

**风险等级：严重**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/vic/victext.py` | 37-50 | `write()` 方法直接使用用户提供的路径 |
| `vools/vic/victext.py` | 79-82 | `read()` 方法直接使用用户提供的路径 |

**漏洞分析：**
```python
# 原始代码（victext.py:48-50）
fd = fd[(7 if fd.startswith(r'file://') else 0):]
with open(fd, mode, encoding="utf-8") as f:
    f.write(self._text)
```
- 用户可传入 `../../../etc/passwd` 等恶意路径
- 仅简单处理 `file://` 前缀，缺乏路径规范化
- 可导致任意文件读写

**修复建议：**
```python
import os

def write(self, file_path="output.sql", mode='w'):
    # 规范化路径
    file_path = os.path.normpath(file_path)
    
    # 可选：限制在特定目录内
    allowed_dir = os.path.abspath("./output")
    full_path = os.path.abspath(file_path)
    
    if not full_path.startswith(allowed_dir):
        raise ValueError("不允许访问指定路径")
    
    with open(full_path, mode, encoding="utf-8") as f:
        f.write(self._text)
```

---

### 1.3 线程安全漏洞（Race Condition）

**风险等级：高**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/decorators/shotcut.py` | 245-264 | 缓存字典无锁保护 |

**漏洞分析：**
```python
# 原始代码（shotcut.py:245-264）
cache = {}  # 全局共享字典

def wrapper(*args, **kwargs) -> R:
    nonlocal cache
    key = str(args) + str(kwargs)
    now = time.time()
    
    expired_keys = [k for k, (_, timestamp) in cache.items() if now - timestamp > ttl]
    for k in expired_keys:
        del cache[k]  # 竞态条件：可能在迭代时被其他线程修改
    
    if key not in cache:
        result = func(*args, **kwargs)
        cache[key] = (result, now)  # 竞态条件：可能被覆盖
    else:
        result, _ = cache[key]
```
- 多个线程同时读写共享字典
- 可能导致数据不一致、KeyError、迭代错误

**修复建议：**
```python
import threading

def ttl_cache(ttl: int = 60):
    cache = {}
    lock = threading.Lock()  # 添加锁
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> R:
        nonlocal cache
        key = str(args) + str(kwargs)
        now = time.time()
        
        with lock:  # 保护所有缓存操作
            expired_keys = [k for k, (_, timestamp) in cache.items() if now - timestamp > ttl]
            for k in expired_keys:
                del cache[k]
            
            if key not in cache:
                result = func(*args, **kwargs)
                cache[key] = (result, now)
            else:
                result, _ = cache[key]
        
        return result
```

---

## 二、中危漏洞

### 2.1 敏感数据明文存储

**风险等级：中**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/core/config.py` | 24 | 密码以明文存储 |
| `vools/core/config.py` | 67-68 | 密码从环境变量明文读取 |

**漏洞分析：**
```python
@dataclass
class DatabaseConfig:
    password: str = ""  # 明文存储密码

# 从环境变量读取
if os.environ.get("DB_PASSWORD"):
    self.database.password = os.environ["DB_PASSWORD"]
```
- 密码以明文形式存储在内存中
- 可能通过日志或调试信息泄露

**修复建议：**
```python
from getpass import getpass

@dataclass
class DatabaseConfig:
    password: str = ""
    
    def get_password(self):
        """安全获取密码（避免直接暴露）"""
        return self.password
    
    def __repr__(self):
        """隐藏密码显示"""
        return f"DatabaseConfig(password='***')"
```

---

### 2.2 异常信息泄露

**风险等级：中**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/security/safe_eval.py` | 118 | 直接暴露语法错误详情 |
| `vools/security/safe_eval.py` | 122 | 直接暴露求值错误详情 |

**漏洞分析：**
```python
except SyntaxError as e:
    raise SafeEvalError(f"语法错误: {e}")  # 可能泄露系统信息
```
- 错误信息可能包含敏感的系统路径或配置信息
- 在生产环境可能被攻击者利用

**修复建议：**
```python
except SyntaxError as e:
    if config.debug:
        raise SafeEvalError(f"语法错误: {e}")
    else:
        raise SafeEvalError("表达式语法错误")
```

---

### 2.3 不安全的文件操作

**风险等级：中**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/decorators/cache.py` | 355 | 缓存目录路径可被操控 |
| `vools/decorators/cache.py` | 357 | 缓存文件名可被操控 |

**漏洞分析：**
```python
cache_dir = os.path.join(os.path.dirname(func_file), "__persist__")
cache_path = os.path.join(cache_dir, f"{file_key}.json")
```
- `file_key` 参数可被用户控制
- 可能导致路径遍历或文件覆盖

**修复建议：**
```python
import hashlib

# 使用哈希替代直接使用文件名
def sanitize_file_key(file_key: str) -> str:
    """安全处理文件名，防止路径遍历"""
    # 移除危险字符
    safe_key = ''.join(c for c in file_key if c.isalnum() or c in ('_', '-'))
    # 使用哈希确保唯一性和安全性
    return hashlib.md5(safe_key.encode()).hexdigest()
```

---

## 三、低危漏洞

### 3.1 硬编码危险模式列表

**风险等级：低**

**问题位置：**

| 文件 | 行号 | 问题描述 |
|------|------|----------|
| `vools/security/safe_eval.py` | 143-148 | 危险模式列表硬编码 |

**漏洞分析：**
```python
DANGEROUS_PATTERNS = [
    'import', 'open', 'exec', 'eval', 'compile',
    '__', 'getattr', 'setattr', 'delattr',
    'os.', 'sys.', 'subprocess', 'requests',
    'eval(', 'exec(', 'compile(', 'open(',
]
```
- 模式匹配基于字符串查找，可能被绕过
- 例如：`__import__('os').system(...)` 中的 `import` 被检测，但 `__builtins__.__import__` 可能绕过

**修复建议：**
使用 AST 解析而非字符串匹配进行安全检查。

---

## 四、安全问题汇总

| 风险等级 | 数量 | 主要问题 |
|----------|------|----------|
| 严重 | 12 | eval/exec 代码注入 |
| 高 | 3 | 路径遍历、线程安全 |
| 中 | 4 | 敏感数据、异常泄露、文件操作 |
| 低 | 1 | 硬编码模式 |

---

## 五、修复优先级建议

| 优先级 | 修复项 | 原因 |
|--------|--------|------|
| P0 | `viclist.py` 中的 eval | 高危代码注入，多处使用 |
| P0 | `victext.py` 中的 exec/eval | 高危代码注入，可执行任意代码 |
| P1 | `victext.py` 路径遍历 | 可读写任意文件 |
| P1 | `shotcut.py` 线程安全 | 并发环境下数据损坏 |
| P2 | `cache.py` 文件操作 | 可能被利用覆盖文件 |
| P2 | `safe_eval.py` 异常泄露 | 信息泄露风险 |
| P3 | `config.py` 密码处理 | 内存中明文存储 |
| P3 | `safe_eval.py` 模式匹配 | 可被绕过 |

---

## 六、代码优化建议

### 6.1 建立安全编码规范

1. **禁止直接使用 eval/exec**：必须通过安全评估层
2. **路径验证**：所有文件路径必须经过规范化和白名单检查
3. **线程安全**：共享状态必须使用锁保护
4. **敏感数据**：密码等敏感信息不应明文打印或存储

### 6.2 安全工具封装

建议创建统一的安全工具模块，封装所有危险操作：

```python
# vools/security/__init__.py
from .safe_eval import safe_eval, SafeEvalError
from .path_utils import sanitize_path, validate_path
from .thread_utils import synchronized, ThreadSafeDict

__all__ = ['safe_eval', 'SafeEvalError', 'sanitize_path', 'validate_path', 'synchronized', 'ThreadSafeDict']
```

---

## 七、总结

vools 项目存在**多处严重的安全漏洞**，主要集中在：

1. **代码注入**：多个文件直接使用 eval/exec 执行用户输入
2. **路径遍历**：文件操作缺乏路径验证
3. **线程安全**：共享缓存字典无锁保护

**建议立即修复 P0 和 P1 级别的漏洞**，特别是 `viclist.py` 和 `victext.py` 中的 eval/exec 使用，这些是最直接的安全威胁。