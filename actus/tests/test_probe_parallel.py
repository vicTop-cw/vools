# -*- coding: utf-8 -*-
"""actus/tests/test_probe_parallel.py — probe() 并行化改造的验收测试。

测什么 / 为什么
---------------
probe() 已从「串行遍历探测器」改为 ThreadPoolExecutor 8 线程
（实测 89s → 目标 <15s；当前探测器 10 个，含新增的 platform_tools）。
改造声明「签名与返回结构不变」，但并行化本身带来两条必须钉住的隐含契约：

  1. **聚合正确**：多个 prober 同时在跑，结果不许串（A 的条目落进 B 的分类）、
     不许丢、不许重复 —— 线程池回填顺序被打乱后，这类错不会自己显形。
     且 items 的合并顺序只能由探测器清单决定，不能由「谁先跑完」决定。
  2. **单点容错**：某个 prober 炸掉不能拖垮整份报告。串行实现里异常会直接
     抛穿 probe()，并行实现必须把 failure 关在单个 future 里，其它 prober 照常出结果。

同时钉住「改造不许动契约」：probe() 的关键字参数与默认值、ProbeReport 的字段、
以及改造前就已存在的 9 个 section 一个都不能少。

怎么做到不真跑 80 秒、也不依赖本机装了什么
------------------------------------------
* 先在各探测器类上打桩：把 ``run()`` / ``probe()`` 换成「立刻返回两条假结果」的桩。
  ``run()`` 是 base.Prober 的模板方法（probe() 里就是 ``p.run()``）；``probe()``
  一并打桩，是为了防止改造后直接调 ``p.probe()`` 让桩落空、真跑一次 80 秒探测。
* 四个维度采集器（``get_platform_info`` 等）换成小 dict，避开 environment 的
  PATH 全盘扫描（本机实测 9.5s 冷 / 6.5s 热）污染计时。
* 「section 齐全」那一条用**真实 prober 代码**跑，但把所有 OS 边界打桩
  （shutil.which 查不到、subprocess 跑不起来、PATH 指向空目录、
  CRITICAL_PACKAGES 缩到 1 个包），整份套件实测 <1s。

并行性的判据是「假 prober 的 [start, end] 是否时间重叠」而不是墙钟阈值：
墙钟在 CI 上必然抖，重叠是可确定判定的。并发、聚合正确性（多重集 / 分类 /
summary 计数）、items 合并顺序稳定性、verbose 进度行完整性分别断言 ——
「并行度退化成 1」和「按完成顺序乱序合并」这两类隐性回归都会在这里亮红。

py3.6 兼容：只用 contextlib/typing 之外的标准库，% 格式化，不用 f-string。
"""

import inspect
import json
import os
import sys
import threading
import time

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.probe as probe_pkg  # noqa: E402
from vools.actus.probe import ProbeReport, probe  # noqa: E402
from vools.actus.probe import cache as cache_mod  # noqa: E402
from vools.actus.probe import python_pkgs as python_pkgs_mod  # noqa: E402
from vools.actus.probe.base import ProbeItem, Prober  # noqa: E402


# ---------------------------------------------------------------------------
# 改造前的基线（这两组常量就是「改造不许动的东西」的清单）
# ---------------------------------------------------------------------------

# probe() 报告里 by_category 的 9 个 section（改造前实测）。
# 断言用「包含」而非「相等」：另一项改造会新增 platform_tools 段，
# 新 section 属于允许的增量，少一个才是回归。
PRE_PARALLEL_SECTIONS = frozenset([
    "platform",
    "permissions",
    "environment",
    "resources",
    "system_tools",
    "runtimes",
    "compilers",
    "python_packages",
    "actions",
])

# 改造前 probe() 会跑的全部探测器类名。
PRE_PARALLEL_PROBERS = frozenset([
    "PlatformProber",
    "PermissionsProber",
    "EnvironmentProber",
    "ResourcesProber",
    "SystemToolsProber",
    "RuntimesProber",
    "CompilersProber",
    "PythonPackagesProber",
    "ActionsProber",
])


