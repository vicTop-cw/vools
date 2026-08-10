# Core Bridge Infrastructure

Core infrastructure for the vools bridge framework.

## Status

- **Decorator:** `@bridge_function`, `@bridge_module`, `@bridge_func_name`
- **LangType:** N/A (infrastructure module)
- **Async Support:** N/A
- **Dependencies:** N/A
- **Module Code:** N/A
- **Project Compilation:** N/A
- **Tests:** No dedicated test file

## Usage

### SharedLibrary loading
```python
from vools.bridge.core import SharedLibrary

lib = SharedLibrary("path/to/mylib.dll")
result = lib.add(1, 2)
```

### Type mapping
```python
from vools.bridge.core import CTypeMapper

argtypes = CTypeMapper.infer_arg_types([1, 3.14, "hello"])
# => [c_long, c_double, c_char_p]
```

### Bridge decorators
```python
from vools.bridge.core import bridge_function

@bridge_function("nim", fallback=python_fallback)
def my_func(data: bytes, length: int) -> bytes:
    pass
```

## Modules

| Module | Description |
|--------|-------------|
| `loader.py` | Shared library loading (`SharedLibrary`, `LibraryLoader`) |
| `types.py` | Type mapping (`CTypeMapper`, `CompileMode`, `LangType`) |
| `decorators.py` | Bridge decorators (`@bridge_function`, `@bridge_module`) |
| `serialization.py` | Data serialization (`Serializer`, CSV/JSON) |
| `sigcache.py` | Signature caching |
| `tracker.py` | Compile tracking |

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

## Lang Types

| Type | Description |
|------|-------------|
| COMPILED | Compiled languages (Nim, Rust, C, C++, Go, etc.) |
| INTERPRETED | Interpreted languages (Lua, Python, Shell, etc.) |
| JVM | JVM languages (Java, Scala, Kotlin) |
| DOTNET | .NET languages (C#) |
| BEAM | BEAM VM languages (Erlang, Elixir) |

## Requirements

- Python 3.8+
- ctypes (standard library)

## Notes

- `core` is the infrastructure layer, not a language bridge
- All language bridge modules depend on core for shared library loading, type mapping, and decorators
- Provides the foundational `CompileMode` and `LangType` enumerations