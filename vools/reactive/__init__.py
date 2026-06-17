"""
vools-reactive - 响应式编程框架
"""

import sys
from . import operators as ops_module
sys.modules['vools.reactive.ops'] = ops_module
ops = ops_module

from .core import schedulers

from .core.observable import Observable, Observer, Subscription, DefaultObserver

def of(*values):
    return Observable.of(*values)

def from_iterable(iterable):
    return Observable.from_iterable(iterable)
from .core.subject import (
    Subject, BehaviorSubject, ReplaySubject, AsyncSubject, PublishSubject,
    subject, behavior_subject, replay_subject, async_subject, publish_subject
)
from .core.schedulers import (
    Scheduler, ImmediateScheduler, CurrentThreadScheduler, AsyncIOScheduler,
    ThreadPoolScheduler, NewThreadScheduler,
    immediate, current_thread, asyncio_scheduler,
    immediate_scheduler, current_thread_scheduler,
    thread_pool_scheduler, new_thread_scheduler
)
from .core.connectable import (
    ConnectableObservable, publish, share, replay, publish_replay, auto_connect
)

from .core.object_pool import ObjectPool, get_pool, pooled_acquire, pooled_release, clear_all_pools

from .operators.operators import (
    map, filter, flat_map, concat_map, switch_map,
    take, skip, take_while, skip_while, take_until,
    distinct_until_changed, debounce, throttle_first,
    tap, delay, start_with, end_with,
    reduce, scan, count, sum, average, minimum, maximum,
    all, any, contains, is_empty,
    to_list, buffer, group_by, merge, concat,
    catch, retry, on_error_return, on_error_resume_next, retry_when,
    first, last, distinct, element_at, skip_until,
    default_if_empty, sequence_equal, timeout, timestamp, iif,
    dispatch_to_workers, dispatch_workers, amb,
    backpressure_buffer, backpressure_drop, backpressure_error, backpressure_latest,
    buffer_until_idle, buffer_with_count, cache, circuit_breaker,
    collect_until, combine_latest, zip, count_events,
    curry_map, debounce_data, debounce_events, debounce_evolution,
    distinct_until_changed_by, distinct_values,
    do_on_completed, do_on_error, do_on_next, finally_with_data,
    filter_by, filter_by_data, filter_by_event_type,
    flat_map_latest, group_by_event_type, ignore_elements,
    lazy_flat_map, observe_on,
    on_condition_met, on_data, on_every_nth, on_next_data,
    on_start, on_stop,
    parallel, rate_limit,
    retry_with_backoff,
    sample, sample_first, seq_bridge,
    skip_last, skip_n_events, skip_until_data,
    subscribe_on, switch,
    take_last, take_n_events, take_until_data,
    throttle_events, throttle_latest, throttle_with_trailing,
    time_interval, to_map, to_set,
    when, when_error, when_start, when_stop,
    window, with_latest_from, with_state,
)

from .operators.extended_operators import (
    from_range, from_callable, from_future, start,
)

from .operators.stats_operators import (
    median, variance, std, quantile,
    arg_min, arg_max, n_unique,
    rolling_sum, rolling_min, rolling_max, rolling_mean,
    cum_sum, cum_min, cum_max, cum_mean, cum_prod,
    sort, top_k, bottom_k,
    drop_none, fill_none, abs_op as abs,
    clamp, explode, flatten,
)

from .monitoring.clipboard import (
    ClipChangeType, ClipData,
    ClipboardDispatcher, ClipSubject, ClipObserver,
    from_clipboard, write_to_clipboard,
)

from .monitoring.file_watcher import (
    FileChangeType, FileData,
    FileSubject, FileObserver, FileDispatcher,
    from_filesystem, write_to_filesystem,
)

from .monitoring.folder_watcher import (
    FolderChangeType, FolderData,
    FolderSubject, FolderObserver, FolderDispatcher,
    from_foldersystem, write_to_foldersystem,
)

from .monitoring.keyboard import (
    KeyEventType, KeyModifier, KeyData,
    KeyboardDispatcher, KeySubject, KeyObserver,
    from_keyboard, write_to_keyboard,
)

from .monitoring.mouse import (
    MouseEventType, MouseData,
    MouseDispatcher, MouseSubject, MouseObserver,
    from_mouse, write_to_mouse,
)

