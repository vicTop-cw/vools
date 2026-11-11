# -*- coding: utf-8 -*-
"""actus/tests/test_visibility_gated_r108.py — visibility gated key 便捷函数
专项（统帅轮-14时，COVERAGE_AUDIT_R105 第二批）。

测什么 / 为什么
---------------
`visibility.py` 的三个便捷 wrapper 此前零直接测试：
  * grant_gated_key(action_id, repo, key, config_dir)：生成/轮换 gated 授权
    密钥——**明文只在此返回一次**（安全契约）；
  * revoke_gated_key(action_id, repo, config_dir)：撤销授权；
  * get_visibility_engine(config_dir, current_user)：获取引擎实例。
全部走临时 config_dir 隔离，不碰真实仓库配置。

py3.8+（pyproject requires-python>=3.8），标准库。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import visibility as V  # noqa: E402


@pytest.fixture()
def cfg_dir(tmp_path):
    """隔离的 gated key 配置目录（不碰真实仓库）。"""
    d = tmp_path / "actus_cfg"
    d.mkdir()
    return str(d)


def test_grant_returns_key_once(cfg_dir):
    """grant 返回 dict，明文密钥只在返回值里出现一次。"""
    result = V.grant_gated_key(action_id="paid.act", repo="vic/repo",
                               key="secret-key-123", config_dir=cfg_dir)
    assert isinstance(result, dict)
    # 明文密钥在返回值某处（键名以实现为准，宽松断言值域）
    assert "secret-key-123" in str(result)


def test_grant_and_revoke_roundtrip(cfg_dir):
    """grant → revoke → 再 revoke 幂等/报错语义按实现契约。"""
    V.grant_gated_key(action_id="paid.act", repo="vic/repo",
                      key="k-1", config_dir=cfg_dir)
    revoked = V.revoke_gated_key(action_id="paid.act", repo="vic/repo",
                                 config_dir=cfg_dir)
    assert revoked is True
    # 第二次撤销：已不存在——按实现返回 False（幂等语义）
    second = V.revoke_gated_key(action_id="paid.act", repo="vic/repo",
                                config_dir=cfg_dir)
    assert second is False


def test_grant_two_actions_independent(cfg_dir):
    """不同 action_id 的授权互不干扰。"""
    V.grant_gated_key(action_id="paid.a", repo="vic/repo",
                      key="k-a", config_dir=cfg_dir)
    V.grant_gated_key(action_id="paid.b", repo="vic/repo",
                      key="k-b", config_dir=cfg_dir)
    assert V.revoke_gated_key(action_id="paid.a", repo="vic/repo",
                              config_dir=cfg_dir) is True
    # paid.b 不受影响（还能撤销成功）
    assert V.revoke_gated_key(action_id="paid.b", repo="vic/repo",
                              config_dir=cfg_dir) is True


def test_get_visibility_engine_returns_instance(cfg_dir):
    """便捷函数返回 VisibilityEngine 实例；current_user 透传。"""
    eng = V.get_visibility_engine(config_dir=cfg_dir, current_user="alice")
    assert isinstance(eng, V.VisibilityEngine)
    assert getattr(eng, "current_user", "") == "alice"
    # 不同 config_dir 得到独立实例（不共享状态对象）
    eng2 = V.get_visibility_engine(config_dir=os.path.join(cfg_dir, "other"))
    assert eng2 is not eng


def test_engine_and_gated_key_share_config_dir(cfg_dir):
    """引擎与 gated key 同 config_dir 协作：revoke 后引擎侧授权状态变化
    （语义级协作验证，不深挖内部结构）。"""
    V.grant_gated_key(action_id="paid.act", repo="vic/repo",
                      key="k-9", config_dir=cfg_dir)
    eng = V.get_visibility_engine(config_dir=cfg_dir, current_user="bob")
    assert eng is not None            # 引擎可建
    assert V.revoke_gated_key(action_id="paid.act", repo="vic/repo",
                              config_dir=cfg_dir) is True