# ---------------------------------------------------------------------------
# 夹具：缓存隔离 / 桩环境
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_probe_cache(tmp_path, monkeypatch):
    """每个用例都不许碰仓库里真实的 _meta/probe_cache.json。

    并行改造的回归路径会反复走「写缓存 / 读缓存」，共用真实缓存文件会让
    用例之间互相污染（前一个用例的 items 变成后一个用例的输入）。
    """
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    return cache_file


# 四个维度的替身：只要非空即可（缓存往返用例要求它们非空）。
_STUB_DIMENSIONS = {
    "get_platform_info": {
        "os": "StubOS", "os_release": "0", "arch": "stub-arch",
        "python_version": "3.x", "python_executable": "python",
        "platform_tag": "stub", "is_windows": False, "is_linux": True,
        "is_macos": False, "path_dirs": [],
    },
    "get_permissions_info": {
        "user": {"name": "stub-user", "uid": 0},
        "is_admin": False,
        "is_elevated": False,
        "can_install_system_wide": False,
        "can_create_startups": False,
        "effective_permissions": {},
    },
    "get_environment_info": {
        "path_dirs": [], "path_count": 0, "path_executables": [],
        "env_vars": {}, "secret_keys_found": {},
        "virtual_env": {"active": False}, "conda_env": {"active": False},
    },
    "get_resources_info": {
        "cpu": {"count_logical": 4}, "memory": {}, "disk": [], "network": {},
    },
}


def _stub_os_boundaries(monkeypatch):
    """把「这台机器上装了什么」的入口全掐掉：查不到、跑不起来。

    打桩点是 OS 边界（shutil.which / subprocess / PATH），不是探测器内部函数，
    所以并行改造怎么重排内部调用都不会让桩落空。
    """

    class _StubProcess(object):
        returncode = 1
        stdout = ""
        stderr = "stub: tool not installed"

    def _which(*args, **kwargs):
        return None

    def _run(*args, **kwargs):
        return _StubProcess()

    def _raise(*args, **kwargs):
        raise OSError("stub: tool not installed")

    import shutil
    import subprocess
    monkeypatch.setattr(shutil, "which", _which)
    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(subprocess, "check_output", _raise)
    monkeypatch.setattr(subprocess, "check_call", _run)
    monkeypatch.setattr(subprocess, "Popen", _raise)


def _stub_dimensions(monkeypatch):
    """四个维度采集器换成小 dict（名字不存在时跳过，兼容改造后的重新组织）。"""
    patched = []
    for name, value in _STUB_DIMENSIONS.items():
        if hasattr(probe_pkg, name):
            monkeypatch.setattr(probe_pkg, name, (lambda v: (lambda: dict(v)))(value))
            patched.append(name)
    return patched


def _sterilize_filesystem(monkeypatch):
    """把「固定安装路径 / 通配安装路径」也打桩掉（干净机器假设）。

    只给 section 齐全性那条用：它要跑真实 prober（含 platform_tools），
    而真机上可能确实装着 VS/WSL/Terminal —— 不打桩会让断言随机器漂移、也变慢。
    注意**不要**加进 stubbed_probe_env：缓存用例依赖 os.path.exists 判断缓存文件，
    把那一路打桩掉会让「命中缓存」用例变成假绿。
    """
    import glob
    import pathlib
    monkeypatch.setattr(glob, "glob", lambda *a, **k: [])
    monkeypatch.setattr(os.path, "exists", lambda *a, **k: False)
    monkeypatch.setattr(os.path, "isfile", lambda *a, **k: False)
    monkeypatch.setattr(os.path, "isdir", lambda *a, **k: False)
    monkeypatch.setattr(pathlib.Path, "exists", lambda self: False)
    monkeypatch.setattr(pathlib.Path, "is_file", lambda self: False)
    monkeypatch.setattr(pathlib.Path, "is_dir", lambda self: False)


@pytest.fixture
def stubbed_probe_env(monkeypatch, tmp_path):
    """快环境：OS 边界打桩 + PATH 指向空目录 + 四维度替身。

    只剩「编排逻辑」在跑 —— 这正是并行改造要测的部分。
    """
    monkeypatch.setenv("PATH", str(tmp_path / "no_tools_here"))
    _stub_os_boundaries(monkeypatch)
    _stub_dimensions(monkeypatch)


# ---------------------------------------------------------------------------
# 假 prober：记录「谁、什么线程、起止时间」
# ---------------------------------------------------------------------------

