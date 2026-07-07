"""
测试 auto_discovery 模块完整流程
"""

print('=' * 70)
print('测试 auto_discovery 模块完整流程')
print('=' * 70)

from vools.bridge import (
    discover_all,
    get_discovery_report,
    configure_from_discovery,
    manager,
    list_languages,
    list_available,
)

print()
print('1. discover_all 测试（本机）')
try:
    result = discover_all(include_wsl=False, configure_manager=False)
    print(f'   result 键: {list(result.keys())}')
    print(f'   local 类型: {type(result.get("local")).__name__}')
    print(f'   wsl 类型: {type(result.get("wsl")).__name__}')
    print(f'   discovered: {result.get("discovered")}')
    print(f'   report 长度: {len(result.get("report", ""))} 字符')
    
    local = result['local']
    print(f'   本机可用语言: {local.available_languages()}')
    print(f'   本机可用数量: {len(local.available_languages())}')
    print('   ✅ discover_all 正常')
except Exception as e:
    print(f'   ❌ discover_all 失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('2. get_discovery_report 测试')
try:
    report = get_discovery_report(include_wsl=False)
    print(f'   报告长度: {len(report)} 字符')
    print('   报告预览 (前 20 行):')
    lines = report.split('\n')[:20]
    for line in lines:
        print(f'     {line}')
    print('   ✅ get_discovery_report 正常')
except Exception as e:
    print(f'   ❌ get_discovery_report 失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('3. configure_from_discovery 测试')
try:
    # 先获取之前的语言数量
    before = len(list_languages())
    print(f'   配置前语言数: {before}')
    
    count = configure_from_discovery(include_wsl=False)
    after = len(list_languages())
    print(f'   配置后语言数: {after}')
    print(f'   配置语言数: {count}')
    print(f'   可用语言: {list_available()}')
    print('   ✅ configure_from_discovery 正常')
except Exception as e:
    print(f'   ❌ configure_from_discovery 失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('4. discover_all + WSL 测试')
try:
    result2 = discover_all(include_wsl=True, configure_manager=False)
    wsl_reports = result2.get('wsl', [])
    print(f'   WSL 发行版数量: {len(wsl_reports)}')
    for wsl_report in wsl_reports:
        print(f'     {wsl_report.host}: {wsl_report.available_languages()[:5]}...')
        print(f'       可用数: {len(wsl_report.available_languages())}')
    print('   ✅ WSL 发现正常')
except Exception as e:
    print(f'   ❌ WSL 发现失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('=' * 70)
print('auto_discovery 模块测试完成')
print('=' * 70)
