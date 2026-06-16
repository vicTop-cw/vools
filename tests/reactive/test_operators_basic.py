"""Test basic transform/filter operators: map, filter, flat_map, etc."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from vools.reactive import Observable, ops, Subject

# ==================== map ====================

def test_map():
    result = []
    Observable.of(1, 2, 3).pipe(ops.map(lambda x: x * 10)).subscribe(on_next=lambda x: result.append(x))
    assert result == [10, 20, 30]

def test_map_error_propagation():
    err = [None]
    def failing(x):
        raise ValueError(f"bad {x}")
    Observable.of(1, 2).pipe(ops.map(failing)).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    assert isinstance(err[0], ValueError)

# ==================== filter ====================

def test_filter():
    result = []
    Observable.of(1, 2, 3, 4, 5).pipe(ops.filter(lambda x: x % 2 == 0)).subscribe(on_next=lambda x: result.append(x))
    assert result == [2, 4]

# ==================== flat_map ====================

def test_flat_map():
    result = []
    Observable.of(1, 2).pipe(
        ops.flat_map(lambda x: Observable.from_iterable([x, x * 10]))
    ).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 10, 2, 20]

# ==================== concat_map ====================

def test_concat_map():
    result = []
    Observable.of(1, 2).pipe(
        ops.concat_map(lambda x: Observable.from_iterable([x, -x]))
    ).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, -1, 2, -2]

# ==================== switch_map ====================

def test_switch_map():
    """switch_map 在 new inner 时取消旧的"""
    result = []
    subj = Subject()
    subj.pipe(
        ops.switch_map(lambda x: Observable.from_iterable([x, x * 10]))
    ).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_next(2)
    subj.on_completed()
    assert result == [1, 10, 2, 20] or result == [2, 20]  # 2可能覆盖1的inner

# ==================== take ====================

def test_take():
    result = []
    Observable.from_range(100).pipe(ops.take(3)).subscribe(on_next=lambda x: result.append(x))
    assert result == [0, 1, 2]

def test_take_completes():
    completed = [False]
    Observable.from_range(100).pipe(ops.take(3)).subscribe(
        on_next=lambda x: None, on_completed=lambda: completed.__setitem__(0, True))
    assert completed[0]

def test_take_zero():
    result = []
    Observable.of(1, 2, 3).pipe(ops.take(0)).subscribe(on_next=lambda x: result.append(x))
    assert result == []

# ==================== skip ====================

def test_skip():
    result = []
    Observable.of(1, 2, 3, 4).pipe(ops.skip(2)).subscribe(on_next=lambda x: result.append(x))
    assert result == [3, 4]

# ==================== first ====================

def test_first():
    result = []
    Observable.of(10, 20, 30).pipe(ops.first()).subscribe(on_next=lambda x: result.append(x))
    assert result == [10]

def test_first_with_predicate():
    result = []
    Observable.of(1, 2, 3, 4, 5).pipe(ops.first(lambda x: x > 3)).subscribe(on_next=lambda x: result.append(x))
    assert result == [4]

# ==================== last ====================

def test_last():
    result = []
    Observable.of(1, 2, 3).pipe(ops.last()).subscribe(on_next=lambda x: result.append(x))
    assert result == [3]

def test_last_with_predicate():
    result = []
    Observable.of(1, 2, 3, 4).pipe(ops.last(lambda x: x < 4)).subscribe(on_next=lambda x: result.append(x))
    assert result == [3]

# ==================== distinct ====================

def test_distinct():
    result = []
    Observable.of(1, 2, 2, 3, 1, 3).pipe(ops.distinct()).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3]

# ==================== element_at ====================

def test_element_at():
    result = []
    Observable.of(10, 20, 30).pipe(ops.element_at(1)).subscribe(on_next=lambda x: result.append(x))
    assert result == [20]

# ==================== take_while ====================

def test_take_while():
    result = []
    Observable.of(1, 2, 3, 4, 5).pipe(ops.take_while(lambda x: x < 4)).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3]

# ==================== skip_while ====================

def test_skip_while():
    result = []
    Observable.of(1, 2, 3, 4, 5).pipe(ops.skip_while(lambda x: x < 3)).subscribe(on_next=lambda x: result.append(x))
    assert result == [3, 4, 5]

# ==================== distinct_until_changed ====================

def test_distinct_until_changed():
    result = []
    Observable.of(1, 1, 2, 2, 3, 1).pipe(ops.distinct_until_changed()).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3, 1]

# ==================== group_by ====================

def test_group_by():
    groups = []
    Observable.of(1, 2, 3, 4).pipe(ops.group_by(lambda x: x % 2)).subscribe(
        on_next=lambda g: groups.append(g))
    assert len(groups) == 2

# ==================== scan ====================

def test_scan():
    result = []
    Observable.of(1, 2, 3).pipe(ops.scan(lambda acc, x: acc + x, 0)).subscribe(on_next=lambda x: result.append(x))
    assert result == [0, 1, 3, 6]  # scan 发射初始值和每个累加结果

# ==================== reduce ====================

def test_reduce():
    result = []
    Observable.of(1, 2, 3).pipe(ops.reduce(lambda acc, x: acc + x, 0)).subscribe(on_next=lambda x: result.append(x))
    assert result == [6]

def test_reduce_no_initial():
    result = []
    Observable.of(5, 6).pipe(ops.reduce(lambda acc, x: acc + x)).subscribe(on_next=lambda x: result.append(x))
    assert result == [11]

# ==================== count ====================

def test_count():
    result = []
    Observable.of(1, 2, 3).pipe(ops.count()).subscribe(on_next=lambda x: result.append(x))
    assert result == [3]

# ==================== all / any / contains / is_empty ====================

def test_all_true():
    result = []
    Observable.of(2, 4, 6).pipe(ops.all(lambda x: x % 2 == 0)).subscribe(on_next=lambda x: result.append(x))
    assert result == [True]

def test_all_false():
    result = []
    Observable.of(2, 3, 4).pipe(ops.all(lambda x: x % 2 == 0)).subscribe(on_next=lambda x: result.append(x))
    assert result == [False]

def test_any_true():
    result = []
    Observable.of(1, 3, 5).pipe(ops.any(lambda x: x > 3)).subscribe(on_next=lambda x: result.append(x))
    assert result == [True]

def test_any_false():
    result = []
    Observable.of(1, 2).pipe(ops.any(lambda x: x > 10)).subscribe(on_next=lambda x: result.append(x))
    assert result == [False]

def test_contains_true():
    result = []
    Observable.of(1, 2, 3).pipe(ops.contains(2)).subscribe(on_next=lambda x: result.append(x))
    assert result == [True]

def test_contains_false():
    result = []
    Observable.of(1, 2, 3).pipe(ops.contains(99)).subscribe(on_next=lambda x: result.append(x))
    assert result == [False]

def test_is_empty_false():
    result = []
    Observable.just(1).pipe(ops.is_empty()).subscribe(on_next=lambda x: result.append(x))
    assert result == [False]

def test_is_empty_true():
    result = []
    Observable.empty().pipe(ops.is_empty()).subscribe(on_next=lambda x: result.append(x))
    assert result == [True]

# ==================== to_list ====================

def test_to_list():
    result = []
    Observable.of(1, 2, 3).pipe(ops.to_list()).subscribe(on_next=lambda x: result.append(x))
    assert result == [[1, 2, 3]]

# ==================== buffer ====================

def test_buffer():
    result = []
    Observable.of(1, 2, 3, 4, 5).pipe(ops.buffer(2)).subscribe(on_next=lambda x: result.append(x))
    assert result == [[1, 2], [3, 4], [5]]

# ==================== start_with / end_with ====================

def test_start_with():
    result = []
    Observable.of(3, 4).pipe(ops.start_with(1, 2)).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3, 4]

def test_end_with():
    result = []
    Observable.of(1, 2).pipe(ops.end_with(3, 4)).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3, 4]

# ==================== tap / do_on_next / do_on_error / do_on_completed ====================

def test_tap():
    side = []
    result = []
    Observable.of(1, 2).pipe(ops.tap(lambda x: side.append(x))).subscribe(on_next=lambda x: result.append(x))
    assert side == [1, 2]
    assert result == [1, 2]

def test_do_on_next():
    side = []
    Observable.of(10).pipe(ops.do_on_next(lambda x: side.append(x))).subscribe(on_next=lambda x: None)
    assert side == [10]

# ==================== ignore_elements ====================

def test_ignore_elements():
    result = []
    Observable.of(1, 2, 3).pipe(ops.ignore_elements()).subscribe(on_next=lambda x: result.append(x))
    assert result == []

# ==================== skip_last / take_last ====================

def test_skip_last():
    result = []
    Observable.of(1, 2, 3).pipe(ops.skip_last(1)).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2]

def test_take_last():
    result = []
    Observable.of(1, 2, 3).pipe(ops.take_last(2)).subscribe(on_next=lambda x: result.append(x))
    assert result == [2, 3]

# ==================== timestamp ====================

def test_timestamp():
    result = []
    Observable.just(42).pipe(ops.timestamp()).subscribe(on_next=lambda x: result.append(x))
    assert len(result) == 1
    val, ts = result[0]
    assert val == 42
    assert isinstance(ts, float)

# ==================== time_interval ====================

def test_time_interval():
    result = []
    obs = Observable.from_iterable([1, 2, 3])
    obs.pipe(ops.time_interval()).subscribe(on_next=lambda x: result.append(x))
    assert len(result) == 3
    for val, interval in result:
        assert isinstance(interval, float)
        assert interval >= 0

# ==================== default_if_empty ====================

def test_default_if_empty():
    result = []
    Observable.empty().pipe(ops.default_if_empty("default")).subscribe(on_next=lambda x: result.append(x))
    assert result == ["default"]

def test_default_if_empty_not_needed():
    result = []
    Observable.just(42).pipe(ops.default_if_empty("default")).subscribe(on_next=lambda x: result.append(x))
    assert result == [42]

# ==================== sum / average / min / max ====================

def test_sum():
    result = []
    Observable.of(1, 2, 3).pipe(ops.sum()).subscribe(on_next=lambda x: result.append(x))
    assert result == [6]

def test_average():
    result = []
    Observable.of(1, 2, 3).pipe(ops.average()).subscribe(on_next=lambda x: result.append(x))
    assert result == [2.0]

def test_minimum():
    result = []
    Observable.of(3, 1, 4, 1, 5).pipe(ops.minimum()).subscribe(on_next=lambda x: result.append(x))
    assert result == [1]

def test_maximum():
    result = []
    Observable.of(3, 1, 4, 1, 5).pipe(ops.maximum()).subscribe(on_next=lambda x: result.append(x))
    assert result == [5]

# ==================== sequence_equal ====================

def test_sequence_equal_true():
    result = []
    Observable.of(1, 2, 3).pipe(ops.sequence_equal(Observable.of(1, 2, 3))).subscribe(on_next=lambda x: result.append(x))
    assert result == [True]

def test_sequence_equal_false():
    result = []
    Observable.of(1, 2).pipe(ops.sequence_equal(Observable.of(1, 99))).subscribe(on_next=lambda x: result.append(x))
    assert result == [False]
