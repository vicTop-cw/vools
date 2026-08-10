"""
vools-reactive 统计聚合扩展算子

提供统计聚合、滚动窗口、累积变换等数据分析操作符
"""

from typing import TypeVar, Callable, Optional, Any, List, Tuple, Union, Iterable, Dict, Set
import statistics
import heapq
import operator as op
from collections import deque

from ..core.observable import Observable, Observer, Subscription
__all__ = ['T', 'R', 'median', 'variance', 'std', 'quantile', 'arg_min', 'arg_max', 'n_unique', 'rolling_sum', 'rolling_min', 'rolling_max', 'rolling_mean', 'cum_sum', 'cum_min', 'cum_max', 'cum_mean', 'cum_prod', 'sort', 'top_k', 'bottom_k', 'drop_none', 'fill_none', 'abs_op', 'clamp', 'explode', 'flatten']

T = TypeVar('T')
R = TypeVar('R')


# ========== 统计聚合算子 ==========

def median() -> Callable[[Observable[T]], Observable[float]]:
    """计算中位数
    
    注：需缓冲全部值，仅有限流适用
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            values = []
            
            def on_next(value: T) -> None:
                values.append(value)
            
            def on_completed():
                if values:
                    observer.on_next(statistics.median(values))
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def variance(ddof: int = 0) -> Callable[[Observable[T]], Observable[float]]:
    """计算方差
    
    注：需缓冲全部值，仅有限流适用
    
    Args:
        ddof: Delta Degrees of Freedom
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            values = []
            
            def on_next(value: T) -> None:
                values.append(value)
            
            def on_completed():
                n = len(values)
                if n > ddof:
                    mean = sum(values) / n
                    variance = sum((x - mean) ** 2 for x in values) / (n - ddof)
                    observer.on_next(variance)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def std(ddof: int = 0) -> Callable[[Observable[T]], Observable[float]]:
    """计算标准差
    
    注：需缓冲全部值，仅有限流适用
    
    Args:
        ddof: Delta Degrees of Freedom
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            values = []
            
            def on_next(value: T) -> None:
                values.append(value)
            
            def on_completed():
                n = len(values)
                if n > ddof:
                    mean = sum(values) / n
                    variance = sum((x - mean) ** 2 for x in values) / (n - ddof)
                    observer.on_next(variance ** 0.5)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def quantile(q: float) -> Callable[[Observable[T]], Observable[float]]:
    """计算分位数
    
    注：需缓冲全部值，仅有限流适用
    
    Args:
        q: 分位数值，范围 [0, 1]
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            values = []
            
            def on_next(value: T) -> None:
                values.append(value)
            
            def on_completed():
                if values:
                    sorted_vals = sorted(values)
                    n = len(sorted_vals)
                    index = q * (n - 1)
                    if index.is_integer():
                        result = sorted_vals[int(index)]
                    else:
                        lower = sorted_vals[int(index)]
                        upper = sorted_vals[int(index) + 1]
                        result = lower + (upper - lower) * (index - int(index))
                    observer.on_next(result)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def arg_min() -> Callable[[Observable[T]], Observable[int]]:
    """返回最小值的索引
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[int]:
        def subscribe(observer: Observer[int]) -> Subscription:
            min_value = None
            min_index = -1
            current_index = 0
            is_empty = True
            
            def on_next(value: T) -> None:
                nonlocal min_value, min_index, current_index, is_empty
                try:
                    if is_empty or value < min_value:
                        min_value = value
                        min_index = current_index
                    is_empty = False
                    current_index += 1
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed():
                if not is_empty:
                    observer.on_next(min_index)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def arg_max() -> Callable[[Observable[T]], Observable[int]]:
    """返回最大值的索引
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[int]:
        def subscribe(observer: Observer[int]) -> Subscription:
            max_value = None
            max_index = -1
            current_index = 0
            is_empty = True
            
            def on_next(value: T) -> None:
                nonlocal max_value, max_index, current_index, is_empty
                try:
                    if is_empty or value > max_value:
                        max_value = value
                        max_index = current_index
                    is_empty = False
                    current_index += 1
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed():
                if not is_empty:
                    observer.on_next(max_index)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def n_unique() -> Callable[[Observable[T]], Observable[int]]:
    """计算不重复值的数量
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[int]:
        def subscribe(observer: Observer[int]) -> Subscription:
            seen = set()
            
            def on_next(value: T) -> None:
                seen.add(value)
            
            def on_completed():
                observer.on_next(len(seen))
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== 滚动窗口算子 ==========

def rolling_sum(window_size: int) -> Callable[[Observable[T]], Observable[T]]:
    """滚动求和
    
    Args:
        window_size: 窗口大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            window = deque(maxlen=window_size)
            current_sum = 0
            
            def on_next(value: T) -> None:
                nonlocal current_sum
                window.append(value)
                current_sum += value
                if len(window) > window_size:
                    current_sum -= window[0]
                observer.on_next(sum(window))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def rolling_min(window_size: int) -> Callable[[Observable[T]], Observable[T]]:
    """滚动最小值
    
    Args:
        window_size: 窗口大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            window = deque(maxlen=window_size)
            
            def on_next(value: T) -> None:
                window.append(value)
                observer.on_next(min(window))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def rolling_max(window_size: int) -> Callable[[Observable[T]], Observable[T]]:
    """滚动最大值
    
    Args:
        window_size: 窗口大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            window = deque(maxlen=window_size)
            
            def on_next(value: T) -> None:
                window.append(value)
                observer.on_next(max(window))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def rolling_mean(window_size: int) -> Callable[[Observable[T]], Observable[float]]:
    """滚动均值
    
    Args:
        window_size: 窗口大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            window = deque(maxlen=window_size)
            
            def on_next(value: T) -> None:
                window.append(value)
                observer.on_next(sum(window) / len(window))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== 累积变换算子 ==========

def cum_sum() -> Callable[[Observable[T]], Observable[T]]:
    """累积求和
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            total = 0
            
            def on_next(value: T) -> None:
                nonlocal total
                total += value
                observer.on_next(total)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def cum_min() -> Callable[[Observable[T]], Observable[T]]:
    """累积最小值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            current_min = None
            is_first = True
            
            def on_next(value: T) -> None:
                nonlocal current_min, is_first
                if is_first:
                    current_min = value
                    is_first = False
                else:
                    current_min = min(current_min, value)
                observer.on_next(current_min)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def cum_max() -> Callable[[Observable[T]], Observable[T]]:
    """累积最大值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            current_max = None
            is_first = True
            
            def on_next(value: T) -> None:
                nonlocal current_max, is_first
                if is_first:
                    current_max = value
                    is_first = False
                else:
                    current_max = max(current_max, value)
                observer.on_next(current_max)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def cum_mean() -> Callable[[Observable[T]], Observable[float]]:
    """累积均值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            total = 0.0
            count = 0
            
            def on_next(value: T) -> None:
                nonlocal total, count
                total += value
                count += 1
                observer.on_next(total / count)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def cum_prod() -> Callable[[Observable[T]], Observable[T]]:
    """累积乘积
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            product = 1
            
            def on_next(value: T) -> None:
                nonlocal product
                product *= value
                observer.on_next(product)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== 排序 Top-N 算子 ==========

