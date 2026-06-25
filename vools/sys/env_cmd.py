"""
vools.sys.env_cmd - 环境探测子命令

提供 --path, --python, --nim 选项。
"""

import os
import sys


class EnvCommands:
    """环境探测命令集"""

    def path(self):
        """
        显示系统 PATH 环境变量
        
        示例: vools sys env --path
        """
        path_var = os.environ.get('PATH', '')
        paths = path_var.split(os.pathsep)
        
        print("PATH 环境变量:")
        print("-" * 50)
        for i, p in enumerate(paths, 1):
            exists = '✓' if os.path.exists(p) else '✗'
            print(f"{exists} {i}. {p}")
        print(f"\n共 {len(paths)} 个路径")

    def python(self):
        """
        显示 Python 版本和路径信息
        
        示例: vools sys env --python
        """
        print("Python 环境信息:")
        print("-" * 50)
        print(f"版本: {sys.version}")
        print(f"版本信息: {sys.version_info}")
        print(f"可执行文件: {sys.executable}")
        print(f"安装路径: {sys.prefix}")
        print(f"exec_prefix: {sys.exec_prefix}")
        
        # 显示 site-packages
        try:
            import site
            print(f"\nsite-packages: {site.getsitepackages()}")
            print(f"用户 site-packages: {site.getusersitepackages()}")
        except Exception:
            pass
        
        # 显示已安装的相关包
        print("\n已安装的相关包:")
        packages_to_check = ['fire', 'ctypes', 'subprocess']
        for pkg in packages_to_check:
            try:
                __import__(pkg)
                print(f"  ✓ {pkg}")
            except ImportError:
                print(f"  ✗ {pkg}")

    def nim(self):
        """
        显示 Nim 编译器信息
        
        示例: vools sys env --nim
        """
        import subprocess
        
        print("Nim 环境信息:")
        print("-" * 50)
        
        try:
            result = subprocess.run(['nim', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print("错误: nim 编译器返回非零状态")
        except FileNotFoundError:
            print("错误: nim 编译器未找到")
        
        # 检查 Nim 库目录
        from ..bridge.core.loader import _LIB_DIR
        print(f"\nNim 库目录: {_LIB_DIR}")
        
        if os.path.exists(_LIB_DIR):
            dlls = [f for f in os.listdir(_LIB_DIR) if f.endswith('.dll') or f.endswith('.so')]
            if dlls:
                print(f"找到 {len(dlls)} 个动态库:")
                for dll in dlls:
                    print(f"  - {dll}")
            else:
                print("目录为空或无动态库文件")
        else:
            print("目录不存在")
