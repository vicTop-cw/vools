"""
JSON 序列化后端
"""

from typing import Any

from .base import BaseBackend
__all__ = ['JsonBackend']

# 尝试导入 orjson，如果不可用则使用标准 json
try:
    import orjson
    _HAS_ORJSON = True
except ImportError:
    import json
    _HAS_ORJSON = False


class JsonBackend(BaseBackend):
    """JSON 序列化后端，支持 orjson 高性能实现"""

    name = "json"

    def __init__(self, use_orjson: bool = True):
        """
        初始化 JSON 后端

        Args:
            use_orjson: 是否优先使用 orjson（如果可用），默认为 True
        """
        self.use_orjson = use_orjson and _HAS_ORJSON

    def dumps(self, obj: Any) -> bytes:
        """
        序列化为 JSON 字节串

        使用 vools_preprocess 预处理对象树（处理内置子类），
        再使用 vools_default 回调处理非原生类型。

        Args:
            obj: 要序列化的对象

        Returns:
            JSON 格式的字节串
        """
        from ...serialize.codec import vools_preprocess, vools_default
        obj = vools_preprocess(obj)
        if self.use_orjson:
            return orjson.dumps(
                obj,
                default=vools_default,
                option=orjson.OPT_PASSTHROUGH_DATETIME | orjson.OPT_PASSTHROUGH_SUBCLASS,
            )
        else:
            return json.dumps(obj, default=vools_default).encode('utf-8')

    def loads(self, data: bytes) -> Any:
        """
        从 JSON 字节串反序列化

        使用 vools_object_hook 回调重建 vools 对象。
        orjson 不支持 object_hook，需后处理。

        Args:
            data: JSON 格式的字节串

        Returns:
            反序列化后的对象
        """
        from ...serialize.codec import vools_object_hook, post_process_orjson
        if self.use_orjson:
            result = orjson.loads(data)
            return post_process_orjson(result)
        else:
            return json.loads(data.decode('utf-8'), object_hook=vools_object_hook)


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

    def dumps_str(self, obj: Any) -> str:
        """
        序列化为 JSON 字符串（不转义 Unicode）

        Args:
            obj: 要序列化的对象

        Returns:
            JSON 格式的字符串
        """
        from ...serialize.codec import vools_preprocess, vools_default
        obj = vools_preprocess(obj)
        if self.use_orjson:
            return orjson.dumps(
                obj,
                default=vools_default,
                option=orjson.OPT_PASSTHROUGH_DATETIME | orjson.OPT_PASSTHROUGH_SUBCLASS,
            ).decode('utf-8')
        else:
            return json.dumps(obj, default=vools_default, ensure_ascii=False)