# Go Bridge

Go language bridge for vools.

## Status

- **Decorator:** `@go`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 36 test functions

## Usage

### Basic
```python
from vools.bridge.go import go

@go
def add(a: int, b: int) -> int:
    return "return int64(a) + int64(b)"

result = add(1, 2)
```

### Async
```python
from vools.bridge.go import go

@go(async_mode=True)
async def fib(n: int) -> int:
    return """
    if int64(n) <= 1 { return 1 }
    return int64(fib(n-1) + fib(n-2))
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

- Go >= 1.18
- Download: https://go.dev/dl/

## Notes

- Compiles to c-shared library via `go build -buildmode=c-shared`
- Uses cgo for C ABI exports (`//export` directives)
- List/bytes parameters are passed as (unsafe.Pointer, length) for zero-copy
- Async mode returns `GoFuture` (supports `await` and `asyncio.gather`)
- ctypes calls release GIL, enabling true parallel execution
- Cache directory: system temp `vools_go_cache`
- `fallback` parameter supports Python fallback