def _registered_prober_classes():
    """尽力从产品侧拿「本次 probe() 真的会跑哪些探测器类」的清单（注册表即真源）。

    为什么不直接用 ``Prober.__subclasses__()``：那是**累积**的。``importlib.reload``
    或测试里临时定义的假探测器都会留下 probe() 根本不会实例化的陈旧类。实测两种
    污染形态：
      * 陈旧类只留在 ``__subclasses__`` 里（如 test_probe.py 里函数内定义的 Boom）；
      * reload 之后旧类**仍被注册表引用**（模块属性上已经是新类）—— 此时「模块属性
        是不是它」这条判据会把真正会被跑的那个类误判成陈旧类。
    只有注册表是唯一真源。取不到（实现改名/重构）时返回空列表，由调用方回退。
    """
    builder = getattr(probe_pkg, "_build_prober_list", None)
    if not callable(builder):
        return []
    try:
        classes = builder()
    except Exception:          # 探测不刨根：注册表不可用就走回退路径
        return []
    return [cls for cls in classes if isinstance(cls, type)]


def _concrete_probers():
    """枚举「probe() 实际会跑」的具体 Prober 子类。

    优先用产品注册表（见 ``_registered_prober_classes``）；注册表不可见时回退到
    递归 ``__subclasses__()`` 并用「模块命名空间里这个名字还指向它吗」过滤陈旧类。
    两条路径的目的相同：**枚举到的类必须恰好是 probe() 会实例化的那批**，否则
    「跑到几个 = 枚举几个」的断言会被无关的陈旧类污染（实测 10 真实 + 12 陈旧 = 22）。
    """
    registered = _registered_prober_classes()
    if registered:
        return list(registered)

    found = []

    def walk(cls):
        for sub in cls.__subclasses__():
            if sub in found:
                continue
            module = sys.modules.get(getattr(sub, "__module__", ""))
            if module is None or getattr(module, sub.__name__, None) is not sub:
                continue          # reload 遗留的陈旧类 / 测试内定义的临时类
            found.append(sub)
            walk(sub)

    walk(Prober)
    return found


class _StubProberRecorder(object):
    """生成假 run()/probe()：返回固定条目，并记录每次调用的线程与时间区间。"""

    def __init__(self, delay=0.0, per_prober=2, delays=None):
        self.delay = delay
        self.per_prober = per_prober
        self.delays = dict(delays or {})
        self.calls = []
        self._lock = threading.Lock()

    def make(self, cls):
        delay = self.delays.get(cls.__name__, self.delay)

        def stub(_self):
            t_start = time.perf_counter()
            if delay:
                time.sleep(delay)
            items = [
                ProbeItem(
                    name="%s#%d" % (cls.__name__, i),
                    category=cls.__name__,
                    available=True,
                    path="/stub/%s_%d" % (cls.__name__, i),
                )
                for i in range(self.per_prober)
            ]
            t_end = time.perf_counter()
            with self._lock:
                self.calls.append({
                    "prober": cls.__name__,
                    "thread": threading.current_thread().name,
                    "start": t_start,
                    "end": t_end,
                })
            return items

        return stub


def _install_fakes(monkeypatch, delay=0.0, per_prober=2, delays=None):
    """给每个具体 prober 同时打桩 run() 与 probe()，返回记录器。"""
    recorder = _StubProberRecorder(
        delay=delay, per_prober=per_prober, delays=delays)
    for cls in _concrete_probers():
        stub = recorder.make(cls)
        monkeypatch.setattr(cls, "run", stub)
        monkeypatch.setattr(cls, "probe", stub)
    return recorder


def _has_overlapping_calls(calls):
    """任意两次假 prober 调用在时间区间上是否重叠（= 真的并行过）。"""
    spans = sorted(((c["start"], c["end"]) for c in calls), key=lambda s: s[0])
    max_end = None
    for start, end in spans:
        if max_end is not None and start < max_end:
            return True
        max_end = end if max_end is None else max(max_end, end)
    return False


