# Java Bridge

Java language bridge for vools.

## Status

- **Decorator:** `@java`, `@java_async`, `@java_module`
- **LangType:** `JVM`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** 12 test functions

## Usage

### Basic
```python
from vools.bridge.java import java

@java
def add(a: int, b: int) -> int:
    return "return a + b;"

result = add(1, 2)
```

### Async
```python
from vools.bridge.java import java

@java(async_mode=True)
async def fib(n: int) -> int:
    return """
    if (n <= 1) {
        return 1;
    }
    return fib(n - 1) + fib(n - 2);
    """

result = await fib(10)
```

### Module decorator
```python
from vools.bridge.java import java_module

@java_module(name='math_ops')
class MathOps:
    def add(a: int, b: int) -> int:
        return "return a + b;"
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

- JDK >= 8 (recommended Java 11+)
- Download: https://adoptium.net/ or https://www.oracle.com/java/
- Optional: Py4J (`pip install py4j`) for gateway mode

## Notes

- Compiles via `javac` to `.class` files, packages as JAR
- Supports both reflection-based invocation and Py4J gateway communication
- Py4J mode keeps JVM running for lower latency on repeated calls
- `@java_module` decorator for batch bridging class methods
- Cache directory: system temp `vools_java_cache`
- `fallback` parameter supports Python fallback