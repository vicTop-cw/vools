"""
仓颉(Cangjie)语言桥接示例

展示如何使用 vools.bridge.cangjie 模块进行跨语言编程。

注意:仓颉运行时初始化问题待解决,部分示例可能无法运行。
"""

import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.cangjie import (
    cjc_compiler_available,
    cangjie,
    compile_and_run,
    compile_and_run_async,
    batch_compile_and_run_async,
    get_cj_type,
    generate_cj_code,
)


def main():
    """主函数"""
    print("=" * 60)
    print("仓颉语言桥接示例")
    print("=" * 60)

    # 1. 检查编译器可用性
    print("\n1. 检查仓颉编译器可用性")
    available = cjc_compiler_available()
    print(f"   cjc 编译器可用: {available}")

    if not available:
        print("   警告:仓颉编译器不可用,部分示例无法运行")
        print("   请确保已安装仓颉 SDK 并将 cjc 添加到 PATH")
        return

    # 2. 类型映射示例
    print("\n2. 类型映射示例")
    print(f"   int → {get_cj_type(int)}")
    print(f"   float → {get_cj_type(float)}")
    print(f"   bool → {get_cj_type(bool)}")
    print(f"   str → {get_cj_type(str)}")
    print(f"   None → {get_cj_type(type(None))}")

    # 3. 代码生成示例
    print("\n3. 代码生成示例")
    code = generate_cj_code(
        'fib',
        ['n'],
        ['Int64'],
        'Int64',
        '''
    if n <= 1 {
        return 1
    } else {
        return fib(n - 1) + fib(n - 2)
    }
        '''
    )
    print("   生成的仓颉代码:")
    print("   " + "-" * 50)
    for line in code.split('\n'):
        if line.strip():
            print("   " + line)
    print("   " + "-" * 50)

    # 4. 装饰器示例(ONLY_CODE 模式)
    print("\n4. 装饰器示例(ONLY_CODE 模式)")

    @cangjie(mode='ONLY_CODE')
    def add(a: int, b: int) -> int:
        return 'return a + b'

    generated_code = add(10, 20)
    print("   生成的 add 函数代码:")
    print("   " + "-" * 50)
    for line in generated_code.split('\n'):
        if line.strip():
            print("   " + line)
    print("   " + "-" * 50)

    # 6. 装饰器示例(FORCE 模式 - 只编译不执行)
    print("\n6. 装饰器示例(FORCE 模式)")

    @cangjie(mode='FORCE')
    def multiply(a: int, b: int) -> int:
        return 'return a * b'

    dll_path = multiply(5, 6)
    print(f"   编译生成的 DLL: {dll_path}")

    # 7. 异步调用示例(ONLY_CODE 模式)
    print("\n7. 异步调用示例(ONLY_CODE 模式)")

    @cangjie(mode='ONLY_CODE', async_mode=True)
    def async_add(a: int, b: int) -> int:
        return 'return a + b'

    # 异步模式需要 asyncio 运行
    async def demo_async():
        # 直接调用会返回 coroutine
        code = await async_add(10, 20)
        return code

    code = asyncio.run(demo_async())
    print("   异步装饰器生成的代码:")
    print("   " + "-" * 50)
    for line in code.split('\n'):
        if line.strip():
            print("   " + line)
    print("   " + "-" * 50)

    # 8. 批量异步编译示例(仅生成代码)
    print("\n8. 批量异步编译示例(仅生成代码)")

    async def demo_async_batch():
        # 批量生成代码,不实际编译执行
        funcs = [
            ('return 1', 'func1', (), 'Int64'),
            ('return 2', 'func2', (), 'Int64'),
            ('return 3', 'func3', (), 'Int64'),
        ]
        # 注意:实际执行需要仓颉运行时支持
        # 这里演示异步调用模式
        for i, (cj_code, func_name, args, ret_type) in enumerate(funcs):
            print(f"   func{i+1} ({func_name}) 代码生成: {cj_code}")

    # 运行异步批量示例
    asyncio.run(demo_async_batch())

    # 9. 注意事项
    print("\n9. 已知限制")
    print("   - 仓颉运行时初始化问题待解决")
    print("   - DLL 调用可能失败,需要运行时库支持")
    print("   - 字符串和数组类型需要特殊处理")
    print("   - 建议:使用 ONLY_CODE 模式生成代码,手动集成到仓颉项目")

    print("\n" + "=" * 60)
    print("示例完成")
    print("=" * 60)


if __name__ == '__main__':
    main()