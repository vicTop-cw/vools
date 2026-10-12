# -*- coding: utf-8 -*-
"""pyk 独立包测试 conftest：让 vools 与 vools.pyk 通过 namespace 合并可用。

使用方式：
    cd <repo_root>/pyk
    python -m pytest tests -v

原理：vools 核心库（仓库根 vools/）与 vools-pyk 独立包（本目录 vools/）通过
pkgutil.extend_path 合并为同一个 vools 命名空间。只要两边都出现在 sys.path 上
（或已 pip 安装到 site-packages），`import vools.pyk` 即可正常解析。
"""
import os
import sys

# 仓库根目录（vools 核心库 + vools-pyk 独立包都在这里）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyk 独立包目录（含 vools/ namespace 容器）
_PYK_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _p in (_REPO_ROOT, _PYK_PKG_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)