def sort(key_fn: Optional[Callable[[T], Any]] = None, reverse: bool = False) -> Callable[[Observable[T]], Observable[T]]:
    """排序后依次发射
    
    注：需缓冲全部值，仅有限流适用
    
    Args:
        key_fn: 排序键函数
        reverse: 是否降序
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            values = []
            
            def on_next(value: T) -> None:
                values.append(value)
            
            def on_completed():
                values.sort(key=key_fn, reverse=reverse)
                for val in values:
                    observer.on_next(val)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def top_k(k: int, key_fn: Optional[Callable[[T], Any]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """获取最大的 k 个值
    
    Args:
        k: 数量
        key_fn: 排序键函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            heap = []
            
            def on_next(value: T) -> None:
                key = key_fn(value) if key_fn else value
                if len(heap) < k:
                    heapq.heappush(heap, (key, value))
                else:
                    if key > heap[0][0]:
                        heapq.heappop(heap)
                        heapq.heappush(heap, (key, value))
            
            def on_completed():
                result = [item[1] for item in sorted(heap, key=lambda x: x[0], reverse=True)]
                for val in result:
                    observer.on_next(val)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def bottom_k(k: int, key_fn: Optional[Callable[[T], Any]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """获取最小的 k 个值
    
    Args:
        k: 数量
        key_fn: 排序键函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            heap = []
            
            def on_next(value: T) -> None:
                key = key_fn(value) if key_fn else value
                if len(heap) < k:
                    heapq.heappush(heap, (-key, value))
                else:
                    if key < -heap[0][0]:
                        heapq.heappop(heap)
                        heapq.heappush(heap, (-key, value))
            
            def on_completed():
                result = [item[1] for item in sorted(heap, key=lambda x: -x[0])]
                for val in result:
                    observer.on_next(val)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== None 值处理与数学工具 ==========

def drop_none() -> Callable[[Observable[Optional[T]]], Observable[T]]:
    """过滤 None 值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[Optional[T]]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: Optional[T]) -> None:
                if value is not None:
                    observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def fill_none(default_value: T) -> Callable[[Observable[Optional[T]]], Observable[T]]:
    """替换 None 值
    
    Args:
        default_value: 默认值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[Optional[T]]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: Optional[T]) -> None:
                observer.on_next(value if value is not None else default_value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def abs_op() -> Callable[[Observable[Union[int, float]]], Observable[float]]:
    """绝对值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[Union[int, float]]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            def on_next(value: Union[int, float]) -> None:
                observer.on_next(op.abs(value))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def clamp(min_val: float, max_val: float) -> Callable[[Observable[Union[int, float]]], Observable[float]]:
    """值域限制
    
    Args:
        min_val: 最小值
        max_val: 最大值
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[Union[int, float]]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            def on_next(value: Union[int, float]) -> None:
                observer.on_next(max(min_val, min(max_val, value)))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== 嵌套流展开算子 ==========

def explode() -> Callable[[Observable[Iterable[T]]], Observable[T]]:
    """展开 Iterable（排除 str/bytes）
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[Iterable[T]]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: Iterable[T]) -> None:
                if isinstance(value, (str, bytes)):
                    observer.on_next(value)
                else:
                    for item in value:
                        observer.on_next(item)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def flatten() -> Callable[[Observable[Iterable[T]]], Observable[T]]:
    """展开 Iterable（与 explode 同语义）
    
    Returns:
        操作符函数
    """
    return explode()