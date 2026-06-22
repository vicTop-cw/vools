import time
from typing import Callable, Any, Iterable, Optional, List, Union
from ..decorators.trd import vic_execute

__all__ = [
    "waiter",
    "for_",
    "foreach",
    "for_p",
    "build",
    "build_text"
]


def waiter(
    checker: Callable[[], bool],
    retry_time: int,
    max_try_times: int,
    backoff_factor: float = 1.0
) -> None:
    """支持指数退避的重试机制。

    持续检查条件是否满足，若不满足则等待后重试，等待时间按指数退避增长。

    Args:
        checker: 条件检查函数，返回 True 表示条件满足
        retry_time: 基础重试等待时间（秒）
        max_try_times: 最大重试次数
        backoff_factor: 退避因子（默认 1.0），每次重试等待时间为 retry_time * (backoff_factor ** (attempt - 1))

    Raises:
        ValueError: 当 max_try_times 小于 1 时抛出
        TimeoutError: 当达到最大重试次数条件仍未满足时抛出
    """
    if max_try_times < 1:
        raise ValueError("max_try_times must be at least 1")

    for attempt in range(1, max_try_times + 1):
        if checker():
            return
        else:
            delay = retry_time * (backoff_factor ** (attempt - 1))
            print(f"Attempt {attempt}: waiting for {delay} seconds")
            time.sleep(delay)

    raise TimeoutError(f"Timeout after {max_try_times} attempts")


def for_(
    func: Callable[..., Any],
    n: int = 1,
    p: bool = False
) -> Callable[..., Any]:
    """将函数包装为支持并发执行的函数。

    Args:
        func: 要包装的函数
        n: 最大并发工作线程数（默认 1）
        p: 是否使用进程而非线程（默认 False）

    Returns:
        包装后的函数
    """
    return vic_execute(max_workers=n, use_process=p)(func)


def foreach(
    lst: Iterable[Any],
    func: Callable[..., Any] = print,
    filter_func: Optional[Union[Callable[[Any], bool], str]] = None,
    filter_first: bool = True
) -> Any:
    """遍历列表并对每个元素执行函数（LINQ 风格）。

    Args:
        lst: 要遍历的可迭代对象
        func: 要执行的函数（默认 print）
        filter_func: 可选的过滤函数或表达式字符串
        filter_first: 是否先过滤再应用函数（默认 True）

    Returns:
        处理后的结果
    """
    from ..data.vlist import VList as vicList
    return vicList(lst).foreach(func, filter_func, filter_first)


for_p: Callable[..., Any] = for_(print)
"""for_p 是 for_(print) 的别名，用于直接打印结果。"""


def build(x: Any) -> Any:
    """将值转换为 VText 并执行 build 操作。

    Args:
        x: 要转换的值

    Returns:
        VText build 操作的结果
    """
    from ..data.vtext import VText as vicText
    return vicText(x).build


build_text = build
"""build_text 是 build 的别名。"""