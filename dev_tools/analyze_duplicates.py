#!/usr/bin/env python
"""
详细分析同名不同义的对象
"""
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def analyze_obj(name, module):
    """分析一个对象"""
    try:
        mod = __import__(module, fromlist=[''])
        obj = getattr(mod, name, None)
        
        print(f"\n{name} (from {module}):")
        print(f"  类型: {type(obj).__name__}")
        
        if hasattr(obj, '__doc__') and obj.__doc__:
            first_line = obj.__doc__.strip().split('\n')[0]
            print(f"  文档: {first_line}")
        
        if hasattr(obj, '__module__'):
            print(f"  定义模块: {obj.__module__}")
        
        if callable(obj):
            try:
                import inspect
                sig = inspect.signature(obj)
                print(f"  签名: {sig}")
            except:
                pass
        
        return obj
    except Exception as e:
        print(f"\n{name} (from {module}): ERROR - {e}")
        return None


def main():
    print("=" * 80)
    print("详细分析同名不同义的对象")
    print("=" * 80)
    
    # 分析 lazy
    print("\n" + "=" * 80)
    print("分析: lazy")
    print("=" * 80)
    lazy1 = analyze_obj("lazy", "vools.decorators.curry_delay")
    lazy2 = analyze_obj("lazy", "vools.decorators.lazy")
    
    # 分析 overloads
    print("\n" + "=" * 80)
    print("分析: overloads")
    print("=" * 80)
    overloads1 = analyze_obj("overloads", "vools.decorators.overloads")
    overloads2 = analyze_obj("overloads", "vools.decorators.selector")
    overloads3 = analyze_obj("overloads", "vools.oop.selector")
    
    # 简单测试
    print("\n" + "=" * 80)
    print("测试调用 (如果可调用)")
    print("=" * 80)
    
    if callable(lazy1):
        try:
            result = lazy1(42)
            print(f"lazy1(42) = {result} ({type(result).__name__})")
        except Exception as e:
            print(f"lazy1(42) ERROR: {e}")
    
    if callable(lazy2):
        try:
            result = lazy2(42)
            print(f"lazy2(42) = {result} ({type(result).__name__})")
        except Exception as e:
            print(f"lazy2(42) ERROR: {e}")


if __name__ == '__main__':
    main()
