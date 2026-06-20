"""
检查 class_fusion 模块来源
"""
import sys
sys.path.insert(0, r'E:\IDEProjects\AI\vools')

# 检查模块来源
import Temp.class_fusion as cf
print(f"class_fusion 模块位置: {cf.__file__}")

# 检查 _apply_method_wrapper 函数
print(f"_apply_method_wrapper 函数: {cf._apply_method_wrapper}")
print(f"_apply_method_wrapper 源码文件: {inspect.getfile(cf._apply_method_wrapper) if hasattr(cf, 'inspect') else 'unknown'}")

import inspect
print(f"\n_apply_method_wrapper 源码:")
print(inspect.getsource(cf._apply_method_wrapper))
