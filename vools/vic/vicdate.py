"""
vicDate 日期类

继承自 datetime.datetime，提供丰富的日期处理方法。

功能特点：
- 支持多种日期格式解析和转换
- 提供日期加减、范围生成、周/月计算等操作
- 支持链式调用（通过 @rself 装饰器）
- 提供日期范围简化和序列生成功能

示例：
    >>> from vools import vicDate
    >>> dt = vicDate('2024-01-15')
    >>> dt.add_days(5)
    vicDate('2024-01-20')
    >>> dt.getDateRange(start='2024-01-01', periods=7)
    ['2024-01-01', '2024-01-02', ...]
"""

__all__ = ['vicDate']

import re
import calendar
from datetime import datetime, timedelta, date
from collections import namedtuple

from ..decorators import rself
from ..datetime.dates_format import DateProcessor


@rself
class vicDate(datetime):
    """
    日期类，继承自 datetime.datetime，提供更多日期处理方法

    支持多种输入格式：
    - 字符串格式: '2024-01-15', '20240115', '2024-01-15 12:30:00'
    - 时间戳: 1705286400 (int/float)
    - datetime 对象: datetime(2024, 1, 15)
    - 不传参数: 使用当前时间

    Args:
        dt: 日期输入，可以是字符串、时间戳、datetime对象或None
        fmt: 日期格式字符串，支持标准Python格式和自定义格式(yyyy, MM, dd等)

    Example:
        >>> vicDate()  # 当前时间
        >>> vicDate('2024-01-15')
        >>> vicDate('20240115')
        >>> vicDate(1705286400)
        >>> vicDate(datetime(2024, 1, 15))
    """

    def __init__(self, dt=None, fmt=None):
        """
        初始化日期对象

        Args:
            dt: 日期输入，可以是字符串、时间戳、datetime对象或None
            fmt: 日期格式字符串，支持标准Python格式和自定义格式(yyyy, MM, dd等)
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

    def do(self, f=print, pre_f=None, sub_f=None):
        """
        执行函数并返回自身，支持链式调用

        Args:
            f: 主函数，默认 print
            pre_f: 前置函数，在主函数前执行
            sub_f: 后置函数，在主函数后执行

        Returns:
            self，支持链式调用

        Example:
            >>> vicDate('2024-01-15').do(print)
            2024-01-15
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)

    @staticmethod
    def get_py_fmt(fmt='yyyyMMdd'):
        """
        将自定义日期格式转换为 Python 标准格式

        支持的自定义格式：
        - yyyy: 四位数年份 (2024)
        - MM: 两位数月份 (01-12)
        - dd: 两位数日期 (01-31)
        - HH: 两位数小时 (00-23)
        - mm: 两位数分钟 (00-59)
        - ss/SS: 两位数秒 (00-59)
        - yy: 两位数年份 (24)

        Args:
            fmt: 自定义日期格式字符串

        Returns:
            Python 标准日期格式字符串

        Example:
            >>> vicDate.get_py_fmt('yyyy-MM-dd')
            '%Y-%m-%d'
            >>> vicDate.get_py_fmt('dd/MM/yyyy')
            '%d/%m/%Y'
        """
        if not '%' in fmt:
            fmt = fmt.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
            fmt = fmt.replace('YYYY', '%Y').replace('SS', '%S').replace('ss', '%S').replace('yy', '%y')
        return fmt

    def get_week(self, num: int = 0, weekday: int = 1):
        """
        获取指定周的日期

        Args:
            num: 周偏移量，0表示当前周，正数表示向前推，负数表示向后推
            weekday: 周几，1=周一，2=周二，...，7=周日

        Returns:
            指定周的指定日期字符串

        Raises:
            ValueError: 如果 weekday 不在 1-7 范围内

        Example:
            >>> dt = vicDate('2024-01-15')  # 周一
            >>> dt.get_week()  # 当前周周一
            '2024-01-15'
            >>> dt.get_week(num=1)  # 上周周一
            '2024-01-08'
            >>> dt.get_week(weekday=5)  # 当前周周五
            '2024-01-19'
        """
        if not weekday in range(1, 8):
            raise ValueError("param weekday must in 1 to 7 , 1 is MonDay !!!")
        w0 = self - (int(self.strftime('%u')) - weekday)
        if num == 0:
            return w0.strftime(self.fmt)
        else:
            return (w0 - num * 7).strftime(self.fmt)

    def get_month(self, num: int = 0, last_day=False):
        """
        获取指定月份的日期

        Args:
            num: 月份偏移量，0表示当前月，正数表示向前推，负数表示向后推
            last_day: 是否返回该月最后一天

        Returns:
            指定月份的日期字符串

        Example:
            >>> dt = vicDate('2024-03-15')
            >>> dt.get_month()  # 当前月第一天
            '2024-03-01'
            >>> dt.get_month(num=1)  # 上个月第一天
            '2024-02-01'
            >>> dt.get_month(last_day=True)  # 当前月最后一天
            '2024-03-31'
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
        """
        简化日期列表为连续日期范围

        Args:
            dates: 日期列表、元组或集合

        Returns:
            简化后的日期范围列表，每个元素是包含 start, end, cnt 的 namedtuple

        Example:
            >>> dt = vicDate('2024-01-01')
            >>> dt.simplify(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-05'])
            [spyDate(start='2024-01-01', end='2024-01-03', cnt=3), ...]
        """
        dates = self.simplify_date_ranges(dates)
        if len(dates) == 0:
            return []
        spyDate = namedtuple("spyDate", ["start", "end", "cnt"])
        return [spyDate(str(vicDate(x, self.fmt)), str(vicDate(y, self.fmt)), int(vicDate(y) - vicDate(x) + 1)) for x, y in dates]

    @staticmethod
    def simplify_date_ranges(dates):
        """
        将日期列表简化为连续的日期范围

        Args:
            dates: 日期列表、元组或集合

        Returns:
            简化后的日期范围列表，每个元素是 (start, end) 元组

        Raises:
            TypeError: 如果输入不是列表、元组或集合

        Example:
            >>> vicDate.simplify_date_ranges(['2024-01-01', '2024-01-02', '2024-01-05'])
            [('2024-01-01', '2024-01-02'), ('2024-01-05', '2024-01-05')]
        """
        if isinstance(dates, (tuple, list, set)):
            pass
        else:
            raise TypeError("dates must be (tuple,list,set) !!!")
        if len(dates) == 0:
            return []

        def _check(x):
            return re.match(r"^[1-2][0-9]{3}[0-1][0-9][0-3][0-9]$", x) or re.match(r"^[1-2][0-9]{3}-[0-1][0-9]-[0-3][0-9]$", x)

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

    @staticmethod
    def _generate_date_range(start_date=None, end_date=None, periods=None, freq='D'):
        """
        生成日期序列（内部方法，使用标准库实现）

        Args:
            start_date: 开始日期（datetime对象）
            end_date: 结束日期（datetime对象）
            periods: 期数
            freq: 频率，可选 'D'(天), 'W'(周), 'M'(月)

        Returns:
            日期列表
        """
        dates = []

        if end_date is not None and periods is not None:
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

        elif start_date is not None and end_date is not None:
            current = start_date
            while current <= end_date:
                dates.append(current)
                if freq == 'D':
                    current += timedelta(days=1)
                elif freq == 'W':
                    current += timedelta(weeks=1)
                elif freq == 'M':
                    year = current.year
                    month = current.month + 1
                    if month > 12:
                        month = 1
                        year += 1
                    last_day = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day
                    day = min(current.day, last_day)
                    current = datetime(year, month, day)
            return dates

        elif start_date is not None and periods is not None:
            current = start_date
            for _ in range(periods):
                dates.append(current)
                if freq == 'D':
                    current += timedelta(days=1)
                elif freq == 'W':
                    current += timedelta(weeks=1)
                elif freq == 'M':
                    year = current.year
                    month = current.month + 1
                    if month > 12:
                        month = 1
                        year += 1
                    last_day = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day
                    day = min(current.day, last_day)
                    current = datetime(year, month, day)
            return dates

        return dates

    def getDateRange(self, start=None, end=None, freq='D', periods=None) -> list:
        """
        生成日期范围列表

        Args:
            start: 开始日期（字符串或datetime对象）
            end: 结束日期（字符串或datetime对象）
            freq: 频率，可选 'D'(天), 'W'(周), 'M'(月)，默认 'D'
            periods: 期数，与 start 或 end 配合使用

        Returns:
            日期字符串列表

        Raises:
            ValueError: 如果 end 和 periods 都未提供

        Example:
            >>> dt = vicDate('2024-01-01')
            >>> dt.getDateRange(end='2024-01-05')  # 日期范围
            ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']
            >>> dt.getDateRange(periods=5)  # 从当前日期向后5天
            ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']
            >>> dt.getDateRange(start='2024-01-01', periods=3, freq='M')  # 3个月
            ['2024-01-01', '2024-02-01', '2024-03-01']
        """
        if end is None and periods is None:
            raise ValueError("params  'end' or 'periods' must give One ")

        if start is not None:
            start_dt = datetime.strptime(start, '%Y-%m-%d') if isinstance(start, str) else start
        else:
            start_dt = None

        if end is not None:
            end_dt = datetime.strptime(end, '%Y-%m-%d') if isinstance(end, str) else end
        else:
            end_dt = None

        if start is None and end is None:
            end_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
            dates = vicDate._generate_date_range(end_date=end_dt, periods=periods, freq=freq)
        elif start is None:
            if periods is None:
                start_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
                dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
            else:
                dates = vicDate._generate_date_range(end_date=end_dt, periods=periods, freq=freq)
        elif end is None:
            if periods is None:
                end_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
                dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
            else:
                dates = vicDate._generate_date_range(start_date=start_dt, periods=periods, freq=freq)
        else:
            start_dt = vicDate(start, '%Y-%m-%d')
            end_dt = vicDate(end, '%Y-%m-%d')
            dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)

        return [d.strftime(self.fmt) for d in dates]

    def getDateRangeEx(self, start=None, end=None, freq='D', periods=None) -> list:
        """
        扩展版日期范围生成，支持更灵活的参数组合

        与 getDateRange 的区别：
        - 支持 start > end 的情况，会自动交换
        - 支持只提供 start 或 end 参数（使用当前日期作为另一边界）

        Args:
            start: 开始日期（字符串或datetime对象）
            end: 结束日期（字符串或datetime对象）
            freq: 频率，可选 'D'(天), 'W'(周), 'M'(月)，默认 'D'
            periods: 期数

        Returns:
            日期字符串列表

        Raises:
            ValueError: 如果没有提供任何参数

        Example:
            >>> dt = vicDate('2024-01-15')
            >>> dt.getDateRangeEx(start='2024-01-20', end='2024-01-01')  # start > end，自动交换
            ['2024-01-01', '2024-01-02', ..., '2024-01-20']
            >>> dt.getDateRangeEx(start='2024-01-01')  # 从开始日期到当前日期
            ['2024-01-01', ..., '2024-01-15']
        """
        p1, p2, p3 = start is not None, end is not None, periods is not None
        cls = self.__class__
        dt_f = lambda x: cls(x, '%Y-%m-%d').strftime('%Y-%m-%d')

        if p1 and p2:
            start_str, end_str = dt_f(start), dt_f(end)
            if start_str > end_str:
                start_str, end_str = end_str, start_str
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        elif p1 and p3:
            start_dt = datetime.strptime(dt_f(start), '%Y-%m-%d')
            dates = vicDate._generate_date_range(start_date=start_dt, periods=periods, freq=freq)
        elif p2 and p3:
            end_dt = datetime.strptime(dt_f(end), '%Y-%m-%d')
            dates = vicDate._generate_date_range(end_date=end_dt, periods=periods, freq=freq)
        elif p1:
            start_str = dt_f(start)
            end_str = self.strftime('%Y-%m-%d')
            if start_str > end_str:
                start_str, end_str = end_str, start_str
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        elif p2:
            end_str = dt_f(end)
            start_str = self.strftime('%Y-%m-%d')
            if start_str > end_str:
                start_str, end_str = end_str, start_str
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        elif p3:
            start_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
            dates = vicDate._generate_date_range(start_date=start_dt, periods=periods, freq=freq)
        else:
            raise ValueError("params  'end' or 'periods' must give One ")

        return [d.strftime(self.fmt) for d in dates]

    def __new__(cls, dt=None, fmt=None):
        """
        创建 vicDate 对象（静态构造方法）

        支持多种输入格式：
        - 时间戳: int 或 float 类型的 Unix 时间戳
        - 字符串: '20240115', '2024-01-15', '2024-01-15 12:30:00'
        - datetime 对象: datetime 或 vicDate 实例
        - None: 使用当前时间

        Args:
            dt: 日期输入，可以是字符串、时间戳、datetime对象或None
            fmt: 日期格式字符串（当字符串格式无法自动识别时需要提供）

        Returns:
            vicDate 实例

        Raises:
            ValueError: 如果字符串格式无法识别且未提供 fmt
            TypeError: 如果输入类型不支持

        Example:
            >>> vicDate('2024-01-15')
            vicDate('2024-01-15')
            >>> vicDate(1705286400)
            vicDate('2024-01-15')
            >>> vicDate(datetime(2024, 1, 15))
            vicDate('2024-01-15')
        """
        if dt is None:
            dt = datetime.now()
        if isinstance(dt, (int, float)):
            result = super().fromtimestamp(dt)
        elif isinstance(dt, str):
            if len(dt) == 8 and dt.isdigit():
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]))
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
                dt = dt.replace('-', '')
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]))
            elif re.match(r"^\d{4}-\d{2}-\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9]$", dt):
                tm = dt.split(" ")[1].split(":")
                dt = dt.split(" ")[0].replace('-', '')
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), int(tm[2]))
            elif re.match(r"^\d{4}\d{2}\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9]$", dt):
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
        """
        解析日期字符串（内部方法）

        Args:
            date_str: 日期字符串
            fmt: 日期格式

        Returns:
            (year, month, day) 元组
        """
        dt = datetime.strptime(date_str, fmt)
        return (dt.year, dt.month, dt.day)

    def add_days(self, days):
        """
        添加天数

        Args:
            days: 要添加的天数，可以是负数

        Returns:
            新的 vicDate 对象

        Example:
            >>> dt = vicDate('2024-01-15')
            >>> dt.add_days(5)
            vicDate('2024-01-20')
            >>> dt.add_days(-3)
            vicDate('2024-01-12')
        """
        new_date = self + timedelta(days=days)
        return vicDate(new_date.strftime('%Y-%m-%d'))

    def sub_days(self, days):
        """
        减去天数（add_days 的便捷方法）

        Args:
            days: 要减去的天数

        Returns:
            新的 vicDate 对象

        Example:
            >>> dt = vicDate('2024-01-15')
            >>> dt.sub_days(5)
            vicDate('2024-01-10')
        """
        return self.add_days(-days)

    def add_months(self, months):
        """
        添加月份

        Args:
            months: 要添加的月份数，可以是负数

        Returns:
            新的 vicDate 对象

        Note:
            如果目标月份的天数少于当前日期，会自动调整到该月最后一天

        Example:
            >>> dt = vicDate('2024-01-31')
            >>> dt.add_months(1)  # 2月没有31日，自动调整到28日
            vicDate('2024-02-28')
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
        """
        减去月份（add_months 的便捷方法）

        Args:
            months: 要减去的月份数

        Returns:
            新的 vicDate 对象

        Example:
            >>> dt = vicDate('2024-03-15')
            >>> dt.sub_months(2)
            vicDate('2024-01-15')
        """
        return self.add_months(-months)

    def add_years(self, years):
        """
        添加年份

        Args:
            years: 要添加的年份数，可以是负数

        Returns:
            新的 vicDate 对象

        Note:
            如果当前日期是2月29日且目标年份不是闰年，会自动调整到2月28日

        Example:
            >>> dt = vicDate('2024-02-29')  # 闰年
            >>> dt.add_years(1)  # 2025不是闰年，调整到28日
            vicDate('2025-02-28')
        """
        year = self.year + years
        month = self.month
        day = self.day

        if month == 2 and day == 29 and not calendar.isleap(year):
            day = 28

        new_date = datetime(year, month, day, self.hour, self.minute, self.second)
        return vicDate(new_date.strftime('%Y-%m-%d'))

    def sub_years(self, years):
        """
        减去年份（add_years 的便捷方法）

        Args:
            years: 要减去的年份数

        Returns:
            新的 vicDate 对象

        Example:
            >>> dt = vicDate('2024-01-15')
            >>> dt.sub_years(1)
            vicDate('2023-01-15')
        """
        return self.add_years(-years)

    def get_date_range(self, end_date, freq='D', fmt='%Y-%m-%d'):
        """
        获取从当前日期到指定日期的范围

        Args:
            end_date: 结束日期（字符串或 vicDate 对象）
            freq: 频率，可选 'D'(天), 'W'(周), 'M'(月)，默认 'D'
            fmt: 输出格式，默认 '%Y-%m-%d'

        Returns:
            日期字符串列表

        Example:
            >>> dt = vicDate('2024-01-01')
            >>> dt.get_date_range('2024-01-03')
            ['2024-01-01', '2024-01-02', '2024-01-03']
        """
        start = self.strftime('%Y-%m-%d')
        if isinstance(end_date, vicDate):
            end = end_date.strftime('%Y-%m-%d')
        else:
            end = end_date

        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')

        dates = vicDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        return [d.strftime(fmt) for d in dates]

    def __add__(self, other):
        if isinstance(other, timedelta):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) + other
            return vicDate(new_datetime)
        elif isinstance(other, (int, float)):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) + timedelta(days=other)
            return vicDate(new_datetime)
        else:
            raise TypeError("只能对整数或 timedelta 执行加法操作")

    def __sub__(self, other):
        if isinstance(other, (int, float)):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second) - timedelta(days=other)
            return vicDate(new_datetime)
        elif isinstance(other, (datetime, vicDate)):
            diff = self.timestamp() - other.timestamp()
            return diff / 86400
        else:
            raise TypeError("只能对整数和日期执行减法操作")

    def __eq__(self, other):
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
        return self < other or self == other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other

    def __str__(self):
        if self.fmt:
            return self.strftime(self.fmt)
        else:
            return super().__str__()

    def __repr__(self):
        return f"vicDate('{self}')"

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        try:
            return getattr(super(), name)
        except:
            return getattr(self._date_processor, name)

    def __dir__(self):
        self_attrs = set(self.__dict__.keys())
        date_attrs = set(dir(datetime))
        processor_attrs = set(dir(self._date_processor))
        return list(sorted(self_attrs | date_attrs | processor_attrs))

    def toString(self, fmt=None):
        return str(self) if fmt is None else self.strftime(self.get_py_fmt(fmt))
