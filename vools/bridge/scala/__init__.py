"""
vools.bridge.scala - Scala 语言桥接模块

使用 Py4J 实现 Python 到 Scala 的跨语言调用。
支持通过 JVM Gateway 调用 Scala/Java 代码。

主要组件：
- ScalaBridge: Scala 语言桥接实现（继承 LangBridge）
- scala_bridge: 全局 ScalaBridge 实例
- ScalaGateway: JVM Gateway 管理器
- scala / scala_async: 装饰器，将 Python 函数桥接到 Scala 方法
- ScalaTypeMapper: Python ↔ JVM 类型映射器

支持同步和异步两种模式。
"""

from .loader import ScalaGateway, get_scala_gateway, is_scala_available
from .decorator import (
    scala,
    scala_gateway,
    scala_async,
    scala_static_bridge,
    bridge_scala_class,
    ainvoke_scala_method,
    abridge_scala_class,
    ScalaModule,
    AsyncScalaModule,
)
from .types import ScalaTypeMapper
from .compiler import (
    ScalaBridge,
    scala_bridge,
    compile_scala,
    is_scala_compiler_available,
    is_java_available,
    get_scala_version,
    check_scala_environment,
    run_scala_app,
)

__all__ = [
    'ScalaBridge',
    'scala_bridge',
    'ScalaGateway',
    'get_scala_gateway',
    'is_scala_available',
    'scala',
    'scala_gateway',
    'scala_async',
    'scala_static_bridge',
    'bridge_scala_class',
    'ainvoke_scala_method',
    'abridge_scala_class',
    'ScalaModule',
    'AsyncScalaModule',
    'ScalaTypeMapper',
    'compile_scala',
    'is_scala_compiler_available',
    'is_java_available',
    'get_scala_version',
    'check_scala_environment',
    'run_scala_app',
]
