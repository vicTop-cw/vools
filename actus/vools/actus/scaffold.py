"""scaffold.py —— 根据自然语言描述生成动作骨架（docs/10 §D.2）。

职责：
1. 根据描述关键词匹配模板（templates/ 目录）；
2. 自动生成合法 action_id（反向域名风格）；
3. 用 description / id / name / trust 替换模板占位符；
4. 写出 .actus.md 骨架文件，并立即调用 validate_action 给出首次校验结果。

本模块是"薄壳"——不持有动作语义，只负责文件生成与占位符替换。
"""

__all__ = ['scaffold_action', 'list_templates', 'match_template']

import json
import os
import re
from typing import Dict, List, Optional

# 模板目录。本模块已迁入 vools.actus，而 `actions/templates/` 仍随宿主仓库走
# （docs/32 迁移约定：仓库只留 .md/.json）。alias 后被 Actus 进程加载时，若仍按
# `__file__` 推导会指向 vools 安装树 —— 那里没有动作模板。故优先读
# `ACTUS_REPO_ROOT`（run_tests.ps1 / CLI 均会设），退回本文件上三级目录。
_TEMPLATES_DIR = os.path.join(
    os.environ.get('ACTUS_REPO_ROOT')
    or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'actions', 'templates')


def list_templates() -> List[Dict[str, str]]:
    """列出全部可用模板（每个模板读取其 #!cfg 中的 id 和 description）。"""
    templates = []
    if not os.path.isdir(_TEMPLATES_DIR):
        return templates
    for fname in sorted(os.listdir(_TEMPLATES_DIR)):
        if not fname.endswith('.actus.md'):
            continue
        path = os.path.join(_TEMPLATES_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = f.read()
            # 尝试从 #!cfg 提取 id 和 description
            from .model import parse_cfg
            from .frontmatter import strip_frontmatter  # noqa: E402
            body = strip_frontmatter(raw)
            try:
                meta = parse_cfg(body)
                templates.append({
                    'template_file': fname,
                    'default_id': meta.get('id', ''),
                    'trust': meta.get('trust', 'audit'),
                    'description': meta.get('description', ''),
                })
            except Exception:
                templates.append({
                    'template_file': fname,
                    'default_id': '',
                    'trust': '',
                    'description': '',
                })
        except Exception:
            pass
    return templates


def _strip_fm(raw: str) -> str:
    """轻量 front-matter 剥离（仅剥离 --- 包裹的 AIGC 头部）。"""
    if not raw.startswith('---'):
        return raw
    end = raw.find('\n---', 3)
    if end == -1:
        return raw
    return raw[end + 4:].lstrip('\n')


def match_template(description: str) -> Optional[str]:
    """根据描述关键词匹配最佳模板，返回模板文件名或 None（用默认 Python 模板）。"""
    desc_lower = description.lower()

    # 关键词 → 模板文件映射
    rules = [
        (['shell', 'bash', 'sh ', '命令行', 'command', 'exec'], 'sandbox.shell.actus.md'),
        (['写文件', 'file write', '写文件', '写磁盘', 'save'], 'audit.file_write.actus.md'),
        (['工作流', 'workflow', 'dag', 'pipeline', '流水线', '编排'], 'workflow.linear.actus.md'),
        (['录制', '回放', 'macro', '键鼠', 'keyboard', 'mouse'], 'macro.playback.actus.md'),
        (['监控', 'monitor', 'watch', '文件夹', '目录监听', 'file watch'], 'monitor.folder.actus.md'),
        (['python', 'py ', 'trusted', '脚本'], 'trusted.python.actus.md'),
    ]

    for keywords, template in rules:
        if any(kw in desc_lower for kw in keywords):
            return template

    # 默认：trusted Python 模板
    return 'trusted.python.actus.md'


def _generate_id(description: str, explicit_id: Optional[str] = None) -> str:
    r"""生成合法 action_id（docs/03 §4.2：^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$，段内允许下划线）。

    显式指定时直接校验使用；否则从描述中自动生成：取前 3 个有意义单词，
    以连字符连接，前缀 actus.generated。
    """
    if explicit_id:
        _validate_id(explicit_id)
        return explicit_id

    # 从描述提取单词
    words = re.findall(r'[a-zA-Z\u4e00-\u9fff]+', description)
    if not words:
        words = ['action']

    slug_words = []
    for w in words[:3]:
        # 中文转 pinyin 风格（退化：直接 unicode 编码）——这里简单用 'zh' 标记
        if re.match(r'[\u4e00-\u9fff]', w):
            slug_words.append('zh')
        else:
            slug_words.append(w.lower())

    slug = '-'.join(slug_words)
    # 保证只含小写字母数字（schema pattern: ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$）
    slug = re.sub(r'[^a-z0-9]', '', slug)

    return f'actus.generated.{slug}'


def _validate_id(aid: str) -> None:
    """校验 action_id 格式（docs/03 §4.2）。"""
    if not re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$', aid):
        from .errors import ActionError
        raise ActionError('action_invalid',
                          f'action_id 格式非法: {aid!r}（应为反向域名风格，如 actus.hello）',
                          {'hint': '见 docs/03 §4.2'})


def _generate_name(aid: str) -> str:
    """从 id 生成可读 name（取最后一段，连字符转空格）。"""
    last = aid.rsplit('.', 1)[-1]
    return last.replace('-', ' ').replace('_', ' ').title()


def scaffold_action(
    description: str,
    action_id: Optional[str] = None,
    trust: str = 'audit',
    output_dir: Optional[str] = None,
    author: str = 'ai-scaffold',
    repo_root: Optional[str] = None,
) -> dict:
    """根据自然语言描述生成动作骨架。

    参数:
        description: 动作用途的自然语言描述。
        action_id: 指定动作 id（缺省自动生成）。
        trust: 信任级别（默认 audit，见 docs/07）。
        output_dir: 输出目录（缺省 = repo_root/actions/ 或模块推断的 actions/）。
        author: 作者标识。
        repo_root: 仓库根目录（用于定位 actions/ 和 _meta/）。

    返回:
        dict: {
            'path': 写出路径,
            'id': 动作 id,
            'trust': 信任级别,
            'template': 使用的模板,
            'validation': { 'valid': bool, 'errors': [...] },
            'next_steps': [...],
        }
    """
    if not description or not description.strip():
        from .errors import ActionError
        raise ActionError('action_invalid', '描述不能为空')

    # 1) 匹配模板
    template_name = match_template(description)
    template_path = os.path.join(_TEMPLATES_DIR, template_name)
    if not os.path.isfile(template_path):
        # 模板缺失 —— 回退到内联最小模板
        template_name = '__inline__'
        template_body = _with_entry_driver(_INLINE_PYTHON_TEMPLATE)
    else:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_body = f.read()
        # 外部模板（如 Actus 仓 actions/templates/*.actus.md）也可能是旧版驱动协议：
        # 只写 `params = json.loads(os.environ['ACTUS_PARAMS'])` + `print(...)`，
        # 而 md 引擎以 __name__='__md_block__' 执行块，那种写法下 data 恒为 null
        # （tests/actus/test_scaffold.py::test_entry_block_has_module_level_driver 钉此）。
        # 这里与内联分支一致补上 ENTRY_DRIVER，保证无论模板来源都满足引擎契约。
        # 注意：不能改 Actus 仓的模板文件，驱动由 vools 侧 scaffold 负责补齐。
        if '_zparams' not in template_body:
            template_body = _with_entry_driver(template_body)

    # 2) 生成 id / name
    aid = _generate_id(description, action_id)
    name = _generate_name(aid)

    # 3) 替换模板中的占位符
    #    占位符: <namespace>.<name> → id,  name → 可读 name,
    #     description → 用户描述, trust → 信任级别, author → 作者
    #    正则用 (?:[^"\\]|\\.)* 匹配 JSON 字符串（可含转义 \"）
    rendered = template_body
    rendered = rendered.replace('actus.<namespace>.<name>', aid)
    rendered = rendered.replace('actus.<namespace>.step1', f'{aid}-step1')
    rendered = rendered.replace('actus.<namespace>.step2', f'{aid}-step2')
    rendered = rendered.replace('actus.<namespace>.step3', f'{aid}-step3')
    # 替换 id（模板 JSON 中的 "id" 字段）
    rendered = re.sub(
        r'("id":\s*)"((?:[^"\\]|\\.)*)"',
        lambda m: f'{m.group(1)}"{aid}"',
        rendered,
        count=1,
    )
    # 替换 name
    rendered = re.sub(
        r'("name":\s*)"((?:[^"\\]|\\.)*)"',
        lambda m: f'{m.group(1)}"{name}"',
        rendered,
        count=1,
    )
    # 替换 description
    rendered = re.sub(
        r'("description":\s*)"((?:[^"\\]|\\.)*)"',
        lambda m: f'{m.group(1)}"{description}"',
        rendered,
        count=1,
    )
    # 替换 trust
    rendered = re.sub(
        r'("trust":\s*)"((?:[^"\\]|\\.)*)"',
        lambda m: f'{m.group(1)}"{trust}"',
        rendered,
        count=1,
    )
    # 替换 usage（使用 json.dumps 保证合法转义）
    usage_text = f'调用示例: {aid.replace(".", "_")}({{"param": "value"}});\n返回: {{"status": "ok"}}'
    usage_escaped = json.dumps(usage_text)[1:-1]
    rendered = re.sub(
        r'("usage":\s*)"((?:[^"\\]|\\.)*)"',
        lambda m: f'{m.group(1)}"{usage_escaped}"',
        rendered,
        count=1,
    )
    # 替换 author（兼容 "string" 和 null 两种写法）
    rendered = re.sub(
        r'("author":\s*)(?:"((?:[^"\\]|\\.)*)"|null)',
        lambda m: f'{m.group(1)}"{author}"',
        rendered,
    )
    # 替换内联模板注释中的 {name}（BUG-0032）
    rendered = rendered.replace('# {name}', f'# {name}')
    # 更新 ai.generated
    rendered = re.sub(
        r'("generated":\s*)(true|false)',
        '"generated": true',
        rendered,
    )

    # 4) 写出文件
    if output_dir is None:
        if repo_root:
            output_dir = os.path.join(repo_root, "actions")
        else:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "actions")
    os.makedirs(output_dir, exist_ok=True)
    # 文件名：id 最后一段
    file_name = aid.rsplit('.', 1)[-1] + '.actus.md'
    file_path = os.path.join(output_dir, file_name)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(rendered)

    # 5) 首次校验
    validation = {'valid': False, 'errors': []}
    try:
        from .model import parse_cfg_from_file
        from .validate import validate_action
        action = parse_cfg_from_file(file_path)
        errs = validate_action(action)
        validation['valid'] = len(errs) == 0
        validation['errors'] = errs
    except Exception as e:
        validation['errors'] = [str(e)]

    # 6) 下一步提示
    next_steps = [
        f'编辑 {file_path} 中的 TODO 部分实现动作逻辑',
        f'运行 actus validate {aid} 校验',
    ]
    if trust == 'audit':
        next_steps.append(f'确认无误后运行 actus run {aid} --confirm 执行（或标记为 trusted）')

    return {
        'path': os.path.abspath(file_path),
        'id': aid,
        'trust': trust,
        'template': template_name,
        'validation': validation,
        'next_steps': next_steps,
    }


