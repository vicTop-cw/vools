"""
vools 命令行工具
"""

__all__ = ['main']

import sys
import argparse
from vools import __version__, config


def main():
    """主函数"""
    # API 命令特殊处理 - 直接将控制权交给 Typer
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        try:
            from vools.api import typer_app
            # 移除 "api" 参数，让 Typer 处理剩余参数
            sys.argv = [sys.argv[0]] + sys.argv[2:] if len(sys.argv) > 2 else [sys.argv[0]]
            typer_app()
            return
        except ImportError:
            print("错误: typer 未安装")
            print("请运行: pip install typer")
            print("或安装带 cli 选项的 vools: pip install vools[cli]")
            sys.exit(1)

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

    # 系统集成命令
    sys_parser = subparsers.add_parser("sys", help="系统集成 (DLL/编译/执行/环境)")
    sys_subparsers = sys_parser.add_subparsers(dest="sys_command", help="sys 子命令")

    # sys dll 子命令
    dll_parser = sys_subparsers.add_parser("dll", help="DLL 管理")
    dll_parser.add_argument("--list", action="store_true", help="列出可用 DLL")
    dll_parser.add_argument("--dll", help="DLL 名称")
    dll_parser.add_argument("--func", help="函数名称")
    dll_parser.add_argument("--args", help="函数参数")

    # sys compile 子命令
    compile_parser = sys_subparsers.add_parser("compile", help="编译源文件")
    compile_parser.add_argument("--lang", help="语言 (nim/c/cpp)")
    compile_parser.add_argument("--file", help="源文件路径")
    compile_parser.add_argument("--output", help="输出文件路径")

    # sys run 子命令
    run_parser = sys_subparsers.add_parser("run", help="执行程序")
    run_parser.add_argument("--python", help="Python 脚本路径")
    run_parser.add_argument("--shell", help="Shell 命令")
    run_parser.add_argument("--args", help="附加参数")

    # sys env 子命令
    env_parser = sys_subparsers.add_parser("env", help="环境探测")
    env_parser.add_argument("--path", action="store_true", help="显示 PATH")
    env_parser.add_argument("--python", action="store_true", help="显示 Python 信息")
    env_parser.add_argument("--nim", action="store_true", help="显示 Nim 信息")

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
    
    elif args.command == "sys":
        from vools.sys import dll_cmd, compile_cmd, run_cmd, env_cmd
        
        if args.sys_command == "dll":
            dll = dll_cmd.DllCommands()
            if args.list:
                dll.list()
            elif args.dll and args.func and args.args:
                dll.dll(args.dll, args.func, args.args)
            elif args.dll and args.func:
                dll.func(args.dll, args.func)
            else:
                dll_parser.print_help()
        
        elif args.sys_command == "compile":
            compile = compile_cmd.CompileCommands()
            if args.lang and args.file and args.output:
                compile.run(args.lang, args.file, args.output)
            elif args.lang:
                compile.lang(args.lang)
            else:
                compile_parser.print_help()
        
        elif args.sys_command == "run":
            run = run_cmd.RunCommands()
            if args.python:
                run.python(args.python, args.args or '')
            elif args.shell:
                run.shell(args.shell, args.args or '')
            else:
                run_parser.print_help()
        
        elif args.sys_command == "env":
            env = env_cmd.EnvCommands()
            if args.path:
                env.path()
            elif args.python:
                env.python()
            elif args.nim:
                env.nim()
            else:
                env_parser.print_help()
        
        else:
            sys_parser.print_help()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
