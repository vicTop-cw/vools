# Erlang Bridge

Erlang language bridge for vools.

## Status

- **Decorator:** `@erlang`
- **LangType:** `BEAM`
- **Async Support:** Yes
- **Dependencies:** Yes
- **Module Code:** Yes
- **Project Compilation:** Yes
- **Tests:** No dedicated test file

## Usage

### Basic
```python
from vools.bridge.erlang import erlang

@erlang
def add(a: int, b: int) -> int:
    return "A + B."

result = add(1, 2)
```

### Async
```python
from vools.bridge.erlang import erlang

@erlang(async_mode=True)
async def fib(n: int) -> int:
    return """
    if N =< 1 -> 1;
       true -> fib(N-1) + fib(N-2)
    end.
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

- Erlang/OTP >= 25
- Download: https://www.erlang.org/downloads

## Notes

- Compiles via `erlc` to `.beam` bytecode, executes via `erl -noshell -eval`
- Invoked via subprocess; each call spawns a new `erl` process
- Variables must start with uppercase (lowercase is atom)
- Statements end with `.` (dot)
- Results parsed from `io:format("~p~n", [result])` output
- Cache directory: system temp `vools_erlang_cache`
- No fallback mechanism