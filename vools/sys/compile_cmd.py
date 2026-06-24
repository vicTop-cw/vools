"""
vools.sys.compile_cmd - 编译器调用子命令

提供 --lang, --file, --output 选项。
"""

import os
import subprocess
import sys


class CompileCommands:
    """编译命令集"""

    def __init__(self):
        self._compilers = {
            'nim': self._nim_compiler,
            'c': self._c_compiler,
            'cpp': self._cpp_compiler,
        }

    def _nim_compiler(self, file: str, output: str):
        """编译 Nim 文件"""
        if not os.path.exists(file):
            print(f"错误: 文件 '{file}' 不存在")
            sys.exit(1)
        
        output_flag = '--out:' + output
        cmd = ['nim', 'c', '--app:lib', output_flag, file]
        
        print(f"执行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                print(f"编译成功: {output}")
            else:
                print(f"编译失败:\n{result.stderr}")
                sys.exit(1)
        except FileNotFoundError:
            print("错误: nim 编译器未找到，请确保 Nim 已安装并添加到 PATH")
            sys.exit(1)

    def _c_compiler(self, file: str, output: str):
        """编译 C 文件"""
        if not os.path.exists(file):
            print(f"错误: 文件 '{file}' 不存在")
            sys.exit(1)
        
        # 尝试使用 gcc 或 cl (MSVC)
        compiler = None
        try:
            subprocess.run(['gcc', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            compiler = 'gcc'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        try:
            subprocess.run(['cl', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            compiler = 'cl'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        if not compiler:
            print("错误: 未找到 C 编译器 (gcc 或 cl)")
            sys.exit(1)
        
        if compiler == 'gcc':
            cmd = ['gcc', '-shared', '-fPIC', '-o', output, file]
        else:
            cmd = ['cl', '/LD', '/Fe:' + output, file]
        
        print(f"执行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                print(f"编译成功: {output}")
            else:
                print(f"编译失败:\n{result.stderr}")
                sys.exit(1)
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)

    def _cpp_compiler(self, file: str, output: str):
        """编译 C++ 文件"""
        if not os.path.exists(file):
            print(f"错误: 文件 '{file}' 不存在")
            sys.exit(1)
        
        # 尝试使用 g++ 或 cl (MSVC)
        compiler = None
        try:
            subprocess.run(['g++', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            compiler = 'g++'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        try:
            subprocess.run(['cl', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            compiler = 'cl'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        if not compiler:
            print("错误: 未找到 C++ 编译器 (g++ 或 cl)")
            sys.exit(1)
        
        if compiler == 'g++':
            cmd = ['g++', '-shared', '-fPIC', '-o', output, file]
        else:
            cmd = ['cl', '/LD', '/Fe:' + output, file]
        
        print(f"执行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                print(f"编译成功: {output}")
            else:
                print(f"编译失败:\n{result.stderr}")
                sys.exit(1)
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)

    def lang(self, lang: str):
        """
        显示支持的编译语言
        
        示例: vools sys compile --lang
        """
        print("支持的编译语言:")
        for l in self._compilers:
            print(f"  - {l}")
        
        # 检查编译器可用性
        print("\n编译器状态:")
        compilers = {
            'nim': ['nim', '--version'],
            'gcc': ['gcc', '--version'],
            'g++': ['g++', '--version'],
            'cl': ['cl', '--version'],
        }
        
        for comp, cmd in compilers.items():
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                version_line = result.stdout.split('\n')[0]
                print(f"  ✓ {comp}: {version_line}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"  ✗ {comp}: 未找到")

    def run(self, lang: str, file: str, output: str):
        """
        编译并返回输出路径
        
        示例: vools sys compile --lang nim --file algo.nim --output algo.dll
        """
        if lang not in self._compilers:
            print(f"错误: 不支持的语言 '{lang}'")
            print(f"支持的语言: {', '.join(self._compilers.keys())}")
            sys.exit(1)
        
        self._compilers[lang](file, output)
