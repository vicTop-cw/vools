"""
vools.bridge.scala.decorator - Scala 桥接装饰器

提供 @scala 装饰器（基于 LangBridge 的编译执行模式），
以及基于 Py4J 的 Scala Gateway 桥接装饰器。
支持同步和异步两种模式。
"""

import functools
import inspect
import logging
from typing import Callable, Optional, Any

from .compiler import _scala_bridge
from .loader import get_scala_gateway, is_scala_available
from .types import ScalaTypeMapper

logger = logging.getLogger(__name__)

scala = _scala_bridge.decorator


def scala_gateway(
    fallback: Optional[Callable] = None,
    class_name: Optional[str] = None,
    method_name: Optional[str] = None,
    jar_path: Optional[str] = None,
    port: int = 25333,
    auto_convert: bool = True,
):
    """
    Scala Gateway 桥接装饰器（Py4J 模式）

    将一个 Python 函数标记为可以使用 Scala 实现。
    如果 Scala Gateway 可用，将调用对应的 Scala 方法；否则调用 fallback。

    支持从函数签名的类型注解自动推断参数类型和返回类型。

    参数：
        fallback: Python 回退实现函数，当 Scala 不可用时调用
        class_name: Scala/Java 类的完全限定名，
                   如 "com.example.MyObject" 或 "MyObject"
        method_name: Scala/Java 方法名（默认使用 Python 函数名）
        jar_path: Scala 应用的 JAR 文件路径（可选）
        port: Py4J Gateway 端口号，默认 25333
        auto_convert: 是否自动转换参数和返回值类型，默认 True

    返回：
        装饰器函数

    用法：

        @scala_gateway(class_name="com.example.MathUtils")
        def add(a: int, b: int) -> int:
            pass

        @scala_gateway(class_name="com.example.StringUtils", method_name="reverse")
        def reverse_string(s: str) -> str:
            pass

        @scala_gateway(class_name="com.example.Crypto", fallback=_py_md5)
        def md5_hash(data: str) -> str:
            pass
    """
    def decorator(func: Callable) -> Callable:
        nonlocal method_name, class_name

        if method_name is None:
            method_name = func.__name__

        # 获取函数签名信息
        sig = inspect.signature(func)
        param_names = []
        param_types = []
        for name, param in sig.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            param_names.append(name)
            if param.annotation is not param.empty:
                param_types.append(param.annotation)
            else:
                param_types.append(None)

        return_annotation = sig.return_annotation
        if return_annotation is sig.empty:
            return_annotation = None

        _cached_object = None
        _gateway_initialized = False

        def _get_scala_object():
            """获取 Scala/Java 对象引用"""
            nonlocal _cached_object, _gateway_initialized, class_name

            if _cached_object is not None:
                return _cached_object

            if not _gateway_initialized:
                gateway = get_scala_gateway(jar_path=jar_path, port=port)
                if not gateway.is_connected:
                    gateway.connect(port=port)
                _gateway_initialized = True

            if class_name is None:
                raise ValueError("class_name must be specified")

            gateway = get_scala_gateway()
            _cached_object = gateway.get_object(class_name)
            return _cached_object

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 绑定参数
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            call_args = list(bound_args.arguments.values())

            # 检查 Scala 是否可用
            if not is_scala_available():
                logger.debug("Scala bridge not available, using fallback")
                if fallback is not None:
                    return fallback(*args, **kwargs)
                raise RuntimeError(
                    f"Scala bridge is not available for '{func.__name__}' "
                    f"and no fallback was provided"
                )

            try:
                # 获取 Scala 对象
                scala_obj = _get_scala_object()

                # 获取方法
                method = getattr(scala_obj, method_name)

                # 转换参数（如果启用自动转换）
                if auto_convert:
                    converted_args = []
                    for arg, py_type in zip(call_args, param_types):
                        if py_type is not None:
                            converted = ScalaTypeMapper.convert_to_jvm(arg, py_type)
                            converted_args.append(converted)
                        else:
                            converted_args.append(arg)
                    call_args = converted_args

                # 调用方法
                result = method(*call_args)

                # 转换返回值（如果启用自动转换）
                if auto_convert and return_annotation is not None:
                    result = ScalaTypeMapper.convert_to_py(result)

                return result

            except Exception as e:
                logger.warning(
                    f"Scala bridge call failed for '{func.__name__}': {e}"
                )
                if fallback is not None:
                    return fallback(*args, **kwargs)
                raise

        # 保存桥接信息
        wrapper._scala_bridge_info = {
            'class_name': class_name,
            'method_name': method_name,
            'jar_path': jar_path,
            'port': port,
            'fallback': fallback,
            'param_names': param_names,
            'param_types': param_types,
            'return_annotation': return_annotation,
        }

        return wrapper

    return decorator


