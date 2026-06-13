"""
vools-reactive - 响应式编程框架

基于 vools 生态深度集成的响应式编程库，提供以下特性：

核心功能:
- Observable: 响应式数据流基础
- Subject: 多播数据流
- Operators: 丰富的操作符集合
- Schedulers: 灵活的调度器

创新特性:
- 与 vools curry, placeholder, pipe_ops 的深度集成
- 支持字符串表达式作为操作符参数
- 统一的同步/异步 API
- 智能背压处理
- 完善的错误恢复机制

示例:
    >>> from vools.reactive import Observable, ops
    >>> 
    >>> # 基础使用
    >>> obs = Observable.from_iterable([1, 2, 3])
    >>> obs.subscribe(on_next=print)
    1
    2
    3
    
    >>> # 使用管道操作
    >>> obs.pipe(
    ...     ops.filter(lambda x: x > 1),
    ...     ops.map(lambda x: x * 2)
    ... ).subscribe(on_next=print)
    4
    6
    
    >>> # 使用 placeholder 表达式
    >>> obs.pipe(
    ...     ops.filter("_ > 1"),
    ...     ops.map("x * 2")
    ... ).subscribe(on_next=print)
    4
    6
    
    >>> # 使用 >> 管道操作符
    >>> obs >> ops.filter(lambda x: x > 1) >> ops.map(lambda x: x * 2)
"""

import sys
from . import operators as ops_module
sys.modules['vools.reactive.ops'] = ops_module
ops = ops_module

from .observable import (
    Observable,
    Observer,
    Subscription,
    DefaultObserver
)

from .operators import (
    # 基础操作符
    map,
    filter,
    flat_map,
    concat_map,
    switch_map,
    concat,
    merge,
    zip,
    combine_latest,
    with_latest_from,
    take,
    skip,
    take_while,
    skip_while,
    take_until,
    skip_until,
    distinct,
    distinct_until_changed,
    first,
    last,
    element_at,
    
    # 时间相关
    debounce,
    throttle_first,
    throttle_latest,
    timeout,
    timestamp,
    
    # 错误处理
    catch,
    retry,
    on_error_return,
    on_error_resume_next,
    retry_when,
    
    # 聚合
    reduce,
    scan,
    count,
    sum,
    average,
    minimum,
    maximum,
    all,
    any,
    contains,
    is_empty,
    default_if_empty,
    sequence_equal,
    to_map,
    to_set,
    
    # 转换
    to_list,
    buffer,
    
    # 工具
    tap,
    delay,
    start_with,
    end_with,
    
    # vools 集成
    curry_map,
    lazy_flat_map,
    seq_bridge,
    iif,
    
    # Do 操作符
    do_on_next,
    do_on_error,
    do_on_completed,
    
    # 高级
    observe_on,
    subscribe_on,
    sample,
    skip_last,
    take_last,
    ignore_elements,
    time_interval,
    flat_map_latest,
    window,
    amb,
    switch,
    
    # Backpressure
    backpressure_buffer,
    backpressure_drop,
    backpressure_error,
    backpressure_latest,
    
    # 创新功能
    retry_with_backoff,
    circuit_breaker,
    debounce_evolution,
    cache,
    parallel,
)

from .extended_operators import (
    # Creating
    from_range,
    from_callable,
    from_future,
    start,
)

from .stats_operators import (
    # 统计聚合算子
    median,
    variance,
    std,
    quantile,
    arg_min,
    arg_max,
    n_unique,
    
    # 滚动窗口算子
    rolling_sum,
    rolling_min,
    rolling_max,
    rolling_mean,
    
    # 累积变换算子
    cum_sum,
    cum_min,
    cum_max,
    cum_mean,
    cum_prod,
    
    # 排序 Top-N 算子
    sort,
    top_k,
    bottom_k,
    
    # None 值处理与数学工具
    drop_none,
    fill_none,
    abs_op as abs,
    clamp,
    
    # 嵌套流展开算子
    explode,
    flatten,
)

from .connectable import (
    # Connectable Observable
    ConnectableObservable,
    publish,
    share,
    replay,
    publish_replay,
    auto_connect,
)

