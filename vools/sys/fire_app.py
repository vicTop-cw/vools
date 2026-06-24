"""
vools.sys.fire_app - Fire CLI 应用实例

使用 Fire 框架自动生成 CLI 界面。
"""

import fire
from . import dll_cmd, compile_cmd, run_cmd, env_cmd


class SysCLI:
    """系统集成 CLI 主类"""

    def __init__(self):
        self.dll = dll_cmd.DllCommands()
        self.compile = compile_cmd.CompileCommands()
        self.run = run_cmd.RunCommands()
        self.env = env_cmd.EnvCommands()


def main():
    """CLI 入口点"""
    fire.Fire(SysCLI)


if __name__ == '__main__':
    main()
