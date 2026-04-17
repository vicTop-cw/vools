"""
日期相关工具函数模块

包含日期处理、日期范围生成等功能
"""

from datetime import datetime, date, timedelta
import calendar
import re
from typing import List, Optional, Tuple, Union, Dict, Any

__all__ = [
    # 从 mydate.py 导入的函数
    'vDate',
    'get_week',
    'get_month',
    'days_gap',
    'weeks_gap',
    'months_gap',
    # 从 mydates.py 导入的函数
    'get_recently_months',
    'get_recently_weeks',
    'get_recently_days',
    'get_dates',
    # 从 range.py 导入的函数和类
    'parse_date_string',
    'get_date_range',
    'simplify_date_ranges',
    'vicDate',
]


# 从 mydate.py 导入的函数
def vDate(dt=None, fmt=None, diffDays: Union[float, int] = 0):
    """
    日期处理函数
    
    参数:
        dt: 日期值（字符串、时间戳或 datetime 对象）
        fmt: 日期格式
        diffDays: 日期偏移天数
    
    返回:
        格式化后的日期字符串
    """
    if isinstance(diffDays, str) or isinstance(fmt, (float, int)):
        diffDays, fmt = fmt, diffDays
    
    def _parse_date(date_str, fmt):
        # 将字符串日期转换为年、月、日
        dt = datetime.strptime(date_str, fmt)
        return (dt.year, dt.month, dt.day)
    
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
        fmt = fmt.replace('yyyy','%Y').replace('MM','%m').replace('dd','%d').replace('mm','%M').replace('HH','%H')
        fmt = fmt.replace('YYYY','%Y').replace('SS','%S').replace('ss','%S').replace('yy','%y')
    
    if dt is None:
        result = datetime.now()
        result = result if diffDays == 0 else result + timedelta(days=diffDays)
        return result.strftime(fmt)

    if isinstance(dt, (int, float)):  # 时间戳
        result = datetime.fromtimestamp(dt)
    elif isinstance(dt, str):  # 字符串日期
        if len(dt) == 8 and dt.isdigit():  # 8位数字格式
            result = datetime(int(dt[:4]), int(dt[4:6]), int(dt[6:]))
        elif re.search(r"^\d{4}-\d{2}-\d{2}$", dt):
            dt = dt.replace('-','')
            result = datetime(int(dt[:4]), int(dt[4:6]), int(dt[6:]))
        elif re.search(r"^\d{4}-\d{2}-\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9]$", dt):
            tm = dt.split(" ")[1].split(":")
            dt = dt.split(" ")[0].replace('-','')
            result = datetime(int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), int(tm[2]))
        elif re.search(r"^\d{4}\d{2}\d{2} [0|1|2][0-9]:[0-5][0-9]:[0-5][0-9]$", dt):
            tm = dt.split(" ")[1].split(":")
            result = datetime(int(dt[:4]), int(dt[4:6]), int(dt[6:]), int(tm[0]), int(tm[1]), int(tm[2]))
        else:
            if fmt is None:
                raise ValueError("需要指定日期格式")
            result = datetime(*_parse_date(dt, fmt))
    elif isinstance(dt, datetime):
        result = dt
    else:
        raise TypeError("不支持的日期类型")
    
    result = result if diffDays == 0 else result + timedelta(days=diffDays)
    return result.strftime(fmt)


def get_week(dt, num: int = 0, weekday: int = 1):
    """
    获取指定日期的周开始日期
    
    参数:
        dt: 日期字符串
        num: 周偏移
        weekday: 一周的开始（1-7，默认为1即周一）
    
    返回:
        周开始日期字符串
    """
    if dt is None:
        return None
    if num is None:
        num = 0
    assert(1 <= weekday <= 7)
    dt = str(dt)[:10].strip()
    l = len(dt)
    assert(l in (8, 10))
    fmt = '%Y-%m-%d' if l == 10 else '%Y%m%d'
    dt = datetime.strptime(dt, fmt)
    w0 = dt - timedelta(days=(int(dt.strftime('%u')) - weekday))
    if num == 0:
        return w0.strftime(fmt)
    else:
        return (w0 - timedelta(days=num * 7)).strftime(fmt)


