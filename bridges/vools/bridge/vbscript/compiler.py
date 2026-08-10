"""
vools.bridge.vbscript.compiler - VBScript 语言桥接编译器实现

提供 VBScriptBridge 类，继承 LangBridge 抽象基类，实现 VBScript 特定的代码生成、
解释执行和调用逻辑。
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
import textwrap
from typing import Any, Optional, List

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType


_IS_WINDOWS = platform.system() == 'Windows'

_CSCRIPT_PATH = 'cscript.exe'

_VBS_SEARCH_PATHS_WINDOWS = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
]


def _setup_vbs_env() -> str:
    """设置 VBScript 运行环境（PATH）；返回 cscript 可执行路径"""
    if not _IS_WINDOWS:
        return _CSCRIPT_PATH

    search_paths = _VBS_SEARCH_PATHS_WINDOWS
    env_paths = os.environ.get('PATH', '').split(os.pathsep)

    for p in search_paths:
        if os.path.exists(p) and p not in env_paths:
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    return _get_cscript_path()


def _get_cscript_path() -> str:
    """获取 cscript 解释器路径"""
    found = shutil.which('cscript')
    if found:
        return found

    if _IS_WINDOWS:
        for p in _VBS_SEARCH_PATHS_WINDOWS:
            candidate = os.path.join(p, 'cscript.exe')
            if os.path.exists(candidate):
                return candidate

    return _CSCRIPT_PATH


_CSCRIPT_PATH = _setup_vbs_env()


def vbscript_compiler_available() -> bool:
    """检查 VBScript 解释器是否可用（执行 `cscript //Nologo`）"""
    if not _IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            [_CSCRIPT_PATH, '//Nologo', '//E:vbscript', '//?'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
        return result.returncode == 0 or 'Microsoft' in result.stdout or 'Microsoft' in result.stderr
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


_VBS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_vbscript_cache')


_VBS_TYPE_ALIASES = {
    'int': 'Integer',
    'integer': 'Integer',
    'long': 'Long',
    'float': 'Double',
    'double': 'Double',
    'single': 'Single',
    'number': 'Double',
    'bool': 'Boolean',
    'boolean': 'Boolean',
    'str': 'String',
    'string': 'String',
    'list': 'Variant()',
    'array': 'Variant()',
    'variant()': 'Variant()',
    'dict': 'Dictionary',
    'dictionary': 'Dictionary',
    'variant': 'Variant',
    'none': 'Variant',
    'nonetype': 'Variant',
    'null': 'Variant',
}


def get_vbs_type(py_type):
    """根据 Python 类型获取 VBScript 端类型字符串"""
    from .types import PY_TO_VBS_TYPE
    if py_type in PY_TO_VBS_TYPE:
        return PY_TO_VBS_TYPE[py_type]

    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _VBS_TYPE_ALIASES:
            return _VBS_TYPE_ALIASES[normalized]
        short = normalized.split('.')[-1]
        if short in _VBS_TYPE_ALIASES:
            return _VBS_TYPE_ALIASES[short]
        return 'Variant'

    return 'Variant'


def infer_vbs_argtypes(args):
    """根据运行时值推断 VBScript 端入参类型"""
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('Boolean')
        elif isinstance(arg, int):
            result.append('Integer')
        elif isinstance(arg, float):
            result.append('Double')
        elif isinstance(arg, str):
            result.append('String')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('String')
        elif isinstance(arg, (list, tuple)):
            result.append('Variant()')
        elif isinstance(arg, dict):
            result.append('Dictionary')
        else:
            result.append('Variant')
    return result


def _preprocess_vbs_body(body: str, auto_signature: bool) -> str:
    """预处理 VBScript 函数体"""
    if not auto_signature:
        return body

    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        indented_lines.append('    ' + line)

    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _escape_vbs_string(s: str) -> str:
    """转义 VBScript 字符串中的特殊字符"""
    return s.replace('"', '""')


def _generate_vbs_source(
    func_name: str,
    arg_names: List,
    arg_vbs_types: List,
    ret_vbs_type: str,
    body: str,
    auto_signature: bool = True,
    args_json: str = None,
    module_code: str = '',
    deps_code: str = '',
) -> str:
    """
    生成完整的 VBScript 源码

    参数：
        func_name: 函数名
        arg_names: 参数名列表
        arg_vbs_types: VBScript 端入参类型列表
        ret_vbs_type: VBScript 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名
        args_json: JSON 编码的参数（用于传递 Python 参数）
        module_code: 模块级代码
        deps_code: 依赖函数代码

    返回：
        完整 VBScript 源码字符串
    """
    params_str = ', '.join(arg_names) if arg_names else ''

    indented_body = _preprocess_vbs_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    code_parts = []

    code_parts.append("' VBScript auto-generated script")
    code_parts.append('Option Explicit')
    code_parts.append('')

    code_parts.append("' 解析参数")
    code_parts.append('Dim argsJson, args')
    code_parts.append(f'argsJson = "{_escape_vbs_string(args_json)}"')
    code_parts.append('Set args = CreateObject("Scripting.Dictionary")')
    code_parts.append('Call ParseJsonArgs(argsJson, args)')
    code_parts.append('')

    if module_code:
        code_parts.append("' 模块级代码")
        code_parts.append(module_code)
        code_parts.append('')

    if deps_code:
        code_parts.append("' 依赖函数")
        code_parts.append(deps_code)
        code_parts.append('')

    if auto_signature:
        code_parts.append(f'Function {func_name}({params_str}){indented_body}End Function')
    else:
        code_parts.append(body)

    code_parts.append('')
    code_parts.append("' 调用函数并输出结果")
    call_args = []
    for i, name in enumerate(arg_names):
        call_args.append(f'args.Item("{name}")')
    call_str = ', '.join(call_args)

    code_parts.append('Dim result')
    if call_str:
        code_parts.append(f'result = {func_name}({call_str})')
    else:
        code_parts.append(f'result = {func_name}()')
    code_parts.append('')

    code_parts.append("' 输出结果")
    code_parts.append('WScript.StdOut.WriteLine SerializeValue(result)')
    code_parts.append('')

    code_parts.append("' ========== Helper Functions ==========")
    code_parts.append('')
    code_parts.append('Sub ParseJsonArgs(jsonStr, dict)')
    code_parts.append('    Dim i, lenJson, key, val, pos')
    code_parts.append('    lenJson = Len(jsonStr)')
    code_parts.append('    i = 1')
    code_parts.append('    Do While i <= lenJson')
    code_parts.append('        Dim ch')
    code_parts.append('        ch = Mid(jsonStr, i, 1)')
    code_parts.append('        If ch = "{" Or ch = "," Then')
    code_parts.append('            i = i + 1')
    code_parts.append('            If i > lenJson Then Exit Do')
    code_parts.append('            ch = Mid(jsonStr, i, 1)')
    code_parts.append('            If ch = "}" Then Exit Do')
    code_parts.append('            Do While Mid(jsonStr, i, 1) = " " And i <= lenJson')
    code_parts.append('                i = i + 1')
    code_parts.append('            Loop')
    code_parts.append('            If Mid(jsonStr, i, 1) = Chr(34) Then')
    code_parts.append('                i = i + 1')
    code_parts.append('                key = ""')
    code_parts.append('                Do While i <= lenJson And Mid(jsonStr, i, 1) <> Chr(34)')
    code_parts.append('                    key = key & Mid(jsonStr, i, 1)')
    code_parts.append('                    i = i + 1')
    code_parts.append('                Loop')
    code_parts.append('                i = i + 1')
    code_parts.append('                Do While Mid(jsonStr, i, 1) = ":" Or Mid(jsonStr, i, 1) = " "')
    code_parts.append('                    i = i + 1')
    code_parts.append('                Loop')
    code_parts.append('                Dim valType')
    code_parts.append('                valType = Mid(jsonStr, i, 1)')
    code_parts.append('                If valType = Chr(34) Then')
    code_parts.append('                    i = i + 1')
    code_parts.append('                    val = ""')
    code_parts.append('                    Do While i <= lenJson And Mid(jsonStr, i, 1) <> Chr(34)')
    code_parts.append('                        If Mid(jsonStr, i, 1) = "\\" Then')
    code_parts.append('                            i = i + 1')
    code_parts.append('                            If i <= lenJson Then')
    code_parts.append('                                Dim escCh')
    code_parts.append('                                escCh = Mid(jsonStr, i, 1)')
    code_parts.append('                                If escCh = "n" Then val = val & vbLf')
    code_parts.append('                                If escCh = "t" Then val = val & vbTab')
    code_parts.append('                                If escCh = "r" Then val = val & vbCr')
    code_parts.append('                                If escCh = "\\" Then val = val & "\\"')
    code_parts.append('                                If escCh = Chr(34) Then val = val & Chr(34)')
    code_parts.append('                            End If')
    code_parts.append('                        Else')
    code_parts.append('                            val = val & Mid(jsonStr, i, 1)')
    code_parts.append('                        End If')
    code_parts.append('                        i = i + 1')
    code_parts.append('                    Loop')
    code_parts.append('                    i = i + 1')
    code_parts.append('                ElseIf valType = "t" Or valType = "f" Then')
    code_parts.append('                    If Mid(jsonStr, i, 4) = "true" Then')
    code_parts.append('                        val = True')
    code_parts.append('                        i = i + 4')
    code_parts.append('                    Else')
    code_parts.append('                        val = False')
    code_parts.append('                        i = i + 5')
    code_parts.append('                    End If')
    code_parts.append('                ElseIf valType = "n" Then')
    code_parts.append('                    val = Null')
    code_parts.append('                    i = i + 4')
    code_parts.append('                Else')
    code_parts.append('                    val = ""')
    code_parts.append('                    Do While i <= lenJson And Mid(jsonStr, i, 1) <> "," And Mid(jsonStr, i, 1) <> "}"')
    code_parts.append('                        val = val & Mid(jsonStr, i, 1)')
    code_parts.append('                        i = i + 1')
    code_parts.append('                    Loop')
    code_parts.append('                    If IsNumeric(val) Then')
    code_parts.append('                        If InStr(val, ".") > 0 Then')
    code_parts.append('                            val = CDbl(val)')
    code_parts.append('                        Else')
    code_parts.append('                            val = CLng(val)')
    code_parts.append('                        End If')
    code_parts.append('                    End If')
    code_parts.append('                End If')
    code_parts.append('                dict.Add key, val')
    code_parts.append('            End If')
    code_parts.append('        Else')
    code_parts.append('            i = i + 1')
    code_parts.append('        End If')
    code_parts.append('    Loop')
    code_parts.append('End Sub')
    code_parts.append('')
    code_parts.append('Function SerializeValue(v)')
    code_parts.append('    If IsNull(v) Or IsEmpty(v) Then')
    code_parts.append('        SerializeValue = "null"')
    code_parts.append('    ElseIf VarType(v) = vbBoolean Then')
    code_parts.append('        If v Then SerializeValue = "true" Else SerializeValue = "false"')
    code_parts.append('    ElseIf VarType(v) = vbInteger Or VarType(v) = vbLong Or VarType(v) = vbDouble Or VarType(v) = vbSingle Or VarType(v) = vbCurrency Or VarType(v) = vbDecimal Then')
    code_parts.append('        SerializeValue = CStr(v)')
    code_parts.append('    ElseIf VarType(v) = vbString Then')
    code_parts.append('        Dim escaped')
    code_parts.append('        escaped = Replace(v, "\\", "\\\\")')
    code_parts.append('        escaped = Replace(escaped, Chr(34), "\\" & Chr(34))')
    code_parts.append('        escaped = Replace(escaped, vbCr, "\\r")')
    code_parts.append('        escaped = Replace(escaped, vbLf, "\\n")')
    code_parts.append('        escaped = Replace(escaped, vbTab, "\\t")')
    code_parts.append('        SerializeValue = Chr(34) & escaped & Chr(34)')
    code_parts.append('    ElseIf IsArray(v) Then')
    code_parts.append('        Dim arrItems, j')
    code_parts.append('        arrItems = ""')
    code_parts.append('        For j = LBound(v) To UBound(v)')
    code_parts.append('            If j > LBound(v) Then arrItems = arrItems & ","')
    code_parts.append('            arrItems = arrItems & SerializeValue(v(j))')
    code_parts.append('        Next')
    code_parts.append('        SerializeValue = "[" & arrItems & "]"')
    code_parts.append('    ElseIf TypeName(v) = "Dictionary" Then')
    code_parts.append('        Dim dictItems, dictKeys, k')
    code_parts.append('        dictItems = ""')
    code_parts.append('        Set dictKeys = v.Keys')
    code_parts.append('        For Each k In dictKeys')
    code_parts.append('            If Len(dictItems) > 0 Then dictItems = dictItems & ","')
    code_parts.append('            dictItems = dictItems & Chr(34) & k & Chr(34) & ":" & SerializeValue(v.Item(k))')
    code_parts.append('        Next')
    code_parts.append('        SerializeValue = "{" & dictItems & "}"')
    code_parts.append('    Else')
    code_parts.append('        SerializeValue = Chr(34) & CStr(v) & Chr(34)')
    code_parts.append('    End If')
    code_parts.append('End Function')

    return '\n'.join(code_parts)


def _execute_vbs_code(code: str, func_name: str, cache_dir: str = None,
                      force: bool = False) -> str:
    """
    执行 VBScript 代码并返回输出

    参数：
        code: 完整 VBScript 源代码
        func_name: 函数名（用于生成文件名）
        cache_dir: 缓存目录，None 则使用 _VBS_CACHE_DIR
        force: 强制重新执行（忽略缓存）

    返回：
        VBScript 执行的输出结果（字符串）
    """
    if cache_dir is None:
        cache_dir = _VBS_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
    base_name = f'vbs_{func_name}_{code_hash}'
    src_path = os.path.join(cache_dir, f'{base_name}.vbs')

    if not force and os.path.exists(src_path):
        result = subprocess.run(
            [_CSCRIPT_PATH, '//Nologo', '//E:vbscript', src_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(code)

    result = subprocess.run(
        [_CSCRIPT_PATH, '//Nologo', '//E:vbscript', src_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'VBScript 执行失败:\n'
            f'stderr:\n{result.stderr}\n'
            f'stdout:\n{result.stdout}\n'
            f'代码:\n{code}'
        )

    return result.stdout.strip()


def _parse_vbs_output(output: str, ret_type: str):
    """
    解析 VBScript 输出结果

    参数：
        output: VBScript 输出的字符串
        ret_type: 期望的返回类型

    返回：
        Python 端的解码结果
    """
    if output == 'null' or output == '':
        return None

    if ret_type in ('Integer', 'Long'):
        try:
            return int(output)
        except ValueError:
            return output
    elif ret_type in ('Double', 'Single'):
        try:
            return float(output)
        except ValueError:
            return output
    elif ret_type == 'Boolean':
        if output.lower() in ('true', '1', 'yes'):
            return True
        elif output.lower() in ('false', '0', 'no', 'null'):
            return False
        return output
    elif ret_type in ('Variant()', 'list', 'array'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type in ('Dictionary', 'dict', 'hash'):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    elif ret_type == 'String':
        if output.startswith('"') and output.endswith('"') and len(output) >= 2:
            return output[1:-1].replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\t', '\t')
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
                if output.startswith('"') and output.endswith('"') and len(output) >= 2:
                    return output[1:-1].replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\t', '\t')
                return output


_code_cache = {}
_cache_lock = threading.Lock()


def _get_cached_code(func_name: str, code: str, force: bool = False) -> str:
    """获取缓存的代码路径，必要时重新生成"""
    with _cache_lock:
        cached = _code_cache.get(func_name)
        if not force and cached and cached[0] == code and os.path.exists(cached[1]):
            return cached[1]
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'vbs_{func_name}_{code_hash}'
        src_path = os.path.join(_VBS_CACHE_DIR, f'{base_name}.vbs')
        os.makedirs(_VBS_CACHE_DIR, exist_ok=True)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        _code_cache[func_name] = (code, src_path)
        return src_path


class VBScriptFuture:
    """VBScript 异步执行结果封装"""

    def __init__(self, future):
        self._future = future

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)


class VBScriptBridge(LangBridge):
    """
    VBScript 语言桥接实现

    继承 LangBridge 抽象基类，实现 VBScript 特定的代码生成、
    解释执行和调用逻辑。
    """

    name = 'vbscript'
    is_compiled = False
    lang_type = LangType.INTERPRETED
    file_ext = '.vbs'
    lib_ext = '.vbs'

    def __init__(self):
        super().__init__()
        _setup_vbs_env()

    def compiler_available(self) -> bool:
        """解释器是否可用"""
        return vbscript_compiler_available()

    def _execute_code(self, package_path, func_name, args, ret_type=None):
        """解包并执行代码，通过 _generate_vbs_source 构建完整执行脚本。"""
        import zipfile, tempfile, subprocess, os, shutil, json
        
        tmpdir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            source_file = os.path.join(tmpdir, self.get_source_filename(func_name))
            
            with open(source_file, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            # 构建参数字典和参数名列表
            args_dict = {}
            arg_names = []
            for i, arg in enumerate(args):
                arg_name = 'arg{}'.format(i)
                arg_names.append(arg_name)
                args_dict[arg_name] = arg
            
            args_json = json.dumps(args_dict, ensure_ascii=False)
            
            vbs_ret_type = get_vbs_type(ret_type) if ret_type is not None else 'Variant'
            vbs_argtypes = infer_vbs_argtypes(args)
            
            # 构建完整可执行脚本
            full_code = _generate_vbs_source(
                func_name=func_name,
                arg_names=arg_names,
                arg_vbs_types=vbs_argtypes,
                ret_vbs_type=vbs_ret_type,
                body=source_code,
                auto_signature=False,
                args_json=args_json,
            )
            
            # 写入并执行完整脚本
            exec_path = os.path.join(tmpdir, '_exec_{}.vbs'.format(func_name))
            with open(exec_path, 'w', encoding='utf-8') as f:
                f.write(full_code)
            
            result = subprocess.run(
                [_CSCRIPT_PATH, '//Nologo', '//E:vbscript', exec_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    'VBScript execution failed:\n'
                    'stderr:\n{}\n'
                    'stdout:\n{}'.format(result.stderr, result.stdout)
                )
            
            return _parse_vbs_output(result.stdout.strip(), vbs_ret_type)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 VBScript 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        parts = []

        if spec.module_code:
            parts.append(spec.module_code)
            parts.append('')

        for dep in spec.dependencies:
            dep_code = self._generate_function(dep)
            if dep_code:
                parts.append(dep_code)
                parts.append('')

        main_code = self._generate_function(spec)
        parts.append(main_code)

        return '\n'.join(parts)

    def _generate_function(self, spec: FunctionSpec) -> str:
        """生成单个函数的 VBScript 代码"""
        arg_names = []
        vbs_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                vbs_argtypes.append('Variant')
            else:
                vbs_argtypes.append(get_vbs_type(ann))

        ret_type = 'Variant'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'Variant'
            else:
                ret_type = get_vbs_type(ann)

        params_str = ', '.join(arg_names) if arg_names else ''

        body = spec.body
        if body:
            body = textwrap.dedent(body).strip()
            # 允许用户在函数体中使用 __FUNC__ 占位符指代当前函数名，
            # 解决 VBScript 需要通过函数名赋值返回值的场景。
            body = body.replace('__FUNC__', spec.name)

        indented_body = _preprocess_vbs_body(body, True)
        if indented_body:
            indented_body = '\n' + indented_body + '\n'
        else:
            indented_body = '\n'

        return f'Function {spec.name}({params_str}){indented_body}End Function'

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 VBScript 代码（对于解释型语言，直接保存源文件并返回路径）

        参数：
            code: VBScript 源代码
            func_name: 函数名（用于生成文件名）
            cache_dir: 缓存目录

        返回：
            源文件路径
        """
        if cache_dir is None:
            cache_dir = _VBS_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        base_name = f'vbs_{func_name}_{code_hash}'
        src_path = os.path.join(cache_dir, f'{base_name}.vbs')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return src_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译（处理）VBScript 项目

        VBScript 是解释型语言，project 模式的含义是：
        - 扫描 project_dir 下所有 .vbs 文件
        - entry='main' 时：返回主文件路径（project_dir/main.vbs），后续由调用方执行
        - entry!='main' 时：把所有 .vbs 文件打包成一个可执行的 vbs 文件，
          在文件末尾调用入口函数

        参数：
            project_dir: 项目目录路径
            entry: 入口函数名，'main' 表示执行主文件
            output_dir: 输出目录

        返回：
            产物路径（主文件路径 或 打包后的 vbs 文件路径）
        """
        output_dir = output_dir or _VBS_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        vbs_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.vbs'):
                    vbs_files.append(os.path.join(root, f))

        if not vbs_files:
            raise RuntimeError(f'No .vbs files found in project directory: {project_dir}')

        vbs_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            main_vbs = os.path.join(project_dir, 'main.vbs')
            if not os.path.exists(main_vbs):
                main_vbs = vbs_files[0]
            return main_vbs
        else:
            project_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:12]
            output_path = os.path.join(output_dir, f'vbs_proj_{project_name}_{entry}_{project_hash}.vbs')

            if os.path.exists(output_path):
                return output_path

            all_code = []
            all_code.append("' VBScript auto-generated project bundle")
            all_code.append(f"' Project: {project_name}")
            all_code.append("Option Explicit")
            all_code.append('')

            for vbs_file in vbs_files:
                rel_path = os.path.relpath(vbs_file, project_dir)
                all_code.append(f"' --- {rel_path} ---")
                with open(vbs_file, 'r', encoding='utf-8') as f:
                    all_code.append(f.read())
                all_code.append('')

            all_code.append("' Entry point call")
            all_code.append(f'WScript.StdOut.WriteLine CStr({entry}())')

            final_code = '\n'.join(all_code)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_code)

            return output_path

    def call_func(self, src_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 VBScript 函数（通过执行 vbs 文件）

        参数：
            src_path: VBScript 源文件路径
            func_name: 函数名
            args: 参数元组
            ret_type: 返回类型

        返回：
            函数返回值
        """
        vbs_ret_type = get_vbs_type(ret_type) if ret_type else 'Variant'

        args_dict = {}
        arg_names = []
        vbs_argtypes = infer_vbs_argtypes(args)

        spec = FunctionSpec(
            name=func_name,
            annotations={},
            args=(),
            defaults={},
            body='',
        )

        with open(src_path, 'r', encoding='utf-8') as f:
            code = f.read()

        for i, arg in enumerate(args):
            arg_name = f'arg{i}'
            arg_names.append(arg_name)
            args_dict[arg_name] = arg

        args_json = json.dumps(args_dict, ensure_ascii=False)

        full_code = _generate_vbs_source(
            func_name=func_name,
            arg_names=arg_names,
            arg_vbs_types=vbs_argtypes,
            ret_vbs_type=vbs_ret_type,
            body=code,
            auto_signature=False,
            args_json=args_json,
        )

        output = _execute_vbs_code(full_code, func_name)
        return _parse_vbs_output(output, vbs_ret_type)

    def run_project(self, project_dir: str, entry: str = 'main',
                    args: tuple = (), cache_dir: str = None) -> Any:
        """
        运行 VBScript 项目

        entry='main' 时：直接执行 cscript project_dir/main.vbs，返回 (returncode, stdout, stderr)
        entry!='main' 时：打包所有 vbs 文件后调用入口函数，返回函数结果
        """
        if entry == 'main':
            main_vbs = os.path.join(project_dir, 'main.vbs')
            if not os.path.exists(main_vbs):
                vbs_files = []
                for root, dirs, files in os.walk(project_dir):
                    for f in files:
                        if f.endswith('.vbs'):
                            vbs_files.append(os.path.join(root, f))
                if not vbs_files:
                    raise RuntimeError(f'No .vbs files found in project directory: {project_dir}')
                main_vbs = vbs_files[0]

            result = subprocess.run(
                [_CSCRIPT_PATH, '//Nologo', '//E:vbscript', main_vbs] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
            return (result.returncode, result.stdout, result.stderr)
        else:
            artifact_path = self.compile_project(project_dir, entry, cache_dir)
            return self.call_func(artifact_path, entry, args)


_vbscript_bridge = VBScriptBridge()


def compile_and_run(code: str, func_name: str = 'main',
                    args: tuple = (), ret_type=None,
                    cache_dir: str = None) -> Any:
    """
    编译并运行 VBScript 代码的便捷函数

    参数：
        code: VBScript 源代码
        func_name: 函数名
        args: 参数元组
        ret_type: 返回类型
        cache_dir: 缓存目录

    返回：
        函数执行结果
    """
    bridge = _vbscript_bridge
    src_path = bridge.compile_code(code, func_name, cache_dir)
    return bridge.call_func(src_path, func_name, args, ret_type)


vbscript = _vbscript_bridge.decorator
vbs = vbscript
