# Mojo Bridge

Mojo language bridge for vools.

## Status

- **Decorator:** `@mojo`
- **LangType:** `COMPILED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 37 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.mojo import mojo

@mojo
def my_function(a: int, b: int) -> int:
    return """
    return a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.mojo import mojo

@mojo(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    return a + b
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

- Mojo 1.0b1 (Modular)
- Linux/macOS natively, or WSL on Windows
- Mojo compiler (`mojo`) available in PATH

## Notes

- Compiles to shared library (.so) and loads via ctypes
- Serialization-free interaction: list parameters use UnsafePointer + length
- Windows requires WSL for compilation; compiled .so runs via WSL Python
- Supports both native Linux/macOS and WSL-based execution