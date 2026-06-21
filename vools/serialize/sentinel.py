"""
序列化专用哨兵对象

提供 NONE 哨兵（替代 None，区分"未设置"和"设置为 None"）。

序列化格式：{'__vools_singleton__': 'vools.serialize.sentinel:NONE'}
"""

class NoneSentinel:
    """
    序列化哨兵：替代 None，区分"未设置"与"设置为 None"。

    示例:
        >>> from vools.serialize.sentinel import NONE, NoneSentinel
        >>> s = Serializer(backend='json')
        >>> data = s.dumps(NONE)
        >>> restored = s.loads(data)
        >>> restored is NONE
        True
    """

    def __getstate__(self):
        return {'__singleton__': 'vools.serialize.sentinel:NONE'}

    def __setstate__(self, state):
        # 单例不需要恢复状态
        pass

    def __reduce__(self):
        # pickle 反序列化时返回单例 NONE
        return (_get_none_singleton, ())

    def __repr__(self):
        return 'NONE'

    def __bool__(self):
        return False


# __reduce__ 所需的辅助函数（必须定义在模块顶层）
def _get_none_singleton():
    return NONE


# 全局单例
NONE = NoneSentinel()
