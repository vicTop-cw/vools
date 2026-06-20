"""
VText 文本类
继承自 str，提供链式文本处理方法
"""

__all__ = ['VText']

import os

from ..decorators import rself
from ..datetime.dates_format import EnhancedDateFormatter
from ..serialize.context import get_protocol


@rself
class VText(str):
    """链式文本类，继承自 str"""

    def __new__(cls, text="", *args, **kwargs):
        return super().__new__(cls, text)

    def __init__(self, text="", *args, **kwargs):
        pass

    def do(self, f=print, pre_f=None, sub_f=None):
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)

    @staticmethod
    def _safe_path(file_path, base_dir=None):
        if base_dir is None:
            base_dir = os.getcwd()

        base_dir = os.path.abspath(base_dir)

        if file_path.startswith(r'file://'):
            file_path = file_path[7:]

        abs_path = os.path.abspath(os.path.join(base_dir, file_path))
        normalized = os.path.normpath(abs_path)

        if not normalized.startswith(base_dir):
            raise ValueError(f"不允许访问指定路径之外的文件: {file_path}")

        return normalized

    def write(self, file_path="output.sql", mode='w'):
        safe_path = self._safe_path(file_path)

        parent_dir = os.path.dirname(safe_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(safe_path, mode, encoding="utf-8") as f:
            f.write(str(self))

    def regexp_split(self, pattern, flags=0, rep='★'):
        from ..utils.tools import regexp_split as _regexp_split
        return _regexp_split(pattern=pattern, source_string=str(self), flags=flags, rep=rep)

    @staticmethod
    def get_content_fromfile(file_path="input.sql", to_text=True):
        safe_path = VText._safe_path(file_path)

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read() if to_text else f.readlines()

    def formatEx(self, **kwargs):
        formatter = EnhancedDateFormatter(str(self)).set(**kwargs)
        return formatter.format()

    # ─── 序列化支持 ───

    def __getnewargs__(self):
        return (str(self),)

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        pass
