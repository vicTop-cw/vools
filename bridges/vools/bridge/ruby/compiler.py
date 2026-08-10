"""
vools.bridge.ruby.compiler - Ruby 语言桥接编译器实现

提供 RubyBridge 类，继承 LangBridge 抽象基类，实现 Ruby 特定的代码生成、
编译（解释执行）和调用逻辑。
"""

import os
import sys
import tempfile
import hashlib
import platform
import inspect
import json
import shutil
import subprocess
import threading
from typing import Any

from .._base import LangBridge, FunctionSpec, FunctionParser
from ..core.types import LangType
from ..core.wsl import resolve_command, windows_to_wsl_path

# ----------------------------------------------------------------------------
# Ruby 命令解析（支持本地或 WSL）
# ----------------------------------------------------------------------------
_RUBY_CMD, _PATH_CONVERTER, _USE_WSL = resolve_command('ruby')

# 保留旧变量名，避免外部导入失败
_RUBY_PATH = _RUBY_CMD[-1]


def ruby_compiler_available() -> bool:
    """检查 Ruby 解释器是否可用（执行 `ruby --version`）"""
    try:
        result = subprocess.run(
            _RUBY_CMD + ['--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            errors='replace', timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 缓存目录
# ----------------------------------------------------------------------------
_RUBY_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_ruby_cache')


# ----------------------------------------------------------------------------
# Python ↔ Ruby 类型映射
# ----------------------------------------------------------------------------

PY_TO_RUBY_TYPE = {
    int: 'Integer',
    float: 'Float',
    bool: 'Boolean',
    str: 'String',
    bytes: 'String',
    list: 'Array',
    dict: 'Hash',
    type(None): 'nil',
}

_RUBY_TYPE_ALIASES = {
    'int': 'Integer',
    'integer': 'Integer',
    'float': 'Float',
    'double': 'Float',
    'bool': 'Boolean',
    'boolean': 'Boolean',
    'str': 'String',
    'string': 'String',
    'bytes': 'String',
    'list': 'Array',
    'array': 'Array',
    'dict': 'Hash',
    'hash': 'Hash',
    'nil': 'nil',
    'none': 'nil',
    'nonetype': 'nil',
}


def get_ruby_type(py_type):
    """根据 Python 类型获取 Ruby 端类型字符串"""
    if py_type in PY_TO_RUBY_TYPE:
        return PY_TO_RUBY_TYPE[py_type]

    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _RUBY_TYPE_ALIASES:
            return _RUBY_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _RUBY_TYPE_ALIASES:
            return _RUBY_TYPE_ALIASES[short]
        return 'Integer'

    return 'Integer'


def infer_ruby_argtypes(args):
    """根据运行时值推断 Ruby 端入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('Boolean')
        elif isinstance(arg, int):
            result.append('Integer')
        elif isinstance(arg, float):
            result.append('Float')
        elif isinstance(arg, str):
            result.append('String')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('String')
        elif isinstance(arg, (list, tuple)):
            result.append('Array')
        elif isinstance(arg, dict):
            result.append('Hash')
        else:
            result.append('Object')
    return result


# ----------------------------------------------------------------------------
# Ruby 代码生成
# ----------------------------------------------------------------------------

def _preprocess_ruby_body(body: str, auto_signature: bool) -> str:
    """预处理 Ruby 函数体"""
    if not auto_signature:
        return body

    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        indented_lines.append('  ' + line)

    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _generate_ruby_source(
    func_name: str,
    arg_names: list,
    arg_ruby_types: list,
    ret_ruby_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
) -> str:
    """
    生成完整的 Ruby 源码

    参数：
        func_name: 函数名
        arg_names: 参数名列表
        arg_ruby_types: Ruby 端入参类型列表
        ret_ruby_type: Ruby 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名
        args_json: JSON 编码的参数（用于传递 Python 参数）

    返回：
        完整 Ruby 源码字符串
    """
    params_str = ', '.join(arg_names) if arg_names else ''

    indented_body = _preprocess_ruby_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    if auto_signature:
        code = f'''# encoding: utf-8
require 'json'

# 解析参数
args_json = '{args_json}'
args = JSON.parse(args_json)

def {func_name}({params_str}){indented_body}end

# 调用函数并输出结果
result = {func_name}(*args)

# 输出结果（JSON 格式）
if result.nil?
  puts 'null'
elsif result.is_a?(Array) || result.is_a?(Hash)
  puts result.to_json
elsif result.is_a?(TrueClass) || result.is_a?(FalseClass)
  puts result.to_s
elsif result.is_a?(Float)
  puts result.to_s
else
  puts result.to_s
end
'''
    else:
        code = f'''# encoding: utf-8
require 'json'

args_json = '{args_json}'
args = JSON.parse(args_json)

{body}
'''
    return code


# ----------------------------------------------------------------------------
# 执行逻辑
# ----------------------------------------------------------------------------

def _execute_ruby_code(code: str, func_name: str, cache_dir: str = None,
                       force: bool = False) -> str:
    """
    执行 Ruby 代码并返回输出

    参数：
        code: 完整 Ruby 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _RUBY_CACHE_DIR
        force: 强制重新执行（忽略缓存）

    返回：
        Ruby 执行的输出结果（字符串）
    """
    if cache_dir is None:
        cache_dir = _RUBY_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'ruby_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.rb')

    if not force and os.path.exists(src_path):
        result = subprocess.run(
            _RUBY_CMD + [_PATH_CONVERTER(src_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace',
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    result = subprocess.run(
        _RUBY_CMD + [_PATH_CONVERTER(src_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors='replace',
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'Ruby 执行失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return result.stdout.strip()


def _parse_ruby_output(output: str, ret_type: str):
    """
    解析 Ruby 输出结果

    参数：
        output: Ruby 输出的字符串
        ret_type: 期望的返回类型

    返回：
        Python 端的解码结果
    """
    if output == 'null' or output == '':
        return None

    if ret_type == 'Integer':
        try:
            return int(output)
        except ValueError:
            return output
    elif ret_type == 'Float':
        try:
            return float(output)
        except ValueError:
            return output
    elif ret_type == 'Boolean':
        if output.lower() in ('true', '1'):
            return True
        elif output.lower() in ('false', '0'):
            return False
        return output
    elif ret_type in ('Array', 'Hash'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type == 'String':
        return output

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        try:
            return int(output)
        except ValueError:
            try:
                return float(output)
            except ValueError:
                return output


# ----------------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------------

_code_cache = {}
_cache_lock = threading.Lock()


def _get_cached_code(func_name: str, code: str, force: bool = False) -> str:
    """获取缓存的代码路径，必要时重新生成"""
    with _cache_lock:
        cached = _code_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'ruby_{func_name}_{code_hash}'
        src_path = os.path.join(_RUBY_CACHE_DIR, f'{base_name}.rb')
        os.makedirs(_RUBY_CACHE_DIR, exist_ok=True)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        _code_cache[func_name] = (code, src_path)
        return src_path


# ============================================================================
# RubyBridge - Ruby 桥接实现（继承 LangBridge）
# ============================================================================

class RubyBridge(LangBridge):
    """
    Ruby 语言桥接实现

    继承 LangBridge 抽象基类，实现 Ruby 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'ruby'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.rb'
    lib_ext = '.rb'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return ruby_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码。"""
        import zipfile, tempfile, subprocess, os, shutil
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            with open(source_file, 'r', encoding='utf-8') as f:
                user_code = f.read()
            
            args_json = json.dumps(list(args))
            ruby_ret_type = get_ruby_type(ret_type) if ret_type else 'Integer'
            
            wrapper_code = f'''# encoding: utf-8
require 'json'

args_json = '{args_json}'
args = JSON.parse(args_json)

{user_code}

result = {func_name}(*args)

if result.nil?
  puts 'null'
elsif result.is_a?(Array) || result.is_a?(Hash)
  puts result.to_json
elsif result.is_a?(TrueClass) || result.is_a?(FalseClass)
  puts result.to_s
elsif result.is_a?(Float)
  puts result.to_s
else
  puts result.to_s
end
'''
            
            wrapper_file = os.path.join(tmpdir, f'run_{func_name}.rb')
            with open(wrapper_file, 'w', encoding='utf-8') as f:
                f.write(wrapper_code)
            
            cmd = _RUBY_CMD + [_PATH_CONVERTER(wrapper_file)]
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    errors='replace', timeout=30)
            if result.returncode != 0:
                raise RuntimeError("Execution failed: " + result.stderr)
            return _parse_ruby_output(result.stdout.strip(), ruby_ret_type)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Ruby 代码

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
        """生成单个函数的 Ruby 代码"""
        arg_names = []
        ruby_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                ruby_argtypes.append('Integer')
            else:
                ruby_argtypes.append(get_ruby_type(ann))

        ret_type = 'Integer'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'nil'
            else:
                ret_type = get_ruby_type(ann)

        params_str = ', '.join(arg_names) if arg_names else ''

        indented_body = _preprocess_ruby_body(spec.body, True)
        if indented_body:
            indented_body = '\n' + indented_body + '\n'
        else:
            indented_body = '\n'

        return f'''def {spec.name}({params_str}){indented_body}end'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Ruby 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: Ruby 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        if cache_dir is None:
            cache_dir = _RUBY_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'ruby_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.rb')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译（处理）Ruby 项目

        Ruby 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .rb 文件
        - entry='main' 时：返回主文件路径（project_dir/main.rb），后续由调用方执行
        - entry!='main' 时：把所有 .rb 文件打包成一个可执行的 rb 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 rb 文件路径）
        """
        output_dir = output_dir or _RUBY_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        rb_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.rb'):
                    rb_files.append(os.path.join(root, f))

        if not rb_files:
            raise RuntimeError(f'No .rb files found in project directory: {project_dir}')

        rb_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            # entry='main' 时，直接返回主文件路径
            main_rb = os.path.join(project_dir, 'main.rb')
            if not os.path.exists(main_rb):
                # 如果没有 main.rb，就用第一个 rb 文件
                main_rb = rb_files[0]
            return main_rb
        else:
            # entry!='main' 时，打包所有 rb 文件到一个文件，并在末尾调用入口函数
            project_hash = self._get_project_hash(project_dir)[:12]
            output_path = os.path.join(output_dir, f'ruby_proj_{project_name}_{entry}_{project_hash}.rb')

            # 如果缓存存在，直接返回
            if os.path.exists(output_path):
                return output_path

            # 拼接所有 rb 文件内容
            all_code = []
            all_code.append('# encoding: utf-8')
            all_code.append(f'# Auto-generated from project: {project_name}')
            all_code.append('')

            for rb_file in rb_files:
                rel_path = os.path.relpath(rb_file, project_dir)
                all_code.append(f'# --- {rel_path} ---')
                with open(rb_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            # 添加入口函数调用
            all_code.append(f'# Entry point call')
            all_code.append(f'result = {entry}(*args) rescue nil')
            all_code.append('')
            all_code.append('# Output result')
            all_code.append('if result.nil?')
            all_code.append("  puts 'null'")
            all_code.append('elsif result.is_a?(Array) || result.is_a?(Hash)')
            all_code.append('  puts result.to_json')
            all_code.append('elsif result.is_a?(TrueClass) || result.is_a?(FalseClass)')
            all_code.append('  puts result.to_s')
            all_code.append('elsif result.is_a?(Float)')
            all_code.append('  puts result.to_s')
            all_code.append('else')
            all_code.append('  puts result.to_s')
            all_code.append('end')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Ruby 函数（通过执行 rb 文件）

        参数：
            src_path: Ruby 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        ruby_ret_type = get_ruby_type(ret_type) if ret_type else 'Integer'

        # 将参数编码为 JSON
        args_json = json.dumps(list(args))

        # 读取源文件内容，添加入口调用
        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        # 生成完整的可执行代码（包含参数解析和结果输出）
        arg_names = [f'arg{i}' for i in range(len(args))]
        arg_ruby_types = infer_ruby_argtypes(args)

        full_code = _generate_ruby_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_ruby_types=arg_ruby_types,
            ret_ruby_type=ruby_ret_type,
            body=code,
            auto_signature=False,
            args_json=args_json,
        )

        output = _execute_ruby_code(full_code, func_name)
        return _parse_ruby_output(output, ruby_ret_type)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: str = None) -> Any:
        """
        运行 Ruby 项目

        entry='main' 时：直接执行 ruby project_dir/main.rb，返回 (returncode, stdout, stderr)
        entry!='main' 时：打包所有 rb 文件后调用入口函数，返回函数结果
        """
        if entry == 'main':
            main_rb = os.path.join(project_dir, 'main.rb')
            if not os.path.exists(main_rb):
                # 找第一个 rb 文件
                rb_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.rb'):
                            rb_files.append(os.path.join(root, f))
                if not rb_files:
                    raise RuntimeError(f'No .rb files found in project directory: {project_dir}')
                main_rb = rb_files[0]

            result = subprocess.run(
                _RUBY_CMD + [_PATH_CONVERTER(main_rb)] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors='replace',
                timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


# 全局 RubyBridge 实例
_ruby_bridge = RubyBridge()
