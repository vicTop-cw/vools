#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试vools模块的功能
"""
from vools import vicTools, vicDate, vicText, vicList, VList, VText, VDate, Seq, NONE

# 测试vicTools
print("=== 测试 vicTools ===")
try:
    # 测试transfer装饰器
    @vicTools.transfer
    def transfer_func():
        return "test"
    result = transfer_func()
    print(f"vicTools.transfer 测试: {result}, 类型: {type(result)}")
    assert result is not None
    assert isinstance(result, vicText)
    
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
    
    # 测试正则表达式方法 (使用 vicTools)
    text2 = vicText("Hello 123 World 456")
    result = vicTools.regexp_findall(r"\d+", str(text2))
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



print("\n=== 测试vicText ===")
today =vicText("{run_date_std+1}").formatEx()
print(today)
txt1 = vicText(r"""
更新上下文变量：{name <- "张三" ; age <- 30 ; city <- "北京; other_var <- ",".join([for str(i) in range(age)]) }
我是 {name} ，我今年 {age} 岁, 我来自 {city}, 今天是 {date},那天是 {run_date}
西瓜：{xigua_price}
香蕉：{banana_price}
凤梨：{fenli_price}
牛油果：{niuyou_price}
总计：{xigua_price+banana_price+fenli_price+niuyou_price}

循环：{','.join([str(i) for i in range(age) if i % 5 == 0])}


{other_var}
""")
print("raw:", txt1)
txt2 = txt1.formatEx(name="张三").formatEx(age=30,range=range).formatEx(city="北京").formatEx(date="{run_date_std+33}").formatEx()
print("formatted:", txt2)
txt3 = txt2.formatEx(xigua_price=100,banana_price=200,fenli_price=300,niuyou_price=400)
print("formatted:", txt3)





print("\n所有测试完成!")
