import re
import datetime
import calendar
from typing import Optional, List, Tuple, Union, Dict, Any, Set
from functools import lru_cache

__all__ = ['DateProcessor','EnhancedDateFormatter']

class DateProcessor:
    """
    日期处理器类
    
    专门处理日期相关的计算和衍生变量，包括：
    1. 单个日期计算（周、月偏移）
    2. 日期列表生成（天、周、月连续列表）
    3. 日期格式转换（紧凑格式yyyyMMdd和标准格式yyyy-MM-dd）
    
    主要功能：
    - 支持日期运算：run_week+3&3, run_month-2&15等
    - 支持日期列表：run_days>3, run_weeks>3&3, run_months<3&1等
    - 自动处理月份天数、闰年等边界情况
    - 确保列表包含基准日期且元素唯一、有序
    
    使用示例：
    >>> processor = DateProcessor('20260227')
    >>> processor.get_single_date('run_week+3&3')
    '20260318'
    >>> processor.get_date_list('run_weeks>3&3')
    "'20260227'，'20260304'，'20260311'，'20260318'"
    """
    
    def __init__(self, run_date: Optional[str] = None):
        """
        初始化日期处理器
        
        Args:
            run_date: 基准日期，支持格式：
                     - 'yyyyMMdd'（如'20260227'）
                     - 'yyyy-MM-dd'（如'2026-02-27'）
                     - datetime.date对象
                     如果为None，则使用昨天日期
        """
        self.set_run_date(run_date)
    
    def set_run_date(self, run_date: Optional[str] = None):
        """
        设置基准日期
        
        Args:
            run_date: 基准日期，格式同上
            
        Raises:
            ValueError: 如果日期格式无法解析
        """
        if run_date is None:
            # 默认使用昨天
            self.run_date = (datetime.datetime.now() - datetime.timedelta(days=1)).date()
        else:
            self.run_date = self._parse_date(run_date)
        
        # 更新所有衍生日期
        self._update_derived_dates()
    
    def _parse_date(self, date_input: Union[str, datetime.date]) -> datetime.date:
        """
        解析日期输入为datetime.date对象
        
        Args:
            date_input: 日期输入
            
        Returns:
            datetime.date: 解析后的日期对象
            
        Raises:
            ValueError: 如果日期格式无法解析
        """
        if isinstance(date_input, datetime.date):
            return date_input
        
        date_str = str(date_input).strip()
        
        # 移除可能的单引号
        if date_str.startswith("'") and date_str.endswith("'"):
            date_str = date_str[1:-1]
        
        # 尝试各种格式
        for fmt in ["%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"]:
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        raise ValueError(f"无法解析日期字符串: {date_input}")
    
    def _date_to_str(self, date_obj: datetime.date, fmt_type: str = "compact") -> str:
        """
        将日期对象转换为字符串
        
        Args:
            date_obj: 日期对象
            fmt_type: 格式类型
                     - "compact": yyyyMMdd格式
                     - "standard": yyyy-MM-dd格式
                     
        Returns:
            str: 格式化后的日期字符串
        """
        if fmt_type == "compact":
            return date_obj.strftime("%Y%m%d")
        else:  # standard
            return date_obj.strftime("%Y-%m-%d")
    
    def _update_derived_dates(self):
        """更新所有衍生日期变量"""
        # 基础格式
        self.run_date_compact = self._date_to_str(self.run_date, "compact")
        self.run_date_standard = self._date_to_str(self.run_date, "standard")
        
        # 周计算
        self.week_begin, self.week_end = self._get_week_range(self.run_date)
        self.run_week_begin_compact = self._date_to_str(self.week_begin, "compact")
        self.run_week_begin_standard = self._date_to_str(self.week_begin, "standard")
        self.run_week_end_compact = self._date_to_str(self.week_end, "compact")
        self.run_week_end_standard = self._date_to_str(self.week_end, "standard")
        
        # 月计算
        self.month_begin, self.month_end = self._get_month_range(self.run_date)
        self.run_month_begin_compact = self._date_to_str(self.month_begin, "compact")
        self.run_month_begin_standard = self._date_to_str(self.month_begin, "standard")
        self.run_month_end_compact = self._date_to_str(self.month_end, "compact")
        self.run_month_end_standard = self._date_to_str(self.month_end, "standard")
    
    def _get_week_range(self, date_obj: datetime.date) -> Tuple[datetime.date, datetime.date]:
        """
        获取日期所在周的周一和周日
        
        Args:
            date_obj: 日期对象
            
        Returns:
            Tuple[datetime.date, datetime.date]: (周一, 周日)
        """
        # 获取星期几 (0=Monday, 6=Sunday)
        weekday = date_obj.weekday()
        
        # 计算周一
        monday = date_obj - datetime.timedelta(days=weekday)
        # 计算周日
        sunday = date_obj + datetime.timedelta(days=6 - weekday)
        
        return monday, sunday
    
    def _get_month_range(self, date_obj: datetime.date) -> Tuple[datetime.date, datetime.date]:
        """
        获取日期所在月的第一天和最后一天
        
        Args:
            date_obj: 日期对象
            
        Returns:
            Tuple[datetime.date, datetime.date]: (月初, 月末)
        """
        # 获取当月第一天
        first_day = date_obj.replace(day=1)
        
        # 获取当月最后一天
        _, last_day_num = calendar.monthrange(date_obj.year, date_obj.month)
        last_day = date_obj.replace(day=last_day_num)
        
        return first_day, last_day
    
    def _get_weekday_date(self, base_date: datetime.date, target_weekday: int, weeks_offset: int = 0) -> datetime.date:
        """
        获取指定周几的日期
        
        Args:
            base_date: 基准日期
            target_weekday: 目标星期几 (1-7, 1=周一, 7=周日)
            weeks_offset: 周偏移量
            
        Returns:
            datetime.date: 计算后的日期
        """
        # 转换target_weekday到Python的weekday (0=周一, 6=周日)
        target_weekday_py = target_weekday - 1 if 1 <= target_weekday <= 7 else 0
        
        # 获取基准日期所在周的周一
        current_weekday = base_date.weekday()  # 0=周一, 6=周日
        current_monday = base_date - datetime.timedelta(days=current_weekday)
        
        # 计算目标日期
        target_date = current_monday + datetime.timedelta(days=target_weekday_py)
        
        # 应用周偏移
        if weeks_offset != 0:
            target_date += datetime.timedelta(weeks=weeks_offset)
        
        return target_date
    
    def _get_month_day_date(self, base_date: datetime.date, target_day: int, months_offset: int = 0) -> datetime.date:
        """
        获取指定月份的第几天
        
        Args:
            base_date: 基准日期
            target_day: 目标日期 (1-31)
            months_offset: 月偏移量
            
        Returns:
            datetime.date: 计算后的日期
        """
        # 计算目标年月
        year = base_date.year
        month = base_date.month + months_offset
        
        # 调整年月
        if month > 12:
            year += (month - 1) // 12
            month = (month - 1) % 12 + 1
        elif month < 1:
            year += (month - 12) // 12
            month = (month - 1) % 12 + 1
            if month == 0:
                month = 12
        
        # 获取该月的天数
        _, last_day = calendar.monthrange(year, month)
        
        # 确保target_day不超过该月的最后一天
        actual_day = min(target_day, last_day)
        
        return datetime.date(year, month, actual_day)
    
    def _get_day_list(self, days_count: int, direction: str, fmt_type: str = "compact") -> str:
        """
        获取日期列表（天级）
        
        Args:
            days_count: 天数
            direction: 方向，">"表示往后，"<"表示往前
            fmt_type: 格式类型，"compact"或"standard"
            
        Returns:
            str: 日期列表字符串，用中文逗号分隔，单引号包裹
        """
        dates = set()  # 使用集合确保唯一性
        
        if direction == ">":
            # 往后推，包括基准日期
            for i in range(days_count + 1):
                date_obj = self.run_date + datetime.timedelta(days=i)
                dates.add(date_obj)
        else:  # direction == "<"
            # 往前推，包括基准日期
            for i in range(days_count + 1):
                date_obj = self.run_date - datetime.timedelta(days=i)
                dates.add(date_obj)
        
        # 排序
        sorted_dates = sorted(dates)
        # 用单引号包裹，中文逗号分隔
        return ",".join([f"'{self._date_to_str(d, fmt_type)}'" for d in sorted_dates])
    
    def _get_week_list(self, weeks_count: int, target_weekday: int, direction: str, fmt_type: str = "compact") -> str:
        """
        获取日期列表（周级）
        
        Args:
            weeks_count: 周数
            target_weekday: 目标星期几 (1-7, 1=周一, 7=周日)
            direction: 方向，">"表示往后，"<"表示往前
            fmt_type: 格式类型，"compact"或"standard"
            
        Returns:
            str: 日期列表字符串，用中文逗号分隔，单引号包裹
        """
        dates = set()
        
        # 总是包含基准日期
        dates.add(self.run_date)
        
        if direction == ">":
            # 往后推，不包括当前周
            for i in range(1, weeks_count + 1):
                date_obj = self._get_weekday_date(self.run_date, target_weekday, i)
                dates.add(date_obj)
        else:  # direction == "<"
            # 往前推，不包括当前周
            for i in range(1, weeks_count + 1):
                date_obj = self._get_weekday_date(self.run_date, target_weekday, -i)
                dates.add(date_obj)
        
        # 排序
        sorted_dates = sorted(dates)
        # 用单引号包裹，中文逗号分隔
        return ",".join([f"'{self._date_to_str(d, fmt_type)}'" for d in sorted_dates])
    
    def _get_month_list(self, months_count: int, target_day: int, direction: str, fmt_type: str = "compact") -> str:
        """
        获取日期列表（月级）
        
        Args:
            months_count: 月数
            target_day: 目标日期 (1-31)
            direction: 方向，">"表示往后，"<"表示往前
            fmt_type: 格式类型，"compact"或"standard"
            
        Returns:
            str: 日期列表字符串，用中文逗号分隔，单引号包裹
        """
        dates = set()
        
        # 总是包含基准日期
        dates.add(self.run_date)
        
        if direction == ">":
            # 往后推，不包括当前月
            for i in range(1, months_count + 1):
                date_obj = self._get_month_day_date(self.run_date, target_day, i)
                dates.add(date_obj)
        else:  # direction == "<"
            # 往前推，不包括当前月
            for i in range(1, months_count + 1):
                date_obj = self._get_month_day_date(self.run_date, target_day, -i)
                dates.add(date_obj)
        
        # 排序
        sorted_dates = sorted(dates)
        # 用单引号包裹，中文逗号分隔
        return ",".join([f"'{self._date_to_str(d, fmt_type)}'" for d in sorted_dates])
    
    @lru_cache
    def get_single_date(self, expr: str) -> str:
        """
        获取单个日期
        
        Args:
            expr: 日期表达式，支持格式：
                 - run_week+3&3: 3周后的周三
                 - run_week-2&5: 2周前的周五
                 - run_month+3&13: 3个月后的13号
                 - run_month-3&1: 3个月前的1号
                 - 带_std后缀表示标准格式
                 
        Returns:
            str: 计算后的日期字符串
            
        Raises:
            ValueError: 如果表达式格式不正确
        """
        # 单个日期变量模式
        # 1. run_week+3&3
        # 2. run_month-2&15
        # 3. run_week_std+1&5
        single_date_pattern = r'^run_(week|month)(_std)?([+-]\d+)(&(\d+))?$'
        
        match = re.match(single_date_pattern, expr)
        if not match:
            raise ValueError(f"无效的日期表达式格式: {expr}")
        
        var_type = match.group(1)  # week 或 month
        is_std = match.group(2)  # _std 或 None
        offset_str = match.group(3)  # +3, -2
        day_str = match.group(5)  # 3, 13, 31 或 None
        
        # 确定格式类型
        fmt_type = "standard" if is_std else "compact"
        
        # 解析偏移量
        offset = int(offset_str)
        
        if var_type == "week":
            # 周计算
            target_weekday = int(day_str) if day_str else self.run_date.weekday() + 1
            date_obj = self._get_weekday_date(self.run_date, target_weekday, offset)
            return self._date_to_str(date_obj, fmt_type)
        else:  # month
            # 月计算
            target_day = int(day_str) if day_str else self.run_date.day
            date_obj = self._get_month_day_date(self.run_date, target_day, offset)
            return self._date_to_str(date_obj, fmt_type)
    
    @lru_cache
    def get_date_list(self, expr: str) -> str:
        """
        获取日期列表
        
        Args:
            expr: 日期列表表达式，支持格式：
                 - run_days>3: 往后3天的连续列表
                 - run_days<3: 往前3天的连续列表
                 - run_weeks>3&3: 往后3周，每周三的列表
                 - run_weeks<3&5: 往前3周，每周五的列表
                 - run_months>3&13: 往后3月，每月13号的列表
                 - run_months<3&1: 往前3月，每月1号的列表
                 - 带_std后缀表示标准格式
                 
        Returns:
            str: 日期列表字符串，用中文逗号分隔，单引号包裹
            
        Raises:
            ValueError: 如果表达式格式不正确
        """
        # 日期列表变量模式
        # 1. run_days>3
        # 2. run_weeks>3&3
        # 3. run_months_std<2&15
        list_date_pattern = r'^run_(days|weeks|months)(_std)?([<>]\d+)(&(\d+))?$'
        
        match = re.match(list_date_pattern, expr)
        if not match:
            raise ValueError(f"无效的日期列表表达式格式: {expr}")
        
        var_type = match.group(1)  # days, weeks, months
        is_std = match.group(2)  # _std 或 None
        count_direction = match.group(3)  # >3, <2
        day_str = match.group(5)  # 3, 13, 31 或 None
        
        # 确定格式类型
        fmt_type = "standard" if is_std else "compact"
        
        # 解析数量和方向
        direction = count_direction[0]  # > 或 <
        count = int(count_direction[1:])
        
        if var_type == "days":
            # 天列表
            return self._get_day_list(count, direction, fmt_type)
        elif var_type == "weeks":
            # 周列表
            target_weekday = int(day_str) if day_str else self.run_date.weekday() + 1
            return self._get_week_list(count, target_weekday, direction, fmt_type)
        else:  # months
            # 月列表
            target_day = int(day_str) if day_str else self.run_date.day
            return self._get_month_list(count, target_day, direction, fmt_type)
    
    def parse_date_expression(self, expr: str) -> Any:
        """
        解析日期表达式
        
        Args:
            expr: 日期表达式，可以是单个日期或日期列表
            
        Returns:
            Any: 解析结果，可能是字符串或日期列表字符串
        """
        try:
            # 先尝试解析为单个日期
            return self.get_single_date(expr)
        except ValueError:
            try:
                # 再尝试解析为日期列表
                return self.get_date_list(expr)
            except ValueError:
                # 都不是，返回None
                return None
    
    def get_all_date_variables(self) -> Dict[str, str]:
        """
        获取所有基础日期变量
        
        Returns:
            Dict[str, str]: 日期变量字典
        """
        return {
            # 基础日期
            "run_date": self.run_date_compact,
            "run_date_std": self.run_date_standard,
            
            # 周计算
            "run_week_begin": self.run_week_begin_compact,
            "run_week_begin_std": self.run_week_begin_standard,
            "run_week_end": self.run_week_end_compact,
            "run_week_end_std": self.run_week_end_standard,
            
            # 月计算
            "run_month_begin": self.run_month_begin_compact,
            "run_month_begin_std": self.run_month_begin_standard,
            "run_month_end": self.run_month_end_compact,
            "run_month_end_std": self.run_month_end_standard,
        }


