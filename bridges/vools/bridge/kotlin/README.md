# Kotlin Bridge

Kotlin language bridge for vools.

## Status

- **Decorator:** `@kotlin`, `@kt`
- **LangType:** `JVM`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 12 test functions

## Usage

### Basic
```python
from vools.bridge.kotlin import kotlin

@kotlin
def add(x: int, y: int) -> int:
    return "return x + y"

result = add(1, 2)
```

### Async
```python
from vools.bridge.kotlin import kotlin

@kotlin(async_mode=True)
async def fib(n: int) -> int:
    return """
    if (n <= 1) {
        return 1
    }
    return fib(n - 1) + fib(n - 2)
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

- Kotlin compiler (kotlinc) >= 1.5
- Java Runtime (JRE) >= 8
- Download: https://kotlinlang.org/docs/command-line.html

## Notes

- Compiles via `kotlinc` to JAR (JVM bytecode)
- Invoked via subprocess with JSON-serialized arguments over stdin/stdout
- Each call spawns a new `kotlin` process
- `@kt` is an alias for `@kotlin`
- Cache directory: `~/.vools_kotlin_cache/`
- `fallback` parameter supports Python fallback