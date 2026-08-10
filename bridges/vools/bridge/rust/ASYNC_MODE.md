# Rust 桥接异步模式快速参考

## 简介

Rust 桥接模块支持异步编译和执行模式，使用 `@rust(async_mode=True)` 装饰器启用。

## 基本用法

```python
import asyncio
from vools.bridge.rust import rust

@rust(async_mode=True)
async def async_fib(n: int) -> int:
    """
    异步斐波那契数列

    编译和执行在后台线程中进行，不阻塞主线程。
    """
    return """
    if n <= 1 {
        1
    } else {
        async_fib(n - 1) + async_fib(n - 2)
    }
    """

# 调用异步函数
result = asyncio.run(async_fib(30))
```

## 核心特性

### 1. 后台线程执行
- 使用 `ThreadPoolExecutor` (默认 4 个工作线程)
- 编译和执行都在后台线程中进行
- 主线程保持响应，不被阻塞

### 2. 异步调用
```python
async def main():
    # 异步调用
    result = await async_fib(20)
    print(f"Result: {result}")

asyncio.run(main())
```

### 3. 并发调用
```python
async def concurrent_demo():
    # 多个异步调用并行执行
    results = await asyncio.gather(
        async_fib(15),
        async_fib(18),
        async_fib(20)
    )
    print(f"Results: {results}")

asyncio.run(concurrent_demo())
```

### 4. 混合同步和异步
```python
@rust
def sync_add(a: int, b: int) -> int:
    return "a + b"

@rust(async_mode=True)
async def async_mul(a: int, b: int) -> int:
    return "a * b"

async def mixed_usage():
    # 同步调用
    sync_result = sync_add(10, 5)

    # 异步调用
    async_result = await async_mul(10, 5)

    # 组合使用
    total = sync_result + async_result
    return total

asyncio.run(mixed_usage())
```

### 5. 带回退机制
```python
def python_fallback(x: int) -> int:
    return x * 10

@rust(async_mode=True, fallback=python_fallback)
async def async_with_fallback(x: int) -> int:
    return "x + 1"

# 如果编译失败或 Rust 不可用，自动回退
result = asyncio.run(async_with_fallback(5))
```

## 与其他模式组合

### DEBUG 模式
```python
@rust(mode='DEBUG', async_mode=True)
async def async_debug_func(x: int) -> int:
    """强制重新编译"""
    return "x * 2"
```

### ONLY_CODE 模式
```python
@rust(mode='ONLY_CODE', async_mode=True)
async def async_code_only(x: int) -> int:
    """只生成代码"""
    return "x + 100"

# 返回生成的 Rust 代码字符串
code = asyncio.run(async_code_only(5))
```

## 适用场景

### ✅ 适合使用异步模式的场景
1. **UI 应用**: 保持 UI 响应，不阻塞主线程
2. **Web 服务**: 处理多个并发请求
3. **实时应用**: 需要保持实时响应
4. **大规模计算**: 后台执行，不影响其他操作

### ❌ 不适合使用异步模式的场景
1. **简单快速计算**: 同步模式开销更小
2. **批量处理**: 同步模式可能更高效
3. **单次调用**: 异步开销可能不值得

## 性能对比

| 场景 | 同步模式 | 异步模式 |
|------|---------|---------|
| 单次调用 | ✅ 快 | ⚠️ 有额外开销 |
| 多次并发调用 | ❌ 串行 | ✅ 并行 |
| UI 响应性 | ❌ 可能阻塞 | ✅ 保持响应 |
| 实现复杂度 | ✅ 简单 | ⚠️ 需要 asyncio |

## 线程池配置

默认使用 4 个工作线程：

```python
from vools.bridge.rust.decorator import _executor

# 修改线程池大小
_executor._max_workers = 8
```

## 错误处理

异步模式下的错误处理：

```python
@rust(async_mode=True)
async def async_with_error_handling(x: int) -> int:
    return "invalid rust code !!!"

try:
    result = asyncio.run(async_with_error_handling(5))
except Exception as e:
    print(f"Error: {e}")
```

## 测试

运行测试验证异步功能：

```bash
# 运行异步测试
pytest tests/test_rust_async.py -v

# 运行快速测试
python tests/test_rust_async_quick.py
```

## 完整示例

```python
import asyncio
from vools.bridge.rust import rust, is_rust_available

def main():
    """完整示例"""
    if not is_rust_available():
        print("Rust compiler not available")
        return

    # 同步函数
    @rust
    def sync_add(a: int, b: int) -> int:
        return "a + b"

    # 异步函数
    @rust(async_mode=True)
    async def async_mul(a: int, b: int) -> int:
        return "a * b"

    async def workflow():
        # 并行执行多个异步调用
        results = await asyncio.gather(
            async_mul(5, 10),
            async_mul(3, 7),
            async_mul(2, 8)
        )

        # 同步调用
        sync_result = sync_add(10, 5)

        return results, sync_result

    # 运行
    results, sync_result = asyncio.run(workflow())
    print(f"Async results: {results}")  # [50, 21, 16]
    print(f"Sync result: {sync_result}")  # 15

if __name__ == '__main__':
    main()
```

## 相关资源

- [详细文档](./README.md)
- [完整示例](../examples/rust_bridge_example.py)
- [测试代码](../tests/test_rust_async.py)
- [快速测试](../tests/test_rust_async_quick.py)