# ── 内联最小模板（模板目录缺失时回退） ──

# 引擎契约（docs/38 §1）：md 引擎以 __name__='__md_block__' 执行块
# （vools/bridge/md/runner.py:698），而 executor 只用入口块的 stdout 造 data。
# 所以调用必须写在模块级 —— 写在 `if __name__ == "__main__":` 里的动作
# 每次执行都"成功"且 data 恒为 null。新增动作只能从这份常量长出去。
ENTRY_DRIVER = '''

# 引擎契约：调用必须在模块级，见 docs/38 §1
import inspect as _zinspect, json as _zjson, os as _zos
_zparams = _zjson.loads(_zos.environ.get('ACTUS_PARAMS') or '{}')
if __name__ != "__main__" or _zparams:
    _zsig = _zinspect.signature(main).parameters
    _zhas_var_kw = any(p.kind is _zinspect.Parameter.VAR_KEYWORD
                       for p in _zsig.values())
    _zrequired_pos = [n for n, p in _zsig.items()
                      if p.kind in (_zinspect.Parameter.POSITIONAL_ONLY,
                                    _zinspect.Parameter.POSITIONAL_OR_KEYWORD)
                      and p.default is _zinspect.Parameter.empty]
    if _zhas_var_kw:
        # main(**kwargs) 形态：原样展开
        print(_zjson.dumps(main(**_zparams), ensure_ascii=False))
    elif _zrequired_pos and any(n not in _zparams for n in _zrequired_pos):
        # 有"ACTUS_PARAMS 满足不了的必需位置参数"（如外部模板的 main(params: dict)，
        # 而 ACTUS_PARAMS 给的是 {'param': ...}）：回退成位置调用 main(_zparams)。
        # 否则 main(**_zparams) 会 TypeError: missing 1 required positional argument，
        # 整个块 rc=1（实测 tests/actus/test_scaffold.py 端到端用例钉此）。
        print(_zjson.dumps(main(_zparams), ensure_ascii=False))
    else:
        # 命名参数形态：过滤掉 main 不认识的键后展开
        print(_zjson.dumps(main(**{k: v for k, v in _zparams.items()
                                   if k in _zsig}), ensure_ascii=False))

if __name__ == "__main__":
    import json, sys
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(**params), ensure_ascii=False, indent=2))
'''

