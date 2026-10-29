# -*- coding: utf-8 -*-
"""`runtimes.py` 契约测试（第 33 轮：运行时注册表 + 7 个后端，覆盖 44% → 目标 ≥65%）。

覆盖重点：
  1. 注册表：别名解析 / 未注册 / 未安装 / 可用列表 / 单例入口；
  2. PythonRuntime：进程内 exec 的 **异常/SystemExit/超时契约**、env/argv/stdin 注入与还原；
  3. 子进程类后端（shell/node/go/rust/ruby/php）：用 `run_cmd_safe` 替身覆盖
     **编译失败 / 编译成功 / 运行超时(-9→124) / 抛异常** 四条路径，不依赖本机装了什么；
  4. shell 类型启发式。

隔离：不写真实仓库；临时文件由各后端自己建在系统临时目录并在 finally 清理。
每条 docstring 写「退步了会怎样」。
"""
import os
import sys

import pytest

from vools.actus import runtimes as R


class FakeProc:
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def fake_run_cmd(monkeypatch):
    """把 `runtimes.run_cmd_safe` 换成可编程替身：记录调用、按队列返回结果。"""
    calls = []
    queue = []

    def fake(cmd, **kw):
        calls.append({'cmd': cmd, 'kw': kw})
        if queue:
            out = queue.pop(0)
            if isinstance(out, Exception):
                raise out
            return out
        return FakeProc()

    monkeypatch.setattr(R, 'run_cmd_safe', fake)
    fake.calls = calls
    fake.queue = queue
    return fake


# ═══════════════════════════════════════════════════════════════════
# ① 注册表
# ═══════════════════════════════════════════════════════════════════


def test_registry_registers_all_builtin_backends():
    """退步了会怎样：内置后端漏注册（或 `_register_defaults` 静默吞掉构造异常）→
    该语言在 CLI/MCP 里表现为"不支持的语言"，而真正原因无从发现。
    """
    reg = R.RuntimeRegistry()
    names = {rt.name for rt in reg._runtimes.values()}
    assert {'python', 'shell', 'node', 'go', 'rust', 'ruby', 'php'} <= names
    # 别名必须指向同一个后端实例（不是新建一份）
    assert reg.get('py') is reg.get('python')
    assert reg.get('bash') is reg.get('shell')
    assert reg.get('js') is reg.get('node')


def test_registry_unknown_language_is_none():
    """退步了会怎样：未知语言返回默认后端（静默回退到某个 runtime）→
    本该拒绝的代码被别的解释器执行，产生难以解释的错误。
    """
    reg = R.RuntimeRegistry()
    assert reg.get('no-such-lang') is None
    assert reg.is_available('no-such-lang') is False


def test_registry_get_rejects_non_string_language():
    """退步了会怎样（R1）：`get(None)` / `get(123)` 走回 `.lower()` → 裸
    `AttributeError`，穿透到 CLI/MCP 变成"内部错误"；修复后与"不支持的语言"
    同一出口（`RuntimeError`），调用方可按语言错误分流。
    """
    reg = R.RuntimeRegistry()
    for bad in (None, 123, 1.5, ['py']):
        with pytest.raises(RuntimeError) as exc:
            reg.get(bad)
        assert '不支持的语言' in str(exc.value)
        assert not isinstance(exc.value, AttributeError)


def test_registry_register_failure_is_logged_not_swallowed(monkeypatch, caplog):
    """退步了会怎样（R3）：某个后端构造抛异常被 `except: pass` 吞掉 → 该语言只表现为
    "不支持的语言"，用户看不到真正原因。修复后必须留 warning，且其它后端照常注册。
    """
    class BrokenBackend:
        def __init__(self):
            raise RuntimeError('模拟构造失败')

        name = 'broken'
        aliases = []

    monkeypatch.setattr(R, 'PythonRuntime', BrokenBackend)
    with caplog.at_level('WARNING', logger='vools.actus.runtimes'):
        reg = R.RuntimeRegistry()

    assert any('运行时注册失败' in rec.getMessage() for rec in caplog.records), \
        [r.getMessage() for r in caplog.records]
    # 其它后端不受影响（shell/node/... 仍注册）
    assert reg.get('shell') is not None
    assert reg.get('py') is None, "被替换成 BrokenBackend 后 python 不应可用"


