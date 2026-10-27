"""
pyk - vools 的 PySpark / PostgreSQL 集成子包（**独立分发包**）

安装：``pip install 'vools[pyk]'`` 或 ``pip install vools-pyk``。

设计目标：
- pyk 是 vools 里所有 pyspark / PostgreSQL 相关 API 的**统一入口**。
- **独立分发**：pyk 不随 vools 核心库打包。核心库保持零 pyspark 依赖、轻量。
  通过 PyPI 独立包 ``vools-pyk`` 分发，namespace 包路径为 ``vools/pyk/``
  （配合 vools 的 ``pkgutil.extend_path`` 合并）。
- 纯 Python 部分 (vools.core / vools.data / ...) 不依赖 pyspark；
  只有 pyk 及其子模块才会 import pyspark，保证 vools 核心可以独立安装/运行。
- 用法：``from vools import pyk`` 或 ``import vools.pyk as pyk``。
  兼容旧 vx.py 的用法：``import pyk`` 由外部 sys.path 兜底（见 install_patch）。

子包规划：
    vools.pyk.core       - spark 基础工具 (SparkSession 管理、run_ds、show_*)
    vools.pyk.df         - DataFrame 扩展 (vicDataFrame 及 DataFrame monkey-patch)
    vools.pyk.text       - vicText 的 pyspark 相关扩展 (toDF, 转 DataFrame)
    vools.pyk.tb         - Hive 表元数据 (vicTableInfo, getCols, get_partitions...)
    vools.pyk.compare    - DataFrame 比对 (vicCompare)
    vools.pyk.postgre    - PostgreSQL 辅助 (vicPostgreSupport)
    vools.pyk.look_upon  - LookUpon 任务调度（PostgreSQL 队列，DAG / 跨表依赖 / 重试）
    vools.pyk.tools      - vicTools 聚合类

延迟加载说明：
- 为避免 ``import vools`` 时强制拉起 pyspark（生产环境可能未装/很慢），
  __init__ 里默认不 import pyspark；用户显式 import pyk 子模块时才加载。
- install_patch() 可手动触发 monkey-patch (把方法挂到 DataFrame / SparkSession)。
"""

from __future__ import absolute_import

__all__ = [
    # 版本
    "__version__",
    # 工具函数
    "install_patch",
    "is_available",
    "get_spark",
    # 子模块（懒加载）
    "core",
    "df",
    "text",
    "tb",
    "compare",
    "postgre",
    "cond",
    "patch",
    "configs",
    "look_upon",
    "tools",
]

__version__ = "0.9.0"

import os
import sys
import importlib

_SUBMODULES = (
    "core", "df", "text", "tb", "compare", "postgre", "cond", "patch",
    "configs", "look_upon", "tools",
)


def is_available() -> bool:
    """检查当前环境是否安装了 pyspark 且可导入。

    Returns:
        True 表示 pyspark 可用；False 表示不可用。
    """
    try:
        import pyspark  # noqa: F401
        return True
    except ImportError:
        return False


def get_spark(app_name: str = "pyk_spark", master: str = None, **kwargs):
    """获取或创建全局 SparkSession。

    参数:
        app_name: Spark 应用名，默认 "pyk_spark"
        master:   master URL；None 则交给 pyspark 默认
        **kwargs: 额外 SparkConf 配置项 (如 spark.sql.shuffle.partitions)

    Returns:
        pyspark.sql.SparkSession 实例（单例）
    """
    from .core import get_spark as _get_spark
    return _get_spark(app_name=app_name, master=master, **kwargs)


def install_patch():
    """把 pyk 提供的扩展方法挂到 DataFrame / SparkSession / Column 等原生类型上。

    幂等：重复调用不会重复挂载。

    Returns:
        None
    """
    from .patch import install_patch as _install_patch
    return _install_patch()


# ============================================================
# 子模块懒加载：顶层只注册名称，真正 import 时才拉起 pyspark。
# 之前这里用 `from . import core` 等显式加载，一旦环境无 pyspark，
# `import vools.pyk` 整体崩掉。改为容错懒加载，让 pyk 包本身可导入。
# 注意：**不要**用 `globals()[name] = None` 占位——那会让
# `from vools.pyk import configs` 直接拿到 None 而不触发 __getattr__ 懒加载
# （Python 只在常规属性查找失败时才调用 __getattr__）。
# ============================================================


def __getattr__(name: str):
    """延迟加载 pyk 子模块；无 pyspark 时抛 AttributeError。"""
    if name in _SUBMODULES:
        try:
            module = importlib.import_module(f".{name}", package=__name__)
            globals()[name] = module
            return module
        except Exception as e:
            raise AttributeError(
                f"vools.pyk.{name} 需要 pyspark；请先安装 pyspark。原始错误: {e}"
            )
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list:
    return sorted(set(globals().keys()) | set(__all__))


# Python 3.6 的【已知缺口】（2026-10-17 寻虫 BUG-78）—— 实测后【刻意不补】，理由：
# 模块级 __getattr__ 属 PEP 562（3.7+ 才生效），3.6 下是死函数，所以 __all__ 里
# 这 11 个懒加载名在 py3.6 上【属性访问】与 `from vools.pyk import *` 拿不到
# （`from vools.pyk import core` 这种 from-import 仍可用：importlib 会退回直接
# 导入子模块，实测 py3.6 通过）。
#
# 为什么不照 vools/datetime、vools/sql 的做法补一段 <3.7 主动绑定 —— 代价实测不可接受：
#   ① 补上后 `import vools`（py3.6）由 0.54s 涨到 1.28s：vools/__init__.py 的既有
#      <3.7 分支会连带 import 本包，本包的主动绑定于是被触发，vools.pyk.core 一项
#      就要 1.17s 并把 numpy + pandas 拉进进程（单文件逐个计时实测）。
#   ② 更硬的证据：ABAB 交错对照（各 4 次，且刻意不带 tests/sql 以排除串扰）——
#      tests/task/test_task_complete.py::test_concurrent_submissions 在【补上后
#      4/4 失败、不补 4/4 通过】。该用例自带 20s 预算、本就是记录在案的时序敏感
#      用例（1dc1c1e 因偶发抖动把超时从 5s 放宽到 20s）。用"补一个 3.6 属性访问
#      缺口"去换一个稳定复现的套件回归，是净亏。
# 因此这里维持懒加载语义（与 py3.7+ 一致、不拖重依赖），把缺口如实登记进
# tests/core/test_pep562_py36_convention.py 的显式豁免表与本仓账本，
# 而不是用一个引入回归的"修复"掩盖它。真要补，得先解决 import vools 不连带
# 拉起 pyk 这个问题（属跨模块设计变更，不在寻虫轮授权范围）。