"""
vools.bridge.rust.compiler - Rust 编译器封装

提供 Cargo 项目创建、编译、缓存管理等功能。

使用 manager 统一管理编译器配置。
"""

import os
import subprocess
import hashlib
import shutil
import platform
import tempfile
import time
from typing import Dict, Optional, List, Any, Tuple
from pathlib import Path

from ..manager import get_helper
from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType
from .templates import generate_lib_code, generate_cargo_toml
from .types import RustTypeMapper, infer_ctypes_types, convert_args

# 使用 manager 的编译器辅助
_rust_helper = get_helper('rust')


class RustCompiler:
    """
    Rust 编译器封装

    提供 Cargo 项目创建、编译、缓存管理等功能。
    支持基于代码哈希的编译缓存，避免重复编译。

    属性：
        cache_dir: 编译缓存目录
        max_cache_size: 最大缓存文件数量
        rustc_available: Rust 编译器是否可用
        cargo_available: Cargo 是否可用
    """

    def __init__(self, cache_dir: str = None, max_cache_size: int = 100):
        """
        初始化 RustCompiler

        参数：
            cache_dir: 编译缓存目录（默认为 __rust__/cache）
            max_cache_size: 最大缓存文件数量（超过时清理最旧的）
        """
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'vools_rust_cache')
        self.max_cache_size = max_cache_size

        # 使用 manager 检查编译器可用性
        self.rustc_available = self._check_rustc()
        self.cargo_available = self._check_cargo()

        # 确保缓存目录存在
        self._ensure_cache_dir()

    def _check_rustc(self) -> bool:
        """检查 rustc 是否可用（使用 manager）"""
        return _rust_helper.is_available()

    def _check_cargo(self) -> bool:
        """检查 cargo 是否可用"""
        try:
            # cargo 通常和 rustc 在同一目录
            cargo_path = _rust_helper.get_compiler_path()
            if cargo_path:
                cargo_bin = os.path.join(os.path.dirname(cargo_path), 'cargo.exe' if platform.system() == 'Windows' else 'cargo')
                if os.path.exists(cargo_bin):
                    return True
            # 兜底检查系统 PATH
            result = subprocess.run(['cargo', '--version'],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)

    def _get_code_hash(self, code: str, func_name: str) -> str:
        """
        计算代码哈希值

        参数：
            code: Rust 代码字符串
            func_name: 函数名称

        返回：
            代码哈希值（MD5）
        """
        content = f'{func_name}\n{code}'
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _get_cache_path(self, code_hash: str, package_name: str = None,
                        cache_dir: str = None) -> Tuple[str, str]:
        """
        获取缓存文件路径

        参数：
            code_hash: 代码哈希值
            package_name: Cargo 包名称（用于匹配实际 DLL 文件名）
            cache_dir: 缓存目录，None 则使用 self.cache_dir

        返回：
            (dll_path, project_dir) 元组
        """
        # 项目目录
        project_dir = os.path.join(cache_dir or self.cache_dir, code_hash)

        # DLL 文件路径（Cargo cdylib 输出以 package_name 命名）
        if package_name:
            if platform.system() == 'Windows':
                dll_name = f'{package_name}.dll'
            elif platform.system() == 'Darwin':
                dll_name = f'lib{package_name}.dylib'
            else:
                dll_name = f'lib{package_name}.so'
        else:
            if platform.system() == 'Windows':
                dll_name = f'{code_hash}.dll'
            else:
                dll_name = f'{code_hash}.so'
        dll_path = os.path.join(project_dir, 'target', 'release', dll_name)

        return (dll_path, project_dir)

    def _check_cache(self, code_hash: str, package_name: str = None,
                     cache_dir: str = None) -> Optional[str]:
        """
        检查缓存是否存在

        参数：
            code_hash: 代码哈希值
            cache_dir: 缓存目录，None 则使用 self.cache_dir

        返回：
            DLL 文件路径，如果缓存不存在则返回 None
        """
        dll_path, project_dir = self._get_cache_path(code_hash, package_name, cache_dir)

        if os.path.exists(dll_path):
            return dll_path
        return None

    def _clean_old_cache(self):
        """

        当缓存文件数量超过 max_cache_size 时，删除最旧的缓存。
        """
        if not os.path.exists(self.cache_dir):
            return

        # 获取所有缓存目录
        cache_dirs = []
        for item in os.listdir(self.cache_dir):
            item_path = os.path.join(self.cache_dir, item)
            if os.path.isdir(item_path):
                # 获取目录修改时间
                mtime = os.path.getmtime(item_path)
                cache_dirs.append((item_path, mtime))

        # 如果超过最大数量，删除最旧的
        if len(cache_dirs) > self.max_cache_size:
            # 按修改时间排序
            cache_dirs.sort(key=lambda x: x[1])

            # 删除最旧的
            num_to_delete = len(cache_dirs) - self.max_cache_size
            for i in range(num_to_delete):
                try:
                    shutil.rmtree(cache_dirs[i][0])
                except Exception as e:
                    print(f'Warning: Failed to delete cache {cache_dirs[i][0]}: {e}')

    def compile(
        self,
        code: str,
        func_name: str,
        package_name: str = None,
        dependencies: Dict[str, str] = None,
        force: bool = False,
        cache_dir: str = None,
    ) -> Optional[str]:
        """
        编译 Rust 代码为 DLL

        参数：
            code: Rust 代码字符串
            func_name: 函数名称
            package_name: Cargo 包名称（可选，默认为 vools_rust_<func_name>）
            dependencies: Cargo 依赖字典（可选）
            force: 是否强制重新编译（忽略缓存）
            cache_dir: 缓存目录，None 则使用 self.cache_dir

        返回：
            DLL 文件路径，编译失败返回 None

        异常：
            RuntimeError: 编译器不可用或编译失败
        """
        # 检查编译器可用性
        if not self.cargo_available:
            raise RuntimeError('Cargo is not available. Please install Rust toolchain.')

        # 计算代码哈希
        code_hash = self._get_code_hash(code, func_name)

        # 生成包名称
        if package_name is None:
            package_name = f'vools_rust_{func_name}'

        actual_cache_dir = cache_dir or self.cache_dir

        # 检查缓存
        if not force:
            cached_dll = self._check_cache(code_hash, package_name, actual_cache_dir)
            if cached_dll:
                return cached_dll

        # 获取项目目录
        dll_path, project_dir = self._get_cache_path(code_hash, package_name, actual_cache_dir)

        # 创建项目目录（如被占用则重命名后清理，避免 Windows 文件锁导致失败）
        if os.path.exists(project_dir):
            try:
                shutil.rmtree(project_dir)
            except OSError:
                # 可能被其他进程锁定，重命名后尝试删除
                trash_dir = project_dir + '_old_' + str(int(time.time()))
                try:
                    os.rename(project_dir, trash_dir)
                    shutil.rmtree(trash_dir)
                except OSError:
                    pass
        os.makedirs(project_dir, exist_ok=True)

        # 创建 src 目录
        src_dir = os.path.join(project_dir, 'src')
        os.makedirs(src_dir, exist_ok=True)

        # 生成 lib.rs
        lib_code = generate_lib_code([code])
        lib_path = os.path.join(src_dir, 'lib.rs')
        with open(lib_path, 'w', encoding='utf-8') as f:
            f.write(lib_code)

        # 生成 Cargo.toml
        cargo_code = generate_cargo_toml(package_name, dependencies=dependencies)
        cargo_path = os.path.join(project_dir, 'Cargo.toml')
        with open(cargo_path, 'w', encoding='utf-8') as f:
            f.write(cargo_code)

        # 执行编译
        try:
            # 执行 cargo build --release
            result = subprocess.run(
                ['cargo', 'build', '--release'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                cwd=project_dir,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                raise RuntimeError(f'Rust compilation failed:\n{error_msg}')

            # 检查 DLL 是否生成
            if not os.path.exists(dll_path):
                raise RuntimeError(f'DLL not generated at {dll_path}')

            # 清理旧缓存
            self._clean_old_cache()

            return dll_path

        except subprocess.TimeoutExpired:
            raise RuntimeError('Rust compilation timeout (60s)')
        except Exception as e:
            raise RuntimeError(f'Rust compilation error: {e}')

    def is_available(self) -> bool:
        """检查 Rust 编译器是否可用"""
        return self.cargo_available and self.rustc_available


# 全局编译器实例
_global_compiler = None


def get_compiler(cache_dir: str = None, max_cache_size: int = 100) -> RustCompiler:
    """获取全局 RustCompiler 实例"""
    global _global_compiler
    if _global_compiler is None:
        _global_compiler = RustCompiler(cache_dir, max_cache_size)
    return _global_compiler


def compile_rust_code(
    code: str,
    func_name: str,
    package_name: str = None,
    dependencies: Dict[str, str] = None,
    force: bool = False
) -> Optional[str]:
    """编译 Rust 代码为 DLL（便捷函数）"""
    compiler = get_compiler()
    return compiler.compile(code, func_name, package_name, dependencies, force)


def is_rust_available() -> bool:
    """检查 Rust 编译器是否可用"""
    compiler = get_compiler()
    return compiler.is_available()


# ============================================================================
# RustBridge - Rust 桥接实现（继承 LangBridge）
# ============================================================================

class RustBridge(LangBridge):
    """
    Rust 语言桥接实现

    继承 LangBridge 抽象基类，实现 Rust 特定的代码生成、编译和调用。
    """

    name = 'rust'
    file_ext = '.rs'
    lib_ext = '.dll' if platform.system() == 'Windows' else (
        '.dylib' if platform.system() == 'Darwin' else '.so'
    )
    lang_type = LangType.COMPILED

    def __init__(self):
        super().__init__()
        self._compiler = None
        self._dependencies = {}

    def _get_compiler(self):
        """获取编译器实例"""
        if self._compiler is None:
            self._compiler = get_compiler()
        return self._compiler

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return is_rust_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Rust 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        # 模块级代码
        if spec.module_code:
            parts.append(spec.module_code)
            parts.append('')

        # 依赖函数（按顺序生成）
        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                parts.append(dep_code)
                parts.append('')

        # 主函数
        main_code = self._generate_function(spec)
        parts.append(main_code)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 Rust 代码"""
        import inspect as _inspect

        arg_names = []
        rust_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is _inspect.Parameter.empty:
                rust_argtypes.append('c_long')
            else:
                rust_argtypes.append(RustTypeMapper.get_rust_type(ann))

        ret_type = 'c_long'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = RustTypeMapper.get_rust_type(ann)

        params = []
        for i, rust_t in enumerate(rust_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{name}: {rust_t}')

        params_str = ', '.join(params)

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        if ret_type == 'void':
            return f'''#[no_mangle]
pub extern "C" fn {spec.name}({params_str}) {{
{indented_body}}}'''
        else:
            return f'''#[no_mangle]
pub extern "C" fn {spec.name}({params_str}) -> {ret_type} {{
{indented_body}}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 Rust 代码"""
        compiler = self._get_compiler()
        result = compiler.compile(
            code, func_name,
            dependencies=self._dependencies or None,
            cache_dir=cache_dir,
        )
        if result is None:
            raise RuntimeError(f'Rust compilation failed for {func_name}')
        return result

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Rust 项目

        优先使用 Cargo 项目（有 Cargo.toml），否则使用 rustc 直接编译单文件。
        entry='main' 时生成可执行文件，否则生成 cdylib 动态库。
        """
        if not os.path.isdir(project_dir):
            raise RuntimeError(f'Project directory not found: {project_dir}')

        output_dir = output_dir or self.default_cache_dir()
        os.makedirs(output_dir, exist_ok=True)

        project_name = os.path.basename(os.path.abspath(project_dir))
        cargo_toml_path = os.path.join(project_dir, 'Cargo.toml')

        system = platform.system()
        is_windows = system == 'Windows'
        is_macos = system == 'Darwin'

        if os.path.exists(cargo_toml_path):
            return self._compile_cargo_project(
                project_dir, entry, output_dir,
                project_name, is_windows, is_macos
            )
        else:
            return self._compile_single_file(
                project_dir, entry, output_dir,
                project_name, is_windows, is_macos
            )

    def _compile_cargo_project(self, project_dir, entry, output_dir,
                               project_name, is_windows, is_macos) -> str:
        """编译 Cargo 项目"""
        if not self.cargo_available:
            raise RuntimeError('Cargo is not available')

        target_dir = os.path.join(project_dir, 'target', 'release')

        if entry == 'main':
            cmd = ['cargo', 'build', '--release']
            if is_windows:
                artifact_name = f'{project_name}.exe'
            else:
                artifact_name = project_name
        else:
            cmd = ['cargo', 'build', '--release', '--lib']
            lib_name = project_name.replace('-', '_')
            if is_windows:
                artifact_name = f'{lib_name}.dll'
            elif is_macos:
                artifact_name = f'lib{lib_name}.dylib'
            else:
                artifact_name = f'lib{lib_name}.so'

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=project_dir,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Cargo build failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}'
            )

        built_path = os.path.join(target_dir, artifact_name)
        if not os.path.exists(built_path):
            for f in os.listdir(target_dir):
                if entry == 'main':
                    if (is_windows and f.endswith('.exe')) or (not is_windows and '.' not in f):
                        built_path = os.path.join(target_dir, f)
                        break
                else:
                    if is_windows and f.endswith('.dll'):
                        built_path = os.path.join(target_dir, f)
                        break
                    elif is_macos and f.endswith('.dylib'):
                        built_path = os.path.join(target_dir, f)
                        break
                    elif f.endswith('.so'):
                        built_path = os.path.join(target_dir, f)
                        break

        if not os.path.exists(built_path):
            raise RuntimeError(f'Build artifact not found in {target_dir}')

        output_path = os.path.join(output_dir, os.path.basename(built_path))
        import shutil
        shutil.copy2(built_path, output_path)

        return output_path

    def _compile_single_file(self, project_dir, entry, output_dir,
                             project_name, is_windows, is_macos) -> str:
        """使用 rustc 直接编译单文件项目"""
        if not self.rustc_available:
            raise RuntimeError('rustc is not available')

        rustc_path = _rust_helper.get_compiler_path() or 'rustc'

        if entry == 'main':
            src_file = os.path.join(project_dir, 'main.rs')
            if not os.path.exists(src_file):
                rs_files = [f for f in os.listdir(project_dir) if f.endswith('.rs')]
                if not rs_files:
                    raise RuntimeError(f'No .rs files found in project directory: {project_dir}')
                src_file = os.path.join(project_dir, rs_files[0])

            if is_windows:
                output_name = f'{project_name}.exe'
            else:
                output_name = project_name
            output_path = os.path.join(output_dir, output_name)

            cmd = [rustc_path, '-O', src_file, '-o', output_path]
        else:
            src_file = os.path.join(project_dir, 'lib.rs')
            if not os.path.exists(src_file):
                rs_files = [f for f in os.listdir(project_dir) if f.endswith('.rs')]
                if not rs_files:
                    raise RuntimeError(f'No .rs files found in project directory: {project_dir}')
                src_file = os.path.join(project_dir, rs_files[0])

            if is_windows:
                output_name = f'{project_name}.dll'
            elif is_macos:
                output_name = f'lib{project_name}.dylib'
            else:
                output_name = f'lib{project_name}.so'
            output_path = os.path.join(output_dir, output_name)

            cmd = [rustc_path, '-O', '--crate-type', 'cdylib', src_file, '-o', output_path]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=project_dir,
            timeout=120
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'rustc compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'command: {" ".join(cmd)}'
            )

        if not os.path.exists(output_path):
            raise RuntimeError(f'Build artifact not found at {output_path}')

        return output_path

    @property
    def rustc_available(self) -> bool:
        """rustc 是否可用"""
        return self._get_compiler().rustc_available

    @property
    def cargo_available(self) -> bool:
        """cargo 是否可用"""
        return self._get_compiler().cargo_available

    _dll_handle_cache: Dict[str, Any] = {}

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 Rust 编译的函数"""
        import ctypes as _ctypes

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"Rust DLL not found: {lib_path}")

        lib = self._dll_handle_cache.get(lib_path)
        if lib is None:
            # Windows 下将 DLL 复制到临时文件再加载，避免锁定缓存目录中的原文件
            if platform.system() == 'Windows':
                tmp_fd, tmp_path = tempfile.mkstemp(suffix='.dll')
                os.close(tmp_fd)
                try:
                    shutil.copy2(lib_path, tmp_path)
                except Exception:
                    os.unlink(tmp_path)
                    raise
                lib = _ctypes.CDLL(tmp_path)
            else:
                lib = _ctypes.CDLL(lib_path)
            self._dll_handle_cache[lib_path] = lib
        func = getattr(lib, func_name)

        ctypes_types = infer_ctypes_types(list(args))
        func.argtypes = ctypes_types

        if ret_type is not None:
            rust_ret = RustTypeMapper.get_rust_type(ret_type)
            func.restype = RustTypeMapper.get_ctypes_type(rust_ret)
        else:
            func.restype = _ctypes.c_long

        converted_args = convert_args(list(args), ctypes_types)
        result = func(*converted_args)

        if func.restype == _ctypes.c_char_p and result:
            if isinstance(result, bytes):
                return result.decode('utf-8')
        return result

    def set_dependencies(self, dependencies: dict):
        """设置 Cargo 依赖"""
        self._dependencies = dependencies or {}


# 全局 RustBridge 实例
_rust_bridge = RustBridge()
