from itertools import (
    accumulate,
    chain,
    compress,
    count,
    cycle,
    dropwhile,
    filterfalse,
    groupby,
    islice,
    product,
    repeat,
    starmap,
    takewhile,
    tee,
    zip_longest
)

from functools import (
    cmp_to_key,
    lru_cache,
    namedtuple,
    partial,
    partialmethod,
    reduce,
    wraps
)
from collections import deque
from collections.abc import Iterable
import sys
import re
from wrapt import decorator as wdeco, ObjectProxy as AOP
from .arrow_func import g
from typing import List, Optional, Tuple, Union
from datetime import datetime, date, timedelta

__all__ = ['box', 'Box', 'setattr_box']


class vicTools:
    @staticmethod
    def static_vars(**kwargs):
        def decorate(func):
            for k, v in kwargs.items():
                setattr(func, k, v)
            return func
        return decorate

    @staticmethod
    def generate_lambda(ex: str, param_symbols="x"):
        param_symbols = ",".join(vicTools.transferCols(param_symbols))
        if isinstance(ex, str):
            ex = f"lambda {param_symbols} : {ex}"
            return eval(ex, globals(), locals())
        else:
            raise TypeError(" ex must be a string !!!")

    @staticmethod
    def shift(iters, num: int = 1, fill_value=None, cycle=False):
        """
        实现列表元素滑动功能，支持循环模式和填充值
        :param iters: 可迭代对象
        :param num: 位移步数（正数右移，负数左移）
        :param fill_value: 填充值（默认None）
        :param cycle: 是否启用循环模式
        :return: 滑动后的列表
        """
        lst = list(iters)
        n = len(lst)
        if n == 0 or num == 0:
            return lst.copy()
        
        if cycle:
            # 循环模式处理（利用deque特性）
            dq = deque(lst)
            dq.rotate(-num)  # deque的rotate方向与位移方向相反
            return list(dq)
        else:
            # 非循环模式处理
            actual_shift = num % n if num > 0 else -(-num % n)
            
            if actual_shift > 0:
                # 右移：左侧填充
                padding = [fill_value] * actual_shift
                return padding + lst[:-actual_shift]
            else:
                # 左移：右侧填充
                padding = [fill_value] * (-actual_shift)
                return lst[-actual_shift:] + padding

    @staticmethod
    def get_py_fmt(fmt='yyyyMMdd'):
        if not '%' in fmt:
            fmt = fmt.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
            fmt = fmt.replace('YYYY', '%Y').replace('SS', '%S').replace('ss', '%S').replace('yy', '%y')
        
        return fmt

    @staticmethod
    def transferCols(cols=None):
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
        """
        生成一个随机的字段名。
        
        :param word_count: 字段名中单词的数量，默认为3。
        :param max_length: 每个单词的最大长度，默认为8。
        :return: 一个字符串，表示随机生成的字段名。
        """
        # 生成单个单词
        def generate_word(length):
            import string
            import random
            letters_and_digits = string.ascii_letters + string.digits
            return ''.join(random.choice(letters_and_digits) for _ in range(length))

        # 生成字段名
        field_name = '_'.join(generate_word(random.randint(1, max_length)) for _ in range(word_count))
        return field_name

    @staticmethod
    def build_text(raw_text_mode="", dct=None, lst=None, sep="\n ,", check_key: str = "item", max_iter_num=999):
        import copy
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
    def toOrderedDict(dct):
        from collections import OrderedDict
        return OrderedDict(dct)

    @staticmethod
    def offset_date(run_date, offset_days, std=False):
        date_format = "%Y-%m-%d" if '-' in run_date else "%Y%m%d"
        date_obj = datetime.strptime(run_date, date_format)
        new_date_obj = date_obj + timedelta(days=offset_days)
        date_format = "%Y-%m-%d" if std else "%Y%m%d"
        return new_date_obj.strftime(date_format)

    @staticmethod
    def aggregate_json_keys(keys_list):
        # 使用集合去重并合并数组
        return list(set(key for keys in keys_list for key in keys))

    @staticmethod
    def calculate_runtime(func):
        from time import time
        def wrapper(*args, **kwargs):
            start_time = time()
            result = func(*args, **kwargs)
            end_time = time()
            run_time = end_time - start_time
            print("函数", func.__name__, "运行时间：", run_time, "秒")
            return result
        return wrapper

    @staticmethod
    def excel_column_to_number(col):
        """根据数字返回Excel列字母"""
        col = col.upper()
        result = 0
        for char in col:
            result = result * 26 + (ord(char) - 64)
        return result

    @staticmethod
    def excel_number_to_column(num):
        """根据Excel列字母返回列数字"""
        result = ""
        while num > 0:
            num -= 1
            remainder = num % 26
            result = chr(65 + remainder) + result
            num //= 26
        return result

    @staticmethod
    def trim(string, chars=None, left=True, right=True):
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
        regex = re.compile(pattern, flags=flags)
        return regex.findall(source_string)

    @staticmethod
    def regexp_replace(pattern, source_string, replacement, flags=0, count=0):
        """
            source_string：源字符串，表示要在其中进行搜索匹配项的字符串。
            pattern：正则表达式模式，表示要匹配的模式。
            replacement:替换后的字符串。
            flags：可选参数，用于指定正则表达式的标志。
            count：可选参数，指定替换的最大次数，默认为 0 表示替换所有匹配项。

            flags:  re.I 或 re.IGNORECASE：忽略大小写匹配。
                    re.M 或 re.MULTILINE：多行模式，使 ^ 和 $ 可以匹配每行的开头和结尾。
                    re.S 或 re.DOTALL：点号 (.) 可以匹配换行符。
                    re.X 或 re.VERBOSE：冗长模式，可以在正则表达式中添加注释和空格，提高可读性。
        """
        regex = re.compile(pattern, flags=flags)
        return regex.sub(string=source_string, repl=replacement, count=count)

    @staticmethod
    def regexp_like(pattern, source_string, flags=0, complete_matching=True):
        """
            source_string：源字符串，表示要在其中进行搜索匹配项的字符串。
            pattern：正则表达式模式，表示要匹配的模式。
            flags：可选参数，用于指定正则表达式的标志。
            complete_matching:用于是否完全匹配而不是包含。

            flags:  re.I 或 re.IGNORECASE：忽略大小写匹配。
                    re.M 或 re.MULTILINE：多行模式，使 ^ 和 $ 可以匹配每行的开头和结尾。
                    re.S 或 re.DOTALL：点号 (.) 可以匹配换行符。
                    re.X 或 re.VERBOSE：冗长模式，可以在正则表达式中添加注释和空格，提高可读性。
        """
        matchs = vicTools.regexp_findall(pattern=pattern, source_string=source_string, flags=flags)
        if complete_matching:
            return len(matchs) == 1 and str(matchs[0]) == source_string
        else:
            return len(matchs) > 0

    @staticmethod
    def regexp_substr(pattern, source_string, flags=0, occurrence=0):
        """
            source_string：源字符串，表示要在其中进行搜索匹配项的字符串。
            pattern：正则表达式模式，表示要匹配的模式。
            flags：可选参数，用于指定正则表达式的标志。
            occurrence:获取匹配集中到的第几个字符串，0代表第一个，以此类推，若>=匹配集的长度，返回None。

            flags:  re.I 或 re.IGNORECASE：忽略大小写匹配。
                    re.M 或 re.MULTILINE：多行模式，使 ^ 和 $ 可以匹配每行的开头和结尾。
                    re.S 或 re.DOTALL：点号 (.) 可以匹配换行符。
                    re.X 或 re.VERBOSE：冗长模式，可以在正则表达式中添加注释和空格，提高可读性。
        """
        matchs = vicTools.regexp_findall(pattern=pattern, source_string=source_string, flags=flags)
        matchs_length = len(matchs)
        return matchs[occurrence] if occurrence in range(matchs_length) or occurrence in range(-matchs_length, 0) else None

    @staticmethod
    def regexp_count(pattern, source_string, flags=0):
        """
            source_string：源字符串，表示要在其中进行搜索匹配项的字符串。
            pattern：正则表达式模式，表示要匹配的模式。
            flags：可选参数，用于指定正则表达式的标志。

            flags:  re.I 或 re.IGNORECASE：忽略大小写匹配。
                    re.M 或 re.MULTILINE：多行模式，使 ^ 和 $ 可以匹配每行的开头和结尾。
                    re.S 或 re.DOTALL：点号 (.) 可以匹配换行符。
                    re.X 或 re.VERBOSE：冗长模式，可以在正则表达式中添加注释和空格，提高可读性。
        """
        return len(vicTools.regexp_findall(pattern=pattern, source_string=source_string, flags=flags))

    @staticmethod
    def regexp_instr(pattern, source_string, flags=0, occurrence=0):
        """
            source_string：源字符串，表示要在其中进行搜索匹配项的字符串。
            pattern：正则表达式模式，表示要匹配的模式。
            flags：可选参数，用于指定正则表达式的标志。
            occurrence:可选参数，获取匹配集中到的第几个字符串，0代表第一个，以此类推，若>=匹配集的长度，返回空串。

            flags:  re.I 或 re.IGNORECASE：忽略大小写匹配。
                    re.M 或 re.MULTILINE：多行模式，使 ^ 和 $ 可以匹配每行的开头和结尾。
                    re.S 或 re.DOTALL：点号 (.) 可以匹配换行符。
                    re.X 或 re.VERBOSE：冗长模式，可以在正则表达式中添加注释和空格，提高可读性。
        """
        temp = vicTools.regexp_substr(pattern=pattern, source_string=source_string, flags=flags, occurrence=occurrence)
        return source_string.find(temp) if temp is not None else -1

    @staticmethod
    def get_char(string, rep='★'):
        if string.count(rep) == 0:
            return rep
        for rep1 in map(chr, range(1, 128)):
            if string.count(rep1) == 0:
                return rep1
        # raise Exception(f"请设置一个源字符不包含{rep}的字符！")
        return None

    @staticmethod
    def check_no_overlap(strings):
        """list<str> 若字符串之间互不包含返回True,否则False,用all语法"""
        return all(strings[i] not in strings[j] for i in range(len(strings)) for j in range(len(strings)) if i != j)

    @staticmethod
    def regexp_split(pattern, source_string, flags=0, rep='★'):
        """
            pattern：正则表达式模式，表示要匹配的模式。
            source_string：源字符串，表示要在其中进行搜索匹配项的字符串。
            注意用的是★作为替换字符，如果字符串包含★将不适用
        """
        # 编译正则表达式
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
                # raise TypeError("pattern 参数类型错误,只接受类型(str,list, tuple, set)")
                return None
        else:
            # raise ValueError(f"请设置一个源字符不包含{rep}的字符！")
            return None

    @staticmethod
    def _split(string, sep, rep='★'):
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
        """
            将separator中每个字符都作为一个分隔符，而不是整体，
            注意用的是★作为替换字符，如果字符串包含★将不适用
        """

        if isinstance(separator, str):
            return string.split(separator)
        elif isinstance(separator, (list, tuple, set)):
            sep = set()
            for p in separator:
                if isinstance(p, str):
                    sep.add(p)
            # rep='★'
            return vicTools._split(string=string, sep=list(sep), rep=rep)
        else:
            # raise TypeError("separator 参数类型错误,只接受类型(str,list, tuple, set)")
            return None


