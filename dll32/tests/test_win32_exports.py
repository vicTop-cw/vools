"""使用 pefile 枚举 DLL 导出函数"""
import os
import sys

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'dll32', '_dlls', 'DirectCOM.dll')

print("检查 DLL:", dll_path)
print("文件存在:", os.path.exists(dll_path))

try:
    import pefile
    print("pefile 导入成功")

    pe = pefile.PE(dll_path)

    # 检查导出表
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT') and pe.DIRECTORY_ENTRY_EXPORT:
        exports = pe.DIRECTORY_ENTRY_EXPORT.symbols
        print("导出函数数量:", len(exports))
        for exp in exports:
            if exp.name:
                print("  ", exp.name.decode('utf-8', errors='ignore'))
            else:
                print("  (ordinal:", exp.ordinal, ")")
    else:
        print("没有导出表 (可能是纯 COM 组件)")

except ImportError as e:
    print("pefile 导入失败:", e)
    print("\n安装 pefile:")
    print("  pip install pefile")
except Exception as e:
    print("处理失败:", e)
    import traceback
    traceback.print_exc()

print("\n=== 测试完成 ===")
