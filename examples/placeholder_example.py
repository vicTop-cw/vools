"""
X / Y / Z 占位符工具使用示例

展示三种占位符在实际场景中的用法：
- X: 方括号终止，适合一次性数据流水线
- Y: 关键字参数终止，适合可读性优先的场景
- Z: 惰性表达式编译，适合需要序列化/传输/复用的场景
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.functional.placeholder_impl import X, Y, Z, expr_to_dict, expr_from_dict


# ============================================================
# 示例 1: X — 数据清洗管道
# ============================================================
def example_x_data_cleaning():
    """使用 X 构建一次性数据清洗管道"""
    print("=" * 50)
    print("示例 1: X — 数据清洗管道")
    print("=" * 50)

    # 场景：清洗用户输入的姓名
    raw_names = ['  Alice  ', 'BOB', '  charlie  ', '  DAVID  ']

    # X 管道：strip → lower → capitalize
    clean = X.strip().lower().capitalize()

    for name in raw_names:
        print(f"  {name!r:20s} → {clean[name]!r}")

    # 场景：提取 CSV 的特定列
    csv_data = ['name,age,city', 'Alice,30,Beijing', 'Bob,25,Shanghai']

    # 跳过表头，取第 2 列（age）
    get_age = X.split(',')[None, 1]
    for row in csv_data[1:]:
        print(f"  {row:25s} → age={get_age[row]}")


# ============================================================
# 示例 2: X — 嵌套数据提取
# ============================================================
def example_x_nested_data():
    """使用 X 提取嵌套数据结构"""
    print("\n" + "=" * 50)
    print("示例 2: X — 嵌套数据提取")
    print("=" * 50)

    data = {
        'users': [
            {'name': 'Alice', 'profile': {'age': 30, 'city': 'Beijing'}},
            {'name': 'Bob', 'profile': {'age': 25, 'city': 'Shanghai'}},
            {'name': 'Charlie', 'profile': {'age': 35, 'city': 'Shenzhen'}},
        ]
    }

    # 提取 users 列表
    get_users = X['users']
    users = get_users[data]
    print(f"  共 {len(users)} 个用户")

    # 提取第一个用户的 name（使用 [None, idx] 追加索引）
    get_first_name = X['users'][None, 0][None, 'name']
    print(f"  第一个用户: {get_first_name[data]}")

    # 提取所有用户的 city（使用 [None, idx] 追加索引构建管道）
    get_city = X['profile'][None, 'city'].as_function()
    cities = [get_city(u) for u in users]
    print(f"  城市列表: {cities}")

    # X 也可以转为函数复用
    get_age = X['profile'][None, 'age'].as_function()
    ages = [get_age(u) for u in users]
    print(f"  年龄列表: {ages}")


# ============================================================
# 示例 3: Y — 可读性优先的数据处理
# ============================================================
def example_y_readable_pipeline():
    """使用 Y 构建可读的数据处理管道"""
    print("\n" + "=" * 50)
    print("示例 3: Y — 可读性优先")
    print("=" * 50)

    text = '  hello,world,foo  '

    # Y 的执行语义更接近普通函数调用
    result = Y.strip().split(',')('  hello,world,foo  ', exe=True)
    print(f"  strip → split: {result}")

    # 带工厂函数
    result = Y.strip().split(',')('  hello,world,foo  ', exe=True, f=tuple)
    print(f"  strip → split → tuple: {result}")

    # Y 也可以转为函数复用
    process = Y.strip().upper().split(',').as_function()
    print(f"  复用管道: {process('  a , B , c  ')}")

    # 下标执行器 — 用 [] 方式执行 Y 管道
    sub = Y.strip().split(',').as_subscript()
    print(f"  下标执行: {sub['  x , y , z  ']}")


# ============================================================
# 示例 4: Z — 表达式编译与复用
# ============================================================
def example_z_expression_compilation():
    """使用 Z 构建可编译复用的表达式"""
    print("\n" + "=" * 50)
    print("示例 4: Z — 表达式编译")
    print("=" * 50)

    # 构建表达式树（不执行）
    expr = Z.strip().upper()[:5]

    # 编译为函数
    pipeline = expr.as_function()

    # 重复使用
    test_strings = ['  hello world  ', '  python  ', '  abcdefghij  ']
    for s in test_strings:
        print(f"  {s!r:20s} → {pipeline(s)!r}")


# ============================================================
# 示例 5: Z — JSON 序列化传输表达式
# ============================================================
def example_z_serialization():
    """使用 Z 序列化表达式，实现跨进程/跨网络传输"""
    print("\n" + "=" * 50)
    print("示例 5: Z — 表达式序列化传输")
    print("=" * 50)

    # 定义数据处理规则
    rule = Z.strip().split(',')[0].upper()

    # 序列化为 JSON
    rule_json = json.dumps(expr_to_dict(rule), ensure_ascii=False, indent=2)
    print(f"  序列化后的规则:\n{rule_json}")

    # 模拟传输到另一端后反序列化
    received = expr_from_dict(json.loads(rule_json))
    processor = received.as_function()

    # 在另一端执行
    print(f"  processor('  hello,world  ') = {processor('  hello,world  ')!r}")


# ============================================================
# 示例 6: Z — 复杂表达式：多参数 + 解包
# ============================================================
def example_z_complex_expressions():
    """使用 Z 构建复杂的多参数表达式"""
    print("\n" + "=" * 50)
    print("示例 6: Z — 复杂表达式")
    print("=" * 50)

    # 两个参数的表达式
    adder = (Z + Z).as_function()
    print(f"  adder(3, 5) = {adder(3, 5)}")

    # 方法链 + 多参数
    f = (Z.strip().split(Z)).as_function()
    print(f"  split('a|b|c', '|') = {f('a|b|c', '|')}")

    # *args 解包
    apply_fn = (Z.invoke(Z.star)).as_function()

    def sum_three(a, b, c):
        return a + b + c
    print(f"  invoke(sum_three, [1,2,3]) = {apply_fn(sum_three, [1, 2, 3])}")

    # 可变参数
    first_two_sum = (Z.args_all[0] + Z.args_all[1]).as_function()
    print(f"  first_two_sum(10, 20) = {first_two_sum(10, 20)}")
    print(f"  first_two_sum(10, 20, 30, 40) = {first_two_sum(10, 20, 30, 40)}")


# ============================================================
# 示例 7: 三者的对比
# ============================================================
def example_comparison():
    """X / Y / Z 三种风格的对比"""
    print("\n" + "=" * 50)
    print("示例 7: X / Y / Z 风格对比")
    print("=" * 50)

    data = '  hello,world  '

    # X 风格：方括号终止
    result_x = X.strip().split(',')['  hello,world  ']
    print(f"  X 风格: X.strip().split(',')['...'] = {result_x}")

    # Y 风格：关键字参数终止
    result_y = Y.strip().split(',')('  hello,world  ', exe=True)
    print(f"  Y 风格: Y.strip().split(',')(..., exe=True) = {result_y}")

    # Z 风格：编译后调用
    pipeline = (Z.strip().split(',')).as_function()
    result_z = pipeline(data)
    print(f"  Z 风格: (Z...).as_function()(...) = {result_z}")

    print("\n  选择指南:")
    print("  - 一次性流水线，追求简洁    → X")
    print("  - 需要可读的函数调用语义    → Y")
    print("  - 表达式需要复用/序列化/传输 → Z")


# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':
    example_x_data_cleaning()
    example_x_nested_data()
    example_y_readable_pipeline()
    example_z_expression_compilation()
    example_z_serialization()
    example_z_complex_expressions()
    example_comparison()
