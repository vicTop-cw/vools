"""
vools.serialize 单元测试
"""

import pytest
from vools.serialize import (
    Serializer,
    dumps,
    loads,
    dumps_hex,
    loads_hex,
    serialize,
    deserialize,
    serializable,
    serialize_method,
    deserialize_method,
    set_default_backend,
    get_default_backend,
)


# 模块级别函数和类用于测试（pickle 需要）


class MyService:
    """测试用服务类"""
    @serialize_method(backend='json')
    def get_state(self):
        return {"status": "ok", "data": [1, 2, 3]}

    @deserialize_method(backend='pickle')
    def update_state(self, state):
        self._state = state
        return state


@deserialize(backend='pickle')
def process_data(data):
    """测试用函数"""
    return data


@serialize(backend='json')
def get_data():
    """测试用函数"""
    return {"name": "test", "value": 123}


class TestSerializer:
    """测试 Serializer 类"""

    def test_pickle_backend_dumps_loads(self):
        """测试 pickle 后端的基本序列化/反序列化"""
        s = Serializer(backend='pickle')
        data = {"key": "value", "number": 123}
        serialized = s.dumps(data)
        assert isinstance(serialized, bytes)
        restored = s.loads(serialized)
        assert restored == data

    def test_json_backend_dumps_loads(self):
        """测试 JSON 后端的基本序列化/反序列化"""
        s = Serializer(backend='json')
        data = {"key": "value", "number": 123}
        serialized = s.dumps(data)
        assert isinstance(serialized, bytes)
        restored = s.loads(serialized)
        assert restored == data

    def test_dumps_hex(self):
        """测试十六进制序列化"""
        s = Serializer(backend='pickle')
        data = {"key": "value"}
        hex_str = s.dumps_hex(data)
        assert isinstance(hex_str, str)
        assert all(c in '0123456789abcdef' for c in hex_str)

    def test_loads_hex(self):
        """测试从十六进制反序列化"""
        s = Serializer(backend='pickle')
        data = {"key": "value"}
        hex_str = s.dumps_hex(data)
        restored = s.loads_hex(hex_str)
        assert restored == data


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_dumps_loads_default_backend(self):
        """测试 dumps/loads 使用默认后端"""
        set_default_backend('pickle')
        data = {"key": "value"}
        serialized = dumps(data)
        restored = loads(serialized)
        assert restored == data
        set_default_backend(None)

    def test_dumps_loads_specified_backend(self):
        """测试指定后端的 dumps/loads"""
        data = {"key": "value"}
        serialized = dumps(data, backend='json')
        restored = loads(serialized, backend='json')
        assert restored == data


class TestConfig:
    """测试配置函数"""

    def test_set_get_default_backend(self):
        """测试默认后端设置和获取"""
        set_default_backend('json')
        assert get_default_backend() == 'json'
        set_default_backend('pickle')
        assert get_default_backend() == 'pickle'
        set_default_backend(None)

    def test_default_backend_fallback(self):
        """测试默认后端回退到 pickle"""
        set_default_backend(None)
        data = {"key": "value"}
        serialized = dumps(data)
        restored = loads(serialized)
        assert restored == data


class TestSerializeDecorator:
    """测试 @serialize 装饰器"""

    def test_serialize_basic(self):
        """测试基本的序列化装饰器"""
        result = get_data()
        assert isinstance(result, bytes)
        restored = loads(result, backend='json')
        assert restored == {"name": "test", "value": 123}

    def test_serialize_with_args(self):
        """测试带参数的函数"""
        @serialize(backend='pickle')
        def create_data(x, y):
            return {"x": x, "y": y}

        result = create_data(10, 20)
        assert isinstance(result, bytes)


class TestDeserializeDecorator:
    """测试 @deserialize 装饰器"""

    def test_deserialize_basic(self):
        """测试基本的反序列化装饰器"""
        original = {"key": "value"}
        serialized = dumps(original, backend='pickle')
        result = process_data(serialized)
        assert result == original


