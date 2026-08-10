# C Bridge

C language bridge for vools.

## Status

- **Decorator:** `CBridge().decorator()` (no top-level `@c` decorator)
- **LangType:** `COMPILED`
- **Async Support:** No
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 35 test functions

## Usage

### Basic
```python
from vools.bridge.c import CBridge

c_bridge = CBridge()

@c_bridge.decorator
def add(a: int, b: int) -> int:
    return "return a + b;"

result = add(1, 2)
```

### With fallback
```python
@c_bridge.decorator(fallback=lambda x: x * x)
def square(x: int) -> int:
    return "return x * x;"
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

- C compiler (GCC, Clang, or MSVC)
- Windows: MinGW-w64 or Visual Studio
- Linux: `sudo apt-get install gcc`
- macOS: `xcode-select --install`

## Notes

- Uses `extern` C function declarations and ctypes for calling
- String parameters are automatically UTF-8 encoded/decoded
- Compiled output is a shared library (.dll/.so/.dylib)
- Cache directory: system temp `vools_c_cache`