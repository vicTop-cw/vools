"""
vicTools 工具类
提供各种实用的工具方法
"""

__all__ = ['vicTools']

import copy
import json
from collections import OrderedDict, namedtuple, deque
from collections.abc import Iterable
import itertools
from functools import wraps, reduce, partial, lru_cache, update_wrapper
import re
import time
from datetime import datetime, timedelta
import string
import pkgutil
import random

from ..data import Seq, NONE
from ..security import safe_compile_expression
from ..functional.placeholder import _
from ..functional.box import Box, setattr_box


@lru_cache(maxsize=256)
def _get_cached_attr(self, name):
    """LRU缓存优化方法（内部使用）"""
    return self.__getattr__(name)


class vicTools:
    """工具类，提供各种实用的工具方法"""

    @staticmethod
    def transfer(func=None, w=None):
        """将函数的返回值转换为对应的vic类型

        Args:
            func: 要包装的函数
            w: 额外的包装函数

        Returns:
            包装后的函数，其返回值会被转换为对应的vic类型
        """
        wraper_func = w
        if func is None:
            return lambda f, w=wraper_func: vicTools.transfer(f, w=w)

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if hasattr(result, '__class__'):
                class_name = result.__class__.__name__
                if class_name in ['vicText', 'vicList']:
                    return result
            if isinstance(result, str):
                from .victext import vicText
                return vicText(result)
            if isinstance(result, Iterable):
                from .viclist import vicList
                return vicList(result)
            return result

        if wraper_func:
            update_wrapper(wrapper, wraper_func)

        return wrapper

    @staticmethod
    def get_index_cols(cols: list, *ix):
        """根据索引获取列名

        Args:
            cols: 列名列表
            *ix: 索引值（从1开始）

        Returns:
            对应的列名列表
        """
        l = len(cols)

        def _inner(i):
            if isinstance(i, int):
                if i == 0:
                    raise ValueError("start from 1 not 0 !!!")
                i = i if i < 0 else i - 1
                return cols[i]
            return i

        return [_inner(j) for j in ix]

    @staticmethod
    def static_vars(**kwargs):
        """为函数添加静态变量

        Args:
            **kwargs: 要添加的静态变量

        Returns:
            装饰器函数
        """
        def decorate(func):
            for k, v in kwargs.items():
                setattr(func, k, v)
            return func

        return decorate

    @staticmethod
    def generate_lambda(ex: str, param_symbols="x"):
        """根据字符串表达式生成lambda函数

        Args:
            ex: 字符串表达式
            param_symbols: 参数符号

        Returns:
            生成的lambda函数
        """
        param_symbols = vicTools.transferCols(param_symbols)
        if isinstance(ex, str):
            return safe_compile_expression(ex, tuple(param_symbols))
        else:
            raise TypeError(" ex must be a string !!!")

    @staticmethod
    def shift(iters, num: int = 1, fill_value=None, cycle=False):
        """实现列表元素滑动功能，支持循环模式和填充值

        Args:
            iters: 可迭代对象
            num: 位移步数（正数右移，负数左移）
            fill_value: 填充值（默认None）
            cycle: 是否启用循环模式

        Returns:
            滑动后的列表
        """
        lst = list(iters)
        n = len(lst)
        if n == 0 or num == 0:
            return lst.copy()

        if cycle:
            dq = deque(lst)
            dq.rotate(-num)
            return list(dq)
        else:
            actual_shift = num % n if num > 0 else -(-num % n)

            if actual_shift > 0:
                padding = [fill_value] * actual_shift
                return padding + lst[:-actual_shift]
            else:
                padding = [fill_value] * (-actual_shift)
                return lst[-actual_shift:] + padding

    @staticmethod
    def get_py_fmt(fmt='yyyyMMdd'):
        """将自定义日期格式转换为Python标准格式

        Args:
            fmt: 自定义日期格式

        Returns:
            Python标准日期格式
        """
        if not '%' in fmt:
            fmt = fmt.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
            fmt = fmt.replace('YYYY', '%Y').replace('SS', '%S').replace('ss', '%S').replace('yy', '%y')

        return fmt

    @staticmethod
    def _generate_date_range(end_date, periods, freq='D'):
        """生成日期序列（使用标准库）

        Args:
            end_date: 结束日期
            periods: 生成的日期数量
            freq: 频率（D-天, W-周, M-月）

        Returns:
            日期对象列表
        """
        dates = []
        current = end_date

        for _ in range(periods):
            dates.append(current)
            if freq == 'D':
                current -= timedelta(days=1)
            elif freq == 'W':
                current -= timedelta(weeks=1)
            elif freq == 'M':
                year = current.year
                month = current.month - 1
                if month == 0:
                    month = 12
                    year -= 1
                last_day = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day
                day = min(current.day, last_day)
                current = datetime(year, month, day)

        return dates[::-1]

    @staticmethod
    def get_date_seq(nums=15, date_type='day', fmt='%m%d', run_ds=None, duo=True, reverse=True):
        """生成日期序列

        Args:
            nums: 生成的日期数量
            date_type: 日期类型（day, week, month）
            fmt: 日期格式
            run_ds: 基准日期
            duo: 是否生成日期范围
            reverse: 是否反转顺序

        Returns:
            日期序列列表
        """
        fmt = vicTools.get_py_fmt(fmt)
        if run_ds is None:
            run_ds = datetime.now().strftime('%Y%m%d')
        if reverse:
            return vicTools.get_date_seq(nums=nums, date_type=date_type, fmt=fmt, run_ds=run_ds, duo=duo, reverse=False)[::-1]

        freq = date_type[0].upper()
        run_date = datetime.strptime(run_ds, '%Y-%m-%d') if "-" in run_ds else datetime.strptime(run_ds, '%Y%m%d')

        if freq == 'D':
            dss = [d.date() for d in vicTools._generate_date_range(run_date, nums, freq='D')]
            return [f"{d.strftime(fmt)}-{d.strftime(fmt)}" for d in dss] if duo else [d.strftime(fmt) for d in dss]

        if freq == 'W':
            temp_run_date = run_date
            if run_date.weekday() != 6:
                days_to_sunday = 6 - run_date.weekday()
                temp_run_date += timedelta(days=days_to_sunday)

            dss = [d.date() for d in vicTools._generate_date_range(temp_run_date, nums, freq='W')]

            result = []
            for i, d in enumerate(dss):
                start_date = d - timedelta(days=6)
                end_date = d if i > 0 else run_date
                if duo:
                    result.append(f"{start_date.strftime(fmt)}-{end_date.strftime(fmt)}")
                else:
                    result.append(f"{end_date.strftime(fmt)}")
            return result

        end_of_month = run_date.replace(month=run_date.month + 1, day=1) - timedelta(days=1)
        dss = [d.date() for d in vicTools._generate_date_range(end_of_month, nums, freq='M')]

        result = []
        for i, d in enumerate(dss):
            start_date = d.replace(day=1)
            end_date = d if i > 0 else run_date
            if duo:
                result.append(f"{start_date.strftime(fmt)}-{end_date.strftime(fmt)}")
            else:
                result.append(f"{end_date.strftime(fmt)}")
        return result

    @staticmethod
    def transferCols(cols=None):
        """将列名转换为列表

        Args:
            cols: 列名，可以是字符串、列表或其他可迭代对象

        Returns:
            列名列表
        """
        if not bool(cols):
            return []
        if isinstance(cols, str):
            if "," in cols:
                return [str(c).strip() for c in cols.split(',')]
            else:
                return [str(cols).strip()]

        if isinstance(cols, Iterable):
            return [str(c).strip() for c in cols]

    @staticmethod
    def generate_random_field_name(word_count=3, max_length=8):
        """生成一个随机的字段名

        Args:
            word_count: 字段名中单词的数量，默认为3
            max_length: 每个单词的最大长度，默认为8

        Returns:
            随机生成的字段名
        """
        def generate_word(length):
            letters_and_digits = string.ascii_letters + string.digits
            return ''.join(random.choice(letters_and_digits) for _ in range(length))

        field_name = '_'.join(generate_word(random.randint(1, max_length)) for _ in range(word_count))
        return field_name

    @staticmethod
    def getAllModules(search_path=None):
        """获取所有模块

        Args:
            search_path: 搜索路径

        Returns:
            模块名列表
        """
        all_modules = [x[1] for x in pkgutil.iter_modules(path=search_path)]
        return all_modules

    @staticmethod
    def getAllPackagesWithVersion():
        """获取所有已安装的包及其版本

        Returns:
            包含包名和版本的命名元组列表
        """
        Pkg = namedtuple("Pkg", ["name", "version"])
        try:
            import importlib.metadata
            installed_packages = importlib.metadata.distributions()
            return [Pkg(p.metadata['Name'], p.version) for p in installed_packages]
        except ImportError:
            import pkg_resources
            installed_packages = pkg_resources.working_set
            return [Pkg(p.key, p.version) for p in installed_packages]

    @staticmethod
    def toOrderedDict(x, fix: str="col_", ix=0) -> OrderedDict:
        """将对象转换为OrderedDict

        Args:
            x: 要转换的对象
            fix: 键名前缀
            ix: 起始索引

        Returns:
            OrderedDict对象
        """
        if isinstance(x, OrderedDict):
            return x
        if isinstance(x, tuple) and hasattr(x, "_fields"):
            return OrderedDict({i: j for i, j in zip(x._fields, x)})
        if isinstance(x, dict):
            return OrderedDict(x)
        if isinstance(x, str):
            x = vicTools.transferCols(x)

        if not isinstance(x, Iterable):
            x = [x]

        return OrderedDict({"{}{}".format(fix, i): j for i, j in enumerate(x, ix)})

    @staticmethod
    def build_text(raw_text_mode="", dct=None, lst=None, sep="\n ,", check_key: str="item", max_iter_num=999):
        """根据模板和数据构建文本

        Args:
            raw_text_mode: 文本模板
            dct: 字典数据
            lst: 列表数据
            sep: 列表元素分隔符
            check_key: 列表元素占位符
            max_iter_num: 最大迭代次数

        Returns:
            构建后的文本
        """
        txt = copy.deepcopy(raw_text_mode)

        if dct:
            dct = vicTools.toOrderedDict(dct)
            kys = ["{" + k + "}" for k in dct.keys()]
            while max_iter_num > 0:
                temp = [i for i in kys if i in txt]
                if len(temp) == 0:
                    break
                for kk in temp:
                    k = kk[1:-1]
                    txt = txt.replace(kk, str(dct[k]))

                max_iter_num -= 1

        if not check_key:
            return txt

        if not lst:
            return txt

        lst = vicTools.transferCols(lst)
        if len(lst) == 0:
            return txt

        if check_key[0] != "{":
            check_key = "{" + check_key
        if check_key[-1] != "}":
            check_key = check_key + "}"

        return sep.join([txt.replace(check_key, v).replace("{ix}", str(i)) for i, v in enumerate(lst)])

    @staticmethod
    def get_json_keys(field_name):
        """获取JSON对象的键

        Args:
            field_name: JSON字符串或字典

        Returns:
            键列表
        """
        try:
            if isinstance(field_name, str):
                field_name = json.loads(field_name)

            if isinstance(field_name, dict):
                return list(field_name.keys())
        except (ValueError, TypeError):
            return []

        return []

    @staticmethod
    def offset_date(run_date, offset_days, std=False):
        """计算偏移后的日期

        Args:
            run_date: 基准日期
            offset_days: 偏移天数
            std: 是否返回标准格式（YYYY-MM-DD）

        Returns:
            偏移后的日期字符串
        """
        date_format = "%Y-%m-%d" if '-' in run_date else "%Y%m%d"
        date_obj = datetime.strptime(run_date, date_format)
        new_date_obj = date_obj + timedelta(days=offset_days)
        date_format = "%Y-%m-%d" if std else "%Y%m%d"
        return new_date_obj.strftime(date_format)

    @staticmethod
    def aggregate_json_keys(keys_list):
        """合并多个JSON键列表

        Args:
            keys_list: 键列表的列表

        Returns:
            合并后的键列表（去重）
        """
        return list(set(key for keys in keys_list for key in keys))

    @staticmethod
    def calculate_runtime(func):
        """计算函数运行时间的装饰器

        Args:
            func: 要装饰的函数

        Returns:
            装饰后的函数
        """
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            run_time = end_time - start_time
            print("函数", func.__name__, "运行时间：", run_time, "秒")
            return result

        return wrapper

    @staticmethod
    def excel_column_to_number(col):
        """根据Excel列字母返回列数字

        Args:
            col: Excel列字母

        Returns:
            列数字
        """
        col = col.upper()
        result = 0
        for char in col:
            result = result * 26 + (ord(char) - 64)
        return result

    @staticmethod
    def excel_number_to_column(num):
        """根据数字返回Excel列字母

        Args:
            num: 列数字

        Returns:
            Excel列字母
        """
        result = ""
        while num > 0:
            num -= 1
            remainder = num % 26
            result = chr(65 + remainder) + result
            num //= 26
        return result

    @staticmethod
    def union_ordered_collection(original_list):
        """返回去重后的列表或元组，位置顺序按原来顺序顺延

        Args:
            original_list: 原始列表或元组

        Returns:
            去重后的列表或元组
        """
        if isinstance(original_list, list):
            return list(OrderedDict.fromkeys(original_list).keys())
        elif isinstance(original_list, tuple):
            return tuple(OrderedDict.fromkeys(original_list).keys())

    @staticmethod
    def trim(string, chars=None, left=True, right=True):
        """修剪字符串

        Args:
            string: 要修剪的字符串
            chars: 要修剪的字符集
            left: 是否修剪左侧
            right: 是否修剪右侧

        Returns:
            修剪后的字符串
        """
        if left == False and right == False:
            return string
        if chars is None:
            if left and right:
                return string.strip()
            elif left:
                return string.lstrip()
            elif right:
                return string.rstrip()

        left_index = 0
        right_index = len(string)

        if left:
            while left_index < right_index and string[left_index] in chars:
                left_index += 1

        if right:
            while right_index > left_index and string[right_index - 1] in chars:
                right_index -= 1

        return string[left_index:right_index]

    @staticmethod
    def regexp_findall(pattern, source_string, flags=0):
        """使用正则表达式查找所有匹配项

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            flags: 正则表达式标志

        Returns:
            匹配项列表
        """
        regex = re.compile(pattern, flags=flags)
        return regex.findall(source_string)

    @staticmethod
    def regexp_replace(pattern, source_string, replacement, flags=0, count=0):
        """使用正则表达式替换匹配项

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            replacement: 替换字符串
            flags: 正则表达式标志
            count: 替换的最大次数

        Returns:
            替换后的字符串
        """
        regex = re.compile(pattern, flags=flags)
        return regex.sub(string=source_string, repl=replacement, count=count)

    @staticmethod
    def regexp_like(pattern, source_string, flags=0, complete_matching=True):
        """检查字符串是否匹配正则表达式

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            flags: 正则表达式标志
            complete_matching: 是否完全匹配

        Returns:
            是否匹配
        """
        matchs = vicTools.regexp_findall(pattern=pattern, source_string=source_string, flags=flags)
        if complete_matching:
            return len(matchs) == 1 and str(matchs[0]) == source_string
        else:
            return len(matchs) > 0

    @staticmethod
    def regexp_substr(pattern, source_string, flags=0, occurrence=0):
        """获取正则表达式匹配的子字符串

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            flags: 正则表达式标志
            occurrence: 匹配项的索引

        Returns:
            匹配的子字符串
        """
        matchs = vicTools.regexp_findall(pattern=pattern, source_string=source_string, flags=flags)
        matchs_length = len(matchs)
        return matchs[occurrence] if occurrence in range(matchs_length) or occurrence in range(-matchs_length, 0) else None

    @staticmethod
    def regexp_count(pattern, source_string, flags=0):
        """计算正则表达式匹配的次数

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            flags: 正则表达式标志

        Returns:
            匹配次数
        """
        return len(vicTools.regexp_findall(pattern=pattern, source_string=source_string, flags=flags))

    @staticmethod
    def regexp_instr(pattern, source_string, flags=0, occurrence=0):
        """获取正则表达式匹配的起始位置

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            flags: 正则表达式标志
            occurrence: 匹配项的索引

        Returns:
            匹配的起始位置
        """
        temp = vicTools.regexp_substr(pattern=pattern, source_string=source_string, flags=flags, occurrence=occurrence)
        return source_string.find(temp) if temp is not None else -1

    @staticmethod
    def get_char(string, rep='★'):
        """获取一个不在字符串中出现的字符

        Args:
            string: 源字符串
            rep: 初始尝试的字符

        Returns:
            不在字符串中出现的字符
        """
        if string.count(rep) == 0:
            return rep
        for rep1 in map(chr, range(1, 128)):
            if string.count(rep1) == 0:
                return rep1
        return None

    @staticmethod
    def check_no_overlap(strings):
        """检查字符串列表中是否存在包含关系

        Args:
            strings: 字符串列表

        Returns:
            如果字符串之间互不包含返回True，否则False
        """
        return all(strings[i] not in strings[j] for i in range(len(strings)) for j in range(len(strings)) if i != j)

    @staticmethod
    def regexp_split(pattern, source_string, flags=0, rep='★'):
        """使用正则表达式分割字符串

        Args:
            pattern: 正则表达式模式
            source_string: 源字符串
            flags: 正则表达式标志
            rep: 临时替换字符

        Returns:
            分割后的字符串列表
        """
        if source_string.count(rep) == 0 and len(rep) == 1:
            sep = set()
            if isinstance(pattern, str):
                regex = re.compile(pattern, flags=flags)
                sep = set(regex.findall(source_string))
                return vicTools._split(string=source_string, sep=list(sep), rep=rep)
            elif isinstance(pattern, (list, tuple, set)):
                for pat in pattern:
                    if isinstance(pat, str):
                        regex = re.compile(pat, flags=flags)
                        temp = set(regex.findall(source_string))
                        sep = sep.union(temp)
                return vicTools._split(string=source_string, sep=list(sep), rep=rep)
            else:
                return None
        else:
            return None

    @staticmethod
    def _split(string, sep, rep='★'):
        """分割字符串

        Args:
            string: 源字符串
            sep: 分隔符列表
            rep: 临时替换字符

        Returns:
            分割后的字符串列表
        """
        rep = vicTools.get_char(string=string, rep=rep)
        if rep is None:
            return None
        if vicTools.check_no_overlap(sep):
            for p in sep:
                string = string.replace(p, rep)
            return string.split(rep)
        else:
            return None

    @staticmethod
    def split(string, separator, rep='★'):
        """分割字符串

        Args:
            string: 源字符串
            separator: 分隔符
            rep: 临时替换字符

        Returns:
            分割后的字符串列表
        """

        if isinstance(separator, str):
            return string.split(separator)
        elif isinstance(separator, (list, tuple, set)):
            sep = set()
            for p in separator:
                if isinstance(p, str):
                    sep.add(p)
            return vicTools._split(string=string, sep=list(sep), rep=rep)
        else:
            return None
