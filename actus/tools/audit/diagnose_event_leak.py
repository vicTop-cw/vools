# -*- coding: utf-8 -*-
"""诊断：逐个测试文件跑，找出谁在全局 EventBus 上留下未跟踪的订阅。"""
import glob
import io
import os
import sys
import contextlib

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import pytest  # noqa: E402
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus import mcp_server  # noqa: E402
from vools.actus.eventbus import get_event_bus  # noqa: E402

files = sorted(glob.glob(os.path.join(REPO, 'tests', 'test_*.py')))
offender = None
for f in files:
    name = os.path.basename(f)
    if 'round11' in name:
        break
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = pytest.main([f, '-q', '--no-header', '-p', 'no:cacheprovider'])
    bus = get_event_bus()
    try:
        state = mcp_server._EVENT_FORWARDING
        tracked = len(state.get('subs') or [])
    except Exception:
        tracked = -1
    count = bus.subscriber_count()
    if count != tracked:
        print('LEAK? %-42s bus=%d tracked=%d code=%s' % (name, count, tracked, code))
        offender = name
        break
    print('ok   %-42s bus=%d' % (name, count))
print('offender:', offender)
