# -*- coding: utf-8 -*-
"""测试 vools.sql.spark.connection（用 fake SparkSession 避免启动 JVM）。"""

import sys
import types
import pytest
import vools.sql.spark.connection as mod
from vools.sql.spark.connection import SparkConnection
from vools.sql.core.result import ResultSet

__all__ = ["TestInit", "TestConnect", "TestClose", "TestExecute",
           "TestExecuteMany", "TestCursor", "TestSql", "TestRead",
           "TestView", "TestProps", "TestRepr", "TestImport"]


# ── Fakes ──

class FakeField:
    def __init__(self, name):
        self.name = name


class FakeSchema:
    def __init__(self, names):
        self.fields = [FakeField(n) for n in names]


class FakeRow:
    def __init__(self, vals):
        self._v = tuple(vals)

    def __iter__(self):
        return iter(self._v)

    def __getitem__(self, i):
        return self._v[i]


class FakeDF:
    def __init__(self, names, rows):
        self.schema = FakeSchema(names)
        self._rows = [FakeRow(r) for r in rows]
        self.view_names = []

    def collect(self):
        return self._rows

    def createTempView(self, name):
        self.view_names.append(name)

    def createOrReplaceTempView(self, name):
        self.view_names.append(name)


class FakeReader:
    def __init__(self, spark):
        self._spark = spark

    def csv(self, path, **kw):
        return FakeDF(["a", "b"], [(1, 2)])

    def parquet(self, path, **kw):
        return FakeDF(["c"], [(3,)])

    def json(self, path, **kw):
        return FakeDF(["d", "e"], [(4, 5)])


class FakeSparkSession:
    instances = []

    def __init__(self, app_name, master, config):
        self._app_name = app_name
        self._master = master
        self._config = config
        self.stopped = False
        self.read = FakeReader(self)
        FakeSparkSession.instances.append(self)

    def sql(self, q):
        return FakeDF(["x"], [(42,)])

    def createDataFrame(self, data):
        return FakeDF(["col0"], data)

    def stop(self):
        self.stopped = True


class FakeBuilder:
    def __init__(self):
        self.app = None
        self.master_ = None
        self.configs = {}
        self._session_cls = FakeSparkSession

    def appName(self, name):
        self.app = name
        return self

    def master(self, m):
        self.master_ = m
        return self

    def config(self, k, v):
        self.configs[k] = v
        return self

    def getOrCreate(self):
        return FakeSparkSession(self.app, self.master_, self.configs)


# ── Fixtures ──

@pytest.fixture(autouse=True)
def fake_pyspark(monkeypatch):
    """把 pyspark.sql.SparkSession 换成 FakeBuilder。"""
    FakeSparkSession.instances = []
    fake_pyspark_mod = types.ModuleType("pyspark")
    fake_pyspark_sql = types.ModuleType("pyspark.sql")
    fake_pyspark_sql.SparkSession = types.SimpleNamespace(builder=FakeBuilder())
    fake_pyspark_sql.DataFrame = FakeDF
    sys.modules["pyspark"] = fake_pyspark_mod
    sys.modules["pyspark.sql"] = fake_pyspark_sql
    yield
    sys.modules.pop("pyspark", None)
    sys.modules.pop("pyspark.sql", None)


def _connected():
    c = SparkConnection(app_name="t", master="local[1]")
    c.connect()
    return c


class TestInit:
    """__init__ 测试。"""

    def test_defaults(self):
        c = SparkConnection()
        assert c._app_name == "vools_spark"
        assert c._master == "local[*]"
        assert c._catalog == "spark_catalog"
        assert c._database == "default"
        assert c._connected is False
        assert c._spark is None

    def test_kwargs(self):
        c = SparkConnection(app_name="x", master="y", catalog="c", database="d",
                            foo="bar")
        assert c._config == {"foo": "bar"}


