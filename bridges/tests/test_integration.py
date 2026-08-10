"""
测试与现有桥接模块的集成
验证自动发现功能是否能正确让桥接模块检测到编译器
"""

print('=' * 70)
print('测试与现有桥接模块的集成')
print('=' * 70)

print()
print('1. 测试各语言编译器可用性检测')
languages_to_test = [
    ('nim', 'nim_compiler_available'),
    ('rust', None),
    ('c', 'cpp_compiler_available'),
    ('cpp', 'cpp_compiler_available'),
    ('typescript', 'ts_compiler_available'),
    ('java', None),
    ('csharp', None),
    ('julia', 'julia_compiler_available'),
    ('go', 'go_compiler_available'),
    ('cangjie', 'cjc_compiler_available'),
    ('ruby', 'ruby_compiler_available'),
    ('r', 'r_compiler_available'),
]

import vools.bridge as bridge

for lang, check_func in languages_to_test:
    try:
        # 检查 manager 中的状态
        status = bridge.get_status(lang)
        print(f'   {lang:15s} manager.available: {status.available}')
        
        # 检查桥接模块的可用性函数
        if check_func and hasattr(bridge, check_func):
            func = getattr(bridge, check_func)
            result = func()
            print(f'   {lang:15s} {check_func}: {result}')
    except Exception as e:
        print(f'   {lang:15s} 错误: {e}')

print()
print('2. 测试配置持久化')
try:
    from vools.bridge import save_config, load_config, get_config_file_path
    
    config_path = get_config_file_path()
    print(f'   配置文件路径: {config_path}')
    
    # 保存配置
    saved_path = save_config()
    print(f'   保存配置: {saved_path}')
    
    # 重新加载
    count = load_config()
    print(f'   加载配置: {count} 种语言')
    
    print('   ✅ 配置持久化正常')
except Exception as e:
    print(f'   ❌ 配置持久化失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('=' * 70)
print('桥接模块集成测试完成')
print('=' * 70)
