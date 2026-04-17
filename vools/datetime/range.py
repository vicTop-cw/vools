from datetime import datetime, date, timedelta
import calendar
from typing import List, Optional, Tuple, Union
import warnings

__all__ = ['get_date_range', 'simplify_date_ranges', 'vicDate']

def parse_date_string(date_str: str, parse_fmt: str = '%Y-%m-%d') -> datetime:
    """
    将日期字符串解析为datetime对象
    
    Args:
        date_str: 日期字符串
        parse_fmt: 解析格式
        
    Returns:
        datetime对象
    """
    if not date_str:
        return None
    
    try:
        return datetime.strptime(date_str, parse_fmt)
    except ValueError as e:
        # 尝试其他常见格式
        common_formats = ['%Y-%m-%d', '%Y%m%d', '%Y/%m/%d', '%Y.%m.%d']
        for fmt in common_formats:
            if fmt == parse_fmt:
                continue
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # 如果所有格式都失败，抛出原始错误
        raise ValueError(f"无法解析日期字符串: {date_str}, 使用格式: {parse_fmt}")


def get_date_range(
    start: Optional[str] = None,
    end: Optional[str] = None,
    freq: str = 'D',
    periods: Optional[int] = None,
    fmt: str = '%Y-%m-%d',
    parse_fmt: str = '%Y-%m-%d'
) -> List[str]:
    """
    生成日期范围（不依赖pandas）
    
    Args:
        start: 开始日期字符串
        end: 结束日期字符串
        freq: 频率，支持 'D'（天）, 'W'（周）, 'M'（月）, 'Y'（年）, 'Q'（季度）, 'H'（半年）
        periods: 期数
        fmt: 输出日期格式
        parse_fmt: 解析输入日期的格式
        
    Returns:
        日期字符串列表
        
    Raises:
        ValueError: 参数无效时抛出
    """
    # 参数验证
    freq = freq.upper()
    valid_freqs = ['D', 'W', 'M', 'Y', 'Q', 'H']
    if freq not in valid_freqs:
        raise ValueError(f"freq必须是以下之一: {valid_freqs}")
    
    # 解析日期字符串
    def parse_date(d: Optional[str]) -> Optional[datetime]:
        if d is None:
            return None
        return parse_date_string(d, parse_fmt)
    
    start_date = parse_date(start)
    end_date = parse_date(end)
    current_date = datetime.now()
    
    # 如果没有提供start和end，但有periods，则使用当前日期
    if start_date is None and end_date is None:
        if periods is None:
            raise ValueError("至少需要提供 start、end 或 periods 中的一个")
        end_date = current_date
    elif start_date is None and end_date is not None and periods is None:
        # 只有end，没有start和periods，使用当前日期作为start
        start_date = current_date
    
    # 根据参数组合确定日期范围
    if start_date is not None and end_date is not None:
        # 有开始和结束日期
        if periods is not None:
            warnings.warn("当提供 start 和 end 时，periods 参数将被忽略")
        
        # 确保start_date <= end_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        date_list = _generate_date_range(start_date, end_date, freq)
        
    elif start_date is not None and periods is not None:
        # 有开始日期和期数
        date_list = _generate_date_range_by_periods(start_date, periods, freq)
        
    elif end_date is not None and periods is not None:
        # 有结束日期和期数
        date_list = _generate_date_range_by_end_periods(end_date, periods, freq)
        
    else:
        raise ValueError("无效的参数组合")
    
    # 格式化日期
    return [d.strftime(fmt) for d in date_list]


def _add_frequency(current: datetime, freq: str) -> datetime:
    """
    根据频率增加日期
    
    Args:
        current: 当前日期
        freq: 频率
        
    Returns:
        增加频率后的日期
    """
    if freq == 'D':
        return current + timedelta(days=1)
    elif freq == 'W':
        return current + timedelta(weeks=1)
    elif freq == 'M':
        # 月份加1
        year = current.year
        month = current.month + 1
        if month > 12:
            year += 1
            month = 1
        
        # 确保日不会超过目标月份的最后一天
        last_day = calendar.monthrange(year, month)[1]
        day = min(current.day, last_day)
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    elif freq == 'Y':
        # 年份加1
        year = current.year + 1
        month = current.month
        day = current.day
        
        # 处理2月29日的情况
        if month == 2 and day == 29 and not calendar.isleap(year):
            day = 28
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    elif freq == 'Q':  # 季度
        months_to_add = 3
        year = current.year
        month = current.month + months_to_add
        
        if month > 12:
            year += (month - 1) // 12
            month = ((month - 1) % 12) + 1
        
        last_day = calendar.monthrange(year, month)[1]
        day = min(current.day, last_day)
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    elif freq == 'H':  # 半年
        months_to_add = 6
        year = current.year
        month = current.month + months_to_add
        
        if month > 12:
            year += (month - 1) // 12
            month = ((month - 1) % 12) + 1
        
        last_day = calendar.monthrange(year, month)[1]
        day = min(current.day, last_day)
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    else:
        # 默认按天处理
        return current + timedelta(days=1)


