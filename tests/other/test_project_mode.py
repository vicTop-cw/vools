"""
项目模式测试 - 测试 LangBridge 的 project 模式功能
"""
import os
import sys
import tempfile
import shutil
def test_c_project_dll():
    """测试 C 项目编译为 DLL 并调用函数"""
    print("=" * 60)
    print("测试 1: C 项目编译为 DLL 并调用函数")
    print("=" * 60)

    from vools.bridge.c import CBridge

    bridge = CBridge()

    if not bridge.compiler_available():
        print("跳过: C 编译器不可用")
        return True

    project_dir = tempfile.mkdtemp(prefix="vools_test_c_proj_")
    cache_dir = tempfile.mkdtemp(prefix="vools_test_c_cache_")

    try:
        math_utils_c = '''
int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}
'''
        with open(os.path.join(project_dir, "math_utils.c"), "w") as f:
            f.write(math_utils_c)

        helper_c = '''
int square(int x) {
    return x * x;
}

int cube(int x) {
    return x * x * x;
}
'''
        with open(os.path.join(project_dir, "helper.c"), "w") as f:
            f.write(helper_c)

        print(f"项目目录: {project_dir}")
        print(f"缓存目录: {cache_dir}")

        print("\n第一次编译...")
        artifact1 = bridge._compile_project_with_cache(project_dir, "add", cache_dir)
        print(f"产物路径: {artifact1}")
        assert os.path.exists(artifact1), "编译产物不存在"
        print("✓ 第一次编译成功")

        result = bridge.call_func(artifact1, "add", (3, 4), int)
        print(f"add(3, 4) = {result}")
        assert result == 7, f"期望 7，得到 {result}"
        print("✓ 函数调用成功")

        result2 = bridge.call_func(artifact1, "multiply", (3, 4), int)
        print(f"multiply(3, 4) = {result2}")
        assert result2 == 12, f"期望 12，得到 {result2}"
        print("✓ 多函数调用成功")

        result3 = bridge.call_func(artifact1, "square", (5,), int)
        print(f"square(5) = {result3}")
        assert result3 == 25, f"期望 25，得到 {result3}"
        print("✓ 多文件函数调用成功")

        print("\n第二次编译（检查缓存）...")
        artifact2 = bridge._compile_project_with_cache(project_dir, "add", cache_dir)
        print(f"产物路径: {artifact2}")
        assert artifact1 == artifact2, "缓存未命中，重新编译了"
        print("✓ 缓存命中，未重新编译")

        print("\n✅ C 项目 DLL 模式测试通过")
        return True

    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_c_project_exe():
    """测试 C 项目编译为 EXE"""
    print("\n" + "=" * 60)
    print("测试 2: C 项目编译为 EXE")
    print("=" * 60)

    from vools.bridge.c import CBridge

    bridge = CBridge()

    if not bridge.compiler_available():
        print("跳过: C 编译器不可用")
        return True

    project_dir = tempfile.mkdtemp(prefix="vools_test_c_exe_")
    cache_dir = tempfile.mkdtemp(prefix="vools_test_c_exe_cache_")

    try:
        main_c = '''
#include <stdio.h>

int add(int a, int b);

int main() {
    int result = add(3, 4);
    printf("%d\\n", result);
    return 0;
}
'''
        with open(os.path.join(project_dir, "main.c"), "w") as f:
            f.write(main_c)

        math_c = '''
int add(int a, int b) {
    return a + b;
}
'''
        with open(os.path.join(project_dir, "math.c"), "w") as f:
            f.write(math_c)

        print(f"项目目录: {project_dir}")
        print(f"缓存目录: {cache_dir}")

        print("\n第一次编译 EXE...")
        artifact1 = bridge._compile_project_with_cache(project_dir, "main", cache_dir)
        print(f"产物路径: {artifact1}")
        assert os.path.exists(artifact1), "编译产物不存在"
        print("✓ EXE 编译成功")

        returncode, stdout, stderr = bridge._run_executable(artifact1, ())
        print(f"返回码: {returncode}")
        print(f"标准输出: {stdout.strip()}")
        if stderr:
            print(f"标准错误: {stderr.strip()}")
        assert returncode == 0, f"程序返回非零值: {returncode}"
        assert "7" in stdout, f"期望输出包含 7，得到: {stdout}"
        print("✓ EXE 运行成功")

        print("\n第二次编译 EXE（检查缓存）...")
        artifact2 = bridge._compile_project_with_cache(project_dir, "main", cache_dir)
        assert artifact1 == artifact2, "缓存未命中，重新编译了"
        print("✓ 缓存命中，未重新编译")

        print("\n✅ C 项目 EXE 模式测试通过")
        return True

    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_c_backward_compatibility():
    """测试 C 模块向后兼容性（不传 project_dir 时行为不变）"""
    print("\n" + "=" * 60)
    print("测试 3: C 模块向后兼容性")
    print("=" * 60)

    from vools.bridge.c import CBridge

    bridge = CBridge()

    if not bridge.compiler_available():
        print("跳过: C 编译器不可用")
        return True

    cache_dir = tempfile.mkdtemp(prefix="vools_test_c_bw_")

    try:
        code = '''
int add(int a, int b) {
    return a + b;
}
'''
        print("使用传统单文件模式编译...")
        lib_path = bridge._compile_with_cache(code, "add", cache_dir)
        print(f"产物路径: {lib_path}")
        assert os.path.exists(lib_path), "编译产物不存在"

        result = bridge.call_func(lib_path, "add", (5, 3), int)
        print(f"add(5, 3) = {result}")
        assert result == 8, f"期望 8，得到 {result}"
        print("✓ 传统模式正常工作")

        print("\n✅ C 模块向后兼容性测试通过")
        return True

    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_freebasic_project():
    """测试 FreeBASIC 项目编译"""
    print("\n" + "=" * 60)
    print("测试 4: FreeBASIC 项目编译")
    print("=" * 60)

    from vools.bridge.freebasic.compiler import FbcBridge

    bridge = FbcBridge()

    if not bridge.compiler_available():
        print("跳过: FreeBASIC 编译器不可用")
        return True

    project_dir = tempfile.mkdtemp(prefix="vools_test_fb_proj_")
    cache_dir = tempfile.mkdtemp(prefix="vools_test_fb_cache_")

    try:
        math_bas = '''
Function Add cdecl Alias "Add"(ByVal a As Long, ByVal b As Long) As Long Export
    Return a + b
End Function

Function Multiply cdecl Alias "Multiply"(ByVal a As Long, ByVal b As Long) As Long Export
    Return a * b
End Function
'''
        with open(os.path.join(project_dir, "math.bas"), "w") as f:
            f.write(math_bas)

        helper_bas = '''
Function Square cdecl Alias "Square"(ByVal x As Long) As Long Export
    Return x * x
End Function
'''
        with open(os.path.join(project_dir, "helper.bas"), "w") as f:
            f.write(helper_bas)

        print(f"项目目录: {project_dir}")
        print(f"缓存目录: {cache_dir}")

        print("\n第一次编译 DLL...")
        artifact1 = bridge._compile_project_with_cache(project_dir, "Add", cache_dir)
        print(f"产物路径: {artifact1}")
        assert os.path.exists(artifact1), "编译产物不存在"
        print("✓ 第一次编译成功")

        result = bridge.call_func(artifact1, "Add", (10, 20), None)
        print(f"Add(10, 20) = {result}")
        assert result == 30, f"期望 30，得到 {result}"
        print("✓ 函数调用成功")

        result2 = bridge.call_func(artifact1, "Multiply", (6, 7), None)
        print(f"Multiply(6, 7) = {result2}")
        assert result2 == 42, f"期望 42，得到 {result2}"
        print("✓ 多函数调用成功")

        result3 = bridge.call_func(artifact1, "Square", (9,), None)
        print(f"Square(9) = {result3}")
        assert result3 == 81, f"期望 81，得到 {result3}"
        print("✓ 多文件函数调用成功")

        print("\n第二次编译（检查缓存）...")
        artifact2 = bridge._compile_project_with_cache(project_dir, "Add", cache_dir)
        assert artifact1 == artifact2, "缓存未命中，重新编译了"
        print("✓ 缓存命中，未重新编译")

        print("\n✅ FreeBASIC 项目编译测试通过")
        return True

    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_project_hash():
    """测试项目哈希计算"""
    print("\n" + "=" * 60)
    print("测试 5: 项目哈希计算")
    print("=" * 60)

    from vools.bridge.c import CBridge

    bridge = CBridge()

    project_dir = tempfile.mkdtemp(prefix="vools_test_hash_")

    try:
        with open(os.path.join(project_dir, "a.c"), "w") as f:
            f.write("int a() { return 1; }")
        with open(os.path.join(project_dir, "b.c"), "w") as f:
            f.write("int b() { return 2; }")

        hash1 = bridge._get_project_hash(project_dir)
        print(f"初始哈希: {hash1}")

        hash2 = bridge._get_project_hash(project_dir)
        print(f"再次计算: {hash2}")
        assert hash1 == hash2, "相同内容哈希不一致"
        print("✓ 相同内容哈希一致")

        with open(os.path.join(project_dir, "c.c"), "w") as f:
            f.write("int c() { return 3; }")

        hash3 = bridge._get_project_hash(project_dir)
        print(f"添加文件后: {hash3}")
        assert hash1 != hash3, "内容变化后哈希未变"
        print("✓ 内容变化后哈希不同")

        print("\n✅ 项目哈希计算测试通过")
        return True

    finally:
        shutil.rmtree(project_dir, ignore_errors=True)


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("LangBridge 项目模式测试")
    print("=" * 60)

    tests = [
        test_project_hash,
        test_c_project_dll,
        test_c_project_exe,
        test_c_backward_compatibility,
        test_freebasic_project,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        try:
            result = test()
            if result:
                passed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"\n❌ 测试失败: {test.__name__}")
            print(f"异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: 通过 {passed}, 失败 {failed}, 跳过 {skipped}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
