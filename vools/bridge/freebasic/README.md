# FreeBASIC Bridge

FreeBASIC language bridge for vools.

## Status

- **Decorator:** `@freebasic`, `@fbc`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 14 test functions

## Usage

### Basic
```python
from vools.bridge.freebasic import freebasic

@freebasic
def add(a: int, b: int) -> int:
    return "Return a + b"

result = add(1, 2)
```

### Async
```python
from vools.bridge.freebasic import freebasic

@freebasic(async_mode=True)
async def fib(n: int) -> int:
    return """
    If n <= 1 Then
        Return 1
    Else
        Return fib(n - 1) + fib(n - 2)
    End If
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

- FreeBASIC compiler (fbc) — bundled with module (fbc32.exe / fbc64.exe)
- No external installation required

## Notes

- Built-in 32/64-bit FreeBASIC compiler included
- Uses `Export` keyword for C ABI compatible function exports
- List parameters are passed as (pointer, length) for zero-copy
- Built-in third-party DLL libraries: SQLite3, Cairo, SDL3, etc.
- Supports `.bas` wrapper modules for simplified DLL access
- Cache directory: system temp `vools_fbc_cache`
- `fallback` parameter supports Python fallback