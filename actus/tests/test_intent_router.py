# -*- coding: utf-8 -*-
"""IntentRouter 的入参校验（扫 intent.py 发现）。

缺陷：公开方法全是零校验——
  1. `set_ready_ids('abc')` → `set()` **逐字符拆开**成 {'a','b','c'}
     （与 BUG-490/492 的 `args='abc'` 同族）
  2. `set_ready_ids(123)` → 裸 TypeError
  3. `register_action(None, 'd')` → 注册出 **id 为 None** 的动作
  4. `register_action(tags='abc')` → tags 存成字符串，后续遍历逐字符
  5. `set_keyword_map(None/[])` → 收下，直到 `route()` 访问 `.items()` 才裸抛
  6. `route(None/123)` → 裸 `AttributeError: 'int' object has no attribute 'lower'`
"""
import pytest

from vools.actus.intent import IntentRouter


@pytest.fixture()
def router():
    return IntentRouter()


# --------------------------------------------------------------------------
# set_ready_ids
# --------------------------------------------------------------------------
def test_ready_ids_string_rejected(router):
    """字符串会被逐字符拆开，必须拒绝。"""
    with pytest.raises(TypeError) as exc:
        router.set_ready_ids("abc")
    assert "逐字符" in str(exc.value), exc.value


def test_ready_ids_non_iterable_rejected(router):
    with pytest.raises(TypeError) as exc:
        router.set_ready_ids(123)
    assert "可迭代" in str(exc.value), exc.value


def test_ready_ids_rejects_empty_id(router):
    with pytest.raises(ValueError):
        router.set_ready_ids(["a.x", ""])


def test_ready_ids_valid(router):
    assert router.set_ready_ids(["a.x", "b.y"]) is router
    assert router._ready_ids == {"a.x", "b.y"}
    assert router.set_ready_ids(None)._ready_ids is None


# --------------------------------------------------------------------------
# register_action / register_workflow
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad_id", [None, "", "   ", 123])
def test_register_action_rejects_bad_id(router, bad_id):
    with pytest.raises(ValueError) as exc:
        router.register_action(bad_id, "desc")
    assert "非空字符串" in str(exc.value), exc.value


def test_register_action_rejects_bad_description(router):
    with pytest.raises(TypeError):
        router.register_action("a.x", None)


def test_register_action_rejects_string_tags(router):
    """tags 传字符串会被逐字符展开。"""
    with pytest.raises(TypeError) as exc:
        router.register_action("a.x", "d", tags="abc")
    assert "逐字符" in str(exc.value), exc.value


def test_register_action_rejects_non_str_tag_items(router):
    with pytest.raises(TypeError):
        router.register_action("a.x", "d", tags=["ok", 123])


def test_register_action_valid(router):
    router.register_action("a.x", "desc", usage="u", tags=["t1", "t2"])
    rec = router.list_actions()[-1]
    assert rec == {"id": "a.x", "description": "desc", "usage": "u",
                   "tags": ["t1", "t2"]}


@pytest.mark.parametrize("bad_id", [None, "", 123])
def test_register_workflow_rejects_bad_id(router, bad_id):
    with pytest.raises(ValueError):
        router.register_workflow(bad_id, "desc")


def test_register_workflow_valid(router):
    router.register_workflow("wf.x", "desc", tags=["t"])
    assert router.list_workflows()[-1]["id"] == "wf.x"


# --------------------------------------------------------------------------
# set_keyword_map
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, [], 123, "abc"])
def test_keyword_map_must_be_dict(router, bad):
    with pytest.raises(TypeError) as exc:
        router.set_keyword_map(bad)
    assert "必须是 dict" in str(exc.value), exc.value


def test_keyword_map_rejects_non_str_values(router):
    with pytest.raises(TypeError):
        router.set_keyword_map({"a": 1})


def test_keyword_map_valid_and_routes(router):
    router.register_action("a.x", "计算器")
    router.set_keyword_map({"计算": "a.x"})
    r = router.route("帮我计算一下")
    assert r["match"] == "keyword"
    assert r["action_id"] == "a.x"


# --------------------------------------------------------------------------
# route
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, 123, [], {}])
def test_route_rejects_non_str_query(router, bad):
    with pytest.raises(TypeError) as exc:
        router.route(bad)
    assert "必须是字符串" in str(exc.value), exc.value


def test_route_empty_query_keeps_existing_behavior(router):
    """空查询仍返回 match=none + 中文原因（既有行为不变）。"""
    r = router.route("   ")
    assert r["match"] == "none" and r["action_id"] is None
    assert r["reason"] == "空查询"


def test_route_no_match(router):
    r = router.route("完全无关的内容")
    assert r["match"] == "none" and r["action_id"] is None