def scala_static_bridge(
    fallback: Optional[Callable] = None,
    class_name: Optional[str] = None,
    method_name: Optional[str] = None,
    jar_path: Optional[str] = None,
    port: int = 25333,
):
    """
    Scala 静态方法桥接装饰器（Py4J 模式）

    与 @scala_gateway 类似，但专门用于调用 Scala 静态方法（单例对象或伴生对象）。

    参数：
        fallback: Python 回退实现函数
        class_name: Scala 对象的完全限定名（单例对象名）
        method_name: 方法名（默认使用 Python 函数名）
        jar_path: JAR 文件路径
        port: Gateway 端口

    用法：
        @scala_static_bridge(class_name="com.example.Math$.MODULE$")
        def add(a: int, b: int) -> int:
            pass
    """
    return scala_gateway(
        fallback=fallback,
        class_name=class_name,
        method_name=method_name,
        jar_path=jar_path,
        port=port,
    )


class ScalaModule:
    """
    Scala 模块封装类

    将一个类中的所有方法桥接到 Scala。

    用法：
        @ScalaModule(class_name="com.example.DataProcessor")
        class DataProcessor:
            def process(self, data: str) -> str:
                pass

            def batch_process(self, items: list) -> list:
                pass
    """

    def __init__(self, class_name: str, jar_path: str = None, port: int = 25333):
        """
        初始化 ScalaModule

        参数：
            class_name: Scala/Java 类的完全限定名
            jar_path: JAR 文件路径（可选）
            port: Gateway 端口
        """
        self.class_name = class_name
        self.jar_path = jar_path
        self.port = port
        self._obj = None

    def __call__(self, cls):
        """装饰器调用"""
        # 保存原始类信息
        original_cls = cls

        # 创建新类，包装所有方法
        class ScalaModuleWrapper(cls):
            _scala_module_info = {
                'class_name': self.class_name,
                'jar_path': self.jar_path,
                'port': self.port,
            }

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                from .loader import get_scala_gateway
                gateway = get_scala_gateway(jar_path=self.jar_path, port=self.port)
                if not gateway.is_connected:
                    gateway.connect(port=self.port)
                self._scala_obj = gateway.get_object(self.class_name)

            def __getattribute__(self, name):
                # 先尝试从 Scala 对象获取
                if name.startswith('_'):
                    return super().__getattribute__(name)

                try:
                    scala_obj = object.__getattribute__(self, '_scala_obj')
                    method = getattr(scala_obj, name)
                    return method
                except AttributeError:
                    # 回退到 Python 实现
                    return super().__getattribute__(name)

        ScalaModuleWrapper.__name__ = original_cls.__name__
        ScalaModuleWrapper.__qualname__ = original_cls.__qualname__
        ScalaModuleWrapper.__module__ = original_cls.__module__

        return ScalaModuleWrapper


# 便捷函数
def bridge_scala_class(
    class_name: str,
    jar_path: str = None,
    port: int = 25333,
):
    """
    创建一个 Scala 类的 Python 代理

    参数：
        class_name: Scala/Java 类的完全限定名
        jar_path: JAR 文件路径
        port: Gateway 端口

    返回：
        Scala 对象的 Python 代理

    用法：
        Math = bridge_scala_class("com.example.Math$MODULE$")
        result = Math.add(1, 2)
    """
    gateway = get_scala_gateway(jar_path=jar_path, port=port)
    if not gateway.is_connected:
        gateway.connect(port=port)
    return gateway.get_object(class_name)


