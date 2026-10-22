"""契约校验：.actus.schema.md + action.schema.json + docs/03 §6 + docs/04 依赖图 + docs/10 新字段。

校验分层：
1. schema 校验（.actus.schema.md 走内置 YAML 校验；旧格式走 contracts/action.schema.json，jsonschema draft-07）；
2. 规范细则校验（entry 指向真实代码块、args 为合法 schema、
   triggers 语义、secrets 声明、ai 元数据等）；
3. 依赖图校验（deps 存在性 + 循环检测，跨动作集合级）。

双格式兼容：
- 形式 A（旧）：```json #!cfg 内联元数据块 → JSON Schema 校验
- 形式 B（新）：.actus.schema.md YAML front-matter → 内置规则校验
"""

__all__ = ['validate_action', 'validate_graph', 'analyze_graph', 'check_entry_block',
           'check_args_schema', 'check_triggers', 'check_secrets',
           'check_block_languages', 'language_notices',
           'validate_schema_md', 'check_schema_md_structure',
           'check_classification', 'classification_notices', 'normalize_multi_field',
           # 资产化治理（future_plan §3 修订落地）
           'check_platform', 'check_id_namespace', 'check_usage_executable',
           'check_self_contained', 'check_trust_tests', 'resolve_test_binding',
           'check_secrets_hardcode', 'check_omega_gate', 'governance_notices']

import json
import os
import re
import sys
from typing import Dict, List, Tuple

from .errors import ActionError
from .model import Action, parse_cfg_from_file
from .constants import (
    TRUST_LEVELS, PLATFORMS,
    KIND_LEVELS, PURPOSE_LEVELS, INDUSTRY_LEVELS, TRIGGER_DECL_LEVELS,
    is_known_kind, is_known_purpose, is_known_industry, is_known_trigger_decl,
    is_known_license, is_known_pricing, is_known_declared_feature,
    # 资产化治理
    is_known_platform, is_namespaced_id, is_secret_sensitive_name,
    SECRET_SENSITIVE_HARDCODE_RE,
)

def _resolve_schema_path() -> str:
    """定位 action.schema.json。

    contracts/ 保留在 Actus 仓库（docs/32 迁移约定：仓库只留 .md/.json），
    而本模块已迁入 vools.actus，故不能仅按模块相对路径推断。
    优先级：
      1. ACTUS_REPO_ROOT/contracts/action.schema.json
      2. 模块相对路径（自带 contracts/ 时）
      3. 从 CWD 向上回溯找 contracts/action.schema.json
    """
    candidates = []
    root = os.environ.get('ACTUS_REPO_ROOT')
    if root:
        candidates.append(os.path.join(root, 'contracts', 'action.schema.json'))
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'contracts', 'action.schema.json'))
    cur = os.path.abspath(os.getcwd())
    for _ in range(6):
        candidates.append(os.path.join(cur, 'contracts', 'action.schema.json'))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]


_SCHEMA_PATH = _resolve_schema_path()

_schema_cache = None


def _load_schema() -> dict:
    """加载 action.schema.json（带缓存），用于契约校验。"""
    global _schema_cache
    if _schema_cache is None:
        with open(_SCHEMA_PATH, 'r', encoding='utf-8') as f:
            _schema_cache = json.load(f)
    return _schema_cache


def validate_action(action: Action) -> List[str]:
    """校验单个动作，返回错误列表（空 = 通过）。

    覆盖 docs/03 §6 全部五条基准校验 + §7.3 契约自检 + docs/10 新增字段校验。
    """
    errors: List[str] = []
    meta = action.meta

    # 1) schema 校验
    try:
        import jsonschema
        jsonschema.validate(instance=meta, schema=_load_schema())
    except ImportError:
        # 无 jsonschema 时退化为手工必填校验（见下），并提示
        errors.append('runtime: 未安装 jsonschema，已跳过 schema 级校验（pip install jsonschema）')
    except Exception as e:  # jsonschema.ValidationError
        errors.append(f'schema: {getattr(e, "message", str(e))}')

    # 2) 必填字段（双重保险，即使无 jsonschema 也强制）
    for k in ('id', 'name', 'version', 'trust', 'entry'):
        if not meta.get(k):
            errors.append(f'schema: 必填字段缺失: {k}')

    # 2b) platform 必填 + 取值合法（future_plan §3 #1：不再缺省全平台）
    if not meta.get('platform'):
        errors.append('schema: 必填字段缺失: platform')
    errors.extend(check_platform(meta))

    # 2c) id 命名约束（future_plan §3 #6：至少两段点分小写）
    errors.extend(check_id_namespace(meta))

    # 3) trust 取值
    if meta.get('trust') not in TRUST_LEVELS:
        errors.append(f'schema: trust 非法: {meta.get("trust")!r}（仅允许 {TRUST_LEVELS}）')

    # 3b) 分类体系 v2.0：kind 验证（未知值 → 打回，docs/03 §2.4）
    kind = meta.get('kind')
    if kind is not None and not is_known_kind(kind):
        errors.append(
            f'schema: kind 非法: {kind!r}（仅允许 {KIND_LEVELS}，'
            'docs/03 §2.4 未知 kind 打回——决定执行逻辑，错误值导致执行混乱）')

    # 4) usage 类型（无 jsonschema 时的 fallback 检查）
    if 'usage' in meta and not isinstance(meta.get('usage'), str):
        errors.append(f'schema: usage 必须是字符串，实际为 {type(meta.get("usage")).__name__}')

    # 4) entry 指向存在的代码块
    errors.extend(check_entry_block(action))

    # 4b) 代码块语言标记合法且可路由（docs/03 §6.2 后半句 + §6.5，docs/41 §A1）
    errors.extend(check_block_languages(action))

    # 5) args 契约自检
    errors.extend(check_args_schema(meta))

    # 6) triggers 语义校验（docs/10 §B.1）
    errors.extend(check_triggers(meta))

    # 7) secrets 声明校验（docs/10 §E.1）
    errors.extend(check_secrets(meta))

    # 8) ai 元数据校验（docs/10 §D.4）
    errors.extend(check_ai_meta(meta))

    # ── 资产化治理（future_plan §3 修订落地）─────────────────────
    # 9) 单文件自包含：entry 不得引用动作目录内同名模块（docs/47 §3）
    errors.extend(check_self_contained(action))

    # 10) trust↔测试绑定：audit/trusted 必须有测试（docs/47 §4）
    errors.extend(check_trust_tests(action))

    # 11) secrets 强制：硬编码凭据 / 未声明敏感 env（future_plan §3 #4）
    errors.extend(check_secrets_hardcode(action))

    # 12) Ω-gate 编排契约（kind=bundle 显式编排类型必须声明，docs/47 §5）
    errors.extend(check_omega_gate(action))

    # 13) usage 可执行形态（存在但纯描述 → 打回，future_plan §3 #8）
    errors.extend(check_usage_executable(meta))

    return errors


