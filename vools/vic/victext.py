"""
vicText 文本类
继承自 str，提供更多文本处理方法
"""

__all__ = ['vicText']

import os
import re
import itertools
from datetime import datetime

from ..decorators import rself
from ..datetime.dates_format import EnhancedDateFormatter


@rself
class vicText(str):
    """文本类，继承自str，提供更多文本处理方法"""

    def __new__(cls, text="", *args, **kwargs):
        return super().__new__(cls, text)

    def __init__(self, text="", *args, **kwargs):
        self._text = text
        self._result = None

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
            f.write(self._text)

    def regexp_split(self, pattern, flags=0, rep='★'):
        from ..vic.victools import vicTools
        return vicTools.regexp_split(pattern=pattern, source_string=self._text, flags=flags, rep=rep)

    @staticmethod
    def get_content_fromfile(file_path="input.sql", to_text=True):
        safe_path = vicText._safe_path(file_path)

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read() if to_text else f.readlines()

    @property
    def text(self):
        return self._text

    @property
    def result(self):
        return self._result

    def formatEx(self, **kwargs):
        formatter = EnhancedDateFormatter(self._text).set(**kwargs)
        return formatter.format()