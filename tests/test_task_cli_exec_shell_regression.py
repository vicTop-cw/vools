# -*- coding: utf-8 -*-
"""回归测试：cli_execute 的 shell 模式参数处理（BUG-381）。

`vools.task.core.cli_exec.execute` 在 `cli.shell=True` 时有两处缺陷：

1. **`script` / `script_path` 被静默丢弃**：构造命令时只有
   `if script_arg is not None and not shell: full_cmd.append(script_arg)`，
   shell 模式既不追加脚本路径，也不报错 —— 解释器被无参启动（实测拿到
   Python 交互式 banner），结果却返回 `ok=True`（假成功）；
2. **追加参数未引号化**：`" ".join([cmd_str] + args)` 让含空格的路径/参数被
   shell 拆开（实测 `E:\\Program` is not recognized），含分号的参数则直接
   变成 shell 命令分隔。

修复：shell 模式下 cmd 字符串按原样使用（shell 语法由调用方负责），其后每个
追加参数（含脚本路径）按平台做**引号化**（Windows 用
`subprocess.list2cmdline`，POSIX 用 `shlex.quote`）；结果里的 `cmd` 字段反映
真实执行的命令串。

非 shell 模式（`shlex.split` + 列表传参）与 stdin/env/timeout/check/未知语言
等路径行为不变。
"""

import os
import sys

import pytest

from vools.task.core.cli_exec import cli_execute

PY = sys.executable
PYQ = f'"{PY}"'      # 含空格路径在 cmd 中的正确写法（shlex.split 依据）


class TestShellModeScript:
    def test_script_is_executed(self):
        # 修复前：脚本被丢弃 → 解释器进入交互模式 → ok=True 但 stdout 为空
        r = cli_execute({'cli': {'cmd': PYQ, 'lang': 'python',
                                 'script': 'print("HELLO_FROM_SCRIPT")',
                                 'shell': True, 'timeout_sec': 30}})
        assert 'HELLO_FROM_SCRIPT' in r['stdout'], r

    def test_script_path_is_executed(self, tmp_path):
        p = tmp_path / 's.py'
        p.write_text('print("FROM_PATH")', encoding='utf-8')
        r = cli_execute({'cli': {'cmd': PYQ, 'lang': 'python',
                                 'script_path': str(p),
                                 'shell': True, 'timeout_sec': 30}})
        assert 'FROM_PATH' in r['stdout'], r

    def test_cmd_field_reflects_real_command(self):
        r = cli_execute({'cli': {'cmd': PYQ, 'args': ['-c', 'print(1)'],
                                 'shell': True, 'timeout_sec': 30}})
        assert '-c' in r['cmd']


class TestShellModeArgsQuoting:
    def test_args_with_spaces(self):
        r = cli_execute({'cli': {'cmd': PYQ,
                                 'args': ['-c', 'import sys; print(sys.argv[1:])',
                                          'a b', 'c;d'],
                                 'shell': True, 'timeout_sec': 30}})
        assert "['a b', 'c;d']" in r['stdout'], r


class TestNonShellUnchanged:
    def test_args(self):
        r = cli_execute({'cli': {'cmd': PYQ,
                                 'args': ['-c', 'import sys; print(sys.argv[1:])',
                                          'a b', 'c;d'],
                                 'timeout_sec': 30}})
        assert "['a b', 'c;d']" in r['stdout'], r

    def test_script(self):
        r = cli_execute({'cli': {'cmd': PYQ, 'lang': 'python',
                                 'script': 'print("NON_SHELL")',
                                 'timeout_sec': 30}})
        assert 'NON_SHELL' in r['stdout'], r

    def test_stdin(self):
        r = cli_execute({'cli': {'cmd': PYQ,
                                 'args': ['-c', 'import sys; print(sys.stdin.read())'],
                                 'stdin': 'PIPE_DATA', 'timeout_sec': 30}})
        assert 'PIPE_DATA' in r['stdout']

    def test_env(self):
        r = cli_execute({'cli': {'cmd': PYQ,
                                 'args': ['-c', 'import os; print(os.environ.get("MYVAR"))'],
                                 'env': {'MYVAR': 'ENV_OK'}, 'timeout_sec': 30}})
        assert 'ENV_OK' in r['stdout']


class TestErrorPaths:
    def test_missing_command(self):
        r = cli_execute({'cli': {'cmd': 'no_such_cmd_xyz_381', 'timeout_sec': 5}})
        assert r['ok'] is False and r['error']

    def test_timeout(self):
        r = cli_execute({'cli': {'cmd': PYQ,
                                 'args': ['-c', 'import time; time.sleep(5)'],
                                 'timeout_sec': 0.2}})
        assert r['ok'] is False and '超时' in str(r['error'])

    def test_check_nonzero_exit(self):
        r = cli_execute({'cli': {'cmd': PYQ, 'args': ['-c', 'import sys; sys.exit(3)'],
                                 'check': True, 'timeout_sec': 30}})
        assert r['ok'] is False and r['exit_code'] == 3

    def test_unknown_language(self):
        r = cli_execute({'cli': {'lang': 'no_such_lang_381'}})
        assert r['ok'] is False and '未知语言' in str(r['error'])