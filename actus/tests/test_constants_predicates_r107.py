# -*- coding: utf-8 -*-
"""actus/tests/test_constants_predicates_r107.py — constants 谓词族专项（统帅轮-13时）。

测什么 / 为什么
---------------
`constants.py` 的 6 个零覆盖判定谓词（COVERAGE_AUDIT_R105 锁定，单一真源，
validate.py 复用）——闭集枚举误判会直接污染 schema 校验/资产池治理：
  * is_known_license / is_known_pricing / is_known_declared_feature：
    闭集 + lower() 归一（'MIT'/'MIT ' 空白尾不在集内——大小写归一但不 trim）；
  * is_namespaced_id：两段点分小写反向域名风格（首段字母开头，段内可下划线数字）；
  * is_testish_id：按 '.' 分段后命中 testish 片段（test/generated/foo/example/bar）；
  * is_secret_sensitive_name：敏感凭据字样正则族（password/token/api[_-]?key...）。

py3.8+（pyproject requires-python>=3.8），标准库。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.constants import (  # noqa: E402
    is_known_declared_feature,
    is_known_license,
    is_known_pricing,
    is_namespaced_id,
    is_secret_sensitive_name,
    is_testish_id,
)


# ---------------------------------------------------------------------------
# is_known_license
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["mit", "apache-2.0", "gpl-3.0", "cc0",
                                   "proprietary", "custom", "MIT", "Apache-2.0"])
def test_license_known_values(value):
    assert is_known_license(value) is True


@pytest.mark.parametrize("value", ["gpl2", "wtfpl", "", "mit ", " unknown"])
def test_license_unknown_values(value):
    """'mit '（尾空白）与 ' unknown'（前空白）不在集内——lower 归一不 trim。"""
    assert is_known_license(value) is False


# ---------------------------------------------------------------------------
# is_known_pricing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["free", "paid", "subscription", "FREE"])
def test_pricing_known_values(value):
    assert is_known_pricing(value) is True


@pytest.mark.parametrize("value", ["freemium", "pay-per-use", "", "Paid "])
def test_pricing_unknown_values(value):
    assert is_known_pricing(value) is False


# ---------------------------------------------------------------------------
# is_known_declared_feature
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "network-access", "file-write", "state-persist",
    "third-party-api", "ui-automation", "Network-Access",
])
def test_feature_known_values(value):
    assert is_known_declared_feature(value) is True


@pytest.mark.parametrize("value", ["network", "file-read", "", "file-write "])
def test_feature_unknown_values(value):
    assert is_known_declared_feature(value) is False


# ---------------------------------------------------------------------------
# is_namespaced_id（两段点分小写反向域名）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "actus.basics.calculator",   # 三段
    "core.add",                  # 两段
    "my_pool.group.item",        # 段内下划线数字合法
    "a.b",                       # 最短合法
])
def test_namespaced_id_valid(value):
    assert is_namespaced_id(value) is True


@pytest.mark.parametrize("value", [
    "single",           # 无点分 → 不合法
    "Core.add",         # 段首大写
    ".leading",         # 空首段
    "trailing.",        # 空尾段
    "1abc.def",         # 段以数字开头
    "",                 # 空
    None,               # None 防御（str() 归一）
])
def test_namespaced_id_invalid(value):
    assert is_namespaced_id(value) is False


# ---------------------------------------------------------------------------
# is_testish_id（按段命中 testish 片段）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "demo.test.target",      # test 段
    "x.generated.y",         # generated 段
    "a.foo.b",               # foo 段
    "some.example.here",     # example 段
    "bar.baz",               # bar 首段
    "TEST.segment",          # 大写归一后命中
])
def test_testish_id_hits(value):
    assert is_testish_id(value) is True


@pytest.mark.parametrize("value", [
    "actus.basics.calculator",   # 干净 id
    "contest.target",            # 'test' 是子串但**整段不等于**——按段判定不算
    "",                          # 空
    None,                        # None 防御
])
def test_testish_id_clean(value):
    assert is_testish_id(value) is False


# ---------------------------------------------------------------------------
# is_secret_sensitive_name（敏感凭据字样正则族）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "GITHUB_TOKEN", "MY_API_KEY", "api-key", "db_password", "passwd",
    "client_secret", "ACCESSKEY", "private-key", "aws_credentials", "pwd",
])
def test_secret_sensitive_hits(name):
    assert is_secret_sensitive_name(name) is True


@pytest.mark.parametrize("name", [
    "HOME", "PATH", "username", "config_path", "locale", "verbosity",
])
def test_secret_sensitive_clean(name):
    assert is_secret_sensitive_name(name) is False


def test_secret_sensitive_none_safe():
    """None 防御（str() 归一）——不抛错返回 False。"""
    assert is_secret_sensitive_name(None) is False
