"""tests/actus/test_scaffold.py — 骨架生成的可执行性回归

背景（2026-10-13 实测）：vools 侧 `scaffold._INLINE_PYTHON_TEMPLATE` 曾是
`.format()` 时代的写法（JSON 里全是 `{{ }}`），但渲染走的是 `.replace()`。
于是生成的动作里 cfg 块是 `{{` 开头 —— **不是合法 JSON**，`parse_cfg` 直接炸；
python 块里的 `{{"status": "ok"}}` 也变成"含 dict 的 set"（`TypeError: unhashable
type: 'dict'`）。vools 侧当时没有任何 scaffold 测试，所以这两处一直没被发现。

另一条是 docs/38 §1 的静默空转：模板只把调用写在 `if __name__ == "__main__":` 里，
而 md 引擎以 `__name__='__md_block__'` 执行块，于是动作"每次都成功但 data 恒为 null"。
本文件同时钉住这两格。
"""
import io
import json
import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus import scaffold  # noqa: E402

FENCE = '`' * 3


@pytest.fixture()
def scaffolded():
    """生成一个骨架动作，返回 (路径, 全文)。"""
    tmp = tempfile.mkdtemp(prefix='vools_scaffold_test_')
    res = scaffold.scaffold_action(
        '回归测试用骨架', action_id='actus.test.scaffoldprobe',
        output_dir=tmp, repo_root=tmp)
    path = res.get('path') or res.get('file_path')
    assert path and os.path.isfile(path), f'scaffold 未产出文件: {res}'
    return path, io.open(path, encoding='utf-8').read()


def _cfg_block(text):
    m = re.search(FENCE + r'json #!cfg\n(.*?)\n' + FENCE, text, re.S)
    assert m, '未找到 #!cfg 块'
    return m.group(1)


def _python_blocks(text):
    return re.findall(FENCE + r'python[^\n]*\n(.*?)' + FENCE, text, re.S)


def test_cfg_block_is_valid_json(scaffolded):
    """cfg 块必须是合法 JSON —— 双括号模板会让它整块非法。"""
    _, text = scaffolded
    raw = _cfg_block(text)
    cfg = json.loads(raw)          # 非法即抛，不吞
    assert cfg['id'] == 'actus.test.scaffoldprobe'
    assert cfg['entry'] == 'main'


def test_no_unrendered_double_braces(scaffolded):
    """生成物里不得残留 `{{` —— 那是模板占位没被替换掉的痕迹。"""
    _, text = scaffolded
    assert '{{' not in text, '生成的动作里残留 {{，模板大括号与渲染方式不匹配'


def test_python_block_compiles(scaffolded):
    """python 块必须可编译（`{{"status": ...}}` 是 set 字面量，会在运行期炸）。"""
    _, text = scaffolded
    blocks = _python_blocks(text)
    assert blocks, '未找到 python 块'
    for i, code in enumerate(blocks):
        compile(code, f'<scaffold-block-{i}>', 'exec')


def test_entry_block_has_module_level_driver(scaffolded):
    """入口块必须带模块级驱动（docs/38 §1），否则引擎下静默空转。"""
    _, text = scaffolded
    code = _python_blocks(text)[-1]
    assert '_zparams' in code, '入口块缺模块级驱动 —— 引擎下 data 会恒为 null'
    # 驱动必须在块内，不能落在闭栏之外的 markdown 里
    close = text.rfind(FENCE)
    assert text.find('_zparams') < close


def test_scaffolded_action_runs_under_md_block_semantics(scaffolded):
    """端到端：以引擎的形状（__name__='__md_block__' + ACTUS_PARAMS）执行，
    stdout 必须是结构化 JSON，而不是空。"""
    import subprocess
    _, text = scaffolded
    code = _python_blocks(text)[-1]
    env = dict(os.environ)
    env['ACTUS_PARAMS'] = json.dumps({'param': 'hello'})
    env['PYTHONPATH'] = os.pathsep.join([
        os.path.join(os.path.dirname(__file__), '..', '..'),
    ])
    runner = (
        'code = ' + repr(code) + '\n'
        'g = {"__name__": "__md_block__"}\n'
        'exec(compile(code, "<block>", "exec"), g)\n'
    )
    r = subprocess.run([sys.executable, '-c', runner],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f'块执行失败: {r.stderr[-400:]}'
    out = (r.stdout or '').strip()
    assert out, 'stdout 为空 —— 动作静默空转（docs/38 §1）'
    data = json.loads(out)
    assert data.get('status') == 'ok', data
