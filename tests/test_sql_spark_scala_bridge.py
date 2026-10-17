# -*- coding: utf-8 -*-
"""测试 vools.sql.spark.scala_bridge（用 fake JVM 避免启动 PySpark）。"""

import os
import sys
import types
import pytest
from vools.sql.spark.scala_bridge import ScalaBridge
from vools.sql.spark.connection import SparkConnection

__all__ = ["TestInit", "TestJvm", "TestGateway", "TestAddJar", "TestGetClass",
           "TestNewInstance", "TestCall", "TestUdf", "TestScalaColl",
           "TestScalaToPython", "TestJvmProperty", "TestRunSparkSubmit",
           "TestImport"]


class FakeJvmNS:
    """模拟 jvm.java.util.ArrayList 等命名空间。"""


class FakeUDF:
    @staticmethod
    def apply(udf_instance, return_type_obj):
        return ("UDF", udf_instance, return_type_obj)


class _Dotted:
    """模拟 Py4J JavaPackage：getattr 支持点分路径，未知叶子可调用。"""

    def __init__(self):
        self._children = {}
        self._leaf = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        parts = name.split(".")
        obj = self
        for p in parts:
            if p in obj._leaf:
                return obj._leaf[p]
            if p not in obj._children:
                obj._children[p] = _Dotted()
            obj = obj._children[p]
        return obj

    def __call__(self, *a, **kw):
        return _FakeAny()

    def _set_leaf(self, name, value):
        parts = name.split(".")
        obj = self
        for p in parts[:-1]:
            if p not in obj._children:
                obj._children[p] = _Dotted()
            obj = obj._children[p]
        obj._leaf[parts[-1]] = value


class _FakeAny:
    """任何操作都返回自身的占位对象。"""
    def __call__(self, *a, **kw):
        return self

    def __getattr__(self, name):
        return self


class FakeSparkConn:
    """带 is_connected / spark 的假连接。"""
    def __init__(self, connected=True):
        self.is_connected = connected
        self._master = "local[1]"
        self._jvm = _make_jvm()
        self.spark = types.SimpleNamespace(
            _jvm=self._jvm,
            _sc=types.SimpleNamespace(_gateway=object(), addPyFile=lambda p: None),
            _jsc=types.SimpleNamespace(addJar=lambda p: None),
            _jsparkSession=types.SimpleNamespace(
                udf=lambda: types.SimpleNamespace(register=lambda n, u: None)
            ),
        )


def _make_jvm():
    """构建一个带点分路径解析的假 JVM。"""
    jvm = _Dotted()
    jvm._set_leaf("java.util.ArrayList", lambda: _FakeList())
    jvm._set_leaf("java.util.HashMap", lambda: _FakeMap())
    # get_jvm_property 直接用 self.jvm.System，故在根挂一个 System
    jvm._set_leaf("System", types.SimpleNamespace(
        setProperty=lambda k, v: None,
        getProperty=lambda k: "prop_value" if k == "test.key" else None,
    ))
    jvm._set_leaf("java.lang.System", types.SimpleNamespace(
        setProperty=lambda k, v: None,
        getProperty=lambda k: "prop_value" if k == "test.key" else None,
    ))
    jvm._set_leaf("org.apache.spark.sql.types.DataTypes", types.SimpleNamespace(
        StringType="ST", IntegerType="IT"
    ))
    jvm._set_leaf("org.apache.spark.sql.expressions.UserDefinedFunction", FakeUDF)
    jvm._set_leaf("scala.collection.JavaConverters", types.SimpleNamespace(
        asScalaList=lambda lst: lst,
        mapAsScalaMap=lambda m: m,
    ))
    return jvm


class _FakeList:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)


class _FakeMap:
    def __init__(self):
        self.data = {}

    def put(self, k, v):
        self.data[k] = v

    def get(self, k):
        return self.data.get(k)


def _bridge(connected=True):
    return ScalaBridge(FakeSparkConn(connected=connected))


class TestInit:
    """__init__ 测试。"""

    def test_basic(self):
        b = _bridge()
        assert b._jvm is None
        assert b._gateway is None
        assert b._conn.is_connected is True


class TestJvm:
    """jvm 属性测试。"""

    def test_cached(self):
        b = _bridge()
        j1 = b.jvm
        j2 = b.jvm
        assert j1 is j2

    def test_not_connected(self):
        b = _bridge(connected=False)
        with pytest.raises(RuntimeError):
            _ = b.jvm


class TestGateway:
    """gateway 属性测试。"""

    def test_cached(self):
        b = _bridge()
        g1 = b.gateway
        g2 = b.gateway
        assert g1 is g2

    def test_not_connected(self):
        b = _bridge(connected=False)
        with pytest.raises(RuntimeError):
            _ = b.gateway


