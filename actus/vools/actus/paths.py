"""paths.py — Actus 仓库路径的**唯一真源**（repo_root / meta_dir）。

为什么要有这个模块
------------------
改前有 12+ 个模块各自写一遍「`os.environ.get(...)` + `__file__` 上三级推导」：
`indexer.py` / `records.py` / `cost.py` / `calllog.py` / `bugreport.py` /
`dependency.py` / `omega_strong.py` / `scaffold.py` / `selfdrive.py` /
`validate.py` / `scattered.py` / `panel.py` / `probe/cache.py`。
同一件事 13 份实现，是典型的多份实现漂移源（同一轮里已经因为「5 份
`_find_action_file` 实现」吃过亏）。本模块把它们收敛成两个函数。

优先级（**写死在这里，全仓统一**）
----------------------------------
    repo_root() : ACTUS_REPO_ROOT       > <本文件上三级目录>（= 仓库根）
    meta_dir()  : ACTUS_META_DIR        > repo_root()/_meta
                
（`ACTUS_META_DIR` 单独生效的意义：用户能把整个运行时数据目录搬到别处 ——
只读仓库、多项目共存、打包安装后 site-packages 不可写这三种场景都靠它。）

**不改名、不改默认**：不设任何环境变量时，两个函数的返回值与现有各模块的
推导**逐字相同**（本轮迁移模块时已逐模块用改前公式做过对照）；显式传
`meta_dir=...` 的调用方（records / calllog / export / executor 都有）行为不变。

纯标准库、无副作用（只做字符串运算，不建目录、不读文件）。
"""

__all__ = [
    'repo_root',
    'meta_dir',
    'DEFAULT_REPO_ROOT',
]

import os

# 包目录（.../vools/actus）与不含环境变量的默认仓库根（.../actus）。
# 依赖本文件的位置：<repo_root>/vools/actus/paths.py → 上三级即仓库根。
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.dirname(os.path.dirname(_PACKAGE_DIR))


def repo_root() -> str:
    """仓库根：`ACTUS_REPO_ROOT` 优先，否则按本文件位置上三级推导。

    与 `indexer._repo_root()` 的既有语义一致（那边本轮不切，避免改全局 repo
    根语义；等它切过来时两者返回值已逐字相同）。
    """
    env = os.environ.get('ACTUS_REPO_ROOT')
    if env:
        return env
    return DEFAULT_REPO_ROOT


def meta_dir() -> str:
    """运行时数据目录 `_meta`：`ACTUS_META_DIR` 优先，否则 `repo_root()/_meta`。

    与 `records._default_meta()` / `cost.COSTS_DIR` 的默认分支 / `probe.cache`
    的 `__file__` 推导逐字相同（不设环境变量时）。
    """
    env = os.environ.get('ACTUS_META_DIR')
    if env:
        return env
    return os.path.join(repo_root(), '_meta')
