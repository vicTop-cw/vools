"""
vools.bridge.java.compiler - Java 编译支持

使用 javac 编译 Java 源码为 class 文件或 JAR。

用法：
    jar_path = compile_java('./src/main.java', output_dir='./target')
"""

import os
import sys
import json
import tempfile
import hashlib
import platform
import subprocess
import logging
from typing import Optional, List, Any

from .._base import LangBridge, FunctionSpec
from ..core.types import LangType

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

_JAVA_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_java_cache')

PY_TO_JAVA_TYPE = {
    int: 'int',
    float: 'double',
    bool: 'boolean',
    str: 'String',
    bytes: 'byte[]',
}


def _find_javac() -> Optional[str]:
    """查找 javac 命令路径"""
    import shutil
    return shutil.which('javac')


def _find_java() -> Optional[str]:
    """查找 java 命令路径"""
    import shutil
    return shutil.which('java')


def is_javac_available() -> bool:
    """检查 javac 编译器是否可用"""
    return _find_javac() is not None


def is_java_available() -> bool:
    """检查 Java 运行时是否可用"""
    return _find_java() is not None


def get_java_version() -> Optional[str]:
    """获取 Java 版本信息"""
    java_path = _find_java()
    if java_path is None:
        return None

    try:
        result = subprocess.run(
            ['java', '-version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return result.stderr.split('\n')[0]
    except Exception:
        return None


def compile_java(
    source_path: str,
    output_dir: Optional[str] = None,
    class_path: Optional[List[str]] = None,
    extra_args: Optional[List[str]] = None,
) -> Optional[str]:
    """
    编译 Java 源码

    参数：
        source_path: Java 源文件路径（.java）或包含源文件的目录
        output_dir: 输出目录，默认在源文件所在目录的 out 子目录
        class_path: 额外的 classpath 列表
        extra_args: 额外的编译参数

    返回：
        输出目录路径，失败返回 None
    """
    javac = _find_javac()
    if javac is None:
        logger.error("javac not found")
        return None

    if not os.path.exists(source_path):
        logger.error(f"Source file not found: {source_path}")
        return None

    # 确定输出目录
    if output_dir is None:
        source_dir = os.path.dirname(os.path.abspath(source_path))
        output_dir = os.path.join(source_dir, 'out')
    output_dir = os.path.abspath(output_dir)

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    try:
        cmd = [
            'javac',
            '-d', output_dir,
        ]

        if class_path:
            cmd.extend(['-classpath', os.pathsep.join(class_path)])

        if extra_args:
            cmd.extend(extra_args)

        # 添加源文件
        if os.path.isfile(source_path):
            cmd.append(source_path)
        else:
            # 编译目录下的所有 .java 文件
            for root, dirs, files in os.walk(source_path):
                for f in files:
                    if f.endswith('.java'):
                        cmd.append(os.path.join(root, f))

        logger.info(f"Compiling with javac: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error(f"Compilation failed: {result.stderr}")
            return None

        logger.info(f"Compilation successful: {output_dir}")
        return output_dir

    except subprocess.TimeoutExpired:
        logger.error("Compilation timed out")
        return None
    except Exception as e:
        logger.error(f"Compilation error: {e}")
        return None


def create_jar(
    class_dir: str,
    jar_path: str,
    main_class: Optional[str] = None,
):
    """
    将编译后的 class 文件打包为 JAR

    参数：
        class_dir: 编译后的 class 文件所在目录
        jar_path: 输出的 JAR 文件路径
        main_class: 主类名（用于创建可执行 JAR）

    返回：
        JAR 文件路径，失败返回 None
    """
    jar_exe = None
    import shutil
    for name in ['jar', 'jar.exe']:
        jar_exe = shutil.which(name)
        if jar_exe:
            break

    if jar_exe is None:
        logger.error("jar command not found")
        return None

    try:
        if main_class:
            cmd = ['jar', '-cfe', jar_path, main_class]
        else:
            cmd = ['jar', '-cf', jar_path]
        cmd.extend(['-C', class_dir])
        cmd.append('.')

        logger.info(f"Creating JAR: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=class_dir,
            timeout=60,
        )

        if result.returncode != 0:
            logger.error(f"JAR creation failed: stdout={result.stdout}, stderr={result.stderr}")
            return None

        logger.info(f"JAR created: {jar_path}")
        return jar_path

    except Exception as e:
        logger.error(f"JAR creation error: {e}")
        return None


def check_java_environment() -> dict:
    """
    检查 Java 编译和运行环境

    返回：
        dict: 包含各项检查结果的字典
    """
    return {
        'java_available': is_java_available(),
        'javac_available': is_javac_available(),
        'java_version': get_java_version(),
        'py4j_available': True,
    }


# ============================================================================
# JavaBridge - Java 桥接实现（继承 LangBridge）
# ============================================================================

class JavaBridge(LangBridge):
    """
    Java 语言桥接实现

    继承 LangBridge 抽象基类，实现 Java 特定的代码生成、编译和调用。
    使用 subprocess 调用 javac/java 进行编译和执行。
    """

    name = 'java'
    lang_type = LangType.JVM
    file_ext = '.java'
    lib_ext = '.jar'  # 实际编译产物是 JAR 而非 .class

    def __init__(self):
        super().__init__()
        self._package = ''

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return is_javac_available() and is_java_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Java 代码

        生成一个包含 public static 方法的 Java 类，
        类名与函数名一致（首字母大写）。
        使用简单的基于行的协议进行参数传递，不依赖第三方库。
        """
        import inspect

        parts = []

        class_name = self._to_class_name(spec.name)

        parts.append(f'public class {class_name} {{')
        parts.append('')

        if spec.module_code:
            for line in spec.module_code.split('\n'):
                parts.append(f'    {line}')
            parts.append('')

        for dep in spec.dependencies:
            dep_code = self._generate_method(dep, is_static=True)
            if dep_code:
                indented = ''
                for line in dep_code.split('\n'):
                    if line.strip():
                        indented += '    ' + line + '\n'
                    else:
                        indented += '\n'
                parts.append(indented)
                parts.append('')

        main_code = self._generate_method(spec, is_static=True, is_public=True)
        indented_main = ''
        for line in main_code.split('\n'):
            if line.strip():
                indented_main += '    ' + line + '\n'
            else:
                indented_main += '\n'
        parts.append(indented_main)

        arg_types = []
        arg_names = []
        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                arg_types.append(int)
            else:
                arg_types.append(ann)

        parts.append('    public static void main(String[] args) throws Exception {')
        parts.append('        java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));')
        parts.append('        java.io.PrintWriter writer = new java.io.PrintWriter(System.out, true);')
        parts.append('        String line;')
        parts.append('        while ((line = reader.readLine()) != null) {')
        parts.append('            line = line.trim();')
        parts.append('            if (line.isEmpty()) continue;')
        parts.append('            String[] parts = line.split("\\t", -1);')
        parts.append('            try {')

        call_args = []
        for i, (atype, aname) in enumerate(zip(arg_types, arg_names)):
            java_type = PY_TO_JAVA_TYPE.get(atype, 'String')
            if atype == int:
                parts.append(f'                int arg{i} = Integer.parseInt(parts[{i}]);')
                call_args.append(f'arg{i}')
            elif atype == float:
                parts.append(f'                double arg{i} = Double.parseDouble(parts[{i}]);')
                call_args.append(f'arg{i}')
            elif atype == bool:
                parts.append(f'                boolean arg{i} = Boolean.parseBoolean(parts[{i}]);')
                call_args.append(f'arg{i}')
            else:
                parts.append(f'                String arg{i} = parts[{i}];')
                call_args.append(f'arg{i}')

        ret_ann = spec.annotations.get('return')
        call_str = f'{spec.name}({", ".join(call_args)})'

        if ret_ann is None or ret_ann is type(None) or str(ret_ann).lower() == 'none':
            parts.append(f'                {call_str};')
            parts.append('                writer.println("OK");')
        else:
            parts.append(f'                Object result = {call_str};')
            parts.append('                writer.println(String.valueOf(result));')

        parts.append('            } catch (Exception e) {')
        parts.append('                writer.println("ERROR:" + e.getMessage());')
        parts.append('            }')
        parts.append('        }')
        parts.append('        reader.close();')
        parts.append('        writer.close();')
        parts.append('    }')
        parts.append('')

        parts.append('}')

        return '\n'.join(parts)

    def _generate_method(self, spec: FunctionSpec, is_static: bool = False,
                         is_public: bool = False) -> str:
        """生成单个方法的 Java 代码"""
        import inspect

        arg_names = []
        java_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            if ann is None or ann is inspect.Parameter.empty:
                java_argtypes.append('int')
            else:
                java_argtypes.append(PY_TO_JAVA_TYPE.get(ann, 'Object'))

        ret_type = 'void'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = PY_TO_JAVA_TYPE.get(ann, 'Object')

        params = []
        for i, java_t in enumerate(java_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{java_t} {name}')

        params_str = ', '.join(params)

        modifiers = []
        if is_public:
            modifiers.append('public')
        if is_static:
            modifiers.append('static')
        modifier_str = ' '.join(modifiers) + ' ' if modifiers else ''

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        return f'''{modifier_str}{ret_type} {spec.name}({params_str}) {{
{indented_body}}}'''

    def _to_class_name(self, func_name: str) -> str:
        """将函数名转换为类名（首字母大写）"""
        if not func_name:
            return 'VoolsJava'
        return func_name[0].upper() + func_name[1:]

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Java 代码，返回 JAR 文件路径

        由于 Java 调用需要 Gson 库来处理 JSON，这里采用简化方案：
        使用 ProcessBuilder 通过标准输入输出传递数据，避免额外依赖。
        """
        if cache_dir is None:
            cache_dir = _JAVA_CACHE_DIR

        os.makedirs(cache_dir, exist_ok=True)

        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]
        class_name = self._to_class_name(func_name)
        jar_name = f'java_{func_name}_{code_hash}'
        jar_path = os.path.join(cache_dir, f'{jar_name}.jar')

        if os.path.exists(jar_path):
            return jar_path

        java_file = os.path.join(cache_dir, f'{class_name}.java')
        with open(java_file, 'w', encoding='utf-8') as f:
            f.write(code)

        class_dir = os.path.join(cache_dir, f'{jar_name}_classes')
        os.makedirs(class_dir, exist_ok=True)

        javac = _find_javac()
        if javac is None:
            raise RuntimeError('javac not found')

        compile_cmd = [
            'javac',
            '-d', class_dir,
            java_file,
        ]

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=cache_dir,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Java compilation failed:\n{result.stderr}\n{result.stdout}'
            )

        jar_result = create_jar(class_dir, jar_path, main_class=class_name)
        if jar_result is None:
            raise RuntimeError('Failed to create JAR')

        try:
            os.remove(java_file)
            import shutil
            shutil.rmtree(class_dir, ignore_errors=True)
        except OSError:
            pass

        return jar_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Java 项目

        扫描 project_dir 下所有 .java 文件，调用 javac 编译，
        然后打包成 JAR。entry='main' 时创建可执行 JAR。
        """
        output_dir = output_dir or _JAVA_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        java_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.java'):
                    java_files.append(os.path.join(root, f))

        if not java_files:
            raise RuntimeError(f'No .java files found in project directory: {project_dir}')

        java_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        class_dir = os.path.join(output_dir, f'{project_name}_classes')
        os.makedirs(class_dir, exist_ok=True)

        javac = _find_javac()
        if javac is None:
            raise RuntimeError('javac not found')

        compile_cmd = [
            'javac',
            '-d', class_dir,
        ] + java_files

        result = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Java project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {java_files}'
            )

        jar_path = os.path.join(output_dir, f'{project_name}.jar')
        main_class = entry if entry != 'main' else None

        jar_result = create_jar(class_dir, jar_path, main_class=main_class)
        if jar_result is None:
            raise RuntimeError('Failed to create JAR')

        return jar_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Java 编译的函数

        通过 subprocess 调用 java 命令执行 JAR，
        使用基于行的协议（tab 分隔参数）通过标准输入输出传递数据。
        """
        java = _find_java()
        if java is None:
            raise RuntimeError('java not found')

        class_name = self._to_class_name(func_name)

        str_args = [str(a) for a in args]
        input_line = '\t'.join(str_args) + '\n'

        cmd = [
            'java',
            '-cp', lib_path,
            class_name,
        ]

        try:
            result = subprocess.run(
                cmd,
                input=input_line,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f'Java execution failed (code {result.returncode}):\n'
                    f'stderr: {result.stderr}\n'
                    f'stdout: {result.stdout}'
                )

            output = result.stdout.strip()
            if not output:
                return None

            if output.startswith('ERROR:'):
                raise RuntimeError(f'Java function error: {output[6:]}')

            if ret_type is not None:
                if ret_type == int:
                    try:
                        return int(output)
                    except (ValueError, TypeError):
                        return output
                elif ret_type == float:
                    try:
                        return float(output)
                    except (ValueError, TypeError):
                        return output
                elif ret_type == bool:
                    return output.lower() in ('true', '1', 'yes')
                elif ret_type == str:
                    return output

            return output

        except subprocess.TimeoutExpired:
            raise RuntimeError('Java execution timed out')

    def set_package(self, package: str):
        """设置 Java 包名"""
        self._package = package or ''


# 全局 JavaBridge 实例
_java_bridge = JavaBridge()