def get_month(dt: str, num: int = 0, is_lastday: bool = False) -> str:
    """
    计算与指定日期相差num个月的月初或月末日期
    
    参数:
        dt: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
        num: 月份差，正数表示过去，负数表示未来，0表示当月
        is_lastday: 是否返回月末日期，False返回月初，True返回月末
    
    返回:
        日期字符串，格式与输入dt相同
    """
    # 检查参数是否为None
    if dt is None or num is None or is_lastday is None:
        return None
    dt = str(dt)[:10].strip()
    
    try:
        # 判断输入格式并解析日期
        if '-' in dt:
            input_format = '%Y-%m-%d'
            output_format = '%Y-%m-%d'
            date_obj = datetime.strptime(dt, input_format)
        else:
            input_format = '%Y%m%d'
            output_format = '%Y%m%d'
            date_obj = datetime.strptime(dt, input_format)
        
        # 计算目标年份和月份
        year = date_obj.year
        month = date_obj.month
        
        # 计算目标月份
        total_months = year * 12 + month - 1 - num
        target_year = total_months // 12
        target_month = total_months % 12 + 1
        
        # 计算月初或月末日期
        if is_lastday:
            # 计算月末：下个月第一天减去一天
            if target_month == 12:
                next_year = target_year + 1
                next_month = 1
            else:
                next_year = target_year
                next_month = target_month + 1
            
            # 获取下个月第一天的前一天（即本月最后一天）
            first_day_next_month = datetime(next_year, next_month, 1)
            last_day = first_day_next_month - timedelta(days=1)
            result_date = last_day
        else:
            # 月初就是当月第一天
            result_date = datetime(target_year, target_month, 1)
        
        # 格式化输出，保持与输入相同的格式
        return result_date.strftime(output_format)
        
    except Exception as e:
        # 日期解析或计算出错时返回None
        return None


def days_gap(dt1: str, dt2: str) -> int:
    """
    计算两个日期之间的天数差 (dt1 - dt2)
    
    参数:
        dt1: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
        dt2: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
    
    返回:
        整数，表示dt1与dt2之间的天数差
    """
    # 检查参数是否为None
    if dt1 is None or dt2 is None:
        return None
    dt1 = str(dt1)[:10].strip()
    dt2 = str(dt2)[:10].strip()
    
    try:
        # 统一处理日期格式
        def parse_date(dt_str):
            if '-' in dt_str:
                return datetime.strptime(dt_str, '%Y-%m-%d')
            else:
                return datetime.strptime(dt_str, '%Y%m%d')
        
        date1 = parse_date(dt1)
        date2 = parse_date(dt2)
        
        # 计算天数差 (dt1 - dt2)
        delta = date1 - date2
        return delta.days
        
    except Exception as e:
        return None


def weeks_gap(dt1: str, dt2: str) -> int:
    """
    计算两个日期之间的周数差 (dt1 - dt2)，周一为一周的第一天
    
    参数:
        dt1: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
        dt2: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
    
    返回:
        整数，表示dt1与dt2之间的周数差
    """
    # 检查参数是否为None
    if dt1 is None or dt2 is None:
        return None
    dt1 = str(dt1)[:10].strip()
    dt2 = str(dt2)[:10].strip()
    
    try:
        # 统一处理日期格式
        def parse_date(dt_str):
            if '-' in dt_str:
                return datetime.strptime(dt_str, '%Y-%m-%d')
            else:
                return datetime.strptime(dt_str, '%Y%m%d')
        
        date1 = parse_date(dt1)
        date2 = parse_date(dt2)
        
        # 计算每个日期所在的周一（周一为一周的第一天）
        # weekday() 返回：周一=0, 周二=1, ..., 周日=6
        monday1 = date1 - timedelta(days=date1.weekday())
        monday2 = date2 - timedelta(days=date2.weekday())
        
        # 计算周数差
        delta = monday1 - monday2
        weeks_diff = delta.days // 7
        
        return weeks_diff
        
    except Exception as e:
        return None


