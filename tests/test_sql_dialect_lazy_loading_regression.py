# -*- coding: utf-8 -*-
"""回归测试：sql 公开方言 API 触发惰性加载（BUG-347）。

内置方言（sqlite/spark/postgres…）通过 `vools/sql/__init__.py` 的模块级
`__getattr__` **惰性导入**。但公开 API 直接查 manager 注册表：

    import vools.sql as s
    s.list_dialects()          # 修复前 -> []（内置方言都存在却没登记）
    s.get_dialect('sqlite')    # -> KeyError "Dialect 'sqlite' not registered"
    s.has_dialect('sqlite')    # -> False
    s.create_dialect('sqlite') # -> KeyError

即「方言实际可用却报未注册」，除非用户先手动 `s.sqlite` 触发导入并自行
register_dialect。

修复：`get_dialect/create_dialect/has_dialect/list_dialects` 先按需
`_load_dialect(name)`（内含防重入与失败缓存），加载后由
`_auto_register_dialect` 把模块内的 Dialect 子类登记到 manager。

注意：注册表是**进程级全局**，其它测试可能已注册 sqlite，因此本测试用
**独立子进程**验证「干净进程里首次调用即可用」。
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SNIPPET = """
import vools.sql as s
dialects = sorted(s.list_dialects())
assert 'sqlite' in dialects, dialects
assert 'spark' in dialects, dialects
assert s.has_dialect('sqlite') is True
assert s.get_dialect('sqlite').__name__ == 'SqliteDialect'
assert type(s.create_dialect('sqlite')).__name__ == 'SqliteDialect'
print('OK', ','.join(dialects))
"""


def _run(code):
    env = dict(os.environ)
    env['PYTHONPATH'] = ROOT
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run([sys.executable, '-c', code], capture_output=True,
                          text=True, env=env, timeout=120)


class TestFreshProcessLazyLoad:
    def test_public_api_triggers_loading(self):
        proc = _run(_SNIPPET)
        assert proc.returncode == 0, f'stdout={proc.stdout!r} stderr={proc.stderr!r}'
        assert 'OK' in proc.stdout

    def test_list_dialects_not_empty_in_clean_process(self):
        proc = _run("import vools.sql as s; print(sorted(s.list_dialects()))")
        assert proc.returncode == 0, proc.stderr
        assert 'sqlite' in proc.stdout

    def test_missing_dependency_still_keyerror(self):
        # mysql 子模块在本环境不存在 -> 明确 KeyError（不是静默伪注册）
        proc = _run("""
import vools.sql as s
try:
    s.get_dialect('mysql')
except KeyError:
    print('KEYERROR')
""")
        assert proc.returncode == 0, proc.stderr
        assert 'KEYERROR' in proc.stdout


class TestInProcess:
    def test_get_dialect_after_warmup(self):
        import vools.sql as s

        _ = s.sqlite
        assert s.has_dialect('sqlite') is True
        assert s.get_dialect('sqlite').__name__ == 'SqliteDialect'

    def test_registered_dialect_still_works(self):
        from vools.sql import get_dialect, register_dialect
        from vools.sql.core.dialect import Dialect

        class _TempDialect(Dialect):
            name = 'temp_dialect'

        register_dialect('temp_bug347', _TempDialect)
        assert get_dialect('temp_bug347') is _TempDialect