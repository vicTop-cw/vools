"""cost.py — 成本账本（阶段 4）。

追踪每次云端 API 调用的成本，支持预算告警。
预算告警复用 notify 模块（docs/31 阶段 4：成本账本落 _meta/costs/，
复用 notify 模块做预算告警，先做最小版）。

账本完整性（第 4x 轮审计修复）：`_meta/costs/<月>.jsonl` 是追加写的，历史行可能
被外部改坏/写坏。改前 `get_cost_summary()` 用 `except Exception: continue` 把这类
行**静默丢掉** —— 实测 3 行账本（1 合法 + 2 坏）只报 `total_usd=1.5, calls=1`，
调用方完全看不出少算过。预算判断直接吃这个 total，于是「真超支也可能不告警」。
现在跳过/降级的行都会计数并分类返回（skipped_* / incomplete_* / ledger_complete），
total_usd / calls 的既有语义保持不变。
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from .paths import meta_dir

__all__ = ['record_cost', 'get_cost_summary', 'check_budget',
           'alert_budget_if_over', 'COSTS_DIR']

# 账本行分类：
#   skip_*       —— 这一行的成本**无法计入**（total_usd 里没有它，是"账本缺口"）
#   incomplete_* —— 这一行**已按默认值计入**（total_usd 里有它，但字段缺失/被纠正）
_SKIP_BAD_JSON = 'bad_json'                  # 整行不是合法 JSON
_SKIP_NOT_OBJECT = 'not_object'              # JSON 合法但不是 object
_SKIP_BAD_COST = 'bad_cost_usd'              # cost_usd 存在但不是数字
_INCOMPLETE_MISSING_COST = 'missing_cost_usd'    # 缺 cost_usd → 按 0 计入
_INCOMPLETE_UNKNOWN_COST = 'unknown_cost'    # cost_usd=null → 成本未知（不计金额，记 tokens）
_INCOMPLETE_MISSING_PROVIDER = 'missing_provider'  # 缺/空 provider → 归 unknown
_INCOMPLETE_BAD_PROVIDER = 'bad_provider'    # provider 非字符串 → 归 unknown

# 成本账本目录：`paths.meta_dir()/costs`（**唯一真源**）。
# 优先级由 paths 统一：ACTUS_META_DIR > ACTUS_REPO_ROOT/_meta > __file__ 推导。
# 2026-10-13（docs/45 S2 shim 化）的历史约束仍然成立：_meta/costs/ 是**宿主仓库**
# 的运行时数据，不能跟着实现文件走 —— 真源的默认分支正是「仓库根/_meta」。
# 本轮修正：改前只读 ACTUS_REPO_ROOT，**ACTUS_META_DIR 对它无效**，用户没法用一条
# 环境变量把整棵 _meta 搬走；现在与其它模块一致了（不设环境变量时路径逐字不变）。
COSTS_DIR = os.path.join(meta_dir(), 'costs')


def _ensure_dir():
    os.makedirs(COSTS_DIR, exist_ok=True)


def record_cost(action_id: str, provider: str, cost_usd: float = None,
                tokens: int = 0, model: str = "", extra: dict = None):
    """记录一次成本调用。

    参数:
        action_id: 调用方标识（AI 层固定用 `ai.llm.complete`）。
        provider: provider / 服务名。
        cost_usd: 本次成本（美元）。**允许 None** —— 表示"这次调用的成本未知"
            （例如没装价格表、模型不在表里）。写 null，绝不用 0 冒充：
            0 的语义是"确认免费"（本地推理），与"不知道"是两件事。
            `get_cost_summary()` 会把 null 行进 `incomplete_reasons['unknown_cost']`
            并单独累计 tokens，不混进 total_usd。
        tokens: 本次消耗 token 数（拿不到就 0）。
        model: 模型名。
        extra: 追加字段（如 prompt/completion 拆分、cost_source 来源标记）。
    """
    _ensure_dir()
    today = datetime.now().strftime('%Y-%m')
    filepath = os.path.join(COSTS_DIR, f'{today}.jsonl')
    entry = {
        'timestamp': datetime.now().isoformat(),
        'action_id': action_id,
        'provider': provider,
        'cost_usd': cost_usd,
        'tokens': tokens,
        'model': model,
    }
    if extra:
        entry.update(extra)
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def _is_number(value) -> bool:
    """真数字（排除 bool —— `isinstance(True, int)` 为真，True 不是成本）。"""
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _empty_summary(month: str) -> dict:
    """空账本 / 账本不存在时的汇总（字段与有数据时完全同构）。"""
    return {
        'month': month,
        'total_usd': 0,
        'calls': 0,
        'by_provider': {},
        'tokens_total': 0,
        'skipped_lines': 0,
        'skipped_reasons': {},
        'incomplete_lines': 0,
        'incomplete_reasons': {},
        'calls_unknown_cost': 0,
        'tokens_unknown_cost': 0,
        'ledger_complete': True,
    }


def get_cost_summary(month: str = None) -> dict:
    """获取月度成本汇总。

    既有字段语义不变（消费方如 `check_budget` 依赖）：
      month / total_usd / calls / by_provider —— 只累加**可解析行**的真实 cost_usd。

    新增完整性信号（均为增量，不影响上面四个键）：
      skipped_lines / skipped_reasons       —— 成本无法计入的行数及分类
      incomplete_lines / incomplete_reasons  —— 已计入但字段缺失/降级/未知成本的行
      calls_unknown_cost / tokens_unknown_cost —— cost_usd=null 的行（成本未知）
      tokens_total                           —— 全部可用行的 token 合计（含未知成本行）
      ledger_complete                        —— 两类异常都为 0 时才为 True

    `cost_usd: null` 的处理（AI 层接线后新增的形态）：该行**计入 calls，不计入
    total_usd**（成本未知 ≠ 成本为 0），进 `incomplete_reasons['unknown_cost']`，
    并把它的 tokens 记进 `tokens_unknown_cost`。这样预算读数不会被"假 0"稀释，
    同时"有调用但成本未知"这件事在返回体里可见。

    为什么不抛异常：账本是运行时旁路数据，读失败不该打断业务调用；但"读不完整"
    必须让调用方看得见 —— 改前它看不见（静默 continue）。
    """
    _ensure_dir()
    if month is None:
        month = datetime.now().strftime('%Y-%m')
    filepath = os.path.join(COSTS_DIR, f'{month}.jsonl')
    total = 0.0
    calls = 0
    by_provider = {}
    by_model = {}
    tokens_total = 0
    calls_unknown_cost = 0
    tokens_unknown_cost = 0
    skipped_reasons = {}
    incomplete_reasons = {}

    def _bump(bucket, key):
        bucket[key] = bucket.get(key, 0) + 1

    def _tokens_of(entry):
        value = entry.get('tokens')
        if isinstance(value, bool) or not isinstance(value, int):
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0
        return value

    if not os.path.exists(filepath):
        return _empty_summary(month)
    with open(filepath, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:          # JSONDecodeError 是 ValueError 子类
                _bump(skipped_reasons, _SKIP_BAD_JSON)
                continue
            if not isinstance(entry, dict):
                _bump(skipped_reasons, _SKIP_NOT_OBJECT)
                continue

            # ── cost_usd：null=成本未知（计入 calls，不计金额）；非数字=无法计入 ──
            if 'cost_usd' not in entry:
                _bump(incomplete_reasons, _INCOMPLETE_MISSING_COST)
                cost = 0.0
                unknown_cost = False
            else:
                cost = entry['cost_usd']
                if cost is None:
                    _bump(incomplete_reasons, _INCOMPLETE_UNKNOWN_COST)
                    cost = 0.0
                    unknown_cost = True
                elif not _is_number(cost):
                    _bump(skipped_reasons, _SKIP_BAD_COST)
                    continue
                else:
                    cost = float(cost)
                    unknown_cost = False

            # ── provider：缺失/空/非字符串 一律归 unknown（仍计入，不丢成本）──
            if 'provider' not in entry or entry.get('provider') in (None, ''):
                _bump(incomplete_reasons, _INCOMPLETE_MISSING_PROVIDER)
                provider = 'unknown'
            else:
                provider = entry['provider']
                if not isinstance(provider, str):
                    _bump(incomplete_reasons, _INCOMPLETE_BAD_PROVIDER)
                    provider = 'unknown'

            row_tokens = _tokens_of(entry)
            tokens_total += row_tokens
            total += cost
            calls += 1
            if unknown_cost:
                calls_unknown_cost += 1
                tokens_unknown_cost += row_tokens
            if provider not in by_provider:
                by_provider[provider] = {'usd': 0, 'calls': 0, 'calls_unknown_cost': 0}
            by_provider[provider]['usd'] += cost
            by_provider[provider]['calls'] += 1
            if unknown_cost:
                by_provider[provider]['calls_unknown_cost'] += 1

            # 第 11 轮：按**模型**分组（此前只有 by_provider；CLI cost 要展示模型级
            # 花费，否则"按模型分组"只能靠人肉再算一遍）。
            model = entry.get('model') or 'unknown'
            if not isinstance(model, str):
                model = 'unknown'
            if model not in by_model:
                by_model[model] = {'usd': 0, 'calls': 0}
            by_model[model]['usd'] += cost
            by_model[model]['calls'] += 1

    skipped_lines = sum(skipped_reasons.values())
    incomplete_lines = sum(incomplete_reasons.values())
    return {
        'month': month,
        'total_usd': round(total, 6),
        'calls': calls,
        'by_provider': by_provider,
        'by_model': by_model,
        'tokens_total': tokens_total,
        'skipped_lines': skipped_lines,
        'skipped_reasons': dict(sorted(skipped_reasons.items())),
        'incomplete_lines': incomplete_lines,
        'incomplete_reasons': dict(sorted(incomplete_reasons.items())),
        'calls_unknown_cost': calls_unknown_cost,
        'tokens_unknown_cost': tokens_unknown_cost,
        'ledger_complete': skipped_lines == 0 and incomplete_lines == 0,
    }


def check_budget(month_limit_usd: float = 10.0) -> dict:
    """检查是否超出预算，返回状态。

    预算判定数学**保持原样**（over_budget 仍只看已计入的 total_usd）。
    只额外透传账本完整性：`ledger_complete=False` 表示 total 可能偏低 —— 由调用方
    决定是否更保守（例如把已计入的 total 当上限、或提示人工核对），本函数不擅自
    抬高/下调预算语义（缺口行的真实成本未知，凭空加成会制造假告警）。
    """
    summary = get_cost_summary()
    total = summary['total_usd']
    over = total > month_limit_usd
    return {
        'budget_usd': month_limit_usd,
        'spent_usd': total,
        'remaining_usd': round(max(0, month_limit_usd - total), 6),
        'over_budget': over,
        'usage_pct': round(total / month_limit_usd * 100, 2) if month_limit_usd > 0 else 0,
        'ledger_complete': summary.get('ledger_complete', True),
        'ledger_skipped_lines': summary.get('skipped_lines', 0),
    }


def alert_budget_if_over(month_limit_usd: float = 10.0, notify: bool = True) -> dict:
    """预算告警最小版（docs/31 阶段 4）：超支时经 notify 模块发告警。

    返回 check_budget 的状态 + alerted 标志；告警失败不影响判定结果。
    """
    status = check_budget(month_limit_usd)
    status['alerted'] = False
    if not status['over_budget'] or not notify:
        return status
    try:
        from .notify import NotifyLevel, get_notification_manager
        mgr = get_notification_manager()
        mgr.notify(
            title='Actus 预算告警',
            body=(f"本月云端成本 ${status['spent_usd']} 已超预算 "
                  f"${status['budget_usd']}（{status['usage_pct']}%）"),
            level=NotifyLevel.WARNING,
            metadata={'kind': 'budget', **status},
        )
        status['alerted'] = True
    except Exception:
        pass  # 告警通道失败不影响预算判定本身
    return status
