"""
vools.bridge.scala.compiler - Scala 源码编译支持

使用 scala-cli 或 scalac 编译 Scala 源码为 JAR 文件，
并提供便捷的编译和运行接口。

依赖：
- scala-cli (推荐): https://scala-cli.virtuslab.org/
- 或 scalac + scala-library

用法：
    # 编译 Scala 源码
    jar_path = compile_scala('./src/main.scala', output_dir='./target')

    # 编译并启动 Scala 应用
    run_scala_app('./src/main.scala', port=25333)
"""

import os
import subprocess
import tempfile
import logging
from typing import Optional, List, Any
import shutil
import inspect

from .._base import LangBridge, FunctionSpec

logger = logging.getLogger(__name__)


def _find_scala_compiler() -> Optional[str]:
    """
    查找可用的 Scala 编译器

    优先查找 scala-cli，其次查找 scalac

    返回：
        编译器路径，如果未找到返回 None
    """
    import shutil

    # 优先使用 scala-cli
    if shutil.which('scala-cli'):
        return 'scala-cli'

    # 回退到 scalac
    if shutil.which('scalac'):
        return 'scalac'

    return None


def _find_java() -> Optional[str]:
    """查找 java 命令路径"""
    import shutil
    return shutil.which('java')


def is_scala_compiler_available() -> bool:
    """
    检查 Scala 编译器是否可用

    返回：
        bool: scala-cli 或 scalac 是否可用
    """
    return _find_scala_compiler() is not None


def is_java_available() -> bool:
    """
    检查 Java 运行时是否可用

    返回：
        bool: java 命令是否可用
    """
    return _find_java() is not None