def _rewrite_cache_items(cache_file, items, timestamp=None):
    """把已落盘缓存里的 items 换成标记条目（其余字段原样保留）。

    **不手写整份 payload**：缓存 payload 带 ``schema_version`` 等版本化字段
    （cache.py 是真源，且正在演进），手写等于把测试钉死在某一个版本上。
    做法是先让 probe() 用桩跑一轮写出结构合法的缓存，再就地改 items ——
    结构合法性与版本一致性都由产品自己保证。
    """
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), "缓存文件顶层不是对象: %r" % (payload,)
    payload["items"] = items
    payload["summary"] = {}
    if timestamp is not None:
        payload["timestamp"] = timestamp
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# 契约：签名与返回结构不变
# ---------------------------------------------------------------------------

def test_probe_signature_and_report_shape_unchanged():
    """并行化只许改内部实现：关键字参数、默认值、报告字段都必须原样。

    允许新增可选关键字（实现侧旋钮），但原有的三个关键字参数必须还在、
    仍由关键字传（probe() 全是 keyword-only），默认值不得漂移 ——
    CLI 的 ``--max-age`` 默认 3600 就钉在这个值上。
    """
    params = inspect.signature(probe).parameters
    for name, default in (("force_refresh", False), ("max_age", 3600), ("verbose", False)):
        assert name in params, "probe() 丢了参数 %s" % name
        assert params[name].default == default, \
            "probe() 的 %s 默认值变成 %r（应为 %r）" % (name, params[name].default, default)
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY, \
            "probe() 的 %s 必须是 keyword-only" % name

    report = ProbeReport()
    data = report.to_dict()
    for key in ("timestamp", "elapsed_ms", "platform", "permissions",
                "environment", "resources", "items", "summary"):
        assert key in data, "ProbeReport 丢了字段 %s" % key


# ---------------------------------------------------------------------------
# 聚合：每个注册的 prober 都跑到，报告自洽
# ---------------------------------------------------------------------------

@pytest.mark.timeout(120)
def test_probe_runs_every_registered_prober(monkeypatch, stubbed_probe_env):
    """9 个探测器一个都不能漏跑，报告要能 JSON 序列化（落缓存/给 LLM 消费）。"""
    recorder = _install_fakes(monkeypatch)
    report = probe(force_refresh=True)

    assert isinstance(report, ProbeReport)
    invoked = [c["prober"] for c in recorder.calls]
    assert invoked, "桩 prober 一个都没被调用 —— probe() 的编排被改坏了"
    missing = PRE_PARALLEL_PROBERS - set(invoked)
    assert not missing, "这些探测器没被跑到（改造漏了？）: %s" % sorted(missing)

    summary = report.summary
    assert summary["total_items"] == len(report.items) > 0
    assert summary["available_items"] + summary["unavailable_items"] == summary["total_items"]
    json.dumps(report.to_dict(), ensure_ascii=False)


@pytest.mark.timeout(120)
def test_parallel_aggregation_has_no_crosstalk(monkeypatch, stubbed_probe_env):
    """多个 prober 并行跑时结果不串、不丢、不重复。

    假 prober 各睡 30ms 制造真实重叠；断言跑在**结果**上（名字/分类的精确
    多重集、summary 计数、分类集合），而不是实现细节。
    """
    recorder = _install_fakes(monkeypatch, delay=0.03, per_prober=2)
    report = probe(force_refresh=True)

    invoked = [c["prober"] for c in recorder.calls]
    assert invoked, "桩 prober 一个都没被调用"
    assert len(invoked) == len(set(invoked)), \
        "同一个 prober 被执行了多次（并行改造里很容易犯的重复提交）: %s" % invoked
    missing = PRE_PARALLEL_PROBERS - set(invoked)
    assert not missing, "这些探测器没被跑到: %s" % sorted(missing)

    expected = sorted(
        ("%s#%d" % (name, i), name) for name in invoked for i in range(2))
    got = sorted((item.name, item.category) for item in report.items)
    assert got == expected, \
        "并行聚合结果串了/丢了/多了：期望 %d 条，实得 %d 条" % (len(expected), len(got))

    summary = report.summary
    assert summary["total_items"] == len(report.items) == len(expected)
    # 分类集合必须正好等于「跑过的 prober」：多出来的分类 = 结果被塞错桶
    assert set(summary["by_category"]) == set(invoked), \
        "报告里出现了不该有的分类: %s" % sorted(set(summary["by_category"]) - set(invoked))
    for name in invoked:
        assert summary["by_category"][name] == {"total": 2, "available": 2}, \
            "%s 的分类计数不对: %r" % (name, summary["by_category"][name])