def normalize_multi_field(values, known_levels: Tuple[str, ...], max_n: int = 5) -> Tuple[List[str], List[str]]:
    """多值字段标准化（docs/03 §2.3）。

    小写归一 → 去重 → 截断到 max_n；已知值进 valid，未知值进 warnings（保留不丢弃，
    前向兼容：未来追加已知值后这些值立即生效）。

    V-23（寻虫 2026-10-22）：旧实现只截已知值（`valid = valid[:max_n]`），
    docstring 承诺的"截断到 max_n"名存实亡——6 值（3 已知+3 未知）max_n=5
    时仍 6 个值被接受，还回显"已截断"假话。现在按总数截断：
    已知值优先保留，未知值补位到 max_n 处即丢弃（丢弃量如实上报）。

    Returns:
        (valid, warnings) —— valid 是归一后的已知值列表，warnings 是未知值提示。
    """
    if values is None:
        return [], []
    if isinstance(values, str):
        values = [values]
    valid: List[str] = []
    unknowns: List[str] = []
    seen = set()
    for v in values:
        if not isinstance(v, str) or not v.strip():
            continue
        norm = v.strip().lower()
        if norm in seen:
            continue
        seen.add(norm)
        if norm in known_levels:
            valid.append(norm)
        else:
            unknowns.append(norm)

    # 截断（V-23）：总量（已知+未知）≤ max_n。已知优先保留，未知补位。
    if len(valid) + len(unknowns) > max_n:
        kept_known = valid[:max_n]
        space = max_n - len(kept_known)
        kept_unknown = unknowns[:space]
        dropped_known = len(valid) - len(kept_known)
        dropped_unknown = len(unknowns) - len(kept_unknown)
        warnings = [f'未知值: {v!r}（已接受，但可能影响索引覆盖）'
                    for v in kept_unknown]
        parts = []
        if dropped_known:
            parts.append('%d 个已知值' % dropped_known)
        if dropped_unknown:
            names = '、'.join(repr(v) for v in unknowns[space:])
            parts.append('%d 个未知值: %s' % (dropped_unknown, names))
        if parts:
            warnings.append('值数量超出上限 %d，已截断（丢弃 %s）'
                            % (max_n, '、'.join(parts)))
        valid = kept_known
    else:
        warnings = [f'未知值: {v!r}（已接受，但可能影响索引覆盖）'
                    for v in unknowns]
    return valid, warnings


def check_classification(meta: Dict) -> List[str]:
    """分类体系 v2.0 验证（docs/03 §2.4 验证分级表）——只含打回级。

    kind 是唯一打回级字段：它决定系统如何执行该动作（exec/link/demo/...），
    错误值导致执行逻辑混乱（如把 link 当 exec 执行）。已在 validate_action
    第 3b 步内联校验，此函数供独立调用（如 CLI check 单项验证）。
    """
    errors: List[str] = []
    kind = meta.get('kind')
    if kind is not None and not is_known_kind(kind):
        errors.append(
            f'schema: kind 非法: {kind!r}（仅允许 {KIND_LEVELS}，docs/03 §2.4）')
    return errors


def classification_notices(meta: Dict) -> List[str]:
    """分类体系 v2.0 警告（docs/03 §2.4 验证分级表）——警告级，不判失败。

    purpose/industry/trigger_decl 未知值 → 警告（分类标签，不影响执行逻辑，
    只影响索引覆盖；未来追加已知值后立即生效）。多值字段超限 → 警告。
    kind × purpose 语义冲突 → 警告（docs/03 §2.4 冲突检测）。
    """
    notices: List[str] = []

    # purpose（多值，默认 [utility]）
    # V-26（寻虫 2026-10-22）：旧判空 `purpose in ('', [], ('',))` 漏
    # purpose=[''] 形态（normalize 已静默丢空串，此处却不再提示"为空按
    # [utility] 处理"），与 None 分支行为不一致。改为看归一后的 valid。
    purpose = meta.get('purpose')
    if purpose is not None:
        purpose_valid, warns = normalize_multi_field(purpose, PURPOSE_LEVELS)
        notices.extend(f'purpose {w}' for w in warns)
        if not purpose_valid:
            notices.append('purpose 为空，默认按 [utility] 处理')

    # industry（多值，默认 [general]）
    industry = meta.get('industry')
    if industry is not None:
        valid, warns = normalize_multi_field(industry, INDUSTRY_LEVELS)
        notices.extend(f'industry {w}' for w in warns)

    # trigger 声明（多值，默认 [manual]）——注意这是声明字段，
    # 与 ## Triggers 段（triggers.py 真源）互补，不校验一致性
    trigger_decl = meta.get('trigger')
    if trigger_decl is not None and not isinstance(trigger_decl, (list, str)):
        notices.append(f'trigger 必须是字符串或列表，实际为 {type(trigger_decl).__name__}')
    elif trigger_decl is not None:
        _, warns = normalize_multi_field(trigger_decl, TRIGGER_DECL_LEVELS)
        notices.extend(f'trigger {w}' for w in warns)

    # kind × purpose 语义冲突检测（警告级，docs/03 §2.4）
    kind = meta.get('kind')
    kind_l = str(kind).lower() if kind else ''
    purpose_list, _ = normalize_multi_field(meta.get('purpose') or 'utility', PURPOSE_LEVELS)
    if kind_l == 'doc' and any(p in ('source', 'sink', 'transform', 'compute', 'orchestrator') for p in purpose_list):
        notices.append(
            f'kind=doc 与 purpose={purpose_list} 语义冲突：纯文档不应声明执行用途（docs/03 §2.4）')
    if kind_l == 'template' and 'orchestrator' in purpose_list:
        notices.append(
            f'kind=template 与 purpose=[orchestrator] 语义冲突：模板不编排（docs/03 §2.4）')

    # ── 生态层声明（docs/03 §5.2 许可证 / §5.4 自声明特性） ──

    # license（单值，默认 mit）——未知值警告（不阻断：作者可能用自定义许可证）
    license_decl = meta.get('license')
    if license_decl and not is_known_license(license_decl):
        notices.append(
            f'license 未知值: {license_decl!r}（默认 mit；已接受，'
            '但消费者可能无法识别——建议补 license_url）')
    if str(license_decl).lower() == 'custom' and not meta.get('license_url'):
        notices.append('license=custom 但缺 license_url（许可证链接，便于使用者查阅）')

    # pricing（单值，默认 free）——paid/subscription 在未接支付前按 gated 免费放行 + 警告
    pricing_decl = meta.get('pricing')
    if pricing_decl and not is_known_pricing(pricing_decl):
        notices.append(f'pricing 未知值: {pricing_decl!r}（默认 free）')
    if str(pricing_decl).lower() in ('paid', 'subscription'):
        notices.append(
            f'pricing={pricing_decl} 已声明，但当前版本未接支付通道：'
            '按 gated 免费放行（docs/03 §5.2 gated 付费预留）')

    # declared_features（多值，默认 []）——未知值警告；与扫描不符的检测在
    # trust 决策侧完成（本模块只做形状与已知值校验）
    declared = meta.get('declared_features')
    if declared is not None and not isinstance(declared, (list, str)):
        notices.append(f'declared_features 必须是列表或字符串，实际为 {type(declared).__name__}')
    elif declared:
        values = declared if isinstance(declared, list) else [declared]
        unknown = [v for v in values
                   if isinstance(v, str) and not is_known_declared_feature(v)]
        if unknown:
            notices.append(f'declared_features 未知值: {unknown}（已知值见 constants.DECLARED_FEATURE_LEVELS）')

    # demo（string，默认 ""）——路径不存在 → 警告（演示文件降低采用门槛）
    demo = meta.get('demo')
    if demo:
        candidates = [str(demo), os.path.join(os.path.dirname(action_path_of(meta) or ''), str(demo))]
        if not any(os.path.isfile(c) for c in candidates):
            notices.append(f'demo 文件不存在: {demo!r}（演示文件降低采用门槛，建议补齐）')

    return notices


