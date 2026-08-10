# Shell Bridge

Shell/Bash language bridge for vools.

## Status

- **Decorator:** `@shell`, `@sh`, `@bash`
- **LangType:** `INTERPRETED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 10 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.shell import shell

@shell
def my_function(a: int, b: int) -> int:
    return """
    echo $((a + b))
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.shell import shell

@shell(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    echo $((a + b))
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

- Bash shell (`bash`) or `sh`
- Available on Linux/macOS by default; on Windows via WSL or Git Bash

## Notes

- Shell is an interpreted language; code is executed via subprocess
- Uses JSON serialization for data exchange between Python and Shell
- `@sh` and `@bash` are aliases for `@shell`