def months_gap(dt1: str, dt2: str) -> int:
    """
    计算两个日期之间的月数差 (dt1 - dt2)
    
    参数:
        dt1: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
        dt2: 日期字符串，格式为yyyyMMdd或yyyy-MM-dd
    
    返回:
        整数，表示dt1与dt2之间的月数差
    """
    # 检查参数是否为None
    if dt1 is None or dt2 is None:
        return None
    dt1 = str(dt1)[:10].strip()
    dt2 = str(dt2)[:10].strip()
    
    try:
        # 统一处理日期格式
        def parse_date(dt_str):
            if '-' in dt_str:
                return datetime.strptime(dt_str, '%Y-%m-%d')
            else:
                return datetime.strptime(dt_str, '%Y%m%d')
        
        date1 = parse_date(dt1)
        date2 = parse_date(dt2)
        
        # 计算月份差：年份差×12 + 月份差
        months_diff = (date1.year - date2.year) * 12 + (date1.month - date2.month)
        
        return months_diff
        
    except Exception as e:
        return None


# 从 mydates.py 导入的函数
def get_recently_months(dt: str, num: int = 11) -> list:
    """
    获取最近几个月的月末日期
    
    参数:
        dt: 日期字符串
        num: 月份数量
    
    返回:
        日期字符串列表
    """
    # 高效处理日期格式
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(dt) == 8 else "%Y-%m-%d"
    try:
        dt_obj = datetime.strptime(dt, fmt)
    except:
        alt_fmt = "%Y-%m-%d" if fmt == "%Y%m%d" else "%Y%m%d"
        dt_obj = datetime.strptime(dt, alt_fmt)
    
    if num == 0:
        return [dt]
    
    abs_num = abs(num)
    result = [dt]
    
    # 高效计算月末日期
    year = dt_obj.year
    month = dt_obj.month
    day = dt_obj.day
    lmd = lambda x, m: result.append(x.strftime(m))
    # 直接计算偏移后的月末
    for i in range(1, abs_num + 1):
        if num > 0:  # 向左偏移（过去）
            target_month = month - i
            target_year = year + (target_month - 1) // 12
            target_month = (target_month - 1) % 12 + 1
        else:  # 向右偏移（未来）
            target_month = month + i
            target_year = year + (target_month - 1) // 12
            target_month = (target_month - 1) % 12 + 1
        
        # 计算月末 - 更高效的方法
        if target_month == 12:
            next_month = datetime(target_year + 1, 1, 1)
        else:
            next_month = datetime(target_year, target_month + 1, 1)
        last_day = next_month - timedelta(days=1)
        
        lmd(last_day, fmt)
    
    return result


def get_recently_weeks(dt: str, num: int = 13) -> list:
    """
    获取最近几个周的周日日期
    
    参数:
        dt: 日期字符串
        num: 周数
    
    返回:
        日期字符串列表
    """
    # 高效处理日期格式
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(dt) == 8 else "%Y-%m-%d"
    try:
        dt_obj = datetime.strptime(dt, fmt)
    except:
        alt_fmt = "%Y-%m-%d" if fmt == "%Y%m%d" else "%Y%m%d"
        dt_obj = datetime.strptime(dt, alt_fmt)
    
    if num == 0:
        return [dt]
    
    abs_num = abs(num)
    result = [dt]
    
    # 计算当前日期是周几 (0=周一, 6=周日)
    current_weekday = dt_obj.weekday()
    lmd = lambda x, m: result.append(x.strftime(m))
    
    # 高效计算周日偏移
    for i in range(1, abs_num + 1):
        if num > 0:  # 向左偏移（过去）
            # 直接计算到目标周日的天数
            days_offset = -7 * i + (6 - current_weekday)
        else:  # 向右偏移（未来）
            # 直接计算到目标周日的天数
            days_offset = 7 * i - current_weekday
        
        target_date = dt_obj + timedelta(days=days_offset)
        lmd(target_date, fmt)
    
    return result


