# -*- coding: utf-8 -*-
"""回归测试：@persist 的缓存键必须包含调用参数（BUG-470）。

修复前缓存文件名**只有函数名/file_key**，调用参数完全不参与：

    @persist(target_folder=tmp)
    def compute(x):
        return x * 2

    compute(3)    # -> 6   （计算并写 compute.json）
    compute(99)   # -> 6   （直接命中同一缓存文件 —— 静默错值！）

修复后带参调用会在文件名后追加 (args, kwargs) 的稳定短哈希；**零参调用保持
原文件名**，因此最常见的 ``fetch_data()`` 形态与既有缓存完全兼容。
"""

import os

import pytest

import vools.cache as ca


def _json_files(folder):
    return sorted(f for f in os.listdir(folder) if f.endswith(".json"))


class TestArgsIncludedInKey:
    def test_different_positional_args(self, tmp_path):
        calls = []

        @ca.persist(target_folder=str(tmp_path))
        def compute(x):
            calls.append(x)
            return x * 2

        assert compute(3) == 6
        assert compute(3) == 6          # 命中缓存
        assert calls == [3]
        assert compute(4) == 8          # 修复前会错误地返回 6
        assert compute(99) == 198
        assert calls == [3, 4, 99]

    def test_different_keyword_args(self, tmp_path):
        calls = []

        @ca.persist(target_folder=str(tmp_path))
        def kwfn(*, a=0):
            calls.append(a)
            return a

        assert kwfn(a=1) == 1
        assert kwfn(a=2) == 2
        assert calls == [1, 2]

    def test_explicit_file_key_still_distinguishes_args(self, tmp_path):
        """显式 file_key 也不能把所有参数混成同一个缓存。"""
        calls = []

        @ca.persist(target_folder=str(tmp_path), file_key="fixed")
        def compute(x):
            calls.append(x)
            return x * 2

        assert compute(3) == 6
        assert compute(42) == 84
        assert calls == [3, 42]


class TestZeroArgBackwardCompatible:
    def test_zero_arg_keeps_plain_file_name(self, tmp_path):
        calls = []

        @ca.persist(target_folder=str(tmp_path), file_key="zero_arg")
        def fetch():
            calls.append(1)
            return {"v": 1}

        assert fetch() == {"v": 1}
        assert fetch() == {"v": 1}
        assert calls == [1]
        assert "zero_arg.json" in _json_files(tmp_path)

    def test_default_key_uses_module_qualname(self, tmp_path):
        @ca.persist(target_folder=str(tmp_path))
        def no_args():
            return 1

        assert no_args() == 1
        files = _json_files(tmp_path)
        assert len(files) == 1
        assert "_" in files[0]          # module.qualname 形态（BUG-112）


class TestForceStillWorks:
    def test_force_recomputes(self, tmp_path):
        calls = []

        @ca.persist(target_folder=str(tmp_path))
        def compute(x):
            calls.append(x)
            return x * 2

        assert compute(3) == 6
        assert compute(3, force=True) == 6
        assert calls == [3, 3]


class TestParamValidationUnchanged:
    @pytest.mark.parametrize("kwargs", [
        {"file_key": 123}, {"force": "yes"}, {"force_when": 123}, {"target_folder": 123},
    ])
    def test_bad_params_loud(self, kwargs):
        with pytest.raises(TypeError):
            ca.persist(**kwargs)