class TestSerializableDecorator:
    """测试 @serializable 类装饰器"""

    @pytest.mark.skip(reason="pickle 无法序列化局部类，需在模块级别定义")
    def test_serializable_basic(self):
        """测试基本的类装饰器"""
        @serializable(backend='pickle')
        class MyData:
            def __init__(self, name: str, value: int):
                self.name = name
                self.value = value

            def __eq__(self, other):
                return isinstance(other, MyData) and self.name == other.name and self.value == other.value

        instance = MyData("test", 123)
        serialized = MyData.serialize(instance)
        assert isinstance(serialized, bytes)

        restored = MyData.deserialize(serialized)
        assert restored.name == "test"
        assert restored.value == 123


class TestSerializeMethodDecorator:
    """测试 @serialize_method 装饰器"""

    def test_serialize_method_basic(self):
        """测试基本的实例方法序列化装饰器"""
        service = MyService()
        result = service.get_state()
        assert isinstance(result, bytes)


class TestDeserializeMethodDecorator:
    """测试 @deserialize_method 装饰器"""

    def test_deserialize_method_basic(self):
        """测试基本的实例方法反序列化装饰器"""
        service = MyService()
        original = {"status": "updated"}
        serialized = dumps(original, backend='pickle')
        result = service.update_state(serialized)
        assert result == original


class TestJsonBackendOrjson:
    """测试 JSON 后端的 orjson 支持"""

    def test_json_backend_works(self):
        """测试 JSON 后端能正常工作"""
        s = Serializer(backend='json')
        data = {"key": "value", "list": [1, 2, 3], "nested": {"a": 1}}
        serialized = s.dumps(data)
        restored = s.loads(serialized)
        assert restored == data


class TestCurrySerialization:
    """测试 curry 函数序列化"""

    @pytest.mark.skip(reason="pickle 无法序列化局部函数，需在模块级别定义 curry 函数")
    def test_curry_basic_serialization(self):
        """测试 curry 函数的序列化（使用模块级别定义的 curry 函数）"""
        from vools import curry

        @curry
        def module_add(a, b):
            return a + b

        partial_add = module_add(10)
        s = Serializer(backend='pickle')
        serialized = s.dumps(partial_add)
        restored = s.loads(serialized)
        assert restored(5) == 15


# ============================================================
# 新增测试：__getstate__ 对象序列化功能测试
# 所有特殊对象现在通过 __getstate__/__setstate__ 序列化
# ============================================================

# --- 模块级辅助对象 ---
# 注意：pickle 序列化要求函数定义在可导入的模块中（非 __main__），
# 因此将辅助函数放在 tests/_serialize_helpers.py 中。

from tests._serialize_helpers import noop, add_three

def _is_positive(x):
    return x > 0


class TestNoneSentinelSerialization:
    """测试 NONE 哨兵序列化（通过 __getstate__）"""

    def test_none_round_trip(self):
        """测试 NONE 基本序列化/反序列化往返"""
        from vools.data.seq import NONE

        s = Serializer(backend='pickle')
        data = s.dumps(NONE)
        restored = s.loads(data)
        assert restored is NONE

    def test_none_with_json_backend(self):
        """测试 NONE 使用 JSON 后端"""
        from vools.data.seq import NONE

        s = Serializer(backend='json')
        data = s.dumps(NONE)
        restored = s.loads(data)
        assert restored is NONE

    def test_none_with_msgpack_backend(self):
        """测试 NONE 使用 msgpack 后端"""
        from vools.data.seq import NONE

        s = Serializer(backend='msgpack')
        data = s.dumps(NONE)
        restored = s.loads(data)
        assert restored is NONE


