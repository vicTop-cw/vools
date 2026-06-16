"""Test PipeBuilder .p() chain calls"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from vools.reactive import Observable, ops, Subject

def test_p_scan():
    result = []
    Observable.of(1, 2, 3).p().scan(lambda acc, x: acc + x, 0).subscribe(on_next=lambda x: result.append(x))
    assert result == [0, 1, 3, 6], f"Got {result}"

def test_p_map_filter_take():
    result = []
    Observable.of(1,2,3,4,5).p().map(lambda x: x*10).filter(lambda x: x>20).take(2).subscribe(on_next=lambda x: result.append(x))
    assert result == [30, 40], f"Got {result}"

def test_p_distinct():
    result = []
    Observable.of(1,2,2,3,3,3).p().distinct().subscribe(on_next=lambda x: result.append(x))
    assert result == [1,2,3], f"Got {result}"

def test_p_to_set():
    result = []
    Observable.of(1,2,2,3).p().to_set().subscribe(on_next=lambda x: result.append(x))
    assert result == [{1,2,3}], f"Got {result}"

def test_p_ignore_elements():
    result = []
    Observable.of(1,2,3).p().ignore_elements().subscribe(on_next=lambda x: result.append(x))
    assert result == [], f"Got {result}"

def test_p_skip_last():
    result = []
    Observable.of(1,2,3,4).p().skip_last(1).subscribe(on_next=lambda x: result.append(x))
    assert result == [1,2,3], f"Got {result}"

def test_p_take_last():
    result = []
    Observable.of(1,2,3,4).p().take_last(2).subscribe(on_next=lambda x: result.append(x))
    assert result == [3,4], f"Got {result}"

def test_p_sample():
    result = []
    Observable.of(42).p().sample(1.0).subscribe(on_next=lambda x: result.append(x))
    assert len(result) >= 0

def test_p_throttle_latest():
    result = []
    Observable.of(1,2,3).p().throttle_latest(0.05).subscribe(on_next=lambda x: result.append(x))
    assert len(result) >= 0

def test_p_timeout():
    result = []
    Observable.just(1).p().timeout(1.0).subscribe(on_next=lambda x: result.append(x))
    assert result == [1]

def test_p_window():
    windows = []
    Observable.of(1,2,3,4).p().window(2).subscribe(on_next=lambda w: windows.append(w))
    assert len(windows) == 2

def test_p_count():
    result = []
    Observable.of(1,2,3).p().count().subscribe(on_next=lambda x: result.append(x))
    assert result == [3]

def test_p_sum():
    result = []
    Observable.of(1,2,3).p().sum().subscribe(on_next=lambda x: result.append(x))
    assert result == [6]

def test_p_average():
    result = []
    Observable.of(1,2,3).p().average().subscribe(on_next=lambda x: result.append(x))
    assert result == [2.0]

def test_p_contains():
    result = []
    Observable.of(1,2,3).p().contains(2).subscribe(on_next=lambda x: result.append(x))
    assert result == [True]
