"""
date 相关工具函数模块

包含 vDate 函数和各种日期相关的 Spark UDF
"""

from datetime import datetime, timedelta
import re
from typing import Optional, Union

__all__ = [
    'vDate',
    'get_week',
    'get_month',
    'days_gap',
    'weeks_gap',
    'months_gap',
]


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
