# -*- coding: utf-8 -*-
"""pytest_compat.py 契约测试（第 42 轮，round 32 任务）。

该模块不是"pytest 版本探测层"，而是 **mdtest exec 环境的 pytest 语义垫片**
（raises/approx/skip/mark/fixture/monkeypatch/capsys）。本文件只测垫片行为，
不启动 mdtest；每条 docstring 写「退步了会怎样」。

已发现的真实 bug 只报告、不修；相关用例用 xfail(strict=True) 钉"正确语义"
（修复后 strict xpass 会变红提醒删标记）。
"""
import io
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import pytest_compat as pc  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_fixtures():
    pc.reset_fixtures()
    yield
    pc.reset_fixtures()


# ═══════════════════════════════════════════════════════════════════════
# raises / fail / skip / approx
# ═══════════════════════════════════════════════════════════════════════

def test_raises_catches_expected_and_exposes_value():
    """退步了会怎样：raises 不捕获预期异常（或 .value 为空）→ 测试永远失败/拿不到异常对象。"""
    with pc.raises(ValueError) as ctx:
        raise ValueError('boom')
    assert isinstance(ctx.value, ValueError) and str(ctx.value) == 'boom'


def test_raises_match_and_tuple():
    """退步了会怎样：match 不生效（错误信息不校验）或元组异常只认第一个。"""
    with pc.raises(ValueError, match='bo+m'):
        raise ValueError('boom')
    with pc.raises((KeyError, TypeError)):
        raise TypeError('t')


def test_raises_did_not_raise_is_assertion_error():
    """退步了会怎样：没有抛异常却被当成通过 → 该失败的保护形同虚设。"""
    with pc.raises(AssertionError, match='DID NOT RAISE'):
        with pc.raises(ValueError):
            pass


def test_raises_match_mismatch_is_assertion_error():
    """退步了会怎样：match 不匹配仍放行 → 异常类型对、原因错也算通过。"""
    with pc.raises(AssertionError, match='pattern'):
        with pc.raises(ValueError, match='nope'):
            raise ValueError('other')


def test_raises_unexpected_exception_propagates():
    """退步了会怎样：非预期异常被吞掉 → 真崩溃被当成"预期异常"隐藏。"""
    with pytest.raises(TypeError):
        with pc.raises(ValueError):
            raise TypeError('unexpected')


def test_fail_and_skip():
    """退步了会怎样：fail 不失败/skip 不抛 Skipped → mdtest 统计的失败/跳过全错。"""
    with pytest.raises(AssertionError, match='boom'):
        pc.fail('boom')
    with pytest.raises(pc.Skipped) as exc:
        pc.skip('later')
    assert exc.value.args[0] == 'later'


def test_approx_numeric_rel_abs_and_non_numeric():
    """退步了会怎样：容差算错（严格相等或无限宽松）→ 浮点断言随机红/永远绿；
    非数值又被 __eq__ 吃掉 → 字符串断言失效。"""
    assert 0.1 + 0.2 == pc.approx(0.3)
    assert 1.0000001 == pc.approx(1.0)
    assert 1.05 == pc.approx(1.0, rel=0.1)
    assert 2.0 == pc.approx(1.0, abs=1.0)
    assert 'abc' == pc.approx('abc')
    assert not ('abc' == pc.approx('abd'))


# ═══════════════════════════════════════════════════════════════════════
# mark：skipif / xfail / parametrize / 未知恒等
# ═══════════════════════════════════════════════════════════════════════

def test_mark_skipif_true_and_false():
    """退步了会怎样：skipif 条件反了/不生效 → 平台相关用例该跳的没跳、不该跳的全跳。"""
    @pc.mark.skipif(True, reason='nope')
    def skipped():
        raise AssertionError('不该执行')

    with pytest.raises(pc.Skipped):
        skipped()

    @pc.mark.skipif(False, reason='nope')
    def runs():
        return 1
    assert runs() == 1


