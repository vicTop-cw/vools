#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
探索 RxPy 4.0 的公开 API
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def explore_module(module, prefix="", depth=0, max_depth=3):
    """递归探索模块结构"""
    if depth > max_depth:
        return
    
    members = inspect.getmembers(module)
    functions = []
    classes = []
    modules = []
    
    for name, obj in members:
        if name.startswith('_'):
            continue
        
        if inspect.ismodule(obj):
            if obj.__name__.startswith('rx'):
                modules.append((name, obj))
        elif inspect.isfunction(obj):
            functions.append(name)
        elif inspect.isclass(obj):
            classes.append(name)
    
    if functions or classes or modules:
        print(f"{'  ' * depth}{prefix}")
        if functions:
            print(f"{'  ' * depth}  函数: {', '.join(sorted(functions))}")
        if classes:
            print(f"{'  ' * depth}  类: {', '.join(sorted(classes))}")
        if modules:
            print(f"{'  ' * depth}  子模块:")
            for name, obj in modules:
                explore_module(obj, name, depth + 1)

def get_public_api(module_name):
    """获取模块的公开 API"""
    try:
        module = __import__(module_name, fromlist=[''])
        print(f"=== {module_name} 模块 ===")
        explore_module(module, module_name)
        return module
    except ImportError as e:
        print(f"无法导入 {module_name}: {e}")
        return None

def analyze_rxpy():
    """分析 RxPy 4.0 的完整 API"""
    print("=" * 80)
    print("RxPy 4.0 API 分析")
    print("=" * 80)
    
    rx = get_public_api('rx')
    
    if rx:
        print("\n" + "=" * 80)
        print("详细操作符列表")
        print("=" * 80)
        
        try:
            from rx import operators as ops
            print("\n[rx.operators]")
            ops_list = [name for name in dir(ops) if not name.startswith('_')]
            ops_list.sort()
            
            # 按类别分组
            creation_ops = []
            transformation_ops = []
            filtering_ops = []
            combination_ops = []
            aggregation_ops = []
            error_ops = []
            utility_ops = []
            conditional_ops = []
            conversion_ops = []
            
            for op in ops_list:
                if op in ['from_iterable', 'from_future', 'from_callable', 'interval', 'timer',
                          'empty', 'never', 'throw', 'range', 'repeat', 'defer', 'generate']:
                    creation_ops.append(op)
                elif op in ['map', 'flat_map', 'concat_map', 'switch_map', 'scan', 'buffer',
                            'window', 'group_by', 'merge_map', 'pairwise', 'pluck', 'scan']:
                    transformation_ops.append(op)
                elif op in ['filter', 'take', 'take_until', 'take_while', 'skip', 'skip_until',
                            'skip_while', 'distinct', 'distinct_until_changed', 'debounce',
                            'throttle_first', 'throttle_last', 'ignore_elements', 'element_at']:
                    filtering_ops.append(op)
                elif op in ['combine_latest', 'concat', 'merge', 'zip', 'with_latest_from',
                            'start_with', 'end_with', 'race', 'amb']:
                    combination_ops.append(op)
                elif op in ['reduce', 'sum', 'min', 'max', 'average', 'count', 'to_list',
                            'to_set', 'to_frozenset', 'to_dict', 'first', 'last', 'single',
                            'find', 'default_if_empty']:
                    aggregation_ops.append(op)
                elif op in ['catch', 'on_error_return', 'on_error_resume_next', 'retry',
                            'retry_when', 'on_error_map']:
                    error_ops.append(op)
                elif op in ['tap', 'delay', 'delay_subscription', 'timeout', 'timestamp',
                            'time_interval', 'dematerialize', 'materialize', 'serialize',
                            'observe_on', 'subscribe_on', 'do']:
                    utility_ops.append(op)
                elif op in ['all', 'any', 'contains', 'is_empty', 'sequence_equal',
                            'skip_until_with_time', 'take_until_with_time']:
                    conditional_ops.append(op)
                elif op in ['to_async', 'from_async', 'as_observable', 'to_iterable',
                            'to_future', 'share']:
                    conversion_ops.append(op)
            
            print("\n🎯 创建操作符 (Creation)")
            print(f"   {', '.join(sorted(creation_ops))}")
            
            print("\n🔄 转换操作符 (Transformation)")
            print(f"   {', '.join(sorted(transformation_ops))}")
            
            print("\n🔍 过滤操作符 (Filtering)")
            print(f"   {', '.join(sorted(filtering_ops))}")
            
            print("\n🔗 组合操作符 (Combination)")
            print(f"   {', '.join(sorted(combination_ops))}")
            
            print("\n📊 聚合操作符 (Aggregation)")
            print(f"   {', '.join(sorted(aggregation_ops))}")
            
            print("\n🛡️ 错误处理操作符 (Error Handling)")
            print(f"   {', '.join(sorted(error_ops))}")
            
            print("\n⚙️ 工具操作符 (Utility)")
            print(f"   {', '.join(sorted(utility_ops))}")
            
            print("\n✅ 条件判断操作符 (Conditional)")
            print(f"   {', '.join(sorted(conditional_ops))}")
            
            print("\n🔀 转换操作符 (Conversion)")
            print(f"   {', '.join(sorted(conversion_ops))}")
            
        except ImportError as e:
            print(f"无法导入 rx.operators: {e}")
        
        print("\n" + "=" * 80)
        print("Observable 类方法")
        print("=" * 80)
        try:
            from rx import Observable
            obs_methods = [m for m in dir(Observable) if not m.startswith('_')]
            print(f"Observable 公开方法: {', '.join(sorted(obs_methods))}")
        except ImportError as e:
            print(f"无法导入 Observable: {e}")
        
        print("\n" + "=" * 80)
        print("Subject 类")
        print("=" * 80)
        try:
            from rx.subject import Subject, BehaviorSubject, ReplaySubject, AsyncSubject
            print("Subject 类型: Subject, BehaviorSubject, ReplaySubject, AsyncSubject")
        except ImportError as e:
            print(f"无法导入 Subject: {e}")
        
        print("\n" + "=" * 80)
        print("调度器 (Schedulers)")
        print("=" * 80)
        try:
            from rx import schedulers
            scheduler_list = [s for s in dir(schedulers) if not s.startswith('_')]
            print(f"调度器: {', '.join(sorted(scheduler_list))}")
        except ImportError as e:
            print(f"无法导入 schedulers: {e}")

if __name__ == "__main__":
    analyze_rxpy()