"""export.py — 动作历史导出 (Phase M2)。

将动作执行历史导出为多种格式：JSON / CSV / Markdown / HTML 报告。
"""

import json
import csv
import io
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class RunHistoryCorruptError(Exception):
    """历史文件存在但读不出来（损坏 / 不可读 / 结构非法）。

    「还没执行过」与「历史文件坏了」必须分得开：改前两者都返回 `[]`，
    CLI 一律打印「📭 暂无执行历史」exit 0 —— 用户不会去修，replay/export
    永远空转，而报告里看不出任何异常。
    """


def _normalize_exec_record(record: Dict) -> Dict:
    """把执行器写的运行记录（`runs/<exec_id>.json`）归一成历史记录形状。

    两种记录字段不同：执行器写 `action` / `exec_id` / `result.status`，
    `history.json` 用 `action_id` / `run_id`|`id` / `status`。归一后
    export（表格的动作/状态列）与 replay 两种数据源走同一套消费代码。
    """
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    exec_id = record.get("exec_id") or record.get("run_id") or record.get("id")
    return {
        "run_id": exec_id,
        "exec_id": record.get("exec_id"),
        "action_id": record.get("action") or record.get("action_id"),
        "params": record.get("params"),
        "status": result.get("status") or record.get("status") or "",
        "timestamp": record.get("timestamp", ""),
        "result": result or None,
    }


def _load_exec_records(meta_dir: str) -> List[dict]:
    """回落数据源：真实执行记录 `runs/<exec_id>.json`（records.list_run_records）。"""
    from .records import list_run_records

    raw = list_run_records(meta_dir, limit=10 ** 6)
    return [_normalize_exec_record(r) for r in raw if isinstance(r, dict)]