# 定义必须返回特定类型的魔法方法列表
_RETURN_TYPE_RESTRICTED_METHODS = {
    # 布尔相关
    '__bool__', '__len__', '__hasattr__', '__contains__',
    
    # 数值转换
    '__int__', '__float__', '__complex__', '__index__', '__iter__',
    
    # 字符串表示
    '__str__', '__repr__', '__format__', '__bytes__', '__fspath__', '__qualname__', '__name__',
    
    # 哈希
    '__hash__',
    
    # 异步相关
    '__aiter__', '__anext__', '__await__', '__aenter__', '__aexit__',
    
    # 数值运算
    '__ceil__', '__floor__', '__trunc__',
    
    # 比较操作（应该返回bool）
    '__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__',
    
    # 其他
    '__length_hint__',
}

# 必须返回None的魔法方法
_MUST_RETURN_NONE = {
    '__setattr__', '__delattr__', '__setitem__', '__delitem__',
    '__set__', '__delete__', '__init__'
}

_OTHER_LIMITATIONS = {
    '__get__' ,#:只能返回实例属性，不能返回类属性
    '__class__',#:只能返回类对象，不能返回实例对象
    '__dict__',#:只能返回实例字典，不能返回类字典
    '__slots__',#:只能返回实例属性，不能返回类属性
    '__init_class__', #:只能返回None，不能返回其他值
    '__is_subclass__',#:只能返回Boolean值，不能返回其他值
    '__getattribute__',
    '__init_subclass__',
    '__subclasshook__',
    '__instancecheck__',
    '__subclasscheck__',
    '__class_getitem__'
}

