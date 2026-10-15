# -*- coding: utf-8 -*-
"""bridges 测试的 Python 3.6 兼容垫片。

各语言桥接测试大量使用 ``asyncio.run(...)``（87 处）。``asyncio.run`` 是
Python 3.7 才加入的便利函数；Python 3.6 的 asyncio 只有
``get_event_loop()`` / ``run_until_complete()``，直接调用
``asyncio.run`` 会抛 ``AttributeError: module 'asyncio' has no attribute
'run'`` —— 实测 py3.6 下 bridges 有 28 个语言测试文件因此失败。

框架本身已提供版本无关的实现
``vools.bridge.core.compat.asyncio_compat.run``（py3.7+ 转发标准库，
py3.6 手工实现）。这里在 py3.6 上把它挂到 ``asyncio.run``，让测试里
原样的 ``asyncio.run(...)`` 调用两种版本都能工作，且复用框架已有实现
（含取消残留任务、关闭 async generators 等收尾逻辑）。

另外：py3.6 上没有可用的 pytest-asyncio（现代版本要求 py3.8+），而 pytest
对返回协程的 ``async def`` 测试函数默认【静默跳过】（PytestUnhandledCoroutineWarning：
"async def functions are not natively supported and have been skipped"），
这是一种【假 skip】——测试根本没跑，却计为通过。bridges 的 async 装饰器测试类
（如 TestCangjieAsync）因此在 py3.6 上全被假跳过。这里注册 pytest_pyfunc_call 钩子：
遇到协程测试就用 asyncio.run（py3.6 下即上面的 compat.run）真实执行并等待结果，
让 async 测试在两种 Python 版本下都真正运行，不再假 skip。
"""
import asyncio
import inspect
import sys


if sys.version_info < (3, 7) and not hasattr(asyncio, 'run'):
    from vools.bridge.core.compat.asyncio_compat import run as _compat_run
    asyncio.run = _compat_run


def pytest_pyfunc_call(pyfuncitem):
    """把 async def 测试函数真正跑起来（py3.6 无 pytest-asyncio 时尤其必要）。

    返回非 None 即表示本钩子已处理该测试；普通同步测试返回 None 交回 pytest 默认。
    仅在确实没有 asyncio 插件（py3.6 装不了现代 pytest-asyncio）的平台上接管，
    py3.7+ 有 pytest-asyncio 时交回它处理，避免与本钩子重复驱动事件循环。
    """
    if sys.version_info >= (3, 7):
        return None
    testfunction = pyfuncitem.obj
    if not inspect.iscoroutinefunction(testfunction):
        return None
    # 只按测试实际声明的形参名注入 fixture（如 monkeypatch/tmp_path），
    # 不盲目塞全部 args，避免把非 fixture 的位置参数也当 fixture 解析。
    argnames = pyfuncitem._fixtureinfo.argnames
    kwargs = {name: pyfuncitem.funcargs[name] for name in argnames}
    asyncio.run(testfunction(**kwargs))
    return True
