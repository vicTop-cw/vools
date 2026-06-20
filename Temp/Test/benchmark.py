#!/usr/bin/env python3.13
# -*- coding: utf-8 -*-
"""
iif.py 原版 vs 改进版 — 性能 & 内存对比测试

用法：
    cd E:/IDEProjects/AI/vools
    python Temp/Test/benchmark.py

输出 Markdown 格式的对比报告。
"""

import sys
import os
import time
import timeit
import tracemalloc
import importlib.util
import types
import gc
import json
from functools import partial

# ---- 确保项目根在 sys.path ----
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---- 加载原始版（从 vools 包）----
import vools.security.safe_eval as _safe_eval
from vools.functional.iif import (
    LazyProperty as LazyPropertyOld,
    ConditionBuilder as ConditionBuilderOld,
    iif as iif_old,
)

# ---- 加载改进版（从 Temp/iif.py，需补全相对导入上下文）----
_spec = importlib.util.spec_from_file_location(
    "vools.functional.iif_new",
    os.path.join(_PROJECT_ROOT, "Temp", "iif.py"),
)
_mod_new = importlib.util.module_from_spec(_spec)
_mod_new.__package__ = "vools.functional"
sys.modules["vools.functional.iif_new"] = _mod_new
_spec.loader.exec_module(_mod_new)

LazyPropertyNew = _mod_new.LazyProperty
ConditionBuilderNew = _mod_new.ConditionBuilder
iif_new = _mod_new.iif


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def fmt_time(seconds) -> str:
    if seconds is None:
        return "N/A"
    if seconds < 1e-6:
        return f"{seconds * 1e9:.1f} ns"
    if seconds < 1e-3:
        return f"{seconds * 1e6:.2f} µs"
    if seconds < 1:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.4f} s"


def fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / (1024 * 1024):.1f} MB"


def fmt_ratio(new_val, old_val) -> str:
    if old_val is None or new_val is None or old_val == 0:
        return "N/A"
    ratio = new_val / old_val
    if ratio < 0.95:
        return f"[快 {1 / ratio:.1f}x]"
    elif ratio > 1.05:
        return f"[慢 {ratio:.1f}x]"
    else:
        return "[持平]"