def test_registry_execute_raises_for_unknown_and_unavailable(monkeypatch):
    """退步了会怎样：不支持/未安装时静默返回空失败（`('', '', 1)`）而不是明确报错 →
    调用方分不清"代码跑失败"和"环境没有这个运行时"。
    """
    reg = R.RuntimeRegistry()
    with pytest.raises(RuntimeError) as exc:
        reg.execute('no-such-lang', 'x', {})
    assert '不支持的语言' in str(exc.value)

    class Unavailable(R.RuntimeBackend):
        name = 'unavail'
        aliases = ['uv']

        def is_available(self):
            return False

        def execute(self, code, context):
            raise AssertionError('不可用时不得进入 execute')

    reg.register(Unavailable())
    with pytest.raises(RuntimeError) as exc2:
        reg.execute('uv', 'x', {})
    assert '运行时不可用' in str(exc2.value)


def test_registry_available_languages_dedupes_by_name(monkeypatch):
    """退步了会怎样：按别名逐条列出（同一运行时出现多次）→ CLI 的 `--lang` 帮助、
    MCP 的可用语言清单里出现重复项。
    """
    reg = R.RuntimeRegistry()

    class Avail(R.RuntimeBackend):
        name = 'avail'
        aliases = ['av', 'avail2']

        def is_available(self):
            return True

        def execute(self, code, context):
            return ('', '', 0)

    reg.register(Avail())
    langs = reg.available_languages()
    assert langs.count('avail') == 1
    assert 'av' not in langs and 'avail2' not in langs


def test_registry_module_singleton_and_wrappers(monkeypatch):
    """退步了会怎样：`execute_block`/`get_available_runtimes` 不走单例（每次新建注册表）
    → 注册的自定义运行时丢失、可用性探测重复执行。
    """
    sentinel = R.RuntimeRegistry()
    monkeypatch.setattr(R, '_registry', sentinel, raising=False)
    assert R._get_registry() is sentinel
    assert R.get_available_runtimes() == sentinel.available_languages()

    calls = {}

    def fake_execute(self, language, code, context):
        calls['args'] = (language, code, context)
        return ('out', '', 0)

    monkeypatch.setattr(R.RuntimeRegistry, 'execute', fake_execute)
    assert R.execute_block('python', 'print(1)', {'env': {}}) == ('out', '', 0)
    assert calls['args'][0] == 'python'


# ═══════════════════════════════════════════════════════════════════
# ② PythonRuntime（进程内 exec）
# ═══════════════════════════════════════════════════════════════════


def test_python_runtime_normal_and_error_paths():
    """退步了会怎样：用户代码异常/SystemExit 的处理口径变化 → 上层把用户错误
    当成功（假绿），或把正常退出当失败。
    """
    rt = R.PythonRuntime()
    assert rt.is_available() is True

    out, err, rc = rt.execute("print('hi')", {})
    assert (out, err, rc) == ('hi\n', '', 0)

    out, err, rc = rt.execute("import sys; sys.exit(3)", {})
    assert rc == 3 and out == ''

    out, err, rc = rt.execute("1/0", {})
    assert rc == 1 and 'ZeroDivisionError' in err


def test_python_runtime_exit_code_is_always_int():
    """退步了会怎样（R2）：`sys.exit('bad')` 的字符串码被原样当 exit_code 返回
    （违反 Tuple[str,str,int] 契约）→ 上层 `exit_code == 124` / `!= 0` 的整型
    判定失效；且退出码文本（"3"）混进 stderr，污染用户看到的错误信息。
    """
    rt = R.PythonRuntime()

    out, err, rc = rt.execute("import sys; sys.exit('bad')", {})
    assert isinstance(rc, int), "exit_code 必须是 int，得到 %r" % (rc,)
    assert rc == 1 and err == ''

    out, err, rc = rt.execute("import sys; sys.exit(3)", {})
    assert (rc, err) == (3, ''), "退出码不得写进 stderr"

    out, err, rc = rt.execute("import sys; sys.exit('7')", {})
    assert rc == 7 and isinstance(rc, int)

    out, err, rc = rt.execute("import sys; sys.exit(None)", {})
    assert rc == 0


