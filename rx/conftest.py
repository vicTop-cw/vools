"""rx 子项目测试引导。

vools-rx 是独立命名空间分发包（``rx/vools/reactive``，``rx/vools`` 无
``__init__.py``，是 PEP 420 命名空间段），它 ``from ...core`` 依赖核心包
``vools``。在 monorepo 里直接 ``pytest rx`` 时，sys.path 只有 ``rx/``，
解析不到兄弟树的 ``vools.core``，导致整个 rx 套件 19 个文件收集失败。

核心库 ``vools/__init__.py`` 用 ``pkgutil.extend_path`` 合并命名空间，因此
只要把 monorepo 根（核心 ``vools/`` 所在处）加进 sys.path，
``vools.reactive``（rx/）与 ``vools.core``（仓库根）就能在同一命名空间共存。

独立安装 vools-rx（vools 作为 pip 依赖装进 site-packages）时不需要本文件，
因此这里做存在性守卫，找不到本地核心树就什么都不做。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # .../vools/rx
_MONOREPO_ROOT = os.path.dirname(_HERE)                     # .../vools
_CORE_PKG = os.path.join(_MONOREPO_ROOT, 'vools', '__init__.py')

if os.path.isfile(_CORE_PKG) and _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)
