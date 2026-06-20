"""辅助函数，供 test_serialize.py 的 pickle 往返测试使用。

定义在此模块中的函数可以被 pickle 正确序列化，
因为 pickle 按模块路径定位函数，tests 包下的文件可作为标准 Python 模块导入。
"""


def noop():
    """空操作函数，用于测试 Selector/Overloads 等需要可调用对象的场景。"""
    return None


def add_three(a, b, c=0):
    """三参数加法，用于测试 Stuff 等需要简单函数的场景。"""
    return a + b + c
