# -*- coding: utf-8 -*-
"""复现 frontmatter.py: _AIGC_KEYS 含 'generated-by-at'，但判别 startswith 元组
只有 ('AIGC:','aigc:','generated-by:') —— 'generated-by-at:' 不命中 'generated-by:'
（第 12 字符 'a' vs ':'）。结果：仅含 generated-by-at 的 AIGC 合规块被判成 meta，
双层 front-matter 场景下 parse_action_metadata 把 AIGC 块当元数据返回。"""
import sys
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus.frontmatter import (_split_frontmatter_blocks, strip_frontmatter,
                                     parse_action_metadata, _AIGC_KEYS)

# 场景 1：区域 0 只用 generated-by-at（_AIGC_KEYS 声明支持该特征键）+ 区域 1 元数据
text = (
    '---\n'
    'generated-by-at: 2026-10-01T10:00:00+08:00\n'
    'generated-by-tool: some-ai\n'
    '---\n'
    '---\n'
    'id: actus.demo\n'
    'name: Demo\n'
    'version: 1.0.0\n'
    '---\n'
    '#!entry main\n'
    '```python #!tag=main\nprint(1)\n```\n'
)
# 先自证判别逻辑与 _AIGC_KEYS 脱节：
probe = 'generated-by-at: x'
hit = probe.startswith(('AIGC:', 'aigc:', 'generated-by:'))
print("generated-by-at 在 _AIGC_KEYS:", 'generated-by-at' in _AIGC_KEYS)
print('generated-by-at: 命中 startswith 判别:', hit)
assert not hit

blocks, body = _split_frontmatter_blocks(text)
kinds = [k for k, _ in blocks]
print('blocks kinds:', kinds)
assert kinds == ['meta', 'meta'], kinds   # AIGC 块被误判成 meta

meta, remaining = parse_action_metadata(text)
print('parse_action_metadata meta:', meta)
# 返回的是 AIGC 块的字典，不是动作元数据
assert 'generated-by-at' in meta and 'id' not in meta
print('→ 确认：双层 front-matter 文件拿到 AIGC 块当元数据（缺 id → 下游必填校验报错，动作不可用）')

# 场景 2：块内含 AIGC: 键时判定正常（对照，说明只有 generated-by-at 单键才踩坑）
text2 = '---\nAIGC: 1\ngenerated-by-at: 2026-10-01\n---\n正文\n'
meta2, rem2 = parse_action_metadata(text2)
print('场景2 meta（对照，应 {}）:', meta2)
assert meta2 == {}

# 场景 2b：只含 generated-by-at（_AIGC_KEYS 声明支持）的孤块
text2b = '---\ngenerated-by-at: 2026-10-01\n---\n正文\n'
meta2b, rem2b = parse_action_metadata(text2b)
print('场景2b meta（文档承诺无元数据块时应为 {}）:', meta2b)
assert meta2b != {}, '实际把 AIGC 合规块当动作元数据返回'
print('→ 确认场景 2b')

# 场景 3：strip_frontmatter 对 generated-by-at 块不剥离（文档说区域 0 = 合规留痕应剥）
s = strip_frontmatter(text)
print('strip 后前 40 字符:', repr(s[:40]))
assert s.startswith('---\ngenerated-by-at'), 'AIGC 块应被剥离'
print('ALL FRONTMATTER REPROS OK')