def test_python_runtime_injects_and_restores_env_argv_stdin():
    """退步了会怎样：注入的 env/argv/stdin 不还原（或还原不全）→ 宿主进程被污染：
    后续命令带着上一个动作的环境变量/CWD/argv 跑（我们修过多起同类问题）。
    """
    rt = R.PythonRuntime()
    before_env = os.environ.get('ACTUS_RT_PROBE')
    before_argv = list(sys.argv)
    before_stdout = sys.stdout

    code = ("import os, sys\n"
            "data = sys.stdin.read() if not sys.stdin.isatty() else ''\n"
            "print(os.environ.get('ACTUS_RT_PROBE') + '|' + ','.join(sys.argv[1:]) + '|' + data)\n")
    out, err, rc = rt.execute(code, {'env': {'ACTUS_RT_PROBE': 'V1'},
                                     'args': ['a', 'b'], 'stdin': 'IN'})
    assert rc == 0, err
    assert out.strip() == 'V1|a,b|IN'

    assert os.environ.get('ACTUS_RT_PROBE') == before_env
    assert sys.argv == before_argv
    assert sys.stdout is before_stdout


def test_python_runtime_accepts_list_args_and_string_args():
    """退步了会怎样：args 支持两种形态（str 按空白切分 / list 原样）之一失效 →
    CLI 传参形态与动作内看到的 argv 不一致。
    """
    rt = R.PythonRuntime()
    out, _, rc = rt.execute("import sys; print(','.join(sys.argv[1:]))", {'args': 'x y'})
    assert (rc, out.strip()) == (0, 'x,y')
    out2, _, rc2 = rt.execute("import sys; print(','.join(sys.argv[1:]))", {'args': ['p', 'q']})
    assert (rc2, out2.strip()) == (0, 'p,q')


# ═══════════════════════════════════════════════════════════════════
# ③ 子进程类后端（用 run_cmd_safe 替身，不依赖本机工具链）
# ═══════════════════════════════════════════════════════════════════


def test_shell_runtime_success_timeout_and_exception(fake_run_cmd):
    """退步了会怎样：子进程后端的三种结局（成功/超时/启动异常）映射错 →
    超时被当普通失败（上层不会重试/不会标 timeout），或异常被当成功。
    """
    rt = R.ShellRuntime()
    assert rt.is_available() is True

    fake_run_cmd.queue.append(FakeProc('ok\n', '', 0))
    out, err, rc = rt.execute('echo ok', {})
    assert (out, rc) == ('ok\n', 0)

    fake_run_cmd.queue.append(FakeProc('', '', -9))          # 超时约定：rc=-9
    out, err, rc = rt.execute('sleep 999', {'timeout': 1})
    assert rc == 124 and '超时' in err

    fake_run_cmd.queue.append(RuntimeError('spawn 失败'))
    out, err, rc = rt.execute('echo x', {})
    assert rc == 1 and 'spawn 失败' in err


def test_shell_detect_heuristics():
    """退步了会怎样：shell 类型判定反了（PowerShell 代码交给 bash / bash 代码交给
    PowerShell）→ 合法脚本只因平台后缀就被判语法错误。
    """
    assert R.ShellRuntime._detect_shell('Write-Host hi') == 'powershell'
    assert R.ShellRuntime._detect_shell('$env:PATH') == 'powershell'
    assert R.ShellRuntime._detect_shell('@echo off') == 'cmd'
    assert R.ShellRuntime._detect_shell('echo hi') == 'bash'