class TestConnect:
    """connect 测试。"""

    def test_basic(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect()
        assert c._connected is True
        assert c._spark is not None
        assert len(FakeSparkSession.instances) == 1

    def test_reconnect_closes_first(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect()
        s1 = c._spark
        c.connect()
        assert s1.stopped is True
        assert len(FakeSparkSession.instances) == 2

    def test_kwargs_app_name(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect(app_name="new")
        assert c._app_name == "new"
        assert FakeSparkSession.instances[-1]._app_name == "new"

    def test_kwargs_master(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect(master="local[2]")
        assert c._master == "local[2]"

    def test_kwargs_catalog(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect(catalog="mycat")
        assert c._catalog == "mycat"

    def test_kwargs_database(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect(database="mydb")
        assert c._database == "mydb"

    def test_kwargs_other(self):
        c = SparkConnection(app_name="t", master="local[1]")
        c.connect(spark_foo="bar")
        assert FakeSparkSession.instances[-1]._config.get("spark_foo") == "bar"


class TestClose:
    """close 测试。"""

    def test_close(self):
        c = _connected()
        s = c._spark
        c.close()
        assert s.stopped is True
        assert c._connected is False
        assert c._spark is None

    def test_close_when_not_connected(self):
        c = SparkConnection()
        c.close()  # 不应抛错
        assert c._connected is False


class TestExecute:
    """execute 测试。"""

    def test_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            c.execute("SELECT 1")

    def test_basic(self):
        c = _connected()
        rs = c.execute("SELECT 1")
        assert isinstance(rs, ResultSet)
        assert rs.columns == ["x"]
        assert rs.rowcount == 1

    def test_params(self):
        c = _connected()
        rs = c.execute("SELECT %s", (1,))
        assert isinstance(rs, ResultSet)


class TestExecuteMany:
    """executemany 测试。"""

    def test_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            c.executemany("INSERT", [("a",)])

    def test_basic(self):
        c = _connected()
        n = c.executemany("SELECT %s", [(1,), (2,)])
        assert n == 2


class TestCursor:
    """cursor 测试。"""

    def test_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            c.cursor()

    def test_basic(self):
        c = _connected()
        assert c.cursor() is c._spark


class TestSql:
    """sql 测试。"""

    def test_basic(self):
        c = _connected()
        rs = c.sql("SELECT 1")
        assert isinstance(rs, ResultSet)


class TestRead:
    """read_csv/read_parquet/read_json 测试。"""

    def test_read_csv_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            c.read_csv("/tmp/x.csv")

    def test_read_csv(self):
        c = _connected()
        rs = c.read_csv("/tmp/x.csv", header=True)
        assert isinstance(rs, ResultSet)
        assert rs.columns == ["a", "b"]

    def test_read_parquet(self):
        c = _connected()
        rs = c.read_parquet("/tmp/x.parquet")
        assert isinstance(rs, ResultSet)
        assert rs.columns == ["c"]

    def test_read_json(self):
        c = _connected()
        rs = c.read_json("/tmp/x.json")
        assert isinstance(rs, ResultSet)
        assert rs.columns == ["d", "e"]


class TestView:
    """create_temp_view/create_or_replace_temp_view 测试。"""

    def test_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            c.create_temp_view("v", object())

    def test_bad_type(self):
        c = _connected()
        with pytest.raises(TypeError):
            c.create_temp_view("v", 42)

    def test_resultset(self):
        c = _connected()
        rs = ResultSet(columns=["a"], rows=[(1,)], rowcount=1)
        c.create_temp_view("v", rs)
        assert True

    def test_dataframe(self):
        c = _connected()
        df = FakeDF(["a"], [(1,)])
        c.create_temp_view("v", df)
        assert df.view_names == ["v"]

    def test_create_or_replace_resultset(self):
        c = _connected()
        rs = ResultSet(columns=["a"], rows=[(1,)], rowcount=1)
        c.create_or_replace_temp_view("v", rs)
        assert True

    def test_create_or_replace_bad_type(self):
        c = _connected()
        with pytest.raises(TypeError):
            c.create_or_replace_temp_view("v", "bad")


class TestProps:
    """spark/scala/app_name/master/catalog/database 测试。"""

    def test_spark_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            _ = c.spark

    def test_spark(self):
        c = _connected()
        assert c.spark is c._spark

    def test_scala_not_connected(self):
        c = SparkConnection()
        with pytest.raises(RuntimeError):
            _ = c.scala

    def test_scala(self):
        c = _connected()
        # ScalaBridge 可能依赖真实 pyspark，这里只验证 lazy 属性不抛异常
        sb = c.scala
        assert sb is not None

    def test_app_name(self):
        c = SparkConnection(app_name="n")
        assert c.app_name == "n"

    def test_master(self):
        c = SparkConnection(master="m")
        assert c.master == "m"

    def test_catalog(self):
        c = SparkConnection(catalog="c")
        assert c.catalog == "c"

    def test_database(self):
        c = SparkConnection(database="d")
        assert c.database == "d"


class TestRepr:
    """__repr__ 测试。"""

    def test_closed(self):
        c = SparkConnection(app_name="n", master="m")
        r = repr(c)
        assert "SparkConnection" in r
        assert "closed" in r

    def test_connected(self):
        c = _connected()
        r = repr(c)
        assert "connected" in r


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        assert "SparkConnection" in mod.__all__
