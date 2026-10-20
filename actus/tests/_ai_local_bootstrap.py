"""让测试用上**本地源码树**而不是 site-packages 里已安装的 wheel。

为什么需要这个模块
------------------
本仓库 (`vools/actus`) 与核心包 (`vools/`) 是两个独立发版的子项目，
布局是「仓库根下再套一层 `vools/<子包>/`」。当二者都装在同一解释器里时：

    vools.__path__ = [<local-packages>/site-packages/vools,   ← 先被扫到
                      <repo_root>/actus/vools]

`vools` 是 namespace package（两个目录都没有 `__init__.py`），
已安装的 wheel 排在前面，于是 `import vools.actus` 拿到的是 0.7.9
的发布版，**本地改动的代码根本没被加载**。实测症状：
`tests/test_actions_direct.py` 连收集都失败，且
`vools.actus.indexer.__file__` 指向 site-packages。

这意味着在这台机器上直接 `pytest` 得到的结论是假的 ——
既包括本文件的作者遇到的假绿/假红，也包括仓库里其他既有测试。

怎么办
------
把 `vools` 手工装成一个 `__path__` 显式指定的模块，等价于 editable 安装，
但**不改环境**。本模块被每个 `test_ai_*.py` 在顶部导入：

    import _ai_local_bootstrap  # noqa: F401  — 必须在 import vools.actus 之前

路径顺序刻意是「actus 子项目在前、核心包在后」：这样
`vools.actus` 命中本地源码，而 `vools.core` / `vools.bridge`
仍能落到核心包或已安装的 vools-bridges。

环境变量 `VOOLS_ACTUS_NO_BOOTSTRAP=1` 可关闭本行为（用于排查）。

Example:
    >>> install()          # doctest: +SKIP
    >>> import vools.actus.ai   # doctest: +SKIP
"""

import os
import sys
import types

# tests/_ai_local_bootstrap.py → vools/actus → vools(仓库根) → AI(工作区根)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ACTUS_ROOT = os.path.dirname(_HERE)              # .../vools/actus  (本仓库)
_CORE_ROOT = os.path.dirname(_ACTUS_ROOT)         # .../vools         (核心包仓库)

__all__ = ['install', 'local_paths', 'actus_meta_dir']

# 环境变量：显式指定 Actus 仓库的 _meta 目录时优先用它
_ENV_META = 'ACTUS_ACTUS_META_DIR'

# install() 是否已执行过。install() 要动 sys.modules，非幂等会导致
# 类身份断裂（见 install 的 docstring）。
_INSTALLED = False


def actus_meta_dir():
    """定位 Actus 仓库的 `_meta` 目录（动作索引所在处）。

    为什么要找：vools-actus 自己**没有** `actions/` 目录 —— 动作全在
    Actus 仓库里。所以 `indexer.load_index()` 用默认 `_repo_root()` 会扫到
    空目录（实测返回 0 个动作），调用方必须显式传入 Actus 的 `_meta`。

    查找顺序：
      1. 环境变量 `ACTUS_ACTUS_META_DIR`
      2. `<vools 工作区根>/Actus/_meta`（本仓库与核心包通常是兄弟树）

    Returns:
        str: 目录路径；**找不到时返回 None**，由测试决定 skip
        —— 硬编码绝对路径会让测试换个机器就失效。
    """
    env = os.environ.get(_ENV_META)
    if env and os.path.isdir(env):
        return env
    for parent in (os.path.dirname(_CORE_ROOT), _CORE_ROOT):
        candidate = os.path.join(parent, 'Actus', '_meta')
        if os.path.isdir(candidate):
            return candidate
    return None


def local_paths():
    """算出本地源码的候选路径，按查找优先级排列。

    两段的分工：
      - `<核心包仓库>/vools` 提供 `vools.core` / `vools.sql` / ... —— 后查
      - `<本仓库>/vools`      提供 `vools.actus`          —— 先查

    Returns:
        list: 存在的 `vools/` 包目录，actus 子项目在前。
    """
    candidates = [os.path.join(_ACTUS_ROOT, 'vools'),
                  os.path.join(_CORE_ROOT, 'vools')]
    return [p for p in candidates if os.path.isdir(p)]


def install():
    """把 `vools` 重装成显式指定 `__path__` 的模块，使本地源码优先。

    **必须幂等**。pytest 收集 N 个测试文件就会调用 `install()` N 次，
    而本函数要动 `sys.modules`：若不幂等，第二次调用会把已加载的
    `vools.actus.*` 全部删掉重建，于是同一个类在内存里有**两个不同的
    对象**。症状很有迷惑性 —— `pytest.raises(ActionError)` 明明抛了
    ActionError 却没捕获到，因为两边引用的是不同副本。

    Returns:
        bool: True 表示引导已生效（或此前已生效）。
    """
    global _INSTALLED
    if _INSTALLED:
        return True
    if os.environ.get('VOOLS_ACTUS_NO_BOOTSTRAP'):
        return False
    paths = local_paths()
    if not paths:
        return False

    # 已经有人在用 site-packages 的 vools（正常包形态，__init__ 真实存在）时，
    # 不要覆盖成裸 namespace —— 那种情况下本仓库的测试本来就跑不了，
    # 交由上层报错更诚实。
    existing = sys.modules.get('vools')
    if existing is not None and getattr(existing, '__file__', None):
        return False

    # 清掉已导入的 vools.actus*，否则会命中上一次解析到的 wheel
    for name in [k for k in list(sys.modules)
                 if k == 'vools.actus' or k.startswith('vools.actus.')]:
        del sys.modules[name]

    # 保留核心包等非 actus 子模块的既有加载结果
    keep = {k: v for k, v in sys.modules.items()
            if k.startswith('vools.') and not k.startswith('vools.actus')}

    ns = types.ModuleType('vools')
    ns.__path__ = list(paths)
    ns.__package__ = 'vools'
    ns.__doc__ = '由 _ai_local_bootstrap 显式构造的本地源码优先命名空间。'
    sys.modules['vools'] = ns
    sys.modules.update(keep)
    sys.path.insert(0, _ACTUS_ROOT)
    _INSTALLED = True
    return True
