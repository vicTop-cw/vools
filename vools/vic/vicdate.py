"""
vicDate 日期类
继承自 datetime，提供更多日期处理方法
"""

import re
import calendar
from datetime import datetime, timedelta, date
import pandas as pd
from collections import namedtuple

from ..vic.victools import vicTools
from ..datetime.dates_format import DateProcessor


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
        self._date_processor = DateProcessor(self.strftime('%Y-%m-%d'))

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

        simplified = []
        start = None

        for i, current_date in enumerate(dates):
            if start is None or (i > 0 and (current_date - dates[i - 1]).days != 1):
                if start is not None:
                    simplified.append((start.strftime(fmt), end.strftime(fmt)))
                start = current_date
            end = current_date

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
        if isinstance(dt, (int, float)):
            result = super().fromtimestamp(dt)
        elif isinstance(dt, str):
            if len(dt) == 8 and dt.isdigit():
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
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), int(tm[2]))
            else:
                if fmt is None:
                    raise ValueError("需要指定日期格式")
                result = super().__new__(cls, *cls._parse_date(dt, fmt))
        elif isinstance(dt, (datetime, cls)):
            result = super().__new__(cls, dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)
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
        dt = datetime.strptime(date_str, fmt)
        return (dt.year, dt.month, dt.day)

    def add_days(self, days):
        """添加天数

        Args:
            days: 天数

        Returns:
            新的vicDate对象
        """
        new_date = self + timedelta(days=days)
        return vicDate(new_date.strftime('%Y-%m-%d'))

    def sub_days(self, days):
        """减去天数

        Args:
            days: 天数

        Returns:
            新的vicDate对象
        """
        return self.add_days(-days)

    def add_months(self, months):
        """添加月数

        Args:
            months: 月数

        Returns:
            新的vicDate对象
        """
        year = self.year
        month = self.month + months

        if month > 12:
            year += (month - 1) // 12
            month = (month - 1) % 12 + 1
        elif month < 1:
            year += (month - 1) // 12
            month = (month - 1) % 12 + 1

        last_day = calendar.monthrange(year, month)[1]
        day = min(self.day, last_day)

        new_date = datetime(year, month, day, self.hour, self.minute, self.second)
        return vicDate(new_date.strftime('%Y-%m-%d'))

    def sub_months(self, months):
        """减去月数

        Args:
            months: 月数

        Returns:
            新的vicDate对象
        """
        return self.add_months(-months)

    def add_years(self, years):
        """添加年数

        Args:
            years: 年数

        Returns:
            新的vicDate对象
        """
        year = self.year + years
        month = self.month
        day = self.day

        if month == 2 and day == 29 and not calendar.isleap(year):
            day = 28

        new_date = datetime(year, month, day, self.hour, self.minute, self.second)
        return vicDate(new_date.strftime('%Y-%m-%d'))

    def sub_years(self, years):
        """减去年数

        Args:
            years: 年数

        Returns:
            新的vicDate对象
        """
        return self.add_years(-years)

    def get_date_range(self, end_date, freq='D', fmt='%Y-%m-%d'):
        """获取日期范围

        Args:
            end_date: 结束日期
            freq: 频率
            fmt: 日期格式

        Returns:
            日期字符串列表
        """
        start = self.strftime('%Y-%m-%d')
        if isinstance(end_date, vicDate):
            end = end_date.strftime('%Y-%m-%d')
        else:
            end = end_date

        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')

        dates = pd.date_range(start=start_dt, end=end_dt, freq=freq)
        return [d.strftime(fmt) for d in dates]

    def __add__(self, other):
        """加法操作

        Args:
            other: 天数

        Returns:
            新的vicDate对象
        """
        if isinstance(other, (int, float)):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) + timedelta(days=other)
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
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) - timedelta(days=other)
            return vicDate(new_datetime)
        elif isinstance(other, (datetime, vicDate)):
            diff = self.timestamp() - other.timestamp()
            return diff / 86400
        else:
            raise TypeError("只能对整数和日期执行减法操作")

    def __eq__(self, other):
        """等于比较"""
        if isinstance(other, vicDate):
            return self.date() == other.date()
        elif isinstance(other, (datetime, date)):
            return self.date() == other.date()
        elif isinstance(other, str):
            try:
                other_date = datetime.strptime(other, '%Y-%m-%d').date()
                return self.date() == other_date
            except:
                return False
        return False

    def __lt__(self, other):
        """小于比较"""
        if isinstance(other, vicDate):
            return self.date() < other.date()
        elif isinstance(other, (datetime, date)):
            return self.date() < other.date()
        elif isinstance(other, str):
            try:
                other_date = datetime.strptime(other, '%Y-%m-%d').date()
                return self.date() < other_date
            except:
                return False
        return False

    def __le__(self, other):
        """小于等于比较"""
        return self < other or self == other

    def __gt__(self, other):
        """大于比较"""
        return not self <= other

    def __ge__(self, other):
        """大于等于比较"""
        return not self < other

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

    def __getattr__(self, name):
        """动态获取属性"""
        if name in self.__dict__:
            return self.__dict__[name]
        try:
            return getattr(super(), name)
        except:
            return getattr(self._date_processor, name)

    def __dir__(self):
        """动态获取属性列表"""
        self_attrs = set(self.__dict__.keys())
        date_attrs = set(dir(datetime))
        processor_attrs = set(dir(self._date_processor))
        return list(sorted(self_attrs | date_attrs | processor_attrs))

    def toString(self, fmt=None):
        """转换为字符串

        Args:
            fmt: 日期格式

        Returns:
            日期字符串
        """
        return str(self) if fmt is None else self.strftime(vicTools.get_py_fmt(fmt))