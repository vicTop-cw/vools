"""枚举 DLL 导出函数"""
import struct
import ctypes
import os

def get_exported_functions(dll_path):
    """从 DLL 中读取导出函数列表"""
    # 使用 ctypes 枚举
    dll = ctypes.WinDLL(dll_path)
    
    # 获取所有以 D 开头的函数
    exports = []
    for name in dir(dll):
        if name.startswith('_') or name.startswith('Dll'):
            exports.append(name)
    
    return exports

def parse_pe_exports(dll_path):
    """解析 PE 文件获取导出表"""
    with open(dll_path, 'rb') as f:
        dos_header = f.read(64)
        if dos_header[:2] != b'MZ':
            return []
        
        # PE header offset at 0x3C
        pe_offset = struct.unpack('<I', dos_header[0x3C:0x40])[0]
        f.seek(pe_offset)
        
        # PE signature
        pe_sig = f.read(4)
        if pe_sig != b'PE\x00\x00':
            return []
        
        # COFF header
        coff_header = f.read(20)
        num_sections = struct.unpack('<H', coff_header[2:4])[0]
        opt_header_size = struct.unpack('<H', coff_header[16:18])[0]
        
        # Optional header
        opt_header = f.read(opt_header_size)
        
        # Data directories
        data_dir_offset = 96  # offset to data directory in optional header
        export_dir_rva = struct.unpack('<I', opt_header[data_dir_offset:data_dir_offset+4])[0]
        export_dir_size = struct.unpack('<I', opt_header[data_dir_offset+4:data_dir_offset+8])[0]
        
        if export_dir_rva == 0:
            return []
        
        # 遍历 sections 找到 export directory
        sections = []
        for i in range(num_sections):
            section = f.read(40)
            name = section[:8].rstrip(b'\x00')
            virtual_size = struct.unpack('<I', section[8:12])[0]
            virtual_addr = struct.unpack('<I', section[12:16])[0]
            raw_data_ptr = struct.unpack('<I', section[20:24])[0]
            raw_data_size = struct.unpack('<I', section[24:28])[0]
            sections.append({
                'name': name,
                'virtual_addr': virtual_addr,
                'raw_ptr': raw_data_ptr,
                'virtual_size': virtual_size,
                'raw_size': raw_data_size
            })
        
        # Find export directory
        export_rva = export_dir_rva
        for sec in sections:
            if sec['virtual_addr'] <= export_rva < sec['virtual_addr'] + sec['virtual_size']:
                offset = export_rva - sec['virtual_addr'] + sec['raw_ptr']
                f.seek(offset)
                
                # Export directory
                characteristics = struct.unpack('<I', f.read(4))[0]
                time_date = struct.unpack('<I', f.read(4))[0]
                major_ver = struct.unpack('<H', f.read(2))[0]
                minor_ver = struct.unpack('<H', f.read(2))[0]
                name_rva = struct.unpack('<I', f.read(4))[0]
                ordinal_base = struct.unpack('<I', f.read(4))[0]
                num_functions = struct.unpack('<I', f.read(4))[0]
                num_names = struct.unpack('<I', f.read(4))[0]
                
                # Read name pointers
                name_ptr_rva = struct.unpack('<I', f.read(4))[0]
                ordinals_ptr_rva = struct.unpack('<I', f.read(4))[0]
                
                # Find name pointers in section
                for sec in sections:
                    if sec['virtual_addr'] <= name_ptr_rva < sec['virtual_addr'] + sec['virtual_size']:
                        name_ptr_offset = name_ptr_rva - sec['virtual_addr'] + sec['raw_ptr']
                        break
                
                names = []
                for i in range(num_names):
                    f.seek(name_ptr_offset + i * 4)
                    name_rva = struct.unpack('<I', f.read(4))[0]
                    
                    # Find name in section
                    for sec in sections:
                        if sec['virtual_addr'] <= name_rva < sec['virtual_addr'] + sec['virtual_size']:
                            name_offset = name_rva - sec['virtual_addr'] + sec['raw_ptr']
                            break
                    
                    f.seek(name_offset)
                    name = b''
                    while True:
                        c = f.read(1)
                        if c == b'\x00':
                            break
                        name += c
                    names.append(name.decode('ascii', errors='ignore'))
                
                return names
                
        return []

# 测试
_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'dll32', '_dlls', 'DirectCOM.dll')
print(f"检查 DLL: {dll_path}")

try:
    exports = parse_pe_exports(dll_path)
    print(f"导出函数数量: {len(exports)}")
    print("\n所有导出函数:")
    for exp in sorted(exports):
        print(f"  {exp}")
except Exception as e:
    print(f"解析失败: {e}")
    import traceback
    traceback.print_exc()
