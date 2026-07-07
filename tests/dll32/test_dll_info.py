"""检查 DLL 类型和详细信息"""
import os
import struct
import ctypes

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 检查两个 DLL
paths = [
    os.path.join(_vools_dir, 'dll32', '_dlls', 'DirectCOM.dll'),
    os.path.join(os.environ.get('USERPROFILE', 'C:\\'), 'dlls', 'DirectCOM.dll'),
]

for dll_path in paths:
    print("\n=== 检查:", dll_path, "===")
    print("文件存在:", os.path.exists(dll_path))

    if os.path.exists(dll_path):
        print("文件大小:", os.path.getsize(dll_path), "bytes")

        try:
            # 尝试加载
            dll = ctypes.WinDLL(dll_path)
            print("DLL 加载成功 (WinDLL)")

            # 尝试 CDLL
            dll2 = ctypes.CDLL(dll_path)
            print("CDLL 加载成功")

        except Exception as e:
            print("加载失败:", e)

        # 检查是否是有效的 PE 文件
        with open(dll_path, 'rb') as f:
            dos_header = f.read(2)
            print("MZ 签名:", dos_header == b'MZ')

            if dos_header == b'MZ':
                f.seek(0x3C)
                pe_offset = struct.unpack('<I', f.read(4))[0]
                f.seek(pe_offset)
                pe_sig = f.read(4)
                expected_pe = b'PE\x00\x00'
                print("PE 签名:", pe_sig == expected_pe)

                # 读取 COFF header
                f.seek(pe_offset + 4)
                machine = struct.unpack('<H', f.read(2))[0]
                # 0x014c = x86, 0x8664 = x64
                if machine == 0x014c:
                    print("机器类型: x86 (32-bit)")
                elif machine == 0x8664:
                    print("机器类型: x64 (64-bit)")
                else:
                    print("机器类型: 0x%04x" % machine)
