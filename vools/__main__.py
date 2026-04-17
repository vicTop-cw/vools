"""
vools 命令行工具
"""

import sys
import argparse
from vools import __version__, config


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description=f"vools - Python 函数式编程工具集 (v{__version__})")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 版本命令
    subparsers.add_parser("version", help="显示版本信息")
    
    # 配置命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("action", choices=["get", "set", "validate", "list"], help="操作")
    config_parser.add_argument("key", nargs="?", help="配置键")
    config_parser.add_argument("value", nargs="?", help="配置值")
    
    # 测试命令
    subparsers.add_parser("test", help="运行测试")
    
    # 解析参数
    args = parser.parse_args()
    
    if args.command == "version":
        print(f"vools version {__version__}")
        print(f"Python version: {sys.version}")
    
    elif args.command == "config":
        if args.action == "get":
            if args.key:
                value = config.get(args.key)
                print(f"{args.key} = {value}")
            else:
                print("请指定配置键")
        
        elif args.action == "set":
            if args.key and args.value:
                config.set(args.key, args.value)
                print(f"已设置 {args.key} = {args.value}")
            else:
                print("请指定配置键和值")
        
        elif args.action == "validate":
            config.validate()
            print("配置验证完成")
        
        elif args.action == "list":
            all_config = config.get_all()
            for section, values in all_config.items():
                print(f"[{section}]")
                for key, value in values.items():
                    print(f"  {key} = {value}")
                print()
    
    elif args.command == "test":
        print("运行基本测试...")
        
        # 测试装饰器
        from vools import memorize, once, repeat
        
        print("\n=== 测试装饰器 ===")
        
        @memorize(duration=5)
        def test_memorize(x):
            print(f"计算 {x}")
            return x * 2
        
        result1 = test_memorize(5)
        print(f"第一次结果: {result1}")
        
        result2 = test_memorize(5)
        print(f"第二次结果: {result2}")
        
        @once
        def test_once():
            print("执行一次")
            return 42
        
        result3 = test_once()
        print(f"第一次调用: {result3}")
        
        result4 = test_once()
        print(f"第二次调用: {result4}")
        
        # 测试函数式编程工具
        from vools import Ops, Seq
        
        print("\n=== 测试函数式编程工具 ===")
        
        result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
        print(f"偶数的两倍之和: {result}")
        
        result = Seq(range(10)).map(lambda x: x * 2).filter(lambda x: x > 5).collect()
        print(f"序列操作结果: {result}")
        
        print("\n测试完成!")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
