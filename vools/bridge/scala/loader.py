"""
vools.bridge.scala.loader - Py4J JVM Gateway 加载器

管理 Py4J JavaGateway 的启动、连接和销毁，
提供统一的 Scala/Java 对象访问接口。

支持同步和异步两种模式。

使用 manager 统一管理编译器配置。
"""

import os
import asyncio
import subprocess
import threading
import logging
from typing import Optional, Any, Coroutine

from ..manager import get_helper

logger = logging.getLogger(__name__)

# 使用 manager 的编译器辅助
_scala_helper = get_helper('scala')

# 全局 Gateway 实例
_gateway: Optional['ScalaGateway'] = None
_gateway_lock = threading.Lock()


def is_scala_available() -> bool:
    """
    检查 Scala 环境是否可用

    使用 manager 统一管理。

    返回：
        bool: Scala 可用返回 True，否则返回 False
    """
    return _scala_helper.is_available()


class ScalaGateway:
    """
    Py4J Scala Gateway 管理器

    负责启动 JVM、连接 Gateway、提供对象访问能力。
    支持两种模式：
    1. 嵌入式：启动内置的 Py4J GatewayServer
    2. 客户端：连接已启动的 Scala/Java 应用

    属性：
        port: Gateway 端口号，默认 25333
        gateway: Py4J JavaGateway 实例
        entry_point: Scala/Java 入口对象的引用
    """

    def __init__(self, port: int = 25333, jar_path: str = None, javaopts: list = None):
        """
        初始化 ScalaGateway

        参数：
            port: Py4J Gateway 端口号，默认 25333
            jar_path: Scala/Java 应用的 JAR 文件路径（可选）
            javaopts: JVM 启动参数列表（可选）
        """
        self.port = port
        self.jar_path = jar_path
        self.javaopts = javaopts or []
        self.gateway = None
        self.entry_point = None
        self._process: Optional[subprocess.Popen] = None
        self._connected = False

    def start(self, app_class: str = None):
        """
        启动 JVM Gateway

        参数：
            app_class: Scala/Java 应用的主类名（当 jar_path 指定时）

        返回：
            self，支持链式调用
        """
        try:
            from py4j.java_gateway import JavaGateway, GatewayParameters
        except ImportError:
            raise ImportError(
                "Py4J is not installed. Please install it with: pip install py4j"
            )

        if self._connected:
            logger.warning("Gateway already connected")
            return self

        if self.jar_path:
            # 模式1: 启动 JAR 应用并连接
            self._start_jar_app(app_class)
            gateway_params = GatewayParameters(
                port=self.port,
                auto_convert=True,
                auto_close=True,
            )
            self.gateway = JavaGateway(gateway_parameters=gateway_params)
        else:
            # 模式2: 直接启动 Py4J Gateway Server（需要 Scala/Java 端配合）
            # 这种模式通常用于嵌入式 JVM
            gateway_params = GatewayParameters(
                port=self.port,
                auto_convert=True,
                auto_close=True,
            )
            self.gateway = JavaGateway(gateway_parameters=gateway_params)

        self.entry_point = self.gateway.jvm
        self._connected = True
        return self

    def _start_jar_app(self, app_class: str = None):
        """启动 JAR 应用作为后台进程"""
        if not os.path.exists(self.jar_path):
            raise FileNotFoundError(f"JAR file not found: {self.jar_path}")

        java_cmd = ['java']
        java_cmd.extend(self.javaopts)
        java_cmd.extend(['-jar', self.jar_path])
        if app_class:
            java_cmd.append(app_class)

        # 启动 JVM 进程
        self._process = subprocess.Popen(
            java_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待 JVM 启动
        import time
        time.sleep(2)

        if self._process.poll() is not None:
            stdout, stderr = self._process.communicate()
            raise RuntimeError(
                f"JVM process exited with code {self._process.returncode}\n"
                f"stdout: {stdout.decode('utf-8', errors='replace')}\n"
                f"stderr: {stderr.decode('utf-8', errors='replace')}"
            )

    def connect(self, port: int = None):
        """
        连接到已运行的 JVM Gateway

        参数：
            port: Gateway 端口号，默认使用初始化时的端口

        返回：
            self，支持链式调用
        """
        try:
            from py4j.java_gateway import JavaGateway, GatewayParameters
        except ImportError:
            raise ImportError(
                "Py4J is not installed. Please install it with: pip install py4j"
            )

        if self._connected:
            logger.warning("Gateway already connected")
            return self

        target_port = port or self.port
        gateway_params = GatewayParameters(
            port=target_port,
            auto_convert=True,
            auto_close=True,
        )
        self.gateway = JavaGateway(gateway_parameters=gateway_params)
        self.entry_point = self.gateway.jvm
        self._connected = True
        return self

    # ==================== 异步方法 ====================

    async def astart(self, app_class: str = None):
        """
        异步启动 JVM Gateway

        参数：
            app_class: Scala/Java 应用的主类名（当 jar_path 指定时）

        返回：
            self，支持链式调用
        """
        try:
            from py4j.java_gateway import JavaGateway, GatewayParameters
        except ImportError:
            raise ImportError(
                "Py4J is not installed. Please install it with: pip install py4j"
            )

        if self._connected:
            logger.warning("Gateway already connected")
            return self

        if self.jar_path:
            # 启动 JAR 应用
            self._start_jar_app(app_class)
            # 异步等待 JVM 启动
            await asyncio.sleep(2)
            gateway_params = GatewayParameters(
                port=self.port,
                auto_convert=True,
                auto_close=True,
            )
            self.gateway = JavaGateway(gateway_parameters=gateway_params)
        else:
            gateway_params = GatewayParameters(
                port=self.port,
                auto_convert=True,
                auto_close=True,
            )
            self.gateway = JavaGateway(gateway_parameters=gateway_params)

        self.entry_point = self.gateway.jvm
        self._connected = True
        return self

    async def aconnect(self, port: int = None):
        """
        异步连接到已运行的 JVM Gateway

        参数：
            port: Gateway 端口号，默认使用初始化时的端口

        返回：
            self，支持链式调用
        """
        try:
            from py4j.java_gateway import JavaGateway, GatewayParameters
        except ImportError:
            raise ImportError(
                "Py4J is not installed. Please install it with: pip install py4j"
            )

        if self._connected:
            logger.warning("Gateway already connected")
            return self

        target_port = port or self.port

        # 在线程池中执行阻塞的连接操作
        loop = asyncio.get_event_loop()
        gateway_params = GatewayParameters(
            port=target_port,
            auto_convert=True,
            auto_close=True,
        )

        self.gateway = await loop.run_in_executor(
            None,
            lambda: JavaGateway(gateway_parameters=gateway_params)
        )
        self.entry_point = self.gateway.jvm
        self._connected = True
        return self

    async def astop(self):
        """
        异步停止 Gateway 并清理资源
        """
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        'taskkill', '/F', '/PID', str(self._process.pid)
                    ) if os.name == 'nt' else asyncio.create_subprocess_exec(
                        'kill', str(self._process.pid)
                    ),
                    timeout=5
                )
            except Exception:
                pass

        if self.gateway:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.gateway.shutdown)
            except Exception:
                pass

        self.gateway = None
        self.entry_point = None
        self._connected = False
        self._process = None

    async def aget_object(self, fully_qualified_name: str) -> Any:
        """
        异步获取 Scala/Java 对象

        参数：
            fully_qualified_name: 对象的完全限定名

        返回：
            Py4J JavaObject 包装的对象引用
        """
        if not self._connected:
            raise RuntimeError("Gateway not connected. Call astart() or aconnect() first.")

        def _get():
            parts = fully_qualified_name.rsplit('.', 1)
            if len(parts) == 2:
                package, name = parts
                try:
                    pkg = getattr(self.entry_point, package)
                    return getattr(pkg, name)
                except AttributeError:
                    pass
            try:
                return getattr(self.entry_point, fully_qualified_name)
            except AttributeError:
                raise AttributeError(f"Cannot find object: {fully_qualified_name}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)

    async def acall_method(self, obj: Any, method_name: str, *args) -> Any:
        """
        异步调用对象的方法

        参数：
            obj: Scala/Java 对象
            method_name: 方法名
            *args: 方法参数

        返回：
            方法返回值
        """
        if not self._connected:
            raise RuntimeError("Gateway not connected. Call astart() or aconnect() first.")

        def _call():
            method = getattr(obj, method_name)
            return method(*args)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)

    def stop(self):
        """
        停止 Gateway 并清理资源
        """
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

        if self.gateway:
            try:
                self.gateway.shutdown()
            except Exception:
                pass

        self.gateway = None
        self.entry_point = None
        self._connected = False
        self._process = None

    def get_object(self, fully_qualified_name: str) -> Any:
        """
        获取 Scala/Java 对象

        参数：
            fully_qualified_name: 对象的完全限定名，
                                   如 "com.example.MyObject"

        返回：
            Py4J JavaObject 包装的对象引用
        """
        if not self._connected:
            raise RuntimeError("Gateway not connected. Call start() or connect() first.")

        # 使用 entry_point 获取静态对象或单例
        parts = fully_qualified_name.rsplit('.', 1)
        if len(parts) == 2:
            package, name = parts
            try:
                pkg = getattr(self.entry_point, package)
                return getattr(pkg, name)
            except AttributeError:
                pass

        # 直接从 jvm 获取
        try:
            return getattr(self.entry_point, fully_qualified_name)
        except AttributeError:
            raise AttributeError(
                f"Cannot find object: {fully_qualified_name}"
            )

    def call_method(self, obj: Any, method_name: str, *args) -> Any:
        """
        调用对象的方法

        参数：
            obj: Scala/Java 对象
            method_name: 方法名
            *args: 方法参数

        返回：
            方法返回值
        """
        if not self._connected:
            raise RuntimeError("Gateway not connected. Call start() or connect() first.")

        method = getattr(obj, method_name)
        return method(*args)

    def new_instance(self, class_name: str, *args) -> Any:
        """
        创建新实例

        参数：
            class_name: 类名，如 "java.util.ArrayList"
            *args: 构造器参数

        返回：
            新创建的对象实例
        """
        if not self._connected:
            raise RuntimeError("Gateway not connected. Call start() or connect() first.")

        clazz = self.get_object(class_name)
        return clazz(*args)

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.stop()
        return False

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.astart()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.astop()
        return False

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected


