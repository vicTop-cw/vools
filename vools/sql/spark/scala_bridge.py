"""
vools.sql.spark.scala_bridge - Scala 桥接模块

提供 PySpark 与 Scala/Java 的互操作能力，
支持调用 Scala 类、注册 Scala UDF、加载 Jar 包等功能。
"""

from typing import Any, Optional, Callable, List, Dict
import os


class ScalaBridge:
    """
    Scala 桥接类

    提供 PySpark 与 Scala/Java 互操作的便捷接口，
    基于 Py4J 实现 Python 与 JVM 的通信。

    用法：
        bridge = ScalaBridge(spark_connection)
        bridge.add_jar('/path/to/your.jar')
        result = bridge.call_scala_method('com.example.MyClass', 'myMethod', arg1, arg2)
    """

    def __init__(self, spark_connection):
        """
        初始化 Scala 桥接

        参数：
            spark_connection: SparkConnection 实例
        """
        self._conn = spark_connection
        self._jvm = None
        self._gateway = None

    @property
    def jvm(self):
        """获取 JVM 实例"""
        if self._jvm is None:
            if not self._conn.is_connected:
                raise RuntimeError("Spark 连接未建立，请先调用 connect()")
            self._jvm = self._conn.spark._jvm
        return self._jvm

    @property
    def gateway(self):
        """获取 Py4J Gateway 实例"""
        if self._gateway is None:
            if not self._conn.is_connected:
                raise RuntimeError("Spark 连接未建立，请先调用 connect()")
            self._gateway = self._conn.spark._sc._gateway
        return self._gateway

    def add_jar(self, jar_path: str) -> None:
        """
        添加 Jar 包到 Spark 上下文

        参数：
            jar_path: Jar 包路径，可以是本地路径或 HDFS 路径
        """
        if not os.path.exists(jar_path) and not jar_path.startswith(('hdfs://', 's3://', 'file:/')):
            raise FileNotFoundError(f"Jar 文件不存在: {jar_path}")
        self._conn.spark._sc.addPyFile(jar_path)
        self._conn.spark._jsc.addJar(jar_path)

    def add_jars(self, jar_paths: List[str]) -> None:
        """
        批量添加 Jar 包

        参数：
            jar_paths: Jar 包路径列表
        """
        for jar_path in jar_paths:
            self.add_jar(jar_path)

    def get_class(self, class_name: str) -> Any:
        """
        获取 Scala/Java 类对象

        参数：
            class_name: 完整的类名，如 'com.example.MyClass'

        返回：
            JavaClass 对象
        """
        return getattr(self.jvm, class_name)

    def new_instance(self, class_name: str, *args: Any) -> Any:
        """
        创建 Scala/Java 类的新实例

        参数：
            class_name: 完整的类名
            *args: 构造函数参数

        返回：
            类的实例对象
        """
        cls = self.get_class(class_name)
        return cls(*args)

    def call_static_method(self, class_name: str, method_name: str, *args: Any) -> Any:
        """
        调用 Scala/Java 类的静态方法

        参数：
            class_name: 完整的类名
            method_name: 方法名
            *args: 方法参数

        返回：
            方法返回值
        """
        cls = self.get_class(class_name)
        method = getattr(cls, method_name)
        return method(*args)

    def call_method(self, obj: Any, method_name: str, *args: Any) -> Any:
        """
        调用 Scala/Java 对象的实例方法

        参数：
            obj: Java 对象实例
            method_name: 方法名
            *args: 方法参数

        返回：
            方法返回值
        """
        method = getattr(obj, method_name)
        return method(*args)

    def register_scala_udf(self, name: str, scala_class_name: str, return_type: str = 'StringType') -> None:
        """
        注册 Scala UDF 到 Spark

        参数：
            name: UDF 名称
            scala_class_name: Scala UDF 类的完整类名
            return_type: 返回类型，如 'StringType', 'IntegerType', 'DoubleType' 等
        """
        spark = self._conn.spark
        jvm = self.jvm

        scala_udf = self.get_class(scala_class_name)
        udf_instance = scala_udf()

        types_cls = getattr(jvm, 'org.apache.spark.sql.types.DataTypes')
        return_type_obj = getattr(types_cls, return_type)

        udf_cls = getattr(jvm, 'org.apache.spark.sql.expressions.UserDefinedFunction')
        j_udf = udf_cls.apply(udf_instance, return_type_obj)

        spark._jsparkSession.udf().register(name, j_udf)

    def register_java_udf(self, name: str, java_class_name: str, return_type: str = 'StringType') -> None:
        """
        注册 Java UDF 到 Spark（同 register_scala_udf）

        参数：
            name: UDF 名称
            java_class_name: Java UDF 类的完整类名
            return_type: 返回类型
        """
        self.register_scala_udf(name, java_class_name, return_type)

    def create_scala_list(self, items: List[Any]) -> Any:
        """
        创建 Scala List

        参数：
            items: Python 列表

        返回：
            Scala List 对象
        """
        jvm = self.jvm
        array_list = jvm.java.util.ArrayList()
        for item in items:
            array_list.add(item)
        return jvm.scala.collection.JavaConverters.asScalaList(array_list)

    def create_scala_map(self, items: Dict[Any, Any]) -> Any:
        """
        创建 Scala Map

        参数：
            items: Python 字典

        返回：
            Scala Map 对象
        """
        jvm = self.jvm
        hash_map = jvm.java.util.HashMap()
        for key, value in items.items():
            hash_map.put(key, value)
        return jvm.scala.collection.JavaConverters.mapAsScalaMap(hash_map)

    def scala_to_python(self, scala_obj: Any) -> Any:
        """
        尝试将 Scala 对象转换为 Python 对象

        参数：
            scala_obj: Scala 对象

        返回：
            对应的 Python 对象
        """
        jvm = self.jvm
        try:
            if hasattr(scala_obj, 'size') and callable(getattr(scala_obj, 'size')):
                try:
                    return [scala_obj.apply(i) for i in range(scala_obj.size())]
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(scala_obj, 'length') and callable(getattr(scala_obj, 'length')):
                return [scala_obj.apply(i) for i in range(scala_obj.length())]
        except Exception:
            pass
        return scala_obj

    def set_jvm_property(self, key: str, value: str) -> None:
        """
        设置 JVM 系统属性

        参数：
            key: 属性名
            value: 属性值
        """
        self.jvm.System.setProperty(key, value)

    def get_jvm_property(self, key: str) -> Optional[str]:
        """
        获取 JVM 系统属性

        参数：
            key: 属性名

        返回：
            属性值，如果不存在返回 None
        """
        return self.jvm.System.getProperty(key)

    def run_spark_submit(
        self,
        main_class: str,
        jar_path: str,
        args: Optional[List[str]] = None,
        master: Optional[str] = None,
        deploy_mode: str = 'client',
        conf: Optional[Dict[str, str]] = None,
        spark_home: Optional[str] = None,
    ) -> int:
        """
        调用 spark-submit 提交 Scala/Java 应用

        参数：
            main_class: 主类名（包含包名）
            jar_path: Jar 包路径
            args: 应用参数列表
            master: Spark Master URL，默认使用当前连接的 master
            deploy_mode: 部署模式，'client' 或 'cluster'
            conf: 额外的 Spark 配置
            spark_home: Spark 安装目录，默认使用 SPARK_HOME 环境变量

        返回：
            进程退出码
        """
        import subprocess

        if spark_home is None:
            spark_home = os.environ.get('SPARK_HOME', '')

        if not spark_home:
            raise RuntimeError("未找到 SPARK_HOME，请设置 spark_home 参数或 SPARK_HOME 环境变量")

        spark_submit = os.path.join(spark_home, 'bin', 'spark-submit')
        if os.name == 'nt':
            spark_submit += '.cmd'

        cmd = [spark_submit]

        if master is None:
            master = self._conn._master
        if master:
            cmd.extend(['--master', master])

        cmd.extend(['--deploy-mode', deploy_mode])
        cmd.extend(['--class', main_class])

        if conf:
            for k, v in conf.items():
                cmd.extend(['--conf', f'{k}={v}'])

        cmd.append(jar_path)

        if args:
            cmd.extend(args)

        result = subprocess.run(cmd, text=True)
        return result.returncode


__all__ = [
    'ScalaBridge',
]