_is_iterable = lambda obj: isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray, memoryview))


def box(func=None, *, signature_from=None):
    if func is None:
        return lambda f: box(f, signature_from=signature_from)
    @wdeco
    def _box(wrapped, instance, args, kwargs):
        def _nobox(obj):
            if isinstance(obj, Box):
                return obj.__wrapped__
            else:
                return obj
        args = list(map(_nobox, args))
        kwargs = {k: _nobox(v) for k, v in kwargs.items()}
        rs = wrapped(*args, **kwargs)
        if rs is None:
            return instance
        if isinstance(rs, Box):
            return rs
        elif isinstance(rs, (dict, list, tuple, set, str, int, float, bool, datetime, bytes, bytearray, slice, complex, type, object)):
            return Box(rs)
        elif isinstance(rs, Iterable) and not isinstance(rs, (str, bytes)):
            return Box(list(rs))
        else:
            return Box(rs)

    if signature_from is not None:
        try:
            from functools import update_wrapper
            update_wrapper(_box, signature_from)
        except ValueError:
            pass
    return _box(func)


### for box magic wrapped functions 
@box
def __box_wrapped_call__(self, *args, **kwargs):
    if callable(self):
        return self(*args, **kwargs)
    if not callable(self.__wrapped__):
        raise TypeError(f"'{type(self).__name__}' object is not callable")
    return self.__wrapped__(*args, **kwargs)


