# C++ Bridge

C++ language bridge for vools.

## Status

- **Decorator:** `@cpp`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated test file

## Usage

### Basic
```python
from vools.bridge.cpp import cpp

@cpp
def add(a: int, b: int) -> int:
    return "return a + b;"

result = add(1, 2)
```

### Async
```python
from vools.bridge.cpp import cpp

@cpp(async_mode=True)
async def fib(n: int) -> int:
    return """
    if (n <= 1) return 1;
    return fib(n - 1) + fib(n - 2);
    """

result = await fib(20)
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

- C++ compiler (GCC, Clang, or MSVC)
- Windows: MinGW-w64, Clang, or Visual Studio
- Linux: `sudo apt-get install g++`
- macOS: `xcode-select --install`

## Notes

- All exported functions use `extern "C"` to avoid name mangling
- Supports STL headers via `includes` parameter
- Cache directory: system temp `vools_cpp_cache`
- `fallback` parameter supports Python fallback on compiler failure