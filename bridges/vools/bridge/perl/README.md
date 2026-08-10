# Perl Bridge

Perl language bridge for vools.

## Status

- **Decorator:** `@perl`, `@pl`
- **LangType:** `INTERPRETED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 12 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.perl import perl

@perl
def my_function(a: int, b: int) -> int:
    return """
    return $a + $b;
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.perl import perl

@perl(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return """
    return $a + $b;
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

- Perl interpreter (`perl`)
- Perl installed and available in PATH

## Notes

- Perl is an interpreted language; code is executed via subprocess
- Uses JSON serialization for data exchange between Python and Perl
- `@pl` is an alias for `@perl`