class CallableDescriptor:
    """描述符，控制__call__属性的访问"""
    def __init__(self):
        self.enabled = False
    
    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError("Can only be accessed from an instance")
        if isinstance(instance, Box):
            if callable(instance.__wrapped__):
                self.enable()
            else:
                self.disable()
                
        if not self.enabled:
            raise TypeError(f"'{type(instance).__name__}' object is not callable")
        # 返回一个可调用函数
        return partial(__box_wrapped_call__, instance)
    
    def enable(self):
        self.enabled = True
    
    def disable(self):
        self.enabled = False


class Box(AOP):
    
    __call__ = CallableDescriptor()
    
    def copy(self):
        cls = type(self)
        return cls(self.__wrapped__.copy())
    
    @box
    def run(self, func=print, *args, **kwargs):
        if isinstance(func, str):
            func = g(func)
        if not callable(func):
            raise TypeError(f"func 参数类型错误,只接受类型(callable)")
        nobox = kwargs.pop('nobox', False)
        arg0 = self if nobox else self.__wrapped__
        unpack = kwargs.pop('unpack', "")
        rerun = kwargs.pop('rerun', False)
        if unpack == "*":
            if not isinstance(arg0, Iterable):
                raise TypeError(f"object of type '{type(arg0).__name__}' has no len()")
            return [func(arg, *args, **kwargs) for arg in arg0] if rerun else func(*arg0, *args, **kwargs)
        elif unpack == "**":
            if not isinstance(arg0, dict):
                raise TypeError(f"object of type '{type(arg0).__name__}' has no len()")
            return {k: func(v, *args, **kwargs) for k, v in arg0.items()} if rerun else func(*args, **arg0, **kwargs)
        else:
            return func(arg0, *args, **kwargs)
    
    @box
    def __dir__(self):
        base = self.__wrapped__
        rs = dir(base)
        st = set(rs)
        if isinstance(base, dict):
            ks = set(_get_methods('dict').keys())
        elif isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            ks = set(_get_methods('list').keys())
        elif isinstance(base, str):
            ks = set(_get_methods('str').keys())
        elif isinstance(base, datetime):
            ks = set(_get_methods('datetime').keys())
        else:
            ks = set()
        rs = st | ks
        if '__call__' in rs and not callable(self.__wrapped__):
            rs -= set(['__call__'])
        return list(sorted(rs))
    
    def __hasattr__(self, name):
        return name in self.__dir__()

    def __getattr__(self, name):
        if not self.__hasattr__(name):
            raise AttributeError(f"type object '{type(self).__name__}' has no attribute '{name}'")
        attr = getattr(self.__wrapped__, name)
        if callable(attr):
            return box(attr)
        return attr


def setattr_box(attr, attr_name: str = None, cover=True, decorator=box, signature_from=None):
    global Box
    try:
        attr_name = attr_name or attr.__name__
    except AttributeError:
        attr_name = attr_name or attr.__qualname__
        if not callable(attr):
            raise TypeError(f"attr 参数类型错误,只接受类型(callable)")

    if hasattr(Box, attr_name) and not cover:
        raise AttributeError(f"attribute '{attr_name}' already exists")
    if decorator is None:
        setattr(Box, attr_name, attr)
        from functools import update_wrapper
        update_wrapper(getattr(Box, attr_name), signature_from)
    elif decorator is box:
        setattr(Box, attr_name, box(attr, signature_from=signature_from))
    else:
        setattr(Box, attr_name, decorator(attr))
        from functools import update_wrapper
        update_wrapper(getattr(Box, attr_name), signature_from)


def show_dir(obj):
    print(f"-----{obj}----")
    print("---------start---------")
    rs = filter(lambda x: not x.startswith("_"), dir(obj))
    from inspect import signature
    rs = map(g(" x => c = getattr(obj,x); None if not callable(c) else (x,sig(c))  ", {'sig': signature, 'obj': obj}), rs)
    
    print(*filter(lambda x: x is not None, rs), sep="\n")
    print("---------end---------")

### for list wrapped functions 

@box
def __list__wrapped_map__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return map(func, self) if cls is None else cls(map(func, self))

@box
def __list__wrapped_filter__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return filter(func, self) if cls is None else cls(filter(func, self))

@box
def __list__wrapped_filterfalse__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return filterfalse(func, self) if cls is None else cls(filterfalse(func, self))