# ==================== 异步版本 ====================


def scala_async(
    fallback: Optional[Callable] = None,
    class_name: Optional[str] = None,
    method_name: Optional[str] = None,
    jar_path: Optional[str] = None,
    port: int = 25333,
    auto_convert: bool = True,
):
    """
    Scala 异步桥接装饰器

    将一个 async 函数标记为可以使用 Scala 实现。
    如果 Scala Gateway 可用，将异步调用对应的 Scala 方法；否则调用 fallback。

    支持从函数签名的类型注解自动推断参数类型和返回类型。

    参数：
        fallback: async 函数的回退实现，当 Scala 不可用时调用
        class_name: Scala/Java 类的完全限定名
        method_name: Scala/Java 方法名（默认使用 Python 函数名）
        jar_path: Scala 应用的 JAR 文件路径（可选）
        port: Py4J Gateway 端口号，默认 25333
        auto_convert: 是否自动转换参数和返回值类型，默认 True

    返回：
        装饰器函数

    用法：

        @scala_async_bridge(class_name="com.example.MathUtils")
        async def add(a: int, b: int) -> int:
            pass

        # 带 fallback
        @scala_async_bridge(class_name="com.example.Crypto", fallback=_async_py_md5)
        async def md5_hash(data: str) -> str:
            pass

        # 在 async 函数中使用
        async def main():
            result = await add(1, 2)
    """
    def decorator(func: Callable):
        nonlocal method_name, class_name

        if method_name is None:
            method_name = func.__name__

        # 获取函数签名信息
        sig = inspect.signature(func)
        param_names = []
        param_types = []
        for name, param in sig.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            param_names.append(name)
            if param.annotation is not param.empty:
                param_types.append(param.annotation)
            else:
                param_types.append(None)

        return_annotation = sig.return_annotation
        if return_annotation is sig.empty:
            return_annotation = None

        _cached_object = None
        _gateway_initialized = False

        async def _get_scala_object():
            """异步获取 Scala/Java 对象引用"""
            nonlocal _cached_object, _gateway_initialized, class_name

            if _cached_object is not None:
                return _cached_object

            if not _gateway_initialized:
                gateway = get_scala_gateway(jar_path=jar_path, port=port)
                if not gateway.is_connected:
                    await gateway.aconnect(port=port)
                _gateway_initialized = True

            if class_name is None:
                raise ValueError("class_name must be specified")

            gateway = get_scala_gateway()
            _cached_object = await gateway.aget_object(class_name)
            return _cached_object

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 绑定参数
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            call_args = list(bound_args.arguments.values())

            # 检查 Scala 是否可用
            if not is_scala_available():
                logger.debug("Scala bridge not available, using fallback")
                if fallback is not None:
                    return await fallback(*args, **kwargs)
                raise RuntimeError(
                    f"Scala bridge is not available for '{func.__name__}' "
                    f"and no fallback was provided"
                )

            try:
                # 异步获取 Scala 对象
                scala_obj = await _get_scala_object()

                # 获取方法
                method = getattr(scala_obj, method_name)

                # 转换参数（如果启用自动转换）
                if auto_convert:
                    converted_args = []
                    for arg, py_type in zip(call_args, param_types):
                        if py_type is not None:
                            converted = ScalaTypeMapper.convert_to_jvm(arg, py_type)
                            converted_args.append(converted)
                        else:
                            converted_args.append(arg)
                    call_args = converted_args

                # 异步调用方法
                gateway = get_scala_gateway()
                result = await gateway.acall_method(scala_obj, method_name, *call_args)

                # 转换返回值（如果启用自动转换）
                if auto_convert and return_annotation is not None:
                    result = ScalaTypeMapper.convert_to_py(result)

                return result

            except Exception as e:
                logger.warning(
                    f"Scala async bridge call failed for '{func.__name__}': {e}"
                )
                if fallback is not None:
                    return await fallback(*args, **kwargs)
                raise

        # 保存桥接信息
        wrapper._scala_bridge_info = {
            'class_name': class_name,
            'method_name': method_name,
            'jar_path': jar_path,
            'port': port,
            'fallback': fallback,
            'param_names': param_names,
            'param_types': param_types,
            'return_annotation': return_annotation,
            'is_async': True,
        }

        return wrapper

    return decorator


