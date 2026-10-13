"""vools.actus.semver 的 pytest 回归（doctest 之外的规范边界锁定）。

semver 已从 Actus engine/actuscore 上移为单一真源，Actus 侧是 module-alias
shim。本文件锁定：非法输入、数值型前导零、预发布 SemVer 优先级、build 元数据
不参与比较、bump 语义，以及（在 Actus 仓库在场时）shim 与 vools 是同一模块。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import semver  # noqa: E402


# ---------- parse ----------

@pytest.mark.parametrize("raw", [
    "", None, "v1.2.3", "1.2", "1.2.x", "01.2.3", "1.02.3", "1.2.3.4",
    " 1.2.3", "1.2.3 ", "1.2.3-", "1.2.3+", "1.2.3-a..b",
])
def test_parse_rejects_invalid(raw):
    with pytest.raises(ValueError):
        semver.parse(raw)


def test_parse_basic_fields():
    v = semver.parse("10.20.30")
    assert (v.major, v.minor, v.patch) == (10, 20, 30)
    assert v.pre == () and v.build is None


def test_parse_prerelease_and_build():
    v = semver.parse("1.2.3-rc.1+build.5")
    assert v.pre == ("rc", "1")
    assert v.build == "build.5"


@pytest.mark.parametrize("pre", ["01", "alpha.01", "1.01"])
def test_numeric_prerelease_no_leading_zero(pre):
    with pytest.raises(ValueError):
        semver.parse("1.0.0-" + pre)


def test_numeric_prerelease_single_zero_allowed():
    assert semver.parse("1.0.0-rc.0").pre == ("rc", "0")


# ---------- compare：SemVer §11 优先级 ----------

@pytest.mark.parametrize("a,b,want", [
    ("1.0.0", "1.0.1", -1),
    ("1.0.1", "1.0.0", 1),
    ("2.0.0", "1.9.9", 1),
    ("1.0.0", "1.0.0", 0),
    ("1.0.0-alpha", "1.0.0", -1),     # 有预发布 < 无预发布
    ("1.0.0-alpha.1", "1.0.0-alpha.2", -1),
    ("1.0.0-alpha.1", "1.0.0-alpha.1.2", -1),  # 更短的字段序列更低
    ("1.0.0-alpha.1", "1.0.0-alpha.beta", -1), # 数字标识符 < 字母
    ("1.0.0-alpha", "1.0.0-alpha.0", -1),
    ("1.0.0-beta", "1.0.0-alpha", 1),
])
def test_compare_precedence(a, b, want):
    assert semver.compare(a, b) == want


def test_build_metadata_ignored_in_precedence():
    assert semver.compare("1.0.0+aaa", "1.0.0+bbb") == 0
    assert semver.compare("1.0.0-rc.1+x", "1.0.0-rc.1+y") == 0


# ---------- bump ----------

@pytest.mark.parametrize("part,want", [
    ("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0"),
])
def test_bump(part, want):
    assert semver.bump("1.2.3", part) == want


def test_bump_drops_prerelease_and_build():
    assert semver.bump("1.2.3-rc.1+build.5", "patch") == "1.2.4"


def test_bump_bad_part_raises():
    with pytest.raises(ValueError):
        semver.bump("1.2.3", "epoch")


# ---------- Actus 侧 module-alias shim 联动（仓库在场时） ----------

def test_actus_engine_shim_is_same_module():
    """engine/actuscore/semver.py 应 alias 到 vools.actus.semver（同一模块对象）。"""
    actus_engine = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "..", "Actus", "engine"))
    actus_engine = os.path.normpath(actus_engine)
    if not os.path.isfile(os.path.join(actus_engine, "actuscore", "semver.py")):
        pytest.skip("独立 Actus 仓库不在本机，跳过 shim 联动测试")
    if actus_engine not in sys.path:
        sys.path.insert(0, actus_engine)
    import actuscore.semver as shim
    assert shim is semver
    assert shim.compare("1.0.0-alpha", "1.0.0") == -1