def test_mark_xfail_semantics():
    """退步了会怎样：xfail 吞掉/不吞异常、strict XPASS 不报错 → 预期失败面失真。"""
    def _raw_fails():
        raise RuntimeError('x')

    def _raw_passes():
        return 1

    fails = pc.mark.xfail(reason='known')(_raw_fails)
    unexpectedly_passes = pc.mark.xfail(reason='known', strict=True)(_raw_passes)

    pc._invoke(fails, {})
    try:
        pc._invoke(unexpectedly_passes, {})
    except AssertionError as exc:
        assert 'XPASS' in str(exc), exc
    else:
        raise AssertionError('strict xfail 未产生 XPASS')

    def _raw_active_false():
        return 2

    active_false = pc.mark.xfail(condition=False, reason='off')(_raw_active_false)
    pc._invoke(active_false, {})


def test_mark_xfail_bare_decorator():
    """退步了会怎样：`@pytest.mark.xfail`（无括号，真实 pytest 支持）把函数变成 deco →
    mdtest 里裸 xfail 的用例直接 TypeError。C1 修复后：返回原函数且带 xfail 元数据。"""
    @pc.mark.xfail
    def f():
        return 1
    assert f() == 1
    assert f._mdtest_xfail[0] is True


def test_mark_parametrize_single_and_multi():
    """退步了会怎样：parametrize 参数绑错/多参数 zip 错 → 每个 case 拿到错的值。"""
    seen = []

    @pc.mark.parametrize('x', [1, 2])
    def single(x):
        seen.append(x)

    pc._invoke(single, {})
    assert seen == [1, 2]

    pairs = []

    @pc.mark.parametrize('a,b', [(1, 2), (3, 4)])
    def multi(a, b):
        pairs.append((a, b))

    pc._invoke(multi, {})
    assert pairs == [(1, 2), (3, 4)]


def test_mark_unknown_is_identity():
    """退步了会怎样：未知 mark 抛 AttributeError → 迁移来的测试用了新 mark 直接崩。"""
    def f():
        return 3

    @pc.mark.slow
    def g():
        return 4
    assert f() == 3 and g() == 4


# ═══════════════════════════════════════════════════════════════════════
# fixture / resolve / call / call_method
# ═══════════════════════════════════════════════════════════════════════

def test_fixture_registration_and_dependency_resolution():
    """退步了会怎样：注册夹具不可用/依赖不递归解析 → 迁移测试全部 UnknownFixture。"""
    @pc.fixture
    def base():
        return 10

    @pc.fixture
    def derived(base):
        return base + 1

    env = {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()}
    assert pc.resolve_fixture('derived', env) == 11


def test_fixture_builtins_and_unknown_lookup():
    """退步了会怎样：内建 tmp_path/monkeypatch/capsys 缺失，或未知夹具静默返回 None
    → 测试拿到错对象还继续跑。"""
    env = {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()}
    assert pc.resolve_fixture('tmp_path', env) == '/tmp'
    assert isinstance(pc.resolve_fixture('monkeypatch', env), pc.MonkeyPatch)
    cap = pc.resolve_fixture('capsys', env)
    assert hasattr(cap, 'readouterr')
    with pytest.raises(LookupError, match='未知夹具'):
        pc.resolve_fixture('nope', env)


def test_fixture_yield_returns_value():
    """退步了会怎样：`@pytest.fixture def f(): yield x` 在垫片里返回 generator →
    迁移测试拿到的是生成器而非夹具值。C3 修复后取到 yield 值，结束时可触发 teardown。"""
    finished = []

    @pc.fixture
    def gen():
        yield 7
        finished.append('done')

    env = {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()}
    assert pc.resolve_fixture('gen', env) == 7
    assert finished == []
    pc.finalize_fixtures(env)
    assert finished == ['done']
    pc.finalize_fixtures(env)   # 幂等，不重复 teardown

# C4：setup_method 内部 TypeError 不得重试
def test_call_method_internal_setup_typeerror_not_retried():
    """退步了会怎样：把 setup_method 体内抛的 TypeError 误判为签名不匹配并重试 →
    初始化副作用执行两次且真实异常被掩盖。"""
    calls = []

    class C:
        def setup_method(self):
            calls.append('setup')
            raise TypeError('real bug inside setup')

        def test_x(self):
            pass

    with pytest.raises(TypeError, match='real bug inside setup'):
        pc.call_method(C, 'test_x', {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()})
    assert calls == ['setup']

