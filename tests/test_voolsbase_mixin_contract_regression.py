# -*- coding: utf-8 -*-
"""回归测试：VoolsBase 混入契约（BUG-415/416/417 的守护网）。

`VoolsBase` 被 vools 中 40+ 类继承（数据容器、编解码器、序列化后端、任务
队列/存储、装饰器管理器等）。BUG-415/416/417 修复了它的相等/哈希/拷贝/重建
语义后，这里把**各子类的实际行为**固化下来，防止后续重构再次引入不一致：

* ``o == o`` 必须为 True（不抛异常、不递归崩溃）
* ``copy()`` 必须返回同类型且可用的对象（旧实现返回垃圾）
* ``to_dict()`` 必须返回 dict
* ``do(...)`` 必须返回 self（`do` 已统一到 VoolsBase）
* 内容可变的对象 ``hash()`` 抛 TypeError 且错误信息含类名（不再泄漏
  "unhashable type: 'list'" 之类内部错误）

构造参数选用各模块中稳定的公开入口；若某类的构造签名变化，本文件会随契约
一起更新（并注明原因）。
"""

import tempfile

import pytest

from vools.core.base import VoolsBase
from vools.crypto.core import CryptoRegistry, Decryptor, Encryptor
from vools.data.seq import Seq
from vools.data.table import Table
from vools.data.vlist import VList
from vools.encoding.core import CodecRegistry
from vools.serialize import Serializer
from vools.serialize.backends.json_backend import JsonBackend
from vools.serialize.backends.msgpack_backend import MsgpackBackend
from vools.serialize.backends.pickle_backend import PickleBackend


@pytest.fixture()
def db_path():
    path = tempfile.mktemp(prefix='_voolsbase_', suffix='.db')
    yield path
    try:
        import os
        os.remove(path)
    except OSError:
        pass


# (标签, 工厂) —— 覆盖不同构造形态（无参/单参/需要路径）
CASES = [
    ('CryptoRegistry', lambda: CryptoRegistry()),
    ('Encryptor', lambda: Encryptor('data')),
    ('Decryptor', lambda: Decryptor('key')),
    ('CodecRegistry', lambda: CodecRegistry()),
    ('Serializer', lambda: Serializer()),
    ('JsonBackend', lambda: JsonBackend()),
    ('MsgpackBackend', lambda: MsgpackBackend()),
    ('PickleBackend', lambda: PickleBackend()),
    ('Seq', lambda: Seq([1, 2])),
    ('VList', lambda: VList([1, 2])),
    ('Table', lambda: Table([[1, 'a']], columns=['id', 'name'], name='T')),
]


@pytest.mark.parametrize('label,factory', CASES, ids=[c[0] for c in CASES])
def test_identity_equality(label, factory):
    with tempfile.TemporaryDirectory():
        obj = factory()
    assert (obj == obj) is True
    assert (obj != obj) is False


@pytest.mark.parametrize('label,factory', CASES, ids=[c[0] for c in CASES])
def test_copy_produces_usable_same_type(label, factory):
    with tempfile.TemporaryDirectory():
        obj = factory()
    copied = obj.copy()
    assert copied is not obj
    assert type(copied).__name__ == type(obj).__name__


@pytest.mark.parametrize('label,factory', CASES, ids=[c[0] for c in CASES])
def test_to_dict_returns_dict(label, factory):
    with tempfile.TemporaryDirectory():
        obj = factory()
    assert isinstance(obj.to_dict(), dict)


@pytest.mark.parametrize('label,factory', CASES, ids=[c[0] for c in CASES])
def test_do_returns_self(label, factory):
    with tempfile.TemporaryDirectory():
        obj = factory()
    assert (obj.do(lambda x: None) is obj) is True


@pytest.mark.parametrize('label,factory', CASES, ids=[c[0] for c in CASES])
def test_hash_rejected_clearly(label, factory):
    with tempfile.TemporaryDirectory():
        obj = factory()
    with pytest.raises(TypeError) as ei:
        hash(obj)
    # 错误信息必须指向对象自身（旧实现抛的是内部 list/dict 不可哈希）
    assert type(obj).__name__ in str(ei.value)


def test_seq_copy_content_preserved():
    # 直接回归 BUG-415：旧实现 copy() 得到 Seq(['_ops', '_active_op'])
    assert list(Seq([1, 2]).copy()) == [1, 2]
    assert list(VList([1, 2]).copy()) == [1, 2]
    t = Table([[1, 'a']], columns=['id', 'name'])
    assert t.copy()._data == [[1, 'a']]
    assert t.copy()._columns == ['id', 'name']


def test_seq_equality_by_content():
    # 直接回归 BUG-415：旧实现 Seq([1,2]) == Seq([1,3]) -> True
    assert (Seq([1, 2]) == Seq([1, 3])) is False
    assert (Seq([1, 2]) == Seq([1, 2])) is True
    assert (Seq([1, 2]) == [1, 2]) is True


def test_from_dict_clear_failure():
    with pytest.raises(TypeError) as ei:
        Seq.from_dict({'x': 1})
    assert 'Seq' in str(ei.value) and 'x' in str(ei.value)

    with pytest.raises(TypeError) as ei:
        Seq.from_dict([1, 2])
    assert 'Seq' in str(ei.value)


def test_voolsbase_direct():
    obj = VoolsBase()
    assert (obj == obj) is True
    assert isinstance(obj.to_dict(), dict)
    assert (obj.do(lambda x: None) is obj) is True
    with pytest.raises(TypeError):
        hash(obj)