def _subtract_frequency(current: datetime, freq: str) -> datetime:
    """
    根据频率减少日期
    
    Args:
        current: 当前日期
        freq: 频率
        
    Returns:
        减少频率后的日期
    """
    if freq == 'D':
        return current - timedelta(days=1)
    elif freq == 'W':
        return current - timedelta(weeks=1)
    elif freq == 'M':
        # 月份减1
        year = current.year
        month = current.month - 1
        if month < 1:
            year -= 1
            month = 12
        
        last_day = calendar.monthrange(year, month)[1]
        day = min(current.day, last_day)
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    elif freq == 'Y':
        # 年份减1
        year = current.year - 1
        month = current.month
        day = current.day
        
        if month == 2 and day == 29 and not calendar.isleap(year):
            day = 28
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    elif freq == 'Q':  # 季度
        months_to_subtract = 3
        year = current.year
        month = current.month - months_to_subtract
        
        if month < 1:
            year -= 1
            month += 12
        
        last_day = calendar.monthrange(year, month)[1]
        day = min(current.day, last_day)
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    elif freq == 'H':  # 半年
        months_to_subtract = 6
        year = current.year
        month = current.month - months_to_subtract
        
        if month < 1:
            year -= 1
            month += 12
        
        last_day = calendar.monthrange(year, month)[1]
        day = min(current.day, last_day)
        
        return datetime(year, month, day, current.hour, current.minute, current.second)
    else:
        # 默认按天处理
        return current - timedelta(days=1)


def _generate_date_range(
    start_date: datetime,
    end_date: datetime,
    freq: str
) -> List[datetime]:
    """生成从start_date到end_date的日期范围"""
    date_list = []
    current = start_date
    
    while current <= end_date:
        date_list.append(current)
        current = _add_frequency(current, freq)
    
    return date_list


def _generate_date_range_by_periods(
    start_date: datetime,
    periods: int,
    freq: str
) -> List[datetime]:
    """从start_date开始，生成指定期数的日期范围"""
    if periods <= 0:
        return []
    
    date_list = []
    current = start_date
    
    for _ in range(periods):
        date_list.append(current)
        current = _add_frequency(current, freq)
    
    return date_list


def _generate_date_range_by_end_periods(
    end_date: datetime,
    periods: int,
    freq: str
) -> List[datetime]:
    """以end_date结束，生成指定期数的日期范围（逆序）"""
    if periods <= 0:
        return []
    
    # 先生成逆序的日期列表
    date_list = []
    current = end_date
    
    for _ in range(periods):
        date_list.append(current)
        current = _subtract_frequency(current, freq)
    
    # 反转列表，使其按时间顺序排列
    date_list.reverse()
    return date_list


def simplify_date_ranges(
    dates: Union[List[str], Tuple[str], set],
    parse_fmt: str = '%Y-%m-%d',
    out_fmt: str = '%Y-%m-%d'
) -> List[Tuple[str, str, int]]:
    """
    简化日期范围，将连续日期合并为区间
    
    Args:
        dates: 日期字符串列表/元组/集合
        parse_fmt: 解析日期格式
        out_fmt: 输出日期格式
        
    Returns:
        包含(start, end, count)的元组列表
    """
    from collections import namedtuple
    
    if not isinstance(dates, (tuple, list, set)):
        raise TypeError("dates必须是tuple、list或set类型")
    
    if not dates:
        return []
    
    # 过滤并转换日期
    filtered_dates = []
    for d in set(str(d) for d in dates):
        try:
            dt = parse_date_string(d, parse_fmt)
            filtered_dates.append(dt)
        except ValueError:
            # 跳过无法解析的日期
            continue
    
    if not filtered_dates:
        return []
    
    filtered_dates.sort()
    
    # 合并连续日期
    simplified = []
    start = end = None
    
    for i, current_date in enumerate(filtered_dates):
        if start is None:
            start = end = current_date
        elif (current_date - end).days == 1:
            end = current_date
        else:
            simplified.append((start, end))
            start = end = current_date
    
    # 添加最后一个区间
    if start is not None:
        simplified.append((start, end))
    
    # 转换为字符串并计算天数
    DateRange = namedtuple("DateRange", ["start", "end", "count"])
    result = []
    
    for start_dt, end_dt in simplified:
        count = (end_dt - start_dt).days + 1
        result.append(DateRange(
            start_dt.strftime(out_fmt),
            end_dt.strftime(out_fmt),
            count
        ))
    
    return result


