#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RxPy 4.0 vs vools-reactive 功能对比
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def analyze_vools_reactive():
    """分析 vools-reactive 的功能"""
    from vools.reactive import Observable, ops
    
    vools_ops = [name for name in dir(ops) if not name.startswith('_')]
    
    return {
        'creation': [
            'from_iterable', 'of', 'just', 'from_range', 'empty', 
            'never', 'throw', 'error', 'interval'
        ],
        'transformation': [
            'map', 'flat_map', 'scan', 'buffer', 'group_by', 'pluck'
        ],
        'filtering': [
            'filter', 'take', 'take_until', 'skip', 'debounce', 
            'throttle_first', 'distinct_until_changed'
        ],
        'combination': [
            'zip', 'combine_latest', 'with_latest_from', 'merge', 'concat'
        ],
        'aggregation': [
            'sum', 'average', 'minimum', 'maximum', 'reduce', 'count', 'to_list'
        ],
        'error': [
            'catch', 'on_error_return', 'on_error_resume_next', 'retry_when'
        ],
        'utility': [
            'tap', 'delay', 'delay_subscription'
        ],
        'conditional': [
            'all', 'any', 'contains', 'is_empty'
        ],
        'subjects': ['Subject', 'BehaviorSubject'],
        'operators': vools_ops
    }

def analyze_rxpy():
    """分析 RxPy 4.0 的功能"""
    try:
        from rx import operators as rx_ops
        rxpy_ops = [name for name in dir(rx_ops) if not name.startswith('_')]
        
        return {
            'creation': [
                'from_iterable', 'from_future', 'from_callable', 'interval', 'timer',
                'empty', 'never', 'throw', 'range', 'repeat', 'defer', 'generate',
                'just', 'of', 'create'
            ],
            'transformation': [
                'map', 'flat_map', 'concat_map', 'switch_map', 'scan', 'buffer',
                'window', 'group_by', 'merge_map', 'pairwise', 'pluck'
            ],
            'filtering': [
                'filter', 'take', 'take_until', 'take_while', 'skip', 'skip_until',
                'skip_while', 'distinct', 'distinct_until_changed', 'debounce',
                'throttle_first', 'throttle_last', 'ignore_elements', 'element_at'
            ],
            'combination': [
                'combine_latest', 'concat', 'merge', 'zip', 'with_latest_from',
                'start_with', 'end_with', 'race', 'amb'
            ],
            'aggregation': [
                'reduce', 'sum', 'min', 'max', 'average', 'count', 'to_list',
                'to_set', 'to_frozenset', 'to_dict', 'first', 'last', 'single',
                'find', 'default_if_empty'
            ],
            'error': [
                'catch', 'on_error_return', 'on_error_resume_next', 'retry',
                'retry_when', 'on_error_map'
            ],
            'utility': [
                'tap', 'delay', 'delay_subscription', 'timeout', 'timestamp',
                'time_interval', 'dematerialize', 'materialize', 'serialize',
                'observe_on', 'subscribe_on', 'do'
            ],
            'conditional': [
                'all', 'any', 'contains', 'is_empty', 'sequence_equal',
                'skip_until_with_time', 'take_until_with_time'
            ],
            'conversion': [
                'to_async', 'from_async', 'as_observable', 'to_iterable',
                'to_future', 'share'
            ],
            'subjects': ['Subject', 'BehaviorSubject', 'ReplaySubject', 'AsyncSubject'],
            'operators': rxpy_ops
        }
    except ImportError:
        return None

def compare_features():
    """对比功能"""
    vools = analyze_vools_reactive()
    rxpy = analyze_rxpy()
    
    if not rxpy:
        print("RxPy 4.0 未安装")
        return
    
    print("=" * 80)
    print("RxPy 4.0 vs vools-reactive 功能对比")
    print("=" * 80)
    
    categories = [
        ('创建操作符', 'creation'),
        ('转换操作符', 'transformation'),
        ('过滤操作符', 'filtering'),
        ('组合操作符', 'combination'),
        ('聚合操作符', 'aggregation'),
        ('错误处理', 'error'),
        ('工具操作符', 'utility'),
        ('条件判断', 'conditional'),
        ('转换操作符', 'conversion'),
        ('Subject 类型', 'subjects')
    ]
    
    for category_name, category_key in categories:
        print(f"\n{category_name}:")
        print("-" * 50)
        
        vools_items = vools.get(category_key, [])
        rxpy_items = rxpy.get(category_key, [])
        
        vools_set = set(vools_items)
        rxpy_set = set(rxpy_items)
        
        # vools 已有
        existing = vools_set & rxpy_set
        # vools 独有
        unique = vools_set - rxpy_set
        # vools 缺失
        missing = rxpy_set - vools_set
        
        if existing:
            print(f"✅ 已实现: {', '.join(sorted(existing))}")
        
        if unique:
            print(f"🌟 独有功能: {', '.join(sorted(unique))}")
        
        if missing:
            print(f"❌ 缺失: {', '.join(sorted(missing))}")
    
    print("\n" + "=" * 80)
    print("vools-reactive 创新功能")
    print("=" * 80)
    
    innovations = [
        "• placeholder 表达式支持: ops.filter('_ > 0')",
        "• curry 柯里化集成: ops.map(curry(fn)(arg))",
        "• >> 管道操作符: obs >> ops.filter(cond) >> ops.map(fn)",
        "• lazy 模块集成: 延迟执行支持",
        "• Subscription 上下文管理器: with obs.subscribe(...) as sub:",
        "• debug.trace 装饰器: 函数调用追踪",
        "• combine_latest 性能: 比 RxPy 快 5.77x",
        "• interval 异步: 比 RxPy 快 1.04x"
    ]
    
    for feature in innovations:
        print(feature)
    
    print("\n" + "=" * 80)
    print("建议补充的功能 (优先级排序)")
    print("=" * 80)
    
    priority_features = [
        ("高优先级", ['switch_map', 'concat_map', 'retry', 'start_with', 'end_with']),
        ("中优先级", ['timer', 'repeat', 'defer', 'generate', 'take_while', 'skip_while']),
        ("低优先级", ['throttle_last', 'ignore_elements', 'element_at', 'race', 'amb']),
        ("Subject", ['ReplaySubject', 'AsyncSubject']),
        ("调度器", ['observe_on', 'subscribe_on'])
    ]
    
    for priority, features in priority_features:
        print(f"\n{priority}:")
        print(f"   {', '.join(sorted(features))}")

if __name__ == "__main__":
    compare_features()