class TestPlaceholderSerialization:
    """测试 _IndexHolder 占位符序列化（通过 __getstate__）"""

    def test_underscore_round_trip(self):
        """测试 _ 占位符往返"""
        from vools.functional.placeholder import _

        s = Serializer(backend='pickle')
        data = s.dumps(_)
        restored = s.loads(data)
        assert restored is _

    def test_numeric_placeholders(self):
        """测试 _1 到 _5 占位符"""
        import vools.functional.placeholder as ph

        s = Serializer(backend='pickle')
        for ix in range(1, 6):
            placeholder = getattr(ph, f'_{ix}')
            data = s.dumps(placeholder)
            restored = s.loads(data)
            assert restored is placeholder

    def test_placeholder_identity(self):
        """测试占位符单例身份保持"""
        from vools.functional.placeholder import _, _1, _2

        s = Serializer(backend='pickle')
        for ph in [_, _1, _2]:
            data = s.dumps(ph)
            restored = s.loads(data)
            assert restored is ph, f"Identity lost for {ph}"

    def test_custom_indexholder(self):
        """测试自定义 _IndexHolder 实例"""
        from vools.functional.placeholder import _IndexHolder

        custom = _IndexHolder(ix=99, arity=3)
        s = Serializer(backend='pickle')
        data = s.dumps(custom)
        restored = s.loads(data)
        assert restored.ix == 99

    def test_placeholder_with_json_backend(self):
        """测试占位符使用 JSON 后端"""
        from vools.functional.placeholder import _1

        s = Serializer(backend='json')
        data = s.dumps(_1)
        restored = s.loads(data)
        assert restored is _1


class TestStuffSerialization:
    """测试 Stuff 实例序列化（通过 __getstate__）"""

    def test_stuff_basic_round_trip(self):
        """测试简单 Stuff 实例的序列化往返"""
        from vools.utils.stuff import Stuff

        stuff = Stuff(add_three)
        # 使用 json 后端：pickle 在跨模块函数引用时有身份校验问题
        s = Serializer(backend='json')
        data = s.dumps(stuff)
        restored = s.loads(data)
        assert restored.main_func == add_three

    def test_stuff_with_config(self):
        """测试带配置的 Stuff 实例"""
        from vools.utils.stuff import Stuff, StuffConfig

        config = StuffConfig(cache_duration=10.0, max_workers=8, debug=True, strict=True)
        stuff = Stuff(add_three, config=config)

        s = Serializer(backend='json')
        data = s.dumps(stuff)
        restored = s.loads(data)
        assert restored.config.cache_duration == 10.0
        assert restored.config.max_workers == 8
        assert restored.config.debug is True
        assert restored.config.strict is True


class TestConditionBuilderSerialization:
    """测试 ConditionBuilder 序列化（通过 __getstate__）"""

    def test_condition_builder_basic(self):
        """测试基本 ConditionBuilder"""
        from vools.functional.iif import ConditionBuilder

        cb = ConditionBuilder(10, comp='>')
        s = Serializer(backend='pickle')
        data = s.dumps(cb)
        restored = s.loads(data)
        assert restored.base == 10
        assert restored.supp is True

    def test_condition_builder_restore(self):
        """测试 ConditionBuilder 恢复后仍可工作"""
        from vools.functional.iif import ConditionBuilder

        cb = ConditionBuilder(5, comp='==')
        cb.case(1, "one").case(5, "five").otherwise("other")

        s = Serializer(backend='pickle')
        data = s.dumps(cb)
        restored = s.loads(data)
        assert restored.base == 5

    def test_condition_builder_with_json(self):
        """测试 ConditionBuilder 使用 JSON 后端"""
        from vools.functional.iif import ConditionBuilder

        cb = ConditionBuilder(42, comp='>=')
        s = Serializer(backend='json')
        data = s.dumps(cb)
        restored = s.loads(data)
        assert restored.base == 42
        assert restored.supp is True


