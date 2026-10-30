"""mdtest.py 契约测试（Round 50）。

契约:
- _unescape_code: 哨兵还原（@FENCE@ → ```，@HASHBANG@ → #!）
- _fixture_env / _cleanup_fixture_env: 临时夹具环境生命周期
- discover_test_files: 类型校验（str/bytes/非列表 TypeError）+ 目录递归 + 后缀过滤
  + 排除 .venv/node_modules 等 + 文件直收 + 排序
- extract_cases: 类型校验 + #!test 提取 + setup 关联 + 命名优先级（name= > tag= > file::blockN）+ skip 标记
- _BufferedStdout: write/flush/getvalue/buffer/__getattr__
- run_case: 入参校验 + skip 短路 + passed/failed/skipped + setup 可见性 + stdout 捕获
- run_tests: 汇总结构
- print_report: 失败详情 + 汇总行
- main: -v 标志 / 无路径默认 tests / 退出码 0/1
"""

import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import vools.actus.mdtest as mdtest_mod
from vools.actus.mdtest import (
    _BufferedStdout, _cleanup_fixture_env, _fixture_env, _unescape_code,
    discover_test_files, extract_cases, main, print_report, run_case, run_tests,
)


class TestUnescape:
    """_unescape_code 哨兵还原。"""

    def test_fence(self):
        assert _unescape_code("@FENCE@python") == "```python"

    def test_hashbang(self):
        assert _unescape_code("@HASHBANG@config") == "#!config"

    def test_both(self):
        code = "@FENCE@\n@HASHBANG@test\n@FENCE@"
        assert _unescape_code(code) == "```\n#!test\n```"

    def test_noop(self):
        assert _unescape_code("plain code") == "plain code"


class TestFixtureEnv:
    """夹具环境生命周期。"""

    def test_fixture_env_keys(self):
        env = _fixture_env()
        try:
            assert 'tmp_path' in env and 'monkeypatch' in env and 'tmp_root' in env
            assert isinstance(env['tmp_path'], Path)
            assert env['tmp_path'].is_dir()
        finally:
            _cleanup_fixture_env(env)

    def test_cleanup_removes_tmp_root(self):
        env = _fixture_env()
        root = env['tmp_root']
        _cleanup_fixture_env(env)
        assert not os.path.isdir(root)

    def test_cleanup_undoes_monkeypatch(self):
        env = _fixture_env()
        mp = env['monkeypatch']
        mp.setattr(os, 'sep', '!@!')
        assert os.sep == '!@!'
        _cleanup_fixture_env(env)
        assert os.sep != '!@!'

    def test_cleanup_with_capsys(self):
        env = _fixture_env()
        cap = MagicMock()
        env['capsys'] = cap
        _cleanup_fixture_env(env)
        cap.restore.assert_called_once()


