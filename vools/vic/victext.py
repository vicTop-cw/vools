"""
vicText 文本类
继承自 str，提供更多文本处理方法
"""

import os
import re
import itertools
from datetime import datetime

from ..vic.victools import vicTools


class vicText(str):
    """文本类，继承自str，提供更多文本处理方法"""

    def __new__(cls, text="", *args, **kwargs):
        """创建vicText对象

        Args:
            text: 文本内容
        """
        return super().__new__(cls, text)

    def __init__(self, text="", *args, **kwargs):
        """初始化vicText对象

        Args:
            text: 文本内容
        """
        self._text = text
        super().__init__()
        self._result = None

    @staticmethod
    def _safe_path(file_path, base_dir=None):
        """安全路径验证，防止路径遍历攻击

        Args:
            file_path: 用户提供的文件路径
            base_dir: 基础目录，默认为当前工作目录

        Returns:
            安全验证后的绝对路径

        Raises:
            ValueError: 路径验证失败时抛出
        """
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
        """将文本写入文件

        Args:
            file_path: 文件路径
            mode: 写入模式

        Returns:
            self

        Raises:
            ValueError: 路径验证失败时抛出
            OSError: 文件操作失败时抛出
        """
        safe_path = self._safe_path(file_path)

        parent_dir = os.path.dirname(safe_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(safe_path, mode, encoding="utf-8") as f:
            f.write(self._text)
        return self

    @vicTools.transfer
    def regexp_split(self, pattern, flags=0, rep='★'):
        """使用正则表达式分割文本

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志
            rep: 临时替换字符

        Returns:
            分割后的列表
        """
        return vicTools.regexp_split(pattern=pattern, source_string=self._text, flags=flags, rep=rep)

    @staticmethod
    @vicTools.transfer
    def get_content_fromfile(file_path="input.sql", to_text=True):
        """从文件读取内容

        Args:
            file_path: 文件路径
            to_text: 是否返回文本

        Returns:
            文本内容或行列表

        Raises:
            ValueError: 路径验证失败时抛出
            OSError: 文件读取失败时抛出
        """
        safe_path = vicText._safe_path(file_path)

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read() if to_text else f.readlines()

    @property
    def text(self):
        """获取文本内容

        Returns:
            文本内容
        """
        return self._text

    @property
    def result(self):
        """获取运行结果

        Returns:
            运行结果
        """
        return self._result