# 性能基准测试

本文档说明 `benchmark/bridge_benchmark.py` 基准测试框架的使用方法。

## 概述

vools 性能基准测试框架用于对比纯 Python 实现与桥接语言（Nim/Rust/Go）实现的性能差异。通过定期运行基准测试，可以量化性能提升效果，确保桥接优化达到预期目标。

## 快速开始

### 运行所有基准测试

```bash
python benchmark/bridge_benchmark.py
```

输出示例：

```
======================================================================
vools 性能基准测试报告
======================================================================
函数: serialize.pickle_encode_small
  纯 Python: 120.35 us | 桥接库: 18.42 us
  速度提升: 6.5x
  内存节省: 15.2%

函数: serialize.pickle_encode_medium
  纯 Python: 850.21 us | 桥接库: 95.33 us
  速度提升: 8.9x
  内存节省: 22.1%
...
======================================================================
```

### 只测试特定函数

```bash
python benchmark/bridge_benchmark.py --func pickle_encode
```

### JSON 输出

```bash
python benchmark/bridge_benchmark.py --json
```

JSON 输出格式：

```json
[
  {
    "name": "serialize.pickle_encode_small",
    "speedup": 6.5,
    "memory_reduction_pct": 15.2,
    "py_time_us": 120.35,
    "bridge_time_us": 18.42,
    "py_memory_bytes": 10240,
    "bridge_memory_bytes": 8678
  }
]
```

### 详细输出

```bash
python benchmark/bridge_benchmark.py --verbose
```

详细输出包含内存使用的具体数值：

```
函数: serialize.pickle_encode_small
  纯 Python: 120.35 us | 桥接库: 18.42 us
  速度提升: 6.5x
  内存节省: 15.2%
  内存: 纯 Python 10,240 bytes | 桥接库 8,678 bytes
```

### 调整迭代次数

```bash
# 迭代 1000 次（默认 100）
python benchmark/bridge_benchmark.py --repeat 1000

# 热身 5 次（默认 3）
python benchmark/bridge_benchmark.py --warmup 5
```

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--func` | str | None | 只测试包含此字符串的函数（部分匹配） |
| `--repeat` | int | 100 | 迭代次数 |
| `--warmup` | int | 3 | 热身次数 |
| `--json` | flag | False | JSON 输出格式 |
| `--verbose` | flag | False | 详细输出 |

## 测试套件

基准测试框架包含以下测试套件：

### 序列化套件 (serialize_suite.py)

测试 pickle 序列化/反序列化的性能：

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| serialize.pickle_encode_small | pickle 编码 | ~100 bytes |
| serialize.pickle_encode_medium | pickle 编码 | ~5KB |
| serialize.pickle_encode_large | pickle 编码 | ~50KB |
| serialize.pickle_decode_* | pickle 解码 | 对应编码数据 |

### 哈希套件 (hash_suite.py)

测试各种哈希函数的性能：

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| sha256_small/medium/large | SHA256 哈希 | 22B/1KB/1MB |
| md5_small/medium/large | MD5 哈希 | 22B/1KB/1MB |
| sha1_small/medium/large | SHA1 哈希 | 22B/1KB/1MB |
| sha224_small/medium/large | SHA224 哈希 | 22B/1KB/1MB |
| sha384_small/medium/large | SHA384 哈希 | 22B/1KB/1MB |
| sha512_small/medium/large | SHA512 哈希 | 22B/1KB/1MB |

### Base64 套件 (base64_suite.py)

测试 Base64 编解码的性能：

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| data.seq.base64_encode_small | Base64 编码 | ~120 bytes |
| data.seq.base64_encode_medium | Base64 编码 | ~1.2KB |
| data.seq.base64_encode_large | Base64 编码 | ~12KB |
| data.seq.base64_decode_* | Base64 解码 | 对应编码数据 |

### JSON 套件 (json_suite.py)

测试 JSON 编码/解码的性能：

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| serialize.json_encode_small | JSON 编码 | ~100 bytes |
| serialize.json_encode_medium | JSON 编码 | ~5KB |
| serialize.json_encode_large | JSON 编码 | ~50KB |
| serialize.json_decode_* | JSON 解码 | 对应编码数据 |

### 压缩套件 (compress_suite.py)

测试压缩/解压的性能：

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| data.seq.gzip_compress_small | gzip 压缩 | ~1.2KB |
| data.seq.gzip_compress_medium | gzip 压缩 | ~12KB |
| data.seq.gzip_compress_large | gzip 压缩 | ~120KB |
| data.seq.gzip_decompress_* | gzip 解压 | 对应压缩数据 |
| data.seq.zlib_compress_* | zlib 压缩 | 各种大小 |
| data.seq.zlib_decompress_* | zlib 解压 | 各种大小 |

## 输出格式说明

### 普通输出

```
函数: {name}
  纯 Python: {py_time_us:.2f} us | 桥接库: {bridge_time_us:.2f} us
  速度提升: {speedup:.1f}x
  内存节省: {memory_reduction:.1f}%
