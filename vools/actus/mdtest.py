"""vools.actus.mdtest — md 测试运行器（Actus docs/33 §Phase 2）。

测试用 md 书写（*.test.md），每个 `#!test` python 块是一个用例：
经 prelude 自动获得 vools.actus 全量 API 与常用标准库，测试代码零 import。

书写约定：
    ```python #!setup        # 可选：文件级准备（本文件每个用例前执行）
    ```python #!test name=用例名
    assert execute('actus.wordcount', {})['status'] == 'success'
    ```

pytest 兼容（经 vools.actus.pytest_compat）：
    import pytest 可用（raises/approx/skip/mark/fixture/MonkeyPatch）；
    夹具：tmp_path / monkeypatch / capsys 内建 + @pytest.fixture 自定义；
    conftest 三件套 action_repo / write_action / execute_in 与 GOOD_ACTION
    由 mdtest 内建引导自动提供（from conftest import ... 迁移时移除）。

运行：
    python -m vools.actus.mdtest tests/            # 目录或文件，可多个
    python -m vools.actus.mdtest tests/ -v         # 显示用例名
退出码：全部通过 0，存在失败 1。
"""
import io
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List

from vools.bridge.md.parser import parse_md
from vools.bridge.md.runner import _build_prelude_env
from vools.actus import pytest_compat
from vools.actus.pytest_compat import (
    MonkeyPatch, Skipped, reset_fixtures, pytest, call as _compat_call,
    call_method as _compat_call_method,
)

# 与 pytest 兼容的默认发现模式
TEST_FILE_SUFFIX = '.test.md'

# 迁移转义（docs/33 §Phase 2）：py 原码内嵌 setup 块时，
# ``` 会提前终止围栏、行首 #! 会被 md 解析器当指令剥离，
# 故转换器写入哨兵，extract_cases 时还原。
_ESCAPE_PAIRS = (('@FENCE@', '```'), ('@HASHBANG@', '#!'))


def _unescape_code(code: str) -> str:
    for sentinel, real in _ESCAPE_PAIRS:
        code = code.replace(sentinel, real)
    return code

# ═══════════════════════════════════════════════════════
# conftest 内建引导（对齐 Actus tests/conftest.py，逐用例重置）
# ═══════════════════════════════════════════════════════

BOOTSTRAP_SOURCE = '''
@pytest.fixture()
def action_repo(tmp_path):
    """隔离临时动作仓库，返回 (actions_dir, meta_dir)。"""
    actions = tmp_path / 'actions'
    meta = tmp_path / '_meta'
    actions.mkdir()
    meta.mkdir()
    return str(actions), str(meta)


@pytest.fixture()
def write_action(action_repo):
    """向临时仓库写一个动作文件，返回其路径。"""
    actions_dir, _meta = action_repo

    def _write(name: str, content: str) -> str:
        path = os.path.join(actions_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    return _write


@pytest.fixture()
def execute_in(action_repo, tmp_path):
    """返回绑定临时仓库的 execute 快捷函数（artifacts 一并隔离）。"""
    actions_dir, meta_dir = action_repo
    artifacts_dir = str(tmp_path / 'artifacts')

    def _execute(action_id, params=None, **kw):
        import vools.actus as actuscore
        return actuscore.execute(action_id, params or {},
                                 actions_dir=actions_dir, meta_dir=meta_dir,
                                 artifacts_dir=artifacts_dir, **kw)

    return _execute


GOOD_ACTION = \'\'\'#!config
#!entry main

# 测试动作

```json #!cfg
{{
  "id": "{aid}",
  "name": "test",
  "version": "1.0.0",
  "trust": "{trust}",
  "deps": [],
  "entry": "main",
  "description": "pytest 临时动作",
  "author": "pytest"
}}
```

```python #!run tag=main
{code}
```
\'\'\'
'''.replace("\\'", "'")


def _fixture_env() -> Dict[str, Any]:
    """为每个用例构造全新夹具环境。"""
    tmp_root = tempfile.mkdtemp(prefix='mdtest_')
    return {
        'tmp_path': Path(tmp_root),
        'monkeypatch': MonkeyPatch(),
        'tmp_root': tmp_root,
    }


def _cleanup_fixture_env(env: Dict[str, Any]) -> None:
    """用例结束：还原 monkeypatch、恢复 capsys、清注册表与临时目录。"""
    mp = env.get('monkeypatch')
    if mp is not None:
        mp.undo()
    cap = env.get('capsys')
    if cap is not None:
        cap.restore()
    reset_fixtures()
    tmp_root = env.get('tmp_root')
    if tmp_root:
        shutil.rmtree(tmp_root, ignore_errors=True)


# ═══════════════════════════════════════════════════════
# 发现与提取
# ═══════════════════════════════════════════════════════


def discover_test_files(paths: List[str]) -> List[str]:
    """发现测试文件：目录递归找 *.test.md，文件直接收录。"""
    files: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                if any(s in root for s in ('.venv', 'venv', 'node_modules',
                                           '__pycache__', '.pytest_cache')):
                    continue
                for n in sorted(names):
                    if n.endswith(TEST_FILE_SUFFIX):
                        files.append(os.path.join(root, n))
        elif os.path.isfile(p):
            files.append(p)
    return sorted(files)


