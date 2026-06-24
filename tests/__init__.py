"""
测试入口文件（已归档结构）

注意：测试文件已按子包归档到子目录。
通过 pytest 运行测试时，pytest 会自动发现所有 test_*.py 文件。
"""

import sys
import os

# 将 vools 包根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
