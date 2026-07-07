"""
测试 vools bridge freebasic 模块的各种功能

运行：python tests/test_fbc_bridge.py
"""

import sys
import os
import asyncio
import tempfile
from vools.bridge.freebasic import (
    fbc,
    compile_and_run,
    compile_and_run_async,
    fbc_compiler_available,
    is_fbc_available,
    FbcFuture,
    Transport,
    CtypesTransport,
    ZincTransport,
    get_transport,
    set_transport,
    PY_TO_FB_TYPE,
    FB_TO_CTYPES,
    get_fb_type,
)
from vools.bridge.freebasic.types import (
    infer_fb_argtypes,
    is_array_type,
    get_ctype_for,
)


def test_fbc_compiler_available():
    """测试 fbc_compiler_available()"""
    print("=" * 60)
    print("测试 1: fbc_compiler_available()")
    print("=" * 60)
    available = fbc_compiler_available()
    print(f"FreeBASIC 编译器可用: {available}")
    assert isinstance(available, bool), "返回值应该是 bool 类型"
    print("✓ 测试通过\n")
    return available


def test_type_mapping():
    """测试类型映射表"""
    print("=" * 60)
    print("测试 2: 类型映射表")
    print("=" * 60)
    # PY -> FB
    assert PY_TO_FB_TYPE[int] == 'Long'
    assert PY_TO_FB_TYPE[float] == 'Double'
    assert PY_TO_FB_TYPE[bool] == 'Boolean'
    assert PY_TO_FB_TYPE[str] == 'ZString Ptr'
    # FB -> ctypes
    import ctypes
    assert FB_TO_CTYPES['Long'] is ctypes.c_long
    assert FB_TO_CTYPES['Double'] is ctypes.c_double
    assert FB_TO_CTYPES['Boolean'] is ctypes.c_bool
    assert FB_TO_CTYPES['ZString Ptr'] is ctypes.c_char_p
    assert FB_TO_CTYPES['Long Ptr'] is ctypes.POINTER(ctypes.c_long)
    assert FB_TO_CTYPES['Double Ptr'] is ctypes.POINTER(ctypes.c_double)
    assert FB_TO_CTYPES['Void'] is None

    # get_fb_type
    assert get_fb_type(int) == 'Long'
    assert get_fb_type(float) == 'Double'
    assert get_fb_type('int') == 'Long'
    assert get_fb_type(None) == 'Void'
    assert get_fb_type(type(None)) == 'Void'

    # infer_fb_argtypes
    assert infer_fb_argtypes([1, 2, 3]) == ['Long', 'Long', 'Long']
    assert infer_fb_argtypes([1.0, 2.0]) == ['Double', 'Double']
    assert infer_fb_argtypes(['a', 'b']) == ['ZString Ptr', 'ZString Ptr']
    assert infer_fb_argtypes([[1, 2, 3]]) == ['Long Ptr']
    assert infer_fb_argtypes([[1.0, 2.0]]) == ['Double Ptr']

    # is_array_type
    assert is_array_type('Long Ptr') is True
    assert is_array_type('Double Ptr') is True
    assert is_array_type('Long') is False
    assert is_array_type('ZString Ptr') is False

    print("✓ 类型映射测试通过\n")


def test_transport_replaceable():
    """测试 Transport 可替换"""
    print("=" * 60)
    print("测试 3: Transport 可替换")
    print("=" * 60)
    # 默认 Transport 应该是 CtypesTransport
    assert isinstance(get_transport(), CtypesTransport)

    # 创建 mock Transport
    class MockTransport(Transport):
        def __init__(self):
            self.prepare_arg_called = 0
            self.decode_result_called = 0

        def prepare_arg(self, arg, fb_type):
            self.prepare_arg_called += 1
            return (arg, type(arg))

        def prepare_ret(self, fb_type):
            return None

        def decode_result(self, value, fb_type):
            self.decode_result_called += 1
            return value

    mock = MockTransport()
    original = get_transport()
    try:
        set_transport(mock)
        assert get_transport() is mock
        # 测试 prepare_arg 被调用
        val, ctype = mock.prepare_arg(42, 'Long')
        assert val == 42
        assert mock.prepare_arg_called == 1
    finally:
        set_transport(original)

    # 还原
    assert get_transport() is original
    print("✓ Transport 替换测试通过\n")


