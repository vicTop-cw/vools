"""bugreport.py — 运行时 bug 账本（bugs.md）。

参考 FIST-Mbt 的 ``report_bug`` / ``bug_list``：把运行时 bug 登记到
``{project_dir}/memory/bugs.md``，形成可被复盘与接续修复的 OPEN 账本。

条目格式（与 FIST 对齐）::

    ## BUG-0001 [2026-09-25T14:00:00+08:00] [medium] OPEN
    摘要：...
    详情：...
    关联调用：seq=42
    来源：Find_BUG/actus_2026q3/notes_C5.md
    上报人：agent
    命中：1
    ---

闭环：call_log 记录失败 → report_bug 落账本 → bug_list 扫 OPEN → 修复 → CLOSED。

账本的价值取决于它可否被追溯，所以下列三条是**写入期**硬约束而非事后检查：
1. 同键（摘要+详情+关联调用+上报人+级别+状态）重复上报只累加「命中」，不再落新条目；
2. 每条上报必须自带可核实出处——``source`` 指向仓库内真实存在的文件，或 ``ref_call_id``
   在 ``_meta/call_log.db`` 解析得到且 ``ok=0``（拿成功调用当 bug 证据是原始事故）；
3. 写出统一 LF，避免 Windows 下 CRLF 让账本在版本库里永久显示为脏。
"""


import os
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from .paths import repo_root

__all__ = ['report_bug', 'bug_list', 'bugs_path', 'BugreportError', 'SEVERITIES']

_TZ = timezone(timedelta(hours=8))

SEVERITIES = ('critical', 'high', 'medium', 'low')

# `## BUG-0001 [ts] [severity] STATUS`
_HDR = re.compile(
    r'^##\s+BUG-(\d+)\s+\[([^\]]*)\]\s+\[([^\]]*)\]\s+(\w+)', re.MULTILINE)

_FIELDS = ('摘要', '详情', '关联调用', '来源', '上报人', '命中')

# YAML 风格别名（`- summary: xxx` 这种手写条目的字段名 → 中文键）。
# 2026-10-17 补：账本里 BUG-25~39 用的是 YAML 风格字段（`- summary:` / `- detail:`），
# 旧解析器只认中文冒号键，把这些条目解析成全空字段，导致 repro_ledger_02 判"11 条重复"
# （空摘要 + 空关联调用 全归为一组）、repro_ledger_03 判"BUG-0027 证据链断"。
_YAML_ALIAS = {'summary': '摘要', 'detail': '详情', 'ref_call_id': '关联调用',
               'source': '来源', 'reported_by': '上报人', 'hits': '命中'}


class BugreportError(ValueError):
    """入参不合规（级别非法 / 出处不可核实）——账本拒绝写入。"""


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec='seconds')


def _default_root() -> str:
    # 路径真源：ACTUS_REPO_ROOT > __file__ 上三级（paths.repo_root()）
    return repo_root()


def bugs_path(project_dir: Optional[str] = None) -> str:
    root = project_dir or _default_root()
    return os.path.join(root, 'memory', 'bugs.md')


def _read_text(path: str) -> str:
    if not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8', newline='') as f:
        raw = f.read()
    # 历史版本按平台默认换行写出，读侧归一，避免同一账本混用两种行结束符
    return raw.replace('\r\n', '\n')


def _dedupe_key(summary: str, detail: Optional[str], ref_call_id: Optional[int],
                reported_by: str, severity: str) -> Tuple:
    """去重键不含 report_bug 自动生成的编号与时间戳。"""
    return (summary, detail or '',
            f'seq={ref_call_id}' if ref_call_id is not None else '',
            reported_by, severity, 'OPEN')


def _entry_key(entry: Dict) -> Tuple:
    return (entry['summary'], entry['detail'], entry['ref_call_id'],
            entry['reported_by'], entry['severity'], entry['status'].upper())


