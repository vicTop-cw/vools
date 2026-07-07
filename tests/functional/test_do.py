from vools import vicText, vicDate, vicList, VText, VDate, VList

# 测试 vicText.do()
print("=== 测试 vicText.do() ===")
text = vicText("hello world")
result = text.do(lambda x: x.upper())
print(f"原始文本: {text}")
print(f"do 返回值: {result}")
print(f"是否返回 self: {result is text}")

# 测试 vicText.do() 带 pre_f 和 sub_f
print("\n=== 测试 vicText.do() 带 pre_f 和 sub_f ===")
text2 = vicText("test")
result2 = text2.do(
    f=lambda x: len(x),
    pre_f=lambda x: x.upper(),
    sub_f=lambda x: print(f"sub_f 执行: 长度是 {x}")
)
print(f"do 返回值: {result2}")
print(f"是否返回 self: {result2 is text2}")

# 测试 vicDate.do()
print("\n=== 测试 vicDate.do() ===")
date = vicDate()
result3 = date.do(lambda x: x.strftime('%Y-%m-%d'))
print(f"原始日期: {date}")
print(f"do 返回值: {result3}")

# 测试 vicList.do()
print("\n=== 测试 vicList.do() ===")
lst = vicList([1, 2, 3, 4, 5])
result4 = lst.do(lambda x: sum(x))
print(f"原始列表: {list(lst)}")
print(f"do 返回值: {result4}")
print(f"是否返回 self: {result4 is lst}")

print("\n所有测试完成!")