_INLINE_PYTHON_TEMPLATE = '''---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: PLACEHOLDER
    ReservedCode1: PLACEHOLDER
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: PLACEHOLDER
    ReservedCode2: PLACEHOLDER
---

# {name}

```json #!cfg
{
  "id": "actus.<namespace>.<name>",
  "name": "my-action",
  "version": "1.0.0",
  "trust": "audit",
  "deps": [],
  "entry": "main",
  "description": "TODO: 动作描述",
  "usage": "调用示例: actus_<namespace>_<name>({\\"param\\": \\"value\\"});\\n返回: {\\"status\\": \\"ok\\"}",
  "author": "ai-scaffold",
  "permissions": ["files:read"],
  "args": {
    "type": "object",
    "properties": {
      "param": { "type": "string", "description": "参数说明" }
    },
    "required": ["param"]
  },
  "ai": { "generated": true, "author": "ai-scaffold", "evolve_policy": "confirm" }
}
```

```python #!run tag=main
"""
动作入口函数（内联模板）。

入参:
    param (str): 从 args 传入的参数。
返回:
    dict: 执行结果。
"""

def main(param: str) -> dict:
    # TODO: 实现动作逻辑
    return {"status": "ok", "result": param}
```
'''


# 闭栏前的驱动注入点：模板正文自带闭栏，所以驱动拼在最后一个块里而不是尾部。

