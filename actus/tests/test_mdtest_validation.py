# -*- coding: utf-8 -*-
"""mdtest / pytest_compat 的入口校验（扫第二档最后一对）。

这两个是**内部测试框架**，影响面限于写 mdtest 用例的人，故只做轻量加固：
把裸错换成带参数名的错误。经探测**未发现实质性缺陷**——
`approx(1) == 1.0001` 为 False 与 pytest 默认容差（rel=1e-6）一致，
`_Mark` 不可调用也属本实现的设计差异，均非 bug。
"""
import pytest

from vools.actus import mdtest


@pytest.mark.parametrize("bad", [None, 123, {"a": 1}])
def test_discover_rejects_non_list(bad):
    with pytest.raises(TypeError) as exc:
        mdtest.discover_test_files(bad)
    assert "paths 必须是路径列表" in str(exc.value), exc.value


def test_discover_rejects_string():
    """字符串会被逐字符当成路径。"""
    with pytest.raises(TypeError) as exc:
        mdtest.discover_test_files("abc")
    assert "逐字符" in str(exc.value), exc.value


def test_discover_empty_ok():
    assert mdtest.discover_test_files([]) == []


@pytest.mark.parametrize("bad", [None, 123, []])
def test_extract_cases_rejects_non_path(bad):
    with pytest.raises(TypeError) as exc:
        mdtest.extract_cases(bad)
    assert "md_path 必须是路径" in str(exc.value), exc.value


def test_extract_cases_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        mdtest.extract_cases(str(tmp_path / "nope.md"))


def test_run_case_rejects_non_dict():
    with pytest.raises(TypeError) as exc:
        mdtest.run_case(None)
    assert "case 必须是 dict" in str(exc.value), exc.value


@pytest.mark.parametrize("case,missing", [({}, "name"), ({"name": "t"}, "file")])
def test_run_case_reports_missing_field(case, missing):
    with pytest.raises(KeyError) as exc:
        mdtest.run_case(case)
    assert missing in str(exc.value), exc.value