@pytest.mark.timeout(120)
def test_probe_executes_probers_concurrently(monkeypatch, stubbed_probe_env):
    """探测器确实在时间上重叠执行（= 真的并行，而不是「写着线程池、跑起来串行」）。

    判据：假 prober 各睡 30ms，任意两次调用区间是否重叠。8 线程跑 10 个探测器
    必然重叠；若完全不重叠说明并行度退化成 1（KPI「89s → <15s」的根基没了）。
    """
    classes = _concrete_probers()
    if len(classes) < 2:
        pytest.skip("可用探测器不足 2 个，无法判定并发")

    recorder = _install_fakes(monkeypatch, delay=0.03, per_prober=1)
    probe(force_refresh=True)

    spans = recorder.calls
    assert len(spans) == len(classes), "有探测器没被执行到"
    assert _has_overlapping_calls(spans), (
        "探测器调用区间完全没有重叠 —— probe() 实际是串行执行"
        "（并行度退化？）；调用区间: %r" % [
            (c["prober"], round(c["start"] % 1000, 3), round(c["end"] % 1000, 3))
            for c in spans])

    threads = {c["thread"] for c in spans}
    assert len(threads) >= 2, "所有探测器都在同一个线程里跑: %r" % sorted(threads)


@pytest.mark.timeout(120)
def test_items_order_does_not_depend_on_completion_order(monkeypatch, stubbed_probe_env):
    """items 的合并顺序只由探测器清单决定，不由「谁先跑完」决定。

    并行实现若按 as_completed 的完成顺序 extend()，items 顺序就会随调度抖动
    （缓存往返、下游 diff、LLM 消费都会跟着抖）。这里跑两轮：第一轮让前面的
    prober 慢、第二轮让后面的 prober 慢 —— 完成顺序相反，但合并顺序必须一致。
    """
    classes = _concrete_probers()
    assert len(classes) >= 2, "可用探测器不足 2 个，无法判定顺序稳定性"

    slow_first = {
        cls.__name__: 0.004 * (len(classes) - i)
        for i, cls in enumerate(classes)
    }
    slow_last = {
        cls.__name__: 0.004 * (i + 1)
        for i, cls in enumerate(classes)
    }

    _install_fakes(monkeypatch, per_prober=1, delays=slow_first)
    first = [item.name for item in probe(force_refresh=True).items]

    # 第二轮换成相反的耗时分布（monkeypatch 覆盖同一批类的桩）
    _install_fakes(monkeypatch, per_prober=1, delays=slow_last)
    second = [item.name for item in probe(force_refresh=True).items]

    assert first == second, \
        "items 顺序随完成顺序漂移了（并行合并按 as_completed 追加？）:\n" \
        "  第一轮: %r\n  第二轮: %r" % (first, second)
    # 每个 prober 一条，因此顺序必须恰好是「探测器清单顺序」（每类恰好出现一次）
    assert len(first) == len(classes)
    assert len(set(first)) == len(first)


@pytest.mark.timeout(120)
def test_verbose_progress_lines_are_not_interleaved(monkeypatch, stubbed_probe_env, capsys):
    """并行下 verbose 的进度行不能被多线程搅在一起（每行一个探测器、格式完整）。

    串行版每行是 ``[probe] XxxProber: a/b available``；并行后若不加锁，
    两个线程的 print 会交错成半行，日志就没法读了。
    """
    recorder = _install_fakes(monkeypatch, delay=0.01, per_prober=1)
    probe(force_refresh=True, verbose=True)

    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.startswith("[probe] ")]
    assert len(lines) == len(recorder.calls), \
        "verbose 进度行数不对：期望每探测器一行（%d 行），实得 %d 行:\n%s" % (
            len(recorder.calls), len(lines), out)
    for line in lines:
        assert line.count("[probe]") == 1, "进度行被拼坏了: %r" % line
        assert line.endswith("available"), "进度行格式不对: %r" % line
        assert ": " in line and "/" in line, "进度行缺少计数: %r" % line


# ---------------------------------------------------------------------------
# 容错：单个 prober 炸掉不能拖垮整份报告
# ---------------------------------------------------------------------------

