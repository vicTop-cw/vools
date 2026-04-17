import copy
import json
from collections import OrderedDict, namedtuple, deque
from collections.abc import Iterable
import itertools
from functools import wraps, reduce, partial, lru_cache, update_wrapper
import re
import time
from datetime import datetime, timedelta
import pandas as pd
import string
import pkgutil
import random

from .data import Seq, NONE
from .functional.placeholder import _
from .functional.box import box, Box, setattr_box

__all__ = ['vicTools', 'vicDate', 'vicText', 'vicList']

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
            # 动态检查类型，避免循环引用
            if hasattr(result, '__class__'):
                class_name = result.__class__.__name__
                if class_name in ['vicText', 'vicList']:
                    return result
            if isinstance(result, str):
                # 动态导入vicText
                from .vools import vicText
                return vicText(result)
            if isinstance(result, Iterable):
                # 动态导入vicList
                from .vools import vicList
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
        param_symbols = ",".join(vicTools.transferCols(param_symbols))
        if isinstance(ex, str):
            ex = f"lambda {param_symbols} : {ex}"
            return eval(ex, globals(), locals())
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
            dss = [d.date() for d in pd.date_range(periods=nums, end=run_date, freq=freq)][::-1]
            return [f"{d.strftime(fmt)}-{d.strftime(fmt)}" for d in dss] if duo else [d.strftime(fmt) for d in dss]
        if freq == 'W':
            temp_run_date = run_date
            if run_date.weekday() != 6:
                temp_run_date += timedelta(days=7)

            dss = [d.date() for d in pd.date_range(periods=nums, end=temp_run_date, freq=freq)][::-1]

            return [(d - timedelta(days=6)).strftime(fmt) + "-" + (d if i > 0 else run_date).strftime(fmt) for i, d in enumerate(dss)] if duo else [(d if i > 0 else run_date).strftime(fmt) for i, d in enumerate(dss)]

        end_of_month = run_date.replace(month=run_date.month + 1, day=1) - timedelta(days=1)

        dss = [d.date() for d in pd.date_range(periods=nums, end=end_of_month, freq=freq)][::-1]

        return [d.replace(day=1).strftime(fmt) + "-" + (d if i > 0 else run_date).strftime(fmt) for i, d in enumerate(dss)] if duo else [(d if i > 0 else run_date).strftime(fmt) for i, d in enumerate(dss)]

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
        # 生成单个单词
        def generate_word(length):
            letters_and_digits = string.ascii_letters + string.digits
            return ''.join(random.choice(letters_and_digits) for _ in range(length))

        # 生成字段名
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
        # 获取所有已安装的包
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
            # 尝试将输入解析为 JSON
            if isinstance(field_name, str):
                # 如果是字符串，尝试将其转换为字典
                field_name = json.loads(field_name)

            # 检查是否为字典
            if isinstance(field_name, dict):
                return list(field_name.keys())
        except (ValueError, TypeError):
            # 捕获 JSON 解析错误或类型错误
            return []

        # 如果不是字典或 JSON 格式的文本，返回空数组
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
        # 使用集合去重并合并数组
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
        # raise Exception(f"请设置一个源字符不包含{rep}的字符！")
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
            # rep='★'
            return vicTools._split(string=string, sep=list(sep), rep=rep)
        else:
            # raise TypeError("separator 参数类型错误,只接受类型(str,list, tuple, set)")
            return None

    @staticmethod
    def get_insert_sql_for_postgre(df: pd.DataFrame, target_table_in_post: str, if_print=True):
        """生成PostgreSQL的插入SQL
        
        Args:
            df: pandas DataFrame
            target_table_in_post: 目标表名
            if_print: 是否打印SQL
            
        Returns:
            创建表SQL、截断表SQL、插入SQL
        """
        # 获取列名
        columns = df.columns.tolist()

        # 获取数据类型并判断如何生成插入的SQL值
        def format_value(value):
            if isinstance(value, (int, float)):  # 数字类型不加引号
                return str(value)
            elif value is None:  # 处理None值
                return 'NULL'
            else:
                return f"'{str(value)}'"  # 其他类型需要加引号

        # 生成插入的SQL值部分
        values_list = []
        for _, row in df.iterrows():
            values = [format_value(row[col]) for col in columns]
            values_list.append(f"({', '.join(values)})")

        # 生成INSERT语句
        insert_sql = f"INSERT INTO {target_table_in_post} ({', '.join(columns)}) VALUES\n" + ",\n".join(values_list) + ";"

        # 生成CREATE TABLE语句，假设所有数据类型是STRING
        # 这里简单假设所有列都是VARCHAR，如果需要根据实际数据类型修改，可以在此修改
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {target_table_in_post} (
            {', '.join([f"{col} VARCHAR" if col != 'xh' else f"{col} INTEGER" for col in columns])}
        );
        """

        # 生成TRUNCATE语句
        truncate_sql = f"TRUNCATE TABLE {target_table_in_post};"

        if if_print:
            print("--CREATE TABLE SQL:")
            print(create_table_sql)
            print("\n--TRUNCATE TABLE SQL:")
            print(truncate_sql)
            print("\n--INSERT INTO SQL:")
            print(insert_sql)

        # 返回表创建语句、清空表语句和插入语句
        return create_table_sql, truncate_sql, insert_sql

class vicDate(datetime):
    """日期类，继承自datetime，提供更多日期处理方法"""
    
    def __init__(self, dt=None, fmt=None):
        """初始化vicDate对象
        
        Args:
            dt: 日期对象、字符串或时间戳
            fmt: 日期格式
        """
        if dt is None:
            dt = datetime.now()

        if fmt is None:
            if isinstance(dt, (int, float)):
                fmt = '%Y-%m-%d %H:%M:%S'
            elif isinstance(dt, str):
                fmt = '%Y-%m-%d' if '-' in dt else '%Y%m%d'
                if ":" in dt:
                    fmt = f"{fmt} %H:%M:%S"
            else:
                fmt = '%Y-%m-%d %H:%M:%S'

        if not '%' in fmt:
            fmt = fmt.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
            fmt = fmt.replace('YYYY', '%Y').replace('SS', '%S').replace('ss', '%S').replace('yy', '%y')

        self.fmt = fmt

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

    def get_week(self, num: int = 0, weekday: int = 1):
        """获取指定周的日期
        
        Args:
            num: 周数偏移
            weekday: 周几（1-7，1表示周一）
            
        Returns:
            日期字符串
        """
        if not weekday in range(1, 8):
            raise ValueError("param weekday must in 1 to 7 , 1 is MonDay !!!")
        w0 = self - (int(self.strftime('%u')) - weekday)
        if num == 0:
            return w0.strftime(self.fmt)
        else:
            return (w0 - num * 7).strftime(self.fmt)

    def get_month(self, num: int = 0, last_day=False):
        """获取指定月的日期
        
        Args:
            num: 月数偏移
            last_day: 是否返回月末日期
            
        Returns:
            日期字符串
        """
        y, m = self.year, self.month
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
        dt = vicDate(f"{y}-{m}-01")
        return (dt - 1).strftime(self.fmt) if last_day else dt.strftime(self.fmt)

    def simplify(self, dates):
        """简化日期列表为日期范围
        
        Args:
            dates: 日期列表
            
        Returns:
            日期范围列表
        """
        dates = self.simplify_date_ranges(dates)
        if len(dates) == 0:
            return []
        spyDate = namedtuple("spyDate", ["start", "end", "cnt"])
        return [spyDate(str(vicDate(x, self.fmt)), str(vicDate(y, self.fmt)), int(vicDate(y) - vicDate(x) + 1)) for x, y in dates]

    @staticmethod
    def simplify_date_ranges(dates):
        """将日期列表简化为日期范围
        
        Args:
            dates: 日期列表
            
        Returns:
            日期范围列表
        """
        # 将日期字符串转换为日期对象，并排序
        if isinstance(dates, (tuple, list, set)):
            pass
        else:
            raise TypeError("dates must be (tuple,list,set) !!!")
        if len(dates) == 0:
            return []

        def _check(x):
            return vicTools.regexp_like(r"^[1-2][0-9]{3}[0-1][0-9][0-3][0-9]$", x) or vicTools.regexp_like(r"^[1-2][0-9]{3}-[0-1][0-9]-[0-3][0-9]$", x)

        dates = filter(_check, {str(d) for d in dates})

        dates = sorted(datetime.strptime(d, "%Y-%m-%d" if "-" in d else "%Y%m%d") for d in dates)

        fmt = "%Y-%m-%d" if "-" in str(dates[0]) else "%Y%m%d"

        # 初始化结果列表和临时变量
        simplified = []
        start = None

        for i, current_date in enumerate(dates):
            # 如果是列表中的第一个日期或者当前日期与前一个日期不连续
            if start is None or (i > 0 and (current_date - dates[i - 1]).days != 1):
                # 如果已经有一个开始日期，添加范围到结果列表
                if start is not None:
                    simplified.append((start.strftime(fmt), end.strftime(fmt)))
                # 更新开始日期
                start = current_date
            # 更新结束日期
            end = current_date

        # 添加最后一个范围到结果列表
        simplified.append((start.strftime(fmt), end.strftime(fmt)))

        return simplified

    def getDateRange(self, start=None, end=None, freq='D', periods=None) -> list:
        """生成日期范围
        
        Args:
            start: 开始日期
            end: 结束日期
            freq: 频率
            periods: 周期数
            
        Returns:
            日期列表
        """
        if end is None and periods is None:
            raise ValueError("params  'end' or 'periods' must give One ")
        if start is None and end is None:
            end = self.strftime('%Y-%m-%d')
            date_range = pd.date_range(end=end, periods=periods, freq=freq)
        elif start is None:
            if periods is None:
                date_range = pd.date_range(start=self.strftime('%Y-%m-%d'), end=end, freq=freq)
            else:
                date_range = pd.date_range(end=end, freq=freq, periods=periods)
        elif end is None:
            if periods is None:
                date_range = pd.date_range(start=start, end=self.strftime('%Y-%m-%d'), freq=freq)
            else:
                date_range = pd.date_range(start=start, freq=freq, periods=periods)
        else:
            start = vicDate(start, '%Y-%m-%d')
            date_range = pd.date_range(start=start, end=vicDate(end, '%Y-%m-%d'), freq=freq) if end else pd.date_range(start=start, periods=periods, freq=freq)

        return [d.date().strftime(self.fmt) for d in date_range]

    def getDateRangeEx(self, start=None, end=None, freq='D', periods=None) -> list:
        """生成日期范围（扩展版）
        
        Args:
            start: 开始日期
            end: 结束日期
            freq: 频率
            periods: 周期数
            
        Returns:
            日期列表
        """
        p1, p2, p3 = start is not None, end is not None, periods is not None
        cls = self.__class__
        dt_f = lambda x: cls(x, '%Y-%m-%d').strftime('%Y-%m-%d')
        if p1 and p2:
            start, end = dt_f(start), dt_f(end)
            if start > end:
                start, end = end, start
            parmas_dct = {'start': start, 'end': end, 'freq': freq}
        elif p1 and p3:
            parmas_dct = {'start': dt_f(start), 'periods': periods, 'freq': freq}
        elif p2 and p3:
            parmas_dct = {'end': dt_f(end), 'periods': periods, 'freq': freq}
        elif p1:
            start = dt_f(start)
            end = self.strftime('%Y-%m-%d')
            if start > end:
                start, end = end, start
            parmas_dct = {'start': start, 'end': end, 'freq': freq}
        elif p2:
            end = dt_f(end)
            start = self.strftime('%Y-%m-%d')
            if start > end:
                start, end = end, start
            parmas_dct = {'start': start, 'end': end, 'freq': freq}
        elif p3:
            start = self.strftime('%Y-%m-%d')
            parmas_dct = {'start': start, 'periods': periods, 'freq': freq}
        else:
            raise ValueError("params  'end' or 'periods' must give One ")

        daterange = pd.date_range(**parmas_dct)
        return [d.strftime(self.fmt) for d in daterange]

    def __new__(cls, dt=None, fmt=None):
        """创建vicDate对象
        
        Args:
            dt: 日期对象、字符串或时间戳
            fmt: 日期格式
            
        Returns:
            vicDate对象
        """
        if dt is None:
            dt = datetime.now()
        if isinstance(dt, (int, float)):  # 时间戳
            # result =  super().__new__(cls, dt)
            result = super().fromtimestamp(dt)
        elif isinstance(dt, str):  # 字符串日期
            if len(dt) == 8 and dt.isdigit():  # 8位数字格式
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]))
            elif re.search(r"^\d{4}-\d{2}-\d{2}$", dt):
                dt = dt.replace('-', '')
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]))
            elif re.search(r"^\d{4}-\d{2}-\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9]$", dt):
                tm = dt.split(" ")[1].split(":")
                dt = dt.split(" ")[0].replace('-', '')

                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), int(tm[2]))
            elif re.search(r"^\d{4}\d{2}\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9]$", dt):
                tm = dt.split(" ")[1].split(":")
                # dt = dt.split(" ")[0].replace('-', '')
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), int(tm[2]))
            else:
                if fmt is None:
                    raise ValueError("需要指定日期格式")
                result = super().__new__(cls, *cls._parse_date(dt, fmt))
        elif isinstance(dt, (datetime, cls)):  # datetime对象
            result = super().__new__(cls, dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)
        # elif isinstance(dt, vicDate):  # vicDate对象
        #     result =   super().__new__(cls, dt.year, dt.month, dt.day)
        else:
            raise TypeError("不支持的日期类型")
        return result

    @staticmethod
    def _parse_date(date_str, fmt):
        """解析日期字符串
        
        Args:
            date_str: 日期字符串
            fmt: 日期格式
            
        Returns:
            (年, 月, 日)元组
        """
        # 将字符串日期转换为年、月、日
        dt = datetime.strptime(date_str, fmt)
        return (dt.year, dt.month, dt.day)

    def __add__(self, other):
        """加法操作
        
        Args:
            other: 天数
            
        Returns:
            新的vicDate对象
        """
        if isinstance(other, (int, float)):
            # 计算新的日期
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) + timedelta(days=other)
            # 创建并返回新的vicDate对象
            return vicDate(new_datetime)
        else:
            raise TypeError("只能对整数执行加法操作")

    def __sub__(self, other):
        """减法操作
        
        Args:
            other: 天数或日期对象
            
        Returns:
            新的vicDate对象或天数差
        """
        if isinstance(other, (int, float)):
            # 计算新的日期
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) - timedelta(days=other)
            # 创建并返回新的vicDate对象
            return vicDate(new_datetime)
        elif isinstance(other, (datetime, vicDate)):
            diff = self.timestamp() - other.timestamp()
            return diff / 86400
        else:
            raise TypeError("只能对整数和日期执行减法操作")

    def __str__(self):
        """字符串表示
        
        Returns:
            日期字符串
        """
        if self.fmt:
            return self.strftime(self.fmt)
        else:
            return super().__str__()

    def __repr__(self):
        """ repr表示
        
        Returns:
            表示字符串
        """
        return f"vicDate('{self}')"

    def toString(self, fmt=None):
        """转换为字符串
        
        Args:
            fmt: 日期格式
            
        Returns:
            日期字符串
        """
        return str(self) if fmt is None else self.strftime(vicTools.get_py_fmt(fmt))

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
        # return [] if temp is None else [vicText(s) for s in temp]
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
        # 简化处理，直接返回原文本
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
        # return [vicText(s) for s in super().split(sep, maxsplit)] if sep is not None else [vicText(s) for s in super().split()]
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
        # return [vicText(s) for s in super().rsplit(sep, maxsplit)] if sep is not None else [vicText(s) for s in super().rsplit()]
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
        return vicList(vicText(s) for s in super().partition(sep))

    def rpartition(self, sep):
        """从右侧分割文本为三部分
        
        Args:
            sep: 分隔符
            
        Returns:
            分割后的vicList对象
        """
        return vicList(vicText(s) for s in super().rpartition(sep))

    def splitlines(self, keepends=False):
        """按行分割文本
        
        Args:
            keepends: 是否保留换行符
            
        Returns:
            分割后的vicList对象
        """
        # return vicList(vicText(s) for s in super().splitlines(keepends))
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
        # 简化处理，直接返回原文本
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

# 元类，用于修改isinstance的行为
class ListLikeMeta(type):
    """列表类似元类，用于修改isinstance的行为"""
    def __instancecheck__(cls, instance):
        """检查实例是否为列表或列表类似对象
        
        Args:
            instance: 要检查的实例
            
        Returns:
            是否为列表或列表类似对象
        """
        return isinstance(instance, (list, cls))

# 定义vicList类，使用元类
class vicList(Seq, metaclass=ListLikeMeta):
    """列表类，继承自Seq，提供更多列表处理方法"""
    
    def __init__(self, *origins):
        """初始化vicList对象
        
        Args:
            *origins: 初始化参数
        """
        # 先初始化数据，避免递归调用
        self._data = []
        # 处理输入参数
        if origins:
            if len(origins) == 1:
                # 如果只有一个参数，尝试将其转换为列表
                origin = origins[0]
                if hasattr(origin, '__iter__') and not isinstance(origin, (str, bytes, bytearray)):
                    self._data = list(origin)
                else:
                    self._data = [origin]
            else:
                # 多个参数，直接作为列表元素
                self._data = list(origins)
        # 调用 Seq 的初始化方法
        super().__init__(self._data)

    def __getitem__(self, index):
        """获取索引或切片
        
        Args:
            index: 索引或切片
            
        Returns:
            对应的元素或切片后的vicList对象
        """
        # 处理切片逻辑
        if isinstance(index, slice):
            return vicList(self._data[index])
        return self._data[index]

    def __len__(self):
        """获取长度
        
        Returns:
            列表长度
        """
        return len(self._data)

    def __iter__(self):
        """迭代列表
        
        Returns:
            迭代器
        """
        return iter(self._data)

    def __and__(self, other):
        """交集操作
        
        Args:
            other: 另一个列表
            
        Returns:
            交集后的vicList对象
        """
        return vicList(set(self._data) & set(other))

    def __or__(self, other):
        """并集操作
        
        Args:
            other: 另一个列表
            
        Returns:
            并集后的vicList对象
        """
        return vicList(set(self._data) | set(other))

    def __sub__(self, other):
        """差集操作
        
        Args:
            other: 另一个列表
            
        Returns:
            差集后的vicList对象
        """
        return vicList(set(self._data) - set(other))

    def __xor__(self, other):
        """对称差集操作
        
        Args:
            other: 另一个列表
            
        Returns:
            对称差集后的vicList对象
        """
        return vicList(set(self._data) ^ set(other))

    def __repr__(self):
        """repr表示
        
        Returns:
            表示字符串
        """
        return f"vicList({self._data!r})"

    @vicTools.transfer
    def __call__(self, func=print, *args, **kwargs):
        """调用列表
        
        Args:
            func: 调用函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            调用结果
        """
        return func(self, *args, **kwargs)

    def islice(self, start=None, stop=None, step=1):
        """自定义切片方法
        
        Args:
            start: 开始索引
            stop: 结束索引
            step: 步长
            
        Returns:
            切片后的vicList对象
        """
        # 处理默认参数
        if start is None:
            start = 0
        if stop is None:
            stop = len(self)

        # 动态计算实际索引
        start = max(0, start) if start >= 0 else max(len(self) + start, 0)
        stop = min(len(self), stop) if stop >= 0 else min(len(self) + stop, len(self))

        # 生成切片数据
        sliced = []
        i = start
        while (i < stop if step > 0 else i > stop) and 0 <= i < len(self):
            sliced.append(self[i])
            i += step
        return vicList(sliced)

    @property
    def unique(self):
        """获取唯一元素
        
        Returns:
            唯一元素的vicList对象
        """
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(OrderedDict.fromkeys(self._data).keys())

    def _run(self, func=print):
        """运行函数
        
        Args:
            func: 运行函数
            
        Returns:
            运行结果列表
        """
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [func(s) for s in self._data]
        elif isinstance(func, str):
            return [eval(func)(s) for s in self._data]
        else:
            return []

    def _run_filter(self, func=bool):
        """运行过滤函数
        
        Args:
            func: 过滤函数
            
        Returns:
            过滤后的结果列表
        """
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [s for s in self._data if func(s)]
        elif isinstance(func, str):
            return [s for s in self._data if eval(func)(s)]
        else:
            return []

    def foreach(self, func=print, filter_func=None, filter_first=True):
        """遍历列表
        
        Args:
            func: 遍历函数
            filter_func: 过滤函数
            filter_first: 是否先过滤
            
        Returns:
            处理后的vicList对象
        """
        if filter_func is None:
            if func is None:
                return self
            return self.map(func)
        if func is None:
            return self.filter(filter_func)

        if filter_first:
            return self.filter(filter_func).map(func)

        return self.map(func).filter(filter_func)

    def filterfalse(self, func=bool):
        """过滤不符合条件的元素
        
        Args:
            func: 过滤函数
            
        Returns:
            过滤后的vicList对象
        """
        if isinstance(func, str):
            func = eval(func)
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList([i for i in self._data if not func(i)])

    @vicTools.transfer
    def filter(self, func=bool):
        """过滤符合条件的元素
        
        Args:
            func: 过滤函数
            
        Returns:
            过滤后的结果
        """
        temp = self._run_filter(func)
        return vicList(temp) if isinstance(temp, Iterable) else temp

    @vicTools.transfer
    def map(self, func=None):
        """映射函数
        
        Args:
            func: 映射函数
            
        Returns:
            映射后的结果
        """
        if func is None:
            self._run(print)
            return self
        temp = self._run(func)
        return vicList(temp) if isinstance(temp, Iterable) else temp

    def _run_ex(self, func=print, symbols="x"):
        """运行函数（扩展版）
        
        Args:
            func: 运行函数
            symbols: 参数符号
            
        Returns:
            运行结果列表
        """
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return list(itertools.starmap(func, self._data))
        elif isinstance(func, str):
            return list(itertools.starmap(eval(func), self._data))
        else:
            return []

    @property
    def inner_iterable(self):
        """检查内部元素是否可迭代
        
        Returns:
            内部元素是否可迭代
        """
        l = len(self)
        if l == 0:
            return False
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return isinstance(self._data[0], Iterable) and not isinstance(self._data[0], (str, bytes, bytearray))

    @property
    def is_empty(self):
        """检查列表是否为空
        
        Returns:
            列表是否为空
        """
        return len(self) == 0

    @property
    def size(self):
        """获取列表大小
        
        Returns:
            列表大小
        """
        return len(self)

    def sizeEx(self, func=None):
        """获取符合条件的元素数量
        
        Args:
            func: 过滤函数
            
        Returns:
            符合条件的元素数量
        """
        if func is None:
            return self.size
        return self.quantify(func)

    def show(self, func=None):
        """显示列表
        
        Args:
            func: 显示函数
            
        Returns:
            self
        """
        if func is None:
            print(self)
            return self
        if callable(func):
            func(self)
        else:
            eval(func)(self)
        return self

    @vicTools.transfer
    def starmap(self, func, symbols=None):
        """星映射函数
        
        Args:
            func: 映射函数
            symbols: 参数符号
            
        Returns:
            映射后的结果
        """
        if self.is_empty:
            return []
        if not self.inner_iterable:
            raise TypeError("first item is not a iterbale !!!")
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if symbols is None:
            l = len(self._data[0])
            i = ord('x') if l <= 3 else ord('a')
            symbols = [chr(i + j) for j in range(l)]
        return self._run_ex(func, symbols)

    def _run2(self, func=print):
        """运行函数（针对整个列表）
        
        Args:
            func: 运行函数
            
        Returns:
            运行结果
        """
        if callable(func):
            return func(self)
        elif isinstance(func, str):
            return eval(func)(self)
        else:
            return []

    @vicTools.transfer
    def run(self, func=print):
        """运行函数
        
        Args:
            func: 运行函数
            
        Returns:
            运行结果
        """
        temp = self._run2(func)
        # return vicList(temp) if isinstance(temp, Iterable) else temp
        return temp

    def enumerate(self, n=0):
        """枚举列表
        
        Args:
            n: 起始索引
            
        Returns:
            枚举后的vicList对象
        """
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(enumerate(self._data, n))

    def take(self, n, action=False):
        """获取前n个元素
        
        Args:
            n: 元素数量
            action: 是否直接返回列表
            
        Returns:
            前n个元素的vicList对象或列表
        """
        """Return first n items of the iterable as a list"""
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if action:
            return self._data[:n]
        return vicList(self._data[:n])

    def prepend(self, value):
        """在列表前添加元素
        
        Args:
            value: 要添加的元素
            
        Returns:
            添加后的vicList对象
        """
        """Prepend a single value in front of an iterator"""
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        # prepend(1, [2, 3, 4]) -> 1 2 3 4
        return vicList([value] + self._data)

    def tail(self, n):
        """获取后n个元素
        
        Args:
            n: 元素数量
            
        Returns:
            后n个元素的vicList对象
        """
        """Return an iterator over the last n items"""
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        # tail(3, 'ABCDEFG') --> E F G
        return vicList(self._data[-n:])

    def any_equal(self, pred=bool):
        """检查是否有元素满足条件
        
        Args:
            pred: 条件函数
            
        Returns:
            是否有元素满足条件
        """
        """Returns True if all the elements are equal to each other"""
        pred = bool if pred is None else pred
        if callable(pred):
            p = pred is bool
        elif isinstance(pred, str):
            p = pred == 'bool'
            if not pred:
                raise ValueError("pred must not empty ,is a bool function ")
            pred = eval(pred)
        else:
            raise TypeError("pred must is a bool function,or a bool function that express by string")

        temp = self.map(pred) if p else self.map(pred).map(bool)

        for i in temp:
            if i:
                return True
        else:
            return False

    def all_equal(self, pred=bool):
        """检查是否所有元素都满足条件
        
        Args:
            pred: 条件函数
            
        Returns:
            是否所有元素都满足条件
        """
        """Returns True if all the elements are equal to each other"""
        pred = bool if pred is None else pred
        if callable(pred):
            p = pred is bool
        elif isinstance(pred, str):
            p = pred == 'bool'
            if not pred:
                raise ValueError("pred must not empty ,is a bool function ")
            pred = eval(pred)
        else:
            raise TypeError("pred must is a bool function,or a bool function that express by string")

        temp = self.map(pred) if p else self.map(pred).map(bool)

        g = itertools.groupby(temp)
        return next(g, True) and not next(g, False)

    def quantify(self, pred=bool, quan=sum):
        """计算满足条件的元素数量
        
        Args:
            pred: 条件函数
            quan: 聚合函数
            
        Returns:
            满足条件的元素数量
        """
        """Count how many times the predicate is true"""
        # 确保_data属性已经被初始化
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if isinstance(pred, str):
            pred = eval(pred)
        return quan(1 for item in self._data if pred(item))

    # 确保 issubclass(cls, list) 返回 True
    @classmethod
    def __subclasscheck__(cls, subclass):
        """检查子类
        
        Args:
            subclass: 子类
            
        Returns:
            是否为子类
        """
        return issubclass(subclass, list) or super().__subclasscheck__(subclass)

    # 确保 isinstance(obj, list) 返回 True
    def __class_getitem__(cls, item):
        """类索引操作
        
        Args:
            item: 索引
            
        Returns:
            列表类型
        """
        return list[item]