# C5：依赖环必须显式报错
def test_fixture_cycle_raises_runtime_error():
    """退步了会怎样：fixture 依赖环静默（一方拿到 None）→ 测试在错误数据上继续跑。"""
    @pc.fixture
    def a(b):
        return 'a'

    @pc.fixture
    def b(a):
        return 'b'

    env = {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()}
    with pytest.raises(RuntimeError, match='依赖环'):
        pc.resolve_fixture('a', env)


def test_call_resolves_fixtures_and_parametrize_args():
    """退步了会怎样：call 把参数名当夹具解析（parametrize 参数抛 LookupError）→
    参数化用例无法执行。"""
    @pc.fixture
    def base():
        return 2

    got = []

    @pc.mark.parametrize('x', [5])
    def t(base, x):
        got.append((base, x))

    pc.call(t, {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()})
    assert got == [(2, 5)]


def test_call_method_setup_and_missing_setup():
    """退步了会怎样：call_method 不实例化/不调用 setup_method → 类级夹具与初始化被跳过；
    没有 setup_method 时又崩。"""
    calls = []

    class C:
        def __init__(self, tmp_path):
            self.tmp = tmp_path

        def setup_method(self, method):
            calls.append(('setup', method.__name__))

        def test_one(self):
            calls.append(('run', self.tmp))

    pc.call_method(C, 'test_one', {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()})
    assert calls == [('setup', 'test_one'), ('run', '/tmp')]

    class D:
        def test(self):
            calls.append(('d',))

    pc.call_method(D, 'test', {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()})
    assert ('d',) in calls


# ═══════════════════════════════════════════════════════════════════════
# capsys
# ═══════════════════════════════════════════════════════════════════════

def test_capsys_captures_and_resets():
    """退步了会怎样：capture 不截获/readouterr 不清零 → 每个用例读到上一个用例的输出。"""
    env = {'tmp_path': '/tmp', 'monkeypatch': pc.MonkeyPatch()}
    cap = pc.resolve_fixture('capsys', env)
    print('hello')
    sys.stderr.write('err')
    out = cap.readouterr()
    assert out.out.strip() == 'hello' and out.err == 'err'
    empty = cap.readouterr()
    assert empty.out == '' and empty.err == ''
    cap.restore()


# ═══════════════════════════════════════════════════════════════════════
# monkeypatch
# ═══════════════════════════════════════════════════════════════════════

def test_monkeypatch_setattr_setenv_delattr_undo():
    """退步了会怎样：undo 不恢复/环境变量泄漏 → 用例间互相污染（本仓库反复踩过的盲区）。"""
    class O:
        x = 1

    mp = pc.MonkeyPatch()
    mp.setattr(O, 'x', 2)
    mp.setenv('MDTEST_X', '1')
    assert O.x == 2 and os.environ['MDTEST_X'] == '1'
    mp.undo()
    assert O.x == 1
    assert 'MDTEST_X' not in os.environ


def test_monkeypatch_delenv_raising_and_string_target():
    """退步了会怎样：delenv 缺失变量静默通过（应 raising 报错）或 setattr 接受字符串目标
    （把真实模块属性改坏且难撤回）。"""
    mp = pc.MonkeyPatch()
    with pytest.raises(KeyError):
        mp.delenv('SURELY_NOT_SET_XYZ', raising=True)
    with pytest.raises(TypeError):
        mp.setattr('os.getcwd', 'x', 1)

    os.environ['MDTEST_DEL'] = 'v'
    mp.delenv('MDTEST_DEL')
    assert 'MDTEST_DEL' not in os.environ
    mp.undo()


def test_monkeypatch_delattr_missing_raises():
    """退步了会怎样：删错属性名却不报错 → 测试以为已隔离，实际旧属性还在。

    C2 修复后与 pytest 一致：删不存在的属性抛 AttributeError。"""
    class O:
        pass
    mp = pc.MonkeyPatch()
    with pytest.raises(AttributeError):
        mp.delattr(O, 'missing')


# ═══════════════════════════════════════════════════════════════════════
# pytest 命名空间
# ═══════════════════════════════════════════════════════════════════════

def test_pytest_namespace_exports():
    """退步了会怎样：exec 环境注入的 pytest 对象缺原语（raises/skip/mark/...）→
    迁移后的测试 import 阶段就 AttributeError。"""
    for name in ('raises', 'approx', 'skip', 'fail', 'mark', 'fixture',
                 'MonkeyPatch', 'Skipped'):
        assert hasattr(pc.pytest, name), name
