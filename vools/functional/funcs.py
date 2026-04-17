import time
from typing import Callable
from ..decorators.trd import vic_execute
from ..vools import vicList,vicText

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
    """支持指数退避的重试"""
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


for_ = lambda func, n = 1,p = False : vic_execute(max_workers=n, use_process=p)(func)
foreach = lambda lst,func=print,filter_func=None,filter_first=True: vicList(lst).foreach(func,filter_func,filter_first)
for_p = for_(print)
build = build_text  = lambda x:  vicText(x).build