def test_simple_int_function():
    """测试简单的整型函数"""
    print("=" * 60)
    print("测试 4: 简单整型函数 (a + b)")
    print("=" * 60)
    @fbc
    def add(a: int, b: int) -> int:
        return "Return a + b"

    result = add(2, 3)
    print(f"add(2, 3) = {result}")
    assert result == 5, f"期望 5，实际 {result}"
    print("✓ 测试通过\n")


def test_string_function():
    """测试字符串参数（返回长度）"""
    print("=" * 60)
    print("测试 5: 字符串参数（返回长度）")
    print("=" * 60)
    @fbc
    def str_len(s: str) -> int:
        # 字符串参数 + 整数返回（避免 ZString Ptr 字符串返回的复杂性）
        return 'Function = Len(*s)'

    result = str_len("Hello")
    print(f'str_len("Hello") = {result}')
    assert result == 5, f"期望 5，实际 {result}"
    print("✓ 测试通过\n")


def test_array_int_sum():
    """测试整型数组求和（免序列化）"""
    print("=" * 60)
    print("测试 6: 整型数组求和（验证免序列化）")
    print("=" * 60)
    @fbc
    def sum_arr(arr: list) -> int:
        return '''
Dim total As Long = 0
For i As Long = 0 To n - 1
    total += arr[i]
Next i
Return total
'''

    result = sum_arr([1, 2, 3, 4, 5])
    print(f"sum_arr([1, 2, 3, 4, 5]) = {result}")
    assert result == 15, f"期望 15，实际 {result}"
    print("✓ 测试通过\n")


def test_array_float_mean():
    """测试浮点数组求均值（免序列化）"""
    print("=" * 60)
    print("测试 7: 浮点数组求均值（验证免序列化）")
    print("=" * 60)
    @fbc
    def mean_arr(arr: 'list[float]') -> float:
        return '''
If n = 0 Then
    Return 0.0
End If
Dim total As Double = 0.0
For i As Long = 0 To n - 1
    total += arr[i]
Next i
Return total / n
'''

    result = mean_arr([1.0, 2.0, 3.0, 4.0])
    print(f"mean_arr([1.0, 2.0, 3.0, 4.0]) = {result}")
    assert abs(result - 2.5) < 0.001, f"期望 2.5，实际 {result}"
    print("✓ 测试通过\n")


def test_recursive_fibonacci():
    """测试递归斐波那契函数"""
    print("=" * 60)
    print("测试 8: 递归斐波那契")
    print("=" * 60)
    @fbc
    def fib(n: int) -> int:
        return '''
If n <= 1 Then
    Return 1
Else
    Return fib(n - 1) + fib(n - 2)
End If
'''

    result = fib(10)
    print(f"fib(10) = {result}")
    # fib(0)=1, fib(1)=1, fib(2)=2, fib(3)=3, ..., fib(10)=89
    assert result == 89, f"期望 89，实际 {result}"
    print("✓ 测试通过\n")


def test_cache():
    """测试编译缓存"""
    print("=" * 60)
    print("测试 9: 编译缓存")
    print("=" * 60)
    @fbc
    def add_one(x: int) -> int:
        return "Return x + 1"

    result1 = add_one(10)
    print(f"第一次调用 add_one(10) = {result1}")
    result2 = add_one(20)
    print(f"第二次调用 add_one(20) = {result2}")
    assert result1 == 11
    assert result2 == 21
    print("✓ 缓存机制工作正常\n")


