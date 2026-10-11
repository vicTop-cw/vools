# vools 性能跃迁计划 Spec（修订版）

## Why

vools 已在 Python 3.6/3.13 双版本上稳定运行，但部分核心函数（如序列化、哈希、JSON、文件 IO）在纯 Python 实现下仍有显著性能瓶颈。本计划通过桥接编译型语言，为高频函数提供可选的高性能替代实现，在保持纯 Python 可用性的前提下实现数量级性能提升。

## What Changes

- **新增 `@bridge` 装饰器体系**：统一管理高性能桥接函数的加载、降级和校验
- **分语言实现优化模块**：按语言特长分配任务
- **构建跨平台分发机制**：预编译 .dll/.so，通过桥接加载器按需注入
- **保持向后兼容**：Python 原生实现始终可用，桥接加速为可选增强

## 桥接语言选型策略（已确定）

| 语言 | 适用场景 | 理由 |
|------|---------|------|
| **Nim** | 通用高速（序列化、哈希、JSON、Base64、压缩） | 编译产物小（~50KB），与 C 无缝互调，Python 原生调用协议 |
| **Rust** | 安全关键（路径验证、正则、超时控制） | 内存安全，无 GC 停顿，保证不崩 |
| **Go** | 异步并行、进程管理 | goroutine 轻量并发，原生跨平台编译 |
| **PowerShell** | Windows 系统配置读取 | 平台原生，无编译依赖 |
| **Shell** | Linux 系统配置读取 | 平台原生，无编译依赖 |
| **Scala** | 高吞吐数据流（待定） | JVM 高吞吐，适合批处理 |

## 约束条件

1. **不修改现有 API**：所有优化通过 `@bridge` 装饰器透明注入，不改变函数签名和返回值
2. **Python 3.6+ 兼容**：桥接库分发物须在 Python 3.6 环境下可用
3. **零破坏性**：未安装桥接库时，纯 Python 实现须完全正常工作
4. **循环导入禁止**：桥接库不得直接 import vools 子包，须通过 shim 中转
5. **谨慎优化已有装饰器的函数**：原函数已有装饰器时，桥接优化须非常谨慎
6. **显著提升才优化**：仅优化速度提升 ≥2x 或内存节省 ≥20% 的函数

## 优化候选函数清单

### Tier 1: 高频调用，预期提升 ≥5x

| 函数 | 当前实现 | 优化语言 | 预期提升 | 风险 | 循环导入风险 |
|------|---------|---------|---------|------|------------|
| `serialize.codec.pickle_encode` | pickle.dumps | Nim | 5-10x | 低 | 无 |
| `serialize.codec.pickle_decode` | pickle.loads | Nim | 5-10x | 低 | 无 |
| `security.hash.sha256_hex` | hashlib.sha256 | Nim | 3-5x | 低 | 无 |
| `security.hash.md5_hex` | hashlib.md5 | Nim | 3-5x | 低 | 无 |
| `data.seq.base64_encode` | base64.b64encode | Nim | 3-5x | 低 | 无 |
| `data.seq.base64_decode` | base64.b64decode | Nim | 3-5x | 低 | 无 |

### Tier 2: 中频调用，预期提升 2-5x

| 函数 | 当前实现 | 优化语言 | 预期提升 | 风险 | 循环导入风险 |
|------|---------|---------|---------|------|------------|
| `serialize.json.dumps` | json.dumps | Nim/Rust | 2-5x | 中 | 无 |
| `serialize.json.loads` | json.loads | Nim/Rust | 2-5x | 中 | 无 |
| `cache.sigcache.hash_signature` | str hash | Nim | 3-8x | 低 | **有**（引用sigcache） |
| `data.seq.compress` | zlib.compress | Nim | 3-5x | 低 | 无 |
| `data.seq.decompress` | zlib.decompress | Nim | 3-5x | 低 | 无 |

### Tier 3: 特定场景，预期提升 2-3x

| 函数 | 当前实现 | 优化语言 | 预期提升 | 风险 | 循环导入风险 |
|------|---------|---------|---------|------|------------|
| `sys.env.get_env` | os.environ | PowerShell/Shell | 平台最优 | 低 | 无 |
| `sys.dll.load_library` | ctypes | Nim | 2-3x | 中 | 无 |

### 待定：Go 并行优化候选

| 函数 | 当前实现 | 优化语言 | 预期提升 | 风险 | 循环导入风险 |
|------|---------|---------|---------|------|------------|
| `reactive.scheduler` 异步调度 | asyncio | Go | 2-5x | 高 | **有** |
| `bridge.loader` 并行加载 | sequential | Go | 2-3x | 中 | 无 |

## 已实现的装饰器接口

`vools/decorators/bridge_decorator.py` 已实现：

```python
@bridge(lang='nim', symbol='serialize_encode', fallback=pickle_encode_impl)
def pickle_encode(obj):
    ...
```

## 循环导入风险标记

**高风险**：`cache.sigcache` 引用了 `bridge` 子包的符号，若要对 `sigcache` 做 Nim 优化，必须通过独立 shim 中转，不得直接在 `sigcache.py` 中 import 桥接模块。

**中风险**：`reactive.scheduler` 使用 asyncio，若用 Go 优化并行调度，需要通过纯 Python shim 中转 asyncio 调用。

## Impact

- Affected specs: 序列化框架、桥接子包体系、装饰器体系
- Affected code: vools/serialize/*, vools/security/*, vools/data/*, vools/cache/*, vools/sys/*
