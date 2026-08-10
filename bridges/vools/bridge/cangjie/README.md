# Cangjie Bridge

Cangjie (仓颉) language bridge for vools.

## Status

- **Decorator:** `@cangjie`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 21 test functions

## Usage

### Basic
```python
from vools.bridge.cangjie import cangjie

@cangjie
def add(a: int, b: int) -> int:
    return "return a + b"

result = add(1, 2)
```

### Async
```python
from vools.bridge.cangjie import cangjie

@cangjie(async_mode=True)
async def fib(n: int) -> int:
    return """
    if n <= 1 {
        return 1
    } else {
        return fib(n - 1) + fib(n - 2)
    }
    """

result = await fib(10)
```

## Compile Modes

| Mode | Description |
|------|-------------|
| NORMAL | Standard compilation |
| DEBUG | Debug mode compilation |
| FORCE | Force recompilation |
| ONLY_RUN | Run only, no compilation |
| ONLY_CODE | Generate code only |
| WHEN_CHANGE_JUST | Compile only when source changes |
| WHEN_CHANGE_AND_RUN | Compile and run when source changes |

## Requirements

- Cangjie SDK (cjc compiler)
- Download from: https://cangjie-lang.cn/

## Notes

- Uses C ABI compatible exports for ctypes interaction
- Async mode returns `CjFuture` (supports `await`)
- Batch async execution via `batch_compile_and_run_async`
- Cache directory: system temp `vools_cangjie_cache`