# 测试函数
def test_date_range():
    """测试日期范围生成函数"""
    print("=== 测试get_date_range函数 ===")
    
    # 测试1: 指定开始和结束日期
    print("\n测试1 - 开始和结束日期:")
    dates1 = get_date_range(start="2023-12-20", end="2023-12-25")
    print(f"日期范围: {dates1}")
    
    # 测试2: 指定开始日期和期数
    print("\n测试2 - 开始日期和期数:")
    dates2 = get_date_range(start="2023-12-25", periods=7)
    print(f"7天日期: {dates2}")
    
    # 测试3: 指定结束日期和期数
    print("\n测试3 - 结束日期和期数:")
    dates3 = get_date_range(end="2023-12-31", periods=5)
    print(f"最后5天: {dates3}")
    
    # 测试4: 按月频率
    print("\n测试4 - 按月频率:")
    dates4 = get_date_range(start="2023-01-01", end="2023-03-01", freq="M")
    print(f"每月: {dates4}")
    
    # 测试5: 按周频率
    print("\n测试5 - 按周频率:")
    dates5 = get_date_range(start="2023-12-01", end="2023-12-31", freq="W")
    print(f"每周: {dates5}")
    
    # 测试6: 按季度频率
    print("\n测试6 - 按季度频率:")
    dates6 = get_date_range(start="2023-01-01", end="2023-12-31", freq="Q")
    print(f"每季度: {dates6}")
    
    # 测试7: 自定义输出格式
    print("\n测试7 - 自定义输出格式:")
    dates7 = get_date_range(start="2023-12-25", periods=3, fmt="%Y%m%d")
    print(f"自定义格式: {dates7}")
    
    # 测试8: 简化日期范围
    print("\n测试8 - 简化日期范围:")
    date_list = ["2023-12-01", "2023-12-02", "2023-12-03", "2023-12-05", "2023-12-06"]
    simplified = simplify_date_ranges(date_list)
    print(f"简化结果: {simplified}")
    
    # 测试9: 不同日期格式解析
    print("\n测试9 - 不同日期格式解析:")
    dates9 = get_date_range(start="20231220", end="20231225", parse_fmt="%Y%m%d", fmt="%Y-%m-%d")
    print(f"不同格式解析: {dates9}")