def action_path_of(meta: Dict) -> str:
    """meta 内记录的动作文件路径（缺 key 返回空串）。

    解析顺序（与 check_self_contained / check_trust_tests 的 abs_path 口径一致）：
      1. meta['_path']：indexer/扫描侧注入的绝对路径；
      2. meta['_abs_path']：author/scattered 侧的注入；
      3. meta['path']：Action 自带的相对路径（parse_cfg_from_file 单独调用时）。
    相对 path 按 ACTUS_REPO_ROOT 解析，保证 demo 等相对字段可定位。
    """
    abs_path = meta.get('_path') or meta.get('_abs_path') or meta.get('path') or ''
    if abs_path and not os.path.isabs(abs_path):
        env = os.environ.get('ACTUS_REPO_ROOT')
        if env:
            abs_path = os.path.join(env, abs_path)
    return abs_path


def check_entry_block(action: Action) -> List[str]:
    """entry 字段必须对应某个带 tag 的代码块（docs/03 §6.2）。

    同时校验 cfg.entry 与文件级 #!entry 一致（两者并存时不允许漂移：
    cfg.entry 是唯一权威，docs/03 §2）。
    """
    errors: List[str] = []
    entry = action.meta.get('entry')
    if not entry:
        return errors
    tags = set()
    for b in action.blocks:
        tags.update(b['tag'])
    if entry not in tags:
        errors.append(f'semantic: entry={entry!r} 未找到对应 tag 的代码块')
    fd_entry = action.file_directives.get('entry')
    if fd_entry and fd_entry != entry:
        errors.append(
            f'semantic: 文件级 #!entry={fd_entry!r} 与 cfg.entry={entry!r} 不一致'
            '（cfg.entry 为唯一权威，docs/03 §2）')
    return errors


def check_block_languages(action: Action) -> List[str]:
    """代码块语言标记必须合法且已注册（docs/03 §6.5）。

    判定范围只含**会被执行的块**：
      * entry 指向的块（executor 的 `only=[action.entry]` 必然跑它）；
      * 任何带 tag 的块（workflow 节点按 `block` 指名、`#!only` 按 tag 挑选，都可能跑）；
      * cfg 元数据块本身按约定必须是 json（已由 model.parse_cfg 强约束），跳过。

    **不带 tag 的块是文档围栏**（实测仓库内 145 个无 tag 的 bash 示例、以及 json/toml/
    yaml/xml 说明块），执行期按 tag 过滤根本不会跑到，因此一律不判 —— 否则 110 个既有
    动作当场全红。这条边界不是和稀泥：docs/03 §6.5 管的是"路由"，不是"文档写法"。

    与 §6.2 的"语言可路由"同源：两处都走 `vools.bridge.md.runner.is_routable`
    这一个真源，避免 runner 与 actus 各持一份语言清单而漂移。
    """
    errors: List[str] = []
    try:
        from vools.bridge.md.runner import is_routable
    except ImportError as exc:
        return [f'runtime: 语言路由表不可用（vools.bridge.md.runner 导入失败：{exc}）']

    entry = action.meta.get('entry')
    for b in action.blocks or []:
        lang = (b.get('language') or '').strip().lower()
        tags = list(b.get('tag') or [])
        if 'cfg' in (b.get('directives') or {}):
            continue                     # 元数据块，不是执行体
        if not tags:
            continue                     # 无 tag 且非 entry → 文档围栏，不参与路由判定
        if is_routable(lang):
            continue
        role = 'entry' if entry in tags else f'tag={",".join(tags)}'
        errors.append(
            f'language: 代码块语言标记 {lang!r}（{role}）未注册，'
            f'不可路由（docs/03 §6.5）')
    return errors


def language_notices(action: Action) -> List[str]:
    """无 tag 文档围栏里不可路由的语言标记 → 只提示，不判失败。

    存在意义是"别装作没看见"：这些块现在跑不到，但一旦有人给它们补上 tag 就会
    立刻进入 §6.5 硬门。列出来供 `actus check` 展示，不作为 errors 计数。
    """
    notices: List[str] = []
    try:
        from vools.bridge.md.runner import is_routable
    except ImportError:
        return notices
    for b in action.blocks or []:
        lang = (b.get('language') or '').strip().lower()
        if (b.get('tag') or []) or 'cfg' in (b.get('directives') or {}):
            continue
        if lang and not is_routable(lang):
            notices.append(f'info: 文档围栏 {lang!r} 不可路由（无 tag，执行期不跑）')
    return notices


def check_args_schema(meta: dict) -> List[str]:
    """args 若声明，必须是可加载的 JSON Schema（docs/03 §7.3.6）。"""
    args = meta.get('args')
    if args is None:
        return []
    if not isinstance(args, dict):
        return ['semantic: args 必须是 JSON Schema object 或 null']
    try:
        import jsonschema
        jsonschema.Draft7Validator.check_schema(args)
    except ImportError:
        return []
    except Exception as e:
        return [f'semantic: args 不是合法 JSON Schema: {e}']
    return []


