# Scala Bridge

Scala language bridge for vools.

## Status

- **Decorator:** `@scala`, `@scala_async`
- **LangType:** `JVM`
- **Async Support:** Yes (via `@scala_async`)
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 12 passed, 0 skipped

## Usage

### Basic
```python
from vools.bridge.scala import scala

@scala
def my_function(a: int, b: int) -> int:
    return """
    a + b
    """

result = my_function(1, 2)
```

### Async
```python
from vools.bridge.scala import scala_async

@scala_async
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

- `scala-cli` (recommended) or `scalac` + `scala-library`
- Java Runtime (JVM)
- Scala toolchain installed and available in PATH

## Notes

- Uses Py4J for Python-to-Scala cross-language calls via JVM Gateway
- Compiles to JAR files via scala-cli or scalac
- `@scala_async` provides native async decorator
- Additional decorators: `@scala_gateway`, `@scala_static_bridge`, `@bridge_scala_class`