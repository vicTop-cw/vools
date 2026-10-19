# -*- coding: utf-8 -*-
"""回归测试：TimedCache 驱逐逻辑（BUG-210）。

原 `TimedCache.set` 先判 `len >= max_size` 就 `popitem`、后写入：
- `max_size=0`/负数时任何 set 都对空缓存 popitem → KeyError（缓存不可用）；
- 覆盖既有 key（容量未涨）也误踢 LRU 头部无辜条目。

修复：`__init__` 拒绝非正整数 max_size（ValueError，与 memorize 的
duration<=0 口径一致）；`set` 更新既有 key 走覆写+move_to_end（不驱逐），
仅新增且满员时 while 驱逐最旧；构造后 max_size 被改小到 0 的退化形状
不崩不写。
"""

import pickle

import pytest

from vools.cache.memorize import TimedCache, _MISS, memorize


class TestMaxSizeValidation:
    """非法 max_size 构造时显式拒绝（BUG-210 ①②）。"""

    @pytest.mark.parametrize("bad", [0, -1, -100, 1.5, "10", True, None])
    def test_invalid_raises(self, bad):
        with pytest.raises(ValueError):
            TimedCache(max_size=bad)

    def test_valid_construction(self):
        c = TimedCache(max_size=1)
        c.set("a", 1)
        assert c.get("a", 999) == 1


class TestUpdateDoesNotEvict:
    """覆盖既有 key 不得驱逐无辜条目（BUG-210 ③）。"""

    def test_overwrite_keeps_others(self):
        c = TimedCache(max_size=2)
        c.set("x", 1)
        c.set("y", 2)
        c.set("y", 99)  # 纯更新，容量未涨
        assert c.get("x", 999) is not _MISS, "无辜头部条目被更新驱逐"
        assert c.get("y", 999) == 99
        assert len(c) == 2

    def test_evict_oldest_on_full_new_key(self):
        c = TimedCache(max_size=2)
        c.set("k1", 1)
        c.set("k2", 2)
        c.get("k1", 999)          # k1 移到队尾 → k2 成为最旧
        c.set("k3", 3)            # 新增满员 → 应驱逐 k2
        assert c.get("k1", 999) is not _MISS
        assert c.get("k2", 999) is _MISS
        assert c.get("k3", 999) is not _MISS


class TestDegenerateDefense:
    """构造后 max_size 被改小的退化形状不崩（防御分支）。"""

    def test_post_shrink_to_zero_survives(self):
        c = TimedCache(max_size=2)
        c.set("a", 1)
        c._max_size = 0  # 内部属性直改（模拟外部滥用）
        c.set("b", 2)    # 旧实现：KeyError: dictionary is empty
        # 退化语义：不崩即可（本分支不承诺写入）


class TestPickleRoundTrip:
    """BUG-146 修复不受影响：合法实例 pickle 往返可用。"""

    def test_roundtrip(self):
        c = TimedCache(max_size=3)
        c.set("p", {"v": 1})
        c2 = pickle.loads(pickle.dumps(c))
        assert c2.get("p", 999) == {"v": 1}
        assert c2._max_size == 3


class TestMemorizeUnaffected:
    """装饰器主链路不受影响。"""

    def test_basic_cache_hit(self):
        n = []

        @memorize(duration=30)
        def f(x):
            n.append(x)
            return x * 2

        assert f(2) == 4
        assert f(2) == 4
        assert len(n) == 1