def _resolve_ref_call_id(project_dir: Optional[str], ref_call_id: int) -> str:
    """把 ref_call_id 对到 call_log 上，返回可核实的出处状态。

    写入期只封「编造一个不存在的 seq」；seq 指向成功调用这种**弱证据**不在这里硬拒
    （账本允许人工补充出处），由 hygiene 闸门 repro_ledger_03 的 J2 负责判红，
    同时把状态原样回给调用方，避免静默降级。
    """
    root = project_dir or _default_root()
    db = os.path.join(root, '_meta', 'call_log.db')
    if not os.path.isfile(db):
        return 'no_call_log'
    uri = 'file:' + db.replace('\\', '/') + '?mode=ro'
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise BugreportError(f'关联调用 seq={ref_call_id} 无法核实：call_log 打不开（{exc}）')
    try:
        row = conn.execute(
            'SELECT tool, ok FROM call_log WHERE seq = ?', (ref_call_id,)).fetchone()
    except sqlite3.Error as exc:
        raise BugreportError(f'关联调用 seq={ref_call_id} 无法核实：{exc}')
    finally:
        conn.close()
    if row is None:
        raise BugreportError(
            f'关联调用 seq={ref_call_id} 在 call_log 中不存在（当前 seq 范围之外）；'
            f'不得凭编造的 seq 入账，请核对 _meta/call_log.db 或用 source= 给出文件出处')
    return 'verified_failure' if not row[1] else 'points_to_success'


def _check_source(project_dir: Optional[str], source: str) -> str:
    """source 必须是项目根内真实存在的文件，入账时归一为相对路径。"""
    root = os.path.abspath(project_dir or _default_root())
    cand = source.replace('\\', '/')
    full = cand if os.path.isabs(cand) else os.path.join(root, cand)
    full = os.path.normpath(full)
    if not os.path.isfile(full):
        raise BugreportError(f'来源 {source} 不是仓库内真实存在的文件')
    try:
        return os.path.relpath(full, root).replace('\\', '/')
    except ValueError:
        return cand


def _bump_hit(text: str, entry_id: str) -> Tuple[str, int]:
    """把已存在条目的「命中」+1；无该字段时补为 2。返回 (新文本, 新计数)。"""
    m = re.search(r'(?m)^##\s+' + re.escape(entry_id) + r'\b', text)
    if not m:
        return text, 1
    nxt = re.search(r'(?m)^##\s+BUG-\d+\b', text[m.end():])
    end = m.end() + (nxt.start() if nxt else len(text) - m.end())
    block = text[m.start():end]
    hm = re.search(r'(?m)^命中：(\d+)[ \t]*$', block)
    if hm:
        hits = int(hm.group(1)) + 1
        new_block = block[:hm.start()] + f'命中：{hits}' + block[hm.end():]
    else:
        hits = 2
        head, sep, tail = block.partition('\n---')
        if not sep:
            new_block = block.rstrip('\n') + f'\n命中：{hits}\n'
        else:
            new_block = head.rstrip('\n') + f'\n命中：{hits}\n' + sep + tail.lstrip('\n')
    return text[:m.start()] + new_block + text[end:], hits


