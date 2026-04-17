from datetime import datetime, timedelta

def get_recently_months(dt: str, num: int) -> list:
    # 高效处理日期格式
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
    lmd = lambda x,m : result.append(x.strftime(m))
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
        
        # result.append(last_day.strftime(fmt))
        lmd(last_day,fmt)
    
    return result

def get_recently_weeks(dt: str, num: int) -> list:
    # 高效处理日期格式
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
    lmd = lambda x,m : result.append(x.strftime(m))
    
    # 高效计算周日偏移
    for i in range(1, abs_num + 1):
        if num > 0:  # 向左偏移（过去）
            # 直接计算到目标周日的天数
            days_offset = -7 * i + (6 - current_weekday)
        else:  # 向右偏移（未来）
            # 直接计算到目标周日的天数
            days_offset = 7 * i - current_weekday
        
        target_date = dt_obj + timedelta(days=days_offset)
        # result.append(target_date.strftime(fmt))
        lmd(target_date,fmt)
    
    return result

def get_recently_days(dt: str, num: int) -> list:
    # 高效处理日期格式
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
    lmd = lambda x,m : result.append(x.strftime(m))
    
    # 直接计算偏移天数
    for i in range(1, abs_num + 1):
        days_offset = i if num < 0 else -i
        target_date = dt_obj + timedelta(days=days_offset)
        lmd(target_date,fmt)
        # result.append(target_date.strftime(fmt))
    
    return result


def get_dates(dt:str,num:int=13,tp:str="d") -> list :
    tp = tp[0].lower() if tp else 'd'
    if tp == "d":
        return get_recently_days(dt,num)
    if tp == "w":
        return get_recently_weeks(dt,num)
    if tp == "m":
        return get_recently_months(dt,num)
    return []

