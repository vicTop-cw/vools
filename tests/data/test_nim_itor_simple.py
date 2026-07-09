import sys
sys.path.insert(0, '.')

from vools.data import Itor, use_nim, get_itor


def test_basic():
    print("=== 基础测试 ===")
    
    use_nim(True)
    itor = get_itor([1, 2, 3, 4, 5])
    result = list(itor)
    print(f"结果: {result}")
    assert result == [1, 2, 3, 4, 5], f"期望 [1,2,3,4,5], 实际 {result}"
    print("通过!")


def test_jump():
    print("\n=== 插队测试 ===")
    
    use_nim(True)
    itor = get_itor([1, 2, 3])
    itor.send(99)
    itor.send([88, 77])
    result = list(itor)
    print(f"结果: {result}")
    assert 99 in result and 88 in result and 77 in result, f"插队失败 {result}"
    print("通过!")


def test_restart():
    print("\n=== 重启测试 ===")
    
    use_nim(True)
    itor = get_itor([1, 2, 3])
    g = iter(itor)
    next(g)
    next(g)
    itor.restart()
    result = list(itor)
    print(f"结果: {result}")
    print("通过!")


def test_infinite():
    print("\n=== 无限迭代器测试 ===")
    
    def gen():
        i = 0
        while i < 10:
            yield i
            i += 1
    
    use_nim(True)
    itor = get_itor(gen())
    result = list(itor)
    print(f"结果: {result}")
    assert result == list(range(10)), f"期望 {list(range(10))}, 实际 {result}"
    print("通过!")


if __name__ == '__main__':
    test_basic()
    test_jump()
    test_restart()
    test_infinite()
    print("\n全部测试通过!")