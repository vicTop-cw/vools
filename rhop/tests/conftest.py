"""pytest 路径引导：让仓库内的 rhop / rx / vools 主包可被导入。"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_ROOT)  # 仓库根，由 _ROOT 推导（可移植）

for _p in (_ROOT, os.path.join(_REPO, "rx"), _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)
