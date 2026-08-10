"""导入测试脚本 - 检查绝对导入、循环导入等问题"""

print('=== 导入测试 ===')
print()

# 1. 导入主包
print('1. vools 主包...')
import vools
from importlib.metadata import version as _pkg_version
print(f'   OK - vools {_pkg_version("vools")}')

# 2. bridge 模块
print('2. vools.bridge...')
import vools.bridge as bridge
print(f'   OK - {len(bridge.list_languages())} 种语言')

# 3. probe 模块
print('3. vools.bridge.probe...')
from vools.bridge import probe
print(f'   OK - {len(probe.BRIDGE_SUPPORTED)} 种语言配置')

# 4. manager 模块
print('4. vools.bridge.manager...')
from vools.bridge.manager import manager as mgr, BridgeManager, LanguageConfig
print(f'   OK - {len(mgr.list_languages())} 种已注册语言')

# 5. auto_discovery 模块
print('5. vools.bridge.auto_discovery...')
from vools.bridge import auto_discovery
print('   OK')

# 6. check_bridges
print('6. vools.bridge.check_bridges...')
from vools.bridge import check_bridges
print('   OK')

# 7. 循环导入检测
print('7. 循环导入检测...')
import importlib
importlib.reload(vools)
importlib.reload(bridge)
importlib.reload(probe)
print('   OK - 重新导入无异常')

print()
print('=== 所有导入测试通过！ ===')