# cron 五字段标准区间（V-24 值域校验的真源）
_cron_field_ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _cron_expr_range_ok(expr: str) -> bool:
    """cron 五字段值域校验（V-24，寻虫 2026-10-22）。

    形状正则放过 '99 99 * * *'（99 分 99 时）、'0 0 31 2 *'（2 月 31 日）——
    非法定时表达式进索引进调度器（webhook/cron 消费面）才炸。
    两层校验：
      1. 单字段区间：各字段数字必须在 min/hour/day/month/week 标准区间内；
      2. 跨字段日历冲突：month=2 时 day>29、month∈{4,6,9,11} 时 day>30
         ——这类组合字段值各自合法但日历上永远不触发（审计 V-24 实例）。
    星号/段通配放行。
    """
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    # 第一遍：单字段区间校验，同时收集 day/month 数字
    day_vals: List[int] = []
    month_vals: List[int] = []
    for idx, (f, (lo, hi)) in enumerate(zip(fields, _cron_field_ranges)):
        if f == '*':
            continue
        for part in f.replace('/', '-').split('-'):
            if not part.isdigit():
                continue  # 段/步长等其他形态由形状正则兜住
            n = int(part)
            if not (lo <= n <= hi):
                return False
            if idx == 2:            # day 字段
                day_vals.append(n)
            elif idx == 3:          # month 字段
                month_vals.append(n)
    # 第二遍：跨字段日历冲突
    for m in month_vals:
        if m == 2 and any(d > 29 for d in day_vals):
            return False
        if m in (4, 6, 9, 11) and any(d > 30 for d in day_vals):
            return False
    return True


def check_triggers(meta: dict) -> List[str]:
    """triggers 字段语义校验（docs/10 §B.1）。

    - cron 类型：expr 必须是合法 cron 表达式（5 字段）
    - watch 类型：path 必须为有效路径字符串
    - webhook 类型：如有 secret_header 必须非空
    - hotkey 类型：key 必须非空
    """
    errors: List[str] = []
    triggers = meta.get('triggers')
    if not triggers:
        return errors
    if not isinstance(triggers, list):
        return ['semantic: triggers 必须是数组']

    cron_field_re = re.compile(
        r'^(\*|[0-9]{1,2}(-[0-9]{1,2})?)(\/[0-9]+)?$'
    )

    for i, t in enumerate(triggers):
        if not isinstance(t, dict):
            errors.append(f'semantic: triggers[{i}] 必须是对象')
            continue
        ttype = t.get('type')
        if ttype not in ('cron', 'watch', 'webhook', 'hotkey', 'on_startup'):
            errors.append(f'semantic: triggers[{i}].type 非法: {ttype!r}')
            continue

        if ttype == 'cron':
            expr = t.get('expr')
            if not expr:
                errors.append(f'semantic: triggers[{i}] cron 缺少 expr')
            elif not isinstance(expr, str):
                errors.append(f'semantic: triggers[{i}].expr 必须是字符串')
            else:
                fields = expr.strip().split()
                if len(fields) != 5:
                    errors.append(f'semantic: triggers[{i}].expr 必须是 5 字段 cron 表达式')
                else:
                    shape_ok = True
                    for f in fields:
                        if not cron_field_re.match(f):
                            errors.append(f'semantic: triggers[{i}].expr 字段非法: {f!r}')
                            shape_ok = False
                            break
                    # V-24（寻虫 2026-10-22）：形状通过后再查值域——
                    # '99 99 * * *'、'0 0 31 2 *' 形状合法但越界，
                    # 非法定时表达式进索引进调度器才炸。
                    if shape_ok and not _cron_expr_range_ok(expr):
                        errors.append(
                            f'semantic: triggers[{i}].expr 值域非法'
                            f'（min0-59/hour0-23/day1-31/month1-12/week0-7）: {expr!r}')

        elif ttype == 'watch':
            path = t.get('path')
            if not path:
                errors.append(f'semantic: triggers[{i}] watch 缺少 path')
            elif not isinstance(path, str):
                errors.append(f'semantic: triggers[{i}].path 必须是字符串')

        elif ttype == 'hotkey':
            key = t.get('key')
            if not key:
                errors.append(f'semantic: triggers[{i}] hotkey 缺少 key')
            elif not isinstance(key, str):
                errors.append(f'semantic: triggers[{i}].key 必须是字符串')

        elif ttype == 'webhook':
            sh = t.get('secret_header')
            if sh is not None and (not isinstance(sh, str) or not sh.strip()):
                errors.append(f'semantic: triggers[{i}].secret_header 不能为空字符串')

    return errors


def check_secrets(meta: dict) -> List[str]:
    """secrets 字段语义校验（docs/10 §E.1）。

    - 每个元素必须有 provider 和 env
    - env 必须是合法环境变量名
    - provider 建议用反向域名风格（如 com.openai）但非强制
    """
    errors: List[str] = []
    secrets = meta.get('secrets')
    if not secrets:
        return errors
    if not isinstance(secrets, list):
        return ['semantic: secrets 必须是数组']

    env_name_re = re.compile(r'^[A-Z][A-Z0-9_]*$')
    providers = set()

    for i, s in enumerate(secrets):
        if not isinstance(s, dict):
            errors.append(f'semantic: secrets[{i}] 必须是对象')
            continue
        provider = s.get('provider')
        env = s.get('env')
        if not provider:
            errors.append(f'semantic: secrets[{i}] 缺少 provider')
        if not env:
            errors.append(f'semantic: secrets[{i}] 缺少 env')
        elif not env_name_re.match(env):
            errors.append(f'semantic: secrets[{i}].env 必须是合法环境变量名（大写字母数字下划线，如 OPENAI_API_KEY）')

        if provider and provider in providers:
            errors.append(f'semantic: secrets[{i}].provider 重复: {provider!r}')
        if provider:
            providers.add(provider)

        scopes = s.get('scopes')
        if scopes is not None:
            if not isinstance(scopes, list):
                errors.append(f'semantic: secrets[{i}].scopes 必须是数组')
            elif any(not isinstance(sc, str) for sc in scopes):
                errors.append(f'semantic: secrets[{i}].scopes 元素必须是字符串')

    return errors


def check_ai_meta(meta: dict) -> List[str]:
    """ai 元数据字段语义校验（docs/10 §D.4）。"""
    errors: List[str] = []
    ai = meta.get('ai')
    if not ai:
        return errors
    if not isinstance(ai, dict):
        return ['semantic: ai 必须是对象']

    if 'generated' in ai and not isinstance(ai.get('generated'), bool):
        errors.append('semantic: ai.generated 必须是布尔值')
    if 'author' in ai and not isinstance(ai.get('author'), str):
        errors.append('semantic: ai.author 必须是字符串')
    if 'evolved_from' in ai and ai.get('evolved_from') is not None \
            and not isinstance(ai.get('evolved_from'), str):
        errors.append('semantic: ai.evolved_from 必须是字符串或 null')
    if 'evolve_policy' in ai and ai.get('evolve_policy') not in ('confirm', 'auto', 'off', None):
        errors.append('semantic: ai.evolve_policy 必须是 confirm/auto/off')

    return errors


