# Dart Bridge

Dart language bridge for vools.

## Status

- **Decorator:** `@dart`, `@dartexe`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated test file

## Usage

### Basic
```python
from vools.bridge.dart import dart

@dart
def add(a: int, b: int) -> int:
    return "return a + b"

result = add(1, 2)
```

### Async
```python
from vools.bridge.dart import dart

@dart(async_mode=True)
async def fib(n: int) -> int:
    return """
    if (n <= 1) return 1;
    return fib(n - 1) + fib(n - 2);
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

- Dart SDK >= 2.12.0
- Download: https://dart.dev/get-dart

## Notes

- Compiles via `dart compile exe` to native executable
- Invoked via subprocess with JSON-serialized arguments over stdin/stdout
- Each call spawns a new process; suitable for low-frequency calls
- Cache directory: system temp `vools_dart_cache`
- `@dartexe` is an alias for `@dart`