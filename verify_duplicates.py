#!/usr/bin/env python
"""
验证发现的同名对象是否是同一个对象
"""
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def check_identity(name, module1, module2):
    """检查两个模块中的同名对象是否是同一个"""
    try:
        mod1 = __import__(module1, fromlist=[''])
        mod2 = __import__(module2, fromlist=[''])
        
        obj1 = getattr(mod1, name, None)
        obj2 = getattr(mod2, name, None)
        
        if obj1 is not None and obj2 is not None:
            if obj1 is obj2:
                return f"[SAME] {name}: {module1} 和 {module2} 是同一个对象"
            else:
                return f"[DIFFERENT] {name}: {module1} 和 {module2} 是不同对象!"
        else:
            return f"[MISSING] {name}: 某个模块中缺失"
    except Exception as e:
        return f"[ERROR] {name}: {e}"


def main():
    print("=" * 80)
    print("验证同名对象的身份")
    print("=" * 80)
    print()
    
    checks = [
        # 成对检查
        ("Overloads", "vools.decorators.selector", "vools.oop.selector"),
        ("Selector", "vools.decorators.selector", "vools.oop.selector"),
        ("arrow_func", "vools.functional.arrow_func", "vools.oop.extend"),
        ("g", "vools.functional.arrow_func", "vools.oop.extend"),
        ("lazy", "vools.decorators.curry_delay", "vools.decorators.lazy"),
        ("overloads", "vools.decorators.overloads", "vools.decorators.selector"),
        ("overloads", "vools.decorators.selector", "vools.oop.selector"),
    ]
    
    results = []
    for name, mod1, mod2 in checks:
        result = check_identity(name, mod1, mod2)
        results.append(result)
        print(result)
    
    print()
    print("=" * 80)
    print("总结：")
    print("=" * 80)
    
    different_count = sum(1 for r in results if "[DIFFERENT]" in r)
    same_count = sum(1 for r in results if "[SAME]" in r)
    
    print(f"相同对象: {same_count}")
    print(f"不同对象: {different_count}")
    
    if different_count > 0:
        print()
        print("警告：发现不同的同名对象！")


if __name__ == '__main__':
    main()
