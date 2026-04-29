"""
测试入口文件
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from .test_decorators import *
    from .test_functional import *
    from .test_utils import *
except ImportError:
    from test_decorators import *
    from test_functional import *
    from test_utils import *


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("运行 vools 测试套件")
    print("=" * 60)
    
    # 装饰器测试
    test_curry_basic()
    test_curry_with_varargs()
    test_curry_class_method()
    test_curry_class()
    test_curry_strict()
    test_delay_curry_basic()
    test_delay_curry_with_varargs()
    test_delay_curry_class_method()
    test_overload_basic()
    test_overload_strict()
    
    # 函数式编程测试
    test_placeholder_basic()
    test_placeholder_advanced()
    test_box_basic()
    test_box_dict()
    test_box_string()
    test_box_datetime()
    test_pipe_ops_seq()
    test_g_function()
    test_iif_function()
    
    # 通用工具测试
    test_basic_functions()
    test_stuff()
    
    print("\n" + "=" * 60)
    print("[SUCCESS] 所有测试通过!")
    print("=" * 60)


if __name__ == '__main__':
    run_all_tests()