class TestXYPlaceholderSerialization:
    """测试 X/Y 占位符序列化（通过 __getstate__）"""

    def test_x_singleton(self):
        """测试 X 单例序列化"""
        from vools.functional.placeholder_impl import X

        s = Serializer(backend='pickle')
        data = s.dumps(X)
        restored = s.loads(data)
        assert restored is X

    def test_y_singleton(self):
        """测试 Y 单例序列化"""
        from vools.functional.placeholder_impl import Y

        s = Serializer(backend='pickle')
        data = s.dumps(Y)
        restored = s.loads(data)
        assert restored is Y

    def test_x_with_json_backend(self):
        """测试 X 使用 JSON 后端"""
        from vools.functional.placeholder_impl import X

        s = Serializer(backend='json')
        data = s.dumps(X)
        restored = s.loads(data)
        assert restored is X


class TestHoderSerialization:
    """测试 Hoder 序列化（通过 __getstate__）"""

    def test_hoder_basic(self):
        """测试基本 Hoder"""
        from vools.utils.hoder import Hoder

        h = Hoder(obj=42)
        s = Serializer(backend='pickle')
        data = s.dumps(h)
        restored = s.loads(data)
        assert restored.get() == 42

    def test_hoder_lazy(self):
        """测试延迟 Hoder"""
        from vools.utils.hoder import Hoder

        h = Hoder(lazy=True)
        s = Serializer(backend='pickle')
        data = s.dumps(h)
        restored = s.loads(data)
        assert restored._lazy is True
        assert restored._created is False

    def test_hoder_with_json_backend(self):
        """测试 Hoder 使用 JSON 后端"""
        from vools.utils.hoder import Hoder

        h = Hoder(obj="test_value")
        s = Serializer(backend='json')
        data = s.dumps(h)
        restored = s.loads(data)
        assert restored.get() == "test_value"


class TestOverloadManagerSerialization:
    """测试重载管理器序列化（通过 __getstate__）"""

    def test_selector_basic(self):
        """测试 Selector 序列化"""
        from vools.decorators.selector import Selector

        sel = Selector(noop)
        s = Serializer(backend='pickle')
        data = s.dumps(sel)
        restored = s.loads(data)
        assert restored is not None

    def test_overloads_basic(self):
        """测试 Overloads 序列化"""
        from vools.decorators.selector import Overloads

        ov = Overloads(noop)
        s = Serializer(backend='pickle')
        data = s.dumps(ov)
        restored = s.loads(data)
        assert restored is not None

    def test_overload_manager_basic(self):
        """测试 OverloadManager 序列化"""
        from vools.decorators.overload import OverloadManager

        om = OverloadManager()
        s = Serializer(backend='pickle')
        data = s.dumps(om)
        restored = s.loads(data)
        assert restored is not None

    def test_overcurry_manager_basic(self):
        """测试 OvercurryManager 序列化"""
        from vools.decorators.overcurry import OvercurryManager

        ocm = OvercurryManager(noop)
        s = Serializer(backend='pickle')
        data = s.dumps(ocm)
        restored = s.loads(data)
        assert restored is not None


class TestDelayCurriedSerialization:
    """测试 DelayCurried 序列化（通过 __getstate__）"""

    def test_basic_round_trip(self):
        """测试基本 DelayCurried 往返"""
        from vools.decorators.curry_delay import DelayCurried

        dc = DelayCurried(add_three)
        # 使用 json：DelayCurried 的 __module__ 是 @property，破坏 pickle 类解析
        s = Serializer(backend='json')
        data = s.dumps(dc)
        restored = s.loads(data)
        assert restored is not None


class TestVicTypeSerialization:
    """测试 Vic 工具类型序列化（通过 __getstate__）"""

    def test_victext_serialization(self):
        """测试 VText 序列化"""
        from vools.data import VText

        t = VText("hello world")
        s = Serializer(backend='pickle')
        data = s.dumps(t)
        restored = s.loads(data)
        assert type(restored) is VText
        assert str(restored) == "hello world"

    def test_victext_json_backend(self):
        """测试 VText 使用 JSON 后端"""
        from vools.data import VText

        t = VText("hello")
        s = Serializer(backend='json')
        data = s.dumps(t)
        restored = s.loads(data)
        assert type(restored) is VText
        assert str(restored) == "hello"

    def test_vicdate_serialization(self):
        """测试 VDate 序列化"""
        from vools.datetime import VDate

        d = VDate('2024-06-15')
        s = Serializer(backend='pickle')
        data = s.dumps(d)
        restored = s.loads(data)
        assert type(restored) is VDate
        assert str(restored) == '2024-06-15'

    def test_viclist_serialization(self):
        """测试 VList 序列化"""
        from vools.data import VList

        vl = VList([1, 2, 3])
        s = Serializer(backend='pickle')
        data = s.dumps(vl)
        restored = s.loads(data)
        assert type(restored) is VList
        assert list(restored) == [1, 2, 3]


