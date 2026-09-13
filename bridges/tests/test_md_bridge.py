"""vools.bridge.md 测试：解析、指令、配置、依赖、清单、产物、执行"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, r'E:\IDEProjects\AI\vools\bridges')

from vools.bridge.md.parser import parse_md, FileDirectives, CodeBlock, ParsedMD
from vools.bridge.md.directives import (
    FILE_DIRECTIVE_KEYS, BLOCK_DIRECTIVE_KEYS,
    parse_block_directives, validate_directives,
)
from vools.bridge.md.deps import parse_toml, check_deps, DepsReport
from vools.bridge.md.manifest import (
    write_manifest, read_manifest,
    minimal_yaml_parse, minimal_yaml_dump,
)
from vools.bridge.md.artifacts import (
    ensure_build_dir, compute_artifact_hash,
    is_artifact_stale, clean_build, register_artifact,
)
from vools.bridge.md.errors import (
    MDBridgeError, MDParseError, MDDirectiveError,
    MDExecutionError, MDImportError,
)
from vools.bridge.md.logger import get_logger
from vools.bridge.md.runner import (
    run_md, run_block, run_multiple_md, resolve_imports,
    scan_library, build_library_manifest, load_library_manifest, run_library,
)


# ═══════════════════════════════════════════════════════
# parser
# ═══════════════════════════════════════════════════════

def test_parse_basic():
    md = "#!config config.lua\n#!deps deps.toml\n\n```python #!run\nprint('hello')\n```\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(md)
        path = f.name
    parsed = parse_md(path)
    assert parsed.file_directives.config == 'config.lua'
    assert parsed.file_directives.deps == 'deps.toml'
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].language == 'python'
    assert 'run' in parsed.blocks[0].directives
    os.unlink(path)
    print('OK: parse basic')


def test_parse_file_directives():
    md = "#!build-dir custom\n#!entry main\n#!only main,test\n\n```python\nx = 1\n```\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(md)
        path = f.name
    parsed = parse_md(path)
    assert parsed.file_directives.build_dir == 'custom'
    assert parsed.file_directives.entry == 'main'
    assert 'main' in parsed.file_directives.only
    os.unlink(path)
    print('OK: parse file directives')


def test_parse_multiple_blocks():
    md = "#!entry main\n\n```python #!run tag=main\nprint(1)\n```\n\n```shell #!skip\necho hi\n```\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(md)
        path = f.name
    parsed = parse_md(path)
    assert len(parsed.blocks) == 2
    assert parsed.blocks[0].tag == ['main']
    assert 'skip' in parsed.blocks[1].directives
    os.unlink(path)
    print('OK: parse multiple blocks')


def test_parse_hash():
    md = "#!entry main\n\n```python #!run\nx = 1\n```\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(md)
        path = f.name
    parsed = parse_md(path)
    assert parsed.md_hash
    assert len(parsed.block_hashes) == 1
    assert parsed.block_hashes[0]
    os.unlink(path)
    print('OK: parse hash')


# ═══════════════════════════════════════════════════════
# directives
# ═══════════════════════════════════════════════════════

def test_parse_block_directives():
    d = parse_block_directives('run export=main tag=main')
    assert d['run'] == ''
    assert d['export'] == 'main'
    assert d['tag'] == 'main'
    print('OK: parse block directives')


def test_parse_block_directives_empty():
    d = parse_block_directives('')
    assert 'run' in d  # 默认 run
    print('OK: parse block directives empty')


def test_validate_directives_ok():
    errors = validate_directives({'run': '', 'tag': 'main'}, 'python')
    assert len(errors) == 0
    print('OK: validate directives ok')


def test_validate_directives_unknown():
    errors = validate_directives({'unknown': 'val'}, 'python')
    assert len(errors) > 0
    print('OK: validate directives unknown')


def test_validate_directives_mutex():
    errors = validate_directives({'run': '', 'skip': ''}, 'python')
    assert any('互斥' in e for e in errors)
    print('OK: validate directives mutex')


# ═══════════════════════════════════════════════════════
# deps
# ═══════════════════════════════════════════════════════

def test_parse_toml_basic():
    toml = '[runtime]\npython = ">=3.6"\nlua = ">=5.1"\n'
    result = parse_toml(toml)
    assert 'runtime' in result
    assert result['runtime']['python'] == '>=3.6'
    print('OK: parse toml basic')


def test_parse_toml_array():
    toml = 'key = ["a", "b"]\n'
    result = parse_toml(toml)
    value = result.get('_global', {}).get('key') if '_global' in result else result.get('key')
    assert isinstance(value, list)
    print('OK: parse toml array')


def test_check_deps_no_file():
    report = check_deps(None, '/tmp')
    assert isinstance(report, DepsReport)
    print('OK: check deps no file')


# ═══════════════════════════════════════════════════════
# manifest
# ═══════════════════════════════════════════════════════

def test_yaml_parse():
    text = 'name: test\nvalue: 123\nitems:\n  - a\n  - b\n'
    result = minimal_yaml_parse(text)
    assert result['name'] == 'test'
    assert result['value'] == 123
    print('OK: yaml parse')


def test_yaml_dump():
    data = {'name': 'test', 'value': 123}
    text = minimal_yaml_dump(data)
    assert 'name: test' in text
    assert 'value: 123' in text
    print('OK: yaml dump')


def test_manifest_write_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        data = {'md_path': 'test.md', 'md_hash': 'abc', 'blocks': []}
        path = write_manifest(tmpdir, data)
        assert os.path.exists(path)
        result = read_manifest(tmpdir)
        assert result is not None
        assert result['md_hash'] == 'abc'
        print('OK: manifest write read')


def test_manifest_read_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = read_manifest(tmpdir)
        assert result is None
        print('OK: manifest read none')


# ═══════════════════════════════════════════════════════
# artifacts
# ═══════════════════════════════════════════════════════

def test_ensure_build_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        bd = os.path.join(tmpdir, '.mdbuild')
        ensure_build_dir(bd)
        assert os.path.exists(os.path.join(bd, 'artifacts'))
        assert os.path.exists(os.path.join(bd, 'sources'))
        assert os.path.exists(os.path.join(bd, 'tmp'))
        print('OK: ensure build dir')


def test_compute_artifact_hash():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write('hello')
        path = f.name
    h = compute_artifact_hash(path)
    assert h == '5d41402abc4b2a76b9719d911017c592'
    os.unlink(path)
    print('OK: compute artifact hash')


def test_register_artifact():
    table = {}
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write('hello')
        path = f.name
    register_artifact(table, 'test', path, 0, 'main')
    assert 'test' in table
    assert table['test']['path'] == path
    os.unlink(path)
    print('OK: register artifact')


def test_clean_build():
    with tempfile.TemporaryDirectory() as tmpdir:
        bd = os.path.join(tmpdir, '.mdbuild')
        ensure_build_dir(bd)
        clean_build(bd)
        assert not os.path.exists(bd)
        print('OK: clean build')


def test_is_artifact_stale():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert is_artifact_stale(tmpdir, 0, 'abc') == True
        print('OK: is artifact stale (no manifest)')


# ═══════════════════════════════════════════════════════
# runner (base)
# ═══════════════════════════════════════════════════════

def test_run_md_basic():
    md = "#!entry main\n\n```python #!run tag=main\nprint('hello from md')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        assert 'hello from md' in result['blocks'][0]['stdout']
        print('OK: run md basic')


def test_run_md_skip():
    md = "#!entry main\n\n```python #!skip tag=skip\nprint('skipped')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['skip'])
        assert result['blocks'][0]['status'] == 'skipped'
        print('OK: run md skip')


def test_run_md_only_code():
    md = "#!entry main\n\n```python #!only-code tag=code\nprint('code')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['code'])
        assert result['blocks'][0]['status'] == 'ok'
        print('OK: run md only-code')


def test_run_md_multiple():
    md = """#!entry main