def get_scala_gateway(jar_path: str = None, port: int = 25333) -> ScalaGateway:
    """
    获取全局 ScalaGateway 实例（单例模式）

    参数：
        jar_path: Scala/Java 应用的 JAR 文件路径
        port: Gateway 端口号

    返回：
        ScalaGateway 实例
    """
    global _gateway

    with _gateway_lock:
        if _gateway is None:
            _gateway = ScalaGateway(port=port, jar_path=jar_path)
        return _gateway


def is_scala_available() -> bool:
    """
    检查 Scala 桥接是否可用

    检查条件：
    1. py4j 库已安装
    2. java 命令可用（可选，检查 JAR 模式时需要）

    返回：
        bool: Scala 桥接是否可用
    """
    # 检查 py4j
    try:
        from py4j.java_gateway import JavaGateway
    except ImportError:
        logger.debug("Py4J is not installed")
        return False

    # 检查 java 命令（用于 JAR 模式）
    import shutil
    java_available = shutil.which('java') is not None
    if not java_available:
        logger.debug("Java command not available")

    return True


def check_scala_runtime() -> dict:
    """
    检查 Scala 运行时环境

    返回：
        dict: 包含各项检查结果的字典
            - py4j_available: bool
            - java_available: bool
            - java_version: str or None
            - scala_version: str or None
    """
    result = {
        'py4j_available': False,
        'java_available': False,
        'java_version': None,
        'scala_version': None,
    }

    # 检查 py4j
    try:
        from py4j.java_gateway import JavaGateway
        result['py4j_available'] = True
    except ImportError:
        pass

    # 检查 java
    import shutil
    if shutil.which('java'):
        result['java_available'] = True
        try:
            proc = subprocess.run(
                ['java', '-version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True
            )
            # java -version 输出到 stderr
            version_line = proc.stderr.split('\n')[0]
            result['java_version'] = version_line
        except Exception:
            pass

    # 检查 scala
    if shutil.which('scala'):
        try:
            proc = subprocess.run(
                ['scala', '-version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True
            )
            result['scala_version'] = proc.stdout + proc.stderr
        except Exception:
            pass

    return result
