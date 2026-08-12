"""检查 vbRichClient5.dll 导出函数"""
import os
import sys

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'dll32', '_dlls', 'vbRichClient5.dll')

print("检查 DLL:", dll_path)
print("文件存在:", os.path.exists(dll_path))
if os.path.exists(dll_path):
    print("文件大小:", os.path.getsize(dll_path), "bytes")

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
                name = exp.name.decode('utf-8', errors='ignore')
                print("  ", name)
            else:
                print("  (ordinal:", exp.ordinal, ")")
    else:
        print("没有导出表")

except ImportError as e:
    print("pefile 导入失败:", e)
except Exception as e:
    print("处理失败:", e)

print("\n=== 测试完成 ===")
