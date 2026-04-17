"""
测试入口文件
"""

import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入所有测试模块
from .test_decorators import *
from .test_functional import *
from .test_utils import *


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("运行 vools 测试套件")
    print("=" * 60)
    
    # 装饰器测试
    test_memorize()
    test_once()
    test_lazy()
    
    # 函数式编程测试
    test_pipe()
    test_ops()
    test_seq()
    test_p()
    test_none()
    
    # 通用工具测试
    test_basic_functions()
    test_stuff()
    
    print("\n" + "=" * 60)
    print("[SUCCESS] 所有测试通过!")
    print("=" * 60)


if __name__ == '__main__':
    run_all_tests()