# 旧驱动协议（外部模板自带）：读 ACTUS_PARAMS → 直接 print。
# 它在新驱动存在时会【重复输出一份 JSON】——executor 只用入口块 stdout 造 data，
# 两份 JSON 会让 json.loads 抛 "Extra data"（实测 tests/actus 端到端用例钉此）。
# 追加 ENTRY_DRIVER 前先把它剥掉。只匹配模块级调用尾巴，不动 `def main` 本体。
_LEGACY_DRIVER_RE = None


def _strip_legacy_driver(block_text):
    """剥掉 python 块尾部旧协议的模块级调用/打印（返回新文本）。"""
    global _LEGACY_DRIVER_RE
    if _LEGACY_DRIVER_RE is None:
        import re as _re
        # 形如:
        #   params = json.loads(os.environ.get('ACTUS_PARAMS') or '{}')
        #   print(json.dumps(main(params), ensure_ascii=False))
        # 允许夹注释行与空行；锚定到块尾。
        _LEGACY_DRIVER_RE = _re.compile(
            r'(?:\n[ \t]*(?:#[^\n]*)?)*'
            r'\n[ \t]*params\s*=\s*json\.loads\(\s*os\.environ\.get\(\s*[\'"]ACTUS_PARAMS[\'"][^\n]*\n'
            r'[ \t]*print\(\s*json\.dumps\(\s*main\([^\n]*\n?'
            r'\s*\)?[^\n]*\n?'
        )
    return _LEGACY_DRIVER_RE.sub('\n', block_text)


def _with_entry_driver(text):
    """把 ENTRY_DRIVER 插进最后一个 python 块的闭栏**之前**。

    插在闭栏之外就落进了 markdown，动作照旧静默空转且没人报错 ——
    这条上一轮踩过（插错位置得到的假绿被当成"补了驱动还是 ok"）。
    注入前先剥掉模板自带的旧协议调用，避免与 ENTRY_DRIVER 重复输出两份 JSON。
    """
    close = text.rfind('```')
    opener = text.rfind('```python', 0, close)
    if close < 0 or opener < 0:
        return text + ENTRY_DRIVER + '\n'
    body = _strip_legacy_driver(text[opener:close])
    return text[:opener] + body + ENTRY_DRIVER + text[close:]
