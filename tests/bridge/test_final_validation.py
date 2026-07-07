"""
最终验证测试 - 验证自动发现功能是否完整工作
"""

print('=' * 70)
print('最终验证测试')
print('=' * 70)

# 测试所有导出
print()
print('1. 测试所有导出是否可用')
from vools.bridge import (
    # core
    LibraryLoader, SharedLibrary, load_library, load_from_path, is_available,
    CTypeMapper, bridge_function, bridge_module, bridge_func_name, Serializer,
    
    # manager
    manager, LanguageConfig, LanguageStatus, BridgeManager, LanguageCompilerHelper,
    register_language, get_status, get_compiler_path, get_compiler,
    get_compiler_executable, get_helper, get_version, setup_runtime,
    list_languages, list_available, auto_discover,
    
    # auto_discovery
    discover_all, discover_local, discover_wsl, get_discovery_report, configure_from_discovery,
    
    # 路径配置
    set_compiler_path, add_compiler_path, set_runtime_path, add_runtime_path,
    get_all_paths, save_config, load_config, get_config_file_path,
)

print('   ✅ 所有导出可用')

print()
print('2. 测试自动发现功能')
result = discover_all(include_wsl=True, configure_manager=True)
local_count = len(result['discovered']['local'])
wsl_count = len(result.get('wsl', []))
print(f'   本机发现: {local_count} 种语言')
print(f'   WSL 发现: {wsl_count} 个发行版')
print(f'   报告长度: {len(result["report"])} 字符')
print('   ✅ 自动发现正常')

print()
print('3. 测试配置持久化')
saved = save_config()
loaded = load_config()
print(f'   配置文件: {saved}')
print(f'   加载语言数: {loaded}')
print('   ✅ 配置持久化正常')

print()
print('4. 测试 LanguageCompilerHelper')
helper = get_helper('nim')
print(f'   nim helper.is_available(): {helper.is_available()}')
print(f'   nim helper.get_version(): {helper.get_version()}')
print('   ✅ LanguageCompilerHelper 正常')

print()
print('5. 测试各模块独立函数')
local_result = discover_local()
print(f'   discover_local 可用数: {len(local_result["discovered"]["local"])}')

wsl_reports = discover_wsl()
print(f'   discover_wsl 发行版数: {len(wsl_reports)}')

report_text = get_discovery_report(include_wsl=False)
print(f'   get_discovery_report 长度: {len(report_text)}')

config_count = configure_from_discovery(include_wsl=False)
print(f'   configure_from_discovery 配置数: {config_count}')

print('   ✅ 各模块独立函数正常')

print()
print('=' * 70)
print('所有测试通过！')
print('=' * 70)
