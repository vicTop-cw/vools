"""
VDate 日期类

继承自 datetime.datetime，提供丰富的日期处理方法。

功能特点：
- 支持多种日期格式解析和转换
- 提供日期加减、范围生成、周/月计算等操作
- 支持链式调用（通过 @rself 装饰器）
- 提供日期范围简化和序列生成功能

示例：
    >>> from vools import VDate
    >>> dt = VDate('2024-01-15')
    >>> dt.add_days(5)
    VDate('2024-01-20')
    >>> dt.getDateRange(start='2024-01-01', periods=7)
    ['2024-01-01', '2024-01-02', ...]
"""

__all__ = ['VDate']

import re
import calendar
from datetime import datetime, timedelta, date
from typing import List, Optional, Union
from collections import namedtuple

from ..decorators import rself
from .dates_format import DateProcessor
from ..serialize.context import get_protocol


def _reconstruct_vdate(year, month, day, hour, minute, second, microsecond, fmt):
    """pickle 重建函数：用独立的基本类型参数避免 datetime 反序列化时序问题"""
    dt = datetime(year, month, day, hour, minute, second, microsecond)
    return VDate(dt, fmt=fmt)


@rself
class VDate(datetime):
    """
    日期类，继承自 datetime.datetime

    支持多种输入格式：
    - 字符串格式: '2024-01-15', '20240115', '2024-01-15 12:30:00'
    - 时间戳: 1705286400 (int/float)
    - datetime 对象: datetime(2024, 1, 15)
    - 不传参数: 使用当前时间

    Args:
        dt: 日期输入，可以是字符串、时间戳、datetime对象或None
        fmt: 日期格式字符串，支持标准Python格式和自定义格式(yyyy, MM, dd等)
    """

    # BUG-200: .date() 应返回原生 datetime.date，跳过 @rself 的返回值包装
    #（包装成 VDate 会 TypeError 崩溃）。
    _rself_exclude = {'date'}

    def __init__(self, dt=None, fmt=None, *args, **kwargs):
        # BUG-386: 组件签名构造（见 __new__）——实例已由 datetime.__new__ 建好，
        # 这里只需补 VDate 自己的记录器/格式，不能再走「解析 dt」的分支。
        if args or kwargs or isinstance(fmt, int):
            _has_time = bool(self.hour or self.minute or self.second or self.microsecond)
            self.fmt = '%Y-%m-%d %H:%M:%S' if _has_time else '%Y-%m-%d'
            self._date_processor = DateProcessor(self.strftime('%Y-%m-%d'))
            return
        """初始化 VDate 实例。

        Args:
            dt: 日期输入，可以是字符串、时间戳、datetime对象或None（默认当前时间）
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
        """执行函数，支持链式处理。

        Args:
            f: 要执行的函数，默认 print
            pre_f: 执行前预处理函数，接收 VDate 对象
            sub_f: 执行后处理函数，接收 VDate 对象

        Returns:
            f 的返回值
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)

    @staticmethod
    def get_py_fmt(fmt='yyyyMMdd'):
        if not '%' in fmt:
            fmt = fmt.replace('yyyy', '%Y').replace('MM', '%m').replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
            fmt = fmt.replace('YYYY', '%Y').replace('SS', '%S').replace('ss', '%S').replace('yy', '%y')
        return fmt

    def get_week(self, num: int = 0, weekday: int = 1):
        """获取指定星期对应的日期。

        Args:
            num: 周偏移，正数=未来，负数=过去
            weekday: 星期几，1-7（1=周一，7=周日）

        Returns:
            格式化后的日期字符串

        Raises:
            ValueError: weekday 不在 1-7 范围内
        """
        if not weekday in range(1, 8):
            raise ValueError(
                f"weekday 必须在 1-7 之间（周一=1），收到 {weekday!r}")
        w0 = self - (int(self.strftime('%u')) - weekday)
        if num == 0:
            return w0.strftime(self.fmt)
        else:
            # BUG-242: 原 `w0 - num * 7` 使正数指向过去，与文档"正数=未来"相反。
            return (w0 + num * 7).strftime(self.fmt)

    def get_month(self, num: int = 0, last_day=False):
        """获取指定月份对应的日期。

        Args:
            num: 月份偏移，0表示本月，1=下月，-1=上月
            last_day: True 返回月份最后一天，False 返回月份第一天

        Returns:
            格式化后的日期字符串
        """
        y, m = self.year, self.month
        # BUG-181: last_day=True 时把目标月索引后移一个月，dt-1 才会落在目标月末；
        # 原 `num - 1` 使 dt-1 落在目标月的前一月月末（月份偏移整体错位）。
        num = num + 1 if last_day else num

        # BUG-181: 原实现 `num>0 → m-=1` / `num<0 → m+=1`，与文档"1=下月，-1=上月"恰好颠倒。
        while num > 0:
            m += 1
            if m == 13:
                m = 1
                y += 1
            num -= 1

        while num < 0:
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            num += 1

        m = m if m > 9 else f'0{m}'
        dt = VDate(f"{y}-{m}-01")
        return (dt - 1).strftime(self.fmt) if last_day else dt.strftime(self.fmt)

    def simplify(self, dates):
        """简化日期列表为连续日期范围。

        Args:
            dates: 日期列表，支持 '20240115' 或 '2024-01-15' 格式

        Returns:
            spyDate 列表，每个包含 start, end, cnt（天数差+1）
        """
        dates = self.simplify_date_ranges(dates)
        if len(dates) == 0:
            return []
        spyDate = namedtuple("spyDate", ["start", "end", "cnt"])
        return [spyDate(str(VDate(x, self.fmt)), str(VDate(y, self.fmt)), int(VDate(y) - VDate(x) + 1)) for x, y in dates]

    @staticmethod
    def simplify_date_ranges(dates):
        """将日期列表合并为连续日期范围。

        Args:
            dates: 日期可迭代对象（tuple, list, set），支持 '20240115' 或 '2024-01-15' 格式

        Returns:
            (start, end) 元组列表，表示连续日期范围

        Raises:
            TypeError: dates 不是 tuple, list, set 类型
        """
        if isinstance(dates, (tuple, list, set)):
            pass
        else:
            raise TypeError("dates must be (tuple,list,set) !!!")
        if len(dates) == 0:
            return []

        def _check(x):
            return re.match(r"^[1-2][0-9]{3}[0-1][0-9][0-3][0-9]$", x) or re.match(r"^[1-2][0-9]{3}-[0-1][0-9]-[0-3][0-9]$", x)

        parsed = []
        for s in {str(d) for d in dates}:
            if not _check(s):
                continue
            try:
                parsed.append(datetime.strptime(s, "%Y-%m-%d" if "-" in s else "%Y%m%d"))
            except ValueError:
                # BUG-189: _check 只校验格式不校验日期有效性（如 "2023-02-30"
                # 过正则但 2 月无 30 日），逐个 try strptime 把无效日期跳过，
                # 而非让单个坏日期毁掉整方法抛未捕获 ValueError。
                continue
        if not parsed:
            # BUG-189: 全部被过滤/无效时返回空，而非对空列表取 dates[0] 抛 IndexError。
            return []
        dates = sorted(parsed)
        fmt = "%Y-%m-%d" if "-" in str(dates[0]) else "%Y%m%d"

        simplified = []
        start = None
        end = None

        for i, current_date in enumerate(dates):
            if start is None or (i > 0 and (current_date - dates[i - 1]).days != 1):
                if start is not None and end is not None:
                    simplified.append((start.strftime(fmt), end.strftime(fmt)))
                start = current_date
            end = current_date

        simplified.append((start.strftime(fmt), end.strftime(fmt)))
        return simplified

    @staticmethod
    def _generate_date_range(start_date=None, end_date=None, periods=None, freq='D'):
        """生成日期范围列表（内部方法）。

        Args:
            start_date: 起始日期（datetime 对象）
            end_date: 结束日期（datetime 对象）
            periods: 生成数量
            freq: 频率，'D'=天，'W'=周，'M'=月

        Returns:
            datetime 对象列表

        Raises:
            ValueError: freq 非法；或 start/end/periods 三者同时给出（原先静默
                忽略 periods —— BUG-389）。

        Note:
            BUG-368: freq 非法时原实现 if/elif 全不命中 → 静默重复日期 / 死循环。
            BUG-388: 'M' 分支原用**本次已夹取的日期**再推进一个月，1-31 → 2-28 →
                3-28（漂移）。现按「起始日锚定 + 每月末夹取」生成：1-31 → 2-28 →
                3-31 → 4-30。
        """
        if not isinstance(freq, str) or freq.strip().upper() not in ('D', 'W', 'M'):
            raise ValueError(
                f"freq 只支持 'D'（天）/ 'W'（周）/ 'M'（月），收到 {freq!r}")
        freq = freq.strip().upper()

        _given = [x is not None for x in (start_date, end_date, periods)]
        if all(_given):
            raise ValueError(
                "start / end / periods 最多给其中两个：三者同时给出时原实现会"
                "静默忽略 periods（BUG-389），请去掉其中一个")

        def _plus_months(anchor_day, base, delta):
            """base 的年月平移 delta 个月，日取 min(anchor_day, 该月最后一天)。"""
            _total = base.year * 12 + (base.month - 1) + delta
            _year, _month0 = divmod(_total, 12)
            _month = _month0 + 1
            _last_day = calendar.monthrange(_year, _month)[1]
            return datetime(_year, _month, min(anchor_day, _last_day))

        dates = []

        if end_date is not None and periods is not None:
            if freq == 'M':
                _anchor_day = end_date.day
                return [_plus_months(_anchor_day, end_date, -_i)
                        for _i in range(periods - 1, -1, -1)]
            current = end_date
            for _ in range(periods):
                dates.append(current)
                if freq == 'D':
                    current -= timedelta(days=1)
                else:  # W
                    current -= timedelta(weeks=1)
            return dates[::-1]

        elif start_date is not None and end_date is not None:
            if freq == 'M':
                _anchor_day = start_date.day
                _i = 0
                current = start_date
                while current <= end_date:
                    dates.append(current)
                    _i += 1
                    current = _plus_months(_anchor_day, start_date, _i)
                return dates
            current = start_date
            while current <= end_date:
                dates.append(current)
                if freq == 'D':
                    current += timedelta(days=1)
                else:  # W
                    current += timedelta(weeks=1)
            return dates

        elif start_date is not None and periods is not None:
            if freq == 'M':
                _anchor_day = start_date.day
                return [_plus_months(_anchor_day, start_date, _i)
                        for _i in range(periods)]
            current = start_date
            for _ in range(periods):
                dates.append(current)
                if freq == 'D':
                    current += timedelta(days=1)
                else:  # W
                    current += timedelta(weeks=1)
            return dates

        return dates

    def getDateRange(self, start: Optional[str] = None, end: Optional[str] = None, freq: str = 'D', periods: Optional[int] = None) -> List[str]:
        """生成日期范围列表。

        Args:
            start: 起始日期字符串（'YYYY-MM-DD' 格式），不指定则使用当前日期或与 end 配合计算
            end: 结束日期字符串（'YYYY-MM-DD' 格式）
            freq: 频率，'D'=天，'W'=周，'M'=月
            periods: 生成数量，与 start 或 end 配合使用

        Returns:
            格式化后的日期字符串列表

        Raises:
            ValueError: end 和 periods 至少需要提供一个
        """
        if end is None and periods is None:
            raise ValueError("params  'end' or 'periods' must give One ")

        # BUG-389: start/end/periods 三者同给时，最终 else 分支只按 start+end
        # 生成、**静默忽略 periods**。显式报错，避免调用方以为 periods 生效。
        if start is not None and end is not None and periods is not None:
            raise ValueError(
                "start / end / periods 最多给其中两个：三者同时给出时原实现会静默"
                "忽略 periods（BUG-389），请去掉其中一个")

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
            dates = VDate._generate_date_range(end_date=end_dt, periods=periods, freq=freq)
        elif start is None:
            if periods is None:
                start_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
                dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
            else:
                dates = VDate._generate_date_range(end_date=end_dt, periods=periods, freq=freq)
        elif end is None:
            if periods is None:
                end_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
                dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
            else:
                dates = VDate._generate_date_range(start_date=start_dt, periods=periods, freq=freq)
        else:
            start_dt = VDate(start, '%Y-%m-%d')
            end_dt = VDate(end, '%Y-%m-%d')
            dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)

        return [d.strftime(self.fmt) for d in dates]

    def getDateRangeEx(self, start: Optional[str] = None, end: Optional[str] = None, freq: str = 'D', periods: Optional[int] = None) -> List[str]:
        """生成日期范围列表（扩展版，自动处理起止顺序）。

        与 getDateRange 不同，本方法会自动调整 start 和 end 的顺序，
        确保返回的日期列表是从早到晚的顺序。

        Args:
            start: 起始日期字符串（'YYYY-MM-DD' 格式）
            end: 结束日期字符串（'YYYY-MM-DD' 格式）
            freq: 频率，'D'=天，'W'=周，'M'=月
            periods: 生成数量

        Returns:
            格式化后的日期字符串列表

        Raises:
            ValueError: end 和 periods 至少需要提供一个
        """
        p1, p2, p3 = start is not None, end is not None, periods is not None
        # BUG-390: 三者同给时第一个分支（p1 and p2）会**静默忽略 periods**，
        # 与 getDateRange 的口径保持一致：显式报错（BUG-389）。
        if p1 and p2 and p3:
            raise ValueError(
                "start / end / periods 最多给其中两个：三者同时给出时会静默忽略 "
                "periods（BUG-390），请去掉其中一个")
        cls = self.__class__
        dt_f = lambda x: cls(x, '%Y-%m-%d').strftime('%Y-%m-%d')

        if p1 and p2:
            start_str, end_str = dt_f(start), dt_f(end)
            if start_str > end_str:
                start_str, end_str = end_str, start_str
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        elif p1 and p3:
            start_dt = datetime.strptime(dt_f(start), '%Y-%m-%d')
            dates = VDate._generate_date_range(start_date=start_dt, periods=periods, freq=freq)
        elif p2 and p3:
            end_dt = datetime.strptime(dt_f(end), '%Y-%m-%d')
            dates = VDate._generate_date_range(end_date=end_dt, periods=periods, freq=freq)
        elif p1:
            start_str = dt_f(start)
            end_str = self.strftime('%Y-%m-%d')
            if start_str > end_str:
                start_str, end_str = end_str, start_str
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        elif p2:
            end_str = dt_f(end)
            start_str = self.strftime('%Y-%m-%d')
            if start_str > end_str:
                start_str, end_str = end_str, start_str
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        elif p3:
            start_dt = datetime.strptime(self.strftime('%Y-%m-%d'), '%Y-%m-%d')
            dates = VDate._generate_date_range(start_date=start_dt, periods=periods, freq=freq)
        else:
            raise ValueError("params  'end' or 'periods' must give One ")

        return [d.strftime(self.fmt) for d in dates]

    def __new__(cls, dt=None, fmt=None, *args, **kwargs):
        # BUG-386: datetime 的 C 实现（now()/today()/fromtimestamp()/replace()/
        # astimezone()/combine()/fromisoformat()…）在内部用**组件签名**重新构造
        # 实例：cls(year, month, day, hour, minute, second, microsecond[, tzinfo[, fold]])。
        # 原签名只接受 (dt, fmt)，这些 API 全部
        #   TypeError: VDate.__new__() takes from 1 to 3 positional arguments but 9 were given
        # 且 @rself 的 __getattr__ 回退到 _date_processor 时还会形成 RecursionError。
        # 这里识别「有额外组件参数 / 第二参是 int（月份）」的形式，交给 datetime.__new__。
        if args or kwargs or isinstance(fmt, int):
            return super().__new__(cls, dt, fmt, *args, **kwargs)
        """创建新的 VDate 实例（override datetime.__new__）。

        Args:
            dt: 日期输入，支持字符串（多种格式）、时间戳、datetime 对象
            fmt: 日期格式字符串

        Returns:
            VDate 实例

        Raises:
            ValueError: 字符串格式日期但未指定 fmt
            TypeError: 不支持的日期类型
        """
        if dt is None:
            dt = datetime.now()
        if isinstance(dt, (int, float)):
            # BUG-180: 原 `super().fromtimestamp(dt)` 在 @rself 装饰下会被
            # datetime.fromtimestamp 内部的 cls(...) 9 参构造拉回 VDate.__new__，
            # 而 __new__(cls, dt=None, fmt=None) 只收 3 参 → TypeError 100% 崩。
            # 改用显式 datetime.fromtimestamp + super().__new__，与下方 datetime 分支同构。
            _ts = datetime.fromtimestamp(dt)
            result = super().__new__(cls, _ts.year, _ts.month, _ts.day,
                                     _ts.hour, _ts.minute, _ts.second,
                                     _ts.microsecond)
        elif isinstance(dt, str):
            if len(dt) == 8 and dt.isdigit():
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]))
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
                dt = dt.replace('-', '')
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]))
            elif re.match(r"^\d{4}-\d{2}-\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9](?:\.\d+)?$", dt):
                tm = dt.split(" ")[1].split(":")
                dt = dt.split(" ")[0].replace('-', '')
                sec_part = tm[2]
                if '.' in sec_part:
                    sec_str, frac = sec_part.split('.', 1)
                    sec = int(sec_str)
                    us = int(frac.ljust(6, '0')[:6])
                else:
                    sec = int(sec_part)
                    us = 0
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), sec, us)
            elif re.match(r"^\d{4}\d{2}\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9](?:\.\d+)?$", dt):
                tm = dt.split(" ")[1].split(":")
                dt = dt.split(" ")[0]
                sec_part = tm[2]
                if '.' in sec_part:
                    sec_str, frac = sec_part.split('.', 1)
                    sec = int(sec_str)
                    us = int(frac.ljust(6, '0')[:6])
                else:
                    sec = int(sec_part)
                    us = 0
                result = super().__new__(cls, int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), sec, us)
            else:
                if fmt is None:
                    raise ValueError("需要指定日期格式")
                # 与 utils.py 同步修：_parse_date 只回 (y,m,d)，带时间的 fmt 会被
                # 静默清零；直接用 strptime 结果保留时分秒。
                _parsed = datetime.strptime(dt, fmt)
                result = super().__new__(cls, _parsed.year, _parsed.month, _parsed.day,
                                         _parsed.hour, _parsed.minute, _parsed.second,
                                         _parsed.microsecond)
        elif isinstance(dt, (datetime, cls)):
            result = super().__new__(cls, dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)
        else:
            raise TypeError("不支持的日期类型")
        return result

    @staticmethod
    def _parse_date(date_str, fmt):
        """解析日期字符串（内部方法）。

        Args:
            date_str: 日期字符串
            fmt: 格式字符串

        Returns:
            (year, month, day) 元组
        """
        dt = datetime.strptime(date_str, fmt)
        return (dt.year, dt.month, dt.day)

    def add_days(self, days: int) -> 'VDate':
        """加 n 天，返回新的 VDate。

        Args:
            days: 天数（正数为未来，负数为过去）

        Returns:
            新的 VDate 实例
        """
        new_date = self + timedelta(days=days)
        return VDate(new_date.strftime('%Y-%m-%d'))

    def sub_days(self, days: int) -> 'VDate':
        """减 n 天，返回新的 VDate。

        Args:
            days: 天数

        Returns:
            新的 VDate 实例
        """
        return self.add_days(-days)

    def add_months(self, months: int) -> 'VDate':
        """加 n 月，返回新的 VDate（处理年末跨年）。

        Args:
            months: 月数（正数为未来，负数为过去）

        Returns:
            新的 VDate 实例
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
        return VDate(new_date.strftime('%Y-%m-%d'))

    def sub_months(self, months: int) -> 'VDate':
        """减 n 月，返回新的 VDate。

        Args:
            months: 月数

        Returns:
            新的 VDate 实例
        """
        return self.add_months(-months)

    def add_years(self, years: int) -> 'VDate':
        """加 n 年，返回新的 VDate。

        Args:
            years: 年数（正数为未来，负数为过去）

        Returns:
            新的 VDate 实例
        """
        year = self.year + years
        month = self.month
        day = self.day

        if month == 2 and day == 29 and not calendar.isleap(year):
            day = 28

        new_date = datetime(year, month, day, self.hour, self.minute, self.second)
        return VDate(new_date.strftime('%Y-%m-%d'))

    def sub_years(self, years: int) -> 'VDate':
        """减 n 年，返回新的 VDate。

        Args:
            years: 年数

        Returns:
            新的 VDate 实例
        """
        return self.add_years(-years)

    def get_date_range(self, end_date: Union[str, 'VDate'], freq: str = 'D', fmt: str = '%Y-%m-%d') -> List[str]:
        """获取从当前日期到结束日期的范围。

        Args:
            end_date: 结束日期（字符串或 VDate 对象）
            freq: 频率，'D'=天，'W'=周，'M'=月
            fmt: 输出格式

        Returns:
            格式化后的日期字符串列表
        """
        start = self.strftime('%Y-%m-%d')
        if isinstance(end_date, VDate):
            end = end_date.strftime('%Y-%m-%d')
        else:
            end = end_date

        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')

        dates = VDate._generate_date_range(start_date=start_dt, end_date=end_dt, freq=freq)
        return [d.strftime(fmt) for d in dates]

    def __add__(self, other: Union[timedelta, int, float]) -> 'VDate':
        """加法运算，支持 timedelta 和整数天数。

        Args:
            other: timedelta 对象或天数（整数/浮点数）

        Returns:
            新的 VDate 实例

        Raises:
            TypeError: 不支持的类型
        """
        if isinstance(other, timedelta):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second, self.microsecond) + other
            # BUG-241: 沿用源实例格式，避免算术结果 str 与构造结果不一致
            #（datetime 输入会被推断成 '%Y-%m-%d %H:%M:%S'）
            return VDate(new_datetime, fmt=self.fmt)
        elif isinstance(other, (int, float)):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second, self.microsecond) + timedelta(days=other)
            return VDate(new_datetime, fmt=self.fmt)
        else:
            raise TypeError("只能对整数或 timedelta 执行加法操作")

    def __sub__(self, other: Union[timedelta, int, float, datetime, 'VDate']) -> Union['VDate', float]:
        """减法运算，支持 timedelta、整数天数和日期。

        Args:
            other: timedelta 对象、天数（整数/浮点数）或日期（datetime/VDate）

        Returns:
            timedelta 减法返回新的 VDate 实例，
            整数/浮点数减法返回天数差（float），
            日期相减返回天数差（float）

        Raises:
            TypeError: 不支持的类型
        """
        if isinstance(other, (int, float)):
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second, self.microsecond) - timedelta(days=other)
            return VDate(new_datetime, fmt=self.fmt)
        elif isinstance(other, timedelta):
            # BUG-241: docstring/类型注解承诺支持 timedelta（"timedelta 减法返回
            # 新的 VDate 实例"），原实现缺失该分支 → 落到 else 抛 TypeError。
            new_datetime = datetime(self.year, self.month, self.day, self.hour, self.minute, self.second, self.microsecond) - other
            return VDate(new_datetime, fmt=self.fmt)
        elif isinstance(other, (datetime, VDate)):
            diff = self.timestamp() - other.timestamp()
            return diff / 86400
        else:
            raise TypeError("只能对整数和日期执行减法操作")

    def __eq__(self, other: object) -> bool:
        """相等比较。

        Args:
            other: 比较对象，支持 VDate、datetime、date 或字符串

        Returns:
            日期相等返回 True，否则返回 False
        """
        # 注意：不用 self.date()/other.date() 参与比较。@rself 装饰器会把
        # datetime.date 返回值用 VDate 构造包装，而 VDate.__new__ 不识别 date
        # 类型会 raise TypeError（BUG-199）。改用 (year, month, day) 元组比较。
        if isinstance(other, VDate):
            return (self.year, self.month, self.day) == (other.year, other.month, other.day)
        elif isinstance(other, (datetime, date)):
            return (self.year, self.month, self.day) == (other.year, other.month, other.day)
        elif isinstance(other, str):
            try:
                other_date = datetime.strptime(other, '%Y-%m-%d').date()
                return (self.year, self.month, self.day) == (other_date.year, other_date.month, other_date.day)
            except Exception:
                return False
        return False

    def __hash__(self) -> int:
        """哈希值（BUG-387）。

        `date`/`datetime` 本可哈希，但本类定义了 `__eq__`（按 (year, month, day)
        比较，忽略时间）后 Python 会把 `__hash__` 置为 None → VDate 变成不可哈希，
        无法作为 dict 键/set 元素。这里按与 `__eq__` 一致的粒度实现哈希。
        """
        return hash((self.year, self.month, self.day))

    def __lt__(self, other: object) -> bool:
        """小于比较。

        Args:
            other: 比较对象，支持 VDate、datetime、date 或字符串

        Returns:
            self < other 返回 True，否则返回 False
        """
        # 与 __eq__ 同理：不用 self.date()/other.date()（@rself 会把它包装成
        # VDate 并触发 TypeError），改用 (year, month, day) 元组比较（BUG-199）。
        if isinstance(other, VDate):
            return (self.year, self.month, self.day) < (other.year, other.month, other.day)
        elif isinstance(other, (datetime, date)):
            return (self.year, self.month, self.day) < (other.year, other.month, other.day)
        elif isinstance(other, str):
            try:
                other_date = datetime.strptime(other, '%Y-%m-%d').date()
                return (self.year, self.month, self.day) < (other_date.year, other_date.month, other_date.day)
            except Exception:
                return False
        return False

    def __le__(self, other: object) -> bool:
        """小于等于比较。

        Args:
            other: 比较对象，支持 VDate、datetime、date 或字符串

        Returns:
            self <= other 返回 True，否则返回 False
        """
        return self < other or self == other

    def __gt__(self, other: object) -> bool:
        """大于比较。

        Args:
            other: 比较对象，支持 VDate、datetime、date 或字符串

        Returns:
            self > other 返回 True，否则返回 False
        """
        return not self <= other

    def __ge__(self, other: object) -> bool:
        """大于等于比较。

        Args:
            other: 比较对象，支持 VDate、datetime、date 或字符串

        Returns:
            self >= other 返回 True，否则返回 False
        """
        return not self < other

    def __str__(self) -> str:
        """返回格式化后的日期字符串。

        Returns:
            按照 fmt 格式化的日期字符串
        """
        if self.fmt:
            return self.strftime(self.fmt)
        else:
            return super().__str__()

    def __repr__(self) -> str:
        """返回 VDate 的官方表示。

        Returns:
            VDate 字符串表示，如 VDate('2024-01-15')
        """
        return f"VDate('{self}')"

    def __getattr__(self, name: str) -> object:
        """动态属性访问，支持代理到内部对象。

        首先在实例字典中查找，然后代理到父类（datetime），
        最后代理到 _date_processor。

        Args:
            name: 属性名称

        Returns:
            属性值

        Raises:
            AttributeError: 属性不存在
        """
        if name in self.__dict__:
            return self.__dict__[name]
        # BUG-386: datetime 的 C 方法（replace/astimezone/…）构造的实例 __dict__
        # 为空（C 层不调用 __init__），这里为 fmt 提供按时间分量推导的惰性默认。
        if name == 'fmt':
            _fmt = '%Y-%m-%d %H:%M:%S' if (self.hour or self.minute or
                                            self.second or self.microsecond) else '%Y-%m-%d'
            object.__setattr__(self, 'fmt', _fmt)
            return _fmt
        # BUG-386: 内部属性（含 _date_processor 自身）缺失时必须直接 AttributeError，
        # 否则回退分支 `getattr(self._date_processor, name)` 会再次触发 __getattr__，
        # 形成无限递归（实测 replace()/astimezone() → RecursionError）。
        if name.startswith('_'):
            raise AttributeError(name)
        try:
            return getattr(super(), name)
        except AttributeError:
            _proc = self.__dict__.get('_date_processor')
            if _proc is None:
                try:
                    _proc = DateProcessor(self.strftime('%Y-%m-%d'))
                    object.__setattr__(self, '_date_processor', _proc)
                except Exception:
                    raise AttributeError(name) from None
            return getattr(_proc, name)

    def __dir__(self) -> List[str]:
        """返回所有可用属性列表。

        合并了实例属性、datetime 属性和 _date_processor 属性。

        Returns:
            属性名称列表
        """
        self_attrs = set(self.__dict__.keys())
        date_attrs = set(dir(datetime))
        processor_attrs = set(dir(self._date_processor))
        return list(sorted(self_attrs | date_attrs | processor_attrs))

    def toString(self, fmt: Optional[str] = None) -> str:
        """转换为字符串。

        Args:
            fmt: 可选的格式字符串，不指定则使用默认格式

        Returns:
            格式化后的日期字符串
        """
        return str(self) if fmt is None else self.strftime(self.get_py_fmt(fmt))

    # ─── 序列化支持 ───

    def __reduce_ex__(self, protocol: int) -> tuple:
        """支持 pickle 序列化。

        Args:
            protocol: pickle 协议版本

        Returns:
            元组，包含重建函数和参数
        """
        return (_reconstruct_vdate, (
            self.year, self.month, self.day,
            self.hour, self.minute, self.second,
            self.microsecond, self.fmt
        ))

    def __getstate__(self) -> dict:
        """获取序列化状态。

        Returns:
            包含 fmt 的字典
        """
        d = self.__dict__
        return {'fmt': d.get('fmt', '%Y-%m-%d')}

    def __setstate__(self, state: dict) -> None:
        """恢复序列化状态。

        Args:
            state: 包含 fmt 的字典
        """
        self.fmt = state.get('fmt', '%Y-%m-%d')
        from .dates_format import DateProcessor
        self._date_processor = DateProcessor(self.strftime('%Y-%m-%d'))
