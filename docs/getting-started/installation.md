# 安装 {#002}

> **模块路径**：`vools`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#002
> **最后更新**：2026-06-30

## 环境要求

- Python 3.6、3.7、3.8、3.9、3.10、3.11、3.12、3.13
- 操作系统：Windows、macOS、Linux
- 无强制外部依赖（核心功能纯 Python 实现）

## 安装方式

### 方式一：pip 安装

```bash
pip install vools
```

### 方式二：从源码安装

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install .
```

### 方式三：开发模式安装

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .
```

## 验证安装

安装完成后，可通过以下方式验证：

### 方法一：导入验证

```python
import vools

print(vools.__version__)  # 输出：0.4.3
print(vools.__author__)    # 输出：Victor
```

✅ 测试通过

### 方法二：功能验证

```python
from vools.functional import Pipe
from vools.decorators import memorize

# 验证函数式工具
result = range(1, 6) | Pipe(lambda x: [i * 2 for i in x]) | Pipe(sum)
print(result)  # 输出：30

# 验证装饰器
@memorize
def add(a, b):
    return a + b

print(add(1, 2))  # 输出：3
print(add(1, 2))  # 输出：3（从缓存返回）
```

✅ 测试通过

## 可选依赖

vools 核心功能无需额外依赖，以下可选依赖提供额外功能：

| 可选依赖 | 用途 | 安装命令 |
|---------|------|---------|
| `dev` | 开发测试工具 | `pip install vools[dev]` |
| `cli` | 命令行工具 | `pip install vools[cli]` |
| `docs` | 文档构建 | `pip install vools[docs]` |
| `serialize` | 序列化增强 | `pip install vools[serialize]` |
| `nim` | Nim 加速模块 | `pip install vools[nim]` |
| `rust` | Rust 加速模块 | `pip install vools[rust]` |
| `mojo` | Mojo 加速模块 | `pip install vools[mojo]` |
| `freebasic` | FreeBASIC 加速模块 | `pip install vools[freebasic]` |

### 序列化增强

```python
# 安装序列化依赖后支持更多格式
pip install vools[serialize]

# msgpack 和 orjson 将被启用
```

## 下一步

安装完成后，请前往 [快速开始](./quickstart.md) 开始使用 vools。