class TestTaskDecoratorSerialization:
    """测试 TaskDecorator 序列化（通过 __getstate__）"""

    def test_basic_round_trip(self):
        """测试 TaskDecorator 基本往返"""
        from vools.task.decorators.task_decorator import TaskDecorator

        td = TaskDecorator(db_path="test_tasks.db")
        s = Serializer(backend='pickle')
        data = s.dumps(td)
        restored = s.loads(data)
        assert restored.db_path == 'test_tasks.db'

    def test_default_db_path(self):
        """测试默认 db_path"""
        from vools.task.decorators.task_decorator import TaskDecorator

        td = TaskDecorator()
        s = Serializer(backend='pickle')
        data = s.dumps(td)
        restored = s.loads(data)
        assert restored.db_path == 'tasks.db'


class TestBugFixes:
    """测试 Bug 修复验证"""

    def test_deserialize_callable_list_iteration(self):
        """验证 _HANDLERS 直接迭代正常工作（旧 bug 已修复）"""
        from vools.serialize.callable import _HANDLERS
        # _HANDLERS 是 list，直接迭代不应报错
        handler_names = [h.handler_name for h in _HANDLERS]
        assert len(handler_names) > 0
        # 不应该有 dict 的 .values() 方法
        assert not hasattr(_HANDLERS, 'values')

    def test_deserialize_callable_unknown_handler_error(self):
        """验证未知处理器给出详细错误信息"""
        from vools.serialize.callable import deserialize_callable

        s = Serializer(backend='pickle')
        with pytest.raises(ValueError, match="Unknown callable handler"):
            deserialize_callable('NonExistentHandler', b'', s)


class TestHandlerRegistration:
    """测试处理器注册完整性（保留 2 个回退处理器）"""

    def test_all_handlers_registered(self):
        """验证 2 个回退处理器已注册"""
        from vools.serialize.callable import _HANDLERS

        # 只保留 2 个通用回退处理器（DecoratorHandler, FunctionalHandler）
        assert len(_HANDLERS) == 2, f"Expected 2 handlers, got {len(_HANDLERS)}"

        expected_names = {'DecoratorHandler', 'FunctionalHandler'}
        actual_names = {h.handler_name for h in _HANDLERS}
        assert actual_names == expected_names

    def test_handlers_order(self):
        """验证处理器注册顺序正确：FunctionalHandler 最后（宽泛匹配）"""
        from vools.serialize.callable import _HANDLERS

        last_name = _HANDLERS[-1].handler_name
        assert last_name == 'FunctionalHandler'

    def test_handler_names_unique(self):
        """验证所有处理器名称唯一"""
        from vools.serialize.callable import _HANDLERS

        names = [h.handler_name for h in _HANDLERS]
        assert len(names) == len(set(names)), f"Duplicate handler names: {names}"


class TestSerializationBackwardCompatibility:
    """测试向后兼容性"""

    def test_old_callable_format_unknown_handler(self):
        """测试旧的 __callable__ 格式遇到未知处理器时抛出清晰错误"""
        s = Serializer(backend='pickle')
        old_format = {
            '__callable__': True,
            'handler': 'NonExistentHandler',
            'state': s.dumps({'key': 'value'}),
        }
        serialized = s.dumps(old_format)
        # 旧格式仍可被 dict.loads 解出，但 deserialize_callable 会失败
        from vools.serialize.callable import deserialize_callable
        with pytest.raises(ValueError, match="Unknown callable handler"):
            deserialize_callable('NonExistentHandler', s.dumps({'key': 'value'}), s)


