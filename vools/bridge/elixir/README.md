# Elixir Bridge

Elixir language bridge for vools.

## Status

- **Decorator:** `@elixir`
- **LangType:** `BEAM`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated test file

## Usage

### Basic
```python
from vools.bridge.elixir import elixir

@elixir
def add(a: int, b: int) -> int:
    return "a + b"

result = add(1, 2)
```

### Async
```python
from vools.bridge.elixir import elixir

@elixir(async_mode=True)
async def fib(n: int) -> int:
    return """
    cond do
      n <= 1 -> 1
      true -> fib(n - 1) + fib(n - 2)
    end
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

- Elixir >= 1.14
- Erlang/OTP (installed automatically with Elixir)
- Download: https://elixir-lang.org/install.html

## Notes

- Compiles via `elixirc` to `.beam` bytecode, executes via `elixir`
- Invoked via subprocess; each call spawns a new `elixir` process
- Results parsed from `io:format("~p~n", [result])` output
- Cache directory: system temp `vools_elixir_cache`
- No fallback mechanism