class TestDiscoverTestFiles:
    """discover_test_files 发现规则。"""

    def test_rejects_string(self):
        with pytest.raises(TypeError, match="路径列表"):
            discover_test_files("tests/")

    def test_rejects_bytes(self):
        with pytest.raises(TypeError):
            discover_test_files(b"tests/")

    def test_rejects_none(self):
        with pytest.raises(TypeError):
            discover_test_files(None)

    def test_rejects_int(self):
        with pytest.raises(TypeError, match="得到 int"):
            discover_test_files(42)

    def test_dir_recursion_and_suffix(self, tmp_path):
        (tmp_path / "a.test.md").write_text("x", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.test.md").write_text("x", encoding="utf-8")
        (sub / "c.md").write_text("x", encoding="utf-8")  # 非测试文件
        files = discover_test_files([str(tmp_path)])
        assert len(files) == 2
        assert all(f.endswith(".test.md") for f in files)

    def test_excludes_dir_names(self, tmp_path):
        """排除 .venv/node_modules 等（隔离子目录，防测试名本身含 venv）。"""
        root = tmp_path / "scandir"
        root.mkdir()
        for d in ('.venv', 'node_modules', '__pycache__', '.pytest_cache'):
            sub = root / d
            sub.mkdir()
            (sub / f"x.test.md").write_text("x", encoding="utf-8")
        (root / "top.test.md").write_text("x", encoding="utf-8")
        files = discover_test_files([str(root)])
        assert [os.path.basename(f) for f in files] == ["top.test.md"]

    def test_file_direct(self, tmp_path):
        f = tmp_path / "one.test.md"
        f.write_text("x", encoding="utf-8")
        assert discover_test_files([str(f)]) == [str(f)]

    def test_missing_path_ignored(self):
        assert discover_test_files(["Z:/definitely/missing"]) == []

    def test_sorted_output(self, tmp_path):
        (tmp_path / "z.test.md").write_text("x", encoding="utf-8")
        (tmp_path / "a.test.md").write_text("x", encoding="utf-8")
        files = discover_test_files([str(tmp_path)])
        assert [os.path.basename(f) for f in files] == ["a.test.md", "z.test.md"]


class TestExtractCases:
    """extract_cases 用例提取。"""

    def test_rejects_non_path(self):
        with pytest.raises(TypeError):
            extract_cases(123)

    def _write_md(self, tmp_path, body: str) -> str:
        p = tmp_path / "sample.test.md"
        p.write_text(body, encoding="utf-8")
        return str(p)

    def test_extract_test_block(self, tmp_path):
        md = '# T\n\n```python #!test name=hello\nassert 1 == 1\n```\n'
        path = self._write_md(tmp_path, md)
        cases = extract_cases(path)
        assert len(cases) == 1
        c = cases[0]
        assert c['name'] == 'hello'
        assert 'assert 1 == 1' in c['code']
        assert c['file'] == path
        assert c['skip'] is False

    def test_name_priority_tag(self, tmp_path):
        """无 name= 时用 tag=。"""
        md = '```python #!test tag=by_tag\npass\n```\n'
        path = self._write_md(tmp_path, md)
        cases = extract_cases(path)
        assert cases[0]['name'] == 'by_tag'

    def test_name_priority_fallback(self, tmp_path):
        """无 name/tag → 文件名（含 .test）::block序号。"""
        md = '```python #!test\npass\n```\n'
        path = self._write_md(tmp_path, md)
        cases = extract_cases(path)
        assert cases[0]['name'].startswith('sample.test::block')

    def test_setup_association(self, tmp_path):
        """用例继承其之前最近的 setup 块。"""
        md = ('```python #!setup\nX = 42\n```\n'
              '```python #!test name=one\npass\n```\n'
              '```python #!setup\nX = 43\n```\n'
              '```python #!test name=two\npass\n```\n')
        path = self._write_md(tmp_path, md)
        cases = extract_cases(path)
        assert [c['name'] for c in cases] == ['one', 'two']
        assert 'X = 42' in cases[0]['setup']
        assert 'X = 43' in cases[1]['setup']

    def test_skip_flag(self, tmp_path):
        md = '```python #!test name=sk skip\npass\n```\n'
        path = self._write_md(tmp_path, md)
        cases = extract_cases(path)
        assert cases[0]['skip'] is True

    def test_no_test_blocks(self, tmp_path):
        md = '# doc\n\n```python\nplain code\n```\n'
        path = self._write_md(tmp_path, md)
        assert extract_cases(path) == []

    def test_unescape_applied(self, tmp_path):
        """哨兵在提取时还原。"""
        md = '```python #!test name=u\nx = "@FENCE@#!"\n```\n'
        path = self._write_md(tmp_path, md)
        cases = extract_cases(path)
        assert '```#!' in cases[0]['code']


class TestBufferedStdout:
    """_BufferedStdout 替身。"""

    def test_write_returns_len_and_captures(self):
        inner = io.StringIO()
        buf = _BufferedStdout(inner)
        assert buf.write("hello") == 5
        assert buf.getvalue() == "hello"

    def test_buffer_binary(self):
        buf = _BufferedStdout(io.StringIO())
        buf.write("hi")
        assert buf.buffer.getvalue() == b"hi"

    def test_write_non_ascii(self):
        buf = _BufferedStdout(io.StringIO())
        buf.write("中文")
        assert buf.buffer.getvalue() == "中文".encode("utf-8")

    def test_getattr_delegates(self):
        buf = _BufferedStdout(io.StringIO("abc"))
        assert buf.getvalue() == "abc"  # 委托给 inner StringIO
        assert buf.read() == "abc"

    def test_flush_noop(self):
        _BufferedStdout(io.StringIO()).flush()


class TestRunCase:
    """run_case 执行契约。"""

    def test_rejects_non_dict(self):
        with pytest.raises(TypeError, match="case 必须是 dict"):
            run_case(None)

    def test_missing_name(self):
        with pytest.raises(KeyError, match="'name'"):
            run_case({"file": "x.md", "code": "pass"})

    def test_missing_file(self):
        with pytest.raises(KeyError, match="'file'"):
            run_case({"name": "t", "code": "pass"})

    def test_skip_short_circuit(self):
        r = run_case({"name": "t", "file": "f.md", "skip": True})
        assert r['status'] == 'skipped' and r['stdout'] == ''

    def test_passing_case(self):
        r = run_case({"name": "t", "file": "f.md", "code": "assert 1 == 1",
                      "skip": False, "setup": ""})
        assert r['status'] == 'passed' and r['error'] == ''

    def test_failing_case(self):
        r = run_case({"name": "t", "file": "f.md", "code": "assert 1 == 2",
                      "skip": False, "setup": ""})
        assert r['status'] == 'failed'
        assert 'AssertionError' in r['error']

    def test_runtime_error_case(self):
        r = run_case({"name": "t", "file": "f.md", "code": "1 / 0",
                      "skip": False, "setup": ""})
        assert r['status'] == 'failed'
        assert 'ZeroDivisionError' in r['error']

    def test_setup_visible_to_case(self):
        r = run_case({"name": "t", "file": "f.md", "code": "assert X == 42",
                      "skip": False, "setup": "X = 42"})
        assert r['status'] == 'passed'

    def test_stdout_captured(self):
        r = run_case({"name": "t", "file": "f.md", "code": "print('hi there')",
                      "skip": False, "setup": ""})
        assert r['status'] == 'passed'
        assert 'hi there' in r['stdout']

    def test_pytest_import_available(self):
        r = run_case({"name": "t", "file": "f.md",
                      "code": "import pytest; assert pytest.approx(1.0) == 1.0",
                      "skip": False, "setup": ""})
        assert r['status'] == 'passed'

    def test_pytest_raises_works(self):
        r = run_case({"name": "t", "file": "f.md",
                      "code": "import pytest\nwith pytest.raises(ValueError):\n    raise ValueError('x')",
                      "skip": False, "setup": ""})
        assert r['status'] == 'passed'

    def test_pytest_skip_raises(self):
        r = run_case({"name": "t", "file": "f.md",
                      "code": "import pytest; pytest.skip('why')",
                      "skip": False, "setup": ""})
        assert r['status'] == 'skipped'
        assert 'why' in r['error']

    def test_tmp_path_fixture(self):
        r = run_case({"name": "t", "file": "f.md",
                      "code": "p = tmp_path / 'f.txt'; p.write_text('x'); assert p.read_text() == 'x'",
                      "skip": False, "setup": ""})
        assert r['status'] == 'passed'

    def test_stdout_restored_after(self):
        old = sys.stdout
        run_case({"name": "t", "file": "f.md", "code": "pass", "skip": False, "setup": ""})
        assert sys.stdout is old

    def test_pytest_module_restored_after(self):
        """执行前后 sys.modules['pytest'] 保持一致。"""
        before = sys.modules.get('pytest')
        run_case({"name": "t", "file": "f.md", "code": "pass", "skip": False, "setup": ""})
        assert sys.modules.get('pytest') is before


class TestRunTests:
    """run_tests 汇总。"""

    def test_summary_structure(self, tmp_path):
        (tmp_path / "ok.test.md").write_text(
            '```python #!test name=ok\nassert 1 == 1\n```\n', encoding="utf-8")
        (tmp_path / "bad.test.md").write_text(
            '```python #!test name=bad\nassert 1 == 2\n```\n', encoding="utf-8")
        (tmp_path / "skip.test.md").write_text(
            '```python #!test name=sk skip\npass\n```\n', encoding="utf-8")
        summary = run_tests([str(tmp_path)])
        assert summary['total'] == 3
        assert summary['passed'] == 1
        assert summary['failed'] == 1
        assert summary['skipped'] == 1
        assert len(summary['cases']) == 3

    def test_empty_dir(self, tmp_path):
        summary = run_tests([str(tmp_path)])
        assert summary['total'] == 0 and summary['passed'] == 0


class TestPrintReport:
    """print_report 输出。"""

    def test_report_lines(self, capsys):
        summary = {
            'total': 2, 'passed': 1, 'failed': 1, 'skipped': 0,
            'cases': [
                {'name': 'ok', 'status': 'passed', 'stdout': '', 'error': ''},
                {'name': 'bad', 'status': 'failed', 'stdout': 'out',
                 'error': 'AssertionError: nope'},
            ],
        }
        print_report(summary)
        out = capsys.readouterr().out
        assert 'FAILED: bad' in out
        assert '--- stdout ---' in out and 'out' in out
        assert 'AssertionError: nope' in out
        assert '1 passed, 1 failed, 0 skipped / 2 total' in out

    def test_report_all_passed(self, capsys):
        summary = {'total': 1, 'passed': 1, 'failed': 0, 'skipped': 0,
                   'cases': [{'name': 'x', 'status': 'passed', 'stdout': '', 'error': ''}]}
        print_report(summary)
        out = capsys.readouterr().out
        assert 'FAILED' not in out
        assert '1 passed, 0 failed' in out


class TestMain:
    """main 入口。"""

    def test_exit_0_all_pass(self, tmp_path, capsys):
        (tmp_path / "ok.test.md").write_text(
            '```python #!test name=ok\nassert 1\n```\n', encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_exit_1_on_failure(self, tmp_path, capsys):
        (tmp_path / "bad.test.md").write_text(
            '```python #!test name=bad\nassert 0\n```\n', encoding="utf-8")
        assert main([str(tmp_path)]) == 1

    def test_no_paths_defaults_tests(self):
        summary = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'cases': []}
        with patch.object(mdtest_mod, 'run_tests', return_value=summary) as rt:
            rc = main([])
        rt.assert_called_once()
        assert rt.call_args.args[0] == ['tests']
        assert rc == 0

    def test_verbose_flag_passed(self):
        summary = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'cases': []}
        with patch.object(mdtest_mod, 'run_tests', return_value=summary) as rt:
            main(['-v', 'somewhere'])
        assert rt.call_args.kwargs['verbose'] is True

    def test_flags_filtered_from_paths(self):
        summary = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'cases': []}
        with patch.object(mdtest_mod, 'run_tests', return_value=summary) as rt:
            main(['--verbose', 'dir1', 'dir2'])
        assert rt.call_args.args[0] == ['dir1', 'dir2']