async def ainvoke_scala_method(
    class_name: str,
    method_name: str,
    *args,
    jar_path: str = None,
    port: int = 25333,
    auto_convert: bool = True,
):
    """
    异步调用 Scala 方法

    这是一个便捷函数，直接调用 Scala 方法而无需使用装饰器。

    参数：
        class_name: Scala/Java 类的完全限定名
        method_name: 方法名
        *args: 方法参数
        jar_path: JAR 文件路径（可选）
        port: Gateway 端口，默认 25333
        auto_convert: 是否自动转换类型

    返回：
        方法返回值

    用法：
        result = await ainvoke_scala_method(
            "com.example.MathUtils",
            "add",
            1, 2
        )
    """
    gateway = get_scala_gateway(jar_path=jar_path, port=port)

    if not gateway.is_connected:
        await gateway.aconnect(port=port)

    scala_obj = await gateway.aget_object(class_name)
    method = getattr(scala_obj, method_name)

    if auto_convert:
        # 转换参数
        converted_args = []
        for arg in args:
            converted = ScalaTypeMapper.convert_to_jvm(arg)
            converted_args.append(converted)
        args = converted_args

    result = await gateway.acall_method(scala_obj, method_name, *args)

    if auto_convert:
        result = ScalaTypeMapper.convert_to_py(result)

    return result


async def abridge_scala_class(
    class_name: str,
    jar_path: str = None,
    port: int = 25333,
):
    """
    异步创建一个 Scala 类的 Python 代理

    参数：
        class_name: Scala/Java 类的完全限定名
        jar_path: JAR 文件路径
        port: Gateway 端口

    返回：
        Scala 对象的 Python 代理

    用法：
        async def main():
            Math = await abridge_scala_class("com.example.Math$MODULE$")
            result = Math.add(1, 2)
    """
    gateway = get_scala_gateway(jar_path=jar_path, port=port)
    if not gateway.is_connected:
        await gateway.aconnect(port=port)
    return await gateway.aget_object(class_name)


class AsyncScalaModule:
    """
    异步 Scala 模块封装类

    将一个类中的所有 async 方法桥接到 Scala。

    用法：
        @AsyncScalaModule(class_name="com.example.DataProcessor")
        class DataProcessor:
            async def process(self, data: str) -> str:
                pass

            async def batch_process(self, items: list) -> list:
                pass
    """

    def __init__(self, class_name: str, jar_path: str = None, port: int = 25333):
        self.class_name = class_name
        self.jar_path = jar_path
        self.port = port
        self._obj = None

    def __call__(self, cls):
        original_cls = cls

        class AsyncScalaModuleWrapper(cls):
            _scala_module_info = {
                'class_name': self.class_name,
                'jar_path': self.jar_path,
                'port': self.port,
                'is_async': True,
            }

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                from .loader import get_scala_gateway
                self._gateway = get_scala_gateway(jar_path=self.jar_path, port=self.port)
                self._scala_obj = None

            async def _get_scala_obj(self):
                if self._scala_obj is None:
                    if not self._gateway.is_connected:
                        await self._gateway.aconnect(port=self.port)
                    self._scala_obj = await self._gateway.aget_object(self.class_name)
                return self._scala_obj

            async def __getattribute__(self, name):
                if name.startswith('_'):
                    return object.__getattribute__(self, name)

                try:
                    scala_obj = await self._get_scala_obj()
                    method = getattr(scala_obj, name)
                    return method
                except AttributeError:
                    return object.__getattribute__(self, name)

        AsyncScalaModuleWrapper.__name__ = original_cls.__name__
        AsyncScalaModuleWrapper.__qualname__ = original_cls.__qualname__
        AsyncScalaModuleWrapper.__module__ = original_cls.__module__

        return AsyncScalaModuleWrapper