@pytest.mark.timeout(120)
def test_prober_internal_failure_does_not_break_other_probers(monkeypatch, stubbed_probe_env):
    """某个 prober 的 probe() 抛异常时，其它 prober 的结果必须照常出。

    保留该类的真实 ``base.Prober.run``（模板方法负责把 probe() 异常兜成
    available=False 的条目）；其余类全部打桩。这是「并行改造不能引入回归」的
    下限：改造后即使异常被 future 捕获，其它 prober 的结果也不许受影响。
    """
    classes = _concrete_probers()
    assert classes, "没有发现任何 Prober 子类"
    raiser = classes[0]

    def _boom(_self):
        raise RuntimeError("stub-prober-boom")

    recorder = _StubProberRecorder()
    for cls in classes:
        if cls is raiser:
            monkeypatch.setattr(cls, "probe", _boom)
        else:
            stub = recorder.make(cls)
            monkeypatch.setattr(cls, "run", stub)
            monkeypatch.setattr(cls, "probe", stub)

    report = probe(force_refresh=True)

    invoked = {c["prober"] for c in recorder.calls}
    assert invoked, "其它 prober 一个都没被跑到（单点失败拖垮了编排）"
    for name in invoked:
        got = [i for i in report.items if i.name.startswith(name + "#")]
        assert len(got) == 2, "%s 的结果没出全: %r" % (name, [i.name for i in report.items])
        assert all(i.category == name and i.available for i in got), \
            "%s 的结果被污染了" % name

    # 崩溃的探测器：要么不出条目，要么必须是「不可用 + 带原因」的显式降级，
    # 绝不能是 available=True 的幽灵条目。
    for item in [i for i in report.items if i.name == raiser.__name__]:
        assert item.available is False
        assert item.error, "降级条目必须带 error 原因，不能静默吞掉"

    assert report.summary["total_items"] == len(report.items)


@pytest.mark.timeout(120)
def test_escaping_prober_failure_does_not_abort_report(monkeypatch, stubbed_probe_env):
    """某个 prober 的 run() 直接抛穿（不被模板方法兜住）时，报告也不能整份中止。

    这是并行改造最关键的容错点：串行实现里 ``p.run()`` 抛异常会直接冒到
    probe() 外面，调用方拿不到任何结果；并行实现必须按 future 吞掉它。
    """
    classes = _concrete_probers()
    raiser = classes[-1]

    def _explode(*args, **kwargs):
        raise RuntimeError("stub-prober-escaped-boom")

    recorder = _StubProberRecorder()
    for cls in classes:
        if cls is raiser:
            # run/probe 都抛：无论实现走哪条路径都不会被兜住，确保真的测到容错
            monkeypatch.setattr(cls, "run", _explode)
            monkeypatch.setattr(cls, "probe", _explode)
        else:
            stub = recorder.make(cls)
            monkeypatch.setattr(cls, "run", stub)
            monkeypatch.setattr(cls, "probe", stub)

    try:
        report = probe(force_refresh=True)
    except Exception as exc:  # noqa: BLE001 — 这里就是要观测「异常是否抛穿」
        pytest.fail(
            "单个 prober 的 run() 抛异常时 probe() 整份中止（%s: %s）——"
            "并行容错契约破了：其它 prober 的结果也一起丢了"
            % (type(exc).__name__, exc))

    invoked = {c["prober"] for c in recorder.calls}
    assert invoked, "其它 prober 一个都没被跑到"
    for name in invoked:
        got = [i for i in report.items if i.name.startswith(name + "#")]
        assert len(got) == 2, "%s 的结果没出全" % name
    assert report.summary["total_items"] == len(report.items)


# ---------------------------------------------------------------------------
# 缓存两条路径：force_refresh 绕过 / 命中缓存不重跑
# ---------------------------------------------------------------------------

