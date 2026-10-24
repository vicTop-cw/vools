# -*- coding: utf-8 -*-
"""后端键可表示性检查（BUG-408）。

不同序列化后端对 **映射键** 的表达能力不同：

* ``json`` / ``vb_json``：JSON 规范只允许字符串键 → Python 的 int/float/bool
  键会被 **静默转成字符串**，往返后键类型改变（``{1: 'a'}`` → ``{'1': 'a'}``）；
* ``msgpack``：支持标量键，但 tuple 键会被编码成 array key，读取时
  ``unpackb`` 无法把它变回可哈希对象 → **写得进去、读不回来**
  （``ValueError: list is not allowed for map key``）。

静默改变键类型 / 写读不对称都很难排查，这里在 ``dumps`` 时做一次有界的
键扫描并发出 ``RuntimeWarning``（不改变序列化结果、不破坏既有数据）。

扫描上限 ``MAX_SCAN_NODES`` 防止对巨型载荷做整树遍历拖慢序列化；
超出上限时不再继续找样例（只标记 ``truncated``）。
"""

from typing import Any, List, Tuple

__all__ = ["MAX_SCAN_NODES", "find_non_str_keys", "find_non_scalar_msgpack_keys"]

MAX_SCAN_NODES = 10000


def _walk(obj: Any, check, samples: List[Any], budget: List[int]) -> None:
    """有界递归扫描 dict 键（budget[0] 为剩余节点数）。"""
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if isinstance(obj, dict):
        for k, v in obj.items():
            if budget[0] <= 0:
                return
            if check(k) and len(samples) < 5:
                samples.append(k)
            _walk(k, check, samples, budget)
            _walk(v, check, samples, budget)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            if budget[0] <= 0:
                return
            _walk(item, check, samples, budget)


def find_non_str_keys(obj: Any) -> Tuple[List[Any], bool]:
    """找出 JSON 后端无法表示的非字符串键（最多返回 5 个样例）。"""
    samples: List[Any] = []
    budget = [MAX_SCAN_NODES]
    _walk(obj, lambda k: not isinstance(k, str), samples, budget)
    return samples, budget[0] <= 0


def find_non_scalar_msgpack_keys(obj: Any) -> Tuple[List[Any], bool]:
    """找出 msgpack 读取端无法还原的键（tuple/frozenset 等非标量）。"""
    samples: List[Any] = []
    budget = [MAX_SCAN_NODES]
    _walk(obj, lambda k: isinstance(k, (tuple, frozenset)), samples, budget)
    return samples, budget[0] <= 0
