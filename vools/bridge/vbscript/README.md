# VBScript Bridge

VBScript language bridge for vools.

## Status

- **Decorator:** `@vbscript`, `@vbs`
- **LangType:** `INTERPRETED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 12 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.vbscript import vbscript

@vbscript
def my_function(a: int, b: int) -> int:
    return """
    my_function = a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.vbscript import vbscript

@vbscript(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    my_async_function = a + b
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

- Windows operating system
- `cscript.exe` (Windows Script Host, built-in on Windows)

## Notes

- VBScript is Windows-only; code is executed via `cscript.exe`
- Uses JSON serialization for data exchange between Python and VBScript
- `@vbs` is an alias for `@vbscript`