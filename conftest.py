# -*- coding: utf-8 -*-
"""根 conftest：把各独立 namespace 子包目录注入 sys.path。

vools 核心库（vools/）与独立子包（rx/ bridges/ xl/ pyk/ dll32/ actus/）通过
``pkgutil.extend_path`` 合并为同一个 ``vools`` 命名空间。在仓库根跑 ``tests/``
时，这些子包目录默认不在 sys.path 上，直接 ``import vools.reactive`` /
``import vools.bridge`` 会误报 ``ModuleNotFoundError``（导致 collection error
或假 skip）。这里统一注入，保证 ``vools.*`` 全命名空间合并可见。

仅当子包目录下确有 ``vools/`` 命名空间容器时才注入，避免把无关目录塞进
sys.path。
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_NAMESPACE_SUBPACKAGES = ('rx', 'bridges', 'xl', 'pyk', 'dll32', 'actus')

for _sub in _NAMESPACE_SUBPACKAGES:
    _dir = os.path.join(_REPO_ROOT, _sub)
    if os.path.isdir(os.path.join(_dir, 'vools')) and _dir not in sys.path:
        sys.path.insert(0, _dir)