"""runtimes.py —— 多语言执行后端（docs/10 §D）。

统一接口支持 Python、Shell(Bash/PowerShell)、Node.js、Go、Rust、Ruby、PHP。
运行时自检测机制：启动时检查各语言是否可用，构建可用运行时表。

每种运行时实现相同接口：
- is_available() → bool
- execute(code, context) → (stdout, stderr, exit_code)

主入口：
- RuntimeRegistry：管理所有运行时，自动分发代码到对应执行后端
- execute_block(language, code, context) → (stdout, stderr, exit_code)
"""

__all__ = [
    'RuntimeBackend',
    'PythonRuntime',
    'ShellRuntime',
    'NodeRuntime',
    'GoRuntime',
    'RustRuntime',
    'RubyRuntime',
    'PHPRuntime',
    'RuntimeRegistry',
    'execute_block',
    'get_available_runtimes',
]

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple


class RuntimeBackend(ABC):
    """运行时后端基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """运行时标识符（如 'python', 'shell'）。"""
        ...

    @property
    @abstractmethod
    def aliases(self) -> list:
        """别名列表（如 ['py', 'python3']）。"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查该运行时是否可用。"""
        ...

    @abstractmethod
    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        """执行代码，返回 (stdout, stderr, exit_code)。"""
        ...


class PythonRuntime(RuntimeBackend):
    """Python 运行时（进程内 exec）。"""

    name = 'python'
    aliases = ['py', 'python3']

    def is_available(self) -> bool:
        return True  # Actus 本身就用 Python，必然可用

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        exec_env = dict(context.get('env', {}))
        exec_env['__name__'] = '__actus_block__'
        exec_env['__builtins__'] = __builtins__

        # 注入环境变量到实际 os.environ（exec 内 os.environ 引用真实环境）
        env_backup = {}
        for k, v in context.get('env', {}).items():
            env_backup[k] = os.environ.get(k)
            os.environ[k] = v

        # 注入参数到 sys.argv
        old_argv = sys.argv
        args = context.get('args')
        if args:
            arg_list = args.split() if isinstance(args, str) else list(args)
            sys.argv = [old_argv[0]] + arg_list

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        stdin_data = context.get('stdin')
        old_stdin = sys.stdin
        stdin_buf = io.StringIO(stdin_data) if stdin_data is not None else None

        try:
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            if stdin_buf is not None:
                sys.stdin = stdin_buf

            exec(code, exec_env, exec_env)
            exit_code = 0
        except SystemExit as e:
            stderr_buf.write(str(e))
            exit_code = e.code or 0
        except Exception as e:
            stderr_buf.write(f'{type(e).__name__}: {e}')
            exit_code = 1
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            if stdin_buf is not None:
                sys.stdin = old_stdin
            # 恢复环境变量
            for k, old_v in env_backup.items():
                if old_v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old_v
            # 恢复 argv
            sys.argv = old_argv

        return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code