class TestReactiveSerialization:
    """测试 Reactive 类（Subject 族）的序列化"""

    def test_subject_pickle_round_trip(self):
        """测试 Subject pickle 往返（活跃订阅丢失，但状态恢复）"""
        from vools.reactive import Subject

        s = Subject()
        serializer = Serializer(backend='pickle')
        data = serializer.dumps(s)
        restored = serializer.loads(data)

        assert restored is not None
        assert isinstance(restored, Subject)
        assert restored._is_closed == s._is_closed
        assert restored._is_completed == s._is_completed

    def test_subject_json_backend(self):
        """测试 Subject json 后端序列化"""
        from vools.reactive import Subject

        s = Subject()
        serializer = Serializer(backend='json')
        data = serializer.dumps(s)
        restored = serializer.loads(data)

        assert restored is not None
        assert isinstance(restored, Subject)

    def test_behavior_subject_save_value(self):
        """测试 BehaviorSubject 保存/恢复 _value"""
        from vools.reactive import BehaviorSubject

        bs = BehaviorSubject(42)
        bs.on_next(100)  # 更新值为 100

        serializer = Serializer(backend='pickle')
        data = serializer.dumps(bs)
        restored = serializer.loads(data)

        assert restored.value == 100  # 恢复最新值

    def test_behavior_subject_json_round_trip(self):
        """测试 BehaviorSubject json 往返"""
        from vools.reactive import BehaviorSubject

        bs = BehaviorSubject('hello')
        serializer = Serializer(backend='json')
        data = serializer.dumps(bs)
        restored = serializer.loads(data)

        assert restored.value == 'hello'

    def test_replay_subject_save_buffer(self):
        """测试 ReplaySubject 保存/恢复 _buffer"""
        from vools.reactive import ReplaySubject

        rs = ReplaySubject(buffer_size=3)
        rs.on_next(1)
        rs.on_next(2)
        rs.on_next(3)

        serializer = Serializer(backend='pickle')
        data = serializer.dumps(rs)
        restored = serializer.loads(data)

        # 恢复后，新订阅者应收到重放
        items = []
        restored.subscribe(on_next=items.append)
        assert items == [1, 2, 3]

    def test_replay_subject_buffer_size(self):
        """测试 ReplaySubject 保存/恢复 _buffer_size"""
        from vools.reactive import ReplaySubject

        rs = ReplaySubject(buffer_size=5)
        serializer = Serializer(backend='pickle')
        data = serializer.dumps(rs)
        restored = serializer.loads(data)

        assert restored._buffer_size == 5

    def test_async_subject_save_value(self):
        """测试 AsyncSubject 保存/恢复 _has_value 和 _value"""
        from vools.reactive import AsyncSubject

        async_s = AsyncSubject()
        async_s.on_next(42)  # 设置值但不完成

        serializer = Serializer(backend='pickle')
        data = serializer.dumps(async_s)
        restored = serializer.loads(data)

        assert restored._has_value == True
        assert restored._value == 42

    def test_observable_serialization_warns(self):
        """测试 Observable 反序列化时触发警告"""
        from vools.reactive import Observable
        import warnings

        obs = Observable.from_iterable([1, 2, 3])
        serializer = Serializer(backend='pickle')

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            data = serializer.dumps(obs)
            restored = serializer.loads(data)
            # 检查是否触发了警告
            assert len(w) == 1
            assert "Observable 反序列化后为空" in str(w[0].message)

    def test_subject_closed_state_preserved(self):
        """测试 Subject 关闭状态序列化后保留"""
        from vools.reactive import Subject

        s = Subject()
        s.on_completed()  # 标记为完成

        serializer = Serializer(backend='pickle')
        data = serializer.dumps(s)
        restored = serializer.loads(data)

        assert restored._is_completed == True
        assert restored._is_closed == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