def get_scala_version() -> Optional[str]:
    """
    获取 Scala 版本信息

    返回：
        版本字符串，失败返回 None
    """
    compiler = _find_scala_compiler()
    if compiler is None:
        return None

    try:
        if compiler == 'scala-cli':
            result = subprocess.run(
                ['scala-cli', 'version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        else:
            result = subprocess.run(
                ['scalac', '-version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        return result.stdout + result.stderr
    except Exception:
        return None


def compile_scala(
    source_path: str,
    output_dir: Optional[str] = None,
    jar_name: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    class_path: Optional[List[str]] = None,
) -> Optional[str]:
    """
    编译 Scala 源码为 JAR 文件

    参数：
        source_path: Scala 源文件路径（.scala）或包含源文件的目录
        output_dir: 输出目录，默认在源文件所在目录的 target 子目录
        jar_name: 生成的 JAR 文件名（不含路径），默认使用源文件名
        extra_args: 额外的编译参数
        class_path: 额外的 classpath 列表

    返回：
        生成的 JAR 文件路径，失败返回 None

    用法：
        # 编译单个文件
        jar_path = compile_scala('./src/main.scala')

        # 指定输出目录和 JAR 名
        jar_path = compile_scala('./src/main.scala', output_dir='./target', jar_name='myapp.jar')

        # 带额外参数
        jar_path = compile_scala('./src/main.scala', extra_args=['-deprecation'])
    """
    compiler = _find_scala_compiler()
    if compiler is None:
        logger.error("Scala compiler not found (scala-cli or scalac)")
        return None

    if not os.path.exists(source_path):
        logger.error(f"Source file not found: {source_path}")
        return None

    # 确定输出目录
    if output_dir is None:
        source_dir = os.path.dirname(os.path.abspath(source_path))
        output_dir = os.path.join(source_dir, 'target')
    output_dir = os.path.abspath(output_dir)

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 确定 JAR 文件名和路径
    if jar_name is None:
        if os.path.isfile(source_path):
            jar_name = os.path.splitext(os.path.basename(source_path))[0] + '.jar'
        else:
            jar_name = 'app.jar'
    jar_path = os.path.join(output_dir, jar_name)

    try:
        if compiler == 'scala-cli':
            cmd = [
                'scala-cli',
                'package',
                source_path,
                '--output', jar_path,
                '--force',
            ]

            # 添加 scala-cli 特定的参数
            if class_path:
                cmd.extend(['--class-path', os.pathsep.join(class_path)])

            if extra_args:
                cmd.extend(extra_args)

            logger.info(f"Compiling with scala-cli: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )

        else:  # scalac
            cmd = [
                'scalac',
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
                # 编译目录下的所有 .scala 文件
                for root, dirs, files in os.walk(source_path):
                    for f in files:
                        if f.endswith('.scala'):
                            cmd.append(os.path.join(root, f))

            logger.info(f"Compiling with scalac: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )

            # scalac 不会自动生成 JAR，需要打包
            if result.returncode == 0 and not jar_path.endswith('.jar'):
                jar_path = jar_path + '.jar'

        if result.returncode != 0:
            logger.error(f"Compilation failed: {result.stderr}")
            return None

        logger.info(f"Compilation successful: {jar_path}")
        return jar_path

    except subprocess.TimeoutExpired:
        logger.error("Compilation timed out")
        return None
    except Exception as e:
        logger.error(f"Compilation error: {e}")
        return None


def create_py4j_jar(
    output_path: str,
    main_class: Optional[str] = None,
    scala_version: str = "2.13.12",
) -> Optional[str]:
    """
    创建一个支持 Py4J 的 Scala JAR 项目骨架

    生成包含 Py4J GatewayServer 启动代码的 Scala 源文件，
    并编译为 JAR。

    参数：
        output_path: 输出路径（.scala 文件路径或 .jar 路径）
        main_class: 主类全名，默认使用默认包
        scala_version: Scala 版本

    返回：
        生成的 JAR 文件路径
    """
    # 生成 Scala 源文件
    scala_source = f'''
import py4j.GatewayServer

object Py4jApp {{
  def main(args: Array[String]): Unit = {{
    val port = if (args.length > 0) args(0).toInt else 25333
    val app = new Py4jApplication
    val gatewayServer = new GatewayServer(app, port)
    gatewayServer.start()
    println(s"Py4J Gateway started on port $port")
    // 保持运行
    Thread.sleep(Long.MaxValue)
  }}
}}

class Py4jApplication {{
  // 在这里添加你的 Scala 方法

  def add(a: Int, b: Int): Int = a + b

  def multiply(a: Int, b: Int): Int = a * b

  def greet(name: String): String = s"Hello, $name!"

  def processList(items: java.util.List[String]): java.util.List[String] = {{
    items.stream().map(_.toUpperCase).collect(java.util.stream.Collectors.toList())
  }}
}}
'''

    # 写入临时文件
    temp_dir = tempfile.mkdtemp()
    scala_file = os.path.join(temp_dir, 'Py4jApp.scala')

    with open(scala_file, 'w', encoding='utf-8') as f:
        f.write(scala_source)

    try:
        # 编译
        jar_path = compile_scala(scala_file, output_dir=os.path.dirname(output_path) or temp_dir)

        if jar_path and os.path.exists(jar_path):
            # 复制到目标位置
            final_path = output_path if output_path.endswith('.jar') else jar_path
            if final_path != jar_path:
                shutil.copy(jar_path, final_path)
            return final_path

        return jar_path

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_scala_app(
    source_or_jar: str,
    port: int = 25333,
    wait_for_gateway: bool = True,
    timeout: int = 30,
) -> Optional[subprocess.Popen]:
    """
    运行 Scala 应用并启动 Py4J Gateway

    参数：
        source_or_jar: Scala 源文件路径或 JAR 文件路径
        port: Py4J Gateway 端口号
        wait_for_gateway: 是否等待 Gateway 就绪
        timeout: 等待超时时间（秒）

    返回：
        subprocess.Popen 对象，失败返回 None

    用法：
        # 运行 Scala 源文件
        proc = run_scala_app('./src/main.scala', port=25333)

        # 运行已编译的 JAR
        proc = run_scala_app('./target/myapp.jar', port=25333)
    """
    java_cmd = _find_java()
    if java_cmd is None:
        logger.error("Java not found")
        return None

    # 确定是源文件还是 JAR
    is_source = source_or_jar.endswith('.scala')

    if is_source:
        # 需要先编译
        jar_path = compile_scala(source_or_jar)
        if jar_path is None:
            return None
    else:
        if not os.path.exists(source_or_jar):
            logger.error(f"JAR file not found: {source_or_jar}")
            return None
        jar_path = source_or_jar

    # 启动 JVM 进程
    cmd = [
        java_cmd,
        '-jar', jar_path,
        str(port),
    ]

    logger.info(f"Starting Scala app: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 等待 Gateway 就绪
    if wait_for_gateway:
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            if proc.poll() is not None:
                # 进程已退出
                stdout, stderr = proc.communicate()
                logger.error(
                    f"Scala app exited with code {proc.returncode}\n"
                    f"stdout: {stdout.decode('utf-8', errors='replace')}\n"
                    f"stderr: {stderr.decode('utf-8', errors='replace')}"
                )
                return None

            # 尝试连接测试
            try:
                from .loader import ScalaGateway
                gateway = ScalaGateway(port=port)
                gateway.connect(port=port)
                gateway.stop()
                logger.info(f"Scala app is ready on port {port}")
                return proc
            except Exception:
                time.sleep(0.5)

        logger.warning("Timeout waiting for Scala app to be ready")

    return proc


# 便捷函数
def check_scala_environment() -> dict:
    """
    检查 Scala 编译和运行环境

    返回：
        dict: 包含各项检查结果的字典
    """
    return {
        'java_available': is_java_available(),
        'scala_compiler_available': is_scala_compiler_available(),
        'compiler': _find_scala_compiler(),
        'scala_version': get_scala_version(),
        'py4j_available': True,  # 如果能导入模块则已在 loader 中检查
    }


# Python 类型到 Scala 类型的映射
_PY_TO_SCALA_TYPE = {
    int: 'Int',
    float: 'Double',
    bool: 'Boolean',
    str: 'String',
    bytes: 'Array[Byte]',
    list: 'List[_]',
    dict: 'Map[_, _]',
    set: 'Set[_]',
    type(None): 'Unit',
}


def _get_scala_type(py_type) -> str:
    """将 Python 类型转换为 Scala 类型名"""
    if py_type is None or py_type is type(None):
        return 'Unit'
    if py_type is inspect.Parameter.empty:
        return 'Any'
    return _PY_TO_SCALA_TYPE.get(py_type, 'Any')


class ScalaBridge(LangBridge):
    """
    Scala 语言桥接实现

    继承 LangBridge 抽象基类，实现 Scala 特定的代码生成、编译和调用。
    使用 scalac 编译，通过 Py4J Gateway 调用。
    """

    name = 'scala'
    file_ext = '.scala'
    lib_ext = '.jar'

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return is_scala_compiler_available() and is_java_available()

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 Scala 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数（包装在 object 中）
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
        """生成单个函数的 Scala 代码（包装在 object 中）"""
        arg_names = []
        scala_argtypes = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            arg_names.append(name)
            scala_argtypes.append(_get_scala_type(ann))

        ret_type = 'Unit'
        if 'return' in spec.annotations:
            ret_type = _get_scala_type(spec.annotations['return'])

        params = []
        for i, scala_t in enumerate(scala_argtypes):
            name = arg_names[i] if i < len(arg_names) else f'arg{i}'
            params.append(f'{name}: {scala_t}')

        params_str = ', '.join(params)

        indented_body = ''
        for line in spec.body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        # 使用 object 包装，确保可以通过 Py4J 访问
        object_name = spec.name.capitalize() + 'Ops'
        return f'''object {object_name} {{
  def {spec.name}({params_str}): {ret_type} = {{
{indented_body}  }}
}}'''

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """
        编译 Scala 代码

        将代码写入临时 .scala 文件，使用 scalac 或 scala-cli 编译为 JAR 文件。
        """
        cache_dir = cache_dir or self.default_cache_dir()
        os.makedirs(cache_dir, exist_ok=True)

        scala_file = os.path.join(cache_dir, f'{func_name}.scala')
        with open(scala_file, 'w', encoding='utf-8') as f:
            f.write(code)

        jar_path = compile_scala(scala_file, output_dir=cache_dir, jar_name=f'{func_name}.jar')

        if jar_path is None:
            raise RuntimeError(f'Scala compilation failed for {func_name}')

        return jar_path

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 Scala 项目

        扫描 project_dir 下所有 .scala 文件，调用 scalac 编译器编译。
        entry='main' 时生成可执行 JAR，否则生成普通 JAR。
        """
        import subprocess

        output_dir = output_dir or self.default_cache_dir()
        os.makedirs(output_dir, exist_ok=True)

        scala_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.scala'):
                    scala_files.append(os.path.join(root, f))

        if not scala_files:
            raise RuntimeError(f'No .scala files found in project directory: {project_dir}')

        scala_files.sort()

        project_name = os.path.basename(os.path.abspath(project_dir))

        if entry == 'main':
            jar_name = f'{project_name}.jar'
        else:
            jar_name = f'{project_name}.jar'

        jar_path = os.path.join(output_dir, jar_name)

        compiler = _find_scala_compiler()
        if compiler is None:
            raise RuntimeError('Scala compiler not found')

        if compiler == 'scala-cli':
            cmd = [
                'scala-cli', 'package',
                project_dir,
                '--output', jar_path,
                '--force',
            ]
        else:  # scalac
            class_dir = os.path.join(output_dir, f'{project_name}_classes')
            os.makedirs(class_dir, exist_ok=True)

            cmd = ['scalac', '-d', class_dir] + scala_files

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=output_dir,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'Scala project compilation failed:\n'
                f'stderr:\n{result.stderr}\n'
                f'stdout:\n{result.stdout}\n'
                f'files: {scala_files}'
            )

        # scalac 需要手动打包 JAR
        if compiler == 'scalac':
            class_dir = os.path.join(output_dir, f'{project_name}_classes')
            jar_exe = shutil.which('jar') or shutil.which('jar.exe')
            if jar_exe is None:
                raise RuntimeError('jar command not found')

            jar_cmd = ['jar', '-cf', jar_path, '-C', class_dir, '.']
            jar_result = subprocess.run(
                jar_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                cwd=output_dir,
                timeout=60,
            )
            if jar_result.returncode != 0:
                raise RuntimeError(
                    f'JAR creation failed:\n{jar_result.stderr}'
                )

        return jar_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """
        调用 Scala 编译的函数

        通过 Py4J Gateway 调用 JAR 中的 Scala 方法。
        """
        from .loader import get_scala_gateway
        from .types import ScalaTypeMapper

        gateway = get_scala_gateway(jar_path=lib_path)

        if not gateway.is_connected:
            gateway.start()

        object_name = func_name.capitalize() + 'Ops'
        scala_obj = gateway.get_object(object_name)

        method = getattr(scala_obj, func_name)

        converted_args = []
        for arg in args:
            converted = ScalaTypeMapper.convert_to_jvm(arg)
            converted_args.append(converted)

        result = method(*converted_args)

        if ret_type is not None:
            result = ScalaTypeMapper.convert_to_py(result)

        return result


# 全局 ScalaBridge 实例
_scala_bridge = ScalaBridge()
scala_bridge = _scala_bridge