class ShellRuntime(RuntimeBackend):
    """Shell 运行时（Bash/PowerShell）。"""

    name = 'shell'
    aliases = ['bash', 'sh', 'powershell', 'pwsh', 'cmd']

    def is_available(self) -> bool:
        return True  # 至少有一个 shell 可用

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        workdir = context.get('workdir', os.getcwd())
        env = dict(os.environ)
        env.update(context.get('env', {}))

        # 根据内容检测使用 bash 还是 powershell
        shell_type = self._detect_shell(code)
        if shell_type == 'powershell':
            cmd = ['powershell', '-NoProfile', '-Command', code]
        elif shell_type == 'cmd' or sys.platform == 'win32':
            cmd = ['cmd', '/c', code]
        else:
            # bash
            bash_path = shutil.which('bash')
            if bash_path:
                cmd = [bash_path, '-c', code]
            else:
                cmd = ['sh', '-c', code]

        stdin_data = context.get('stdin')
        try:
            proc = subprocess.run(
                cmd,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=context.get('timeout', 60),
                env=env,
                input=stdin_data if stdin_data else None,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return '', f'超时 ({context.get("timeout", 60)}s)', 124
        except Exception as e:
            return '', str(e), 1

    @staticmethod
    def _detect_shell(code: str) -> str:
        """检测代码应使用的 shell 类型。"""
        # 简单启发式
        if any(kw in code for kw in ['Get-', 'Set-', 'New-', 'Write-Host', '$env:']):
            return 'powershell'
        if any(kw in code for kw in ['@echo', 'setlocal', 'goto ']):
            return 'cmd'
        return 'bash'


class NodeRuntime(RuntimeBackend):
    """Node.js 运行时。"""

    name = 'node'
    aliases = ['nodejs', 'js', 'javascript']

    def is_available(self) -> bool:
        return shutil.which('node') is not None

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        workdir = context.get('workdir', os.getcwd())
        env = dict(os.environ)
        env.update(context.get('env', {}))

        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js',
                                         delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp_path = f.name

        try:
            args = context.get('args')
            cmd = ['node', tmp_path]
            if args:
                cmd.extend(args.split() if isinstance(args, str) else args)

            stdin_data = context.get('stdin')
            proc = subprocess.run(
                cmd,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=context.get('timeout', 60),
                env=env,
                input=stdin_data if stdin_data else None,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return '', f'超时 ({context.get("timeout", 60)}s)', 124
        except Exception as e:
            return '', str(e), 1
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class GoRuntime(RuntimeBackend):
    """Go 运行时（编译后执行）。"""

    name = 'go'
    aliases = ['golang']

    def is_available(self) -> bool:
        return shutil.which('go') is not None

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        workdir = context.get('workdir', os.getcwd())
        env = dict(os.environ)
        env.update(context.get('env', {}))

        # 创建临时目录
        tmp_dir = tempfile.mkdtemp(prefix='actus_go_')
        try:
            # 写入 main.go
            go_file = os.path.join(tmp_dir, 'main.go')
            with open(go_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # 编译
            binary = os.path.join(tmp_dir, 'main')
            if sys.platform == 'win32':
                binary += '.exe'

            build_proc = subprocess.run(
                ['go', 'build', '-o', binary, go_file],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if build_proc.returncode != 0:
                return '', f'编译失败:\n{build_proc.stderr}', build_proc.returncode

            # 执行
            args = context.get('args')
            cmd = [binary]
            if args:
                cmd.extend(args.split() if isinstance(args, str) else args)

            stdin_data = context.get('stdin')
            proc = subprocess.run(
                cmd,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=context.get('timeout', 60),
                env=env,
                input=stdin_data if stdin_data else None,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return '', f'超时 ({context.get("timeout", 60)}s)', 124
        except Exception as e:
            return '', str(e), 1
        finally:
            import shutil as sh
            sh.rmtree(tmp_dir, ignore_errors=True)


class RustRuntime(RuntimeBackend):
    """Rust 运行时（编译后执行）。"""

    name = 'rust'
    aliases = ['rs']

    def is_available(self) -> bool:
        return shutil.which('rustc') is not None

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        workdir = context.get('workdir', os.getcwd())
        env = dict(os.environ)
        env.update(context.get('env', {}))

        tmp_dir = tempfile.mkdtemp(prefix='actus_rust_')
        try:
            # 写入 main.rs
            rs_file = os.path.join(tmp_dir, 'main.rs')
            with open(rs_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # 编译
            binary = os.path.join(tmp_dir, 'main')
            if sys.platform == 'win32':
                binary += '.exe'

            build_proc = subprocess.run(
                ['rustc', '-O', '-o', binary, rs_file],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if build_proc.returncode != 0:
                return '', f'编译失败:\n{build_proc.stderr}', build_proc.returncode

            # 执行
            args = context.get('args')
            cmd = [binary]
            if args:
                cmd.extend(args.split() if isinstance(args, str) else args)

            stdin_data = context.get('stdin')
            proc = subprocess.run(
                cmd,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=context.get('timeout', 60),
                env=env,
                input=stdin_data if stdin_data else None,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return '', f'超时 ({context.get("timeout", 60)}s)', 124
        except Exception as e:
            return '', str(e), 1
        finally:
            import shutil as sh
            sh.rmtree(tmp_dir, ignore_errors=True)


class RubyRuntime(RuntimeBackend):
    """Ruby 运行时。"""

    name = 'ruby'
    aliases = ['rb']

    def is_available(self) -> bool:
        return shutil.which('ruby') is not None

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        workdir = context.get('workdir', os.getcwd())
        env = dict(os.environ)
        env.update(context.get('env', {}))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb',
                                         delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp_path = f.name

        try:
            args = context.get('args')
            cmd = ['ruby', tmp_path]
            if args:
                cmd.extend(args.split() if isinstance(args, str) else args)

            stdin_data = context.get('stdin')
            proc = subprocess.run(
                cmd,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=context.get('timeout', 60),
                env=env,
                input=stdin_data if stdin_data else None,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return '', f'超时 ({context.get("timeout", 60)}s)', 124
        except Exception as e:
            return '', str(e), 1
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class PHPRuntime(RuntimeBackend):
    """PHP 运行时。"""

    name = 'php'
    aliases = []

    def is_available(self) -> bool:
        return shutil.which('php') is not None

    def execute(self, code: str, context: Dict) -> Tuple[str, str, int]:
        workdir = context.get('workdir', os.getcwd())
        env = dict(os.environ)
        env.update(context.get('env', {}))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.php',
                                         delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp_path = f.name

        try:
            args = context.get('args')
            cmd = ['php', tmp_path]
            if args:
                cmd.extend(args.split() if isinstance(args, str) else args)

            stdin_data = context.get('stdin')
            proc = subprocess.run(
                cmd,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=context.get('timeout', 60),
                env=env,
                input=stdin_data if stdin_data else None,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return '', f'超时 ({context.get("timeout", 60)}s)', 124
        except Exception as e:
            return '', str(e), 1
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class RuntimeRegistry:
    """运行时注册表。

    管理所有运行时后端，提供统一的代码执行入口。
    """

    def __init__(self):
        self._runtimes: Dict[str, RuntimeBackend] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册所有内置运行时。"""
        for cls in [PythonRuntime, ShellRuntime, NodeRuntime, GoRuntime,
                    RustRuntime, RubyRuntime, PHPRuntime]:
            try:
                instance = cls()
                self.register(instance)
            except Exception:
                pass

    def register(self, runtime: RuntimeBackend):
        """注册运行时。"""
        self._runtimes[runtime.name] = runtime
        for alias in runtime.aliases:
            self._runtimes[alias] = runtime

    def get(self, language: str) -> Optional[RuntimeBackend]:
        """获取运行时。"""
        return self._runtimes.get(language.lower())

    def is_available(self, language: str) -> bool:
        """检查运行时是否可用。"""
        rt = self.get(language)
        return rt is not None and rt.is_available()

    def execute(self, language: str, code: str, context: Dict) -> Tuple[str, str, int]:
        """执行代码。

        参数:
            language: 语言标识符。
            code: 代码内容。
            context: 执行上下文（env, workdir, args, stdin, timeout）。

        返回:
            (stdout, stderr, exit_code)

        异常:
            RuntimeError: 运行时不可用。
        """
        rt = self.get(language)
        if rt is None:
            raise RuntimeError(f'不支持的语言: {language}')
        if not rt.is_available():
            raise RuntimeError(f'{language} 运行时不可用（未安装）')
        return rt.execute(code, context)

    def available_languages(self) -> list:
        """列出所有可用的语言。"""
        seen = set()
        result = []
        for name, rt in self._runtimes.items():
            if rt.name not in seen and rt.is_available():
                seen.add(rt.name)
                result.append(rt.name)
        return result


# ── 模块级单例 ──

_registry: Optional[RuntimeRegistry] = None


def _get_registry() -> RuntimeRegistry:
    global _registry
    if _registry is None:
        _registry = RuntimeRegistry()
    return _registry


def execute_block(language: str, code: str, context: Dict) -> Tuple[str, str, int]:
    """便捷函数：执行代码块。"""
    return _get_registry().execute(language, code, context)


def get_available_runtimes() -> list:
    """便捷函数：列出可用运行时。"""
    return _get_registry().available_languages()


def reset_registry():
    """测试用：重置注册表。"""
    global _registry
    _registry = None