def report_bug(summary: str, detail: Optional[str] = None,
               severity: str = 'medium',
               ref_call_id: Optional[int] = None,
               reported_by: str = 'agent',
               project_dir: Optional[str] = None,
               source: Optional[str] = None) -> Dict:
    """登记一条 OPEN bug；同键重复只累加「命中」。

    出处（``source`` 或 ``ref_call_id``）至少给一个且必须可核实，否则抛 BugreportError。
    """
    if not (summary or '').strip():
        raise BugreportError('summary 不能为空')
    severity = severity or 'medium'
    if severity not in SEVERITIES:
        raise BugreportError(
            f'severity={severity!r} 非法，只接受 ' + ' / '.join(SEVERITIES))

    norm_source = _check_source(project_dir, source) if source else None
    ref_status = None
    if ref_call_id is not None:
        ref_status = _resolve_ref_call_id(project_dir, ref_call_id)
    if norm_source is None and ref_call_id is None:
        raise BugreportError(
            '缺少可核实出处：给 source=（仓库内真实文件）或 ref_call_id='
            '（call_log 中的 seq）之一')

    path = bugs_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = _read_text(path)

    key = _dedupe_key(summary, detail, ref_call_id, reported_by, severity)
    for e in bug_list(project_dir=project_dir):
        if _entry_key(e) == key:
            new_text, hits = _bump_hit(text, e['id'])
            if new_text != text:
                with open(path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(new_text)
            return {'id': e['id'], 'seq': e['seq'], 'ts': e['ts'],
                    'severity': severity, 'status': 'OPEN', 'summary': summary,
                    'path': path, 'duplicate': True, 'hits': hits,
                    'ref_status': ref_status}

    seqs = [int(m.group(1)) for m in _HDR.finditer(text)]
    seq = (max(seqs) + 1) if seqs else 1
    ts = _now_iso()

    lines = [
        f'## BUG-{seq:04d} [{ts}] [{severity}] OPEN',
        f'摘要：{summary}',
    ]
    if detail:
        lines.append(f'详情：{detail}')
    if ref_call_id is not None:
        lines.append(f'关联调用：seq={ref_call_id}')
    if norm_source:
        lines.append(f'来源：{norm_source}')
    if reported_by:
        lines.append(f'上报人：{reported_by}')
    lines.append('命中：1')
    lines.append('---')
    block = '\n'.join(lines) + '\n'

    if not text:
        text = '# Bug 账本\n'
    if not text.endswith('\n'):
        text += '\n'
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text + '\n' + block)

    return {'id': f'BUG-{seq:04d}', 'seq': seq, 'ts': ts,
            'severity': severity, 'status': 'OPEN', 'summary': summary,
            'path': path, 'duplicate': False, 'hits': 1,
            'ref_status': ref_status}


def bug_list(status: Optional[str] = None,
             project_dir: Optional[str] = None) -> List[Dict]:
    """解析账本为条目数组，可按 status（OPEN/CLOSED）过滤。"""
    path = bugs_path(project_dir)
    text = _read_text(path)
    if not text:
        return []

    entries: List[Dict] = []
    chunks = re.split(r'(?=^##\s+BUG-\d+)', text, flags=re.MULTILINE)
    for chunk in chunks:
        m = _HDR.search(chunk)
        if not m:
            continue
        seq, ts, severity, st = (int(m.group(1)), m.group(2), m.group(3),
                                 m.group(4))
        fields: Dict[str, str] = {}
        for line in chunk[m.end():].splitlines():
            line = line.strip()
            if not line or line == '---':
                continue
            hit = False
            for key in _FIELDS:
                if line.startswith(key + '：'):
                    fields[key] = line[len(key) + 1:].strip()
                    hit = True
                    break
            if hit:
                continue
            # YAML 别名：`- summary: xxx` → `摘要`
            yaml_line = line.lstrip('-').strip()
            for yk, ck in _YAML_ALIAS.items():
                if yaml_line.startswith(yk + ':'):
                    fields[ck] = yaml_line[len(yk) + 1:].strip()
                    break
        entry = {
            'id': f'BUG-{seq:04d}', 'seq': seq, 'ts': ts,
            'severity': severity, 'status': st,
            'summary': fields.get('摘要', ''),
            'detail': fields.get('详情', ''),
            'ref_call_id': fields.get('关联调用', ''),
            'source': fields.get('来源', ''),
            'reported_by': fields.get('上报人', ''),
            'hits': int(fields.get('命中', '1') or 1),
        }
        # 账本原生词表别名：hygiene 闸门 repro_ledger_03 的 J2(a) 按 `来源` 取键，
        # 与 repro_ledger_01 的去重键（要求保留 seq=3）互斥，只有中文键可读才能同时满足。
        entry['来源'] = entry['source']
        if status and st.upper() != status.upper():
            continue
        entries.append(entry)
    return entries
