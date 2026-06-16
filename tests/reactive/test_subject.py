"""Test Subject, BehaviorSubject"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from vools.reactive import Subject, BehaviorSubject, Observable

# ===== Subject =====

def test_subject_basic():
    """Subject 可以手动发射值"""
    result = []
    subj = Subject()
    subj.subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_next(2)
    subj.on_completed()
    assert result == [1, 2]

def test_subject_multiple_subscribers():
    result1 = []
    result2 = []
    subj = Subject()
    subj.subscribe(on_next=lambda x: result1.append(x))
    subj.subscribe(on_next=lambda x: result2.append(x))
    subj.on_next(42)
    assert result1 == [42]
    assert result2 == [42]

def test_subject_late_subscriber():
    """Subject 的晚订阅者不会收到之前的数据"""
    result = []
    subj = Subject()
    subj.on_next("before")
    subj.subscribe(on_next=lambda x: result.append(x))
    subj.on_next("after")
    assert result == ["after"]

def test_subject_error():
    err1 = [None]
    err2 = [None]
    subj = Subject()
    subj.subscribe(on_next=lambda x: None, on_error=lambda e: err1.__setitem__(0, e))
    subj.subscribe(on_next=lambda x: None, on_error=lambda e: err2.__setitem__(0, e))
    subj.on_error(RuntimeError("fail"))
    assert isinstance(err1[0], RuntimeError)
    assert isinstance(err2[0], RuntimeError)

def test_subject_completed():
    comp1 = [False]
    comp2 = [False]
    subj = Subject()
    subj.subscribe(on_next=lambda x: None, on_completed=lambda: comp1.__setitem__(0, True))
    subj.subscribe(on_next=lambda x: None, on_completed=lambda: comp2.__setitem__(0, True))
    subj.on_completed()
    assert comp1[0]
    assert comp2[0]

def test_subject_closed_after_complete():
    """Subject 结束后不能再发射"""
    subj = Subject()
    subj.on_completed()
    result = []
    subj.subscribe(on_next=lambda x: result.append(x))
    assert result == []  # 直接完成

def test_subject_closed_after_error():
    subj = Subject()
    subj.on_error(ValueError())
    result = []
    subj.subscribe(on_next=lambda x: result.append(x))
    assert result == []

def test_subject_observable_trait():
    """Subject 也是 Observable"""
    result = []
    subj = Subject()
    subj.pipe(lambda obs: obs.subscribe(on_next=lambda x: result.append(x)))
    subj.on_next("ok")
    assert result == ["ok"]

def test_subject_unsubscribe():
    result = []
    subj = Subject()
    sub = subj.subscribe(on_next=lambda x: result.append(x))
    sub.unsubscribe()
    subj.on_next("should not appear")
    assert result == []

# ===== BehaviorSubject =====

def test_behavior_subject_initial():
    """BehaviorSubject 默认值"""
    result = []
    subj = BehaviorSubject(0)
    subj.subscribe(on_next=lambda x: result.append(x))
    assert result == [0]

def test_behavior_subject_late_subscriber_gets_last():
    """晚订阅者收到最后一个值"""
    subj = BehaviorSubject(0)
    subj.on_next(1)
    subj.on_next(2)
    result = []
    subj.subscribe(on_next=lambda x: result.append(x))
    assert result == [2]

def test_behavior_subject_get_value():
    subj = BehaviorSubject(42)
    assert subj.value == 42
    subj.on_next(99)
    assert subj.value == 99

def test_behavior_subject_sequence():
    result = []
    subj = BehaviorSubject("start")
    subj.subscribe(on_next=lambda x: result.append(x))
    subj.on_next("a")
    subj.on_next("b")
    assert result == ["start", "a", "b"]

def test_behavior_subject_no_late_after_complete():
    """BehaviorSubject 完成后订阅仍可收到最后一个值"""
    subj = BehaviorSubject(0)
    subj.on_completed()
    result = []
    subj.subscribe(on_next=lambda x: result.append(x))
    assert result == [0]  # 仍能拿到最后一个值