class TestAddJar:
    """add_jar/add_jars 测试。"""

    def test_missing_file(self, tmp_path):
        b = _bridge()
        with pytest.raises(FileNotFoundError):
            b.add_jar(str(tmp_path / "nope.jar"))

    def test_remote_path(self):
        b = _bridge()
        # 不抛错即通过（hdfs:// 前缀跳过 exists 检查）
        b.add_jar("hdfs:///x.jar")
        b.add_jar("s3://bucket/x.jar")
        b.add_jar("file:/tmp/x.jar")

    def test_add_jars(self):
        b = _bridge()
        b.add_jars(["hdfs:///a.jar", "s3:///b.jar"])


class TestGetClass:
    """get_class 测试。"""

    def test_basic(self):
        b = _bridge()
        cls = b.get_class("org.apache.spark.sql.types.DataTypes")
        assert cls.StringType == "ST"


class TestNewInstance:
    """new_instance 测试。"""

    def test_basic(self):
        b = _bridge()
        obj = b.new_instance("java.util.ArrayList")
        assert obj is not None


class TestCall:
    """call_static_method / call_method 测试。"""

    def test_static(self):
        b = _bridge()
        r = b.call_static_method("java.lang.System", "getProperty", "test.key")
        assert r == "prop_value"

    def test_method(self):
        b = _bridge()
        obj = _FakeMap()
        obj.put("k", "v")
        r = b.call_method(obj, "get", "k")
        assert r == "v"


class TestUdf:
    """register_scala_udf / register_java_udf 测试。"""

    def test_scala(self):
        b = _bridge()
        b.register_scala_udf("my_udf", "com.example.MyUDF", "StringType")

    def test_scala_integer(self):
        b = _bridge()
        b.register_scala_udf("my_udf2", "com.example.MyUDF2", "IntegerType")

    def test_java(self):
        b = _bridge()
        b.register_java_udf("my_java", "com.example.MyJavaUDF")


class TestScalaColl:
    """create_scala_list / create_scala_map 测试。"""

    def test_list(self):
        b = _bridge()
        result = b.create_scala_list([1, 2, 3])
        assert result.items == [1, 2, 3]

    def test_empty_list(self):
        b = _bridge()
        result = b.create_scala_list([])
        assert result.items == []

    def test_map(self):
        b = _bridge()
        result = b.create_scala_map({"a": 1})
        assert result.data == {"a": 1}

    def test_empty_map(self):
        b = _bridge()
        result = b.create_scala_map({})
        assert result.data == {}


class TestScalaToPython:
    """scala_to_python 测试。"""

    def test_returns_obj(self):
        b = _bridge()
        obj = object()
        assert b.scala_to_python(obj) is obj

    def test_with_size(self):
        b = _bridge()

        class Seq:
            def size(self):
                return 3

            def apply(self, i):
                return i * 10

        result = b.scala_to_python(Seq())
        assert result == [0, 10, 20]


class TestJvmProperty:
    """set/get_jvm_property 测试。"""

    def test_set(self):
        b = _bridge()
        b.set_jvm_property("k", "v")

    def test_get(self):
        b = _bridge()
        assert b.get_jvm_property("test.key") == "prop_value"
        assert b.get_jvm_property("nope") is None


class TestRunSparkSubmit:
    """run_spark_submit 测试。"""

    def test_no_spark_home(self, monkeypatch):
        monkeypatch.delenv("SPARK_HOME", raising=False)
        b = _bridge()
        with pytest.raises(RuntimeError):
            b.run_spark_submit("com.example.Main", "/tmp/x.jar")

    def test_with_spark_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARK_HOME", str(tmp_path))
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        ext = ".cmd" if os.name == "nt" else ""
        submit = fake_bin / f"spark-submit{ext}"
        submit.write_text("exit 0", encoding="utf-8")

        b = _bridge()
        code = b.run_spark_submit("com.example.Main", "/tmp/x.jar")
        assert code == 0

    def test_with_master_and_conf(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARK_HOME", str(tmp_path))
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        ext = ".cmd" if os.name == "nt" else ""
        submit = fake_bin / f"spark-submit{ext}"
        submit.write_text("exit 0", encoding="utf-8")

        b = _bridge()
        code = b.run_spark_submit(
            "com.example.Main", "/tmp/x.jar",
            master="local[1]", conf={"a": "b"}, args=["--foo"],
            deploy_mode="cluster"
        )
        assert code == 0


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        import vools.sql.spark.scala_bridge as m
        assert "ScalaBridge" in m.__all__