@box
def __list__wrapped_enumerate__(self, start=0, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return enumerate(self, start) if cls is None else cls(enumerate(self, start))

@box
def __list__wrapped_reduce__(self, func, *, cls=None):
    func = g(func) if isinstance(func, str) else func
    return reduce(func, self) if cls is None else cls(reduce(func, self))

@box
def __list__wrapped_zip__(self, *its, **kwargs):
    cls = kwargs.pop('cls', None)
    cls = cls or type(self.__wrapped__)
    return zip(self, *its, **kwargs) if cls is None else cls(zip(self, *its, **kwargs))

@box
def __list__wrapped_zip_longest__(self, *its, **kwargs):
    cls = kwargs.pop('cls', None)
    cls = cls or type(self.__wrapped__)
    fillvalue = kwargs.pop('fillvalue', None)
    return zip_longest(self, *its, fillvalue=fillvalue) if cls is None else cls(zip_longest(self, *its, fillvalue=fillvalue))

@box
def __list__wrapped_all__(self, func):
    func = g(func) if isinstance(func, str) else func
    return all(self) if func is None else all(func(x) for x in self)

@box
def __list__wrapped_any__(self, func):
    func = g(func) if isinstance(func, str) else func
    return any(self) if func is None else any(func(x) for x in self)

@box
def __list__wrapped_collect__(self, func=None, *, cls=list):
    """
    collect the elements of the iterator into a list or other iterable.
    if func is not None, apply the function to each element before collecting.
    """
    if func is None:
        return cls(self)
    else:
        func = g(func) if isinstance(func, str) else func
        return cls(filter(lambda x: x is not None, map(func, self)))

@box
def __list__wrapped_sorted__(self, key=None, reverse=False, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return sorted(self, key=key, reverse=reverse) if cls is None else cls(sorted(self, key=key, reverse=reverse))

@box
def __list__wrapped_compress__(self, selectors, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return compress(self, selectors) if cls is None else cls(compress(self, selectors))

@box
def __list__wrapped_groupby__(self, key=None, *, cls=None):
    cls = cls or type(self.__wrapped__)
    key = g(key) if isinstance(key, str) else key
    return groupby(self, key=key) if cls is None else cls(groupby(self, key=key))

@box
def __list__wrapped_count_by__(self, key=None, *, cls=None):
    # cls = cls or type(self.__wrapped__)
    key = g(key) if isinstance(key, str) else key
    from .seq import Seq
    return Seq(self).count_by(key=key).collect() if cls is None else cls(Seq(self).count_by(key=key).collect())

@box
def __list__wrapped_reduce_by__(self, key=None, func=None, *, cls=None):
    cls = cls or type(self.__wrapped__)
    key = g(key) if isinstance(key, str) else key
    func = g(func) if isinstance(func, str) else func
    from .seq import Seq
    return Seq(self).reduce_by(key=key, func=func).collect() if cls is None else cls(Seq(self).reduce_by(key=key, func=func).collect())

@box
def __list__wrapped_find__(self, func=None, *, cls=None):
    # cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    from .seq import Seq
    return Seq(self).find(func=func) if cls is None else cls(Seq(self).find(func=func))

@box
def __list__wrapped_find_index__(self, func=None, *, cls=None):
    # cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    from .seq import Seq
    return Seq(self).find_index(func=func) if cls is None else cls(Seq(self).find_index(func=func))

@box
def __list__wrapped_accum__(self, func, initial=None, *, cls=None):
    # cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return accumulate(self, func, initial=initial) if cls is None else cls(accumulate(self, func, initial=initial))

@box
def __list__wrapped_take_while__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return takewhile(func, self) if cls is None else cls(takewhile(func, self))

@box
def __list__wrapped_drop_while__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return dropwhile(func, self) if cls is None else cls(dropwhile(func, self))

@box
def __list__wrapped_take__(self, n, action=False, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return islice(self, n) if cls is None else cls(islice(self, n))

@box
def __list__wrapped_tee__(self, n=2, fillvalue=None, *, cls=None):
    cls = cls or type(self.__wrapped__)
    from .seq import Seq
    return Seq(self).tee(n, fillvalue=fillvalue) if cls is None else cls(Seq(self).tee(n, fillvalue=fillvalue))

@box
def __list__wrapped_skip__(self, n, *, cls=None):
    cls = cls or type(self.__wrapped__)
    from .seq import Seq
    return Seq(self).skip(n) if cls is None else cls(Seq(self).skip(n))

@box
def __list__wrapped_mapmap__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    from .seq import Seq
    rs = Seq(self).mapmap(func).collect()
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_flatten__(self, *, cls=None):
    cls = cls or type(self.__wrapped__)
    from .seq import Seq
    return Seq(self).flatten().collect() if cls is None else cls(Seq(self).flatten().collect())

@box
def __list__wrapped_starmap__(self, func, *, cls=None):
    cls = cls or type(self.__wrapped__)
    func = g(func) if isinstance(func, str) else func
    return starmap(func, self) if cls is None else cls(starmap(func, self))

@box
def __list__wrapped_join__(self, sep=','):
    return sep.join(self.map(str))

@box
def __list__wrapped_distinct__(self, *, cls=None):
    cls = cls or type(self.__wrapped__)
    from .seq import Seq
    return Seq(self).distinct().collect() if cls is None else cls(Seq(self).distinct().collect())

@box
def __list__wrapped_extend__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(self) + list(other)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_append__(self, other, *, cls=None):
    if isinstance(self.__wrapped__, list):
        self.__wrapped__.append(other)
        return self
    cls = cls or type(self.__wrapped__)
    rs = list(self) + [other]
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_prepend__(self, other, *, cls=None):
    if isinstance(self.__wrapped__, list):
        self.__wrapped__.insert(0, other)
        return self
    cls = cls or type(self.__wrapped__)
    rs = [other] + list(self)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_add__(self, *a, **k):
    cls = k.pop('cls', type(self.__wrapped__))
    from .seq import Seq
    rs = Seq(self).add(*a, **k).collect()
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_insert__(self, index, other, *, cls=None):
    if isinstance(self.__wrapped__, list):
        self.__wrapped__.insert(index, other)
        return self
    cls = cls or type(self.__wrapped__)
    rs = list(self)
    rs.insert(index, other)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_remove__(self, value, *, cls=None):
    if isinstance(self.__wrapped__, list):
        self.__wrapped__.remove(value)
        return self
    cls = cls or type(self.__wrapped__)
    rs = list(self)
    rs.remove(value)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_pop__(self, index=-1, *, cls=None):
    if isinstance(self.__wrapped__, list):
        self.__wrapped__.pop(index)
        return self
    cls = cls or type(self.__wrapped__)
    rs = list(self)
    rs.pop(index)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_popleft__(self, *, cls=None):
    if isinstance(self.__wrapped__, deque):
        self.__wrapped__.popleft()
        return self
    if not isinstance(self.__wrapped__, list):
        self.__wrapped__.pop(0)
        return self
    
    cls = cls or type(self.__wrapped__)
    rs = deque(self)
    rs.popleft()
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_sort__(self, *, cls=None):
    if isinstance(self.__wrapped__, list):
        self.__wrapped__.sort()
        return self
    cls = cls or type(self.__wrapped__)
    rs = list(self)
    rs.sort()
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_count__(self, value, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(self).count(value)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_index__(self, value, start=0, stop=None, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(self)
    rs.index(value, start, stop)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_reverse__(self, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(self)
    rs.reverse()
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_rotate__(self, n, *, cls=None):
    if isinstance(self.__wrapped__, deque):
        self.__wrapped__.rotate(n)
        return self
    cls = cls or type(self.__wrapped__)
    rs = deque(self)
    rs.rotate(n)
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_intersection__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(set(self) & set(other))
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_union__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(set(self) | set(other))
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_difference__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(set(self) - set(other))
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_symmetric_difference__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = list(set(self) ^ set(other))
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_issubset__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = set(self).issubset(set(other))
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_issuperset__(self, other, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = set(self).issuperset(set(other))
    return rs if cls is None else cls(rs)

@box
def __list__wrapped_shift__(self, num=1, fill_value=None, cycle=False, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = vicTools.shift(self, num=num, fill_value=fill_value, cycle=cycle)
    return rs if cls is None else cls(rs)


### for dict wrapped functions 

@box
def __dict__wrapped_keys__(self, *, cls=None):
    cls = cls or list
    return self.__wrapped__.keys() if cls is None else cls(self.__wrapped__.keys())

@box
def __dict__wrapped_values__(self, *, cls=None):
    cls = cls or list
    return self.__wrapped__.values() if cls is None else cls(self.__wrapped__.values())

@box
def __dict__wrapped_items__(self, *, cls=None):
    cls = cls or list
    return self.__wrapped__.items() if cls is None else cls(self.__wrapped__.items())

@box
def __dict__wrapped_get__(self, key, default=None, *, cls=None):
    # cls = cls or type(self.__wrapped__)
    return self.__wrapped__.get(key, default) if cls is None else cls(self.__wrapped__.get(key, default))

@box
def __dict__wrapped_pop__(self, key, default=None, *, cls=None):
    # cls = cls or type(self.__wrapped__)
    return self.__wrapped__.pop(key, default) if cls is None else cls(self.__wrapped__.pop(key, default))

@box
def __dict__wrapped_popitem__(self, item, *, all=False, cls=None):
    if isinstance(self.__wrapped__, dict):
        rs = {}
        for k, v in self.__wrapped__.items():
            if v == item:
                if not all:
                    self.__wrapped__.pop(k)
                    return k, v if cls is None else cls((k, v))
                rs[k] = v
        else:
            for k in rs:
                self.__wrapped__.pop(k)
        return rs if cls is None else cls(rs)
    
    cls = cls or type(self.__wrapped__)
    rs = {}
    ks = set()
    for k, v in self.items():
        if v == item:
            rs[k] = v
            if not all:
                break
    if ks:
        for k in ks:
            self.pop(k)
    return rs if cls is None else cls(rs)

@box
def __dict__wrapped_update__(self, other, *, cls=None):
    if isinstance(self.__wrapped__, dict):
        self.__wrapped__.update(other)
        return self
    cls = cls or type(self.__wrapped__)
    rs = dict(self)
    rs.update(other)
    return rs if cls is None else cls(rs)

@box
def __dict__wrapped_clear__(self, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return Box({})


## for string wrapped functions 
@box
def __str__wrapped_replace_vars__(self, repl_dict=None, *, cls=None):
    run_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    cls = cls or type(self.__wrapped__)
    s = str(self)
    pt = r"\{run_date(_std)?([\+\-][0-9]+)?\}"
    ss = self.regexp_findall(pt, s)
    sss = list(map(lambda x: vicTools.offset_date(run_date=run_date, offset_days=int(x[1]) if x[1] else 0, std=bool(x[0])), ss))
    for x, y in zip(ss, sss):
        x = "{run_date" + x[0] + x[1] + "}"
        s = s.replace(x, y)
    if repl_dict is not None:
        s = s.format(**repl_dict)
    return s if cls is None else cls(s)

@box
def __str__wrapped_write__(self, file_path="", *, mode='w', encoding='utf-8'):
    file_path = str(file_path) or str(self)
    with open(file_path, mode=mode, encoding=encoding) as f:
        f.write(self)
    return self

@box
def __str__wrapped_read__(self, file_path="", *, mode='r', encoding='utf-8', lines=False):
    file_path = str(file_path) or str(self)
    with open(file_path, mode=mode, encoding=encoding) as f:
        if lines:
            return f.readlines()
        return f.read()

@box
def __str__wrapped_readlines__(self, file_path="", *, mode='r', encoding='utf-8'):
    return self.read(file_path, mode=mode, encoding=encoding, lines=True)

def __str__wrapped_readlines_iter__(self, file_path="", *, mode='r', encoding='utf-8'):
    file_path = str(file_path) or str(self)
    with open(file_path, mode=mode, encoding=encoding) as f:
        for line in f:
            yield line


@box
def __str__wrapped_rlike__(self, pattern, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return cls(re.search(pattern, self) is not None)

@box
def __str__wrapped_regexp_replace__(self, pattern, repl, *, count=0, cls=None):
    cls = cls or type(self.__wrapped__)
    return re.sub(pattern, repl, self, count=count) if cls is None else cls(re.sub(pattern, repl, self, count=count))

@box
def __str__wrapped_split__(self, sep=None, maxsplit=-1, *, cls=None):
    cls = cls or type(self.__wrapped__)
    wrapped = self.__wrapped__
    return wrapped.split(sep, maxsplit) if cls is None else cls(wrapped.split(sep, maxsplit))

@box
def __str__wrapped_regexp_findall__(self, pattern, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return re.findall(pattern, self) if cls is None else cls(re.findall(pattern, self))

@box
def __str__wrapped_regexp_split__(self, pattern, flags=0, rep='★', *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = vicTools.regexp_split(pattern, self, flags=flags, rep=rep)
    return rs if cls is None else cls(rs)

@box
def __str__wrapped_regexp_count__(self, pattern, *, cls=None):
    cls = cls or type(self.__wrapped__)
    return len(re.findall(pattern, self)) if cls is None else cls(len(re.findall(pattern, self)))

@box
def __str__wrapped_regexp_substr__(self, pattern, flags=0, occurrence=0, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = vicTools.regexp_substr(pattern, self, flags=flags, occurrence=occurrence)
    return rs if cls is None else cls(rs)

@box
def __str__wrapped_regexp_instr__(self, pattern, start=1, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = vicTools.regexp_instr(pattern, self, flags=0, occurrence=start-1)
    return rs if cls is None else cls(rs)

@box
def __str__wrapped_trim__(self, chars=None, left=True, right=True, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = vicTools.trim(self, chars=chars, left=left, right=right)
    return rs if cls is None else cls(rs)

@box
def __str__wrapped_builed_text__(self, dct=None, lst=None, sep='\n ,', check_key: str = 'item', max_iter_num=999, *, cls=None):
    cls = cls or type(self.__wrapped__)
    rs = vicTools.build_text(self, dct=dct, lst=lst, sep=sep, check_key=check_key, max_iter_num=max_iter_num)
    return rs if cls is None else cls(rs)

## for datetime wrapped functions 
@box
def __datetime__wrapped_get_py_fmt__(self, fmt='yyyyMMdd'):
    if not '%' in fmt:
        fmt = fmt.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
        fmt = fmt.replace('YYYY', '%Y').replace('SS', '%S').replace('ss', '%S').replace('yy', '%y')
    
    return fmt

@box
def __datetime__wrapped_datetime_add__(self, other):
    if isinstance(other, (int, float)):
        diff_days = timedelta(days=other)
        rs = self.__wrapped__ + diff_days
    elif isinstance(other, timedelta):
        diff_days = other
        rs = self.__wrapped__ + diff_days
    elif isinstance(other, datetime):
        rs = float((self.__wrapped__ - other).total_seconds())
    return rs

@box
def __datetime__wrapped__datetime_sub__(self, other):
    if isinstance(other, (int, float)):
        diff_days = timedelta(days=other)
        rs = self.__wrapped__ - diff_days
    elif isinstance(other, timedelta):
        diff_days = other
        rs = self.__wrapped__ - diff_days
    elif isinstance(other, datetime):
        rs = float((self.__wrapped__ - other).total_seconds())
    return rs

@box
def __datetime__wrapped_get_week__(self, num: int = 0, weekday: int = 1, fmt='%Y%m%d'):
    fmt = str(self.get_py_fmt(fmt))
    if not weekday in range(1, 8):
        raise ValueError("param weekday must in 1 to 7 , 1 is MonDay !!!")
    d = int(self.__wrapped__.strftime('%u')) - weekday
    w0 = self.__wrapped__ - timedelta(days=d)
    if num == 0:
        return w0.strftime(fmt)
    else:
        w = w0 - timedelta(days=7 * num)
        return w.strftime(fmt)

@box
def __datetime__wrapped_get_month__(self, num: int = 0, last_day=False, fmt='%Y%m%d'):
    fmt = str(self.get_py_fmt(fmt))
    y, m = self.__wrapped__.year, self.__wrapped__.month
    num = num - 1 if last_day else num

    while num > 0:
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        num -= 1
    
    while num < 0:
        m += 1
        if m == 13:
            m = 1
            y += 1
        num += 1
    
    m = m if m > 9 else f'0{m}'
    fmt = str(self.get_py_fmt('yyyy-MM-01'))
    dt = datetime.strptime(f'{y}-{m}-01', fmt)
    return (dt - timedelta(days=1)).strftime(fmt) if last_day else dt.strftime(fmt)

@box
def __datetime__wrapped_get_date_range__(self, start_date=None, end_date=None, periods=None, freq='D', fmt='yyyyMMdd') -> List[str]:
    from .daterange import get_date_range
    dt_str = self.strftime(str(self.get_py_fmt(fmt)))
    if start_date is not None and end_date is not None:
        pass
    elif start_date is None and end_date is not None:
        start_date = dt_str
    elif start_date is not None and end_date is None:
        end_date = dt_str
    else:
        end_date = dt_str
    return get_date_range(start_date, end_date, periods=periods, freq=freq, fmt=fmt)

@box
def __datetime__wrapped_strftime__(self, fmt='%Y%m%d'):
    return self.__wrapped__.strftime(fmt)

@box
def __datetime__wrapped_strptime__(self, date_str, fmt='%Y%m%d'):
    return datetime.strptime(date_str, self.get_py_fmt(fmt))



_local_dir = dir()

@lru_cache(maxsize=256)
def _get_methods(tp):
    start = f"__{tp}__wrapped_"
    end = "__"
    b = lambda x: x.startswith(start) and x.endswith(end)
    return {x[len(start):-len(end)]: eval(x) for x in _local_dir if b(x)}


for tp in ['list', 'dict', 'str', 'datetime']:
    for name, func in _get_methods(tp).items():
        setattr(Box, name, func)


if __name__ == '__main__':
    # show_dir(Seq)
    # print(_get_methods('list').keys())
    # print(Box([1,2,3]).__dir__())

    lst = Box([1, 2, 3])
    lst1 = lst.append(4)
    print(lst1)
    print(lst)
    print(lst.map(lambda x: x + 1))
    print(lst.filter(lambda x: x > 1))
    print(lst.reduce(lambda x, y: x + y))
    # print(dir(lst))

    dt = Box(datetime.now())
    print(dt.get_week(weekday=1))
    print(dt.get_month(last_day=True))
    # print(dt.get_date_range(start_date='20210101', end_date='20211231', freq='M', fmt='%Y%m'))
    # help(dt.map)
    # print(dir(lst))
    # print(dir(lst.__wrapped__))
    lst.run(dir).run()


    func = lambda x: x + 1
    f = Box(func)
    print(f(1))
    print(f.run("_(13)"))

    print(callable(f), callable(lst))

    print(dir(Box('17')))
    
    
    d = Box({'a': 1, 'b': 2, 'c': 2})
    
    print(d)
    p = d.popitem(item=2, all=True)
    print(p)
    print(d)
    
    fmt = dt.get_py_fmt('yyyyMMdd')
    print(fmt, type(fmt), isinstance(fmt, str))
    yest = datetime.now() - timedelta(days=1)
    print(dt.strftime(fmt))