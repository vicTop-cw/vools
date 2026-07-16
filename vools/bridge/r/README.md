# R Bridge

R language bridge for vools.

## Status

- **Decorator:** `@r`, `@r_module`
- **LangType:** `INTERPRETED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 31 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.r import r

@r
def my_function(a: int, b: int) -> int:
    return """
    return(a + b)
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.r import r

@r(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    return(a + b)
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

- R interpreter and Rscript
- `jsonlite` package recommended (`install.packages("jsonlite")`)
- On Windows, WSL 2 with R installed

## Notes

- R is an interpreted language; code is executed via subprocess
- Uses JSON-based inter-process data exchange
- Windows execution uses WSL to call Rscript
- `@r_module` supports module-level R code