# Ruby Bridge

Ruby language bridge for vools.

## Status

- **Decorator:** `@ruby`
- **LangType:** `INTERPRETED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 12 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.ruby import ruby

@ruby
def my_function(a: int, b: int) -> int:
    return """
    a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.ruby import ruby

@ruby(async_mode=True)
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

- Ruby interpreter (>= 2.0)
- Ruby installed and available in PATH

## Notes

- Ruby is an interpreted language; code is executed via subprocess
- Uses JSON serialization for data exchange between Python and Ruby