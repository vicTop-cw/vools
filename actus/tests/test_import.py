# -*- coding: utf-8 -*-
"""
测试 vools-actus 基础 GUI 动作 - 简化版
"""

import sys
import os

# 添加 actus/vools 目录到路径
vools_actus_dir = os.path.join(os.path.dirname(__file__), 'vools')
sys.path.insert(0, vools_actus_dir)

print("Python 路径:")
for p in sys.path[:5]:
    print(f"  {p}")

# 测试导入
try:
    import vools.actus
    print(f"\n✓ vools.actus 导入成功: {vools.actus.__file__}")
except Exception as e:
    print(f"\n✗ vools.actus 导入失败: {e}")

try:
    from vools.actus.actions.basics.calculator import CalculatorAction
    print("✓ CalculatorAction 导入成功")
except Exception as e:
    print(f"✗ CalculatorAction 导入失败: {e}")

try:
    from vools.actus.actions.basics.todo_list import TodoListAction
    print("✓ TodoListAction 导入成功")
except Exception as e:
    print(f"✗ TodoListAction 导入失败: {e}")

try:
    from vools.actus.actions.basics.text_editor import TextEditorAction
    print("✓ TextEditorAction 导入成功")
except Exception as e:
    print(f"✗ TextEditorAction 导入失败: {e}")

try:
    from vools.actus.actions.basics.image_viewer import ImageViewerAction
    print("✓ ImageViewerAction 导入成功")
except Exception as e:
    print(f"✗ ImageViewerAction 导入失败: {e}")
