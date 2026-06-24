"""
vools.sys.run_cmd - 程序执行子命令

提供 --python, --shell, --args 选项。
"""

import os
import subprocess
import sys


class RunCommands:
    """程序执行命令集"""

    def python(self, script: str, args: str = ''):
        """
        执行 Python 脚本
        
        示例: vools sys run --python script.py --args "--help"
        """
        if not os.path.exists(script):
            print(f"错误: 脚本 '{script}' 不存在")
            sys.exit(1)
        
        cmd = [sys.executable, script]
        if args:
            cmd.extend(args.split())
        
        print(f"执行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd)
            sys.exit(result.returncode)
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)

    def shell(self, command: str, args: str = ''):
        """
        执行系统 shell 命令
        
        示例: vools sys run --shell "dir" --args "/b"
        """
        cmd = command
        if args:
            cmd = cmd + ' ' + args
        
        print(f"执行: {cmd}")
        try:
            if os.name == 'nt':
                result = subprocess.run(cmd, shell=True, executable='cmd.exe')
            else:
                result = subprocess.run(cmd, shell=True, executable='/bin/bash')
            sys.exit(result.returncode)
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)

    def args(self, args: str):
        """
        显示参数用法
        
        示例: vools sys run --args "--help"
        """
        print(f"接收到的参数: {args}")
        print("\n用法示例:")
        print("  vools sys run --python script.py --args 'arg1 arg2'")
        print("  vools sys run --shell 'dir' --args '/b'")
