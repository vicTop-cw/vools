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


def load_run_history(meta_dir: str = ".", limit: int = 0) -> List[dict]:
    """加载运行历史。

    参数:
        meta_dir: 元数据目录。
        limit: 返回条数限制（0=全部）。

    返回:
        运行记录列表，按时间倒序。
    """
    history_file = Path(meta_dir) / "runs" / "history.json"
    if not history_file.exists():
        return []

    try:
        content = json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(content, list):
            records = content
        elif isinstance(content, dict) and "runs" in content:
            records = content["runs"]
        else:
            records = [content]

        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        if limit > 0:
            records = records[:limit]
        return records
    except (json.JSONDecodeError, OSError):
        return []


def export_to_json(records: List[dict]) -> str:
    """导出为 JSON 字符串。"""
    return json.dumps(records, ensure_ascii=False, indent=2)


def export_to_csv(records: List[dict]) -> str:
    """导出为 CSV 字符串。"""
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
        导出的内容字符串（如果 output_path 为空）。
    """
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
        return None

    return result


__all__ = [
    'export_history',
    'export_to_csv',
    'export_to_html',
    'export_to_json',
    'export_to_markdown',
    'load_run_history',
    'logger'
]