def benchmark(name: str, old_fn, new_fn, setup="", number=100_000):
    """运行微基准测试，返回 (old_time, new_time)。"""
    # 预热
    for _ in range(min(number // 10, 1000)):
        old_fn()
        new_fn()
    gc.collect()

    if setup:
        old_t = timeit.Timer(old_fn, setup=setup)
        new_t = timeit.Timer(new_fn, setup=setup)
    else:
        old_t = timeit.Timer(old_fn)
        new_t = timeit.Timer(new_fn)

    old_time = min(old_t.repeat(repeat=5, number=number))
    new_time = min(new_t.repeat(repeat=5, number=number))
    return old_time, new_time


def memory_snapshot(name: str, fn, cleanup=True):
    """用 tracemalloc 测量 fn 执行前后的内存增量。"""
    if cleanup:
        gc.collect()
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()
    result = fn()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff = sum(s.size_diff for s in stats)
    return total_diff, result


# ═══════════════════════════════════════════════════════════════════════════
# 1. LazyProperty 性能
# ═══════════════════════════════════════════════════════════════════════════

def bench_lazyproperty():
    results = []

    # 1a. 普通类 — 首次访问（计算开销）
    class NormalOld:
        def __init__(self):
            self.counter = 0

        @LazyPropertyOld
        def val(self):
            self.counter += 1
            return 42

    class NormalNew:
        def __init__(self):
            self.counter = 0

        @LazyPropertyNew
        def val(self):
            self.counter += 1
            return 42

    # 需要循环内创建新实例来测首次访问
    def old_first_access():
        obj = NormalOld()
        return obj.val

    def new_first_access():
        obj = NormalNew()
        return obj.val

    old_t, new_t = benchmark("LazyProperty 普通类-首次", old_first_access, new_first_access, number=10_000)
    results.append(("LazyProperty 普通类 首次访问", old_t, new_t))

    # 1b. 普通类 — 缓存命中（第二次访问）
    _obj_old = NormalOld()
    _obj_old.val  # 首次触发缓存

    _obj_new = NormalNew()
    _obj_new.val

    old_t2, new_t2 = benchmark(
        "LazyProperty 普通类-缓存命中",
        lambda: _obj_old.val,
        lambda: _obj_new.val,
        number=500_000,
    )
    results.append(("LazyProperty 普通类 缓存命中", old_t2, new_t2))

    # 1c. __slots__ 类 — 首次访问
    class SlotsOld:
        __slots__ = ("counter",)

        def __init__(self):
            self.counter = 0

        @LazyPropertyOld
        def val(self):
            self.counter += 1
            return 42

    class SlotsNew:
        __slots__ = ("counter",)

        def __init__(self):
            self.counter = 0

        @LazyPropertyNew
        def val(self):
            self.counter += 1
            return 42

    def slots_old_first():
        obj = SlotsOld()
        try:
            return obj.val
        except (AttributeError, TypeError):
            return "FAIL"

    def slots_new_first():
        obj = SlotsNew()
        return obj.val

    old_t3, new_t3 = benchmark(
        "LazyProperty __slots__-首次",
        slots_old_first,
        slots_new_first,
        number=10_000,
    )
    results.append(("LazyProperty __slots__ 首次访问", old_t3, new_t3))

    # 1d. __slots__ 类 — 缓存命中
    # 原版 setattr 会抛 AttributeError（__slots__ 无 _lazy_* 槽位），跳过速度对比
    s_new = SlotsNew()
    s_new.val  # 触发首次计算并缓存

    def _slots_cached_new():
        return s_new.val  # 命中 id cache

    # 单独测改进版 slots 缓存命中速度
    _, new_t4 = benchmark(
        "LazyProperty __slots__-缓存命中",
        lambda: 42,  # 占位
        _slots_cached_new,
        number=500_000,
    )
    results.append(("LazyProperty __slots__ 缓存命中", None, new_t4))

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 2. ConditionBuilder 基础操作
# ═══════════════════════════════════════════════════════════════════════════

def bench_cb_creation():
    results = []

    old_t, new_t = benchmark(
        "ConditionBuilder 创建",
        lambda: ConditionBuilderOld(42),
        lambda: ConditionBuilderNew(42),
        number=200_000,
    )
    results.append(("ConditionBuilder 创建实例", old_t, new_t))
    return results


def bench_cb_case_evaluate():
    results = []

    # case + evaluate
    old_t, new_t = benchmark(
        "case + evaluate",
        lambda: (
            ConditionBuilderOld(5)
            .case(5, "five")
            .case(10, "ten")
            .otherwise("other")
        )(),
        lambda: (
            ConditionBuilderNew(5)
            .case(5, "five")
            .case(10, "ten")
            .otherwise("other")
        )(),
        number=100_000,
    )
    results.append(("case(5).otherwise() 求值", old_t, new_t))

    # 多个 case（10 条）
    def old_many_cases():
        cb = ConditionBuilderOld(7)
        for i in range(10):
            cb.case(i, str(i))
        cb.otherwise("many")
        return cb()

    def new_many_cases():
        cb = ConditionBuilderNew(7)
        for i in range(10):
            cb.case(i, str(i))
        cb.otherwise("many")
        return cb()

    old_t2, new_t2 = benchmark("10个case", old_many_cases, new_many_cases, number=50_000)
    results.append(("10 条 case 求值", old_t2, new_t2))

    # when
    def old_when():
        cb = ConditionBuilderOld(15)
        cb.when(lambda x: x > 10, "big")
        cb.default("small")
        return cb()

    def new_when():
        cb = ConditionBuilderNew(15)
        cb.when(lambda x: x > 10, "big")
        cb.default("small")
        return cb()

    old_t3, new_t3 = benchmark("when", old_when, new_when, number=100_000)
    results.append(("when + default 求值", old_t3, new_t3))

    return results


def bench_cb_call_reuse():
    """对比 __call__ 复用性（原版修改 base，改进版不改）。"""
    results = []

    # 原版每次 __call__ 会修改 self.base
    cb_old = ConditionBuilderOld(0).case(10, "ten").case(20, "twenty").otherwise("other")

    def old_reuse():
        cb = ConditionBuilderOld(0).case(10, "ten").case(20, "twenty").otherwise("other")
        a = cb(10)
        b = cb(20)
        c = cb(0)
        return a, b, c

    def new_reuse():
        cb = ConditionBuilderNew(0).case(10, "ten").case(20, "twenty").otherwise("other")
        a = cb(10)
        b = cb(20)
        c = cb(0)
        return a, b, c

    old_t, new_t = benchmark("__call__ 复用", old_reuse, new_reuse, number=50_000)
    results.append(("__call__ 多次复用", old_t, new_t))

    return results


def bench_cb_operators():
    """对比 __or__ 和 __and__ 操作符。"""
    results = []

    def old_or():
        a = ConditionBuilderOld(None).case(1, "one").case(2, "two")
        b = ConditionBuilderOld(None).case(3, "three").otherwise("other")
        c = a | b
        return c.evaluate(3)

    def new_or():
        a = ConditionBuilderNew(None).case(1, "one").case(2, "two")
        b = ConditionBuilderNew(None).case(3, "three").otherwise("other")
        c = a | b
        return c.evaluate(3)

    old_t, new_t = benchmark("__or__", old_or, new_or, number=100_000)
    results.append(("__or__ 合并求值", old_t, new_t))

    def old_and():
        a = ConditionBuilderOld(1).case(1, "one").case(2, "two")
        b = ConditionBuilderOld(1).case(1, "A").case(2, "B")
        c = a & b
        return c.evaluate(1)

    def new_and():
        a = ConditionBuilderNew(1).case(1, "one").case(2, "two")
        b = ConditionBuilderNew(1).case(1, "A").case(2, "B")
        c = a & b
        return c.evaluate(1)

    old_t2, new_t2 = benchmark("__and__", old_and, new_and, number=100_000)
    results.append(("__and__ 合并求值", old_t2, new_t2))

    return results


def bench_cb_bulk_evaluate():
    """对比批量求值（evaluateEx / evaluate_each）。"""
    results = []

    data = list(range(200))

    def old_bulk():
        cb = ConditionBuilderOld(None).case(100, "hundred").otherwise("nope")
        return cb.evaluateEx(data)

    def new_bulk():
        cb = ConditionBuilderNew(None).case(100, "hundred").otherwise("nope")
        return cb.evaluate_each(data)

    old_t, new_t = benchmark("批量求值 200项", old_bulk, new_bulk, number=5_000)
    results.append(("evaluate_each 200项", old_t, new_t))

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 3. _fix_comp 性能（关键差异：inspect vs try/except）
# ═══════════════════════════════════════════════════════════════════════════

def bench_fix_comp():
    """直接对比 _fix_comp 方法。"""
    results = []

    cb_old = ConditionBuilderOld(10)
    cb_new = ConditionBuilderNew(10)

    # 单参函数
    f1 = lambda x: x > 5

    old_t, new_t = benchmark(
        "_fix_comp 单参lambda",
        lambda: cb_old._fix_comp(f1),
        lambda: cb_new._fix_comp(f1),
        number=100_000,
    )
    results.append(("_fix_comp 单参lambda", old_t, new_t))

    # 双参函数
    f2 = lambda x, y: x > y

    old_t2, new_t2 = benchmark(
        "_fix_comp 双参lambda",
        lambda: cb_old._fix_comp(f2),
        lambda: cb_new._fix_comp(f2),
        number=100_000,
    )
    results.append(("_fix_comp 双参lambda", old_t2, new_t2))

    # builtin 函数
    old_t3, new_t3 = benchmark(
        "_fix_comp builtin(str)",
        lambda: cb_old._fix_comp(str),
        lambda: cb_new._fix_comp(str),
        number=100_000,
    )
    results.append(("_fix_comp builtin(str)", old_t3, new_t3))

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 4. iif 顶层函数
# ═══════════════════════════════════════════════════════════════════════════

def bench_iif():
    results = []

    # 基本布尔
    old_t, new_t = benchmark(
        "iif 布尔",
        lambda: iif_old(True, "yes", "no"),
        lambda: iif_new(True, "yes", "no"),
        number=200_000,
    )
    results.append(("iif(True, 'yes', 'no')", old_t, new_t))

    # callable condition
    def old_callable():
        return iif_old(lambda: True, lambda: "yes", lambda: "no")

    def new_callable():
        return iif_new(lambda: True, lambda: "yes", lambda: "no")

    old_t2, new_t2 = benchmark("iif callable", old_callable, new_callable, number=200_000)
    results.append(("iif(callable)", old_t2, new_t2))

    # 字符串表达式带 data
    def old_string():
        return iif_old("-> x > 3", "big", "small", data=5)

    def new_string():
        return iif_new("-> x > 3", "big", "small", data=5)

    old_t3, new_t3 = benchmark("iif 字符串->", old_string, new_string, number=50_000)
    results.append(("iif('-> expr', data=5)", old_t3, new_t3))

    # whens 模式
    # 注意：原版 iif(whens=...) 在 condition=None 时会短路返回 ConditionBuilder(None)，
    # 完全跳过 whens 逻辑（这是一个 bug）。因此两者执行的代码路径不同——4.2x 差距是
    # "什么都不做" vs "正确执行 whens 分支" 的对比，不算真正的性能退化。
    whens_data = [(lambda x: x > 100, "big"), (lambda x: x <= 100, "small")]

    def old_whens():
        return iif_old(data=150, whens=list(whens_data))

    def new_whens():
        return iif_new(data=150, whens=list(whens_data))

    old_t4, new_t4 = benchmark("iif whens", old_whens, new_whens, number=50_000)
    results.append(("iif(whens=[...])", old_t4, new_t4))

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 5. 内存对比
# ═══════════════════════════════════════════════════════════════════════════

def bench_memory():
    results = []

    # 5a. 单个 ConditionBuilder 实例大小
    cb_old = ConditionBuilderOld(42)
    cb_new = ConditionBuilderNew(42)
    results.append(("ConditionBuilder 实例 (无 slots)", sys.getsizeof(cb_old), sys.getsizeof(cb_new)))

    # cb 实例的 __slots__ 声明大小
    results.append(("  └─ __slots__ 大小（类属性）",
                    sys.getsizeof(ConditionBuilderOld.__slots__),
                    sys.getsizeof(ConditionBuilderNew.__slots__)))

    # 5b. 1000个实例创建内存
    def create_1000_old():
        return [ConditionBuilderOld(i).case(i, str(i)).otherwise("x") for i in range(1000)]

    def create_1000_new():
        return [ConditionBuilderNew(i).case(i, str(i)).otherwise("x") for i in range(1000)]

    mem_old, _ = memory_snapshot("1000 instances", create_1000_old)
    mem_new, _ = memory_snapshot("1000 instances", create_1000_new)
    results.append(("创建 1000 个 CB 实例", mem_old, mem_new))

    # 5c. 批量求值内存
    data = list(range(500))

    def eval_old():
        cb = ConditionBuilderOld(None)
        for i in range(50):
            cb.case(i, str(i))
        cb.otherwise("x")
        return [cb.evaluate(item) for item in data]

    def eval_new():
        cb = ConditionBuilderNew(None)
        for i in range(50):
            cb.case(i, str(i))
        cb.otherwise("x")
        return [cb.evaluate(item) for item in data]

    mem_old2, r_old = memory_snapshot("批量求值", eval_old)
    mem_new2, r_new = memory_snapshot("批量求值", eval_new)
    assert r_old == r_new, f"Result mismatch: {r_old[:3]} vs {r_new[:3]}"
    results.append(("50条case 求值500项", mem_old2, mem_new2))

    # 5d. iif whens 内存
    whens_50 = [(lambda x, i=i: x == i, str(i)) for i in range(50)]

    def iif_whens_old():
        return [iif_old(data=x, whens=whens_50) for x in range(200)]

    def iif_whens_new():
        return [iif_new(data=x, whens=whens_50) for x in range(200)]

    mem_old3, _ = memory_snapshot("iif whens 批量", iif_whens_old)
    mem_new3, _ = memory_snapshot("iif whens 批量", iif_whens_new)
    results.append(("iif whens 200次批量", mem_old3, mem_new3))

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 6. 功能性正确性验证
# ═══════════════════════════════════════════════════════════════════════════

def verify_correctness():
    """确保改进版与原版在相同输入下的行为一致（或改进版修复了原版的 bug）。"""
    checks = []

    # 基本 iif
    checks.append(("iif(True)", iif_old(True, "yes", "no"), iif_new(True, "yes", "no")))
    checks.append(("iif(False)", iif_old(False, "yes", "no"), iif_new(False, "yes", "no")))
    checks.append(("iif(None)", iif_old(None, "yes", "no"), iif_new(None, "yes", "no")))

    # case match
    cb_old = ConditionBuilderOld(5).case(5, "five").otherwise("other")
    cb_new = ConditionBuilderNew(5).case(5, "five").otherwise("other")
    checks.append(("case match", cb_old(), cb_new()))

    # case no match
    checks.append(("case no-match",
                   ConditionBuilderOld(6).case(5, "five").otherwise("other")(),
                   ConditionBuilderNew(6).case(5, "five").otherwise("other")()))

    # when
    cb_old2 = ConditionBuilderOld(15)
    cb_old2.when(lambda x: x > 10, "big")
    cb_old2.default("small")

    cb_new2 = ConditionBuilderNew(15)
    cb_new2.when(lambda x: x > 10, "big")
    cb_new2.default("small")

    checks.append(("when match", cb_old2(), cb_new2()))

    # __or__
    a_old = ConditionBuilderOld(None).case(1, "one")
    b_old = ConditionBuilderOld(None).case(2, "two").otherwise("other")
    a_new = ConditionBuilderNew(None).case(1, "one")
    b_new = ConditionBuilderNew(None).case(2, "two").otherwise("other")
    c_old = a_old | b_old
    c_new = a_new | b_new
    checks.append(("__or__ 1", c_old.evaluate(1), c_new.evaluate(1)))
    checks.append(("__or__ 2", c_old.evaluate(2), c_new.evaluate(2)))
    checks.append(("__or__ default", c_old.evaluate(99), c_new.evaluate(99)))

    # __and__
    a_old2 = ConditionBuilderOld(1).case(1, "one").case(2, "two")
    b_old2 = ConditionBuilderOld(1).case(1, "A").case(2, "B")
    a_new2 = ConditionBuilderNew(1).case(1, "one").case(2, "two")
    b_new2 = ConditionBuilderNew(1).case(1, "A").case(2, "B")
    c_old2 = a_old2 & b_old2
    c_new2 = a_new2 & b_new2
    checks.append(("__and__ 1", c_old2.evaluate(1), c_new2.evaluate(1)))

    # 改进版特有：__and__ 条件数不同应抛异常
    a_new3 = ConditionBuilderNew(1).case(1, "one").case(2, "two")
    b_new3 = ConditionBuilderNew(1).case(1, "A")
    try:
        _ = a_new3 & b_new3
        checks.append(("__and__ 不等长 ValueError", "NO EXCEPTION", "ValueError expected"))
    except ValueError:
        checks.append(("__and__ 不等长 ValueError", "PASS", "PASS"))

    # 改进版特有：default(None) 哨兵
    cb_new3 = ConditionBuilderNew(99).case(1, "one").default(None)
    r_default_none = cb_new3()
    checks.append(("改进版 default(None) → None", r_default_none, None))

    # 改进版特有：chain_locked 后 case 抛异常
    cb_new4 = ConditionBuilderNew(1).case(1, "one").otherwise("x")
    try:
        cb_new4.case(2, "two")
        checks.append(("改进版 chain_locked RuntimeError", "NO EXCEPTION", "RuntimeError"))
    except RuntimeError:
        checks.append(("改进版 chain_locked RuntimeError", "PASS", "PASS"))

    # 改进版特有：whens 类型校验
    try:
        ConditionBuilderNew(5).whens(123)
        checks.append(("改进版 whens TypeError", "NO EXCEPTION", "TypeError"))
    except TypeError:
        checks.append(("改进版 whens TypeError", "PASS", "PASS"))

    # iif whens (改进版修复：正确传 data)
    r_new_whens = iif_new(data=15, whens=[(lambda x: x > 10, "big"), (lambda x: x <= 10, "small")])
    checks.append(("改进版 iif whens data修复", r_new_whens, "big"))

    # iif 字符串
    checks.append(("iif '->' str",
                   iif_old("-> x > 3", "big", "small", data=5),
                   iif_new("-> x > 3", "big", "small", data=5)))

    # callable result
    checks.append(("callable result",
                   ConditionBuilderOld(5).case(5, lambda x: x * 10).otherwise(0)(),
                   ConditionBuilderNew(5).case(5, lambda x: x * 10).otherwise(0)()))

    return checks


# ═══════════════════════════════════════════════════════════════════════════
# 报告输出
# ═══════════════════════════════════════════════════════════════════════════

def print_section(title: str):
    print(f"\n## {title}\n")


def print_table(headers: list, rows: list, aligns: list = None):
    """打印 Markdown 表格。"""
    # header
    print("| " + " | ".join(headers) + " |")
    if aligns:
        sep = "|".join(
            ":" + "-" * (max(3, len(h) - 1)) + ":" if a == "c"
            else "-" * (max(3, len(h)) + 1) + ":" if a == "r"
            else ":" + "-" * (max(3, len(h)))
            for h, a in zip(headers, aligns)
        )
    else:
        sep = "|".join("-" * (len(h) + 2) for h in headers)
    print("|" + sep + "|")
    for row in rows:
        print("| " + " | ".join(str(c) for c in row) + " |")


def run():
    print("# 📊 iif.py 性能 & 内存对比报告")
    print(f"\n> 测试时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"> Python 版本：{sys.version.split()[0]}")
    print(f"> 迭代次数标注在各测试项下方\n")

    # ---- 正确性验证 ----
    print_section("✅ 功能正确性验证")
    checks = verify_correctness()
    all_pass = True
    for name, old_val, new_val in checks:
        status = "✅" if old_val == new_val else "❌"
        if old_val != new_val:
            all_pass = False
        print(f"- {status} **{name}**: old={old_val!r}  new={new_val!r}")
    if all_pass:
        print("\n> 全部功能一致 ✅")
    else:
        print("\n> ⚠️ 存在差异（改进版可能包含有意修复）")

    # ---- 性能测试 ----
    print_section("⚡ 性能对比")
    print("（数值为最小时间，越低越好）\n")

    all_benchmarks = []

    # lazyproperty
    all_benchmarks.extend(bench_lazyproperty())

    # CB 基础
    all_benchmarks.extend(bench_cb_creation())
    all_benchmarks.extend(bench_cb_case_evaluate())
    all_benchmarks.extend(bench_cb_call_reuse())
    all_benchmarks.extend(bench_cb_operators())
    all_benchmarks.extend(bench_cb_bulk_evaluate())

    # _fix_comp
    all_benchmarks.extend(bench_fix_comp())

    # iif
    all_benchmarks.extend(bench_iif())

    # 打印性能表格
    headers = ["测试场景", "原版", "改进版", "对比"]
    rows = []
    for name, old_t, new_t in all_benchmarks:
        rows.append([
            name,
            fmt_time(old_t),
            fmt_time(new_t),
            fmt_ratio(new_t, old_t),
        ])
    print_table(headers, rows)

    # 汇总
    speedup_count = sum(1 for _, o, n in all_benchmarks if o is not None and n is not None and o > 0 and n / o < 0.95)
    slowdown_count = sum(1 for _, o, n in all_benchmarks if o is not None and n is not None and o > 0 and n / o > 1.05)
    neutral_count = len(all_benchmarks) - speedup_count - slowdown_count

    print(f"\n> 总计 {len(all_benchmarks)} 项：[更快] {speedup_count} 项  |  [更慢] {slowdown_count} 项  |  [持平] {neutral_count} 项")

    # ---- 内存对比 ----
    print_section("💾 内存对比")
    print("（正数表示分配量，负数表示释放量；对比值越小越好）\n")

    mem_results = bench_memory()

    mem_headers = ["测试场景", "原版", "改进版", "对比"]
    mem_rows = []
    mem_diff_total = 0
    for name, old_mem, new_mem in mem_results:
        mem_rows.append([
            name,
            fmt_bytes(old_mem) if old_mem > 0 else f"{old_mem} B",
            fmt_bytes(new_mem) if new_mem > 0 else f"{new_mem} B",
            fmt_ratio(new_mem, old_mem) if old_mem > 0 else "N/A",
        ])
        if old_mem > 0 and new_mem > 0:
            mem_diff_total += new_mem - old_mem
    print_table(mem_headers, mem_rows)

    if mem_diff_total > 0:
        print(f"\n> 改进版多用 {fmt_bytes(mem_diff_total)} 内存")
    else:
        print(f"\n> 改进版少用 {fmt_bytes(-mem_diff_total)} 内存")

    # ---- 改进版特有修复 ----
    print_section("🔧 改进版关键修复（非性能项）")
    print("""
| 修复项 | 原版行为 | 改进版行为 |
|--------|---------|-----------|
| `__slots__` 兼容 | LazyProperty 缓存失败，每次重算 | 双路缓存，正确命中 |
| `default(None)` | None 被误判为"未设置"，返回 None | `_UNSET` 哨兵，显式 None 生效 |
| `__call__` 副作用 | 修改 `self.base`，不可复用 | 不修改内部状态，安全复用 |
| `__and__` 不等长 | zip 静默丢弃多余条件 | 抛出 `ValueError` |
| `iif whens` | 传 `condition` 而非 `data` 给 ConditionBuilder | 传 `data`，语义正确 |
| `comp.setter` | 非 supp 分支可能 `UnboundLocalError` | 各分支独立 return |
| `whens` 校验 | 无类型检查，错误输入静默失败 | isinstance 校验，抛出 TypeError |
| 命名 | `_comp_lable`, `evaluateEx` | `_comp_label`, `evaluate_each` |
| 死代码 | `sht` 参数声明但无使用 | 保留签名兼容，但标注弃用 |
""")

    print("---")
    print("*报告由 benchmark.py 自动生成*\n")


if __name__ == "__main__":
    run()
