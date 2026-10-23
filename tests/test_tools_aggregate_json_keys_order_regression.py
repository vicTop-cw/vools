# -*- coding: utf-8 -*-
"""回归测试：aggregate_json_keys 保序去重（BUG-336）。

原实现：

    return list(set(key for keys in keys_list for key in keys))

用 **set** 去重 → 返回顺序由字符串哈希决定，而 Python 默认对 str 做
**PYTHONHASHSEED 随机化**，因此**每次进程运行顺序都可能不同**：

    同一输入 [['id','name','score'], ['name','city','age'], ['score','city']]
    进程1 -> ['name', 'id', 'age', 'score', 'city']
    进程2 -> ['age', 'score', 'id', 'name', 'city']
    进程3 -> ['id', 'score', 'city', 'name', 'age']

下游据此生成的列序/字段序（表结构、SQL SELECT、Excel 表头等）**不可复现**。

修复：改为保序去重（`OrderedDict.fromkeys`），与本文件
`union_ordered_collection` 的口径一致：顺序 = 各键首次出现的先后。
"""

import pytest

from vools.utils.tools import aggregate_json_keys, union_ordered_collection


class TestOrderPreserved:
    def test_first_appearance_order(self):
        keys = [['id', 'name', 'score'], ['name', 'city', 'age'], ['score', 'city']]
        assert aggregate_json_keys(keys) == ['id', 'name', 'score', 'city', 'age']

    def test_single_list_keeps_its_order(self):
        assert aggregate_json_keys([['b', 'a', 'c']]) == ['b', 'a', 'c']

    def test_reverse_input_reflected(self):
        assert aggregate_json_keys([['c', 'b', 'a']]) == ['c', 'b', 'a']

    def test_dedup_within_list(self):
        assert aggregate_json_keys([['a', 'a', 'b', 'a']]) == ['a', 'b']

    def test_empty(self):
        assert aggregate_json_keys([]) == []
        assert aggregate_json_keys([[]]) == []

    def test_matches_union_ordered_collection(self):
        keys = [['id', 'name'], ['name', 'score']]
        flat = [k for sub in keys for k in sub]
        assert aggregate_json_keys(keys) == union_ordered_collection(flat)


class TestDeterminism:
    def test_stable_across_calls(self):
        # 同进程内多次调用结果一致（保序实现天然满足）
        keys = [['z', 'y', 'x'], ['y', 'w']]
        results = {tuple(aggregate_json_keys(keys)) for _ in range(20)}
        assert results == {('z', 'y', 'x', 'w')}

    def test_no_mutation_of_input(self):
        keys = [['a', 'b'], ['b', 'c']]
        snapshot = [list(sub) for sub in keys]
        aggregate_json_keys(keys)
        assert keys == snapshot

    def test_non_ascii_keys_stable(self):
        keys = [['名称', '编号'], ['编号', '城市']]
        assert aggregate_json_keys(keys) == ['名称', '编号', '城市']