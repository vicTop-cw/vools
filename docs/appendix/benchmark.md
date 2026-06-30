# 性能基准 (Benchmark)

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#A03
> **最后更新**：2026-06-30

---

## 概述

vools 性能基准测试框架用于对比纯 Python 实现与桥接语言（Nim/Rust/Go）实现的性能差异。通过定期运行基准测试，可以量化性能提升效果，确保桥接优化达到预期目标。

## 快速开始

### 运行所有基准测试

```bash
python benchmark/bridge_benchmark.py
```

### 只测试特定函数

```bash
python benchmark/bridge_benchmark.py --func pickle_encode
```

### JSON 输出

```bash
python benchmark/bridge_benchmark.py --json
```

### 详细输出

```bash
python benchmark/bridge_benchmark.py --verbose
```

## 基准测试结果

### 序列化性能

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| pickle_encode (小数据) | ~120 us | ~18 us | 6-8x |
| pickle_decode (小数据) | ~100 us | ~15 us | 6-7x |
| pickle_encode (大数据) | ~2000 us | ~200 us | 10x |
| json_encode | ~50 us | ~15 us | 3x |
| json_decode | ~45 us | ~12 us | 4x |

### 哈希函数性能

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| sha256_hex (1KB) | ~15 us | ~3 us | 5x |
| md5_hex (1KB) | ~12 us | ~2 us | 6x |
| sha1_hex (1KB) | ~10 us | ~2 us | 5x |
| sha512_hex (1KB) | ~18 us | ~4 us | 4.5x |

### 编码性能

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| base64_encode (1KB) | ~8 us | ~2 us | 4x |
| base64_decode (1KB) | ~7 us | ~2 us | 3.5x |

### 压缩性能

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| zlib_compress (10KB) | ~500 us | ~100 us | 5x |
| zlib_decompress (10KB) | ~200 us | ~50 us | 4x |
| gzip_compress (10KB) | ~600 us | ~120 us | 5x |
| gzip_decompress (10KB) | ~250 us | ~60 us | 4x |

## 测试套件

### 序列化套件 (serialize_suite.py)

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| serialize.pickle_encode_small | pickle 编码 | ~100 bytes |
| serialize.pickle_encode_medium | pickle 编码 | ~5KB |
| serialize.pickle_encode_large | pickle 编码 | ~50KB |
| serialize.pickle_decode_* | pickle 解码 | 对应编码数据 |

### 哈希套件 (hash_suite.py)

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| sha256_small/medium/large | SHA256 哈希 | 22B/1KB/1MB |
| md5_small/medium/large | MD5 哈希 | 22B/1KB/1MB |
| sha1_small/medium/large | SHA1 哈希 | 22B/1KB/1MB |

### Base64 套件 (base64_suite.py)

| 测试名称 | 说明 | 数据大小 |
|---------|------|--------|
| data.seq.base64_encode_small | Base64 编码 | ~120 bytes |
| data.seq.base64_encode_medium | Base64 编码 | ~1.2KB |
| data.seq.base64_encode_large | Base64 编码 | ~12KB |

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--func` | str | None | 只测试包含此字符串的函数 |
| `--repeat` | int | 100 | 迭代次数 |
| `--warmup` | int | 3 | 热身次数 |
| `--json` | flag | False | JSON 输出格式 |
| `--verbose` | flag | False | 详细输出 |

## 在代码中使用

### 作为模块导入

```python
from benchmark.bridge_benchmark import BridgeBenchmark

runner = BridgeBenchmark(repeat=100, warmup=3)

# 导入测试套件
from suites import get_serialize_suite, get_hash_suite

# 运行套件
runner.run_suite(get_serialize_suite())

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
    py_func=lambda: sum(range(10000)),
    bridge_func=lambda: 49995000,
    args=(),
)

print(runner.report())
```

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