__all__ = [
    'Observable', 'Observer', 'Subscription', 'DefaultObserver', 'of', 'from_iterable',
    'Subject', 'BehaviorSubject', 'ReplaySubject', 'AsyncSubject', 'PublishSubject',
    'subject', 'behavior_subject', 'replay_subject', 'async_subject', 'publish_subject',
    'Scheduler', 'ImmediateScheduler', 'CurrentThreadScheduler', 'AsyncIOScheduler',
    'ThreadPoolScheduler', 'NewThreadScheduler',
    'immediate', 'current_thread', 'asyncio_scheduler',
    'immediate_scheduler', 'current_thread_scheduler',
    'thread_pool_scheduler', 'new_thread_scheduler',
    'ConnectableObservable', 'publish', 'share', 'replay', 'publish_replay', 'auto_connect',
    
    'map', 'filter', 'flat_map', 'concat_map', 'switch_map',
    'take', 'skip', 'take_while', 'skip_while', 'take_until',
    'distinct_until_changed', 'debounce', 'throttle_first',
    'tap', 'delay', 'start_with', 'end_with',
    'reduce', 'scan', 'count', 'sum', 'average', 'minimum', 'maximum',
    'all', 'any', 'contains', 'is_empty',
    'to_list', 'buffer', 'group_by', 'merge', 'concat',
    'catch', 'retry', 'on_error_return', 'on_error_resume_next', 'retry_when',
    'first', 'last', 'distinct', 'element_at', 'skip_until',
    'default_if_empty', 'sequence_equal', 'timeout', 'timestamp', 'iif',
    'dispatch_to_workers', 'dispatch_workers', 'amb',
    'backpressure_buffer', 'backpressure_drop', 'backpressure_error', 'backpressure_latest',
    'buffer_until_idle', 'buffer_with_count', 'cache', 'circuit_breaker',
    'collect_until', 'combine_latest', 'zip', 'count_events',
    'curry_map', 'debounce_data', 'debounce_events', 'debounce_evolution',
    'distinct_until_changed_by', 'distinct_values',
    'do_on_completed', 'do_on_error', 'do_on_next', 'finally_with_data',
    'filter_by', 'filter_by_data', 'filter_by_event_type',
    'flat_map_latest', 'group_by_event_type', 'ignore_elements',
    'lazy_flat_map', 'observe_on',
    'on_condition_met', 'on_data', 'on_every_nth', 'on_next_data',
    'on_start', 'on_stop',
    'parallel', 'rate_limit', 'retry_with_backoff',
    'sample', 'sample_first', 'seq_bridge',
    'skip_last', 'skip_n_events', 'skip_until_data',
    'subscribe_on', 'switch',
    'take_last', 'take_n_events', 'take_until_data',
    'throttle_events', 'throttle_latest', 'throttle_with_trailing',
    'time_interval', 'to_map', 'to_set',
    'when', 'when_error', 'when_start', 'when_stop',
    'window', 'with_latest_from', 'with_state',
    
    'combine_latest_map', 'merge_all', 'merge_map',
    'pairwise', 'partition', 'race', 'repeat', 'retry_until',
    'scan_with_index', 'switch_on_next', 'take_until_not',
    'combine_latest_with', 'merge_with', 'switch_map_to',
    'from_range', 'from_callable', 'from_future', 'start',
    
    'median', 'variance', 'std', 'quantile',
    'arg_min', 'arg_max', 'n_unique',
    'rolling_sum', 'rolling_min', 'rolling_max', 'rolling_mean',
    'cum_sum', 'cum_min', 'cum_max', 'cum_mean', 'cum_prod',
    'sort', 'top_k', 'bottom_k',
    'drop_none', 'fill_none', 'abs', 'clamp',
    'explode', 'flatten',
    
    'ClipChangeType', 'ClipData', 'ClipboardDispatcher', 'ClipSubject', 'ClipObserver',
    'from_clipboard', 'write_to_clipboard',
    'FileChangeType', 'FileData', 'FileSubject', 'FileObserver', 'FileDispatcher',
    'from_filesystem', 'write_to_filesystem',
    'FolderChangeType', 'FolderData', 'FolderSubject', 'FolderObserver', 'FolderDispatcher',
    'from_foldersystem', 'write_to_foldersystem',
    'KeyEventType', 'MouseEventType', 'KeyModifier', 'KeyData', 'MouseData',
    'KeyboardDispatcher', 'MouseDispatcher',
    'KeySubject', 'MouseSubject', 'KeyObserver', 'MouseObserver',
    'from_keyboard', 'from_mouse', 'write_to_keyboard', 'write_to_mouse',
]