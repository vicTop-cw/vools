# -*- coding: utf-8 -*-
"""阶段1：入参七形态的验收（ACTUS_REFACTOR_PLAN §3.2）。

支持：JSON 字面量 / @file / stdin / @url / @action:<id>。
本轮修掉两处安全缺陷并锁定：
  - 白名单语义反了：`if allow_hosts:` 把空列表当成「不校验」⇒ 任何 URL 都能
    下载（与文档『空列表表示禁止所有远程』相反，SSRF 风险）
  - SSL 证书校验被禁用（CERT_NONE + check_hostname=False）⇒ 动作源可被
    中间人替换（供应链风险，计划 §六.3）
"""
import io
import json

import pytest

from vools.actus.resolver import resolve_params_extended


def test_params_json_literal():
    assert resolve_params_extended('{"a": 1}') == {"a": 1}


def test_params_empty():
    assert resolve_params_extended("") == {}
    assert resolve_params_extended("{}") == {}


def test_params_at_file(tmp_path):
    f = tmp_path / "args.json"
    f.write_text(json.dumps({"from_file": True}), encoding="utf-8")
    assert resolve_params_extended("@" + str(f)) == {"from_file": True}


def test_params_at_file_not_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_params_extended("@" + str(f))


# --------------------------------------------------------------------------
# 安全门禁：URL 默认拒绝
# --------------------------------------------------------------------------
def test_params_url_without_whitelist_is_denied():
    """未配置白名单时必须拒（此前会直接去下载）。"""
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@https://example.invalid/a.json")
    assert getattr(exc.value, "code", "") == "remote_host_denied", exc.value


def test_params_bare_url_without_whitelist_is_denied():
    with pytest.raises(Exception) as exc:
        resolve_params_extended("https://example.invalid/a.json")
    assert getattr(exc.value, "code", "") == "remote_host_denied", exc.value


def test_params_url_outside_whitelist_is_denied():
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@https://evil.invalid/a.json",
                                allow_hosts=["example.invalid"])
    assert getattr(exc.value, "code", "") == "remote_host_denied", exc.value


def test_params_url_inside_whitelist_attempts_download():
    """白名单内应放行到下载阶段（本环境 DNS 不通 ⇒ remote_download_failed）。"""
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@https://example.invalid/a.json",
                                allow_hosts=["example.invalid"])
    code = getattr(exc.value, "code", "")
    assert code != "remote_host_denied", "白名单内的主机不应被白名单门禁拦下"
    assert code in ("remote_download_failed", "remote_too_large"), code


# --------------------------------------------------------------------------
# SSL 校验不得被禁用
# --------------------------------------------------------------------------
def test_download_helpers_do_not_disable_ssl_verification():
    """源码级契约：两个下载函数都不得再出现 CERT_NONE / check_hostname=False。"""
    import inspect
    from vools.actus import resolver as r
    for fn in (r._download_url, r._download_json_url):
        src = inspect.getsource(fn)
        assert "CERT_NONE" not in src, "%s 仍在禁用 SSL 证书校验" % fn.__name__
        assert "check_hostname = False" not in src, "%s 仍在禁用主机名校验" % fn.__name__
