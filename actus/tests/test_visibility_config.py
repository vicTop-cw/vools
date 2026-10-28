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
    """序列化契约：**显式非默认值**必须原样往返（不能两边同一实现自证）。

    审计加固：原来只 `back.to_dict() == orig.to_dict()` —— 同一对
    from_dict/to_dict 两边对称丢字段时仍然相等（变异证明：对称丢掉
    require_signature 字段 → 本文件 30 passed）。现在显式构造非默认值并逐字段断言。
    """
    team = TeamConfig.from_dict({
        "team": "t",
        "members": [{"id": "a", "role": "admin"}, {"id": "b", "role": "viewer"}],
        "require_signature": False,
        "default_trust": "trusted",
    })
    serialized = team.to_dict()
    assert serialized["require_signature"] is False, "to_dict 丢了 require_signature"
    assert serialized["default_trust"] == "trusted", "to_dict 丢了 default_trust"
    assert [m["id"] for m in serialized["members"]] == ["a", "b"]

    back = TeamConfig.from_dict(serialized)
    assert back.require_signature is False, "require_signature 在往返中丢失（对称丢字段会绿）"
    assert back.default_trust == "trusted", "default_trust 在往返中丢失"
    assert back.is_member("a") and back.get_role("a") == "admin"
    assert back.is_admin("a") and not back.is_admin("b")
    assert back.to_dict() == serialized


def test_registry_roundtrip():
    """序列化契约：git/branch/auth/priority 等非默认字段必须原样往返。

    注意对外字段名是 `type`（to_dict/from_dict 的契约键），不是 dataclass 字段名
    `registry_type` —— 这里把**精确字典**也断言出来，防止对外键被悄悄改名。
    """
    orig = RegistryConfig(name="n", url="u", registry_type="git",
                          branch="dev", auth="ssh", priority=7)
    serialized = orig.to_dict()
    assert serialized == {"name": "n", "url": "u", "type": "git",
                          "branch": "dev", "auth": "ssh", "priority": 7}

    back = RegistryConfig.from_dict(serialized)
    assert (back.name, back.url, back.registry_type, back.branch, back.auth,
            back.priority) == ("n", "u", "git", "dev", "ssh", 7)
    assert back.to_dict() == serialized


def test_minimal_dicts_use_defaults():
    """缺省键仍走默认值（不因校验而破坏原有宽松用法）。"""
    r = RegistryConfig.from_dict({"name": "n", "url": "u"})
    assert (r.registry_type, r.branch, r.auth, r.priority) == ("http", "main", "", 0)
    t = TeamConfig.from_dict({"team": "t"})
    assert t.members == [] and t.require_signature is True
    assert t.default_trust == "community"