```python #!run tag=main
print('block 1')
```

```python #!run tag=test
print('block 2')
```

```python #!skip
print('skipped')
```
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert len(result['blocks']) >= 1
        print('OK: run md multiple')


def test_run_md_export_import():
    md = """#!entry main

```python #!run export=data tag=main
print("data_content")
```

```python #!run import=data tag=test
import os
print(os.environ.get('MD_IMPORT_data', 'not found'))
```
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main', 'test'])
        assert 'data' in result['artifacts_table']
        print('OK: run md export import')


# ═══════════════════════════════════════════════════════
# runner (M2)
# ═══════════════════════════════════════════════════════

def test_run_md_workdir():
    md = "#!entry main\n\n```python #!run workdir=. tag=main\nimport os\nprint(os.getcwd())\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        assert result['blocks'][0]['workdir'] is not None
        print('OK: run md workdir')


def test_run_md_args():
    md = "#!entry main\n\n```python #!run args=hello tag=main\nx = 1\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        assert result['blocks'][0]['args'] == 'hello'
        print('OK: run md args')


def test_run_md_env():
    md = """#!entry main

```python #!run env=MY_VAR=hello tag=main
import os
print(os.environ.get('MY_VAR'))
```
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        print('OK: run md env')


def test_run_md_timeout():
    md = """#!entry main

```python #!run timeout=5 tag=main
print('fast')
```
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        assert result['blocks'][0]['timeout'] == 5
        print('OK: run md timeout')


def test_run_md_output():
    md = "#!entry main\n\n```python #!run output=result.txt tag=main\nprint('output_data')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        assert result['blocks'][0]['output_file'] is not None
        print('OK: run md output')


def test_run_md_incremental():
    md = "#!entry main\n\n```python #!run tag=main\nprint('incremental')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result1 = run_md(md_path, only=['main'])
        assert result1['blocks'][0]['status'] == 'ok'
        result2 = run_md(md_path, only=['main'])
        assert result2['blocks'][0]['status'] == 'skipped'
        result3 = run_md(md_path, only=['main'], force=True)
        assert result3['blocks'][0]['status'] == 'ok'
        print('OK: run md incremental')


def test_run_md_stdin():
    md = """#!entry main

