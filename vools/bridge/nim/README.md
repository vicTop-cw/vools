# Nim Bridge

Nim language bridge for vools.

## Status

- **Decorator:** `@nim`
- **LangType:** `COMPILED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated tests

## Usage

### Basic
```python
from vools.bridge.nim import nim

@nim
def my_function(a: int, b: int) -> int:
    return "a + b"

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.nim import nim

@nim(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return "a + b"

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

- Nim compiler (`nim`)
- Nim installed and available in PATH

## Notes

- Compiles to shared library (.dll/.so) and loads via ctypes
- Uses C-compatible types (cint, cdouble, cbool, cstring) for ABI compatibility
- Functions are exported with `{.exportc.}` pragma
- Includes pre-built optimized modules for crypto, sequences, datetime, and encoding operations