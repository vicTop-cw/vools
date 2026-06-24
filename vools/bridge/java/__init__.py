"""
vools.bridge.java - Java 语言桥接模块

使用 Py4J 实现 Python 到 Java 的跨语言调用。
支持通过 JVM Gateway 调用 Java 代码。

主要组件：
- JavaGateway: JVM Gateway 管理器
- java / java_async: 装饰器，将 Python 函数桥接到 Java 方法
- JavaTypeMapper: Python ↔ JVM 类型映射器
- JavaBridge: LangBridge 抽象基类的 Java 实现（代码生成、编译和调用

支持同步和异步两种模式。
"""

from .loader import JavaGateway, get_java_gateway, is_java_available
from .decorator import (
    java,
    java_gateway,
    java_async,
    java_static_bridge,
    bridge_java_class,
    ainvoke_java_method,
    abridge_java_class,
    JavaModule,
    AsyncJavaModule,
)
from .types import JavaTypeMapper
from .compiler import (
    JavaBridge,
    compile_java,
    create_jar,
    is_javac_available,
    check_java_environment,
    get_java_version,
    PY_TO_JAVA_TYPE,
)

__all__ = [
    'JavaGateway',
    'get_java_gateway',
    'is_java_available',
    'java',
    'java_gateway',
    'java_async',
    'java_static_bridge',
    'bridge_java_class',
    'ainvoke_java_method',
    'abridge_java_class',
    'JavaModule',
    'AsyncJavaModule',
    'JavaTypeMapper',
    'JavaBridge',
    'compile_java',
    'create_jar',
    'is_javac_available',
    'check_java_environment',
    'get_java_version',
    'PY_TO_JAVA_TYPE',
]
