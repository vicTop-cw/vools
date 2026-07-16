# C# Bridge

C# language bridge for vools.

## Status

- **Decorator:** `@csharp`, `@cs`
- **LangType:** `DOTNET`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 14 test functions

## Usage

### Basic
```python
from vools.bridge.csharp import csharp

@csharp
def add(a: int, b: int) -> int:
    return "return a + b;"

result = add(1, 2)
```

### Async
```python
from vools.bridge.csharp import csharp

@csharp(async_mode=True)
async def compute(x: int) -> int:
    return "return x * x;"

result = await compute(5)
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

- .NET SDK >= 6.0 (recommended .NET 9)
- Download: https://dotnet.microsoft.com/download

## Notes

- Uses `dotnet publish` with NativeAOT for native DLL compilation
- Method must be declared as `public static`
- Parameters passed via ctypes, not JSON serialization
- Cache directory: system temp `vools_csharp_cache`