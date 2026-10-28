"""vools.actus.sigma — Sigma-Law 规范引擎（docs/41 §3 主题 A，G1）。

本模块把归档项目 sigma-lang（ΣLang）的核心能力内置化进 actus，作为
**元动作引擎**：任何安装了 vools-actus 的机器 / 零散动作运行时都可直接使用，
不必绑定 actus 主仓（docs/41 §A2 落点理由）。

能力清单（docs/41 §A2）：
    1. spec 解析          parse_module / parse_module_text / extract_sigma_block
    2. Iron Laws 校验     check_iron_laws（17 条，可机检的落地，不可机检的显式 advisory）
    3. verify 调用        verify_module / run_sigma_block（语言路由入口；verify_spec 已删——它只是 verify_module 的薄包装且全仓零调用）
    4. spec JSON 生成     to_spec_json / validate_spec_json
    5. sigma-spec2judge   judge_spec（spec JSON → judge 验收断言）
    6. sigma-bootstrap    bootstrap（spec → impl 骨架 → verify 闭环）

设计约束：
    * **仅标准库**：与 sigma-lang 三端验证器的 Python 端一致，不引入 jsonschema/yaml/requests。
    * **语义与 sigma-lang 三端验证器对齐**：MD 语法、违规名、参考求值器的取值顺序均逐字移植，
      否则同一份规约在 actus 与 sigma-lang 之间会出现判定漂移。
    * **不纳入 sigma-cli 运行时依赖**（docs/41 §A2）：只借鉴其调用形态。

来源与许可：移植自 sigma-lang v0.7.x（MIT，Copyright (c) 2025 ΣLang Working Group）。
MIT §4 要求在实质部分中包含版权声明，故保留本段与 LICENSE-SIGMA 归属说明。
"""


__all__ = [
    # 常量与词表
    'SIGMA_LANGUAGE_TAGS', 'SIGMA_VERSION', 'IRON_LAWS', 'ERROR_NAMES',
    'NUMERIC_TYPES', 'OPAQUE_MATH', 'BUILTIN_FNS',
    # 解析
    'parse_module', 'parse_module_text', 'extract_sigma_block', 'parse_package',
    # 校验
    'check_iron_laws', 'check_python', 'verify_module',
    'SpecError', 'IronLawViolation',
    # spec JSON
    'to_spec_json', 'validate_spec_json', 'load_spec_json', 'SigmaEngine',
    'fingerprint_of', 'fingerprint_of_spec',
    # judge / bootstrap
    'judge_spec', 'spec_to_assertions', 'bootstrap', 'render_impl_skeleton',
    # 语言路由入口
    'run_sigma_block', 'is_sigma_language', 'sigma_block_is_loadable',
]

__version__ = '1.0.0'

import io
import json
import os
import re
import sys
import hashlib
import importlib.util
import contextlib
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 0. 语言标记（docs/41 §A1）
# ---------------------------------------------------------------------------

#: 代码块语言标记：动作内 ```sigma / ```sigma-spec / ```sigma-md 均路由到本引擎。
SIGMA_LANGUAGE_TAGS = ('sigma', 'sigma-spec', 'sigma-md')

#: 本引擎所兼容的 Sigma 规约方言版本（对齐 sigma-lang spec/json-schema.md v1.0）
SIGMA_VERSION = '1.0'

NUMERIC_TYPES = {'ℕ', 'ℤ', 'ℚ', 'ℝ', 'ℂ', 'Conf', 'Time'}

#: §S.3 Opaque 类符号：不得被 shadow（verify_consensus.py:528 / main.rs:769 逐字一致）
OPAQUE_MATH = {'⊕', '⊗', '⊖', '⊘', '⊙', '≡', '≥', '≤', '∈', 'ℕ', 'ℤ', 'ℚ', 'ℝ'}

#: 规范固定错误名（spec/json-schema.md:145-149 == sigma_engine.py:67-73）
ERROR_NAMES = [
    'BountyErr', 'StateError', 'AuthError', 'TypeError', 'ShapeError',
    'QuotaExhausted', 'InsufficientEscrow', 'InsufficientPoints',
    'InsufficientStock', 'TeamFull', 'InsufficientFunds', 'UnknownAsset',
    'InsufficientShares', 'UnknownItem', 'DivByZero', 'NotTraceable',
    'ReserveErr', 'BidAmountErr', 'ClosedErr', 'TimeoutErr',
]


def is_sigma_language(language: str) -> bool:
    """语言标记是否属于 sigma 族（大小写不敏感）。"""
    return (language or '').strip().lower() in SIGMA_LANGUAGE_TAGS


# ---------------------------------------------------------------------------
# 1. Iron Laws 登记表（17 条）
#
#    来源：README.md:493-511 + spec/spec_p0_foundations.md §0.1/§0.2（I–XII）
#          spec/spec_top_extensions.md（XIII–XVII）
#          impl/verifier/src/main.rs:216-239（唯一的机器可读枚举真源）
#
#    `check` 为 None 表示本机无法判定（需要跨端共识或外部语料），显式记为
#    advisory —— 绝不静默当作通过（docs/03 §6「严禁静默降级」）。
# ---------------------------------------------------------------------------

IRON_LAWS: Tuple[Dict[str, Any], ...] = (
    {'id': 'I', 'key': 'fingerprint_uniqueness', 'zh': '指纹唯一性',
     'en': 'Fingerprint Uniqueness', 'check': 'check_fingerprint_uniqueness'},
    {'id': 'II', 'key': 'encoding_to_nat', 'zh': '编码到 ℕ',
     'en': 'Encoding to ℕ', 'check': 'check_encoding'},
    {'id': 'III', 'key': 'law_declaration', 'zh': '定律声明',
     'en': 'Law Declaration', 'check': 'check_law_declaration'},
    {'id': 'IV', 'key': 'test_mandatory', 'zh': '测试强制',
     'en': 'Test Mandatory', 'check': 'check_tests_mandatory'},
    {'id': 'V', 'key': 'no_implementation_in_spec', 'zh': '规范中无实现',
     'en': 'No Implementation in Spec', 'check': 'check_no_implementation'},
    {'id': 'VI', 'key': 'backward_compatibility', 'zh': '向后兼容',
     'en': 'Backward Compatibility', 'check': 'check_backward_compat'},
    {'id': 'VII', 'key': 'explicit_dependencies', 'zh': '显式依赖',
     'en': 'Explicit Dependencies', 'check': 'check_dependencies'},
    {'id': 'VIII', 'key': 'temporal_determinism', 'zh': '时序确定性',
     'en': 'Temporal Determinism', 'check': 'check_timing_contract'},
    {'id': 'IX', 'key': 'calibration_requirement', 'zh': '校准要求',
     'en': 'Calibration Requirement', 'check': 'check_calibration'},
    {'id': 'X', 'key': 'effect_transparency', 'zh': '效应透明',
     'en': 'Effect Transparency', 'check': 'check_effect_transparency'},
    {'id': 'XI', 'key': 'capability_discipline', 'zh': '能力纪律',
     'en': 'Capability Discipline', 'check': 'check_capabilities'},
    {'id': 'XII', 'key': 'resource_linearity', 'zh': '资源线性',
     'en': 'Resource Linearity', 'check': 'check_resource_linearity'},
    {'id': 'XIII', 'key': 'verifier_consensus', 'zh': '验证器共识',
     'en': 'Verifier Consensus', 'check': 'check_consensus'},
    {'id': 'XIV', 'key': 'negative_test_mandatory', 'zh': '负向测试强制',
     'en': 'Negative Test Mandatory', 'check': 'check_negative_tests'},
    {'id': 'XV', 'key': 'export_completeness', 'zh': '导出完整性',
     'en': 'Export Completeness', 'check': 'check_export_completeness'},
    {'id': 'XVI', 'key': 'compatibility_proof', 'zh': '兼容性证明',
     'en': 'Compatibility Proof', 'check': 'check_compat_proof'},
    {'id': 'XVII', 'key': 'probabilistic_guarantee', 'zh': '概率保证',
     'en': 'Probabilistic Guarantee', 'check': 'check_guarantee'},
)

#: 非定律但同属规范细则的补充检查（§S 遮蔽纪律 / P-01 证明结构 / E-03 可移植断言 /
#: E-06 内部一致性 / E-10 求值确定性 / S-01 包签名）。
SUPPLEMENTAL_CHECKS = (
    'check_shadowing_discipline',   # §S（spec_top_rules.md）
    'check_proof_structure',        # P-01（spec_top_proofs.md）
    'check_test_portability',       # E-03
    'check_internal_consistency',   # E-06
    'check_eval_determinism',       # E-10
    'check_package_signature',      # E-08 / S-01
)


class SpecError(Exception):
    """规约本身不可解析/不合结构 —— 对应 actus 的 action_invalid 分流。"""


class IronLawViolation(Exception):
    """命名错误基类（与 spec/json-schema.md「错误名约定」一致）。"""

    def __init__(self, message: str = ''):
        super().__init__(message)
        self.message = message
        self.name = self.__class__.__name__


#: 动态生成 20 个命名异常类：BountyErr / StateError / AuthError / …
ERROR_CLASSES = {n: type(n, (IronLawViolation,), {}) for n in ERROR_NAMES}


class UnknownOpError(IronLawViolation):
    """引擎内部错误：引用了 spec 中不存在的操作。"""


class SpecValidationError(IronLawViolation):
    """引擎内部错误：spec JSON 结构不符合 schema。"""


def _raise_error(name: str, message: str = '') -> None:
    """按规范错误名抛异常；未注册名回退 ValueError(name)，与参考实现一致。"""
    cls = ERROR_CLASSES.get(name)
    if cls is not None:
        raise cls(message)
    raise ValueError(name)


# ---------------------------------------------------------------------------
# 2. 值语法与受限求值器（移植自 verify_consensus.py:1445-1510 / 562-1441）
#
#    ⚠ 运算符切分顺序与上游 if-chain **逐字一致**（⊕ ⊗ ⊖ ⊘ ⊙ ≡ ≥ ≤ ∈），
#    切分用「首个出现位置 + 右结合递归」。改动顺序会造成三端判定漂移。
# ---------------------------------------------------------------------------

#: §C 实世界常量（spec_top_rules.md §C），按指纹可解析，IEEE-754 double。
CONSTANTS: Dict[str, Tuple[str, float]] = {
    '0xK001': ('fnum', 3.141592653589793),      # π
    '0xK002': ('fnum', 2.718281828459045),      # e
    '0xK003': ('fnum', 1.618033988749895),      # φ
    '0xK004': ('fnum', 0.5772156649015329),     # γ
    '0xK005': ('fnum', 1.4142135623730951),     # √2
    '0xK006': ('fnum', 0.6931471805599453),     # ln2
    '0xK007': ('fnum', 0.915965594177219),      # G_𝒦
    '0xK008': ('fnum', 1.2020569031595942),     # ζ3
    '0xK009': ('fnum', 4.66920160910299),       # δ_ℱ
    '0xQ001': ('num', 299792458),               # c
    '0xQ002': ('fnum', 6.62607015e-34),         # h
    '0xQ003': ('fnum', 1.054571817e-34),        # ℏ
    '0xQ004': ('fnum', 6.67430e-11),            # G_𝔫
    '0xQ005': ('fnum', 8.8541878128e-12),       # ε₀
    '0xQ006': ('fnum', 1.25663706212e-6),       # μ₀
    '0xQ007': ('fnum', 1.602176634e-19),        # e
    '0xQ008': ('fnum', 1.380649e-23),           # k_B
    '0xQ009': ('fnum', 6.02214076e23),          # N_A
    '0xQ00A': ('fnum', 8.314462618),            # R
    '0xQ00B': ('fnum', 9.1093837015e-31),       # mₑ
    '0xQ00C': ('fnum', 1.67262192369e-27),      # mₚ
    '0xQ00D': ('fnum', 7.2973525693e-3),        # α
    '0xQ00E': ('fnum', 5.670374419e-8),         # σ
    '0xQ00F': ('fnum', 9.80665),                # g₀
    '0xQ010': ('fnum', 10973731.568160),        # R_∞
}

_UNICODE_MINUS = ('−', '﹣', '－', '‐', '‑')


def parse_val(s: str) -> Optional[Tuple[str, Any]]:
    """解析字面量：`2` / `0.5` / `[1,2,3]` / `[[1,2],[3,4]]` / `(1,0)`。失败 None。"""
    for ch in _UNICODE_MINUS:
        s = s.replace(ch, '-')
    s = s.strip()
    if re.fullmatch(r'-?\d+', s):
        return ('num', int(s))
    if re.fullmatch(r'-?\d+\.\d+', s):
        return ('fnum', float(s))
    if s.startswith('[') and s.endswith(']'):
        return parse_list(s[1:-1])
    if s.startswith('(') and s.endswith(')'):
        return parse_list(s[1:-1])
    return None


def parse_list(inner: str) -> Optional[Tuple[str, list]]:
    if inner.strip() == '':
        return ('list', [])
    items = []
    for p in split_all_top_level(inner, ','):
        v = parse_val(p)
        if v is None:
            return None
        items.append(v)
    return ('list', items)


def split_top_level(s: str, sep: str) -> Optional[Tuple[str, str]]:
    """在首个深度 0 的 sep 处切一刀，返回 (left, right)；没有则 None。"""
    depth = 0
    for i, c in enumerate(s):
        if c in '[(':
            depth += 1
        elif c in '])':
            depth -= 1
        elif c == sep and depth == 0:
            return (s[:i], s[i + 1:])
    return None


def split_all_top_level(s: str, sep: str) -> List[str]:
    """在每个深度 0 的 sep 处切分。"""
    pieces = []
    depth = 0
    start = 0
    for i, c in enumerate(s):
        if c in '[(':
            depth += 1
        elif c in '])':
            depth -= 1
        elif c == sep and depth == 0:
            pieces.append(s[start:i].strip())
            start = i + 1
    pieces.append(s[start:].strip())
    return [p for p in pieces if p != '']


def fmt_val(v: Tuple[str, Any]) -> str:
    if v[0] == 'num':
        return str(v[1])
    if v[0] == 'fnum':
        return repr(v[1])
    return '[' + ','.join(fmt_val(x) for x in v[1]) + ']'


def elemwise_add(a, b):
    if a[0] == 'num' and b[0] == 'num':
        return ('num', a[1] + b[1])
    if a[0] in ('num', 'fnum') and b[0] in ('num', 'fnum'):
        return ('fnum', float(a[1]) + float(b[1]))
    if a[0] == 'list' and b[0] == 'list':
        if len(a[1]) != len(b[1]):
            return 'ShapeError'
        out = []
        for x, y in zip(a[1], b[1]):
            r = elemwise_add(x, y)
            if isinstance(r, str):
                return r
            out.append(r)
        return ('list', out)
    return 'ShapeError'


def elemwise_sub(a, b):
    if a[0] == 'num' and b[0] == 'num':
        return ('num', a[1] - b[1])
    if a[0] in ('num', 'fnum') and b[0] in ('num', 'fnum'):
        return ('fnum', float(a[1]) - float(b[1]))
    if a[0] == 'list' and b[0] == 'list':
        if len(a[1]) != len(b[1]):
            return 'ShapeError'
        out = []
        for x, y in zip(a[1], b[1]):
            r = elemwise_sub(x, y)
            if isinstance(r, str):
                return r
            out.append(r)
        return ('list', out)
    return 'ShapeError'


def elemwise_mul(a, b):
    """⊙ Hadamard 逐元素乘。"""
    if a[0] == 'num' and b[0] == 'num':
        return ('num', a[1] * b[1])
    if a[0] in ('num', 'fnum') and b[0] in ('num', 'fnum'):
        return ('fnum', float(a[1]) * float(b[1]))
    if a[0] == 'list' and b[0] == 'list':
        if len(a[1]) != len(b[1]):
            return 'ShapeError'
        out = []
        for x, y in zip(a[1], b[1]):
            r = elemwise_mul(x, y)
            if isinstance(r, str):
                return r
            out.append(r)
        return ('list', out)
    return 'ShapeError'