def extract_cases(md_path: str) -> List[Dict[str, Any]]:
    """提取一个 md 中的全部 #!test 块为用例列表。

    用例结构：{name, code, file, index, skip, setup}
    setup：同文件中在其之前最近的一个 `#!setup` 块（可选），先于用例执行，
    其顶层变量对用例可见 —— 对应 pytest 模块级准备逻辑。
    命名优先级：#!test name=xxx > tag=xxx > <文件名>::块序号
    """
    parsed = parse_md(md_path)
    cases: List[Dict[str, Any]] = []
    base = os.path.splitext(os.path.basename(md_path))[0]
    pending_setup: str = ''
    for block in parsed.blocks:
        dirs = block.directives or {}
        if 'setup' in dirs and 'test' not in dirs:
            pending_setup = block.content
            continue
        if 'test' not in dirs:
            continue
        name = dirs.get('name') or (dirs.get('tag') or None)
        if not name:
            name = f'{base}::block{block.index}'
        cases.append({
            'name': name,
            'code': block.content,
            'file': md_path,
            'index': block.index,
            'skip': 'skip' in dirs,
            'setup': pending_setup,
        })
    return cases


# ═══════════════════════════════════════════════════════
# 执行
# ═══════════════════════════════════════════════════════


def run_case(case: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
    """执行单个用例，返回 {name, status, stdout, error}。

    status: passed | failed | skipped（含 pytest.skip 与 skipif）。
    setup 与用例共享同一 exec_env（globals 即 exec_env），
    setup 定义的函数/类/常量对用例体可见。
    exec 期间 sys.modules['pytest'] 指向 pytest_compat，
    使 `import pytest` 与 `from conftest import ...` 之外的 pytest 用法全部兼容。
    """
    if case.get('skip'):
        return {'name': case['name'], 'status': 'skipped',
                'stdout': '', 'error': ''}

    exec_env: Dict[str, Any] = dict(_build_prelude_env(config or {}))
    exec_env.update(_fixture_env())
    exec_env['__name__'] = '__md_test__'
    exec_env['__file__'] = case['file']
    exec_env['pytest'] = pytest
    exec_env['_call'] = lambda fn: _compat_call(fn, exec_env)
    exec_env['_call_method'] = lambda cls, m: _compat_call_method(cls, m, exec_env)

    # 先注册 conftest 等价夹具（setup 中的同名定义可覆盖）
    reset_fixtures()
    bootstrap = exec(BOOTSTRAP_SOURCE, exec_env)

    stdout_buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    old_pytest_mod = sys.modules.get('pytest')
    sys.modules['pytest'] = pytest
    try:
        sys.stdout = stdout_buf
        sys.stderr = stdout_buf
        setup_code = case.get('setup') or ''
        if setup_code.strip():
            exec(setup_code, exec_env, exec_env)
        exec(case['code'], exec_env, exec_env)
        return {'name': case['name'], 'status': 'passed',
                'stdout': stdout_buf.getvalue(), 'error': ''}
    except Skipped as e:
        return {'name': case['name'], 'status': 'skipped',
                'stdout': stdout_buf.getvalue(),
                'error': str(e) or 'skipped'}
    except Exception as e:
        tb = traceback.format_exc()
        return {'name': case['name'], 'status': 'failed',
                'stdout': stdout_buf.getvalue(),
                'error': f'{type(e).__name__}: {e}\n{tb}'}
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        if old_pytest_mod is not None:
            sys.modules['pytest'] = old_pytest_mod
        else:
            sys.modules.pop('pytest', None)
        _cleanup_fixture_env(exec_env)


def run_tests(paths: List[str], verbose: bool = False) -> Dict[str, Any]:
    """运行全部测试，返回汇总 {total, passed, failed, skipped, cases}。"""
    files = discover_test_files(paths)
    results: List[Dict[str, Any]] = []
    for f in files:
        for case in extract_cases(f):
            r = run_case(case)
            results.append(r)
            mark = {'passed': '.', 'failed': 'F', 'skipped': 's'}[r['status']]
            print(mark, end='', flush=True)
            if verbose:
                print(f"  {r['status']:8s} {r['name']}")
    print()
    summary = {
        'total': len(results),
        'passed': sum(1 for r in results if r['status'] == 'passed'),
        'failed': sum(1 for r in results if r['status'] == 'failed'),
        'skipped': sum(1 for r in results if r['status'] == 'skipped'),
        'cases': results,
    }
    return summary


def print_report(summary: Dict[str, Any]) -> None:
    """打印失败详情与汇总行。"""
    for r in summary['cases']:
        if r['status'] == 'failed':
            print(f"FAILED: {r['name']}")
            if r['stdout']:
                print('--- stdout ---')
                print(r['stdout'].rstrip())
            print('--- error ---')
            print(r['error'].rstrip())
            print()
    print(f"mdtest: {summary['passed']} passed, {summary['failed']} failed, "
          f"{summary['skipped']} skipped / {summary['total']} total")


def main(argv: List[str] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = '-v' in argv or '--verbose' in argv
    paths = [a for a in argv if not a.startswith('-')]
    if not paths:
        paths = ['tests']
    summary = run_tests(paths, verbose=verbose)
    print_report(summary)
    return 0 if summary['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
