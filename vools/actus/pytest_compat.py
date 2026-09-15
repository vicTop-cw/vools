"""vools.actus.pytest_compat — md 测试环境中的 `pytest` 兼容垫片。

用途：tests/*.py 机械迁移为 *.test.md 后，原测试体中的 pytest 语义
（raises/approx/skip/mark/fixture）由本模块在 mdtest exec 环境中提供，
测试代码零改动（docs/33 §Phase 2）。

仅覆盖 Actus 测试实际用到的子集；未知 mark 走恒等装饰器降级。
"""
import functools
import inspect
import io
import re
import sys
import types
from typing import Any, Dict, List

# ═══════════════════════════════════════════════════════
# 异常与基本断言原语
# ═══════════════════════════════════════════════════════


class Skipped(Exception):
    """pytest.skip 等价异常；mdtest 捕获后计为 skipped。"""


def skip(reason: str = '') -> None:
    raise Skipped(reason)


def fail(reason: str = '') -> None:
    raise AssertionError(reason)


class _RaisesContext:
    """pytest.raises 上下文管理器（含 match 与 .value）。"""

    def __init__(self, expected_exception, match: str = None):
        self.expected = expected_exception
        self.match = match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f'DID NOT RAISE {self.expected}')
        expected = self.expected if isinstance(self.expected, tuple) else (self.expected,)
        if not issubclass(et, expected):
            return False  # 非预期异常，原样抛出
        self.value = ev
        if self.match and not re.search(self.match, str(ev)):
            raise AssertionError(f'pattern {self.match!r} not found in {str(ev)!r}')
        return True


def raises(expected_exception, match: str = None) -> _RaisesContext:
    return _RaisesContext(expected_exception, match=match)


class approx:
    """pytest.approx 数字近似（rel/abs 容差；非数值降级为精确比较）。"""

    def __init__(self, expected, rel=None, abs=None):
        self.expected = expected
        self.rel = 1e-6 if rel is None else rel
        self.abs = 1e-12 if abs is None else abs

    def __eq__(self, actual) -> bool:
        try:
            return abs(actual - self.expected) <= max(self.rel * abs(self.expected), self.abs)
        except TypeError:
            return actual == self.expected

    def __req__(self, other) -> bool:
        return self.__eq__(other)


# ═══════════════════════════════════════════════════════
# mark 装饰器（skipif / xfail / parametrize / 其余恒等）
# ═══════════════════════════════════════════════════════


def _copy_meta(src, dst):
    for attr in ('_mdtest_parametrize', '_mdtest_xfail'):
        if hasattr(src, attr):
            setattr(dst, attr, getattr(src, attr))
    return dst


class _Mark:
    """pytest.mark 兼容：skipif/xfail/parametrize 实装，其余恒等。"""

    @staticmethod
    def skipif(condition, reason: str = None):
        def deco(fn):
            if condition:
                @functools.wraps(fn)
                def wrapper(*a, **k):
                    raise Skipped(reason or 'skipif')
                return _copy_meta(fn, wrapper)
            return fn
        return deco

    @staticmethod
    def xfail(condition=None, reason: str = None, strict: bool = False):
        def deco(fn):
            fn._mdtest_xfail = (bool(condition if condition is not None else True), strict, reason)
            return fn
        return deco

    @staticmethod
    def parametrize(argnames, argvalues):
        names = [n.strip() for n in argnames.split(',')] if isinstance(argnames, str) else list(argnames)

        def deco(fn):
            fn._mdtest_parametrize = (names, argvalues)
            return fn
        return deco

    def __getattr__(self, name):
        # 未知 mark（如 mark.slow）恒等降级
        def deco(fn):
            return fn
        return deco


mark = _Mark()


# ═══════════════════════════════════════════════════════
# fixture 注册表（每用例重置，setup 块重跑即重新注册）
# ═══════════════════════════════════════════════════════

_FIXTURE_REGISTRY: Dict[str, Any] = {}


def reset_fixtures() -> None:
    _FIXTURE_REGISTRY.clear()


def fixture(fn=None, **kwargs):
    """pytest.fixture 兼容：注册到当前用例的夹具注册表。"""
    def deco(fn):
        _FIXTURE_REGISTRY[fn.__name__] = fn
        return fn
    if callable(fn):
        return deco(fn)
    return deco


def resolve_fixture(name: str, env: Dict[str, Any]) -> Any:
    """按名解析夹具值：内建 > 注册夹具（递归解析其参数，记忆化）。"""
    memo: Dict[str, Any] = env.setdefault('_fixture_memo', {})
    if name in memo:
        return memo[name]
    if name == 'tmp_path':
        return env['tmp_path']
    if name == 'monkeypatch':
        return env['monkeypatch']
    if name == 'capsys':
        cap = _Capsys(env)
        env['capsys'] = cap
        return cap
    if name in _FIXTURE_REGISTRY:
        fn = _FIXTURE_REGISTRY[name]
        memo[name] = None  # 环路护栏
        kwargs = {p: resolve_fixture(p, env)
                  for p in inspect.signature(fn).parameters}
        val = fn(**kwargs)
        memo[name] = val
        return val
    raise LookupError(f'未知夹具: {name}（mdtest 内建: tmp_path/monkeypatch/capsys + @pytest.fixture）')


