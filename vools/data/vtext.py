"""
VText 文本类
继承自 str，提供链式文本处理方法
"""

__all__ = ['VText']

import os
from typing import Any, Optional, Union, Tuple, Dict, List, Callable

from ..decorators import rself
from ..datetime.dates_format import EnhancedDateFormatter
from ..serialize.context import get_protocol


@rself
class VText(str):
    """链式文本类，继承自 str"""

    def __new__(cls, text: str = "", *args: Any, **kwargs: Any) -> 'VText':
        """创建新的 VText 实例。

        Args:
            text: 初始文本内容
            *args: 传递给父类的额外位置参数
            **kwargs: 传递给父类的额外关键字参数

        Returns:
            新的 VText 实例
        """
        return super().__new__(cls, text)

    def __init__(self, text: str = "", *args: Any, **kwargs: Any) -> None:
        """初始化 VText 实例。

        Args:
            text: 初始文本内容
            *args: 预留位置参数
            **kwargs: 预留关键字参数
        """
        pass

    def do(
        self,
        f: Callable[..., Any] = print,
        pre_f: Optional[Callable[['VText'], 'VText']] = None,
        sub_f: Optional[Callable[[Any], None]] = None
    ) -> 'VText':
        """执行副作用操作，返回自身以支持链式调用。

        Args:
            f: 要执行的函数（默认 print）
            pre_f: 在 f 执行前执行的预处理函数
            sub_f: 在 f 执行后执行的后处理函数（无返回值要求）

        Returns:
            self，自身引用以支持链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self

    @staticmethod
    def _safe_path(file_path: str, base_dir: Optional[str] = None) -> str:
        """安全路径解析，防止路径遍历攻击。

        Args:
            file_path: 文件路径（可以是 file:// URI 格式）
            base_dir: 基础目录，默认为当前工作目录

        Returns:
            规范化后的绝对路径

        Raises:
            ValueError: 当路径试图访问 base_dir 之外的文件时抛出
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

    def write(self, file_path: str = "output.sql", mode: str = 'w') -> None:
        """将文本内容写入文件。

        Args:
            file_path: 文件路径（支持 file:// URI 格式）
            mode: 写入模式，默认 'w'（覆盖写入），可设为 'a'（追加写入）

        Raises:
            ValueError: 当路径试图访问指定目录之外时抛出
            OSError: 当目录创建或文件写入失败时抛出
        """
        safe_path = self._safe_path(file_path)

        parent_dir = os.path.dirname(safe_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(safe_path, mode, encoding="utf-8") as f:
            f.write(str(self))

    def regexp_split(self, pattern: str, flags: int = 0, rep: str = '★') -> 'VText':
        """使用正则表达式分割文本并替换。

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志位（默认 0）
            rep: 替换字符串（默认 '★'），用于标记分割位置

        Returns:
            分割替换后的 VText
        """
        from ..utils.tools import regexp_split as _regexp_split
        return _regexp_split(pattern=pattern, source_string=str(self), flags=flags, rep=rep)

    @staticmethod
    def get_content_fromfile(file_path: str = "input.sql", to_text: bool = True) -> Union[str, List[str]]:
        """从文件读取内容。

        Args:
            file_path: 文件路径（支持 file:// URI 格式）
            to_text: 为 True 时返回字符串，为 False 时返回行列表

        Returns:
            文件内容（字符串或行列表）

        Raises:
            ValueError: 当路径试图访问指定目录之外时抛出
            OSError: 当文件读取失败时抛出
        """
        safe_path = VText._safe_path(file_path)

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read() if to_text else f.readlines()

    def formatEx(self, **kwargs: Any) -> str:
        """使用 EnhancedDateFormatter 格式化文本。

        支持日期时间格式化等扩展格式选项。

        Args:
            **kwargs: 格式化参数，传递给 EnhancedDateFormatter

        Returns:
            格式化后的字符串
        """
        formatter = EnhancedDateFormatter(str(self)).set(**kwargs)
        return formatter.format()

    # ─── 序列化支持 ───

    def __getnewargs__(self) -> Tuple[str]:
        """返回序列化时用于重建实例的参数。

        Returns:
            包含字符串值的元组
        """
        return (str(self),)

    def __getstate__(self) -> Dict[str, str]:
        """获取序列化状态。

        Returns:
            包含字符串值的字典
        """
        return {}

    def __setstate__(self, state: Dict[str, str]) -> None:
        """设置序列化状态。

        Args:
            state: 序列化状态字典
        """
        pass