# ════════════════════════════════════════════════════════════════════
# 资产化治理（future_plan §3 修订落地，docs/47）
# ────────────────────────────────────────────────────────────────────
# 薄：不重复 MCP/SKILL 官方治理规范，.actus.md 只保留最小执行契约；
# 厚：platform 必填 / 自包含 / trust↔测试 / secrets 强制 / Ω-gate /
#     id 命名 / usage 可执行——每条都有校验兜底，不做空壳。
# ════════════════════════════════════════════════════════════════════

# kind 豁免清单：非可执行资产（不参与 trust↔测试绑定）
_NON_EXEC_KINDS = ('demo', 'template', 'alias', 'doc', 'link')


def check_platform(meta: dict) -> List[str]:
    """platform 必填 + 取值合法（future_plan §3 #1，docs/03 §2 平台枚举）。

    历史缺陷：platform 为选填、缺省即全平台 → 动作无法表达真实运行域
    （如 adapter.cli.pandoc 只能跑在 windows/desktop），资产池按平台过滤失真。
    落地：缺字段报错（见 validate_action 2b），取值非法报错，多余值警告级。
    """
    errors: List[str] = []
    platforms = meta.get('platform')
    if platforms is None:
        return errors                     # 缺失已在 validate_action 2b 单独报
    if isinstance(platforms, str):
        platforms = [platforms]
    if not isinstance(platforms, list):
        return ['semantic: platform 必须是字符串或数组']
    unknown = [p for p in platforms
               if isinstance(p, str) and not is_known_platform(p)]
    if unknown:
        errors.append(
            f'semantic: platform 含未知值: {unknown}'
            f'（已知值 {PLATFORMS}，docs/03 §2 可使用平台）')
    if any(not isinstance(p, str) or not p.strip() for p in platforms):
        errors.append('semantic: platform 元素必须是非空字符串')
    return errors


def check_id_namespace(meta: dict) -> List[str]:
    """id 命名约束（future_plan §3 #6）：至少两段点分小写（反向域名风格）。

    注意：只做格式校验（actus.test.foo 格式合法仍通过），「测试味 id 不进
    资产池」的严格判定在 indexer 资产池层（结合 kind 与测试夹具引用豁免），
    否则引擎测试里引用的夹具动作会被通用校验打成 error，破坏测试。
    """
    errors: List[str] = []
    aid = meta.get('id')
    if aid and not is_namespaced_id(aid):
        errors.append(
            f'semantic: id {aid!r} 不符合资产池命名：至少两段点分小写'
            '（如 actus.hello / jump.push，docs/47 §3.4）')
    return errors


def check_usage_executable(meta: dict) -> List[str]:
    """usage 必须可执行（future_plan §3 #8）。

    usage 的存在意义是「一句话告诉我怎么跑」，纯描述文本不可执行。
    规则：
      - usage 缺失 / 非字符串 → 警告（governance_notices），不判失败
        （存量动作大量缺 usage，硬打回会连坐资产池）；
      - usage 存在但纯描述（不含 actus run / 动作 id / 函数式调用形态）→ 打回；
      - 极短占位符（如 'u'）无实义，视同缺失 → 仅警告，不判失败。
    """
    errors: List[str] = []
    usage = meta.get('usage')
    if usage is None or not isinstance(usage, str):
        return errors
    aid = meta.get('id') or ''
    text = usage.strip()
    if not text:
        return errors
    if 'actus run' in text or ' run ' in text or aid in text:
        return errors
    # 函数式调用形态（sigma 模板：`actus_<namespace>_<name>({...})`；
    # 一般动作：`<id>(args)` 或 `调用示例: foo(...)`）→ 可执行，不判失败。
    if '(' in text and ')' in text:
        if 'actus' in text or aid.split('.')[-1] in text or '调用示例' in text:
            return errors
    # 极短占位符（'u' 等）无描述语义，视同缺失 → 仅警告。
    if len(text) <= 3:
        return errors
    errors.append(
        f'semantic: usage 不可执行（docs/47 §3.5）：{usage!r}'
        '——应含可执行调用形态，如 `actus run <id> [args]`')
    return errors


def _extract_block_source(action: Action, tag: str) -> str:
    """从 body 提取指定 tag 代码块源码（近似解析，够静态扫描用）。

    blocks 只记录 {language, tag, directives}，不含源码；这里按常见围栏
    `` ```lang #!tag=a,b `` 与 `` ```lang #!entry `` 形态从 action.body 提取。
    提取不到返回空串（扫描侧保守跳过，不误报）。
    """
    body = action.body or ''
    if not body:
        return ''
    fence_re = re.compile(
        r'^```([^\n]*)\n(.*?)^```',
        re.MULTILINE | re.DOTALL,
    )
    for m in fence_re.finditer(body):
        header = m.group(1) or ''
        if tag in header:
            return m.group(2)
    return ''


def _repo_root_from_path(action: Action) -> str:
    """推断仓库根：动作绝对路径 <root>/actions/... → 上溯到 actions 目录的上级。

    支持多级子目录结构（actions/a.actus.md 与 actions/<sub>/a.actus.md 均命中）。

    无绝对路径（单文件校验、未过 indexer）时回退 ACTUS_REPO_ROOT / 当前目录。
    """
    abs_path = action.meta.get('_path') or getattr(action, 'path', '') or ''
    if abs_path:
        # action.path 可能是仓库相对路径（如 actions/x.actus.md），也可能是绝对路径
        if not os.path.isabs(abs_path):
            env = os.environ.get('ACTUS_REPO_ROOT')
            if env:
                abs_path = os.path.join(env, abs_path)
        norm = os.path.normpath(abs_path)
        parent = os.path.dirname(norm)
        # 逐级上溯直到父目录名 == 'actions'；找不到则放弃该分支
        while parent and os.path.basename(parent) != 'actions':
            next_parent = os.path.dirname(parent)
            if next_parent == parent:
                break
            parent = next_parent
        if os.path.basename(parent) == 'actions':
            return os.path.dirname(parent)
    env = os.environ.get('ACTUS_REPO_ROOT')
    if env:
        return env
    # 引擎代码侧仓库（vools/actus）作为兜底，便于包内种子动作自校验
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def resolve_test_binding(action: Action) -> Tuple[bool, List[str]]:
    """trust↔测试绑定解析（docs/47 §4）。

    判定顺序：
      1. meta.tests 显式声明（路径列表）→ 逐一检查文件存在；
      2. 自动推断：<root>/tests/**/*.py 内容包含完整动作 id（单词边界）。
    返回 (bound, refs)：bound=是否有测试绑定；refs=引用文件相对路径列表。
    """
    meta = action.meta
    aid = meta.get('id') or ''
    if not aid:
        return False, []

    declared = meta.get('tests')
    if declared:
        if isinstance(declared, str):
            declared = [declared]
        if isinstance(declared, list):
            root = _repo_root_from_path(action)
            refs = []
            for d in declared:
                if os.path.isabs(str(d)):
                    cand = str(d)
                else:
                    cand = os.path.join(root, str(d))
                if os.path.isfile(cand):
                    refs.append(str(d))
            if refs:
                return True, refs

    root = _repo_root_from_path(action)
    tests_dir = os.path.join(root, 'tests')
    if not os.path.isdir(tests_dir):
        return False, []
    refs: List[str] = []
    pat = re.compile(rf'(?<![\w.]){re.escape(aid)}(?![\w.])')
    for dirpath, _dirnames, filenames in os.walk(tests_dir):
        for fn in sorted(filenames):
            if not fn.endswith('.py'):
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                    if pat.search(f.read()):
                        refs.append(os.path.relpath(full, root).replace(os.sep, '/'))
            except OSError:
                continue
    return bool(refs), refs