class EnhancedDateFormatter:
    """
    增强的日期格式化器类
    
    支持渐进式文本替换，特别强化了日期处理功能：
    1. 支持普通变量替换：{variable}, {expression}, {variable:format}
    2. 支持日期变量替换：{run_date}, {run_week+3&3}, {run_weeks>3&3}等
    3. 支持渐进式替换：可以逐步设置变量
    4. 支持表达式计算：{len(items)}, {price * quantity}等
    
    主要特性：
    - 默认提供run_date变量（昨天日期）
    - 支持基于run_date的各种衍生计算
    - 支持日期运算和日期列表
    - 支持浮点数格式化、列表格式化等
    - 智能错误处理，计算失败时保留原始占位符
    
    使用示例：
    >>> formatter = EnhancedDateFormatter("商品：{goods}, 数量：{len(goods)}, 日期：{run_date_std}")
    >>> formatter.set(goods=["苹果", "香蕉", "橙子"])
    >>> print(formatter.format())
    商品：['苹果', '香蕉', '橙子'], 数量：3, 日期：2026-02-26
    """
    
    def __init__(self, template: str, default_run_date: Optional[str] = None):
        """
        初始化格式化器
        
        Args:
            template: 包含占位符的模板字符串
            default_run_date: 默认运行日期，格式同DateProcessor
        """
        self.template = template
        self.date_processor = DateProcessor(default_run_date)
        self.context = {}  # 存储用户设置的变量
        self.parsed_placeholders = self._parse_placeholders()
        
        # 初始化上下文中的日期变量
        self._init_date_variables()
    
    def _parse_placeholders(self) -> List[Dict[str, Any]]:
        """
        解析模板中的所有占位符
        
        Returns:
            List[Dict[str, Any]]: 占位符信息列表
        """
        pattern = r'\{([^}]+)\}'
        placeholders = []
        
        for match in re.finditer(pattern, self.template):
            placeholder = match.group(0)
            content = match.group(1)
            start, end = match.span()
            
            # 解析表达式和格式说明符
            expr_part, format_spec = self._parse_placeholder_content(content)
            
            placeholders.append({
                'full': placeholder,
                'content': content,
                'expr_part': expr_part,
                'format_spec': format_spec,
                'start': start,
                'end': end
            })
        
        return placeholders
    
    def _parse_placeholder_content(self, content: str) -> Tuple[str, str]:
        """
        解析占位符内容，分离表达式和格式说明符
        
        Args:
            content: 占位符内容
            
        Returns:
            Tuple[str, str]: (表达式部分, 格式说明符)
        """
        if ':' in content:
            parts = content.split(':', 1)
            expr_part = parts[0]
            format_spec = ':' + parts[1]
        else:
            expr_part = content
            format_spec = ''
        
        return expr_part, format_spec
    
    def _init_date_variables(self):
        """初始化上下文中的日期变量"""
        date_vars = self.date_processor.get_all_date_variables()
        self.context.update(date_vars)
    
    def _evaluate_expression(self, expr_part: str) -> Any:
        """
        计算表达式的值
        
        Args:
            expr_part: 表达式部分
            
        Returns:
            Any: 计算结果
        """
        # 先尝试作为日期表达式计算
        result = self.date_processor.parse_date_expression(expr_part)
        if result is not None:
            return result
        
        # 尝试作为Python表达式计算
        try:
            # 创建安全的命名空间
            namespace = {
                '__builtins__': {
                    'len': len,
                    'str': str,
                    'int': int,
                    'float': float,
                    'bool': bool,
                    'list': list,
                    'dict': dict,
                    'tuple': tuple,
                    'sum': sum,
                    'min': min,
                    'max': max,
                    'abs': abs,
                    'round': round,
                }
            }
            
            # 添加上下文变量
            namespace.update(self.context)
            
            # 编译并执行表达式
            code = compile(expr_part, '<string>', 'eval')
            result = eval(code, namespace)
            return result
            
        except Exception:
            # 如果计算失败，检查是否是简单变量
            if expr_part in self.context:
                return self.context[expr_part]
            else:
                # 返回原始表达式
                return f"{{{expr_part}}}"
    
    def set(self, **kwargs):
        """
        设置变量值
        
        Args:
            **kwargs: 变量名和值的键值对
            
        Returns:
            self: 支持链式调用
        """
        # 检查是否设置了run_date
        if 'run_date' in kwargs:
            # 更新日期处理器
            self.date_processor.set_run_date(kwargs['run_date'])
            # 重新初始化日期变量
            self._init_date_variables()
        
        # 更新上下文
        self.context.update(kwargs)
        return self
    
    def get(self, var_name: str, default: Any = None) -> Any:
        """
        获取变量值
        
        Args:
            var_name: 变量名
            default: 默认值
            
        Returns:
            Any: 变量值
        """
        return self.context.get(var_name, default)
    
    def clear(self, var_name: Optional[str] = None):
        """
        清除变量
        
        Args:
            var_name: 要清除的变量名，如果为None则清除所有变量
        """
        if var_name is None:
            self.context.clear()
            # 重置为默认日期
            self._init_date_variables()
        elif var_name in self.context:
            del self.context[var_name]
            
            # 如果删除的是run_date，重新初始化
            if var_name == 'run_date':
                self._init_date_variables()
    
    def format(self) -> str:
        """
        根据当前上下文格式化模板
        
        Returns:
            str: 格式化后的字符串
        """
        if not self.parsed_placeholders:
            return self.template
        
        result_parts = []
        last_pos = 0
        
        for placeholder in self.parsed_placeholders:
            # 添加占位符之前的文本
            result_parts.append(self.template[last_pos:placeholder['start']])
            
            try:
                # 计算表达式的值
                value = self._evaluate_expression(placeholder['expr_part'])
                
                # 将值转换为字符串
                value_str = self._value_to_string(value, placeholder['format_spec'])
                
                result_parts.append(value_str)
                
            except Exception as e:
                # 如果计算失败，保留原始占位符
                result_parts.append(placeholder['full'])
            
            last_pos = placeholder['end']
        
        # 添加最后一个占位符之后的文本
        result_parts.append(self.template[last_pos:])
        
        return ''.join(result_parts)
    
    def _value_to_string(self, value: Any, format_spec: str) -> str:
        """
        将值转换为字符串，应用格式说明符
        
        Args:
            value: 任意值
            format_spec: 格式说明符
            
        Returns:
            str: 格式化后的字符串
        """
        # 如果是字典或列表，转换为字符串
        if isinstance(value, dict):
            value_str = str(value)
        elif isinstance(value, list):
            # 处理中文逗号
            formatted_list = []
            for item in value:
                if isinstance(item, str) and '，' in item:
                    formatted_list.append(f'"{item}"')
                else:
                    formatted_list.append(str(item))
            value_str = f"[{', '.join(formatted_list)}]"
        elif hasattr(value, '__iter__') and not isinstance(value, str):
            value_str = str(list(value))
        else:
            value_str = str(value)
        
        # 应用格式说明符
        if format_spec:
            # 处理浮点数格式化
            if isinstance(value, (int, float)) and format_spec.startswith(':'):
                try:
                    # 移除开头的冒号
                    fmt = format_spec[1:]
                    # 构建格式字符串
                    if 'f' in fmt or 'e' in fmt or 'g' in fmt or 'E' in fmt or 'G' in fmt:
                        # 浮点数格式化
                        value_str = format(value, fmt)
                    elif 'd' in fmt or 'x' in fmt or 'o' in fmt or 'b' in fmt:
                        # 整数格式化
                        value_str = format(int(value), fmt)
                    else:
                        # 通用格式化
                        value_str = format(value, fmt)
                except (ValueError, TypeError):
                    # 如果格式化失败，使用原始值
                    pass
        
        return value_str
    
    def get_remaining_placeholders(self) -> List[str]:
        """
        获取尚未被替换的占位符列表
        
        Returns:
            List[str]: 未替换的占位符列表
        """
        remaining = []
        for placeholder in self.parsed_placeholders:
            try:
                value = self._evaluate_expression(placeholder['expr_part'])
                if isinstance(value, str) and value.startswith('{') and value.endswith('}'):
                    remaining.append(placeholder['full'])
            except Exception:
                remaining.append(placeholder['full'])
        return remaining
    
    def is_complete(self) -> bool:
        """
        检查是否所有占位符都已替换
        
        Returns:
            bool: 是否所有占位符都已替换
        """
        return len(self.get_remaining_placeholders()) == 0
    
    def __str__(self) -> str:
        """字符串表示，返回格式化后的文本"""
        return self.format()
    
    def __repr__(self) -> str:
        """对象表示"""
        return f"EnhancedDateFormatter(template={self.template!r}, run_date={self.date_processor.run_date_compact})"