```python #!run stdin=input.txt tag=main
import sys
data = sys.stdin.read() if hasattr(sys.stdin, 'read') else ''
print(f'got: {data}')
```
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert result['blocks'][0]['status'] == 'ok'
        print('OK: run md stdin')


# ═══════════════════════════════════════════════════════
# CLI (M2)
# ═══════════════════════════════════════════════════════

def test_cli_check():
    import subprocess
    md = "#!entry main\n\n```python #!run tag=main\nprint(1)\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = subprocess.run(
            [sys.executable, '-m', 'vools.bridge.md', 'check', md_path],
            capture_output=True, text=True, cwd=r'E:\IDEProjects\AI\vools\bridges',
        )
        assert result.returncode == 0
        assert 'Dependency Check' in result.stdout
        print('OK: cli check')


def test_cli_info():
    import subprocess
    md = "#!entry main\n\n```python #!run tag=main\nprint(1)\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = subprocess.run(
            [sys.executable, '-m', 'vools.bridge.md', 'info', md_path],
            capture_output=True, text=True, cwd=r'E:\IDEProjects\AI\vools\bridges',
        )
        assert result.returncode == 0
        assert 'File:' in result.stdout
        assert 'Blocks' in result.stdout
        print('OK: cli info')


def test_cli_clean():
    import subprocess
    md = "#!entry main\n\n```python #!run tag=main\nprint(1)\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = subprocess.run(
            [sys.executable, '-m', 'vools.bridge.md', 'clean', md_path],
            capture_output=True, text=True, cwd=r'E:\IDEProjects\AI\vools\bridges',
        )
        assert result.returncode == 0
        assert 'Cleaned' in result.stdout
        print('OK: cli clean')


# ═══════════════════════════════════════════════════════
# directive validation (M2)
# ═══════════════════════════════════════════════════════

def test_validate_timeout():
    errors = validate_directives({'run': '', 'timeout': 'abc'}, 'python')
    assert any('timeout' in e for e in errors)
    print('OK: validate timeout')


def test_validate_export_import_mutex():
    errors = validate_directives({'run': '', 'export': 'a', 'import': 'b'}, 'python')
    assert any('export' in e and 'import' in e for e in errors)
    print('OK: validate export import mutex')


# ═══════════════════════════════════════════════════════
# M3: multi-file import
# ═══════════════════════════════════════════════════════

def test_run_md_import():
    md_main = "#!entry main\n\n```python #!run tag=main\nprint('main block')\n```\n\n```python #!run import=utils.md tag=main\nimport sys\nprint('imported')\n```\n"
    md_utils = "#!entry utils\n\n```python #!run tag=utils\nprint('utils block')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        main_path = os.path.join(tmpdir, 'main.md')
        utils_path = os.path.join(tmpdir, 'utils.md')
        with open(main_path, 'w', encoding='utf-8') as f:
            f.write(md_main)
        with open(utils_path, 'w', encoding='utf-8') as f:
            f.write(md_utils)
        result = run_md(main_path, only=['main'])
        assert len(result['blocks']) >= 1
        assert any(b['status'] == 'ok' for b in result['blocks'])
        print('OK: run md import')