class vicDate:
    """
    日期处理类
    
    提供丰富的日期操作功能
    """
    
    def __init__(self, date_str=None, fmt=None):
        """
        初始化vicDate对象
        
        参数:
            date_str: 日期字符串
            fmt: 日期格式
        """
        self.date_obj = None
        self.fmt = fmt
        
        if date_str is not None:
            self.date_obj = parse_date_string(date_str, fmt)
        else:
            self.date_obj = datetime.now()
    
    def strftime(self, fmt=None):
        """
        格式化日期
        
        参数:
            fmt: 日期格式
        
        返回:
            格式化后的日期字符串
        """
        fmt = fmt or self.fmt or '%Y-%m-%d'
        return self.date_obj.strftime(fmt)
    
    def add_days(self, days):
        """
        添加天数
        
        参数:
            days: 天数
        
        返回:
            新的vicDate对象
        """
        new_date = self.date_obj + timedelta(days=days)
        return vicDate(new_date.strftime('%Y-%m-%d'))
    
    def sub_days(self, days):
        """
        减去天数
        
        参数:
            days: 天数
        
        返回:
            新的vicDate对象
        """
        new_date = self.date_obj - timedelta(days=days)
        return vicDate(new_date.strftime('%Y-%m-%d'))
    
    def add_months(self, months):
        """
        添加月数
        
        参数:
            months: 月数
        
        返回:
            新的vicDate对象
        """
        year = self.date_obj.year
        month = self.date_obj.month + months
        
        if month > 12:
            year += (month - 1) // 12
            month = (month - 1) % 12 + 1
        elif month < 1:
            year += (month - 1) // 12
            month = (month - 1) % 12 + 1
        
        last_day = calendar.monthrange(year, month)[1]
        day = min(self.date_obj.day, last_day)
        
        new_date = datetime(year, month, day, self.date_obj.hour, self.date_obj.minute, self.date_obj.second)
        return vicDate(new_date.strftime('%Y-%m-%d'))
    
    def sub_months(self, months):
        """
        减去月数
        
        参数:
            months: 月数
        
        返回:
            新的vicDate对象
        """
        return self.add_months(-months)
    
    def add_years(self, years):
        """
        添加年数
        
        参数:
            years: 年数
        
        返回:
            新的vicDate对象
        """
        year = self.date_obj.year + years
        month = self.date_obj.month
        day = self.date_obj.day
        
        # 处理2月29日的情况
        if month == 2 and day == 29 and not calendar.isleap(year):
            day = 28
        
        new_date = datetime(year, month, day, self.date_obj.hour, self.date_obj.minute, self.date_obj.second)
        return vicDate(new_date.strftime('%Y-%m-%d'))
    
    def sub_years(self, years):
        """
        减去年数
        
        参数:
            years: 年数
        
        返回:
            新的vicDate对象
        """
        return self.add_years(-years)
    
    def get_date_range(self, end_date, freq='D', fmt='%Y-%m-%d'):
        """
        获取日期范围
        
        参数:
            end_date: 结束日期
            freq: 频率
            fmt: 日期格式
        
        返回:
            日期字符串列表
        """
        start = self.strftime('%Y-%m-%d')
        if isinstance(end_date, vicDate):
            end = end_date.strftime('%Y-%m-%d')
        else:
            end = end_date
        
        return get_date_range(start=start, end=end, freq=freq, fmt=fmt)
    
    def getDateRangeEx(self, end_date, freq='D', fmt='%Y-%m-%d'):
        """
        获取日期范围（扩展方法）
        
        参数:
            end_date: 结束日期
            freq: 频率
            fmt: 日期格式
        
        返回:
            日期字符串列表
        """
        return self.get_date_range(end_date, freq, fmt)
    
    def __str__(self):
        """
        字符串表示
        """
        return self.strftime()
    
    def __repr__(self):
        """
        repr表示
        """
        return f"vicDate({self.strftime()})"
    
    def __eq__(self, other):
        """
        等于比较
        """
        if isinstance(other, vicDate):
            return self.date_obj == other.date_obj
        elif isinstance(other, (datetime, date)):
            return self.date_obj == other
        elif isinstance(other, str):
            try:
                other_date = parse_date_string(other)
                return self.date_obj == other_date
            except:
                return False
        return False
    
    def __lt__(self, other):
        """
        小于比较
        """
        if isinstance(other, vicDate):
            return self.date_obj < other.date_obj
        elif isinstance(other, (datetime, date)):
            return self.date_obj < other
        elif isinstance(other, str):
            try:
                other_date = parse_date_string(other)
                return self.date_obj < other_date
            except:
                return False
        return False
    
    def __le__(self, other):
        """
        小于等于比较
        """
        return self < other or self == other
    
    def __gt__(self, other):
        """
        大于比较
        """
        return not self <= other
    
    def __ge__(self, other):
        """
        大于等于比较
        """
        return not self < other


if __name__ == "__main__":
    # 运行测试
    test_date_range()
    
    # 测试vicDate类
    print("\n=== 测试vicDate类 ===")
    
    # 测试1: 初始化
    print("\n测试1 - 初始化:")
    d1 = vicDate()
    print(f"当前日期: {d1}")
    
    d2 = vicDate("2023-12-25")
    print(f"指定日期: {d2}")
    
    # 测试2: 日期操作
    print("\n测试2 - 日期操作:")
    d3 = d2.add_days(7)
    print(f"加7天: {d3}")
    
    d4 = d3.sub_months(1)
    print(f"减1个月: {d4}")
    
    # 测试3: 日期范围
    print("\n测试3 - 日期范围:")
    d5 = vicDate("2023-12-20")
    d6 = vicDate("2023-12-25")
    dates = d5.get_date_range(d6)
    print(f"日期范围: {dates}")
    
    # 测试4: 比较操作
    print("\n测试4 - 比较操作:")
    print(f"d2 < d3: {d2 < d3}")
    print(f"d3 > d4: {d3 > d4}")
    print(f"d2 == d2: {d2 == d2}")
