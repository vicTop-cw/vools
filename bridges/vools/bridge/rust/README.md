# Rust Bridge

Rust language bridge for vools.

## Status

- **Decorator:** `@rust`, `@rust_module`
- **LangType:** `COMPILED`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 46 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.rust import rust

@rust
def my_function(a: int, b: int) -> int:
    return """
    a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.rust import rust

@rust(async_mode=True)
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

- Rust compiler (`rustc`) and Cargo
- Rust toolchain installed and available in PATH

## Notes

- Compiles to shared library (.dll/.so/.dylib) via Cargo and loads via ctypes
- Uses `#[no_mangle]` and `extern "C"` for ABI-compatible exports
- Supports project compilation with Cargo.toml generation
- Full type mapping between Python annotations and Rust types