```

**字段说明：**

- `纯 Python`：纯 Python 实现的耗时（微秒）
- `桥接库`：桥接语言实现的耗时（微秒）
- `速度提升`：纯 Python 耗时 / 桥接库耗时
- `内存节省`：((纯Python内存 - 桥接库内存) / 纯Python内存) × 100%

### JSON 输出字段

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 测试名称 |
| speedup | float | 速度提升倍数 |
| memory_reduction_pct | float | 内存减少百分比 |
| py_time_us | float | 纯 Python 耗时（微秒） |
| bridge_time_us | float | 桥接库耗时（微秒） |
| py_memory_bytes | int | 纯 Python 内存峰值（字节） |
| bridge_memory_bytes | int | 桥接库内存峰值（字节） |

## 在代码中使用

### 作为模块导入

```python
from benchmark.bridge_benchmark import BridgeBenchmark

runner = BridgeBenchmark(repeat=100, warmup=3)

# 导入测试套件
from suites import get_serialize_suite, get_hash_suite

# 运行套件
runner.run_suite(get_serialize_suite())
runner.run_suite(get_hash_suite())

# 输出报告
print(runner.report(verbose=True))
```

### 自定义测试用例

```python
from benchmark.bridge_benchmark import BridgeBenchmark

runner = BridgeBenchmark(repeat=100)

# 添加自定义测试
runner.bench(
    name="my_custom_function",
    py_func=lambda: sum(range(10000)),  # 纯 Python 实现
    bridge_func=lambda: 49995000,       # 桥接实现
    args=(),
)

print(runner.report())
```

### 单次测试

```python
import time
import tracemalloc
import statistics

def bench(name, py_func, bridge_func, repeat=100, warmup=3):
    """单次基准测试"""
    # 热身
    for _ in range(warmup):
        py_func()
        bridge_func()
    
    # 计时
    py_times = []
    tracemalloc.start()
    for _ in range(repeat):
        start = time.perf_counter()
        py_func()
        py_times.append((time.perf_counter() - start) * 1_000_000)
    _, py_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    bridge_times = []
    tracemalloc.start()
    for _ in range(repeat):
        start = time.perf_counter()
        bridge_func()
        bridge_times.append((time.perf_counter() - start) * 1_000_000)
    _, bridge_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    py_time = statistics.median(py_times)
    bridge_time = statistics.median(bridge_times)
    speedup = py_time / bridge_time
    memory_reduction = (py_peak - bridge_peak) / py_peak * 100
    
    print(f"{name}:")
    print(f"  纯 Python: {py_time:.2f} us")
    print(f"  桥接库: {bridge_time:.2f} us")
    print(f"  速度提升: {speedup:.1f}x")
    print(f"  内存节省: {memory_reduction:.1f}%")
```

## 性能参考

以下是典型硬件上的参考性能数据（实际数据因硬件而异）：

| 函数 | 纯 Python | 桥接库 | 提升倍数 |
|------|----------|--------|---------|
| pickle_encode (小数据) | ~120 us | ~18 us | 6-8x |
| pickle_decode (小数据) | ~100 us | ~15 us | 6-7x |
| sha256_hex (1KB) | ~15 us | ~3 us | 5x |
| base64_encode (1KB) | ~8 us | ~2 us | 4x |
| json_encode (小数据) | ~50 us | ~15 us | 3x |

## 注意事项

1. **预热**：基准测试包含热身阶段，确保 JIT 和缓存达到稳定状态
2. **中位数**：使用中位数而非平均值，减少极端值影响
3. **内存测量**：使用 `tracemalloc` 测量峰值内存
4. **关闭杀毒软件**：某些杀毒软件可能影响测量准确性
5. **稳定环境**：运行基准测试时避免其他高负载任务

## 持续集成

基准测试可以集成到 CI 流程中：

```bash
# 在 CI 中运行并检查性能回归
python benchmark/bridge_benchmark.py --json > benchmark_results.json

# 使用 jq 检查关键指标
jq '.[] | select(.name == "serialize.pickle_encode_small") | .speedup' benchmark_results.json
```