@pytest.mark.timeout(120)
def test_force_refresh_bypasses_cache(monkeypatch, stubbed_probe_env, isolated_probe_cache):
    """force_refresh=True 必须无视一份「确实会命中」的缓存，重新跑 prober。

    断言分两步，避免假绿：
      1. 先确认种子缓存**真的能命中**（否则「绕过缓存」就无从谈起）；
      2. 再确认 force_refresh=True 既不吃缓存、也真的重新执行了 prober。
    """
    recorder = _install_fakes(monkeypatch)
    probe(force_refresh=True)                     # 写出结构合法的真实缓存
    _rewrite_cache_items(isolated_probe_cache, [
        {"name": "FROM_CACHE", "category": "cached", "available": True},
    ])

    hit = probe(force_refresh=False, max_age=999999)
    assert "FROM_CACHE" in [i.name for i in hit.items], \
        "种子缓存没被命中（schema / 维度校验拒了它）—— 本用例的绕过断言会失去意义"

    report = probe(force_refresh=True)
    assert "FROM_CACHE" not in [i.name for i in report.items], \
        "force_refresh=True 仍然吃了缓存"
    assert recorder.calls, "force_refresh=True 没有重新执行 prober"


@pytest.mark.timeout(120)
def test_cache_hit_skips_probers_and_keeps_dimensions(monkeypatch, stubbed_probe_env):
    """命中缓存时不再跑 prober，且 items/四维度都要原样回来。

    改造后报告由线程池回填组装，写缓存的内容若少维度（历史上就丢过
    platform/permissions/environment/resources），缓存路径会静默给出空报告。
    """
    recorder = _install_fakes(monkeypatch, per_prober=1)

    fresh = probe(force_refresh=True)
    ran = len(recorder.calls)
    assert ran, "force_refresh=True 没有执行 prober"

    cached = probe(force_refresh=False, max_age=999999)
    assert len(recorder.calls) == ran, "命中缓存却重新跑了 prober"

    assert [i.name for i in cached.items] == [i.name for i in fresh.items], \
        "缓存往返后 items 变了：%r vs %r" % (
            [i.name for i in cached.items], [i.name for i in fresh.items])

    data = cached.to_dict()
    for key in ("platform", "permissions", "environment", "resources"):
        assert data[key], "命中缓存后 %s 维度丢了" % key


# ---------------------------------------------------------------------------
# section 齐全性：用真实 prober 代码，只把 OS 边界与数据表缩到最小
# ---------------------------------------------------------------------------

@pytest.mark.timeout(120)
def test_report_contains_all_pre_parallel_sections(monkeypatch, tmp_path):
    """改造前就有的 9 个 section 一个都不能少（这条走真实探测逻辑）。

    为了不真跑 80 秒：
      * shutil.which / subprocess 全打桩 → 所有工具一律探不到（快且确定）；
      * PATH 指向空目录 → environment 不再扫真实 PATH（本机实测 2.9s → 毫秒级）；
      * CRITICAL_PACKAGES 缩到 1 个已知包 → python_pkgs 不再逐个查 66 个包
        （本机实测 5.6s）。包表内容由 test_probe.py 负责，这里只验 section 存在。
    """
    monkeypatch.setenv("PATH", str(tmp_path / "no_tools_here"))
    _stub_os_boundaries(monkeypatch)
    _sterilize_filesystem(monkeypatch)
    monkeypatch.setattr(
        python_pkgs_mod, "CRITICAL_PACKAGES", [("pip", "pip", False)])

    report = probe(force_refresh=True)
    assert isinstance(report, ProbeReport)
    data = report.to_dict()
    for key in ("timestamp", "elapsed_ms", "platform", "permissions",
                "environment", "resources", "items", "summary"):
        assert key in data, "报告缺字段 %s" % key

    sections = set(data["summary"]["by_category"])
    missing = PRE_PARALLEL_SECTIONS - sections
    assert not missing, \
        "并行改造丢了 section: %s（实际 section: %s）" % (sorted(missing), sorted(sections))

    # 新能力（platform_tools）已接进 probe() 的话，报告里必须真有这一段 ——
    # 常量清单只保证「旧段没丢」，这一段保证「新段没白写」。
    if getattr(probe_pkg, "PlatformToolsProber", None) is not None:
        assert "platform_tools" in sections, \
            "平台特有能力探测器已接入 probe()，但报告里没有 platform_tools section" \
            "（实际 section: %s）" % sorted(sections)

    summary = data["summary"]
    assert summary["total_items"] == len(data["items"]) > 0
    assert summary["available_items"] + summary["unavailable_items"] == summary["total_items"]
    # 报告必须能 JSON 序列化（缓存 + LLM 消费两条下游都依赖）
    json.dumps(data, ensure_ascii=False)
