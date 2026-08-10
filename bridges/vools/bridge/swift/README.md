# Swift Bridge

Swift language bridge for vools.

## Status

- **Decorator:** `@swift`, `@swiftc`
- **LangType:** `COMPILED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated tests

## Usage

### Basic
```python
from vools.bridge.swift import swift

@swift
def my_function(a: int, b: int) -> int:
    return """
    return a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.swift import swift

@swift(async_mode=True)
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

- Swift compiler (`swift`)
- Swift toolchain installed and available in PATH
- On Windows, WSL with Swift installed

## Notes

- Uses `swift` interpreter to run .swift files directly via subprocess
- Parameters passed via JSON on stdin/stdout
- Supports WSL execution on Windows
- `@swiftc` is an alias for `@swift`