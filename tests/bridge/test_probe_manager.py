"""
测试 manager 模块 auto_discover 功能
"""
import sys

print('=' * 70)
print('测试 manager 模块 auto_discover 功能')
print('=' * 70)

from vools.bridge import (
    manager,
    get_status,
    get_compiler_path,
    get_helper,
    list_languages,
    list_available,
    auto_discover,
)

print()
print('1. 基本 API 测试')
print(f'   manager 类型: {type(manager).__name__}')
print(f'   list_languages(): {list_languages()}')
print(f'   list_available(): {list_available()}')

print()
print('2. 单语言状态测试 (nim)')
status = get_status('nim')
print(f'   available: {status.available}')
print(f'   version: {status.version}')
nim_path = get_compiler_path('nim')
print(f'   path: {nim_path}')

print()
print('3. auto_discover 测试（本机）')
try:
    result = manager.auto_discover(include_wsl=False)
    print(f'   本机发现语言数: {len(result.get("local", []))}')
    print(f'   WSL 发现语言数: {len(result.get("wsl", []))}')
    print(f'   本机语言: {result.get("local", [])[:10]}...')
    print('   ✅ auto_discover 正常')
except Exception as e:
    print(f'   ❌ auto_discover 失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('4. LanguageCompilerHelper 测试')
try:
    helper = get_helper('nim')
    print(f'   helper 类型: {type(helper).__name__}')
    print(f'   helper.is_available(): {helper.is_available()}')
    print(f'   helper.get_compiler_path(): {helper.get_compiler_path()}')
    print('   ✅ LanguageCompilerHelper 正常')
except Exception as e:
    print(f'   ❌ LanguageCompilerHelper 失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('5. 配置管理测试')
try:
    config = manager.get_config('nim')
    print(f'   config.name: {config.name}')
    print(f'   config.compiler: {config.compiler}')
    paths = config.compiler_paths[:2]
    print(f'   config.compiler_paths: {paths}...')
    print('   ✅ 配置管理正常')
except Exception as e:
    print(f'   ❌ 配置管理失败: {e}')

print()
print('=' * 70)
print('manager 模块测试完成')
print('=' * 70)