def load_run_history(meta_dir: str = ".", limit: int = 0) -> List[dict]:
    """加载运行历史，按时间倒序。

    参数:
        meta_dir: 元数据目录。
        limit: 返回条数限制（0=全部）。

    返回:
        运行记录列表（dict 列表），按时间倒序。

    数据源（本轮修）：优先 `runs/history.json`；**该文件不存在时回落到真实
    执行记录** `runs/<exec_id>.json`（`records.list_run_records`）。
    改前只读 history.json，而全仓没有任何代码写这个文件 —— 于是不设
    `ACTUS_META_DIR` 时 replay/export 永远打印「📭 暂无执行历史」，
    功能在真实使用中等于不存在。

    文件**存在但损坏**时抛 `RunHistoryCorruptError`（不再静默当成空历史），
    由 CLI 明确报「历史文件损坏」并 exit 1。
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError(f"limit 必须是 ≥0 的整数（0=全部），得到 {limit!r}")
    history_file = Path(meta_dir) / "runs" / "history.json"

    if history_file.exists():
        try:
            content = json.loads(history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RunHistoryCorruptError(f"{history_file}: {exc}") from exc
        if isinstance(content, list):
            records = [r for r in content if isinstance(r, dict)]
        elif isinstance(content, dict) and isinstance(content.get("runs"), list):
            records = [r for r in content["runs"] if isinstance(r, dict)]
        elif isinstance(content, dict):
            records = [content]
        else:
            raise RunHistoryCorruptError(
                f"{history_file}: 顶层既不是数组也不是对象（{type(content).__name__}）")
    else:
        records = _load_exec_records(meta_dir)

    records.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    if limit > 0:
        records = records[:limit]
    return records


EXPORT_FORMATS = ("json", "csv", "markdown", "md", "html")


def _require_records(records) -> List[dict]:
    """记录必须是 dict 列表。

    此前 `export_to_json('abc')` 会把字符串当记录序列化出 `"abc"`、
    `export_to_csv(None)` 抛裸 TypeError —— 调用方以为导出了空报告。
    """
    if not isinstance(records, (list, tuple)):
        raise TypeError(
            f"records 必须是 dict 列表，得到 {type(records).__name__}"
            f"（字符串不是记录集）")
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise TypeError(
                f"records[{i}] 必须是 dict，得到 {type(r).__name__}")
    return list(records)


def export_to_json(records: List[dict]) -> str:
    """导出为 JSON 字符串。"""
    return json.dumps(_require_records(records), ensure_ascii=False, indent=2)


def export_to_csv(records: List[dict]) -> str:
    """导出为 CSV 字符串。"""
    records = _require_records(records)
    output = io.StringIO()

    # 收集所有可能的字段
    fields = ["timestamp", "action_id", "status", "duration", "error"]
    for r in records:
        for k in r:
            if k not in fields:
                fields.append(k)

    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        writer.writerow(r)

    return output.getvalue()


def export_to_markdown(records: List[dict], title: str = "动作执行历史") -> str:
    """导出为 Markdown 报告。"""
    records = _require_records(records)
    if not isinstance(title, str):
        raise TypeError(f"title 必须是字符串，得到 {type(title).__name__}")
    lines = [f"# {title}", ""]
    lines.append(f"生成时间: {datetime.now().isoformat()}")
    lines.append(f"总记录数: {len(records)}")
    lines.append("")

    # 统计
    success = sum(1 for r in records if r.get("status") == "ok")
    failed = sum(1 for r in records if r.get("status") == "failed")
    lines.append(f"- ✅ 成功: {success}")
    lines.append(f"- ❌ 失败: {failed}")
    lines.append("")

    # 表格
    lines.append("| 时间 | 动作 | 状态 | 耗时 |")
    lines.append("|------|------|------|------|")
    for r in records:
        ts = r.get("timestamp", "")
        action = r.get("action_id", r.get("id", ""))
        status = r.get("status", "")
        duration = r.get("duration", "")
        icon = "✅" if status == "ok" else "❌"
        lines.append(f"| {ts} | {action} | {icon} {status} | {duration}s |")

    return "\n".join(lines)


def export_to_html(records: List[dict], title: str = "Actus 执行报告") -> str:
    """导出为 HTML 报告。"""
    records = _require_records(records)
    if not isinstance(title, str):
        raise TypeError(f"title 必须是字符串，得到 {type(title).__name__}")
    success = sum(1 for r in records if r.get("status") == "ok")
    failed = sum(1 for r in records if r.get("status") == "failed")
    total = len(records)

    rows = ""
    for r in records:
        ts = r.get("timestamp", "")
        action = r.get("action_id", r.get("id", ""))
        status = r.get("status", "")
        duration = r.get("duration", "")
        error = r.get("error", "")
        css_class = "success" if status == "ok" else "failed"
        rows += f'<tr class="{css_class}"><td>{ts}</td><td>{action}</td><td>{status}</td><td>{duration}s</td><td>{error}</td></tr>\n'

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
h1 {{ color: #e94560; }}
.stats {{ display: flex; gap: 20px; margin: 20px 0; }}
.stat {{ background: #16213e; padding: 15px 25px; border-radius: 8px; }}
.stat.success {{ border-left: 4px solid #00d26a; }}
.stat.failed {{ border-left: 4px solid #e94560; }}
.stat.total {{ border-left: 4px solid #0f3460; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th, td {{ padding: 10px 15px; text-align: left; border-bottom: 1px solid #333; }}
th {{ background: #0f3460; color: #e94560; }}
tr.success {{ background: rgba(0, 210, 106, 0.1); }}
tr.failed {{ background: rgba(233, 69, 96, 0.1); }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>生成时间: {datetime.now().isoformat()}</p>
<div class="stats">
    <div class="stat total">总执行: {total}</div>
    <div class="stat success">成功: {success}</div>
    <div class="stat failed">失败: {failed}</div>
</div>
<table>
<thead><tr><th>时间</th><th>动作</th><th>状态</th><th>耗时</th><th>错误</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""


def export_history(meta_dir: str = ".", output_path: str = "",
                   format_: str = "json", limit: int = 0) -> Optional[str]:
    """导出运行历史。

    参数:
        meta_dir: 元数据目录。
        output_path: 输出文件路径（空则返回字符串）。
        format_: 导出格式 (json/csv/markdown/html)。
        limit: 记录数限制。

    返回:
        导出的内容字符串（output_path 为空时）；写文件时返回**写入路径**；
        没有任何记录时返回 None（唯一表示「没东西可导」的返回值）。
    """
    # 未知 format_ 此前**静默回退成 json**：调用方要 csv 却拿到 JSON，无任何提示。
    if format_ not in EXPORT_FORMATS:
        raise ValueError(
            f"未知导出格式 {format_!r}，可用: {', '.join(EXPORT_FORMATS)}")
    records = load_run_history(meta_dir, limit)
    if not records:
        return None

    exporters = {
        "json": export_to_json,
        "csv": export_to_csv,
        "markdown": export_to_markdown,
        "md": export_to_markdown,
        "html": export_to_html,
    }

    exporter = exporters.get(format_, export_to_json)
    result = exporter(records)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(result, encoding="utf-8")
        # 返回写入路径（原来是 None）：None 必须只表示「没有可导出的记录」，
        # 否则 CLI 无法区分「写成功了」与「根本没写」—— 改前它对着一个根本
        # 不存在的文件打印「✅ 已导出到: ...」并 exit 0（CI 随后 FileNotFoundError）。
        return str(output_path)

    return result


__all__ = [
    'RunHistoryCorruptError',
    'export_history',
    'export_to_csv',
    'export_to_html',
    'export_to_json',
    'export_to_markdown',
    'load_run_history',
    'logger'
]