# 使用示例
if __name__ == "__main__":
    print("=" * 60)
    print("EnhancedDateFormatter 使用示例")
    print("=" * 60)
    
    print("\n1. 基本使用示例:")
    print("-" * 40)
    
    formatter = EnhancedDateFormatter("""
run_date: {run_date}
run_date_std: {run_date_std}
run_week+3&3: {run_week+3&3}
run_week-3&5: {run_week-3&5}
run_month+3&13: {run_month+3&13}
run_month+2&31: {run_month+2&31}
run_month-3&1: {run_month-3&1}
run_month-3&31: {run_month-3&31}
run_week_std+3&3: {run_week_std+3&3}
run_month_std+2&31: {run_month_std+2&31}
""", default_run_date='20260227')

    print(formatter.format())
    
    print("\n2. 日期列表示例:")
    print("-" * 40)
    
    formatter2 = EnhancedDateFormatter("""
天列表（往后3天）: {run_days>3}
天列表（往前3天，标准格式）: {run_days_std<3}
周列表（往后3周，每周3）: {run_weeks>3&3}
周列表（往前3周，每周5，标准格式）: {run_weeks_std<3&5}
月列表（往后3月，每月13号）: {run_months>3&13}
月列表（往后3月，每月31号）: {run_months>3&31}
月列表（往前3月，每月1号）: {run_months<3&1}
月列表（往前3月，每月31号，标准格式）: {run_months_std<3&31}
""", default_run_date='20260227')
    
    result = formatter2.format()
    print(result)
    
    # 验证结果
    lines = result.strip().split('\n')
    for line in lines:
        if '周列表（往后3周，每周3）:' in line:
            expected = "'20260227'，'20260304'，'20260311'，'20260318'"
            actual = line.split(':')[1].strip()
            print(f"\n验证run_weeks>3&3:")
            print(f"预期: {expected}")
            print(f"实际: {actual}")
            print(f"是否正确: {actual == expected}")
    
    print("\n3. 综合示例（渐进式替换）:")
    print("-" * 40)
    
    raw_str = "商品：{goods} ,数量：{len(goods)} ,金额：{amt:.2f} ,支用日期：{run_date_std} ,结清日期：{run_date_std+15}"
    fmt = EnhancedDateFormatter(raw_str, default_run_date='20260227')
    
    print("初始状态:")
    print(fmt.format())
    print()
    
    fmt.set(goods=["a", "b"])
    print("设置goods后:")
    print(fmt.format())
    print()
    
    fmt.set(run_date='20260309')
    print("设置run_date为'20260309'后:")
    print(fmt.format())
    print()
    
    fmt.set(amt=17.1)
    print("设置amt后:")
    print(fmt.format())
    print()
    
    fmt.set(amt=12.3, run_date='2026-09-03')
    print("设置amt和run_date为'2026-09-03'后:")
    print(fmt.format())
    print()
    
    print("4. SQL查询示例:")
    print("-" * 40)
    
    sql_template = """
-- 近7天数据
SELECT * FROM sales 
WHERE ds >= '{run_days_std<6}'
  AND ds <= '{run_date_std}'
  AND channel = '电商'

-- 近4周数据（每周一）
UNION ALL
SELECT * FROM sales 
WHERE ds IN ({run_weeks_std<4&1})
  AND channel = '门店'

-- 近3个月数据（每月最后一天）
UNION ALL
SELECT * FROM sales 
WHERE ds IN ({run_months_std<3&31})
  AND channel = '批发'
"""
    
    formatter4 = EnhancedDateFormatter(sql_template, default_run_date='20260227')
    print(formatter4.format())
    
    print("\n5. 获取剩余占位符:")
    print("-" * 40)
    
    formatter5 = EnhancedDateFormatter("姓名: {name}, 年龄: {age}, 日期: {run_date_std}")
    formatter5.set(name="张三", run_date='2024-01-01')
    print("格式化结果:", formatter5.format())
    print("剩余占位符:", formatter5.get_remaining_placeholders())
    print("是否完整:", formatter5.is_complete())