def test_run_md_cross_file_artifacts():
    md_a = "#!entry main\n\n```python #!run export=data tag=main\nprint('data_from_a')\n```\n"
    md_b = "#!entry main\n\n```python #!run import=data tag=main\nprint('got data')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_a_path = os.path.join(tmpdir, 'a.md')
        md_b_path = os.path.join(tmpdir, 'b.md')
        with open(md_a_path, 'w', encoding='utf-8') as f:
            f.write(md_a)
        with open(md_b_path, 'w', encoding='utf-8') as f:
            f.write(md_b)
        result_a = run_md(md_a_path, only=['main'])
        assert 'data' in result_a['artifacts_table']
        result_b = run_md(md_b_path, only=['main'])
        assert len(result_b['blocks']) >= 1
        print('OK: run md cross file artifacts')


def test_run_multiple_md():
    md_1 = "#!entry main\n\n```python #!run tag=main\nprint('file 1')\n```\n"
    md_2 = "#!entry main\n\n```python #!run tag=main\nprint('file 2')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_1_path = os.path.join(tmpdir, '1.md')
        md_2_path = os.path.join(tmpdir, '2.md')
        with open(md_1_path, 'w', encoding='utf-8') as f:
            f.write(md_1)
        with open(md_2_path, 'w', encoding='utf-8') as f:
            f.write(md_2)
        result = run_multiple_md([md_1_path, md_2_path], only=['main'])
        assert len(result['results']) == 2
        assert md_1_path in result['results']
        assert md_2_path in result['results']
        print('OK: run multiple md')


def test_resolve_imports():
    md_main = "#!entry main\n\n```python #!run tag=main\nprint('main')\n```\n\n```python #!run import=utils.md tag=main\n```\n"
    md_utils = "#!entry utils\n\n```python #!run tag=utils\nprint('utils')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        main_path = os.path.join(tmpdir, 'main.md')
        utils_path = os.path.join(tmpdir, 'utils.md')
        with open(main_path, 'w', encoding='utf-8') as f:
            f.write(md_main)
        with open(utils_path, 'w', encoding='utf-8') as f:
            f.write(md_utils)
        parsed = parse_md(main_path)
        blocks = resolve_imports(parsed, tmpdir, os.path.join(tmpdir, '.mdbuild'))
        assert len(blocks) >= 2
        print('OK: resolve imports')


# ═══════════════════════════════════════════════════════
# M4: library-level
# ═══════════════════════════════════════════════════════

def test_scan_library():
    """扫描目录返回所有 .md 文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建几个 .md 文件
        for name in ['a.md', 'b.md', 'c.md']:
            with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as f:
                f.write(f'#!entry main\n\n```python #!run tag=main\nprint("{name}")\n```\n')
        md_files = scan_library(tmpdir)
        assert len(md_files) == 3
        print('OK: scan library')


def test_build_library_manifest():
    """构建库级 manifest.yaml"""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ['a.md', 'b.md']:
            with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as f:
                f.write(f'#!entry main\n\n```python #!run tag=main\nprint("{name}")\n```\n')
        manifest = build_library_manifest(tmpdir)
        assert manifest['total'] == 2
        assert len(manifest['md_files']) == 2
        print('OK: build library manifest')


def test_load_library_manifest():
    """加载库级 manifest.yaml"""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ['a.md', 'b.md']:
            with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as f:
                f.write(f'#!entry main\n\n```python #!run tag=main\nprint("{name}")\n```\n')
        build_library_manifest(tmpdir)
        manifest = load_library_manifest(tmpdir)
        assert manifest is not None
        assert manifest['total'] == 2
        print('OK: load library manifest')


def test_run_library():
    """执行整个库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ['a.md', 'b.md']:
            with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as f:
                f.write(f'#!entry main\n\n```python #!run tag=main\nprint("{name}")\n```\n')
        result = run_library(tmpdir, only=['main'])
        assert len(result['results']) == 2
        print('OK: run library')


# ═══════════════════════════════════════════════════════
# M5: 高级调试与性能分析
# ═══════════════════════════════════════════════════════

def test_run_md_breakpoint():
    """断点调试"""
    md = "#!entry main\n\n```python #!run breakpoint tag=main\nprint('paused')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'], debug=True)
        assert result['blocks'][0]['status'] == 'paused'
        assert result['blocks'][0]['breakpoint'] is True
        print('OK: run md breakpoint')


def test_run_md_profiling():
    """性能分析"""
    md = "#!entry main\n\n```python #!run tag=main\nprint('profile')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'], profile=True)
        assert result['blocks'][0]['status'] == 'ok'
        print('OK: run md profiling')