from .subject import (
    Subject,
    BehaviorSubject,
    ReplaySubject,
    AsyncSubject,
    PublishSubject,
    
    # 工厂函数
    subject,
    behavior_subject,
    replay_subject,
    async_subject,
    publish_subject,
)

from .schedulers import (
    Scheduler,
    ImmediateScheduler,
    CurrentThreadScheduler,
    AsyncIOScheduler,
    ThreadPoolScheduler,
    NewThreadScheduler,
    
    # 全局实例
    immediate,
    current_thread,
    asyncio_scheduler,
    
    # 工厂函数
    immediate_scheduler,
    current_thread_scheduler,
    asyncio_scheduler as create_asyncio_scheduler,
    thread_pool_scheduler,
    new_thread_scheduler
)

__all__ = [
    # Observable
    'Observable',
    'Observer',
    'Subscription',
    'DefaultObserver',
    
    # Observable Factory Methods
    'from_range',
    'from_callable',
    'from_future',
    'start',
    
    # Operators
    'map',
    'filter',
    'flat_map',
    'concat_map',
    'switch_map',
    'concat',
    'merge',
    'zip',
    'combine_latest',
    'with_latest_from',
    'take',
    'skip',
    'take_while',
    'skip_while',
    'take_until',
    'skip_until',
    'distinct',
    'distinct_until_changed',
    'first',
    'last',
    'element_at',
    'debounce',
    'throttle_first',
    'throttle_latest',
    'timeout',
    'timestamp',
    'catch',
    'retry',
    'on_error_return',
    'on_error_resume_next',
    'retry_when',
    'reduce',
    'scan',
    'count',
    'sum',
    'average',
    'minimum',
    'maximum',
    'all',
    'any',
    'contains',
    'is_empty',
    'default_if_empty',
    'sequence_equal',
    'to_map',
    'to_set',
    'to_list',
    'buffer',
    'tap',
    'delay',
    'start_with',
    'end_with',
    'curry_map',
    'lazy_flat_map',
    'seq_bridge',
    'iif',
    
    # Do Operators
    'do_on_next',
    'do_on_error',
    'do_on_completed',
    
    # Advanced Operators
    'observe_on',
    'subscribe_on',
    'sample',
    'skip_last',
    'take_last',
    'ignore_elements',
    'time_interval',
    'flat_map_latest',
    'window',
    'amb',
    'switch',
    
    # Backpressure
    'backpressure_buffer',
    'backpressure_drop',
    'backpressure_error',
    'backpressure_latest',
    
    # Innovation Features
    'retry_with_backoff',
    'circuit_breaker',
    'debounce_evolution',
    'cache',
    'parallel',
    
    # Connectable Observable
    'ConnectableObservable',
    'publish',
    'share',
    'replay',
    'publish_replay',
    'auto_connect',
    
    # Subject
    'Subject',
    'BehaviorSubject',
    'ReplaySubject',
    'AsyncSubject',
    'PublishSubject',
    'subject',
    'behavior_subject',
    'replay_subject',
    'async_subject',
    'publish_subject',
    
    # Schedulers
    'Scheduler',
    'ImmediateScheduler',
    'CurrentThreadScheduler',
    'AsyncIOScheduler',
    'ThreadPoolScheduler',
    'NewThreadScheduler',
    'immediate',
    'current_thread',
    'asyncio_scheduler',
    'immediate_scheduler',
    'current_thread_scheduler',
    'create_asyncio_scheduler',
    'thread_pool_scheduler',
    'new_thread_scheduler',
    
    # 统计聚合算子
    'median',
    'variance',
    'std',
    'quantile',
    'arg_min',
    'arg_max',
    'n_unique',
    
    # 滚动窗口算子
    'rolling_sum',
    'rolling_min',
    'rolling_max',
    'rolling_mean',
    
    # 累积变换算子
    'cum_sum',
    'cum_min',
    'cum_max',
    'cum_mean',
    'cum_prod',
    
    # 排序 Top-N 算子
    'sort',
    'top_k',
    'bottom_k',
    
    # None 值处理与数学工具
    'drop_none',
    'fill_none',
    'abs',
    'clamp',
    
    # 嵌套流展开算子
    'explode',
    'flatten',
]