def elemwise_div(a, b):
    """⊘ 逐元素除：整除回 num，否则 fnum；除零 DivByZero。"""
    if a[0] == 'num' and b[0] == 'num':
        if b[1] == 0:
            return 'DivByZero'
        if a[1] % b[1] == 0:
            return ('num', a[1] // b[1])
        return ('fnum', a[1] / b[1])
    if a[0] in ('num', 'fnum') and b[0] in ('num', 'fnum'):
        if float(b[1]) == 0.0:
            return 'DivByZero'
        return ('fnum', float(a[1]) / float(b[1]))
    if a[0] == 'list' and b[0] == 'list':
        if len(a[1]) != len(b[1]):
            return 'ShapeError'
        out = []
        for x, y in zip(a[1], b[1]):
            r = elemwise_div(x, y)
            if isinstance(r, str):
                return r
            out.append(r)
        return ('list', out)
    return 'ShapeError'


def mat_mul(a, b):
    """⊗ 矩阵乘（行 × 列列表）。"""
    if a[0] == 'list' and b[0] == 'list':
        out = []
        for row in a[1]:
            if row[0] != 'list':
                return 'ShapeError'
            cells = row[1]
            if len(cells) != len(b[1]):
                return 'ShapeError'
            acc = 0
            is_float = False
            for c, v in zip(cells, b[1]):
                if c[0] not in ('num', 'fnum') or v[0] not in ('num', 'fnum'):
                    return 'TypeError'
                if c[0] == 'fnum' or v[0] == 'fnum':
                    is_float = True
                acc += float(c[1]) * float(v[1])
            out.append(('fnum', acc) if is_float else ('num', int(acc)))
        return ('list', out)
    return 'ShapeError'


def value_eq(a, b):
    """≡ 结构相等 → num 1/0；类型不符 TypeError。"""
    if a[0] != b[0]:
        return 'TypeError'
    if a[0] == 'list':
        if len(a[1]) != len(b[1]):
            return ('num', 0)
        for x, y in zip(a[1], b[1]):
            r = value_eq(x, y)
            if isinstance(r, str):
                return r
            if r == ('num', 0):
                return ('num', 0)
        return ('num', 1)
    if a[0] in ('num', 'fnum'):
        return ('num', 1) if a[1] == b[1] else ('num', 0)
    return 'TypeError'


def value_cmp(a, b, op: str):
    """≥ / ≤ 标量比较 → num 1/0；列表 TypeError。"""
    if a[0] == 'list' or b[0] == 'list':
        return 'TypeError'
    if a[0] not in ('num', 'fnum') or b[0] not in ('num', 'fnum'):
        return 'TypeError'
    x, y = float(a[1]), float(b[1])
    if op == 'ge':
        return ('num', 1) if x >= y else ('num', 0)
    return ('num', 1) if x <= y else ('num', 0)


def value_in(a, b):
    """∈ 成员判定 → num 1/0；右端非列表 TypeError。"""
    if b[0] != 'list':
        return 'TypeError'
    for e in b[1]:
        r = value_eq(a, e)
        if isinstance(r, str):
            return r
        if r == ('num', 1):
            return ('num', 1)
    return ('num', 0)


def collect_path(idx):
    if idx[0] == 'num':
        return [idx[1]]
    if idx[0] == 'list':
        out = []
        for it in idx[1]:
            out.extend(collect_path(it))
        return out
    return []


def index_into(target, idx):
    path = collect_path(idx)
    cur = target
    for i in path:
        if cur[0] != 'list':
            return 'TypeError'
        items = cur[1]
        if i >= len(items):
            return 'OutOfBounds'
        cur = items[i]
    return cur


# ── 参考操作语义（§SK / §PF / §IN）────────────────────────────────────────
# 上游把它写成 if-chain；这里改成「有序 (前缀, handler) 表」，顺序与
# verify_consensus.py:702-1259 完全一致，保证三端共识判定不漂移。

def _args1(s: str, name: str) -> Optional[List[str]]:
    """`name(x, y, …)` → 顶层切分后的实参串列表；不是该调用则 None。"""
    if not (s.startswith(name + '(') and s.endswith(')')):
        return None
    inner = s[len(name) + 1:-1]
    parts = split_all_top_level(inner, ',')
    return parts


def _args2(s: str, name: str) -> Optional[List[str]]:
    parts = _args1(s, name)
    if parts is None or len(parts) < 2:
        return None
    return parts


def _args3(s: str, name: str) -> Optional[List[str]]:
    parts = _args1(s, name)
    if parts is None or len(parts) < 3:
        return None
    return parts


def _num(v):
    return isinstance(v, tuple) and v[0] == 'num'


def _listv(v):
    return isinstance(v, tuple) and v[0] == 'list'


def _scalar(v):
    return isinstance(v, tuple) and v[0] in ('num', 'fnum')


def _task_open_row(a, b):
    return ('list', [('num', a), ('num', b), ('num', 0), ('num', 0)])


def _op_task_create(e, args):
    if len(args) < 2:
        return f'bad task_create args: {args}'
    va, vb = e(args[0]), e(args[1])
    if isinstance(va, str):
        return va
    if isinstance(vb, str):
        return vb
    if not _num(va) or not _num(vb):
        return 'TypeError'
    if vb[1] < 0:                     # Bounty : Type ≝ ℕ
        return 'BountyErr'
    return _task_open_row(va[1], vb[1])


def _op_accept_task(e, args):
    if len(args) < 2:
        return f'bad accept_task args: {args}'
    vt, vh = e(args[0]), e(args[1])
    if isinstance(vt, str):
        return vt
    if isinstance(vh, str):
        return vh
    if not _listv(vt) or len(vt[1]) != 4 or not _num(vh):
        return 'TypeError'
    task = vt[1]
    if task[2] != ('num', 0):          # status 0 = open
        return 'StateError'
    return ('list', [task[0], task[1], ('num', 1), ('num', vh[1])])


def _op_task_submit(e, args):
    if not args:
        return 'bad task_submit args'
    vt = e(args[0])
    if isinstance(vt, str):
        return vt
    if not _listv(vt) or len(vt[1]) != 4:
        return 'TypeError'
    task = vt[1]
    if task[2] != ('num', 1):          # status 1 = in_progress
        return 'StateError'
    return ('list', [task[0], task[1], ('num', 2), task[3]])


def _op_task_accept(e, args):
    if len(args) < 2:
        return f'bad task_accept args: {args}'
    vt, vc = e(args[0]), e(args[1])
    if isinstance(vt, str):
        return vt
    if isinstance(vc, str):
        return vc
    if not _listv(vt) or len(vt[1]) != 4 or not _num(vc):
        return 'TypeError'
    task = vt[1]
    if task[2] != ('num', 2):          # status 2 = pending_review
        return 'StateError'
    if vc[1] != task[0][1]:            # INV-4：仅作者可验收
        return 'AuthError'
    return ('list', [task[0], task[1], ('num', 3), task[3]])


def _op_review_merge(e, args):
    v = e(args[0]) if args else 'TypeError'
    if isinstance(v, str):
        return v
    if not _listv(v):
        return 'TypeError'
    w_accept = w_reject = 0
    for o in v[1]:
        if not _listv(o) or len(o[1]) != 3:
            return 'ShapeError'
        vote = o[1][1][1]
        weight = o[1][2][1]
        if vote == 1:
            w_accept += weight
        elif vote == 0:
            w_reject += weight
        else:
            return 'TypeError'
    return ('num', 1 if w_accept >= w_reject else 0)


def _op_contribution_score(e, args):
    v = e(args[0])
    if isinstance(v, str):
        return v
    if not _listv(v):
        return 'TypeError'
    total = 0
    for a in v[1]:
        if not _listv(a) or len(a[1]) != 3:
            return 'ShapeError'
        total += a[1][2][1]
    return ('num', max(0, total))


def _op_credit_score(e, args):
    v = e(args[0])
    if isinstance(v, str):
        return v
    if not _listv(v):
        return 'TypeError'
    credit = 100
    for en in v[1]:
        if not _listv(en) or len(en[1]) != 2:
            return 'ShapeError'
        kind, count = en[1][0][1], en[1][1][1]
        if kind == 0:                  # complete: +5 per count
            credit += 5 * count
        elif kind == 1:                # breach: ×7//10 per count
            for _ in range(count):
                credit = (credit * 7) // 10
        else:
            return 'TypeError'
    return ('num', max(0, credit))


def _op_portfolio_new(e, args):
    vc = e(args[0])
    if isinstance(vc, str):
        return vc
    if not _num(vc):
        return 'TypeError'
    if vc[1] < 0:                      # Cash : Type ≝ ℕ
        return 'TypeError'
    return ('list', [('num', vc[1]), ('num', 0), ('num', 0)])


def _portfolio_trade(e, args, buying: bool):
    name = 'buy' if buying else 'sell'
    if len(args) < 3:
        return f'bad {name} args: {args}'
    vp, va, vq = e(args[0]), e(args[1]), e(args[2])
    for v in (vp, va, vq):
        if isinstance(v, str):
            return v
    if not _listv(vp) or len(vp[1]) != 3 or not _num(va) or not _num(vq):
        return 'TypeError'
    asset, qty = va[1], vq[1]
    if asset not in (0, 1):
        return 'UnknownAsset'
    cash, qA, qB = vp[1]
    if buying:
        if cash[1] < qty:
            return 'InsufficientFunds'
        if asset == 0:
            return ('list', [('num', cash[1] - qty), ('num', qA[1] + qty), qB])
        return ('list', [('num', cash[1] - qty), qA, ('num', qB[1] + qty)])
    held = qA[1] if asset == 0 else qB[1]
    if qty > held:
        return 'InsufficientShares'
    if asset == 0:
        return ('list', [('num', cash[1] + qty), ('num', qA[1] - qty), qB])
    return ('list', [('num', cash[1] + qty), qA, ('num', qB[1] - qty)])


def _op_portfolio_value(e, args):
    vp = e(args[0])
    if isinstance(vp, str):
        return vp
    if not _listv(vp) or len(vp[1]) != 3:
        return 'TypeError'
    cash, qA, qB = vp[1]
    return ('num', cash[1] + qA[1] + qB[1])


def _op_risk_score(e, args):
    vp = e(args[0])
    if isinstance(vp, str):
        return vp
    if not _listv(vp) or len(vp[1]) != 3:
        return 'TypeError'
    _, qA, qB = vp[1]
    return ('num', qA[1] + qB[1])


def _op_quota_new(e, args):
    vm = e(args[0])
    if isinstance(vm, str):
        return vm
    if not _num(vm):
        return 'TypeError'
    if vm[1] < 0:
        return 'TypeError'
    return ('list', [('num', vm[1]), ('num', vm[1])])


def _op_quota_use(e, args):
    if len(args) < 2:
        return f'bad quota_use args: {args}'
    vq, va = e(args[0]), e(args[1])
    if isinstance(vq, str):
        return vq
    if isinstance(va, str):
        return va
    if not _listv(vq) or len(vq[1]) != 2 or not _num(va):
        return 'TypeError'
    monthly, remaining = vq[1]
    if va[1] > remaining[1]:
        return 'QuotaExhausted'
    return ('list', [monthly, ('num', remaining[1] - va[1])])


def _op_quota_reset(e, args):
    vq = e(args[0])
    if isinstance(vq, str):
        return vq
    if not _listv(vq) or len(vq[1]) != 2:
        return 'TypeError'
    monthly, _ = vq[1]
    return ('list', [monthly, monthly])


def _op_quota_advance(e, args):
    vq = e(args[0])
    if isinstance(vq, str):
        return vq
    if not _listv(vq) or len(vq[1]) != 2:
        return 'TypeError'
    monthly, remaining = vq[1]
    if monthly[0] != 'num' or remaining[0] != 'num':
        return 'TypeError'
    return ('list', [monthly, ('num', remaining[1] + monthly[1])])


def _op_points_hold(e, args):
    if len(args) < 2:
        return f'bad points_hold args: {args}'
    vp, vx = e(args[0]), e(args[1])
    if isinstance(vp, str):
        return vp
    if isinstance(vx, str):
        return vx
    if not _listv(vp) or len(vp[1]) != 2 or not _num(vx):
        return 'TypeError'
    escrow, available = vp[1]
    return ('list', [('num', escrow[1] + vx[1]), available])


def _op_points_release(e, args):
    if len(args) < 2:
        return f'bad points_release args: {args}'
    vp, vx = e(args[0]), e(args[1])
    if isinstance(vp, str):
        return vp
    if isinstance(vx, str):
        return vx
    if not _listv(vp) or len(vp[1]) != 2 or not _num(vx):
        return 'TypeError'
    escrow, available = vp[1]
    if vx[1] > escrow[1]:
        return 'InsufficientEscrow'
    return ('list', [('num', escrow[1] - vx[1]), ('num', available[1] + vx[1])])


def _op_points_withdraw(e, args):
    if len(args) < 2:
        return f'bad points_withdraw args: {args}'
    vp, vx = e(args[0]), e(args[1])
    if isinstance(vp, str):
        return vp
    if isinstance(vx, str):
        return vx
    if not _listv(vp) or len(vp[1]) != 2 or not _num(vx):
        return 'TypeError'
    escrow, available = vp[1]
    if vx[1] > available[1]:
        return 'InsufficientPoints'
    return ('list', [escrow, ('num', available[1] - vx[1])])


def _badge_level_of(score: int) -> int:
    if score < 100:
        return 0                       # 铜
    if score < 300:
        return 1                       # 银
    if score < 600:
        return 2                       # 金
    return 3                           # 钻石


def _op_badge_level(e, args):
    vs = e(args[0])
    if isinstance(vs, str):
        return vs
    if not _num(vs):
        return 'TypeError'
    return ('num', _badge_level_of(vs[1]))


def _op_badge_issue(e, args):
    if len(args) < 3:
        return f'bad badge_issue args: {args}'
    vv, vu, vsc = e(args[0]), e(args[1]), e(args[2])
    for v in (vv, vu, vsc):
        if isinstance(v, str):
            return v
    if not _num(vv) or not _num(vu) or not _num(vsc):
        return 'TypeError'
    if vv[1] < 1000:                   # 授权核验师编号段
        return 'AuthError'
    return ('list', [('num', vv[1]), ('num', vu[1]), ('num', _badge_level_of(vsc[1]))])


def _op_dispute_review(e, args):
    v = e(args[0])
    if isinstance(v, str):
        return v
    if not _listv(v):
        return 'TypeError'
    w_support = w_reject = 0
    for en in v[1]:
        if not _listv(en) or len(en[1]) != 3:
            return 'ShapeError'
        side, weight = en[1][1][1], en[1][2][1]
        if side == 1:
            w_support += weight
        elif side == 0:
            w_reject += weight
        else:
            return 'TypeError'
    return ('num', 1 if w_support >= w_reject else 0)


def _op_team_create(e, args):
    if len(args) < 3:
        return f'bad team_create args: {args}'
    vo, vk, vc = e(args[0]), e(args[1]), e(args[2])
    for v in (vo, vk, vc):
        if isinstance(v, str):
            return v
    if not _num(vo) or not _num(vk) or not _num(vc):
        return 'TypeError'
    if vc[1] < 1:
        return 'TypeError'
    return ('list', [('num', vo[1]), ('num', vk[1]), ('num', 1), ('num', vc[1])])


def _op_team_join(e, args):
    if len(args) < 2:
        return f'bad team_join args: {args}'
    vt, vm = e(args[0]), e(args[1])
    if isinstance(vt, str):
        return vt
    if isinstance(vm, str):
        return vm
    if not _listv(vt) or len(vt[1]) != 4 or not _num(vm):
        return 'TypeError'
    owner, kind, size, capacity = vt[1]
    if size[1] >= capacity[1]:
        return 'TeamFull'
    return ('list', [owner, kind, ('num', size[1] + 1), capacity])


def _op_team_share(e, args):
    if len(args) < 2:
        return f'bad team_share args: {args}'
    vc, vr = e(args[0]), e(args[1])
    if isinstance(vc, str):
        return vc
    if isinstance(vr, str):
        return vr
    if not _listv(vc) or not _num(vr):
        return 'TypeError'
    total = 0
    for entry in vc[1]:
        if not _listv(entry) or len(entry[1]) != 2:
            return 'ShapeError'
        total += entry[1][1][1]
    if total == 0:
        return 'DivByZero'
    shares = []
    for entry in vc[1]:
        m, c = entry[1][0], entry[1][1][1]
        shares.append(('list', [m, ('num', (vr[1] * c) // total)]))
    return ('list', shares)


def _op_points_ledger(e, args):
    v = e(args[0])
    if isinstance(v, str):
        return v
    if not _listv(v):
        return 'TypeError'
    ledger = []
    for i, entry in enumerate(v[1], 1):
        if not _listv(entry) or len(entry[1]) != 3:
            return 'ShapeError'
        kind, amount, source = entry[1]
        if kind[0] != 'num' or amount[0] != 'num' or source[0] != 'num':
            return 'TypeError'
        if source[1] < 1:
            return 'NotTraceable'
        if amount[1] < 0:
            return 'TypeError'
        ledger.append(('list', [('num', i), source, amount]))
    return ('list', ledger)


def _op_inventory_new(e, args):
    if len(args) < 2:
        return f'bad inventory_new args: {args}'
    va, vb = e(args[0]), e(args[1])
    if isinstance(va, str):
        return va
    if isinstance(vb, str):
        return vb
    if not _num(va) or not _num(vb):
        return 'TypeError'
    if va[1] < 0 or vb[1] < 0:
        return 'TypeError'
    return ('list', [('num', va[1]), ('num', vb[1])])


def _stock_change(e, args, receiving: bool):
    name = 'receive_stock' if receiving else 'ship_stock'
    if len(args) < 3:
        return f'bad {name} args: {args}'
    vi, vx, vq = e(args[0]), e(args[1]), e(args[2])
    for v in (vi, vx, vq):
        if isinstance(v, str):
            return v
    if not _listv(vi) or len(vi[1]) != 2 or not _num(vx) or not _num(vq):
        return 'TypeError'
    if vx[1] not in (0, 1):
        return 'UnknownItem'
    if vq[1] < 0:
        return 'TypeError'
    inv = list(vi[1])
    held = inv[vx[1]][1]
    if receiving:
        inv[vx[1]] = ('num', held + vq[1])
        return ('list', inv)
    if vq[1] > held:
        return 'InsufficientStock'
    inv[vx[1]] = ('num', held - vq[1])
    return ('list', inv)


def _op_stock_level(e, args):
    if len(args) < 2:
        return f'bad stock_level args: {args}'
    vi, vx = e(args[0]), e(args[1])
    if isinstance(vi, str):
        return vi
    if isinstance(vx, str):
        return vx
    if not _listv(vi) or len(vi[1]) != 2 or not _num(vx):
        return 'TypeError'
    if vx[1] not in (0, 1):
        return 'TypeError'
    return vi[1][vx[1]]


def _op_fill_rate(e, args):
    if len(args) < 2:
        return f'bad fill_rate args: {args}'
    vs, vd = e(args[0]), e(args[1])
    if isinstance(vs, str):
        return vs
    if isinstance(vd, str):
        return vd
    if not _num(vs) or not _num(vd):
        return 'TypeError'
    if vd[1] == 0:
        return 'DivByZero'
    return ('fnum', vs[1] / vd[1])


#: 每个参考操作的最少实参数目（与上游 `len(parts) < N` 判定逐条对应）。
#: 未列出的单参操作沿用上游写法：整体作为一条表达式求值，不切分。
_REF_MIN_ARGS: Dict[str, int] = {
    'index': 2, 'task_create': 2, 'accept_task': 2, 'task_accept': 2,
    'quota_use': 2, 'points_hold': 2, 'points_release': 2, 'points_withdraw': 2,
    'team_join': 2, 'team_share': 2, 'inventory_new': 2, 'stock_level': 2,
    'fill_rate': 2, 'buy': 3, 'sell': 3, 'team_create': 3, 'badge_issue': 3,
    'receive_stock': 3, 'ship_stock': 3,
}

#: 有序参考操作表 —— **顺序即语义**，与上游 if-chain 一一对应。
REFERENCE_OPS: Tuple[Tuple[str, Callable[[Callable, List[str]], Any]], ...] = (
    ('index', lambda e, a: (index_into(e(a[0]), parse_val(a[1]))
                            if parse_val(a[1]) is not None
                            else f'bad index: {a[1]}')),
    ('task_create', _op_task_create),
    ('accept_task', _op_accept_task),
    ('task_submit', _op_task_submit),
    ('task_accept', _op_task_accept),
    ('review_merge', _op_review_merge),
    ('contribution_score', _op_contribution_score),
    ('credit_score', _op_credit_score),
    ('portfolio_new', _op_portfolio_new),
    ('buy', lambda e, a: _portfolio_trade(e, a, True)),
    ('sell', lambda e, a: _portfolio_trade(e, a, False)),
    ('portfolio_value', _op_portfolio_value),
    ('risk_score', _op_risk_score),
    ('quota_new', _op_quota_new),
    ('quota_use', _op_quota_use),
    ('quota_reset', _op_quota_reset),
    ('points_hold', _op_points_hold),
    ('points_release', _op_points_release),
    ('points_withdraw', _op_points_withdraw),
    ('badge_level', _op_badge_level),
    ('badge_issue', _op_badge_issue),
    ('dispute_review', _op_dispute_review),
    ('team_create', _op_team_create),
    ('team_join', _op_team_join),
    ('team_share', _op_team_share),
    ('quota_advance', _op_quota_advance),
    ('points_ledger', _op_points_ledger),
    ('inventory_new', _op_inventory_new),
    ('receive_stock', lambda e, a: _stock_change(e, a, True)),
    ('ship_stock', lambda e, a: _stock_change(e, a, False)),
    ('stock_level', _op_stock_level),
    ('fill_rate', _op_fill_rate),
)

#: 运算符切分顺序（上游 ⊕ ⊗ ⊖ ⊘ ⊙ ≡ ≥ ≤ ∈ 的 if-chain 顺序，右结合）。
_OPERATOR_ORDER: Tuple[Tuple[str, Callable[[Any, Any], Any]], ...] = (
    ('⊕', elemwise_add),
    ('⊗', mat_mul),
    ('⊖', elemwise_sub),
    ('⊘', elemwise_div),
    ('⊙', elemwise_mul),
    ('≡', value_eq),
    ('≥', lambda a, b: value_cmp(a, b, 'ge')),
    ('≤', lambda a, b: value_cmp(a, b, 'le')),
    ('∈', value_in),
)


def eval_expr(s: str) -> Any:
    """求值一条规约表达式：字面量 / 运算符 / index(...) / 参考操作 / I₂ / 常量。

    返回 (kind, value) 值元组；出错时返回错误名字符串（'ShapeError' 等），
    与上游 Rust/Elixir 的 `Err(...)` 语义一致。
    """
    s = s.strip()
    if s in CONSTANTS:
        return CONSTANTS[s]
    if s == 'I₂':
        return ('list', [('list', [('num', 1), ('num', 0)]),
                         ('list', [('num', 0), ('num', 1)])])
    if s == 'points_new()':
        return ('list', [('num', 0), ('num', 0)])
    if 'where shape mismatch' in s:
        return 'ShapeError'

    for glyph, fn in _OPERATOR_ORDER:
        if glyph in s:
            a, b = s.split(glyph, 1)
            va, vb = eval_expr(a), eval_expr(b)
            if isinstance(va, str):
                return va
            if isinstance(vb, str):
                return vb
            return fn(va, vb)

    for name, handler in REFERENCE_OPS:
        head = name + '('
        if s.startswith(head) and s.endswith(')'):
            inner = s[len(head):-1]
            min_args = _REF_MIN_ARGS.get(name, 1)
            if min_args == 1:
                # 上游对单参操作直接整体求值（不切分），保持一致
                return handler(eval_expr, [inner.strip()])
            parts = split_all_top_level(inner, ',')
            if len(parts) < min_args:
                return f'bad {name} args: {inner}'
            return handler(eval_expr, [p.strip() for p in parts])

    v = parse_val(s)
    if v is None:
        # 非法字面量（如 "+5"、"1e3"）→ 错误串，与 Rust/Elixir 同形（M-4 literal grammar）
        return f'unparseable: {s}'
    return v


def eval_test(input_expr: str, expected: str) -> Optional[str]:
    """跑一条规范测试。通过返回 None，失败返回差异描述。"""
    expect_err = expected.strip().startswith('⊥')
    v = eval_expr(input_expr)
    if isinstance(v, str):                     # 求值期错误
        if expect_err:
            want = expected.strip()[1:].strip()
            if not want or want.split()[0] == v or v.endswith(want):
                return None
            return f'expected error {want}, got {v}'
        return f'evaluation failed: {v}'
    if expect_err:
        return f'expected error, got {fmt_val(v)}'
    ev = parse_val(expected)
    if ev is None:
        return f'unparseable expectation: {expected}'
    if ev == v:
        return None
    return f'expected {fmt_val(ev)}, got {fmt_val(v)}'


def eval_compat_test(inp: str, exp: str) -> Any:
    """上游兼容测试入口的等价物：True 通过，否则失败描述串。"""
    detail = eval_test(inp, exp)
    return True if detail is None else detail


# ---------------------------------------------------------------------------
# 3. Sigma-Markdown 解析（移植 verify_consensus.py:42-347，逐字对齐语法）
# ---------------------------------------------------------------------------

_SECTION_HEADINGS = (
    '## Imports', '## Exports', '## Compat Tests', '## Proof', '## Guarantee',
    '## Determinism', '## Signature', '## Shadowing', '## Timing', '## Capabilities',
)


def _new_module(name: str = 'parsed_module') -> Dict[str, Any]:
    return {
        'name': name, 'version': '0.1.0', 'expected': None,
        'imports': [], 'exports': [], 'compat_tests': [], 'ops': [], 'fns': [],
        'proof_declared': False, 'proof_has_model': False, 'proof_has_invariant': False,
        'guarantee_declared': False, 'guarantee_metric': None,
        'guarantee_threshold': None, 'guarantee_dataset': None,
        'determinism_declared': False, 'determinism_precision': None,
        'determinism_rounding': None, 'determinism_sort_stability': None,
        'signature_declared': False, 'signature_signer': None,
        'signature_pubkey_fp': None, 'signature_algorithm': None,
        'signature_value': None, 'shadow_targets': [],
        'timing_contract': None, 'capabilities': [],
        'package': None,
    }


def parse_module_text(text: str) -> Dict[str, Any]:
    """解析一段 Sigma 规约文本（整份 .md 模块即源码）。

    语法（与 Rust `parse_sigma_module` / Elixir `sigma_verify.exs` 同一契约）：
      * 前言 `# Module:` / `# Version:` / `# Expected: PASS|FAIL`
      * 章节 `## Imports|Exports|Compat Tests|Proof|Guarantee|Determinism|
              Signature|Shadowing|Timing|Capabilities`
      * 操作 `## Operation: <name> (…)`，子节 `### Signature|Laws|Tests|Definition`
      * `Fingerprint: 0xA001`、`# Pre:` / `# Post:`
      * 定律行 = 含 `∀`/`∃`/`≡` 且不含 `|` 的行；测试行 = `| Input | Output |`
      * 期望值以 `⊥` 开头表示负向/错误用例
    """
    lines = [l.rstrip('\n') for l in text.splitlines()]

    module = _new_module()
    in_imports = in_exports = in_compat_tests = False
    in_proof = in_guarantee = in_determinism = False
    in_signature = in_shadowing = in_timing = in_capabilities = False
    in_definition = False
    in_fence = False
    blk: Optional[Dict[str, Any]] = None

    def close_section():
        nonlocal in_imports, in_exports, in_compat_tests, in_proof, in_guarantee
        nonlocal in_determinism, in_signature, in_shadowing, in_timing
        nonlocal in_capabilities, in_definition
        in_imports = in_exports = in_compat_tests = False
        in_proof = in_guarantee = in_determinism = False
        in_signature = in_shadowing = in_timing = in_capabilities = False
        in_definition = False

    def flush():
        # 与 Rust flush_block 同语义：有指纹 → op；无指纹但有签名 → 声明函数（编码）；
        # 两者皆无 → 丢弃。
        #
        # 审计修复（Law I 可达性）：改前只要没有 Fingerprint 就一律降级成 `fns`
        # 声明 —— 于是一个**漏写 Fingerprint 的 Operation** 会从 ops 里静默消失，
        # Law I 的 `MissingFingerprint` 分支永远走不到（实测只能手工构造 module
        # 才能触发），而且"零操作"规约还会因此真空通过所有定律。
        # 现在：带测试/定律/定义的签名块视为**显式 Operation**，保留为 op 并置
        # fp=None，让 Law I 如实报 `MissingFingerprint`；只有"纯签名"块才当声明函数
        # （Law II 的 encoder 声明依赖这条路径）。
        nonlocal blk
        if blk is not None:
            if blk['fp'] is not None:
                module['ops'].append(blk)
            elif blk['sig'] and (blk['tests'] or blk['laws'] or blk['definition']):
                module['ops'].append(blk)
            elif blk['sig']:
                module['fns'].append(blk)
            blk = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        m = re.match(r'^# Module:\s*(.+)$', line)
        if m:
            module['name'] = m.group(1).strip()
            continue
        m = re.match(r'^# Version:\s*(.+)$', line)
        if m:
            module['version'] = m.group(1).strip()
            continue
        m = re.match(r'^# Expected:\s*(.+)$', line)
        if m:
            module['expected'] = m.group(1).strip()
            continue
        # L1/L2 包前言（std/*.md 与 tools/sigma-cli.py:47-55 HEADER_FIELDS 同构）
        for key, field in (('Package', 'package'),):
            m = re.match(rf'^# {key}:\s*(.+)$', line)
            if m:
                module[field] = m.group(1).strip()
                break
        else:
            for key in ('Style', 'Domain', 'Intent', 'Depends', 'Fingerprint Prefix',
                        'Maintainer', 'License'):
                if re.match(rf'^# {re.escape(key)}:', line):
                    break
            else:
                pass

        matched_heading = None
        for h in _SECTION_HEADINGS:
            if line == h:
                matched_heading = h
                break

        if matched_heading is not None:
            close_section()
            if matched_heading == '## Imports':
                in_imports = True
            elif matched_heading == '## Exports':
                in_exports = True
            elif matched_heading == '## Compat Tests':
                in_compat_tests = True
            elif matched_heading == '## Proof':
                in_proof = True
                module['proof_declared'] = True
            elif matched_heading == '## Guarantee':
                in_guarantee = True
                module['guarantee_declared'] = True
            elif matched_heading == '## Determinism':
                in_determinism = True
                module['determinism_declared'] = True
            elif matched_heading == '## Signature':
                in_signature = True
                module['signature_declared'] = True
            elif matched_heading == '## Shadowing':
                in_shadowing = True
            elif matched_heading == '## Timing':
                in_timing = True
            elif matched_heading == '## Capabilities':
                in_capabilities = True
            elif matched_heading in ('## Implementation', '## Definition'):
                in_definition = True
            continue

        if line.startswith('```'):
            in_fence = not in_fence
            continue

        # 章节退出语义与上游一致：遇到任何标题就关掉当前章节标志并**继续往下处理**
        # （上游 verify_consensus.py:182-253 的 fall-through）。若只在精确匹配的章节名
        # 上复位，`## Operation:` 之后的签名/指纹行会被上一个章节处理器吞掉。
        is_heading = line.startswith('## ') or line.startswith('### ')
        if in_timing:
            if is_heading:
                in_timing = False
            else:
                m = re.match(r'^(max_latency|max_retries|timeout_budget|deadline_miss_policy):\s*(.*)$', line)
                if m:
                    if module['timing_contract'] is None:
                        module['timing_contract'] = {}
                    module['timing_contract'][m.group(1)] = m.group(2).strip()
                continue
        if in_capabilities:
            if is_heading:
                in_capabilities = False
            else:
                for token in line.split(','):
                    t = token.strip()
                    if t and t != '```' and t not in module['capabilities']:
                        module['capabilities'].append(t)
                continue
        if in_shadowing:
            if is_heading:
                in_shadowing = False
            else:
                m = re.match(r'^shadow\s+(\S+)', line)
                if m:
                    target = m.group(1).split('→')[0].strip()
                    if target:
                        module['shadow_targets'].append(target)
                continue
        if in_signature:
            if is_heading:
                in_signature = False
            else:
                m = re.match(r'^(signer|pubkey_fp|algorithm|signature):\s*(.*)$', line)
                if m:
                    key = 'value' if m.group(1) == 'signature' else m.group(1)
                    module[f'signature_{key}'] = m.group(2).strip()
                continue
        if in_determinism:
            if is_heading:
                in_determinism = False
            else:
                m = re.match(r'^(precision|rounding|sort_stability):\s*(.*)$', line)
                if m:
                    module[f'determinism_{m.group(1)}'] = m.group(2).strip()
                continue
        if in_guarantee:
            if is_heading:
                in_guarantee = False
            else:
                m = re.match(r'^(metric|threshold|dataset):\s*(.*)$', line)
                if m:
                    module[f'guarantee_{m.group(1)}'] = m.group(2).strip()
                continue
        if in_proof:
            if is_heading:
                if line == '### Model':
                    module['proof_has_model'] = True
                    continue
                if line == '### Invariant':
                    module['proof_has_invariant'] = True
                    continue
                if line == '### Trusted':
                    continue
                in_proof = False          # 其它标题退出 proof，落到下面继续处理
            else:
                continue
        if in_compat_tests:
            if not in_fence and is_heading:
                in_compat_tests = False   # 新标题结束兼容测试节，落到下面继续处理
            elif line.startswith('|'):
                if line.startswith('|-') or 'Input' in line or 'Output' in line or 'Expected' in line:
                    continue
                cells = [c.strip() for c in line.strip('|').split('|')]
                if len(cells) >= 2:
                    module['compat_tests'].append((cells[0], cells[1]))
                continue
            else:
                continue
        if in_definition:
            if is_heading:
                in_definition = False
            elif blk is not None:
                blk.setdefault('definition', []).append(line)
                continue
            else:
                continue
        if in_exports:
            if not is_heading:
                for tok in re.split(r'[,\s]+', line):
                    t = tok.strip()
                    if t and t != '```':
                        module['exports'].append(t)
                continue
            in_exports = False
        if in_imports:
            m = re.match(r'^import\s+(\S+)', line)
            if m:
                module['imports'].append(m.group(1).strip().rstrip(','))
                continue
            in_imports = False            # 非 import 行：落到下面重新处理

        # 围栏外的 Markdown 标题即块边界
        if not in_fence and (line.startswith('## ') or line.startswith('### ')):
            if line in ('### Signature', '### Laws', '## Laws', '### Tests', '## Tests',
                        '### Definition', '## Definition'):
                if blk is not None:
                    if 'Laws' in line:
                        blk['mode'] = 'laws'
                    elif 'Tests' in line:
                        blk['mode'] = 'tests'
                    elif 'Definition' in line:
                        blk['mode'] = 'definition'
                    else:
                        blk['mode'] = 'sig'
                continue
            flush()
            heading = line.lstrip('#').strip()
            heading = re.sub(r'^Operation:\s*', '', heading).strip()
            blk = {'name': heading, 'sig': '', 'fp': None, 'laws': [], 'tests': [],
                   'mode': 'sig', 'has_pre': False, 'has_post': False,
                   'pre': None, 'post': None, 'definition': []}
            continue

        if in_fence and line in ('## Laws', '## Tests', '## Definition'):
            if blk is not None:
                blk['mode'] = ('laws' if 'Laws' in line
                               else 'tests' if 'Tests' in line else 'definition')
            continue

        if blk is None:
            continue

        m = re.match(r'^Fingerprint:\s*(.+)$', line)
        if m:
            blk['fp'] = m.group(1).strip()
            continue
        if line.startswith('# Pre:'):
            blk['has_pre'] = True
            blk['pre'] = line[len('# Pre:'):].strip()
            continue
        if line.startswith('# Post:'):
            blk['has_post'] = True
            blk['post'] = line[len('# Post:'):].strip()
            continue
        if blk['mode'] == 'definition':
            blk['definition'].append(line)
            continue
        if blk['mode'] == 'tests' and line.startswith('|'):
            if line.startswith('|-') or 'Input' in line or 'Output' in line or 'Expected' in line:
                continue
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) >= 2:
                blk['tests'].append((cells[0], cells[1]))
            continue
        # 签名检测必须先于 `≡` 定律启发式：`≡ : ℕ × ℕ → ℕ` 这类符号名本身含 ≡。
        if not blk['sig'] and ':' in line and '→' in line and not line.startswith('|'):
            blk['sig'] = line
            name = line.split(':', 1)[0].strip()
            if name and not re.search(r'\s', name):
                blk['name'] = name
            continue
        if blk['mode'] == 'laws' or line.startswith(('∀', '∃')) or '≡' in line:
            if '|' not in line:
                blk['laws'].append(line)
            continue

    flush()
    return module


def parse_module(path: str) -> Dict[str, Any]:
    """从文件解析 Sigma MD 模块。"""
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError as exc:
        raise SpecError(f'无法读取规约文件 {path}: {exc}') from exc
    return parse_module_text(text)


def _scan_fenced(text: str, greedy: bool) -> str:
    """按围栏扫描取第一个 sigma 块正文；greedy=True 时取到最后一个裸围栏。"""
    lines = (text or '').splitlines()
    fence_re = re.compile(r'^(\s*)(`{3,}|~{3,})\s*(\S*)')
    start = open_marker = None
    closes = []
    for i, line in enumerate(lines):
        m = fence_re.match(line)
        if not m:
            continue
        marker, lang = m.group(2), m.group(3).lower()
        if start is None:
            if lang in SIGMA_LANGUAGE_TAGS:
                start, open_marker = i, marker
            continue
        if lang == '' and marker[0] == open_marker[0] and len(marker) >= len(open_marker):
            closes.append(i)
    if start is None:
        return ''
    if not closes:
        return '\n'.join(lines[start + 1:])            # 未闭合：交给调用方如实报错
    end = closes[-1] if greedy else closes[0]
    return '\n'.join(lines[start + 1:end])


def extract_sigma_block(text: str) -> str:
    """从动作 Markdown 里抽出第一个 ```sigma 块的正文（docs/41 §A1）。

    **围栏感知**：规约块内部常嵌 ` ```md ` 子围栏（## Imports/Exports 的写法）。
    CommonMark 语义下内层裸 ``` 会提前闭合外层，导致规约被截断，因此这里先按
    标准语义取最短块；若那段文本里一个操作都解析不出来，再退回取到最后一个
    裸围栏（把内层 ```md 当作块内内容）。两种取法都失败时返回**第一次**的结果，
    让调用方拿到真实错误，绝不静默当空规约通过。
    """
    strict = _scan_fenced(text, greedy=False)
    if strict.strip() and _has_content(strict):
        return strict
    wide = _scan_fenced(text, greedy=True)
    if wide.strip() and _has_content(wide):
        return wide
    return strict or wide


def _has_content(body: str) -> bool:
    try:
        m = parse_module_text(body)
    except Exception:                                  # noqa: BLE001 —— 交给上层报错
        return False
    return bool(m['ops'] or m['fns'])


#: L2 包前言字段（tools/sigma-cli.py:47-55）
PACKAGE_HEADER_FIELDS = ('Package', 'Version', 'Depends', 'Fingerprint Prefix',
                         'Domain', 'Maintainer', 'License')


def parse_package(path: str) -> Optional[Dict[str, Any]]:
    """解析 `# Package:` 前言（L1/L2 包格式）。无前言返回 None。"""
    if not os.path.isfile(path):
        return None
    meta: Dict[str, Any] = {}
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if line and not line.startswith('# '):
                break
            m = re.match(r'^#\s*(.+?):\s*(.+)$', line)
            if m and m.group(1) in PACKAGE_HEADER_FIELDS:
                meta[m.group(1).lower().replace(' ', '_')] = m.group(2).strip()
    return meta or None


def return_type(sig: str) -> str:
    """语义类 = 最后一个 → 之后的类型（verify_consensus.py:354）。"""
    if not sig:
        return 'Any'
    return sig.split('→')[-1].strip()


def param_types(sig: str) -> List[str]:
    """从 `name : A × B → C` 提取入参类型列表。"""
    if ':' not in sig:
        return []
    right = sig.split(':', 1)[1]
    left = right.split('→')[0] if '→' in right else right
    return [p.strip() for p in re.split(r'[×,]', left) if p.strip()]


# ---------------------------------------------------------------------------
# 4. Iron Laws 校验（17 条 + 补充细则）
#
#    可机检的严格判；需要跨端共识（Law XIII）或外部语料的，显式标 advisory，
#    绝不当作通过。违规名沿用 sigma-lang 的 `Kind(args)` 形态，三端可比对。
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: Dict[str, Callable[[Dict[str, Any]], List[str]]] = {}


def _law(fn: Callable[[Dict[str, Any]], List[str]]) -> Callable:
    _CHECK_REGISTRY[fn.__name__] = fn
    return fn


@_law
def check_fingerprint_uniqueness(module: Dict[str, Any]) -> List[str]:
    """Law I — 指纹唯一性。"""
    out, seen = [], set()
    for op in module['ops']:
        if op['fp'] is None:
            out.append(f"MissingFingerprint({op['name']})")
            continue
        if op['fp'] in seen:
            out.append(f"FingerprintConflict({op['name']}, {op['fp']})")
        seen.add(op['fp'])
    return out


@_law
def check_encoding(module: Dict[str, Any]) -> List[str]:
    """Law II — 非数值返回类型必须声明到 ℕ 的编码。

    判定口径（审计修正）：改前只做子串匹配（函数名含 'encode' + 返回类型串
    出现在签名里），**声明一个空壳 encoder**（无指纹、无定义）就能满足
    `f: ℕ → Str` 的编码要求 —— 实测如此。
    现在要求：
      1. encoder 必须是**真正存在的东西**（有指纹的 op，或有定义的 fn），
         纯签名声明不算（否则"声明即通过"）；
      2. encoder 的签名必须**结构化对应**：返回类型是数值（编码到 ℕ），
         且某个参数类型 == 待编码操作的返回类型。
    """
    encoders = []
    for blk in list(module.get('fns') or []) + list(module.get('ops') or []):
        if 'encode' not in (blk.get('name') or '').lower():
            continue
        if not blk.get('sig'):
            continue
        if blk.get('fp') is None and not (blk.get('definition') or []):
            continue                     # 空壳声明不算数
        encoders.append(blk['sig'])
    out = []
    for op in module['ops']:
        rt = return_type(op['sig'])
        if rt in NUMERIC_TYPES:
            continue
        if not any(_signature_encodes(sig, rt) for sig in encoders):
            out.append(f"MissingEncoding({op['name']})")
    return out


def _signature_encodes(sig: str, target_type: str) -> bool:
    """该签名是否是 target_type → ℕ 的编码：返回数值 && 某参数类型是 target_type。"""
    if not sig:
        return False
    if return_type(sig) not in NUMERIC_TYPES:
        return False
    return any(p == target_type for p in param_types(sig))


@_law
def check_law_declaration(module: Dict[str, Any]) -> List[str]:
    """Law III — 每个操作都必须声明定律。"""
    return [f"NoLawsDeclared({op['name']})" for op in module['ops'] if not op['laws']]


@_law
def check_tests_mandatory(module: Dict[str, Any]) -> List[str]:
    """Law IV — 每个操作至少 1 条规范测试。"""
    return [f"NoTestsDefined({op['name']})" for op in module['ops'] if not op['tests']]


@_law
def check_no_implementation(module: Dict[str, Any]) -> List[str]:
    """Law V — 规范中不得含实现（移植 main.rs:813 的关键字黑名单）。"""
    forbidden = ('algorithm', 'for loop', 'while loop', 'malloc', 'free')
    out = []
    for op in module['ops']:
        body = ' '.join(op.get('definition') or [])
        low = body.lower()
        for kw in forbidden:
            if kw in low:
                out.append(f"ImplementationLeak({op['name']})")
                break
    return out


_SEMVER_RE = re.compile(r'^\d+\.\d+\.\d+$')


@_law
def check_backward_compat(module: Dict[str, Any]) -> List[str]:
    """Law VI — 已发布即冻结；这里校验版本形态（main.rs:728 semver-only 口径）。"""
    v = (module.get('version') or '').strip()
    if not _SEMVER_RE.match(v):
        return [f'MalformedVersion({module.get("version")})']
    return []


@_law
def check_dependencies(module: Dict[str, Any]) -> List[str]:
    """Law VII — 显式依赖且无环（tools/sigma-cli.py:153 check_acyclic 的等价物）。"""
    out = []
    imports = module['imports']
    if 'core' not in imports:
        out.append(f'NoCoreImport({module["name"]})')
    self_name = module['name']
    if self_name in imports:
        out.append(f'SelfDependency({self_name})')
    seen: set = set()
    dup = [i for i in imports if i in seen or seen.add(i)]
    for d in set(dup):
        out.append(f'DuplicateImport({d})')
    return out


_IO_MARKERS = ('print', 'read_file', 'http_', 'send', 'recv', 'write_file', 'connect')
_ASYNC_HINTS = ('IO', 'Comm', 'Net', 'FS')


@_law
def check_timing_contract(module: Dict[str, Any]) -> List[str]:
    """Law VIII — 有异步/IO 效应必须声明时序契约（main.rs:842）。"""
    bodies = ' '.join(' '.join(op.get('definition') or []) for op in module['ops'])
    has_async = any(mk in bodies for mk in _IO_MARKERS)
    if has_async and module.get('timing_contract') is None:
        return [f'NoTimingContract({module["name"]})']
    return []


@_law
def check_calibration(module: Dict[str, Any]) -> List[str]:
    """Law IX — Conf 型操作必须在定律里锚定 0/1（main.rs:744）。

    判定口径（审计修正）：必须是**独立的 0 / 1 字面量**，不是任意子串。
    改前用 `'0' not in laws and '1' not in laws` —— 定律行里写 `# 见 RFC 1.0`
    就能同时含 0/1 而通过（实测 Conf 型操作零校准锚点也判 pass）。
    """
    out = []
    for op in module['ops']:
        if 'Conf' not in return_type(op['sig']):
            continue
        laws = ' '.join(op['laws'])
        if not _CALIBRATION_ANCHOR_RE.search(laws):
            out.append(f"Uncalibrated({op['name']})")
    return out


# 独立的 0 或 1 字面量：前后不能紧邻数字或小数点（排除 "1.0" / "10" / "0.5"）。
_CALIBRATION_ANCHOR_RE = re.compile(r'(?<![\d.])[01](?![\d.])')


@_law
def check_effect_transparency(module: Dict[str, Any]) -> List[str]:
    """Law X — 效应必须显式声明（main.rs:853）。"""
    declared = ' '.join(module.get('capabilities') or []) + ' ' + json.dumps(
        module.get('timing_contract') or {}, ensure_ascii=False)
    declared_io = any(h in declared for h in _ASYNC_HINTS) or any(
        k in declared.lower() for k in ('io', 'net', 'fs', 'comm'))
    out = []
    for op in module['ops']:
        body = ' '.join(op.get('definition') or [])
        if any(mk in body for mk in _IO_MARKERS) and not declared_io:
            out.append(f"UndeclaredEffect({op['name']}, IO)")
    return out


_CAPABILITY_MARKERS = (
    ('ReadFile', ('read_file', 'readln')),
    ('WriteFile', ('write_file', 'append_file')),
    ('Network', ('http_', 'connect', 'send', 'recv')),
    ('CmdExec', ('exec', 'system(')),
    ('SpawnAgent', ('spawn',)),
)


@_law
def check_capabilities(module: Dict[str, Any]) -> List[str]:
    """Law XI — FFI/能力使用必须显式声明（main.rs:884 marker 表逐字移植）。"""
    caps = set(module.get('capabilities') or [])
    out = []
    for op in module['ops']:
        body = ' '.join(op.get('definition') or [])
        for cap, needles in _CAPABILITY_MARKERS:
            if any(n in body for n in needles) and cap not in caps:
                out.append(f"MissingCapability({op['name']}, {cap})")
    return out


_CALL_RE = re.compile(r'\b(open|close|use)\s*\(\s*([^)]*?)\s*\)')


@_law
def check_resource_linearity(module: Dict[str, Any]) -> List[str]:
    """Law XII — open 恰好 close 一次（main.rs:907：泄漏 / 双关 / 关后用）。"""
    out = []
    for op in module['ops']:
        body = ' '.join(op.get('definition') or [])
        if not body:
            continue
        opens: Dict[str, int] = {}
        closes: Dict[str, int] = {}
        for kind, res in _CALL_RE.findall(body):
            if kind == 'open':
                opens[res] = opens.get(res, 0) + 1
            elif kind == 'close':
                closes[res] = closes.get(res, 0) + 1
        for r, oc in opens.items():
            if oc > closes.get(r, 0):
                out.append(f"ResourceLeak({op['name']}:{r})")
        for r, cc in closes.items():
            if cc > opens.get(r, 0):
                out.append(f"DoubleClose({op['name']}:{r})")
        for m in re.finditer(r'\buse\s*\(\s*([^)]*?)\s*\)', body):
            r = m.group(1)
            cp = re.search(r'\bclose\s*\(\s*' + re.escape(r) + r'\s*\)', body)
            if cp and cp.start() < m.start():
                out.append(f"UseAfterClose({op['name']}:{r})")
    return out


@_law
def check_consensus(module: Dict[str, Any]) -> List[str]:
    """Law XIII — 验证器共识。

    三端独立验证器（Rust/Elixir/Python）不在本机常驻，单端无法判定共识成立与否，
    因此本条在 actus 侧记为 **advisory**（不判失败、也不谎报通过）。
    真实共识需由 sigma-cli 形态的外部验证器完成（docs/41 §A2：不纳入运行时依赖）。
    """
    return []


@_law
def check_negative_tests(module: Dict[str, Any]) -> List[str]:
    """Law XIV — 每个操作至少一条 ⊥ 负向测试。"""
    out = []
    for op in module['ops']:
        if not any(exp.strip().startswith('⊥') for _, exp in op['tests']):
            out.append(f"NoNegativeTest({op['name']})")
    return out


@_law
def check_export_completeness(module: Dict[str, Any]) -> List[str]:
    """Law XV — Exports 与定义符号一一对应（无幽灵、无隐藏）。"""
    exports = module['exports']
    if not exports:
        return []                    # 无 Exports 块不检查（v0.1 政策，与上游一致）
    defined = {op['name'] for op in module['ops']}
    out = [f'GhostExport({e})' for e in exports if e not in defined]
    out += [f"HiddenExport({op['name']})" for op in module['ops'] if op['name'] not in exports]
    return out


@_law
def check_compat_proof(module: Dict[str, Any]) -> List[str]:
    """Law XVI — `## Compat Tests` 全过，否则驳回「向后兼容」声明。"""
    out = []
    for inp, exp in module['compat_tests']:
        result = eval_compat_test(inp, exp)
        if result is not True:
            out.append(f'CompatTestFailed({inp}): {result}')
    return out


@_law
def check_guarantee(module: Dict[str, Any]) -> List[str]:
    """Law XVII — 概率保证声明必须齐备且良构。"""
    if not module['guarantee_declared']:
        return []
    out = []
    metric = module.get('guarantee_metric') or ''
    if metric not in ('accuracy', 'f1', 'brier'):
        out.append(f'MalformedGuarantee(invalid metric: {metric!r})')
    try:
        thr = float(module.get('guarantee_threshold') or '')
        if not (0.0 <= thr <= 1.0):
            out.append('MalformedGuarantee(threshold out of range 0..=1)')
    except ValueError:
        out.append('MalformedGuarantee(threshold not a number)')
    if not (module.get('guarantee_dataset') or '').strip():
        out.append('MalformedGuarantee(missing dataset)')
    return out


# ── 补充细则（§S / P-01 / E-03 / E-06 / E-10 / S-01）──────────────────────

@_law
def check_shadowing_discipline(module: Dict[str, Any]) -> List[str]:
    """§S 遮蔽与绑定纪律：重复符号 / Opaque 遮蔽 / 影子目标缺失。"""
    out = []
    seen = set()
    for op in module['ops']:
        if op['name'] in seen:
            out.append(f"DuplicateSymbol({op['name']})")
        seen.add(op['name'])
    for target in module['shadow_targets']:
        if target in OPAQUE_MATH or target.startswith(('0xK', '0xQ')):
            out.append(f'OpaqueShadowAttempt({target})')
    defined = {op['name'] for op in module['ops']}
    for target in module['shadow_targets']:
        if '.' in target:
            continue                 # 限定名指向外部包，v0.1 不可解析
        if target not in defined:
            out.append(f'ShadowTargetMissing({target})')
    return out


@_law
def check_proof_structure(module: Dict[str, Any]) -> List[str]:
    """P-01 承载力规约结构：## Proof 必须带 Model + Invariant，Pre/Post 成对。"""
    if not module['proof_declared']:
        return []
    out = []
    if not module['proof_has_model']:
        out.append(f"MissingModel({module['name']})")
    if not module['proof_has_invariant']:
        out.append(f"MissingInvariant({module['name']})")
    for op in module['ops']:
        if op['has_pre'] != op['has_post']:
            out.append(f"IncompleteContract({op['name']})")
    return out


@_law
def check_test_portability(module: Dict[str, Any]) -> List[str]:
    """E-03 测试可移植性：期望值必须是错误或可解析字面量。"""
    out = []
    for op in module['ops']:
        for _inp, exp in op['tests']:
            e = exp.strip()
            if not (e.startswith('⊥') or parse_val(e) is not None):
                out.append(f"UnportableAssertion({op['name']}, {exp})")
    return out


@_law
def check_internal_consistency(module: Dict[str, Any]) -> List[str]:
    """E-06 内部一致性：测试期望值的形状须与返回类型一致。"""
    out = []
    for op in module['ops']:
        rt = return_type(op['sig'])
        numeric = rt in NUMERIC_TYPES
        container = any(k in rt for k in ('List', 'Tensor', 'Map', 'Seq', 'Fmap'))
        if not numeric and not container:
            continue
        for _inp, exp in op['tests']:
            e = exp.strip()
            if e.startswith('⊥'):
                continue
            val = parse_val(e)
            if val is None:
                continue
            kind = val[0]
            if (container and not numeric and kind in ('num', 'fnum')) or \
               (numeric and not container and kind == 'list'):
                out.append(f"SignatureMismatch({op['name']}, {exp})")
    return out


@_law
def check_eval_determinism(module: Dict[str, Any]) -> List[str]:
    """E-10 求值确定性：## Determinism 三项必须良构。"""
    if not module['determinism_declared']:
        return []
    out = []
    p = module.get('determinism_precision') or ''
    try:
        if int(p) < 1:
            out.append(f'MalformedDeterminism(invalid precision: {p!r})')
    except ValueError:
        out.append(f'MalformedDeterminism(invalid precision: {p!r})')
    if (module.get('determinism_rounding') or '') not in ('round', 'floor', 'ceil', 'trunc'):
        out.append(f"MalformedDeterminism(invalid rounding: {module.get('determinism_rounding')!r})")
    if (module.get('determinism_sort_stability') or '') not in ('true', 'false'):
        out.append(f"MalformedDeterminism(invalid sort_stability: {module.get('determinism_sort_stability')!r})")
    return out


@_law
def check_package_signature(module: Dict[str, Any]) -> List[str]:
    """E-08 / S-01 包签名：声明 ## Signature 就必须良构。"""
    if not module['signature_declared']:
        return []
    out = []
    if not (module.get('signature_signer') or '').strip():
        out.append('MalformedSignature(missing signer)')
    fp = module.get('signature_pubkey_fp') or ''
    if not (fp.startswith('sha256:') and len(fp) > len('sha256:')):
        out.append(f'MalformedSignature(invalid pubkey_fp: {fp!r})')
    if (module.get('signature_algorithm') or '') != 'ed25519':
        out.append(f"MalformedSignature(invalid algorithm: {module.get('signature_algorithm')!r})")
    if not (module.get('signature_value') or '').strip():
        out.append('MalformedSignature(missing signature)')
    return out


def run_canonical_tests(module: Dict[str, Any]) -> Dict[str, Any]:
    """跑全部规范测试（Law IV 的实质部分）：返回 {passed,total,failures}。"""
    passed = total = 0
    failures = []
    for op in module['ops']:
        for inp, exp in op['tests']:
            total += 1
            detail = eval_test(inp, exp)
            if detail is None:
                passed += 1
            else:
                failures.append({'op': op['name'], 'input': inp,
                                 'expected': exp, 'actual': detail})
    return {'passed': passed, 'total': total, 'failures': failures}


def check_python(module: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """兼容 sigma-lang 原语：全部规则一次跑完，返回 (通过?, 违规列表)。"""
    violations: List[str] = []
    for name in _CHECK_REGISTRY:
        violations.extend(_CHECK_REGISTRY[name](module))
    return (not violations, violations)


def check_iron_laws(module: Dict[str, Any], strict: bool = True) -> Dict[str, Any]:
    """逐条定律报告判定，供三门门禁与元动作消费。

    返回：
        {passed, failed_laws: [{id,key,zh,en,violations}], advisory_laws: [...],
         supplemental: {...}, violations: [...], tests: {...}}
    """
    law_results, failed, advisory = [], [], []
    skipped_laws: List[Dict[str, Any]] = []
    all_violations: List[str] = []

    skipped_ids = _skipped_law_ids(module)
    for law in IRON_LAWS:
        fn = _CHECK_REGISTRY.get(law['check'])
        violations = fn(module) if fn else []
        entry = {'id': law['id'], 'key': law['key'], 'zh': law['zh'], 'en': law['en'],
                 'violations': violations}
        law_results.append(entry)
        if law['key'] == 'verifier_consensus':
            # 单端无法判定共识 → 显式 advisory，不冒充通过
            advisory.append(entry)
            continue
        if violations:
            failed.append(entry)
            all_violations.extend(violations)
        elif law['id'] in skipped_ids:
            # 未声明相关章节 → 本条**没查**（不是查过且通过）。显式标 skipped，
            # 让消费方分得清"通过"与"跳过"（改前这里一律 status='pass'）。
            entry['status'] = 'skipped'
            entry['skip_reason'] = skipped_ids[law['id']]
            skipped_laws.append(entry)
        else:
            entry['status'] = 'pass'

    supplemental = {}
    supplemental_skipped = _skipped_supplemental(module)
    for name in SUPPLEMENTAL_CHECKS:
        fn = _CHECK_REGISTRY.get(name)
        vs = fn(module) if fn else []
        supplemental[name] = vs
        all_violations.extend(vs)

    tests = run_canonical_tests(module)
    # 审计修复（P1）：改前 `passed` 只看 failed_laws + supplemental，
    # **完全不含规范测试结果** —— 一条 `0/2 全挂` 的规约照样 pass、verdict=pass、
    # run_sigma_block exit 0（报告正文却打印 "0/2 passed"）。
    # 现在：测试失败一律算不通过，且**不设"strict 才管测试"的双轨**（那等于默认放行）。
    # 测试为空不算失败 —— 那由 Law IV（NoTestsDefined）负责拦。
    base_ok = not failed and not tests['failures']
    passed = base_ok and not any(supplemental.values())
    if not passed and not strict:
        passed = base_ok            # 宽松模式只放宽补充细则，测试失败仍拦
    return {
        'passed': passed,
        'strict': strict,
        'laws': law_results,
        'failed_laws': failed,
        'advisory_laws': advisory,
        'skipped_laws': skipped_laws,
        'supplemental': supplemental,
        'supplemental_skipped': supplemental_skipped,
        'violations': all_violations,
        'test_failures': len(tests['failures']),
        'tests': tests,
        'module': module.get('name'),
        'fingerprint': fingerprint_of(module),
    }


# 哪些定律因"规约未声明相应章节"而无法检查（→ status=skipped，不是 pass）。
# 与各 check 里的 `if not ...: return []` 一一对应；放这里集中登记，避免
# "改了 check 忘了改报告"的漂移。
_SKIPPED_LAW_REASONS = (
    ('XV', lambda m: not (m.get('exports') or []),
     '未声明 ## Exports 块（v0.1 政策：无 Exports 不检查一一对应）'),
    ('XVII', lambda m: not m.get('guarantee_declared'),
     '未声明 ## Guarantee 块（无从检查概率保证是否良构）'),
)

# 补充细则的跳过条件（同理：未声明即未检查）。
_SKIPPED_SUPPLEMENTAL_REASONS = (
    ('check_proof_structure', lambda m: not m.get('proof_declared'),
     '未声明 ## Proof 块'),
    ('check_eval_determinism', lambda m: not m.get('determinism_declared'),
     '未声明 ## Determinism 块'),
    ('check_package_signature', lambda m: not m.get('signature_declared'),
     '未声明 ## Signature 块'),
)


def _skipped_law_ids(module: Dict[str, Any]) -> Dict[str, str]:
    """返回 {law_id: reason}：本条定律因"未声明"而**没检查**。"""
    out = {}
    for law_id, absent, reason in _SKIPPED_LAW_REASONS:
        try:
            if absent(module):
                out[law_id] = reason
        except (TypeError, AttributeError):
            continue
    return out


def _skipped_supplemental(module: Dict[str, Any]) -> Dict[str, str]:
    """返回 {check_name: reason}：该补充细则因"未声明"而没检查。"""
    out = {}
    for name, absent, reason in _SKIPPED_SUPPLEMENTAL_REASONS:
        try:
            if absent(module):
                out[name] = reason
        except (TypeError, AttributeError):
            continue
    return out


def fingerprint_of(module: Dict[str, Any]) -> str:
    """规约内容指纹（Law I 的可追溯基线，sha256 over 规范化文本）。"""
    canon = json.dumps(
        {'name': module.get('name'), 'version': module.get('version'),
         'ops': [{'name': o['name'], 'fp': o['fp'], 'sig': o['sig'],
                  'laws': o['laws'], 'tests': o['tests']} for o in module['ops']],
         'exports': module.get('exports')},
        ensure_ascii=False, sort_keys=True)
    return 'sha256:' + hashlib.sha256(canon.encode('utf-8')).hexdigest()


def fingerprint_of_spec(spec: Dict[str, Any]) -> str:
    """spec JSON 的内容指纹 —— 与 MD 侧 `fingerprint_of` 同一套规范化口径。

    公开这个入口是为了让动作/模板能钉住"我实现的是哪一版规约"：直接调
    `fingerprint_of(_module_from_spec(spec))` 会把私有函数变成事实 API，
    指纹算法一改，所有下游动作一起漂。
    """
    return fingerprint_of(_module_from_spec(spec))


# ---------------------------------------------------------------------------
# 5. spec JSON（docs/41 §A3：与 omega/*.spec.json 互喂）
# ---------------------------------------------------------------------------

def to_spec_json(module: Dict[str, Any], spec_id: Optional[str] = None) -> Dict[str, Any]:
    """由 Sigma MD 模块生成 spec JSON（v1.0 结构，spec/json-schema.md:19-28）。"""
    prefix = None
    ops = []
    for op in module['ops']:
        fp = op['fp'] or '0x0000'
        if prefix is None:
            m = re.match(r'^(0x[0-9A-Fa-f]{2})', fp)
            prefix = (m.group(1) + '000') if m else '0x0000'
        laws = [{'forall': _law_forall(l), 'predicate': _law_predicate(l),
                 'description': l} for l in op['laws']]
        pre = []
        if op.get('pre'):
            pre.append({'expr': op['pre'], 'error': _pre_error(op),
                        'description': op['pre']})
        tests = []
        for inp, exp in op['tests']:
            e = exp.strip()
            if e.startswith('⊥'):
                name = e[1:].strip().split()[0] if e[1:].strip() else 'TypeError'
                tests.append({'input': [_as_json_value(x) for x in _split_input(inp, op['name'])],
                              'output': None, 'error': name,
                              'description': f'{inp} → ⊥ {e[1:].strip()}'})
            else:
                v = parse_val(e)
                tests.append({'input': [_as_json_value(x) for x in _split_input(inp, op['name'])],
                              'output': _to_plain(v) if v else e,
                              'description': f'{inp} → {e}'})
        entry = {
            'name': op['name'],
            'fingerprint': fp,
            'signature': {'params': param_types(op['sig']), 'returns': return_type(op['sig'])},
            'definition': {'kind': 'expression', 'params': [],
                           'body': ' '.join(op.get('definition') or []) or op['sig']},
            'preconditions': pre,
            'laws': laws,
            'tests': tests,
        }
        if op.get('post'):
            entry['postcondition'] = op['post']
        ops.append(entry)

    doc = {
        'spec': spec_id or module.get('package') or module['name'],
        'version': module.get('version') or '0.1.0',
        'fingerprint_prefix': prefix or '0x0000',
        'types': [],
        'operations': ops,
        'meta': {
            'source': 'vools.actus.sigma',
            'sigma_dialect': SIGMA_VERSION,
            'imports': module.get('imports') or [],
            'exports': module.get('exports') or [],
            'fingerprint': fingerprint_of(module),
            'expected': module.get('expected'),
        },
    }
    if module.get('timing_contract'):
        doc['meta']['timing_contract'] = module['timing_contract']
    if module.get('capabilities'):
        doc['meta']['capabilities'] = module['capabilities']
    if module.get('guarantee_declared'):
        doc['guarantee'] = {'metric': module.get('guarantee_metric'),
                            'threshold': module.get('guarantee_threshold'),
                            'dataset': module.get('guarantee_dataset')}
    return doc


def _law_forall(law: str) -> List[str]:
    m = re.match(r'^∀\s*([^·.]+?)\s*[·.]\s*', law)
    if not m:
        return []
    return re.split(r'[\s,]+', m.group(1).strip())


def _law_predicate(law: str) -> str:
    parts = re.split(r'[·.]', law, maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else law


def _pre_error(op: Dict[str, Any]) -> str:
    for _inp, exp in op['tests']:
        e = exp.strip()
        if e.startswith('⊥'):
            tail = e[1:].strip().split()
            if tail and tail[0] in ERROR_NAMES:
                return tail[0]
    return 'TypeError'


def _split_input(inp: str, op_name: str) -> List[str]:
    """`f(a, b)` 形式取实参；否则按**顶层逗号**切分（不再按空白切）。

    审计修复（P2）：改前最后的兜底是 `re.split(r'\\s+', inp)` —— 把
    `| 1 + 1 | 2 |` 这类**表达式**测试切成 `[1, '+', 1]` 三个实参，
    spec JSON 往返后 judge 报 `expected 1 arg(s), got 3`（实测）。
    表达式应整体作为一个输入节点；只有多实参写法（逗号）才切。
    """
    parts = _args1(inp.strip(), op_name)
    if parts:
        return parts
    if ',' in inp:
        return split_all_top_level(inp, ',')
    return [inp.strip()]


def _as_json_value(token: str) -> Any:
    v = parse_val(token)
    return _to_plain(v) if v is not None else token


def _to_plain(v):
    if v is None:
        return None
    if v[0] == 'list':
        return [_to_plain(x) for x in v[1]]
    return v[1]


def _plain_cmp(value):
    """把值归一成"可比较的普通表示"（spec 测试 vs 实现/引擎结果对比用）。

    审计修复（P1，judge 恒 WA）：引擎对 definition 里的字符串节点原样返回
    （`{kind:'expression', body:'1'}` → `'1'`，`params` 为空时 `'x'` 也不会绑定），
    而 spec 期望值是 `1` —— `'1' == 1` 为 False，于是**连常量定义都判 WA**，
    任何合法 spec 的自洽 judge 恒 exit 1。
    这里两侧统一归一：sigma 值元组 → plain；可解析字面量串 → plain；列表递归。
    """
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        try:
            return _to_plain(value)
        except (IndexError, TypeError):
            return value
    if isinstance(value, str):
        v = parse_val(value)
        if v is not None:
            return _to_plain(v)
        return value
    if isinstance(value, list):
        return [_plain_cmp(v) for v in value]
    return value


_SPEC_JSON_REQUIRED = ('spec', 'version', 'fingerprint_prefix', 'types', 'operations')


def validate_spec_json(spec: Dict[str, Any], strict: bool = True) -> List[str]:
    """spec JSON 结构校验（对齐 spec/json-schema.md 的必填项 + §一致性要求）。

    一致性要求（json-schema.md:155-160）逐字落地：
      1. 每个 operation 需要 name / fingerprint / signature{params,returns}；
      2. 每个操作至少 1 条 laws；
      3. preconditions 的错误名必须与 tests 的 error 一致，且必须是 20 个规范名之一；
      4. 每个操作至少 1 条 tests（Law IV）。
    **不**额外要求「每个操作都有负向用例」—— 那是 MD 方言的 Law XIV，上游
    json-schema.md 对 JSON 侧没有这条；把没写的规则加进来会误判官方 spec。
    `strict=False` 时只判顶层结构。
    """
    if not isinstance(spec, dict):
        return ['spec JSON must be an object']
    errors = []
    for k in _SPEC_JSON_REQUIRED:
        if k not in spec:
            errors.append(f'schema: 缺少顶层字段 {k!r}')
    ops = spec.get('operations')
    if not isinstance(ops, list):
        errors.append("schema: 'operations' 必须是列表")
        return errors
    if not strict:
        return errors
    seen_fp: Dict[str, str] = {}
    for op in ops:
        if not isinstance(op, dict) or not op.get('name'):
            errors.append('schema: 每个 operation 需要 name')
            continue
        name = op['name']
        if not op.get('fingerprint'):
            errors.append(f'schema: {name} 缺 fingerprint（Law I）')
        else:
            fp = op['fingerprint']
            if fp in seen_fp:
                errors.append(f'Law I: 指纹冲突 {name} 与 {seen_fp[fp]} 同为 {fp}')
            else:
                seen_fp[fp] = name
        sig = op.get('signature')
        if not isinstance(sig, dict) or 'params' not in sig or 'returns' not in sig:
            errors.append(f'schema: {name} 的 signature 需含 params/returns')
        if not (op.get('laws') or []):
            errors.append(f'Law III: {name} 未声明任何 laws')
        if not (op.get('tests') or []):
            errors.append(f'Law IV: {name} 未声明任何 tests')
        errs = {t.get('error') for t in (op.get('tests') or []) if t.get('error')}
        pre_errs = {p.get('error') for p in (op.get('preconditions') or []) if p.get('error')}
        for u in sorted((errs | pre_errs) - set(ERROR_NAMES)):
            errors.append(f'schema: {name} 使用未注册错误名 {u!r}')
        if pre_errs and not (pre_errs & errs):
            errors.append(f'Law XVI: {name} 的 preconditions 错误名与 tests 不一致')
    return errors


def load_spec_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding='utf-8') as f:
            spec = json.load(f)
    except OSError as exc:
        raise SpecError(f'无法读取 spec JSON {path}: {exc}') from exc
    except ValueError as exc:
        raise SpecError(f'spec JSON 解析失败：{exc}') from exc
    return spec


# ---------------------------------------------------------------------------
# 6. SigmaEngine —— spec JSON 自动求值器（移植 sigma_engine.py:523-673）
# ---------------------------------------------------------------------------

def _require_list(x, fn_name):
    if not isinstance(x, list):
        _raise_error('TypeError', f'{fn_name}: expected a list, got {type(x).__name__}')
    return x


def _require_int(x, fn_name):
    if not isinstance(x, int) or isinstance(x, bool):
        _raise_error('TypeError', f'{fn_name}: expected an int, got {x!r}')
    return x


def _require_str(x, fn_name):
    if not isinstance(x, str):
        _raise_error('TypeError', f'{fn_name}: expected a str, got {type(x).__name__}')
    return x


def _fn_index(xs, i):
    _require_list(xs, 'index')
    _require_int(i, 'index')
    try:
        return xs[i]
    except IndexError:
        _raise_error('ShapeError', f'index: index {i} out of range for list of len {len(xs)}')


def _fn_len(xs):
    return len(_require_list(xs, 'len'))


def _fn_min(*args):
    if len(args) == 1:
        return min(_require_list(args[0], 'min'))
    return min(_require_int(a, 'min') for a in args)


def _fn_max(*args):
    if len(args) == 1:
        return max(_require_list(args[0], 'max'))
    return max(_require_int(a, 'max') for a in args)


def _fn_fold_add(xs):
    _require_list(xs, 'fold_add')
    if xs and all(isinstance(x, list) for x in xs):
        return sum(x[-1] for x in xs)
    return sum(xs)


def _fn_map(xs, field):
    _require_list(xs, 'map')
    _require_int(field, 'map')
    return [x[field] for x in xs]


def _fold_ints(fn_name):
    def _f(*args):
        from functools import reduce
        vals = [_require_int(x, fn_name) for x in args]
        return reduce(_REDUCE_OPS[fn_name], vals)
    return _f


_REDUCE_OPS = {
    'add': lambda a, b: a + b,
    'sub': lambda a, b: a - b,
    'mul': lambda a, b: a * b,
}


def _fn_floordiv(a, b):
    _require_int(a, 'floordiv')
    _require_int(b, 'floordiv')
    if b == 0:
        _raise_error('DivByZero', 'floordiv: division by zero')
    return a // b


def _fn_div(a, b):
    _require_int(a, 'div')
    _require_int(b, 'div')
    if b == 0:
        _raise_error('DivByZero', 'div: division by zero')
    return a / b


def _fn_mod(a, b):
    _require_int(a, 'mod')
    _require_int(b, 'mod')
    if b == 0:
        _raise_error('DivByZero', 'mod: division by zero')
    return a % b


def _cmp(op):
    def _f(a, b):
        return bool(_COMPARATORS[op](a, b))
    return _f


_COMPARATORS = {
    'eq': lambda a, b: a == b, 'ne': lambda a, b: a != b,
    'gt': lambda a, b: a > b, 'ge': lambda a, b: a >= b,
    'lt': lambda a, b: a < b, 'le': lambda a, b: a <= b,
}


def _fn_weighted(xs, cols=(1, 2), want=None):
    """对 [.., vote, weight] 行按 want 过滤后求 weight 之和（§SK weighted_*）。"""
    _require_list(xs, 'weighted')
    total = 0
    for row in xs:
        _require_list(row, 'weighted')
        if len(row) < max(cols) + 1:
            _raise_error('ShapeError', f'weighted: row {row!r} too short')
        if row[cols[0]] == want:
            total += row[cols[1]]
    return total


def _fn_weighted_accept(xs):
    return _fn_weighted(xs, want=1)


def _fn_weighted_reject(xs):
    return _fn_weighted(xs, want=0)


def _fn_weighted_support(xs):
    return _fn_weighted(xs, want=1)


def _fn_fold_credit(init, events):
    _require_int(init, 'fold_credit')
    _require_list(events, 'fold_credit')
    credit = init
    for e in events:
        _require_list(e, 'fold_credit')
        if len(e) < 2:
            _raise_error('TypeError', f'fold_credit: event {e!r} needs [kind, count]')
        kind, count = e[0], e[1]
        _require_int(kind, 'fold_credit')
        _require_int(count, 'fold_credit')
        if kind == 0:
            credit += 5 * count
        elif kind == 1:
            for _ in range(count):
                credit = (credit * 7) // 10
        else:
            _raise_error('TypeError', f'fold_credit: unknown kind {kind}')
    return max(0, credit)


def _fn_split_floor(contribs, reward):
    _require_list(contribs, 'split_floor')
    _require_int(reward, 'split_floor')
    total = 0
    rows = []
    for row in contribs:
        _require_list(row, 'split_floor')
        if len(row) < 2:
            _raise_error('TypeError', f'split_floor: row {row!r} has fewer than 2 fields')
        rows.append(row)
        total += row[1]
    if total == 0:
        _raise_error('DivByZero', 'split_floor: total contribution is 0')
    return [[m, (reward * c) // total] for m, c in rows]


def _fn_enumerate_ledger(entries):
    _require_list(entries, 'enumerate_ledger')
    ledger = []
    for i, entry in enumerate(entries, 1):
        _require_list(entry, 'enumerate_ledger')
        if len(entry) < 3:
            _raise_error('TypeError', f'enumerate_ledger: entry {entry!r} has fewer than 3 fields')
        _, amount, source_id = entry[0], entry[1], entry[2]
        if source_id < 1:
            _raise_error('NotTraceable', f'enumerate_ledger: source_id {source_id} not traceable')
        if amount < 0:
            _raise_error('TypeError', f'enumerate_ledger: negative amount {amount}')
        ledger.append([i, source_id, amount])
    return ledger


TIME_EPOCH_SEED = 1700000000      # 确定性测试用固定种子，不读真实时钟


def _fn_str_len(s):
    return len(_require_str(s, 'str_len'))


def _fn_str_concat(*parts):
    return ''.join(_require_str(p, 'str_concat') for p in parts)


def _fn_str_contains(hay, needle):
    _require_str(hay, 'str_contains')
    _require_str(needle, 'str_contains')
    return needle in hay


def _fn_option_some(x):
    if x is None:
        _raise_error('TypeError', 'option_some: None denotes none; wrap a non-None value')
    return x


def _fn_map_get(m, key):
    if not isinstance(m, dict):
        _raise_error('TypeError', f'map_get: expected a Map (dict), got {type(m).__name__}')
    return m.get(key)


BUILTIN_FNS: Dict[str, Callable] = {
    'index': _fn_index, 'len': _fn_len, 'min': _fn_min, 'max': _fn_max,
    'fold_add': _fn_fold_add, 'map': _fn_map,
    'add': _fold_ints('add'), 'sub': _fold_ints('sub'), 'mul': _fold_ints('mul'),
    'floordiv': _fn_floordiv, 'div': _fn_div, 'mod': _fn_mod,
    'eq': _cmp('eq'), 'ne': _cmp('ne'), 'lt': _cmp('lt'), 'le': _cmp('le'),
    'gt': _cmp('gt'), 'ge': _cmp('ge'),
    'weighted_accept': _fn_weighted_accept, 'weighted_reject': _fn_weighted_reject,
    'weighted_support': _fn_weighted_support, 'fold_credit': _fn_fold_credit,
    'split_floor': _fn_split_floor, 'enumerate_ledger': _fn_enumerate_ledger,
    'str_len': _fn_str_len, 'str_concat': _fn_str_concat,
    'str_contains': _fn_str_contains,
    'time_now_epoch': lambda: TIME_EPOCH_SEED,
    'option_some': _fn_option_some, 'option_none': lambda: None,
    'map_get': _fn_map_get,
}

#: preconditions[].expr 里可用的白名单辅助函数（受限 eval，无 __builtins__）
EXPR_HELPERS: Dict[str, Any] = {
    'min': min, 'max': max, 'len': len, 'abs': abs, 'sum': sum,
    'index': lambda xs, i: xs[i],
    'sum_contribs': lambda c: sum(x[1] for x in c),
    'min_source_id': lambda e: min((x[2] for x in e), default=10 ** 9),
}


class _ExprEvaluator:
    """共享表达式求值；SigmaEngine 继承后嵌套调用可回到 engine.eval。"""

    def _eval_node(self, node, env):
        if node is None:
            return None
        if isinstance(node, bool):
            return node
        if isinstance(node, (int, float)):
            return node
        if isinstance(node, str):
            if node == '$_':
                if self._last_result is None:
                    raise SpecValidationError("'$_' used before any operation result exists")
                return self._last_result
            if node in env:
                return env[node]
            return node                       # 字符串字面量
        if isinstance(node, list):
            return [self._eval_node(x, env) for x in node]
        if isinstance(node, dict):
            if 'op' in node:
                return self.eval(node['op'], [self._eval_node(a, env) for a in node.get('args', [])])
            if 'list' in node:
                return [self._eval_node(x, env) for x in node['list']]
            if 'map' in node:
                return {k: self._eval_node(v, env) for k, v in node['map'].items()}
            if 'if' in node:
                ctx = self._first_list_param(env)
                if self._eval_cond(node['if'], env, ctx):
                    return self._eval_node(node.get('then'), env)
                return self._eval_node(node.get('else'), env)
            if 'fn' in node:
                fn = self.builtin_fns.get(node['fn'])
                if fn is None:
                    _raise_error('TypeError', f'unknown builtin fn: {node["fn"]}')
                return fn(*[self._eval_node(a, env) for a in node.get('args', [])])
            raise SpecValidationError(f'invalid expression node: {node!r}')
        raise SpecValidationError(f'invalid expression node type: {type(node).__name__}')

    def _eval_cond(self, cond, env, ctx):
        if isinstance(cond, bool):
            return cond
        if isinstance(cond, dict):
            if 'expr' in cond:
                return bool(self._eval_expr(cond['expr'], env))
            if 'fn' in cond or 'op' in cond:
                return bool(self._eval_node(cond, env))
            if 'not' in cond:
                return not self._eval_cond(cond['not'], env, ctx)
            if 'and' in cond:
                return all(self._eval_cond(c, env, ctx) for c in cond['and'])
            if 'or' in cond:
                return any(self._eval_cond(c, env, ctx) for c in cond['or'])
            if 'field' in cond:
                op = next((k for k in _COMPARATORS if k in cond), None)
                if op is None or ctx is None:
                    raise SpecValidationError(f'invalid field condition: {cond!r}')
                val = ctx[cond['field']]
                target = cond[op]
                if isinstance(target, (dict, list)):
                    target = self._eval_node(target, env)
                return bool(_COMPARATORS[op](val, target))
            raise SpecValidationError(f'invalid condition node: {cond!r}')
        raise SpecValidationError(f'invalid condition: {cond!r}')

    def _eval_expr(self, expr: str, env: Dict[str, Any]):
        """受限 eval：仅参数名 + 白名单辅助函数（spec JSON 属受信输入）。"""
        ns = dict(self.expr_helpers)
        ns.update(env)
        try:
            return eval(expr, {'__builtins__': {}}, ns)   # noqa: S307
        except ZeroDivisionError:
            _raise_error('DivByZero', expr)
        except Exception as exc:
            raise SpecValidationError(f'bad precondition expr {expr!r}: {exc}') from exc

    @staticmethod
    def _first_list_param(env):
        for v in env.values():
            if isinstance(v, list):
                return v
        return None


class SigmaEngine(_ExprEvaluator):
    """按 spec JSON 自动求值的通用 verifier 引擎（docs/41 §A3 语料互喂的执行端）。"""

    def __init__(self, spec: Optional[Dict[str, Any]] = None):
        self.spec = None
        self.operations: Dict[str, Dict[str, Any]] = {}
        self.types: Dict[str, Dict[str, Any]] = {}
        self.builtin_fns = dict(BUILTIN_FNS)
        self.expr_helpers = dict(EXPR_HELPERS)
        self._last_result = None
        if spec is not None:
            self._load(spec)

    @classmethod
    def from_spec(cls, path: str) -> 'SigmaEngine':
        return cls(load_spec_json(path))

    def _load(self, spec: Dict[str, Any]) -> None:
        if not isinstance(spec, dict) or not isinstance(spec.get('operations'), list):
            raise SpecValidationError("spec JSON must be an object with an 'operations' list")
        self.spec = spec
        self.types = {t.get('name'): t for t in spec.get('types', [])}
        self.operations = {}
        for op in spec.get('operations', []):
            if not isinstance(op, dict) or not op.get('name'):
                raise SpecValidationError("each operation needs a 'name'")
            self.operations[op['name']] = op

    def eval(self, op_name: str, args: List[Any]) -> Any:
        """按 spec 求值操作：签名元数校验 → 前置条件 → definition 求值。"""
        op = self.operations.get(op_name)
        if op is None:
            raise UnknownOpError(f'unknown operation: {op_name}')
        sig = op.get('signature') or {}
        n_params = len(sig.get('params') or [])
        if len(args) != n_params:
            _raise_error('ShapeError',
                         f'{op_name}: expected {n_params} arg(s), got {len(args)}')
        definition = op.get('definition') or {}
        params = definition.get('params') or [f'arg{i}' for i in range(n_params)]
        env = dict(zip(params, args))
        for pc in op.get('preconditions') or []:      # 前置条件先于求值
            self._check_precondition(pc, env, op_name)
        kind = definition.get('kind', 'lambda')
        if kind == 'table':
            result = self._eval_table(op, args, env)
        elif kind in ('lambda', 'expression'):
            result = self._eval_node(definition.get('body'), env)
        else:
            raise SpecValidationError(f'{op_name}: unknown definition kind {kind!r}')
        self._last_result = result                    # 更新 "$_" 指向
        return result

    def _check_precondition(self, pc: Dict[str, Any], env: Dict[str, Any], op_name: str) -> None:
        expr = pc.get('expr')
        if expr is None:
            raise SpecValidationError(f'{op_name}: precondition without "expr"')
        if not self._eval_expr(expr, env):
            err = pc.get('error', 'TypeError')
            desc = pc.get('description') or f'{op_name}: precondition failed: {expr}'
            _raise_error(err, desc)

    def _eval_table(self, op: Dict[str, Any], args: List[Any],
                    env: Dict[str, Any]) -> Any:
        """kind=table 状态机转移：按序匹配 when → 校验 guard → 应用 set。"""
        state = args[0]
        if not isinstance(state, list):
            _raise_error('TypeError', f"{op['name']}: table input must be a List")
        definition = op.get('definition') or {}
        default_error = definition.get('default_error', 'StateError')
        for row in definition.get('table') or []:
            when = row.get('when')
            if when is not None and not self._eval_cond(when, env, state):
                continue
            guard = row.get('guard')
            if guard is not None:
                g_err = guard.get('error', default_error)
                g_cond = {k: v for k, v in guard.items() if k != 'error'}
                if not self._eval_cond(g_cond, env, state):
                    _raise_error(g_err, f"{op['name']}: guard failed")
            result = list(state)
            sets = row.get('set') or []
            if isinstance(sets, dict):
                sets = [sets]
            for s in sets:
                idx = s.get('field')
                if idx is None or 'value' not in s:
                    raise SpecValidationError(f"{op['name']}: set needs 'field' and 'value'")
                while len(result) <= idx:
                    result.append(0)
                result[idx] = self._eval_node(s.get('value'), env)
            return result
        _raise_error(default_error, f"{op['name']}: no table row matched for state {state!r}")

    def _resolve_input_node(self, x: Any) -> Any:
        """corpus input 节点：表达式 dict 先求值，列表递归，"$_" 取上一个结果。

        审计修复（P2）：字符串节点若是**字面量**先解析成具体值（`'1'` → 1），
        若是**表达式**（`'1 + 1'`）则用 sigma 求值器算出来 —— 否则 spec JSON 里
        的表达式输入会被当成原始字符串传给实现/引擎（judge 因此也是 WA）。
        求值失败时保持原字符串（可能是合法的字符串输入）。
        """
        if isinstance(x, dict):
            return self._eval_node(x, {})      # 如 {"op": "task_create", "args": [7, 100]}
        if isinstance(x, list):
            return [self._resolve_input_node(v) for v in x]
        if isinstance(x, str):
            if x == '$_':
                if self._last_result is None:
                    raise SpecValidationError("'$_' in corpus input before any operation result")
                return self._last_result
            lit = parse_val(x)
            if lit is not None:
                return _to_plain(lit)
            ev = eval_expr(x)
            if isinstance(ev, tuple) and len(ev) == 2:
                return _to_plain(ev)
            return x
        return x

    def run_corpus(self, ops: Optional[List[str]] = None) -> List[Tuple[str, Dict[str, Any], bool, str]]:
        """跑 spec 自带 tests：[(op, test, ok, detail)]，逐条如实回报。"""
        self._last_result = None               # "$_" 序列从头开始
        out = []
        order = [o for o in (self.spec or {}).get('operations') or []
                 if not ops or o.get('name') in ops]
        for op in order:
            name = op.get('name')
            for t in op.get('tests') or []:
                inputs = [self._resolve_input_node(v) for v in (t.get('input') or [])]
                want_err = t.get('error')
                want_out = t.get('output')
                try:
                    got = self.eval(name, inputs)
                except IronLawViolation as exc:
                    got_name = getattr(exc, 'name', None) or type(exc).__name__
                    if want_err and got_name == want_err:
                        out.append((name, t, True, f'expected error {want_err}'))
                    elif want_err:
                        out.append((name, t, False, f'expected error {want_err}, got {got_name}'))
                    else:
                        out.append((name, t, False, f'unexpected {got_name}: {exc}'))
                except Exception as exc:                    # 引擎内部错误也不许静默
                    out.append((name, t, False,
                                f'unexpected exception {type(exc).__name__}: {exc}'))
                else:
                    if want_err:
                        out.append((name, t, False,
                                    f'expected error {want_err}, got {got!r}'))
                    elif _plain_cmp(got) == _plain_cmp(want_out):
                        out.append((name, t, True, f'{got!r}'))
                    else:
                        out.append((name, t, False, f'expected {want_out!r}, got {got!r}'))
        return out


# ---------------------------------------------------------------------------
# 7. sigma-spec2judge：spec JSON → judge 验收断言（docs/41 §A2 / §A3）
# ---------------------------------------------------------------------------

def spec_to_assertions(spec: Dict[str, Any], ops_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """把 spec JSON 摊平成可交给 Omega / 三门门禁的验收断言清单。

    每条断言 = {id, op, fingerprint, kind, input, expect_output, expect_error,
    law, description}，与 omega/*.spec.json 的「输入-期望」语料同构（docs/41 §A3）。
    """
    assertions: List[Dict[str, Any]] = []
    for op in spec.get('operations') or []:
        name = op.get('name')
        if not name or (ops_filter and name not in ops_filter):
            continue
        fp = op.get('fingerprint')
        for i, t in enumerate(op.get('tests') or [], 1):
            assertions.append({
                'id': f'{name}#t{i}',
                'op': name,
                'fingerprint': fp,
                'kind': 'negative' if t.get('error') else 'positive',
                'input': list(t.get('input') or []),
                'expect_output': t.get('output'),
                'expect_error': t.get('error'),
                'description': t.get('description') or '',
            })
        for i, law in enumerate(op.get('laws') or [], 1):
            assertions.append({
                'id': f'{name}#law{i}',
                'op': name,
                'fingerprint': fp,
                'kind': 'law',
                'law': law.get('predicate'),
                'forall': law.get('forall') or [],
                'description': law.get('description') or '',
            })
        for i, pre in enumerate(op.get('preconditions') or [], 1):
            assertions.append({
                'id': f'{name}#pre{i}',
                'op': name,
                'fingerprint': fp,
                'kind': 'precondition',
                'expr': pre.get('expr'),
                'expect_error': pre.get('error'),
                'description': pre.get('description') or '',
            })
    return assertions


def judge_spec(spec_path: Optional[str] = None, spec: Optional[Dict[str, Any]] = None,
               submission_path: Optional[str] = None, time_limit: float = 5.0,
               ops_filter: Optional[List[str]] = None, report_path: str = '',
               impl: Optional[Dict[str, Callable]] = None,
               strict_laws: bool = True) -> Dict[str, Any]:
    """spec JSON → judge 断言并逐条验收（tools/sigma-spec2judge.py 的 in-process 形态）。

    两种被验收对象：
      * `submission_path` / `impl`：Python 实现，导出与 operations 同名的可调用
        （对应 sigma-impl-verify.py 的 resolve_ops 语义，进程内直跑，无子进程）；
      * 两者都省略：用 spec 自带 definition 经 SigmaEngine 自校验（spec 自身一致性）。

    `strict_laws=True` 时 spec 结构不合 v1.0 schema 直接判不过；已知存在合法但
    不完美的历史 spec（如某些操作确实没有负向用例），可显式置 False 降级为告警 ——
    降级必须**显式**发生并写进报告，不得默认静默。

    返回 {"summary","verdicts","exit_code","report_path","fingerprint","spec_errors"}。
    """
    if spec is None:
        if not spec_path:
            raise SpecError('judge_spec 需要 spec_path 或 spec')
        spec = load_spec_json(spec_path)
    errors = validate_spec_json(spec, strict=strict_laws)
    if errors:
        result = {'summary': {'total': 0, 'pass': 0, 'fail': len(errors), 'verdicts': []},
                  'spec_errors': errors, 'verdicts': [], 'exit_code': 1,
                  'report_path': report_path, 'strict_laws': strict_laws,
                  'fingerprint': fingerprint_of(_module_from_spec(spec))}
        if report_path:
            _write_report(report_path, result)
        return result

    ops = {o['name']: o for o in spec.get('operations') or []}
    target_ops = [n for n in (ops_filter or list(ops)) if n in ops]

    resolved = impl
    if submission_path:
        resolved = _load_impl_symbols(submission_path)

    verdicts: List[Dict[str, Any]] = []
    if resolved is not None:
        # 对着外部实现跑：input 里的表达式节点先由 spec 引擎求值成具体值
        ref = SigmaEngine(spec)
        for name in target_ops:
            fn = resolved.get(name)
            if fn is None:
                verdicts.append({'id': name, 'verdict': 'WA', 'detail': 'implementation missing'})
                continue
            for i, t in enumerate(ops[name].get('tests') or [], 1):
                try:
                    inputs = [ref._resolve_input_node(v) for v in (t.get('input') or [])]
                except Exception as exc:
                    verdicts.append({'id': f'{name}#t{i}', 'verdict': 'WA',
                                     'detail': f'input resolve failed: {exc}'})
                    continue
                want_err = t.get('error')
                got: Any = None
                raised: Optional[str] = None
                try:
                    got = fn(*inputs)
                except IronLawViolation as exc:
                    raised = getattr(exc, 'name', type(exc).__name__)
                except Exception as exc:
                    raised = f'{type(exc).__name__}'
                if want_err:
                    ok = raised == want_err
                    detail = '' if ok else f'expected {want_err}, got {raised or repr(got)}'
                else:
                    # 审计修复（P1）：两侧统一归一后再比较 —— 实现可能返回 sigma 内部
                    # 值元组 / 字面量串，spec 里存的是普通值（`'1'` vs `1`）。
                    ok = raised is None and _plain_cmp(got) == _plain_cmp(t.get('output'))
                    detail = '' if ok else (raised or f'expected {t.get("output")!r}, got {got!r}')
                verdicts.append({'id': f'{name}#t{i}',
                                 'verdict': 'PASS' if ok else 'WA', 'detail': detail})
    else:
        # spec 自洽：交给引擎按 spec 的 definition 求值
        engine = SigmaEngine(spec)
        rows = engine.run_corpus(ops=target_ops)
        for name, t, ok, detail in rows:
            verdicts.append({'id': t.get('_vid') or name, 'verdict': 'PASS' if ok else 'WA',
                             'detail': detail, 'input': t.get('input'),
                             'expect_output': t.get('output'), 'expect_error': t.get('error')})

    summary = {
        'total': len(verdicts),
        'pass': sum(1 for v in verdicts if v['verdict'] == 'PASS'),
        'wa': sum(1 for v in verdicts if v['verdict'] == 'WA'),
    }
    exit_code = 0 if summary['total'] and summary['pass'] == summary['total'] else 1
    result = {'summary': summary, 'verdicts': verdicts, 'exit_code': exit_code,
              'report_path': report_path, 'strict_laws': strict_laws,
              'fingerprint': fingerprint_of(_module_from_spec(spec))}
    if report_path:
        _write_report(report_path, result)
    return result


def _write_report(report_path: str, payload: Dict[str, Any]) -> None:
    try:
        d = os.path.dirname(os.path.abspath(report_path))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _module_from_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """spec JSON → module dict（供 Iron Laws / bootstrap 复用）。

    审计修复（P1，bootstrap 恒假阴性）：改前只搬 name/fp/sig/laws/exports，
    **丢掉 imports 与 tests** —— 于是任何 spec 派生出来的 module 都恒违反
    Law IV（NoTestsDefined）、Law VII（NoCoreImport）、Law XIV（NoNegativeTest），
    `bootstrap(spec=...)` 永远过不了第 1 步（文档承诺的 spec→impl→verify 闭环失效）。
    现在把 `to_spec_json()` 写进 spec 的字段**逐项还原**（保持往返可逆）：
    imports（meta.imports）与 tests（input/output/error → `(输入, 期望)` 对）。
    """
    m = _new_module(spec.get('spec') or 'spec_module')
    m['version'] = spec.get('version') or m['version']
    meta = spec.get('meta') or {}
    imports = meta.get('imports') if isinstance(meta, dict) else None
    if not imports:
        imports = spec.get('imports') or []
    m['imports'] = [str(i) for i in imports]
    for op in spec.get('operations') or []:
        tests = []
        for t in op.get('tests') or []:
            if not isinstance(t, dict):
                continue
            inp = _join_input_nodes(t.get('input') or [])
            err = t.get('error')
            if err:
                # 反向映射：`to_spec_json` 把 MD 的裸 `⊥`（未指定错误名）序列化成
                # 默认 'TypeError'；还原成裸 `⊥` 才能保持"spec → module"与
                # 直接读 MD 的测试语义等价（具体错误名则原样保留）。
                expected = '⊥' if str(err) == 'TypeError' else '⊥ %s' % err
            else:
                expected = _plain_to_sigma(t.get('output'))
            tests.append((inp, expected))
        m['ops'].append({'name': op.get('name'), 'fp': op.get('fingerprint'),
                         'sig': f"{op.get('name')} : "
                                f"{' × '.join((op.get('signature') or {}).get('params') or [])}"
                                f" → {return_type_of(op)}",
                         'laws': [l.get('predicate', '') for l in op.get('laws') or []],
                         'tests': tests, 'mode': 'sig', 'has_pre': False, 'has_post': False,
                         'pre': None, 'post': None, 'definition': []})
    m['exports'] = sorted({op.get('name') for op in spec.get('operations') or []})
    # spec 里可能没有 Exports 概念 → 不伪造"有 Exports"，但要把 imports 带上，
    # 否则 Law VII 恒定失败（见上）。
    return m


def _join_input_nodes(nodes) -> str:
    """spec 的 input 节点列表 → MD 测试的输入表达式串（`_split_input` 的逆）。"""
    if not isinstance(nodes, list):
        return _plain_to_sigma(nodes)
    parts = [_plain_to_sigma(n) for n in nodes]
    return ', '.join(parts)


def _plain_to_sigma(value) -> str:
    """普通值 → sigma 字面量文本（供 spec → module 回填测试期望值）。"""
    if value is None:
        return '⊥'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '[' + ', '.join(_plain_to_sigma(v) for v in value) + ']'
    return json.dumps(value, ensure_ascii=False)


def return_type_of(op: Dict[str, Any]) -> str:
    return (op.get('signature') or {}).get('returns') or 'Any'


def _load_impl_symbols(path: str) -> Dict[str, Callable]:
    """从实现文件挑出与 operations 同名的可调用（sigma-impl-verify.py:56 语义）。"""
    if not os.path.isfile(path):
        raise SpecError(f'实现文件不存在: {path}')
    name = re.sub(r'\W+', '_', os.path.basename(path)) + '_impl'
    spec_obj = importlib.util.spec_from_file_location(name, path)
    if spec_obj is None or spec_obj.loader is None:
        raise SpecError(f'无法加载实现文件: {path}')
    mod = importlib.util.module_from_spec(spec_obj)
    sys.modules[name] = mod
    try:
        spec_obj.loader.exec_module(mod)          # 实现属调用方提供的可信代码
    except Exception as exc:
        raise SpecError(f'实现导入失败: {type(exc).__name__}: {exc}') from exc
    symbols: Dict[str, Callable] = {}
    for attr in ('OPERATIONS', 'OPS', '_OPS'):
        val = getattr(mod, attr, None)
        if isinstance(val, dict):
            symbols.update({k: v for k, v in val.items() if callable(v)})
    for k, v in vars(mod).items():
        if callable(v) and getattr(v, '__module__', None) == mod.__name__:
            symbols.setdefault(k, v)
    return symbols


# ---------------------------------------------------------------------------
# 8. sigma-bootstrap：spec → impl 骨架 → verify 闭环（docs/41 §A2）
# ---------------------------------------------------------------------------

_SKELETON_TMPL = '''# -*- coding: utf-8 -*-
"""由 vools.actus.sigma.bootstrap 生成的实现骨架。

规约指纹: {fingerprint}
每个函数对应 spec 中一个 operation，签名与 preconditions 来自 spec，
实现体留 TODO —— 填完再跑 verify 闭环。
"""

__spec__ = {spec_id!r}
__version__ = {version!r}
__fingerprint__ = {fingerprint!r}

'''


def render_impl_skeleton(spec: Dict[str, Any]) -> str:
    """由 spec JSON 生成 Python 实现骨架（每个 operation 一个 stub）。"""
    out = [_SKELETON_TMPL.format(
        fingerprint=fingerprint_of(_module_from_spec(spec)),
        spec_id=spec.get('spec'), version=spec.get('version'))]
    for op in spec.get('operations') or []:
        name = op.get('name')
        params = (op.get('definition') or {}).get('params') or \
                 [f'a{i}' for i in range(len((op.get('signature') or {}).get('params') or []))]
        out.append(f"def {name}({', '.join(params)}):")
        out.append(f'    """{name} : {" × ".join((op.get("signature") or {}).get("params") or [])}'
                   f' → {return_type_of(op)}  [fingerprint {op.get("fingerprint")}]"""')
        for pre in op.get('preconditions') or []:
            out.append(f'    # pre: {pre.get("expr")}  else -> {pre.get("error")}')
        for law in op.get('laws') or []:
            out.append(f'    # law: {law.get("predicate")}')
        out.append('    raise NotImplementedError  # TODO: implement per spec')
        out.append('')
    out.append('OPERATIONS = {')
    for op in spec.get('operations') or []:
        out.append(f"    {op['name']!r}: {op['name']},")
    out.append('}')
    return '\n'.join(out) + '\n'


def bootstrap(spec_path: Optional[str] = None, spec: Optional[Dict[str, Any]] = None,
              module: Optional[Dict[str, Any]] = None, impl_path: str = '',
              out_dir: str = '.', max_rounds: int = 3) -> Dict[str, Any]:
    """spec → impl 骨架 → verify 的闭环（docs/41 §A2 sigma-bootstrap）。

    三步各自显式回报，任何一步不过就整体判不过（不静默降级）：
      step1 规约可读且过 Iron Laws；
      step2 实现存在（缺失时生成骨架并标 `needs_impl`，不当作通过）；
      step3 judge 验收（spec 自洽或对着实现跑）。
    """
    report = {'ok': False, 'steps': [], 'artifacts': {}, 'rounds': 0}

    def step(name, ok, detail):
        report['steps'].append({'step': name, 'ok': bool(ok), 'detail': detail})

    # step 1: 规约可读
    if module is None:
        md_path = spec.get('meta', {}).get('source_path') if spec else None
        module = parse_module(md_path) if md_path else _module_from_spec(spec or {})
    laws = check_iron_laws(module, strict=False)
    if not laws['passed']:
        # 失败原因必须分型说清：改前只写"违规 N 条"，而"规范测试失败"不在
        # violations 里 → 会出现 "违规 0 条: []" 这种自相矛盾的失败说明。
        reasons = []
        if laws['violations']:
            reasons.append('违规 %d 条: %s' % (len(laws['violations']), laws['violations'][:5]))
        if laws.get('test_failures'):
            reasons.append('规范测试失败 %d/%d' % (
                laws['test_failures'], laws['tests']['total']))
        step('spec_readable', False, '; '.join(reasons) or 'Iron Laws 未过')
        report['laws'] = laws
        return report
    step('spec_readable', True, 'Iron Laws 通过')

    if spec is None:
        spec = to_spec_json(module)
        spec.setdefault('meta', {})['source_path'] = spec_path or ''

    spec_errors = validate_spec_json(spec)
    if spec_errors:
        step('spec_json_valid', False, '; '.join(spec_errors[:5]))
        report['spec_errors'] = spec_errors
        return report
    step('spec_json_valid', True, f'{len(spec.get("operations") or [])} 个操作')

    # 落盘 spec JSON（供 Omega 语料互喂，docs/41 §A3）
    if out_dir and not impl_path:
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, f"{re.sub(r'[^0-9A-Za-z_.-]+', '_', str(spec.get('spec')))}.spec.json")
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        report['artifacts']['spec_json'] = p

    # step 2: 实现
    if impl_path:
        if not os.path.isfile(impl_path):
            skel = os.path.join(out_dir or '.', 'impl_skeleton.py')
            os.makedirs(os.path.dirname(skel) or '.', exist_ok=True)
            with open(skel, 'w', encoding='utf-8') as f:
                f.write(render_impl_skeleton(spec))
            report['artifacts']['skeleton'] = skel
            step('impl_exists', False, f'实现缺失，已生成骨架 {skel}（needs_impl，不判通过）')
            return report
        step('impl_exists', True, impl_path)
    else:
        step('impl_exists', True, 'spec 自洽模式：用 spec 自带 definition 求值')

    # step 3: judge
    judged = None
    for _round in range(max(1, max_rounds)):
        report['rounds'] += 1
        judged = judge_spec(spec=spec, submission_path=impl_path or None,
                            report_path=os.path.join(out_dir, 'judge_report.json')
                            if out_dir else '')
        if judged['exit_code'] == 0:
            break
    step('judge', judged is not None and judged['exit_code'] == 0,
         f"pass {judged['summary']['pass']}/{judged['summary']['total']}" if judged else 'no judge')
    report['judge'] = judged
    report['ok'] = all(s['ok'] for s in report['steps'])
    return report


# ---------------------------------------------------------------------------
# 9. verify 入口 + 语言路由（docs/41 §A1 / §A3 三门之「sigma 验证器」）
# ---------------------------------------------------------------------------

def verify_module(module: Dict[str, Any], strict: bool = True) -> Dict[str, Any]:
    """对已解析模块做完整验证：Iron Laws + 规范测试。"""
    report = check_iron_laws(module, strict=strict)
    report['verdict'] = 'pass' if report['passed'] else 'fail'
    return report


def sigma_block_is_loadable(text: str) -> Tuple[bool, Optional[str]]:
    """docs/41 §A1 校验：sigma 块内容须可被 sigma 解析器加载。"""
    body = extract_sigma_block(text) if '```' in (text or '') else (text or '')
    if not body.strip():
        return (False, 'sigma 规约块为空')
    try:
        module = parse_module_text(body)
    except Exception as exc:                          # 解析器不期望抛，抛了也别吞
        return (False, f'sigma 解析异常: {type(exc).__name__}: {exc}')
    if not module['ops'] and not module['fns']:
        return (False, 'sigma 规约块未定义任何操作（无 ## Operation / Fingerprint）')
    # 审计修复（P1）：只有声明函数、没有任何 Operation → 没有可执行操作，
    # 不能算"可加载"。改前守卫是 `not ops and not fns`，一个残留的声明 fn
    # 就能让"零操作规约"通过（实测漏写 Fingerprint 时 ops=0 / fns=['f'] → True）。
    if not module['ops']:
        return (False, 'sigma 规约块没有任何 Operation（只有签名声明）')
    return (True, None)


def run_sigma_block(text: str, as_json: bool = False) -> Tuple[str, str, int]:
    """sigma 语言路由的执行入口（由 vools.bridge.md runner 调用）。

    契约与三端验证器一致：stdout 为报告，stderr 为人类可读说明，
    exit code 0=过 / 1=不过。**解析失败也返回 1 并明确报错，不静默降级。**
    """
    body = extract_sigma_block(text) if '```' in (text or '') else (text or '')
    if not body.strip():
        return '', 'sigma: 规约块为空（缺 ## Operation / Fingerprint）', 1
    try:
        module = parse_module_text(body)
    except Exception as exc:
        return '', f'sigma: 规约解析失败 {type(exc).__name__}: {exc}', 1
    if not module['ops'] and not module['fns']:
        return '', 'sigma: 规约块未定义任何操作', 1
    # 审计修复（P1）：守卫必须按 **ops** 判。改前 `not ops and not fns` 让
    # "漏写 Fingerprint 的 Operation 被降级成声明 fn"这种情况直接通过（实测
    # ops=0 / fns=['f'] → run_sigma_block exit 0），即零操作规约真空通过。
    if not module['ops']:
        return '', 'sigma: 规约块没有任何 Operation（只有签名声明，无可执行操作）', 1

    report = verify_module(module)
    buf = io.StringIO()
    if as_json:
        json.dump(report, buf, ensure_ascii=False, indent=2, default=str)
    else:
        buf.write(f"# Sigma 验证报告 — {report['module']}\n")
        buf.write(f"指纹: {report['fingerprint']}\n")
        buf.write(f"判定: {report['verdict'].upper()}\n\n")
        buf.write('## Iron Laws (17)\n')
        for law in report['laws']:
            if law.get('status') == 'advisory' or law['id'] == 'XIII':
                mark = 'ADVISORY'
            elif law.get('status') == 'skipped':
                # 审计修复（P3）：未声明章节 → 本条**没查**，如实标 SKIPPED，
                # 不能和"查过且通过"共用 PASS（消费方会误读成已检查）。
                mark = 'SKIPPED'
            else:
                mark = 'PASS' if not law['violations'] else 'FAIL'
            buf.write(f"  Law {law['id']:<5} {law['zh']} [{law['key']}]: {mark}\n")
        skipped = report.get('skipped_laws') or []
        if skipped:
            buf.write('\n## 未检查（未声明，不等同通过）\n')
            for law in skipped:
                buf.write(f"  Law {law['id']}: {law.get('skip_reason', '')}\n")
        for name, reason in (report.get('supplemental_skipped') or {}).items():
            buf.write(f"  {name}: {reason}\n")
        failed = report['failed_laws']
        if failed:
            buf.write('\n## 违规\n')
            for law in failed:
                for v in law['violations']:
                    buf.write(f"  Law {law['id']}: {v}\n")
        sup = {k: v for k, v in report['supplemental'].items() if v}
        if sup:
            buf.write('\n## 补充细则\n')
            for k, v in sup.items():
                for item in v:
                    buf.write(f"  {k}: {item}\n")
        t = report['tests']
        buf.write(f"\n## 规范测试\n  {t['passed']}/{t['total']} passed\n")
        for f in t['failures'][:20]:
            buf.write(f"    ✗ {f['op']}: {f['input']} → 期望 {f['expected']}"
                      f" 实际 {f['actual']}\n")
    out = buf.getvalue()
    if report['passed']:
        return out, '', 0
    return out, f"sigma 规约未过门禁：{len(report['violations'])} 条违规", 1