def test_run_md_parallel():
    """并行执行"""
    md = """#!entry main

```python #!run tag=main
print('block 1')
```

```python #!run tag=main
print('block 2')
```

```python #!run tag=main
print('block 3')
```
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'], parallel=True)
        assert len(result['blocks']) >= 1
        assert all(b['parallel'] is True for b in result['blocks'])
        print('OK: run md parallel')


def test_run_md_cache_optimization():
    """智能缓存优化"""
    md = "#!entry main\n\n```python #!run tag=main\nprint('cached')\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)

        # 第一次运行
        result1 = run_md(md_path, only=['main'])
        assert result1['blocks'][0]['status'] == 'ok'

        # 第二次运行（应命中缓存）
        result2 = run_md(md_path, only=['main'])
        assert result2['blocks'][0]['status'] == 'skipped'
        assert result2['blocks'][0]['cache_hit'] is True

        print('OK: run md cache optimization')


# ═══════════════════════════════════════════════════════
# M7: edge cases & error handling
# ═══════════════════════════════════════════════════════

def test_error_base_class():
    """MDBridgeError 基础异常"""
    err = MDExecutionError("test error", md_path="test.md", block_index=0)
    assert "test error" in str(err)
    assert "test.md" in str(err)
    assert "block: 0" in str(err)
    print('OK: error base class')


def test_error_import_missing():
    """导入不存在的文件"""
    md = "#!entry main\n\n```python #!run tag=main\nprint('main')\n```\n\n```python #!run import=nonexistent.md tag=main\n```\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, 'test.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
        result = run_md(md_path, only=['main'])
        assert len(result['blocks']) >= 1
        print('OK: error import missing')


def test_error_directive_validation():
    """指令校验错误"""
    errors = validate_directives({'unknown_directive': 'val'}, 'python')
    assert len(errors) > 0
    assert any('未知指令' in e for e in errors)
    print('OK: error directive validation')


def test_logger_module():
    """日志系统"""
    logger = get_logger()
    assert logger is not None
    logger.debug('debug message')
    logger.info('info message')
    print('OK: logger module')


def test_parse_empty_md():
    """解析空 md 文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write('')
        path = f.name
    parsed = parse_md(path)
    assert parsed.md_hash is not None
    assert len(parsed.blocks) == 0
    os.unlink(path)
    print('OK: parse empty md')


def test_parse_no_code_blocks():
    """解析无代码块的 md"""
    md = "# Title\n\nSome text without code blocks.\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(md)
        path = f.name
    parsed = parse_md(path)
    assert len(parsed.blocks) == 0
    os.unlink(path)
    print('OK: parse no code blocks')


if __name__ == '__main__':
    test_parse_basic()
    test_parse_file_directives()
    test_parse_multiple_blocks()
    test_parse_hash()
    test_parse_block_directives()
    test_parse_block_directives_empty()
    test_validate_directives_ok()
    test_validate_directives_unknown()
    test_validate_directives_mutex()
    test_parse_toml_basic()
    test_parse_toml_array()
    test_check_deps_no_file()
    test_yaml_parse()
    test_yaml_dump()
    test_manifest_write_read()
    test_manifest_read_none()
    test_ensure_build_dir()
    test_compute_artifact_hash()
    test_register_artifact()
    test_clean_build()
    test_is_artifact_stale()
    test_run_md_basic()
    test_run_md_skip()
    test_run_md_only_code()
    test_run_md_multiple()
    test_run_md_export_import()
    test_run_md_workdir()
    test_run_md_args()
    test_run_md_env()
    test_run_md_timeout()
    test_run_md_output()
    test_run_md_incremental()
    test_run_md_stdin()
    test_cli_check()
    test_cli_info()
    test_cli_clean()
    test_validate_timeout()
    test_validate_export_import_mutex()
    test_run_md_import()
    test_run_md_cross_file_artifacts()
    test_run_multiple_md()
    test_resolve_imports()
    # M4 tests
    test_scan_library()
    test_build_library_manifest()
    test_load_library_manifest()
    test_run_library()
    # M5 tests
    test_run_md_breakpoint()
    test_run_md_profiling()
    test_run_md_parallel()
    test_run_md_cache_optimization()
    # M7 tests
    test_error_base_class()
    test_error_import_missing()
    test_error_directive_validation()
    test_logger_module()
    test_parse_empty_md()
    test_parse_no_code_blocks()
    print()
    print('All 55 md.bridge tests passed!')
