# -*- coding: utf-8 -*-
"""回归测试：cache.persist 的两处缺陷（BUG-345）。

## 1. 非可调用 func 静默接受

    persist("x")      # 返回 wrapper（不报错）；当装饰器用时才在 wrapper 里炸
    @persist("x")     # AttributeError: 'str' object has no attribute '__module__'
    def f(): ...

修复：入口校验 func 必须 callable 或 None（与 once / cache_with_ttl 同口径）。

## 2. 缓存文件"合法 JSON 但缺字段"抛 KeyError

    {"no_result": 1}          # -> KeyError: 'result'
    {"result": 1}             # -> KeyError: 'start_time'/'end_time'（下游）

而"损坏 JSON"（`{not-json`）却是**优雅重算**——同一类坏缓存两种命运。
修复：缺 result/start_time/end_time 任一字段一律按"未命中"处理（重算）。

注意：默认 force_when 是"按天刷新"，所以命中类断言必须写**新鲜时间戳**，
否则会被日刷逻辑判为过期（这是既有正确行为，不是缺陷）。
"""

import json
import os
import time

import pytest

import vools.cache.persist as persist_mod
from vools.cache.persist import persist


@pytest.fixture()
def cache_dir(tmp_path):
    return str(tmp_path)


def _write_cache(cache_dir, key, payload):
    path = os.path.join(cache_dir, f"{key}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


class TestPersistFuncValidation:
    @pytest.mark.parametrize("bad", ["x", 123, 1.5, ["f"]])
    def test_non_callable_func(self, bad):
        with pytest.raises(TypeError) as ei:
            persist(bad)
        assert "func" in str(ei.value)

    def test_none_returns_decorator(self, cache_dir):
        assert callable(persist(None))
        assert callable(persist())


class TestInvalidCacheIsTreatedAsMiss:
    def test_missing_result_key(self, cache_dir):
        calls = []

        @persist(target_folder=cache_dir, file_key="k_missing_result")
        def f():
            calls.append(1)
            return "computed"

        assert f() == "computed"
        _write_cache(cache_dir, "k_missing_result", {"no_result": 1})
        assert f() == "computed"
        assert len(calls) == 2

    def test_missing_timestamps(self, cache_dir):
        calls = []

        @persist(target_folder=cache_dir, file_key="k_missing_ts")
        def f():
            calls.append(1)
            return "computed"

        assert f() == "computed"
        _write_cache(cache_dir, "k_missing_ts", {"result": 1})
        assert f() == "computed"
        assert len(calls) == 2

    def test_corrupted_json(self, cache_dir):
        calls = []

        @persist(target_folder=cache_dir, file_key="k_bad_json")
        def f():
            calls.append(1)
            return "computed"

        assert f() == "computed"
        with open(os.path.join(cache_dir, "k_bad_json.json"), "w", encoding="utf-8") as fh:
            fh.write("{not-json")
        assert f() == "computed"
        assert len(calls) == 2

    def test_non_dict_cache_payload(self, cache_dir):
        @persist(target_folder=cache_dir, file_key="k_list")
        def f():
            return "computed"

        assert f() == "computed"
        _write_cache(cache_dir, "k_list", [1, 2, 3])
        assert f() == "computed"


class TestFreshCacheStillHits:
    def test_hit_uses_cached_value(self, cache_dir):
        calls = []

        @persist(target_folder=cache_dir, file_key="k_hit")
        def f():
            calls.append(1)
            return "computed"

        assert f() == "computed"
        now = time.time()
        _write_cache(
            cache_dir,
            "k_hit",
            {"result": "from-cache", "start_time": now, "end_time": now},
        )
        assert f() == "from-cache"
        assert len(calls) == 1          # 未再执行

    def test_force_bypasses_cache(self, cache_dir):
        calls = []

        @persist(target_folder=cache_dir, file_key="k_force")
        def f():
            calls.append(1)
            return "computed"

        assert f() == "computed"
        now = time.time()
        _write_cache(
            cache_dir,
            "k_force",
            {"result": "from-cache", "start_time": now, "end_time": now},
        )
        assert f(force=True) == "computed"
        assert len(calls) == 2


class TestOtherBehaviourUnchanged:
    def test_default_key_is_stable(self, cache_dir):
        @persist(target_folder=cache_dir)
        def unique_fn_name_for_test():
            return 1

        assert unique_fn_name_for_test() == 1
        # 默认 file_key = sanitize(module + qualname)，只断言其中含函数名（不含模块前缀假设）
        assert any(
            name.endswith(".json") and "unique_fn_name_for_test" in name
            for name in os.listdir(cache_dir)
        ), os.listdir(cache_dir)

    def test_param_fingerprint_separates_args(self, cache_dir):
        """BUG-470：带参函数不同实参必须各自缓存，不能复用首个结果。"""
        calls = []

        @persist(target_folder=cache_dir, file_key="k_args")
        def f(x):
            calls.append(x)
            return x * 10

        assert f(1) == 10
        assert f(2) == 20
        assert f(1) == 10
        assert calls == [1, 2]

    def test_non_json_serializable_return_raises(self, cache_dir):
        @persist(target_folder=cache_dir, file_key="k_obj")
        def f():
            return object()

        with pytest.raises(TypeError):
            f()

    def test_invalid_other_params(self):
        with pytest.raises(TypeError):
            persist(file_key=123)
        with pytest.raises(TypeError):
            persist(target_folder=123)
        with pytest.raises(TypeError):
            persist(force="x")
        with pytest.raises(TypeError):
            persist(force_when=123)