def check_trust_tests(action: Action) -> List[str]:
    """trust↔测试绑定（future_plan §3 #3，docs/47 §4）。

    - trust=audit：必须带测试（缺绑定 → 打回：audit 级动作没有测试等于裸奔）；
    - trust=trusted：必须有回归记录（缺绑定 → 打回：trusted 是「可信」承诺，
      必须有可复跑的验证闭环）；
    - trust=sandbox：豁免（沙箱隔离本身就是安全边界，不强制测试）；
    - kind ∈ demo/template/alias/doc/link：非可执行资产，豁免。
    """
    errors: List[str] = []
    meta = action.meta
    trust = meta.get('trust')
    if trust not in ('audit', 'trusted'):
        return errors
    kind = str(meta.get('kind') or 'exec').lower()
    if kind in _NON_EXEC_KINDS:
        return errors

    bound, refs = resolve_test_binding(action)
    if bound:
        return errors
    hint = '（可用 meta.tests 显式声明测试文件，或补 tests/ 下引用该 id 的用例）'
    errors.append(
        f'trust: trust={trust} 但无测试绑定{hint}（docs/47 §4：'
        'audit 必须带测试，trusted 必须有回归记录）')
    return errors


def check_self_contained(action: Action) -> List[str]:
    """单文件自包含校验（future_plan §3 #2，docs/47 §3）。

    资产化动作必须「单文件可跑」：entry 代码块不得依赖动作目录内同名
    模块（相对导入另一个 .py）——否则复制/分发动作时漏文件即静默失败。

    豁免：
      - 标准库（sys.stdlib_module_names）；
      - 已安装第三方包（importlib.util.find_spec 命中且不在动作目录树内）；
      - vools 家族（运行时自动注入核心库，docs/08 §1 依赖注入约定）；
      - actuscore（引擎内置运行时，索引/执行环境注入，同属依赖注入约定）。
    仅静态正则扫描，查不到即跳过（不误报）。
    """
    errors: List[str] = []
    entry = action.meta.get('entry')
    if not entry:
        return errors
    source = _extract_block_source(action, entry)
    if not source:
        return errors

    import_re = re.compile(r'^\s*(?:from|import)\s+([a-zA-Z_]\w*)', re.MULTILINE)
    imported = set()
    for m in import_re.finditer(source):
        line = source[:m.start()].count('\n')
        # 跳过注释行内的 import 字样
        prefix = source.split('\n')[line].lstrip()
        if prefix.startswith('#'):
            continue
        imported.add(m.group(1))

    if not imported:
        return errors

    abs_path = action.meta.get('_path') or ''
    if not abs_path:
        return errors
    action_dir = os.path.dirname(os.path.normpath(abs_path))

    try:
        stdlib = set(sys.stdlib_module_names)  # py3.10+
    except AttributeError:
        stdlib = set()

    for mod in imported:
        if mod in stdlib or mod == 'vools' or mod.startswith('vools.') \
                or mod == 'actuscore' or mod.startswith('actuscore.'):
            continue
        # 动作目录内同名模块（相对导入 → 违约）
        if os.path.isfile(os.path.join(action_dir, mod + '.py')) or \
                os.path.isdir(os.path.join(action_dir, mod)):
            errors.append(
                f'selfcontained: entry 相对导入 {mod!r} 破坏单文件自包含'
                f'（{os.path.join(action_dir, mod + ".py")} 存在，docs/47 §3）')
            continue
        # 已安装包则豁免
        try:
            import importlib.util
            if importlib.util.find_spec(mod) is not None:
                continue
        except (ImportError, ValueError):
            pass
        errors.append(
            f'selfcontained: entry 导入 {mod!r} 既非标准库也非已安装包，'
            '无法确认自包含（docs/47 §3——资产动作应单文件可跑）')
    return errors


def check_secrets_hardcode(action: Action) -> List[str]:
    """secrets 强制（future_plan §3 #4，docs/47 §6）。

    静态扫描 entry 源码：
      - 硬编码敏感凭据（password/token/api_key/secret = "..."）→ 打回
        （凭据必须走 Vault 注入，不得落盘动作文件）；
      - 读取敏感 env（os.environ['X'] / os.getenv('X')，X 命中敏感字样）
        但未在 meta.secrets 声明 → 打回（声明缺失 → 运行时无注入）。
    豁免 ACTUS_* 系统级变量（引擎注入，与动作无关）。
    """
    errors: List[str] = []
    entry = action.meta.get('entry')
    if not entry:
        return errors
    source = _extract_block_source(action, entry)
    if not source:
        return errors

    # 1) 硬编码凭据
    if SECRET_SENSITIVE_HARDCODE_RE.search(source):
        errors.append(
            'secrets: 检测到硬编码敏感凭据（password/token/api_key/secret 等'
            '直接赋字面量）——凭据必须走 Vault 注入，不得写入动作文件（docs/47 §6）')

    # 2) 敏感 env 未声明
    declared_envs = set()
    for s in action.meta.get('secrets') or []:
        if isinstance(s, dict) and s.get('env'):
            declared_envs.add(s['env'])

    env_read_re = re.compile(
        r'(?:os\.environ\s*\[\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*\]'
        r'|os\.getenv\s*\(\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*\)'
        r'|os\.environ\.get\s*\(\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*\)'
        r'|getenv\s*\(\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*\))')
    for m in env_read_re.finditer(source):
        env = next((g for g in m.groups() if g), None)
        if not env or env.startswith('ACTUS_'):
            continue
        if env in declared_envs:
            continue
        if is_secret_sensitive_name(env):
            errors.append(
                f'secrets: 读取敏感环境变量 {env} 但未在 meta.secrets 声明'
                '（docs/47 §6——声明后运行时才会注入 Vault 凭据）')
    return errors