# ═══════════════════════════════════════════════════════
# 调用器：_call(fn) / _call_method(cls, mname)
# ═══════════════════════════════════════════════════════


def _invoke(fn, kwargs: Dict[str, Any]) -> None:
    """带 parametrize/xfail 语义地调用 fn；失败抛异常，skip 抛 Skipped。"""
    pm = getattr(fn, '_mdtest_parametrize', None)
    combos = [None]
    if pm:
        names, values = pm
        combos = [dict(zip(names, c if isinstance(c, tuple) else (c,))) for c in values]

    xfail_meta = getattr(fn, '_mdtest_xfail', None)
    for extra in combos:
        call_kwargs = dict(kwargs)
        if extra:
            call_kwargs.update(extra)
        if xfail_meta:
            active, strict, reason = xfail_meta
            if not active:
                fn(**call_kwargs)
                continue
            try:
                fn(**call_kwargs)
            except Skipped:
                raise
            except Exception:
                pass  # 预期失败 → xfailed，视为通过
            else:
                if strict:
                    raise AssertionError(f'XPASS(strict): {reason or fn.__name__}')
        else:
            fn(**call_kwargs)


def call(fn, env: Dict[str, Any]) -> None:
    """解析 fn 签名中的夹具参数并调用（parametrize 在 _invoke 内展开）。"""
    params = list(inspect.signature(fn).parameters)
    kwargs = {}
    for p in params:
        try:
            kwargs[p] = resolve_fixture(p, env)
        except LookupError:
            if p in (getattr(fn, '_mdtest_parametrize', (None, []))[0] or []):
                continue  # parametrize 参数由 _invoke 提供
            raise
    _invoke(fn, kwargs)


def call_method(cls, mname: str, env: Dict[str, Any]) -> None:
    """实例化测试类（解析 __init__ 夹具）→ setup_method → 调用测试方法。"""
    sig = inspect.signature(cls.__init__)
    init_params = [p for p, v in sig.parameters.items()
                   if p != 'self'
                   and v.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                      inspect.Parameter.VAR_KEYWORD)]
    kwargs = {p: resolve_fixture(p, env) for p in init_params}
    inst = cls(**kwargs)
    sm = getattr(inst, 'setup_method', None)
    if callable(sm):
        try:
            sm(getattr(inst, mname))
        except TypeError:
            sm()
    call(getattr(inst, mname), env)


# ═══════════════════════════════════════════════════════
# capsys 最小实现
# ═══════════════════════════════════════════════════════


class _Capsys:
    """capsys：截获当前 sys.stdout/stderr，readouterr() 读取并清零。"""

    def __init__(self, env: Dict[str, Any]):
        self._out = io.StringIO()
        self._err = io.StringIO()
        self._env = env
        self._old_out, self._old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = self._out, self._err

    def readouterr(self):
        o, e = self._out.getvalue(), self._err.getvalue()
        self._out.seek(0)
        self._out.truncate(0)
        self._err.seek(0)
        self._err.truncate(0)
        return types.SimpleNamespace(out=o, err=e)

    def restore(self) -> None:
        if sys.stdout is self._out:
            sys.stdout = self._old_out
        if sys.stderr is self._err:
            sys.stderr = self._old_err


# ═══════════════════════════════════════════════════════
# monkeypatch（自 mdtest 收敛至此，供两处共用）
# ═══════════════════════════════════════════════════════

_MISSING = object()


class MonkeyPatch:
    """monkeypatch 最小子集：setattr / delattr / setenv / delenv / undo。"""

    def __init__(self):
        self._undo: List[Any] = []

    def setattr(self, obj, name, value):
        if isinstance(obj, str):
            raise TypeError('setattr 目标不能是字符串；设置环境变量请用 setenv')
        old = getattr(obj, name, _MISSING)
        self._undo.append((obj, name, old))
        setattr(obj, name, value)

    def delattr(self, obj, name):
        old = getattr(obj, name, _MISSING)
        self._undo.append((obj, name, old))
        if old is not _MISSING:
            delattr(obj, name)

    def setenv(self, name, value):
        old = os.environ.get(name, _MISSING)
        self._undo.append((os.environ, name, old))
        os.environ[name] = value

    def delenv(self, name, raising=True):
        old = os.environ.get(name, _MISSING)
        self._undo.append((os.environ, name, old))
        if old is not _MISSING:
            del os.environ[name]
        elif raising:
            raise KeyError(name)

    def undo(self):
        import os as _os
        for obj, name, old in reversed(self._undo):
            if old is _MISSING:
                if obj is _os.environ:
                    _os.environ.pop(name, None)
                elif hasattr(obj, name):
                    try:
                        delattr(obj, name)
                    except AttributeError:
                        pass
            else:
                setattr(obj, name, old)
        self._undo.clear()


import os  # noqa: E402  — MonkeyPatch.setenv 使用


# ═══════════════════════════════════════════════════════
# pytest 命名空间对象（注入 exec_env['pytest']）
# ═══════════════════════════════════════════════════════

pytest = types.SimpleNamespace(
    raises=raises,
    approx=approx,
    skip=skip,
    fail=fail,
    mark=mark,
    fixture=fixture,
    MonkeyPatch=MonkeyPatch,
    Skipped=Skipped,
)