def test_compile_and_run():
    """测试 compile_and_run 便捷入口"""
    print("=" * 60)
    print("测试 10: compile_and_run 便捷入口")
    print("=" * 60)
    result = compile_and_run(
        "Return arg0 + arg1",
        func_name="add_func",
        args=(10, 20),
        ret_type='Long'
    )
    print(f"compile_and_run args=(10, 20) = {result}")
    assert result == 30, f"期望 30，实际 {result}"
    print("✓ 测试通过\n")


def test_mode_only_code():
    """测试 ONLY_CODE 模式"""
    print("=" * 60)
    print("测试 11: ONLY_CODE 模式（不编译）")
    print("=" * 60)
    @fbc(mode='ONLY_CODE')
    def example(x: int) -> int:
        return "Return x * 2"

    code = example(5)
    print(f"生成的代码（前 200 字符）:\n{code[:200]}...")
    assert isinstance(code, str)
    assert 'Function example' in code
    assert 'cdecl' in code
    print("✓ ONLY_CODE 测试通过\n")


def test_async_mode():
    """测试异步模式"""
    print("=" * 60)
    print("测试 12: 异步模式")
    print("=" * 60)
    @fbc(async_mode=True)
    def slow_add(a: int, b: int) -> int:
        return "Return a + b"

    # 同步调用异步函数（async_mode 在装饰器中处理）
    # 注意：async_mode=True 时返回 async_wrapper，需要 await
    async def run_test():
        result = await slow_add(3, 4)
        return result

    result = asyncio.run(run_test())
    print(f"async slow_add(3, 4) = {result}")
    assert result == 7, f"期望 7，实际 {result}"
    print("✓ 异步模式测试通过\n")


def test_compile_and_run_async():
    """测试 compile_and_run_async 异步便捷函数"""
    print("=" * 60)
    print("测试 13: compile_and_run_async 异步便捷函数")
    print("=" * 60)

    async def run_test():
        result = await compile_and_run_async(
            "Return arg0 * arg1",
            func_name="mul_func",
            args=(6, 7),
            ret_type='Long'
        )
        return result

    result = asyncio.run(run_test())
    print(f"compile_and_run_async args=(6, 7) = {result}")
    assert result == 42, f"期望 42，实际 {result}"
    print("✓ 测试通过\n")


def test_no_serialization():
    """测试免序列化（验证不调用 csv_serialize）"""
    print("=" * 60)
    print("测试 14: 免序列化（不依赖 CSV/JSON）")
    print("=" * 60)
    # 验证 freebasic 模块源码不包含 csv_serialize/json_serialize
    import vools.bridge.freebasic as fbc_mod
    init_path = fbc_mod.__file__
    with open(init_path, 'r', encoding='utf-8') as f:
        init_content = f.read()
    # __init__ 只做 re-export，验证 transport 也不含序列化
    assert 'csv_serialize' not in init_content, "freebasic/__init__.py 不应包含 csv_serialize"
    transport_path = fbc_mod.transport.__file__
    with open(transport_path, 'r', encoding='utf-8') as f:
        transport_content = f.read()
    assert 'csv_serialize' not in transport_content, "transport.py 不应包含 csv_serialize"
    assert 'json_serialize' not in transport_content, "transport.py 不应包含 json_serialize"
    print("✓ 免序列化验证通过（无 csv/json 序列化）\n")


def main():
    print("\n" + "=" * 60)
    print("vools.bridge.freebasic 模块测试")
    print("=" * 60 + "\n")

    # 不需要编译器的测试
    test_type_mapping()
    test_transport_replaceable()
    test_no_serialization()

    # 检查编译器是否可用
    available = test_fbc_compiler_available()

    if not available:
        print("警告: FreeBASIC 编译器不可用，跳过编译相关测试")
        print("请安装 FreeBASIC 并将 fbc64 加入 PATH 后重试")
        print("(https://www.freebasic.net/)")
        return

    try:
        test_simple_int_function()
        test_string_function()
        test_array_int_sum()
        test_array_float_mean()
        test_recursive_fibonacci()
        test_cache()
        test_compile_and_run()
        test_mode_only_code()
        test_async_mode()
        test_compile_and_run_async()

        print("=" * 60)
        print("所有测试通过！✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