def check_omega_gate(action: Action) -> List[str]:
    """Ω-gate 编排契约（future_plan §3 #5，docs/47 §5）。

    编排动作（kind=bundle）跨动作组装，下游失败必须可容错解包
    （内层 data.status==ok 即成功），否则编排链一处失败即静默中断。
    规则：
      - kind=bundle（显式编排类型）：必须声明 meta.contract='omega-gate'
        （或 entry 源码含 Ω-gate 解包形态 data.status）→ 缺则打回；
      - 普通带 deps 的动作：缺失仅警告（governance_notices），不判失败。
    """
    errors: List[str] = []
    if str(action.meta.get('kind') or '').lower() != 'bundle':
        return errors
    if action.meta.get('contract') == 'omega-gate':
        return errors
    source = _extract_block_source(action, action.meta.get('entry') or '')
    if 'data.status' in source:
        return errors
    errors.append(
        'omega-gate: kind=bundle 编排动作未声明 Ω-gate 契约'
        '（meta.contract="omega-gate" 或 entry 内使用 data.status 解包，'
        'docs/47 §5——编排链必须可容错，禁止一处失败静默中断）')
    return errors


def governance_notices(meta: dict) -> List[str]:
    """资产化治理警告级项（docs/47）：不判失败，但索引/检查时展示。

    - usage 缺失或非字符串（纯描述已由 check_usage_executable 打回）；
    - 普通带 deps 动作缺 Ω-gate 契约声明。
    """
    notices: List[str] = []

    usage = meta.get('usage')
    if usage is None:
        notices.append('info: 缺 usage 字段——建议补一行可执行调用示例（docs/47 §3.5）')
    elif not isinstance(usage, str):
        notices.append(f'info: usage 必须是字符串，实际为 {type(usage).__name__}')

    if meta.get('deps') and str(meta.get('kind') or 'exec').lower() != 'bundle':
        notices.append(
            'info: 编排动作（deps 非空）建议声明 Ω-gate 契约'
            '（meta.contract="omega-gate"，docs/47 §5）')

    return notices


def validate_graph(actions: Dict[str, Action]) -> None:
    """校验依赖图：deps 存在性 + 循环检测（docs/04 §4/§5）。

    检测到环即抛 ActionError(dependency_cycle)，附环路径；
    缺失依赖抛 ActionError(dependency_missing)。

    注意：`system:`/`lang:`/`mcp:`/`action:`/`pip:`/`npm:` 等运行时依赖
    不在 actions 图中，由 DependencyResolver 在执行期按三策略处理，此处跳过
    （与 Actus engine/actuscore/validate.py 保持一致）。
    """
    # 非 action 的依赖（构建产物、系统命令、语言包、MCP server 等），由 DependencyResolver 运行时校验
    _KNOWN_BUILD_PREFIXES = ("cs_", "build:")
    _KNOWN_RUNTIME_PREFIXES = ("system:", "lang:", "mcp:", "action:", "pip:", "npm:")

    def _is_build_dep(dep: str) -> bool:
        """构建期依赖（pip/npm/cargo 包）：跳过图存在性校验。"""
        return any(dep.startswith(p) or dep == p.rstrip(":") for p in _KNOWN_BUILD_PREFIXES)

    def _is_runtime_dep(dep: str) -> bool:
        """运行时依赖（系统命令/语言包/MCP/action）：跳过图存在性校验。"""
        return any(dep.startswith(p) for p in _KNOWN_RUNTIME_PREFIXES)

    # 存在性
    for aid, a in actions.items():
        for dep in a.meta.get('deps', []) or []:
            if _is_build_dep(dep) or _is_runtime_dep(dep):
                continue  # 运行时依赖不在 actions 图中，由 DependencyResolver 校验
            if dep not in actions:
                raise ActionError(
                    'dependency_missing',
                    f'动作 {aid} 依赖 {dep} 不存在',
                    {'from': aid, 'missing': dep})

    # 循环检测（DFS 三色标记）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {aid: WHITE for aid in actions}
    path: List[str] = []

    def dfs(node: str) -> None:
        """DFS 三色标记：检测循环依赖（GRAY=在栈上，遇到即为环）。"""
        color[node] = GRAY
        path.append(node)
        for dep in actions[node].meta.get('deps', []) or []:
            if color.get(dep, BLACK) == GRAY:
                cycle = path[path.index(dep):] + [dep]
                raise ActionError(
                    'dependency_cycle',
                    '检测到循环依赖: ' + ' → '.join(cycle),
                    {'cycle': cycle})
            if color.get(dep, BLACK) == WHITE:
                dfs(dep)
        path.pop()
        color[node] = BLACK

    for aid in actions:
        if color[aid] == WHITE:
            dfs(aid)


