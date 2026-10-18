# -*- coding: utf-8 -*-
"""strip_margin 方法测试"""

import os
import sys

# 由本文件位置反推仓库根，避免硬编码绝对路径（可在别的机器/CI 直接跑）
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)

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


# ============================================================
# BUG-88: _safe_path 前缀检查可被 ../ 旁路
# 旧代码 `normalized.startswith(base_dir)` 允许访问前缀匹配的兄弟目录
# ============================================================
import pytest
import tempfile
import shutil


@pytest.fixture
def _safe_path_env():
    """创建隔离的临时目录结构用于路径遍历测试"""
    td = tempfile.mkdtemp()
    base_dir = os.path.join(td, 'root')
    os.makedirs(base_dir)
    # 创建前缀匹配的兄弟目录（旧代码可绕过检查）
    evil_dir = os.path.join(td, 'root_sibling')
    os.makedirs(evil_dir)
    with open(os.path.join(evil_dir, 'secret.txt'), 'w') as f:
        f.write('TOP SECRET')
    yield td, base_dir, evil_dir
    shutil.rmtree(td, ignore_errors=True)


def test_safe_path_normal_access(_safe_path_env):
    """正常相对路径应该解析成功"""
    td, base_dir, _ = _safe_path_env
    result = VText._safe_path('file.txt', base_dir=base_dir)
    assert os.path.isabs(result)
    assert os.path.normpath(result).startswith(os.path.normpath(base_dir))


def test_safe_path_same_dir(_safe_path_env):
    """base_dir 自身应该允许访问"""
    td, base_dir, _ = _safe_path_env
    result = VText._safe_path('.', base_dir=base_dir)
    assert result == os.path.normpath(base_dir)


def test_safe_path_normal_subdir(_safe_path_env):
    """正常子目录应该允许访问"""
    td, base_dir, _ = _safe_path_env
    sub = os.path.join(base_dir, 'sub')
    os.makedirs(sub, exist_ok=True)
    result = VText._safe_path('sub/file.txt', base_dir=base_dir)
    assert result.startswith(os.path.normpath(base_dir) + os.sep)


def test_safe_path_sibling_traversal_blocked(_safe_path_env):
    """BUG-88: ../root_sibling/... 前缀匹配旁路应该被阻止"""
    td, base_dir, _ = _safe_path_env
    with pytest.raises(ValueError, match="不允许访问"):
        VText._safe_path('../root_sibling/secret.txt', base_dir=base_dir)


def test_safe_path_parent_traversal_blocked(_safe_path_env):
    """BUG-88: 向上穿越到父目录应该被阻止"""
    td, base_dir, _ = _safe_path_env
    with pytest.raises(ValueError, match="不允许访问"):
        VText._safe_path('../etc/passwd', base_dir=base_dir)


def test_safe_path_deep_traversal_blocked(_safe_path_env):
    """BUG-88: 多重 ../ 穿越应该被阻止"""
    td, base_dir, _ = _safe_path_env
    with pytest.raises(ValueError, match="不允许访问"):
        VText._safe_path('../../../etc/passwd', base_dir=base_dir)


def test_safe_path_absolute_opt_in(_safe_path_env):
    """显式绝对路径直通（设计如此，不是漏洞）"""
    td, base_dir, evil_dir = _safe_path_env
    result = VText._safe_path(os.path.join(evil_dir, 'secret.txt'))
    assert os.path.isabs(result)


def test_safe_path_file_uri(_safe_path_env):
    """file:// URI 格式应该正确解析"""
    td, base_dir, _ = _safe_path_env
    uri = 'file://' + os.path.join(base_dir, 'x.txt')
    result = VText._safe_path(uri)
    assert result == os.path.normpath(os.path.join(base_dir, 'x.txt'))


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