def get_recently_days(dt: str, num: int = 13) -> list:
    """
    获取最近几天的日期
    
    参数:
        dt: 日期字符串
        num: 天数
    
    返回:
        日期字符串列表
    """
    # 高效处理日期格式
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(dt) == 8 else "%Y-%m-%d"
    try:
        dt_obj = datetime.strptime(dt, fmt)
    except:
        alt_fmt = "%Y-%m-%d" if fmt == "%Y%m%d" else "%Y%m%d"
        dt_obj = datetime.strptime(dt, alt_fmt)
    
    if num == 0:
        return [dt]
    
    abs_num = abs(num)
    result = [dt]
    lmd = lambda x, m: result.append(x.strftime(m))
    
    # 直接计算偏移天数
    for i in range(1, abs_num + 1):
        days_offset = i if num < 0 else -i
        target_date = dt_obj + timedelta(days=days_offset)
        lmd(target_date, fmt)
    
    return result


def get_dates(dt: str, num: int = 13, tp: str = "d") -> list:
    """
    获取日期范围
    
    参数:
        dt: 日期字符串
        num: 数量
        tp: 类型 ('d'=天, 'w'=周, 'm'=月)
    
    返回:
        日期字符串列表
    """
    tp = tp[0].lower() if tp else 'd'
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(dt) == 8 else "%Y-%m-%d"
    try:
        dt_obj = datetime.strptime(dt, fmt)
    except:
        alt_fmt = "%Y-%m-%d" if fmt == "%Y%m%d" else "%Y%m%d"
        dt_obj = datetime.strptime(dt, alt_fmt)
    
    if num == 0:
        return [dt]
    
    abs_num = abs(num)
    result = [dt]
    lmd = lambda x, m: result.append(x.strftime(m))

    if tp == "d":
        for i in range(1, abs_num + 1):
            days_offset = i if num < 0 else -i
            target_date = dt_obj + timedelta(days=days_offset)
            lmd(target_date, fmt)
    elif tp == "w":
        # 计算当前日期是周几 (0=周一, 6=周日)
        current_weekday = dt_obj.weekday()
        for i in range(1, abs_num + 1):
            if num > 0:  # 向左偏移（过去）
                # 直接计算到目标周日的天数
                days_offset = -7 * i + (6 - current_weekday)
            else:  # 向右偏移（未来）
                # 直接计算到目标周日的天数
                days_offset = 7 * i - current_weekday
            
            target_date = dt_obj + timedelta(days=days_offset)
            lmd(target_date, fmt)
    elif tp == "m":
        # 高效计算月末日期
        year = dt_obj.year
        month = dt_obj.month
        day = dt_obj.day
        # 直接计算偏移后的月末
        for i in range(1, abs_num + 1):
            if num > 0:  # 向左偏移（过去）
                target_month = month - i
                target_year = year + (target_month - 1) // 12
                target_month = (target_month - 1) % 12 + 1
            else:  # 向右偏移（未来）
                target_month = month + i
                target_year = year + (target_month - 1) // 12
                target_month = (target_month - 1) % 12 + 1
            
            # 计算月末 - 更高效的方法
            if target_month == 12:
                next_month = datetime(target_year + 1, 1, 1)
            else:
                next_month = datetime(target_year, target_month + 1, 1)
            last_day = next_month - timedelta(days=1)
            
            lmd(last_day, fmt)
    else:
        return []
    
    return result


# 从 range.py 导入的函数
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
            import warnings
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


# 从 range.py 导入的类
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