def analyze_graph(actions: Dict[str, Action]) -> Dict[str, dict]:
    """非抛出版依赖图分析：按节点给出错误，不「一条坏边连坐整个市场」。

    旧行为（build_index 历史上）是：validate_graph 抛出第一个错误后，把
    **所有**动作一律标 invalid。结果一条 ``A 依赖 B 不存在`` 会让上百个
    与该依赖毫无关系的动作（vault.*/textstats/…）全部从 MCP / LLM 目录
    下架 —— 爆炸半径是整个动作市场。

    本函数只把**真正受影响**的动作判为图错误：
      - 缺失依赖：声明该坏 deps 的动作本身；
      - 循环依赖：环上的每个成员；
      - 以及（可选，默认包含）沿依赖边正向传播到的下游：一个动作依赖了
        不可用的东西，它本身也无法可靠执行，其下游同理。这条锥用
        ``propagate`` 控制，需要「仅标记直接坏点」时可关。

    Args:
        actions: aid -> Action（通常是已通过单动作契约校验的子集）。

    Returns:
        Dict[str, dict]：仅含有图问题的节点，键为 action_id，值为
        ``{'code': 'dependency_missing'|'dependency_cycle', 'message': str}``。
        图干净时返回空 dict。

    Note:
        运行时依赖（system:/lang:/mcp:/...）与构建依赖（cs_*/build:）
        不在动作图中，跳过存在性校验，口径与 validate_graph 一致。
    """
    _KNOWN_BUILD_PREFIXES = ("cs_", "build:")
    _KNOWN_RUNTIME_PREFIXES = ("system:", "lang:", "mcp:", "action:", "pip:", "npm:")

    def _is_build_dep(dep: str) -> bool:
        """构建期依赖（pip/npm/cargo 包）：跳过图存在性校验。"""
        return any(dep.startswith(p) or dep == p.rstrip(":") for p in _KNOWN_BUILD_PREFIXES)

    def _is_runtime_dep(dep: str) -> bool:
        """运行时依赖（system/lang/mcp/action 命令）：跳过图存在性校验。"""
        return any(dep.startswith(p) for p in _KNOWN_RUNTIME_PREFIXES)

    issues: Dict[str, dict] = {}

    def mark(aid: str, code: str, message: str) -> None:
        """给节点打标签：同一节点保留最严重/最早的一条，避免信息淹没。"""
        # 同一节点保留最严重/最早的一条，避免信息淹没
        issues.setdefault(aid, {'code': code, 'message': message})

    # 正向边：aid -> 它依赖的动作（仅图内动作）
    edges: Dict[str, List[str]] = {}
    for aid, a in actions.items():
        edges[aid] = [d for d in (a.meta.get('deps', []) or [])
                      if not _is_build_dep(d) and not _is_runtime_dep(d)]

    # 1) 缺失依赖：只标记声明它的动作
    missing_owners: List[str] = []
    for aid, deps in edges.items():
        for dep in deps:
            if dep not in actions:
                mark(aid, 'dependency_missing', f'动作 {aid} 依赖 {dep} 不存在')
                missing_owners.append(aid)

    # 2) 循环检测：标记环上的每个成员（DFS 三色，收集所有环，不首遇即停）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {aid: WHITE for aid in actions}

    def dfs_cycle(node: str, stack: List[str]) -> None:
        """DFS 三色标记收集环：环上的每个成员都打标记（不首遇即停）。"""
        color[node] = GRAY
        stack.append(node)
        for dep in edges.get(node, []):
            if dep not in actions:
                continue  # 缺失已在上面处理
            if color.get(dep, BLACK) == GRAY:
                idx = stack.index(dep)
                cyc = stack[idx:] + [dep]
                msg = '检测到循环依赖: ' + ' → '.join(cyc)
                for member in cyc[:-1]:
                    mark(member, 'dependency_cycle', msg)
            elif color.get(dep, BLACK) == WHITE:
                dfs_cycle(dep, stack)
        stack.pop()
        color[node] = BLACK

    for aid in actions:
        if color[aid] == WHITE:
            dfs_cycle(aid, [])

    # 3) 正向传播：依赖了坏节点的下游锥同样不可用（BFS）
    reverse: Dict[str, List[str]] = {}
    for aid, deps in edges.items():
        for d in deps:
            reverse.setdefault(d, []).append(aid)

    seeds = list(issues.keys())
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        cur = stack.pop()
        for child in reverse.get(cur, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
                if child not in issues:
                    mark(child, 'dependency_unavailable',
                         f'动作 {child} 的（传递）依赖 {cur} 不可用')

    return issues


def load_and_validate(path: str) -> Action:
    """便捷入口：解析 + 校验，失败抛 ActionError。"""
    action = parse_cfg_from_file(path)
    errs = validate_action(action)
    if errs:
        raise ActionError('action_invalid',
                          f'动作校验失败: {action.meta.get("id", path)}',
                          {'errors': errs})
    return action


def validate_schema_md(action: Action) -> List[str]:
    """校验 .actus.schema.md 格式的动作（形式 B）。

    对 YAML front-matter 元数据执行内置规则校验，不依赖外部 JSON Schema。
    覆盖 ACTUS_SCHEMA_SPEC.md 区域 1 的全部硬性约束。
    """
    errors: List[str] = []
    meta = action.meta

    # C04: 必填字段（规范 L126 — kind 也是必填，不设默认）
    for k in ('id', 'name', 'version', 'trust', 'entry', 'kind'):
        if not meta.get(k):
            errors.append(f'schema: 必填字段缺失: {k}')

    # C04b: platform 必填 + 取值合法（future_plan §3 #1）
    if not meta.get('platform'):
        errors.append('schema: 必填字段缺失: platform')
    errors.extend(check_platform(meta))

    # C04c: id 命名约束（future_plan §3 #6）
    errors.extend(check_id_namespace(meta))

    # C05: trust 取值
    if meta.get('trust') not in TRUST_LEVELS:
        errors.append(f'schema: trust 非法: {meta.get("trust")!r}（仅允许 {TRUST_LEVELS}）')

    # S3: kind 取值（规范 L103 — 打回级）
    kind = meta.get('kind')
    if kind is not None and not is_known_kind(kind):
        errors.append(f'schema: kind 非法: {kind!r}（仅允许 {KIND_LEVELS}）')

    # C06: entry 指向存在的代码块
    errors.extend(check_entry_block(action))

    # C07: args 契约自检（meta['args'] 已由 model._parse_schema_md_action 从
    # ## Input Schema JSON 代码块自动提取）
    errors.extend(check_args_schema(meta))

    # C08: dependencies 格式
    deps = meta.get('dependencies')
    if deps is not None:
        if not isinstance(deps, dict):
            errors.append('schema: dependencies 必须是 YAML mapping')
        else:
            if 'pip' in deps and not isinstance(deps['pip'], list):
                errors.append('schema: dependencies.pip 必须是列表')
            if 'system' in deps and not isinstance(deps['system'], list):
                errors.append('schema: dependencies.system 必须是列表')
            if 'env' in deps and not isinstance(deps['env'], list):
                errors.append('schema: dependencies.env 必须是列表')

    # C09: triggers 语义
    errors.extend(check_triggers(meta))

    # C10: permissions 白名单
    perms = meta.get('permissions')
    if perms is not None:
        if not isinstance(perms, list):
            errors.append('schema: permissions 必须是列表')
        else:
            from .constants import PERMISSIONS
            for p in perms:
                if p not in PERMISSIONS:
                    errors.append(f'schema: 未知权限: {p!r}')

    # C11: 至少一个代码块
    if not action.blocks:
        errors.append('schema: 未找到任何代码块（需要至少一个实现块）')

    # C12: tag 唯一性（tag 已是 list，+= 安全）
    all_tags = []
    for b in action.blocks:
        t = b.get('tag', [])
        if isinstance(t, list):
            all_tags += t
        elif t:
            all_tags.append(t)
    seen = set()
    for t in all_tags:
        if t in seen:
            errors.append(f'schema: 代码块 tag 重复: {t!r}')
        seen.add(t)

    # C13: usage 可执行形态（future_plan §3 #8）
    errors.extend(check_usage_executable(meta))

    return errors


def check_schema_md_structure(body: str) -> List[str]:
    """校验 .actus.schema.md 正文结构完整性。

    检查必需的 Markdown 区域是否存在：
    - ## Input Schema（JSON 代码块）
    - ## Dependencies（YAML 代码块）
    - ## Implementation（至少一个代码块）
    """
    errors = []
    required_sections = [
        ('input schema', '## Input Schema'),
        ('dependencies', '## Dependencies'),
        ('implementation', '## Implementation'),
    ]
    for name, heading in required_sections:
        if heading.lower() not in body.lower():
            errors.append(f'structure: 缺少 {heading} 区域（{name}）')
    return errors
