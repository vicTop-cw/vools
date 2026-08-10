# Haskell Bridge

Haskell language bridge for vools.

## Status

- **Decorator:** `@haskell`
- **LangType:** `COMPILED`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated test file

## Usage

### Basic
```python
from vools.bridge.haskell import haskell

@haskell
def add(a: int, b: int) -> int:
    return "a + b"

result = add(1, 2)
```

### Async
```python
from vools.bridge.haskell import haskell

@haskell(async_mode=True)
async def fib(n: int) -> int:
    return """
    if n <= 1 then 1
    else fib (n - 1) + fib (n - 2)
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

- GHC >= 9.0
- Download: https://www.haskell.org/ghc/download.html
- Recommended: GHCup for version management

## Notes

- Compiles via `ghc -O2` to native executable
- Invoked via subprocess with stdin/stdout parameter passing
- Parameters serialized via `read`/`show` (Haskell type classes)
- Compiled executable is cached, not recompiled for same code
- GHC compilation is slow; cache is essential for performance
- Cache directory: system temp `vools_haskell_cache`
- No fallback mechanism