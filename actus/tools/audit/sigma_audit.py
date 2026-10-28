# -*- coding: utf-8 -*-
"""sigma.py 审计：17 条 Iron Laws 逐条反例 + 门禁假通过探测。"""
import json, os, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
from vools.actus import sigma

BASE = """# Module: audit.demo
# Version: 0.1.0
# Expected: PASS

## Imports
import core
import util

## Exports
f

## Operation: f (ℕ)
### Signature
f: ℕ → ℕ
### Laws
∀x: f(x) ≡ x
### Tests
| Input | Output |
| 1 + 1 | 2 |
| 1 / 0 | ⊥ |
### Definition
x
Fingerprint: 0xA001
"""

def mod(text=BASE):
    return sigma.parse_module_text(text)

def violations(module):
    r = sigma.check_iron_laws(module)
    return r

print('=== 0) 基线 ===')
m = mod()
r = violations(m)
print('  passed=%s | tests=%d/%d | failed_laws=%s | advisory=%s'
      % (r['passed'], r['tests']['passed'], r['tests']['total'],
         [l['id'] for l in r['failed_laws']], [l['id'] for l in r['advisory_laws']]))

# ── 逐条反例：每条只破坏一条定律 ──
cases = {
 'I   (删 Fingerprint)': BASE.replace('Fingerprint: 0xA001\n', ''),
 'I   (重复指纹)': BASE + '## Operation: g (ℕ)\n### Signature\ng: ℕ → ℕ\n### Laws\n∀x: g(x) ≡ x\n### Tests\n| Input | Output |\n| 1 | 1 |\nFingerprint: 0xA001\n',
 'II  (返回类型 Str 无 encoder)': BASE.replace('f: ℕ → ℕ', 'f: ℕ → Str'),
 'III (删 Laws)': BASE.replace('∀x: f(x) ≡ x\n', ''),
 'IV  (删 Tests)': BASE.replace('| Input | Output |\n| 1 + 1 | 2 |\n| 1 / 0 | ⊥ |\n', ''),
 'V   (Definition 含 while loop)': BASE.replace('### Definition\nx', '### Definition\nwhile loop {}'),
 'VI  (版本非 semver)': BASE.replace('# Version: 0.1.0', '# Version: 1.0'),
 'VII (不 import core)': BASE.replace('import core\n', ''),
 'VIII(print 无 Timing)': BASE.replace('### Definition\nx', '### Definition\nprint("hi")'),
 'IX  (Conf 返回但 Laws 无 0/1)': BASE.replace('f: ℕ → ℕ', 'f: ℕ → Conf').replace('∀x: f(x) ≡ x', '∀x: f(x) ≡ g(x)'),
 'X   (IO 无 Capabilities/Timing)': BASE.replace('### Definition\nx', '### Definition\nread_file(p)'),
 'XI  (read_file 无 ReadFile 能力)': BASE.replace('### Definition\nx', '### Definition\nread_file(p)'),
 'XII (open 不 close)': BASE.replace('### Definition\nx', '### Definition\nopen(r1)'),
 'XIV (无 ⊥ 负向测试)': BASE.replace('| 1 / 0 | ⊥ |\n', ''),
 'XV  (幽灵 export)': BASE.replace('## Exports\nf', '## Exports\nf, ghost'),
 'XVI (Compat Tests 失败)': BASE.replace('Fingerprint: 0xA001',
     'Fingerprint: 0xA001\n\n## Compat Tests\n| Input | Output |\n| 1 + 1 | 3 |\n'),
 'XVII(Guarantee 声明但 metric 非法)': BASE.replace('Fingerprint: 0xA001',
     'Fingerprint: 0xA001\n\n## Guarantee\nmetric: nonsense\nthreshold: 0.9\ndataset: d\n'),
}
print('\n=== 1) 逐条反例：破坏后能否被捕获 ===')
for label, text in cases.items():
    try:
        mm = mod(text)
        rr = sigma.check_iron_laws(mm)
        # 找出该条定律的结果
        law_id = label.split()[0]
        entry = next((l for l in rr['laws'] if l['id'] == law_id), None)
        caught = bool(entry and entry['violations'])
        print('  %-34s passed=%-5s 本定律violations=%s' % (
            label, rr['passed'], (entry['violations'] if entry else 'N/A')))
    except Exception as exc:
        print('  %-34s 抛异常 %s: %s' % (label, type(exc).__name__, str(exc)[:60]))
