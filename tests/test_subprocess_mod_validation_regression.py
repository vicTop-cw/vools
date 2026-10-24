# -*- coding: utf-8 -*-
"""回归测试：VProcess / run_command 的命令与超时参数校验（BUG-405）。

`VProcess` 把参数原样交给 `subprocess.Popen`，没有入口校验：

    VProcess([])        # OSError: [WinError 87] 参数错误（天书）
    VProcess('')        # 同上
    VProcess(123)       # TypeError: 'int' object is not iterable（跑偏）
    VProcess(cmd, timeout=-1)   # 接受；负超时语义未定义

`run_command` / `run_command_async` 内部都构造 `VProcess`，因此同样受影响。
修复：cmd 必须是非空 str 或非空字符串序列；timeout 必须是数字（bool 除外）
且 >= 0（0 合法），或 None。正常执行/返回码/流式读取行为不变。
"""

import sys

import pytest

from vools.vconcurrent.subprocess_mod import VProcess, run_command, run_command_async

PY = sys.executable


class TestCommandValidation:
    @pytest.mark.parametrize('cmd', [[], (), ''])
    def test_empty_command(self, cmd):
        with pytest.raises(ValueError) as ei:
            VProcess(cmd)
        assert 'cmd' in str(ei.value)

    def test_whitespace_command(self):
        with pytest.raises(ValueError):
            VProcess('   ')

    @pytest.mark.parametrize('cmd', [123, None, 3.5, {'a': 1}])
    def test_bad_command_type(self, cmd):
        with pytest.raises(TypeError):
            VProcess(cmd)

    @pytest.mark.parametrize('parts', [['echo', 1], ['echo', None], [b'echo']])
    def test_non_str_sequence_items(self, parts):
        with pytest.raises(TypeError) as ei:
            VProcess(parts)
        assert 'cmd[' in str(ei.value)


class TestTimeoutValidation:
    @pytest.mark.parametrize('timeout', [-1, -0.5, -100])
    def test_negative_timeout(self, timeout):
        with pytest.raises(ValueError):
            VProcess([PY, '-c', 'print(1)'], timeout=timeout)

    @pytest.mark.parametrize('timeout', ['5', True, [1]])
    def test_non_numeric_timeout(self, timeout):
        with pytest.raises(TypeError):
            VProcess([PY, '-c', 'print(1)'], timeout=timeout)

    def test_none_and_zero_allowed(self):
        p = VProcess([PY, '-c', 'print("x")'], timeout=None)
        assert p.communicate(timeout=10)[0].strip() == 'x'
        p2 = VProcess([PY, '-c', 'print("y")'], timeout=0)
        # timeout=0 表示已到期：communicate 允许显式覆盖
        assert p2.communicate(timeout=10)[0].strip() == 'y'


class TestWrapperValidation:
    def test_run_command_empty(self):
        with pytest.raises(ValueError):
            run_command([])

    def test_run_command_negative_timeout(self):
        with pytest.raises(ValueError):
            run_command([PY, '-c', 'print(1)'], timeout=-1)

    def test_run_command_async_empty(self):
        with pytest.raises(ValueError):
            run_command_async([])


class TestNormalExecutionUnchanged:
    def test_run_command(self):
        rc, out, err = run_command([PY, '-c', 'print("hello")'])
        assert (rc, out.strip(), err) == (0, 'hello', '')

    def test_returncode(self):
        p = VProcess([PY, '-c', 'import sys; sys.exit(7)'])
        p.communicate(timeout=30)
        assert p.returncode == 7

    def test_run_command_stderr(self):
        rc, out, err = run_command(
            [PY, '-c', 'import sys; print("boom", file=sys.stderr); sys.exit(2)'])
        assert rc == 2
        assert 'boom' in err

    def test_timeout_kills_and_raises(self):
        import subprocess

        with pytest.raises(subprocess.TimeoutExpired):
            run_command([PY, '-c', 'import time; time.sleep(5)'], timeout=0.3)

    def test_iter_stdout(self):
        p = VProcess([PY, '-c', 'print("l1"); print("l2")'], text=True)
        assert [line.strip() for line in p.iter_stdout()] == ['l1', 'l2']
        p.communicate(timeout=30)