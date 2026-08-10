# TypeScript Bridge

TypeScript/JavaScript language bridge for vools.

## Status

- **Decorator:** `@ts`, `@typescript`
- **LangType:** `INTERPRETED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 13 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.typescript import ts

@ts
def my_function(a: int, b: int) -> int:
    return """
    return a + b;
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.typescript import ts

@ts(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    return a + b;
    """

result = await my_async_function(1, 2)
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

- Node.js runtime
- TypeScript compiler (`tsc`)
- Both installed and available in PATH

## Notes

- TypeScript is compiled to JavaScript via `tsc`, then executed via Node.js
- Uses JSON over stdin/stdout for data exchange
- Caching is based on MD5 hash of source code
- `@typescript` is an alias for `@ts`
- Suitable for I/O-intensive tasks and Node.js ecosystem integration