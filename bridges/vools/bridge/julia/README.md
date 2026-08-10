# Julia Bridge

Julia language bridge for vools.

## Status

- **Decorator:** `@julia`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 56 test functions

## Usage

### Basic
```python
from vools.bridge.julia import julia

@julia
def add(a: int, b: int) -> int:
    return "return a + b"

result = add(1, 2)
```

### Async
```python
from vools.bridge.julia import julia

@julia(async_mode=True)
async def fib(n: int) -> int:
    return """
    if n <= 1
        return 1
    end
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

- Julia >= 1.6
- Download: https://julialang.org/downloads/
- Optional: StaticCompiler.jl for shared library compilation

## Notes

- Primary mode: subprocess invocation via `julia` command
- Optional: StaticCompiler.jl for compiling to shared library with ctypes loading
- Arrays are 1-indexed in Julia (not 0-indexed)
- String concatenation uses `*` operator (not `+`)
- JIT compilation on first call; subsequent calls within same process are fast
- Cache directory: system temp `vools_julia_cache`
- No fallback mechanism