# -*- coding: utf-8 -*-
"""strip_margin 方法测试"""

import sys
sys.path.insert(0, r'E:\IDEProjects\AI\vools')

from vools.data.vtext import VText


# ============================================================
# 规则1: | 开头 → 仅掐头
# ============================================================
def test_rule1_pipe():
    text = VText("""\
|hello
|  world
  |  indented""")
    result = text.strip_margin()
    print("=== 规则1: | 仅掐头 ===")
    print(repr(result))
    assert result == "hello\n  world\n  indented", f"Failed: {repr(result)}"


# ============================================================
# 规则2: #| 开头 → 整行丢弃
# ============================================================
def test_rule2_hash_pipe():
    text = VText("""\
|keep this
#| this is a comment, should be removed
|keep this too""")
    result = text.strip_margin()
    print("\n=== 规则2: #| 整行丢弃 ===")
    print(repr(result))
    assert result == "keep this\nkeep this too", f"Failed: {repr(result)}"


# ============================================================
# 规则3: $| 开头 → 掐头 + formatEx 多次直到收敛
# ============================================================
def test_rule3_dollar_pipe():
    text = VText("""\
$|hello {name}
$|no format here""")
    result = text.strip_margin(name="World")
    print("\n=== 规则3: $| 掐头 + formatEx ===")
    print(repr(result))
    assert result == "hello World\nno format here", f"Failed: {repr(result)}"


# ============================================================
# 规则4: $\d+| 开头 → 掐头 + n 空格缩进 + formatEx
# ============================================================
def test_rule4_dollar_indent():
    text = VText("""\
$|def greet({name}):
$4|print(f\"Hello, {name}\")
$4|return 42
$|# end""")
    result = text.strip_margin(name="user")
    print("\n=== 规则4: $digit+| 缩进生成 Python 代码 ===")
    print(result)
    assert result == 'def greet(user):\n    print(f"Hello, user")\n    return 42\n# end', \
        f"Failed: {repr(result)}"


# ============================================================
# 规则5: 不匹配任何规则 → 原样返回
# ============================================================
def test_rule5_plain():
    text = VText("""\
plain line
  another plain line""")
    result = text.strip_margin()
    print("\n=== 规则5: 原样返回 ===")
    print(repr(result))
    assert result == "plain line\n  another plain line", f"Failed: {repr(result)}"


# ============================================================
# 综合: 生成完整的 Python 代码
# ============================================================
def test_generate_python_code():
    text = VText("""\
#| 这是注释，会被丢弃
$|class {class_name}:
$4|def __init__(self, name):
$8|self.name = name
$4|
$4|def greet(self):
$8|return f\"Hello, {self.name}!\"
$|
$|if __name__ == \"__main__\":
$4|obj = {class_name}(\"{instance_name}\")
$4|print(obj.greet())""")
    result = text.strip_margin(class_name="Person", instance_name="Alice")
    print("\n=== 综合: 生成 Python 类 ===")
    print(result)
    print("\n--- 执行生成的代码 ---")
    exec(result)


# ============================================================
# 综合: 生成 Nim 代码
# ============================================================
def test_generate_nim_code():
    text = VText("""\
#| Nim 示例
$|type
$4|{type_name} = object
$8|name: string
$8|age: int
$|
$|proc greet(self: {type_name}): string =
$4|result = \"Hello, \" & self.name""")
    result = text.strip_margin(type_name="Person")
    print("\n=== 综合: 生成 Nim 代码 ===")
    print(result)


# ============================================================
# 多重缩进 + 嵌套 formatEx
# ============================================================
def test_compound_indent():
    text = VText("""\
$|def outer():
$4|{inner_var} = 1
$4|if {inner_var} > 0:
$8|print(\"positive\")
$8|{inner_var} += 1
$4|return {inner_var}""")
    result = text.strip_margin(inner_var="x")
    print("\n=== 多重缩进 ===")
    print(result)
    expected = "def outer():\n    x = 1\n    if x > 0:\n        print(\"positive\")\n        x += 1\n    return x"
    assert result == expected, f"Failed:\n{result}\n!=\n{expected}"


if __name__ == '__main__':
    test_rule1_pipe()
    test_rule2_hash_pipe()
    test_rule3_dollar_pipe()
    test_rule4_dollar_indent()
    test_rule5_plain()
    test_compound_indent()
    test_generate_python_code()
    test_generate_nim_code()
    print("\n 全部测试通过!")