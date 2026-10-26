# -*- coding: utf-8 -*-
"""配置反序列化的边界（扫 visibility.py 发现）。

缺陷：三个 `from_dict` 全是裸 `d.get(...)`，且字段值零校验：
  1. 非 dict 输入 → 裸 `AttributeError: 'NoneType' object has no attribute 'get'`
  2. `members` 传字符串 → **逐字符迭代**后炸；传 [None]/[123] 同样裸 AttributeError
  3. **空 user_id 成为合法成员** → `is_member('')` 为 True、`get_role('')` 有角色
  4. `role='superadmin'` 拼错**静默收下** → `is_admin` 为 False，权限静默消失
  5. `priority='high'` 收下 → 注册表排序时才炸
"""
import pytest

from vools.actus.visibility import (MEMBER_ROLES, RegistryConfig, TeamConfig,
                                    TeamMember)


# --------------------------------------------------------------------------
# 非 dict 输入
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, "x", [], 123])
def test_registry_rejects_non_dict(bad):
    with pytest.raises(ValueError) as exc:
        RegistryConfig.from_dict(bad)
    assert "需要 dict" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", [None, "x", [], 123])
def test_team_rejects_non_dict(bad):
    with pytest.raises(ValueError) as exc:
        TeamConfig.from_dict(bad)
    assert "需要 dict" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", [None, "x", [], 123])
def test_member_rejects_non_dict(bad):
    with pytest.raises(ValueError) as exc:
        TeamMember.from_dict(bad)
    assert "需要 dict" in str(exc.value), exc.value


# --------------------------------------------------------------------------
# members 形态
# --------------------------------------------------------------------------
def test_members_must_be_list():
    with pytest.raises(ValueError) as exc:
        TeamConfig.from_dict({"members": "abc"})
    assert "必须是列表" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", [[None], [123], ["str"]])
def test_member_items_must_be_dict(bad):
    with pytest.raises(ValueError) as exc:
        TeamConfig.from_dict({"members": bad})
    assert "需要 dict" in str(exc.value), exc.value


# --------------------------------------------------------------------------
# 字段值校验
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad_id", ["", "   ", None, 123])
def test_member_id_must_be_non_empty_str(bad_id):
    """空 id 会让 is_member('') 命中，必须拒绝。"""
    with pytest.raises(ValueError) as exc:
        TeamMember.from_dict({"id": bad_id})
    assert "非空字符串" in str(exc.value), exc.value


def test_member_role_whitelist():
    """拼错的角色必须报错（否则权限静默消失）。"""
    with pytest.raises(ValueError) as exc:
        TeamMember.from_dict({"id": "bob", "role": "superadmin"})
    assert "role" in str(exc.value).lower(), exc.value
    for role in sorted(MEMBER_ROLES):
        assert TeamMember.from_dict({"id": "bob", "role": role}).role == role


def test_priority_must_be_int():
    with pytest.raises(ValueError) as exc:
        RegistryConfig.from_dict({"name": "n", "url": "u", "priority": "high"})
    assert "必须是整数" in str(exc.value), exc.value


def test_priority_bool_rejected():
    """bool 是 int 的子类，但配置里 True 不是优先级。"""
    with pytest.raises(ValueError):
        RegistryConfig.from_dict({"priority": True})


def test_require_signature_must_be_bool():
    with pytest.raises(ValueError) as exc:
        TeamConfig.from_dict({"team": "t", "require_signature": "yes"})
    assert "布尔" in str(exc.value), exc.value


@pytest.mark.parametrize("field,value", [("name", 1), ("url", None), ("type", 2)])
def test_registry_str_fields(field, value):
    with pytest.raises(ValueError) as exc:
        RegistryConfig.from_dict({field: value})
    assert "必须是字符串" in str(exc.value), exc.value


# --------------------------------------------------------------------------
# 合法路径不回归
# --------------------------------------------------------------------------
def test_team_roundtrip():
    orig = TeamConfig(name="t", members=[TeamMember(user_id="a", role="admin"),
                                         TeamMember(user_id="b", role="viewer")])
    back = TeamConfig.from_dict(orig.to_dict())
    assert back.to_dict() == orig.to_dict()
    assert back.is_member("a") and back.get_role("a") == "admin"
    assert back.is_admin("a") and not back.is_admin("b")


def test_registry_roundtrip():
    orig = RegistryConfig(name="n", url="u", registry_type="git",
                          branch="dev", auth="ssh", priority=5)
    back = RegistryConfig.from_dict(orig.to_dict())
    assert back.to_dict() == orig.to_dict()


def test_minimal_dicts_use_defaults():
    """缺省键仍走默认值（不因校验而破坏原有宽松用法）。"""
    r = RegistryConfig.from_dict({"name": "n", "url": "u"})
    assert (r.registry_type, r.branch, r.auth, r.priority) == ("http", "main", "", 0)
    t = TeamConfig.from_dict({"team": "t"})
    assert t.members == [] and t.require_signature is True
    assert t.default_trust == "community"
