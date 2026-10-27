# -*- coding: utf-8 -*-
"""回归测试：serialize 对循环引用的错误信息（BUG-344）。

修复前：

    d = {}; d["self"] = d
    dumps(d, "json")      # RecursionError: maximum recursion depth exceeded
    dumps(d, "vb_json")   # 同上
    dumps(d, "msgpack")   # 同上
    # 错误信息完全指不到"数据里有环"，排查成本高；json 标准库自己会报
    # ValueError: Circular reference detected

修复：预处理阶段（codec.vools_preprocess）与 vb_json 后端的 _stringify 都加
**当前路径 id 集合**做环检测，重入即抛 ValueError 说明是循环引用并给处置建议；
离开容器时移除 id，因此"共享但非环"的引用仍可重复序列化。pickle 后端原生支持
循环引用，不受影响。
"""

import pickle

import pytest

import vools.serialize as sr

CYCLE_BACKENDS = ["json", "vb_json", "msgpack"]


def _cyclic_dict():
    d = {}
    d["self"] = d
    return d


def _cyclic_list():
    lst = []
    lst.append(lst)
    return lst


def _deep_cycle():
    nested = {"a": [1, {"b": [2]}]}
    nested["a"][1]["back"] = nested
    return nested


class TestCycleDetectionRaisesValueError:
    @pytest.mark.parametrize("fmt", CYCLE_BACKENDS)
    def test_cyclic_dict(self, fmt):
        with pytest.raises(ValueError) as ei:
            sr.dumps(_cyclic_dict(), fmt)
        assert "循环引用" in str(ei.value)

    @pytest.mark.parametrize("fmt", CYCLE_BACKENDS)
    def test_cyclic_list(self, fmt):
        with pytest.raises(ValueError) as ei:
            sr.dumps(_cyclic_list(), fmt)
        assert "循环引用" in str(ei.value)

    @pytest.mark.parametrize("fmt", CYCLE_BACKENDS)
    def test_deep_cycle(self, fmt):
        with pytest.raises(ValueError):
            sr.dumps(_deep_cycle(), fmt)

    def test_error_is_not_recursion_error(self):
        """明确区分：必须是我们自己的 ValueError，而不是 RecursionError。"""
        with pytest.raises(ValueError):
            try:
                sr.dumps(_cyclic_dict(), "json")
            except RecursionError as exc:      # pragma: no cover - 修复前行为
                pytest.fail(f"仍抛 RecursionError: {exc}")


class TestNoFalsePositive:
    @pytest.mark.parametrize("fmt", ["json", "vb_json", "msgpack"])
    def test_shared_reference_is_not_a_cycle(self, fmt):
        shared = [1, 2]
        out = sr.loads(sr.dumps([shared, shared], fmt), fmt)
        assert out == [[1, 2], [1, 2]]

    @pytest.mark.parametrize("fmt", ["json", "vb_json", "msgpack"])
    def test_repeated_immutable(self, fmt):
        assert sr.loads(sr.dumps(["a", "a", "a"], fmt), fmt) == ["a", "a", "a"]

    @pytest.mark.parametrize("fmt", ["json", "vb_json", "msgpack"])
    def test_nested_containers(self, fmt):
        payload = {"a": [1, {"b": [2, 3]}], "c": (4, 5)}
        assert sr.loads(sr.dumps(payload, fmt), fmt) == {
            "a": [1, {"b": [2, 3]}],
            "c": [4, 5],
        }

    def test_after_failed_cycle_the_path_set_is_clean(self):
        """失败一次后，后续正常序列化不能被残留 id 影响。"""
        with pytest.raises(ValueError):
            sr.dumps(_cyclic_dict(), "json")
        assert sr.loads(sr.dumps({"ok": 1}, "json"), "json") == {"ok": 1}


class TestPickleUnaffected:
    def test_pickle_still_handles_cycles(self):
        d = _cyclic_dict()
        restored = pickle.loads(pickle.dumps(d))
        assert restored["self"] is restored

    def test_vools_pickle_backend_roundtrip(self):
        data = {"a": [1, 2]}
        assert sr.loads(sr.dumps(data, "pickle"), "pickle") == data
