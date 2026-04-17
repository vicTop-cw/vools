#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试vools模块的功能
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools import vicTools, vicDate, vicText, vicList, Seq, NONE

# 测试vicTools
print("=== 测试 vicTools ===")
try:
    # 测试transfer装饰器
    @vicTools.transfer
    def test_transfer():
        return "test"
    result = test_transfer()
    print(f"vicTools.transfer 测试: {result}, 类型: {type(result)}")
    
    # 测试split函数
    test_str = "a,b;c.d"
    result = vicTools.split(test_str, [",", ";", "."])
    print(f"vicTools.split 测试: {result}")
    
    # 测试regexp_replace函数
    test_str = "Hello 123 World"
    result = vicTools.regexp_replace(r"\d+", test_str, "456")
    print(f"vicTools.regexp_replace 测试: {result}")
    
    print("vicTools 测试通过!")
except Exception as e:
    print(f"vicTools 测试失败: {e}")

# 测试vicDate
print("\n=== 测试 vicDate ===")
try:
    # 测试创建日期对象
    date1 = vicDate()
    print(f"vicDate() 测试: {date1}")
    
    date2 = vicDate("20240101")
    print(f"vicDate('20240101') 测试: {date2}")
    
    date3 = vicDate("2024-01-01 12:00:00")
    print(f"vicDate('2024-01-01 12:00:00') 测试: {date3}")
    
    # 测试日期运算
    date4 = date2 + 1
    print(f"日期加法测试: {date2} + 1 = {date4}")
    
    date5 = date2 - 1
    print(f"日期减法测试: {date2} - 1 = {date5}")
    
    # 测试日期格式转换
    print(f"日期格式化测试: {date2.toString('yyyy-MM-dd')}")
    
    print("vicDate 测试通过!")
except Exception as e:
    print(f"vicDate 测试失败: {e}")

# 测试vicText
print("\n=== 测试 vicText ===")
try:
    # 测试创建文本对象
    text1 = vicText("Hello World")
    print(f"vicText('Hello World') 测试: {text1}")
    
    # 测试字符串方法
    print(f"upper() 测试: {text1.upper()}")
    print(f"lower() 测试: {text1.lower()}")
    
    # 测试正则表达式方法
    text2 = vicText("Hello 123 World 456")
    result = text2.regexp_findall(r"\d+")
    print(f"regexp_findall 测试: {result}")
    
    # 测试split方法
    text3 = vicText("a,b,c")
    result = text3.split(",")
    print(f"split 测试: {result}")
    
    print("vicText 测试通过!")
except Exception as e:
    print(f"vicText 测试失败: {e}")

# 测试vicList
print("\n=== 测试 vicList ===")
try:
    # 测试创建列表对象
    lst1 = vicList([1, 2, 3, 4, 5])
    print(f"vicList([1, 2, 3, 4, 5]) 测试: {lst1}")
    
    # 测试类型检查
    print(f"isinstance(lst1, list) 测试: {isinstance(lst1, list)}")
    print(f"type(lst1) 测试: {type(lst1)}")
    
    # 测试即时执行特性
    print("即时执行测试:")
    lst2 = vicList([1, 2, 3, 4, 5])
    result = lst2.map(lambda x: x * 2)
    print(f"map(lambda x: x * 2) 结果: {result}")
    print(f"map 结果类型: {type(result)}")
    
    # 测试filter方法
    result = lst1.filter(lambda x: x > 2)
    print(f"filter(lambda x: x > 2) 结果: {result}")
    
    # 测试切片
    result = lst1[1:4]
    print(f"切片测试 [1:4]: {result}")
    
    # 测试数学运算
    lst3 = vicList([1, 2, 3])
    lst4 = vicList([3, 4, 5])
    print(f"交集测试: {lst3 & lst4}")
    print(f"并集测试: {lst3 | lst4}")
    print(f"差集测试: {lst3 - lst4}")
    
    # 测试其他方法
    print(f"unique 测试: {vicList([1, 2, 2, 3, 3, 3]).unique}")
    print(f"take(2) 测试: {lst1.take(2)}")
    print(f"prepend(0) 测试: {lst1.prepend(0)}")
    print(f"tail(2) 测试: {lst1.tail(2)}")
    
    print("vicList 测试通过!")
except Exception as e:
    print(f"vicList 测试失败: {e}")

# 测试与Seq的兼容性
print("\n=== 测试与Seq的兼容性 ===")
try:
    # 测试Seq的基本功能
    seq = Seq([1, 2, 3, 4, 5])
    result = seq.map(lambda x: x * 2).filter(lambda x: x > 5).collect()
    print(f"Seq 测试: {result}")
    
    # 测试vicList继承自Seq
    print(f"issubclass(vicList, Seq) 测试: {issubclass(vicList, Seq)}")
    
    print("与Seq的兼容性测试通过!")
except Exception as e:
    print(f"与Seq的兼容性测试失败: {e}")

print("\n所有测试完成!")