def test_node_runtime_compile_free_and_timeout(fake_run_cmd, tmp_path):
    """退步了会怎样：node 临时文件不清理 / 超时映射错 → 临时目录堆积、超时被误判。
    """
    rt = R.NodeRuntime()
    fake_run_cmd.queue.append(FakeProc('hello\n', '', 0))
    out, err, rc = rt.execute("console.log('hello')", {'workdir': str(tmp_path)})
    assert (out, rc) == ('hello\n', 0)
    tmp_js = fake_run_cmd.calls[0]['cmd'][1]
    assert tmp_js.endswith('.js')
    assert not os.path.exists(tmp_js), "node 临时文件未清理"

    fake_run_cmd.queue.append(FakeProc('', '', -9))
    out, err, rc = rt.execute('while(1){}', {'timeout': 1})
    assert rc == 124


def test_go_and_rust_compile_failure_and_success(fake_run_cmd):
    """退步了会怎样：编译失败被当成运行输出/成功（或编译错误信息丢失）→
    用户看到的失败原因是一堆运行期噪音而不是编译错误。
    """
    go = R.GoRuntime()
    fake_run_cmd.queue.append(FakeProc('', 'syntax error', 2))
    out, err, rc = go.execute('package main', {})
    assert rc == 2 and '编译失败' in err and 'syntax error' in err

    fake_run_cmd.queue.append(FakeProc('', '', 0))          # build ok
    fake_run_cmd.queue.append(FakeProc('go-out', '', 0))    # run ok
    out, err, rc = go.execute('package main', {})
    assert (out, rc) == ('go-out', 0)

    rust = R.RustRuntime()
    fake_run_cmd.queue.append(FakeProc('', 'rustc error', 1))
    out, err, rc = rust.execute('fn main(){}', {})
    assert rc == 1 and '编译失败' in err

    fake_run_cmd.queue.append(FakeProc('', '', 0))
    fake_run_cmd.queue.append(FakeProc('rust-out', '', 0))
    out, err, rc = rust.execute('fn main(){}', {})
    assert (out, rc) == ('rust-out', 0)


def test_ruby_and_php_runtime_paths(fake_run_cmd):
    """退步了会怎样：脚本类后端的临时文件/超时/异常路径失效 → 与 node 同族问题。
    """
    rb = R.RubyRuntime()
    fake_run_cmd.queue.append(FakeProc('rb-out', '', 0))
    out, err, rc = rb.execute("puts 'x'", {})
    assert (out, rc) == ('rb-out', 0)
    tmp = fake_run_cmd.calls[0]['cmd'][1]
    assert tmp.endswith('.rb') and not os.path.exists(tmp)

    php = R.PHPRuntime()
    fake_run_cmd.queue.append(FakeProc('', '', -9))
    out, err, rc = php.execute('<?php echo 1;', {'timeout': 1})
    assert rc == 124


def test_availability_probes_use_which(monkeypatch):
    """退步了会怎样：可用性探测不再走 `shutil.which`（或恒真/恒假）→
    明明没装的运行时被报"可用"（执行时才炸），或装了的被报"不可用"。
    """
    monkeypatch.setattr(R.shutil, 'which', lambda name: None)
    for cls in (R.NodeRuntime, R.GoRuntime, R.RubyRuntime, R.PHPRuntime):
        assert cls().is_available() is False, cls.__name__

    monkeypatch.setattr(R.shutil, 'which', lambda name: '/fake/' + name)
    for cls in (R.NodeRuntime, R.GoRuntime, R.RubyRuntime, R.PHPRuntime):
        assert cls().is_available() is True, cls.__name__


def test_rust_availability_probes_rustc(monkeypatch):
    """退步了会怎样：rust 只看 `which rustc` 而不真的探一次版本 → 装了 rustup 但
    没有默认 toolchain 的机器上会报"可用"，运行必挂。
    """
    monkeypatch.setattr(R.shutil, 'which', lambda name: '/fake/rustc')
    monkeypatch.setattr(R, 'run_cmd_safe', lambda *a, **k: FakeProc('rustc 1.0', '', 0))
    assert R.RustRuntime().is_available() is True

    monkeypatch.setattr(R, 'run_cmd_safe', lambda *a, **k: FakeProc('', 'no toolchain', 1))
    assert R.RustRuntime().is_available() is False
