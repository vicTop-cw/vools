"""tests/actus/conftest.py — 可选子包 vools.actus 的缺席守卫

`vools.actus` 由**独立分发**的 `vools-actus` 包提供（源码在仓库根的 `actus/`，
安装方式 `pip install -e actus/`），核心包 `vools` 的 pyproject 明确把
`vools.actus*` 排除在打包范围外。

因此在「只装了 vools 核心」的环境里，本目录的 10 个测试模块会各自抛
`ModuleNotFoundError: No module named 'vools.actus'`。过去这 10 个错误发生在
**收集阶段**，会让 `pytest tests/` 整轮中断（Interrupted: 12 errors during
collection）——不只是这 10 个用例没跑，后面所有目录都跑不到。

按本仓既有惯例（`pytest.importorskip`，见 tests/data/test_table.py:59、
tests/serialize/test_serialize_types.py:140），缺席时应**跳过**而不是中断。
这里用目录级 `collect_ignore_glob` 把整个目录在收集阶段排除；装上
vools-actus 后本目录自动恢复参与测试，无需改动。
"""
import pytest

try:  # 装了 vools-actus（含 vools.actus 命名空间）才收集本目录
    import vools.actus  # noqa: F401

    _ACTUS_AVAILABLE = True
except Exception:  # pragma: no cover - 取决于环境是否安装可选子包
    _ACTUS_AVAILABLE = False

if not _ACTUS_AVAILABLE:
    collect_ignore_glob = ["*.py"]
