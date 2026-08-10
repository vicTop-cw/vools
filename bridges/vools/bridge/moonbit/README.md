# MoonBit Bridge

MoonBit language bridge for vools.

## Status

- **Decorator:** `@moonbit`
- **LangType:** `COMPILED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated tests

## Usage

### Basic
```python
from vools.bridge.moonbit import moonbit

@moonbit
def my_function(a: int, b: int) -> int:
    return """
    a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.moonbit import moonbit

@moonbit(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    a + b
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

- MoonBit compiler (`moon`)
- `moon` available in PATH, or WSL on Windows

## Notes

- Uses `moon run` to execute MoonBit code
- Parameters are hardcoded into the main function at call time
- Caching is based on function definition (excluding parameter values) for efficient reuse
- Supports WSL execution on Windows