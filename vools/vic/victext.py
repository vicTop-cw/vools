"""
vicText 文本类
继承自 str，提供更多文本处理方法
"""

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

        Returns:
            vicText对象
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

    def write(self, file_path="output.sql", mode='w'):
        """将文本写入文件

        Args:
            file_path: 文件路径
            mode: 写入模式

        Returns:
            self
        """
        fd = file_path
        fd = fd[(7 if fd.startswith(r'file://') else 0):]
        with open(fd, mode, encoding="utf-8") as f:
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
        """
        fd = file_path
        fd = fd[(7 if fd.startswith(r'file://') else 0):]
        with open(fd, "r", encoding="utf-8") as f:
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

    @result.setter
    def result(self, value):
        """设置运行结果

        Args:
            value: 运行结果

        Raises:
            ValueError: 结果属性只能被run函数执行设置
        """
        raise ValueError("result属性只能被run函数执行设置！！！")

    def build(self, dct=None, lst=None, sep="\n ,", check_key: str="item", max_iter_num=999, prefix: str="", suffix: str=""):
        """根据模板和数据构建文本

        Args:
            dct: 字典数据
            lst: 列表数据
            sep: 列表元素分隔符
            check_key: 列表元素占位符
            max_iter_num: 最大迭代次数
            prefix: 前缀
            suffix: 后缀

        Returns:
            构建后的vicText对象
        """
        txt = prefix + vicTools.build_text(self._text, dct, lst, sep, check_key, max_iter_num) + suffix
        return vicText(txt)

    def _run(self, func=exec):
        """运行文本

        Args:
            func: 运行函数

        Returns:
            运行结果
        """
        if self._text.strip() == "":
            return None
        if callable(func):
            return func(self._text)
        elif isinstance(func, str):
            if func.lower() == "exec":
                return exec(self._text)
            elif func.lower() == "eval":
                return eval(self._text)
            elif func.lower() == "spark.sql":
                return None
            return func(self._text)
        else:
            return None

    @vicTools.transfer
    def run(self, func=print):
        """运行文本并设置结果

        Args:
            func: 运行函数

        Returns:
            运行结果或self
        """
        self._result = self._run(func)
        if self._result is None:
            return self
        if isinstance(self._result, str):
            return vicText(self._result)
        return self._result

    def trim(self, chars=None, left=True, right=True):
        """修剪文本

        Args:
            chars: 要修剪的字符集
            left: 是否修剪左侧
            right: 是否修剪右侧

        Returns:
            修剪后的vicText对象
        """
        return vicText(vicTools.trim(self._text, chars, left, right))

    @vicTools.transfer
    def regexp_findall(self, pattern, flags=0):
        """使用正则表达式查找所有匹配项

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志

        Returns:
            匹配项列表
        """
        return vicTools.regexp_findall(pattern, self._text, flags)

    def regexp_replace(self, pattern, replacement, flags=0, count=0):
        """使用正则表达式替换匹配项

        Args:
            pattern: 正则表达式模式
            replacement: 替换字符串
            flags: 正则表达式标志
            count: 替换的最大次数

        Returns:
            替换后的vicText对象
        """
        return vicText(vicTools.regexp_replace(pattern, self._text, replacement, flags, count))

    def regexp_like(self, pattern, flags=0, complete_matching=True):
        """检查文本是否匹配正则表达式

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志
            complete_matching: 是否完全匹配

        Returns:
            是否匹配
        """
        return vicTools.regexp_like(pattern, self._text, flags, complete_matching)

    def regexp_substr(self, pattern, flags=0, occurrence=0):
        """获取正则表达式匹配的子字符串

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志
            occurrence: 匹配项的索引

        Returns:
            匹配的子字符串
        """
        return vicTools.regexp_substr(pattern, self._text, flags, occurrence)

    def regexp_count(self, pattern, flags=0):
        """计算正则表达式匹配的次数

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志

        Returns:
            匹配次数
        """
        return vicTools.regexp_count(pattern, self._text, flags)

    def regexp_instr(self, pattern, flags=0, occurrence=0):
        """获取正则表达式匹配的起始位置

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志
            occurrence: 匹配项的索引

        Returns:
            匹配的起始位置
        """
        return vicTools.regexp_instr(pattern, self._text, flags, occurrence)

    @vicTools.transfer
    def splitEx(self, separator, rep='★'):
        """分割文本

        Args:
            separator: 分隔符
            rep: 临时替换字符

        Returns:
            分割后的列表
        """
        temp = vicTools.split(self._text, separator, rep)
        return [] if temp is None else temp

    def like(self, pattern: str, ignorecase=True):
        """检查文本是否匹配模式

        Args:
            pattern: 模式字符串
            ignorecase: 是否忽略大小写

        Returns:
            是否匹配
        """
        txt = self.text
        if ignorecase:
            txt, pattern = txt.lower(), pattern.lower()
        import fnmatch
        return fnmatch.fnmatch(txt, pattern)

    def upper(self):
        """转换为大写

        Returns:
            大写的vicText对象
        """
        return vicText(super().upper())

    def lower(self):
        """转换为小写

        Returns:
            小写的vicText对象
        """
        return vicText(super().lower())

    def title(self):
        """转换为标题格式

        Returns:
            标题格式的vicText对象
        """
        return vicText(super().title())

    def capitalize(self):
        """首字母大写

        Returns:
            首字母大写的vicText对象
        """
        return vicText(super().capitalize())

    def swapcase(self):
        """交换大小写

        Returns:
            交换大小写后的vicText对象
        """
        return vicText(super().swapcase())

    def replace(self, old, new, count=None):
        """替换文本

        Args:
            old: 旧字符串
            new: 新字符串
            count: 替换的最大次数

        Returns:
            替换后的vicText对象
        """
        return vicText(super().replace(old, new, count)) if count is not None else vicText(super().replace(old, new))

    def __repr__(self):
        """repr表示

        Returns:
            表示字符串
        """
        return f"vicText({self._text})"

    def __str__(self):
        """字符串表示

        Returns:
            文本内容
        """
        return super().__str__()

    def replace_run_date(self, run_date=None):
        """替换运行日期

        Args:
            run_date: 运行日期

        Returns:
            替换后的vicText对象
        """
        if '{run_date' not in self:
            return self
        return self

    @vicTools.transfer
    def split(self, sep=None, maxsplit=-1):
        """分割文本

        Args:
            sep: 分隔符
            maxsplit: 最大分割次数

        Returns:
            分割后的列表
        """
        return super().split(sep, maxsplit) if sep is not None else super().split()

    @vicTools.transfer
    def rsplit(self, sep=None, maxsplit=-1):
        """从右侧分割文本

        Args:
            sep: 分隔符
            maxsplit: 最大分割次数

        Returns:
            分割后的列表
        """
        return super().rsplit(sep, maxsplit) if sep is not None else super().rsplit()

    def strip(self, chars=None):
        """修剪文本两侧

        Args:
            chars: 要修剪的字符集

        Returns:
            修剪后的vicText对象
        """
        return vicText(super().strip(chars)) if chars is not None else vicText(super().strip())

    def lstrip(self, chars=None):
        """修剪文本左侧

        Args:
            chars: 要修剪的字符集

        Returns:
            修剪后的vicText对象
        """
        return vicText(super().lstrip(chars)) if chars is not None else vicText(super().lstrip())

    def rstrip(self, chars=None):
        """修剪文本右侧

        Args:
            chars: 要修剪的字符集

        Returns:
            修剪后的vicText对象
        """
        return vicText(super().rstrip(chars)) if chars is not None else vicText(super().rstrip())

    def zfill(self, width):
        """用零填充

        Args:
            width: 填充后的宽度

        Returns:
            填充后的vicText对象
        """
        return vicText(super().zfill(width))

    @vicTools.transfer
    def discard_comments(self):
        """丢弃注释

        Returns:
            无注释的文本
        """
        ss = re.sub(r'--.*?$|/\*.*?\*/', '', self, flags=re.MULTILINE | re.DOTALL)
        result = [line for line in ss.split('\n') if line.strip()]
        return "\n".join(result)

    @vicTools.transfer
    def move_trailing_commas(self, discard_comment=True):
        """移动尾随逗号

        Args:
            discard_comment: 是否丢弃注释

        Returns:
            处理后的文本
        """
        txt = self.discard_comments().text if discard_comment else self._text
        arr = txt.split('\n')
        patt1 = re.compile(r',\s*\t*(--.*)?$')
        patt3 = re.compile(r'^\s*\t*(--.*)?$')
        patt11 = re.compile(r',\s*\t*(--.*?$|/\*.*?\*/)', re.MULTILINE | re.DOTALL)
        patt411 = re.compile(r'(.*),((\s*\t*(--.*?$|/\*.*?\*/))', re.MULTILINE | re.DOTALL)
        patt4 = re.compile(r'(.*),((\s*\t*(--.*)?)$')

        result = []
        p = False
        for line in arr:
            if patt3.search(line):
                result.append(line)
            else:
                if p:
                    s = "".join(itertools.takewhile(lambda x: x in [' ', '\t'], line)) + ","
                    line = s + line.lstrip()
                    p = False
                if patt1.search(line):
                    result.append(re.sub(patt4, r'\1\2', line))
                    p = True
                elif patt11.search(line):
                    result.append(re.sub(patt411, r'\1\2', line))
                    p = True
                else:
                    result.append(line)
        else:
            if p:
                result.append(",")
        return '\n'.join(result)

    def partition(self, sep):
        """分割文本为三部分

        Args:
            sep: 分隔符

        Returns:
            分割后的vicList对象
        """
        from ..vic.viclist import vicList
        return vicList(vicText(s) for s in super().partition(sep))

    def rpartition(self, sep):
        """从右侧分割文本为三部分

        Args:
            sep: 分隔符

        Returns:
            分割后的vicList对象
        """
        from ..vic.viclist import vicList
        return vicList(vicText(s) for s in super().rpartition(sep))

    def splitlines(self, keepends=False):
        """按行分割文本

        Args:
            keepends: 是否保留换行符

        Returns:
            分割后的vicList对象
        """
        from ..vic.viclist import vicList
        return vicList(super().splitlines(keepends))

    def center(self, width, fillchar=None):
        """居中文本

        Args:
            width: 宽度
            fillchar: 填充字符

        Returns:
            居中后的vicText对象
        """
        return vicText(super().center(width, fillchar)) if fillchar is not None else vicText(super().center(width))

    def ljust(self, width, fillchar=None):
        """左对齐文本

        Args:
            width: 宽度
            fillchar: 填充字符

        Returns:
            左对齐后的vicText对象
        """
        return vicText(super().ljust(width, fillchar)) if fillchar is not None else vicText(super().ljust(width))

    def rjust(self, width, fillchar=None):
        """右对齐文本

        Args:
            width: 宽度
            fillchar: 填充字符

        Returns:
            右对齐后的vicText对象
        """
        return vicText(super().rjust(width, fillchar)) if fillchar is not None else vicText(super().rjust(width))

    def expandtabs(self, tabsize=8):
        """展开制表符

        Args:
            tabsize: 制表符大小

        Returns:
            展开后的vicText对象
        """
        return vicText(super().expandtabs(tabsize))

    def translate(self, table):
        """翻译文本

        Args:
            table: 翻译表

        Returns:
            翻译后的vicText对象
        """
        return vicText(super().translate(table))

    def join(self, iterable):
        """连接可迭代对象

        Args:
            iterable: 可迭代对象

        Returns:
            连接后的vicText对象
        """
        return vicText(super().join(iterable))

    def format(self, *args, **kwargs):
        """格式化文本

        Args:
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            格式化后的vicText对象
        """
        return vicText(super().format(*args, **kwargs))

    def formatEx(self, **kwargs):
        """扩展格式化文本

        Args:
            **kwargs: 关键字参数

        Returns:
            格式化后的vicText对象
        """
        temp = kwargs.pop('run_date', datetime.now().strftime('%Y-%m-%d'))
        txt = self.replace("${run_", "{run_").text
        return self

    def __add__(self, other):
        """加法操作

        Args:
            other: 另一个字符串或vicText对象

        Returns:
            连接后的vicText对象
        """
        if isinstance(other, str):
            txt = other
        elif isinstance(other, self.__class__):
            txt = other.text
        else:
            raise TypeError('argument `other` is invalided type ')
        return vicText(self.text + txt)

    def __sub__(self, other):
        """减法操作

        Args:
            other: 要删除的字符串

        Returns:
            删除后的vicText对象
        """
        return vicText(self.regexp_replace(other, ''))

    def __radd__(self, other):
        """右加法操作

        Args:
            other: 另一个字符串或vicText对象

        Returns:
            连接后的vicText对象
        """
        if isinstance(other, str):
            txt = other
        elif isinstance(other, self.__class__):
            txt = other.text
        else:
            raise TypeError('argument `other` is invalided type ')
        return vicText(txt + self.text)

    def __mul__(self, n):
        """乘法操作

        Args:
            n: 重复次数

        Returns:
            重复后的vicText对象
        """
        return vicText(super().__mul__(n))

    def __rmul__(self, n):
        """右乘法操作

        Args:
            n: 重复次数

        Returns:
            重复后的vicText对象
        """
        return vicText(super().__rmul__(n))

    def __mod__(self, other):
        """取模操作

        Args:
            other: 格式化参数

        Returns:
            格式化后的vicText对象
        """
        return vicText(super().__mod__(other))

    def __rmod__(self, other):
        """右取模操作

        Args:
            other: 格式化参数

        Returns:
            格式化后的vicText对象
        """
        return vicText(super().__rmod__(other))

    def __getitem__(self, key):
        """获取索引或切片

        Args:
            key: 索引或切片

        Returns:
            对应的vicText对象
        """
        return vicText(super().__getitem__(key))

    def __setitem__(self, key, value):
        """设置索引或切片

        Args:
            key: 索引或切片
            value: 新值
        """
        return super().__setitem__(key, value)

    def __delitem__(self, key):
        """删除索引或切片

        Args:
            key: 索引或切片
        """
        return super().__delitem__(key)

    def __iter__(self):
        """迭代文本

        Returns:
            迭代器
        """
        return (vicText(s) for s in super().__iter__())

    def __reversed__(self):
        """反转迭代文本

        Returns:
            反转迭代器
        """
        return (vicText(s) for s in super().__reversed__())

    @vicTools.transfer
    def __call__(self, func=print, *args, **kwargs):
        """调用文本

        Args:
            func: 调用函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            调用结果
        """
        return func(self, *args, **kwargs)