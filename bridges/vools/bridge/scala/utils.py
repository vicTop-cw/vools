"""
vools.bridge.scala.utils - Scala 桥接辅助工具

提供常用工具函数，包括：
- Scala 代码模板生成
- JAR 检查和依赖分析
- Gateway 端口管理
"""

import os
import socket
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def find_available_port(start_port: int = 25333, end_port: int = 25399) -> Optional[int]:
    """
    查找可用的端口

    参数：
        start_port: 起始端口号
        end_port: 结束端口号

    返回：
        可用的端口号，未找到返回 None
    """
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    return None


def is_port_in_use(port: int) -> bool:
    """
    检查端口是否已被占用

    参数：
        port: 端口号

    返回：
        bool: 端口是否已被占用
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', port))
            return False
    except OSError:
        return True


def get_default_jar_path() -> Optional[str]:
    """
    获取默认的 Scala 应用 JAR 路径

    查找常见位置的 JAR 文件：
    - ./target/scala-*/app.jar
    - ./target/*.jar
    - ./lib/*.jar

    返回：
        JAR 文件路径，未找到返回 None
    """
    search_patterns = [
        './target/scala-*/app.jar',
        './target/*.jar',
        './lib/*.jar',
        './build/libs/*.jar',
    ]

    import glob

    for pattern in search_patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            # 返回最新的 JAR 文件
            newest = max(matches, key=os.path.getmtime)
            return newest

    return None


def check_jar_class(jar_path: str, class_name: str) -> bool:
    """
    检查 JAR 文件中是否包含指定的类

    参数：
        jar_path: JAR 文件路径
        class_name: 类名（可以是完全限定名或简单名）

    返回：
        bool: 类是否存在于 JAR 中
    """
    import zipfile

    if not os.path.exists(jar_path):
        return False

    try:
        with zipfile.ZipFile(jar_path, 'r') as zf:
            # 获取所有 .class 文件路径
            class_files = [f for f in zf.namelist() if f.endswith('.class')]

            # 转换为类名格式
            for cf in class_files:
                # path/to/package/ClassName.class -> package.path.to.ClassName
                class_path = cf[:-6].replace('/', '.')
                if class_path.endswith(class_name):
                    return True

    except Exception as e:
        logger.warning(f"Error checking JAR: {e}")

    return False


def list_jar_classes(jar_path: str) -> List[str]:
    """
    列出 JAR 文件中的所有类

    参数：
        jar_path: JAR 文件路径

    返回：
        类名字符串列表
    """
    import zipfile

    classes = []

    if not os.path.exists(jar_path):
        return classes

    try:
        with zipfile.ZipFile(jar_path, 'r') as zf:
            for f in zf.namelist():
                if f.endswith('.class') and '$' not in f[:-6]:
                    # 排除内部类
                    class_path = f[:-6].replace('/', '.')
                    classes.append(class_path)
    except Exception as e:
        logger.warning(f"Error listing JAR classes: {e}")

    return classes


def generate_scala_object(
    package_name: str,
    object_name: str,
    methods: Dict[str, Dict[str, Any]],
) -> str:
    """
    生成 Scala object 的代码模板

    参数：
        package_name: 包名，如 "com.example"
        object_name: 对象名，如 "MathUtils"
        methods: 方法定义字典，格式为：
            {
                'methodName': {
                    'params': [('paramName', 'paramType'), ...],
                    'return_type': 'ReturnType',
                    'body': '// Scala code'
                }
            }

    返回：
        Scala 源代码字符串

    用法：
        source = generate_scala_object(
            package_name="com.example",
            object_name="MathUtils",
            methods={
                'add': {
                    'params': [('a', 'Int'), ('b', 'Int')],
                    'return_type': 'Int',
                    'body': 'a + b'
                }
            }
        )
    """
    lines = []

    # 包声明
    if package_name:
        lines.append(f"package {package_name}")
        lines.append("")

    # 对象声明
    lines.append(f"object {object_name} {{")

    # 方法
    for method_name, method_def in methods.items():
        params = method_def.get('params', [])
        return_type = method_def.get('return_type', 'Unit')
        body = method_def.get('body', '')

        # 生成参数列表
        param_str = ', '.join([f"{name}: {ptype}" for name, ptype in params])

        lines.append(f"  def {method_name}({param_str}): {return_type} = {{")
        lines.append(f"    {body}")
        lines.append(f"  }}")
        lines.append("")

    lines.append("}")

    return '\n'.join(lines)


