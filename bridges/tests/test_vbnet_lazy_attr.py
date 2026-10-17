# -*- coding: utf-8 -*-
"""bridges/tests/test_vbnet_lazy_attr.py — vbnet.api 两种取法必须都成立（钉 BUG-77/78）

同包同一个 `api`，历史上两种写法两种结果：
  - `from vools.bridge.vbnet import api`   —— 一直能成（importlib 的 from-import
    会退回直接导入子模块，绕过 __getattr__）；
  - `vools.bridge.vbnet.api` 属性访问      —— py3.6 下拿到 MISSING：模块级
    __getattr__ 属 PEP 562（3.7+ 才生效），而 vbnet 的 api 是【只靠 __getattr__
    暴露】的懒加载名，3.6 上没人绑它（2026-10-16 实测；vools-bridges
    requires-python = ">=3.6"，属承诺范围内必须可用 = BUG-78）。
  另有一处互递归（BUG-77）：__getattr__ 里的 `from . import api` 会被
  _handle_fromlist 的 hasattr(父包,'api') 回调进 __getattr__ 自己，实测一次属性
  访问自递归 50 层（修复靠 `except Exception` 吞掉 RecursionError 才"看着能用"）。

既有 bridges/tests/test_vbnet_api.py 只测 from-import 那一侧，所以这两条都漏了；
本锁专门钉"两种取法等价 + 不自递归"。api 子模块本身要 pywin32/COM 才好用，
但【能不能拿到模块对象】与 COM 是否可用是两件事，本锁只判前者。
"""

import importlib
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, 'bridges')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MODULE = 'vools.bridge.vbnet'


def _module_obj():
    """取【真模块对象】。

    不能用 `import vools.bridge.vbnet as V`：vools/bridge/__init__.py 把装饰器
    同名再导出成 globals()['vbnet']（L558），from-import 链上的 as 绑定拿到的
    可能是那个函数而不是模块 —— 上一轮探针就是这么把结论测歪的（自己造出
    "form A MISSING"的假证据）。sys.modules 里的才是模块本体。
    """
    m = importlib.import_module(MODULE)
    assert isinstance(m, types.ModuleType), '拿到的不是模块: %r' % type(m)
    return m


def test_api_available_by_attribute_access():
    """属性访问必须拿得到 api（py3.6 曾经只有 from-import 能成）。"""
    m = _module_obj()
    assert hasattr(m, 'api'), \
        '%s.api 属性访问失败：__getattr__ 在 py3.6 是死函数（PEP 562 为 3.7+），' \
        '需要 <3.7 主动绑定分支' % MODULE
    assert getattr(m, 'api') is not None


def test_both_access_forms_agree():
    """两种写法必须给出同一个模块对象 —— 不能一个成一个 MISSING。"""
    m = _module_obj()
    ns = {}
    exec('from %s import api as _a' % MODULE, ns)
    via_from = ns['_a']
    via_attr = getattr(m, 'api', None)
    assert via_attr is not None, '属性访问拿不到 api（from-import 却能拿到 = 两本账）'
    assert via_attr is via_from, '两种取法给了不同对象: %r vs %r' % (
        type(via_attr).__name__, type(via_from).__name__)


def test_api_submodule_is_a_module():
    m = _module_obj()
    api = getattr(m, 'api', None)
    if api is None:
        # 3.6 下若真缺 pywin32，属性访问也应给出模块对象（模块本身可导入，
        # 实测 py3.6 importlib.import_module('.api') 成功），所以这不是合法出口
        raise AssertionError('%s.api 仍是 MISSING（BUG-78 复发）' % MODULE)
    assert isinstance(api, types.ModuleType)


def test_no_self_recursion_resolving_api():
    """解析 api 时 __getattr__ 只进一次（修复前实测 50 次；3.6 下应为 0 次）。

    坑（本锁自己踩过一次）：只 pop globals()['api'] 不够 —— 同文件里先跑的
    test_api_available_by_attribute_access 已经把 _api_loaded 置 True，
    _load_api 会在 `if _api_loaded: return True` 处短路、返回 globals().get('api')
    == None，于是测到的是"返回 None"而不是"是否自递归"。所以这里把加载器的
    状态一起复位（_api_loaded/_api_loading/_api_error），测完原样还原。
    """
    m = _module_obj()
    real = m.__getattr__
    calls = []

    def counting(name, _c=calls, _r=real):
        if name == 'api':
            _c.append(1)
            if len(_c) > 20:
                raise RecursionError('probe cap: 自递归')
        return _r(name)

    saved_state = {k: m.__dict__.get(k) for k in ('api', '_api_loaded', '_api_loading', '_api_error')}
    m.__getattr__ = counting
    try:
        sys.setrecursionlimit(1000)
        if sys.version_info >= (3, 7):
            # 冷启动：清掉绑定与"已加载"标记，逼 __getattr__ 真走一遍加载器
            m.__dict__.pop('api', None)
            m._api_loaded = False
            m._api_loading = False
            m._api_error = None
            got = getattr(m, 'api', None)
            assert got is not None, '冷启动解析 api 拿不到模块'
            assert len(calls) == 1, \
                '解析 api 自递归 %d 次（应为 1；修复前实测 50）' % len(calls)
        else:
            # 3.6：不能 pop（__getattr__ 是死函数，pop 掉就只能靠 eager 分支，
            # 而 eager 是一次性的）—— 只验"名字可得 + __getattr__ 一次都没被调"
            got = getattr(m, 'api', None)
            assert got is not None, \
                'py3.6 下 vools.bridge.vbnet.api 应由 <3.7 主动绑定分支提供（BUG-78）'
            assert len(calls) == 0, \
                'py3.6 下模块级 __getattr__ 不该被调用（PEP 562 是 3.7+），实际 %d 次' % len(calls)
    finally:
        m.__getattr__ = real
        for k, v in saved_state.items():
            if v is None:
                m.__dict__.pop(k, None)
            else:
                m.__dict__[k] = v
