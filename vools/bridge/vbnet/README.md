# VB.NET Bridge

VB.NET language bridge for vools.

## Status

- **Decorator:** `@vbnet`, `@vb`
- **LangType:** `DOTNET`
- **Async Support:** Yes (via `async_mode=True`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 60 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.vbnet import vbnet

@vbnet
def my_function(a: int, b: int) -> int:
    return "Return a + b"

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.vbnet import vbnet

@vbnet(async_mode=True)
async def my_async_function(a: int, b: int) -> int:
    return "Return a + b"

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

- .NET SDK (`dotnet`)
- .NET SDK installed and available in PATH

## Notes

- Compiles to .NET DLL via `dotnet build` and loads via ctypes
- Auto-generates VB.NET code, project files (.vbproj), and class wrappers
- Uses MD5-based code caching for compiled DLLs
- `@vb` is an alias for `@vbnet`
- Includes optional API.tlb COM automation support (Windows only, requires pywin32)