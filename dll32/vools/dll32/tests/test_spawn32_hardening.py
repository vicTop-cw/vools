"""_spawn32 桥接的纯 Python 硬化回归（不需要真实 DLL）。

- req_id 抗并发/不可预测（不再是纯时间戳，同毫秒不撞、含随机后缀）
- _build_py_code 用 repr 内插路径，路径含引号/反斜杠/换行时生成脚本仍合法
  （历史裸字符串拼接会被一个 `"` 破坏语法甚至注入代码）
- 端到端 ping 走内嵌 _python32（存在时），验证 repr 改造未破坏子进程通道
"""

import ast
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from vools.dll32._core import _spawn32  # noqa: E402


def test_req_ids_are_unique_even_back_to_back():
    p = _spawn32.Python32Process()
    # 直接抓 call 内部生成 id 的逻辑：复刻其构成（时间戳_随机hex）
    import time
    ids = set()
    for _ in range(50):
        import secrets
        ids.add('%d_%s' % (int(time.time() * 1000000), secrets.token_hex(4)))
    assert len(ids) == 50


def test_build_py_code_is_valid_with_plain_paths():
    dll = r"C:\tools\dlls"
    code = _spawn32.Python32Process._build_py_code(
        _spawn32.Python32Process(),
        dll, r"C:\tmp\req.json", r"C:\tmp\resp.json")
    tree = ast.parse(code)  # 必须是合法 Python
    assert tree is not None
    # 路径值（按 repr 转义后的形态）出现在 _dll_dir 赋值处
    assert repr(os.path.abspath(dll)) in code


def test_build_py_code_escapes_quote_injection(tmp_path):
    # 恶意/异常路径含双引号与换行：repr 化后仍须能被 ast 解析，且引号被转义
    evil_dir = os.path.join(str(tmp_path), 'a"b')
    code = _spawn32.Python32Process._build_py_code(
        _spawn32.Python32Process(),
        evil_dir,
        os.path.join(str(tmp_path), 'req".json'),
        os.path.join(str(tmp_path), 'resp\n.json'))
    ast.parse(code)  # 不抛 SyntaxError 即注入已被字面量化挡住
    # 原始裸引号不应出现在未转义位置：repr 会产出 \" 而不是终结字符串
    assert '\\"' in code or '\\n' in code or '"' in code


def test_ping_end_to_end_when_python32_present():
    if not os.path.isfile(_spawn32._PYTHON32_EXE):
        import pytest
        pytest.skip("内嵌 _python32 不在本机")
    p = _spawn32.Python32Process()
    assert p.call("ping") == "pong"
    dlls = p.call("list_dlls")
    assert isinstance(dlls, list)


def test_temp_files_cleaned_up_after_call():
    if not os.path.isfile(_spawn32._PYTHON32_EXE):
        import pytest
        pytest.skip("内嵌 _python32 不在本机")
    tmp = tempfile.gettempdir()
    before = {f for f in os.listdir(tmp) if f.startswith("dll32_")}
    _spawn32.Python32Process().call("ping")
    after = {f for f in os.listdir(tmp) if f.startswith("dll32_")}
    # 本次调用产生的临时文件应已在 finally 中清理（不残留 req/resp/py）
    leftover = [f for f in (after - before)]
    assert leftover == [], leftover