def generate_py4j_app(
    package_name: str = "com.example",
    object_name: str = "Py4jApp",
    port: int = 25333,
) -> str:
    """
    生成 Py4J Gateway 应用代码

    参数：
        package_name: 包名
        object_name: 对象名
        port: 默认端口

    返回：
        Scala 源代码
    """
    template = f'''package {package_name}

import py4j.GatewayServer

object {object_name} {{
  def main(args: Array[String]): Unit = {{
    val actualPort = if (args.nonEmpty) args(0).toInt else {port}
    val app = new {object_name.replace("App", "Application")}()
    val gateway = new GatewayServer(app, actualPort)
    gateway.start()
    println(s"Py4J Gateway started on port $actualPort")
    Thread.sleep(Long.MaxValue)
  }}
}}

class {object_name.replace("App", "Application")} {{
  // Add your methods here

  def hello(name: String): String = s"Hello, $name!"

  def add(a: Int, b: Int): Int = a + b
}}
'''
    return template


def scala_type_to_python(type_str: str) -> str:
    """
    转换 Scala 类型名为 Python 类型提示字符串

    参数：
        type_str: Scala 类型字符串

    返回：
        Python 类型提示字符串
    """
    type_map = {
        'Int': 'int',
        'Long': 'int',
        'Short': 'int',
        'Byte': 'int',
        'Float': 'float',
        'Double': 'float',
        'Boolean': 'bool',
        'String': 'str',
        'Unit': 'None',
        'Any': 'Any',
        'AnyRef': 'object',
        'List': 'list',
        'Seq': 'list',
        'Array': 'list',
        'Map': 'dict',
        'Set': 'set',
        'Option': 'Optional',
    }

    # 移除泛型参数
    base_type = type_str.split('[')[0].strip()

    # 处理基本类型
    if base_type in type_map:
        return type_map[base_type]

    # 处理 Option[T]
    if type_str.startswith('Option['):
        inner = type_str[7:-1]
        return f"Optional[{scala_type_to_python(inner)}]"

    # 保留原始类型
    return type_str


def validate_scala_identifier(name: str) -> bool:
    """
    验证是否是有效的 Scala 标识符

    参数：
        name: 标识符名称

    返回：
        bool: 是否有效
    """
    if not name:
        return False

    # 检查首字符
    first_char = name[0]
    if not (first_char.isalpha() or first_char == '_' or first_char == '$'):
        return False

    # 检查后续字符
    for char in name[1:]:
        if not (char.isalnum() or char == '_' or char == '$'):
            return False

    # 检查关键字
    keywords = {
        'abstract', 'case', 'catch', 'class', 'def', 'do', 'else',
        'extends', 'false', 'final', 'finally', 'for', 'forSome',
        'if', 'implicit', 'import', 'lazy', 'match', 'new', 'null',
        'object', 'override', 'package', 'private', 'protected',
        'return', 'sealed', 'super', 'this', 'throw', 'trait',
        'try', 'true', 'type', 'val', 'var', 'while', 'with', 'yield',
    }

    return name not in keywords


def parse_fully_qualified_name(fqn: str) -> tuple:
    """
    解析完全限定名为包名和简单名

    参数：
        fqn: 完全限定名，如 "com.example.MyObject"

    返回：
        (package_name, simple_name) 元组
    """
    parts = fqn.rsplit('.', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return '', fqn
