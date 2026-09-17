"""template.py —— 动作模板系统 (Phase M1)。

提供预定义的动作模板，加速 AI 和用户创建新动作。
模板存储在 actions/templates/ 目录，文件结构完整可直接使用。
"""

import json
import os
import re
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 内置模板 ──────────────────────────────────────────────────────────────

BUILTIN_TEMPLATES: Dict[str, dict] = {
    "python-basic": {
        "name": "Python 基础动作",
        "description": "最简单的 Python 动作模板，接收参数并返回结果",
        "category": "template",
        "tags": ["python", "basic", "template"],
        "body": '''"""${action_name} — ${description}"""

import json
import sys


def main(params: dict) -> dict:
    """动作入口。
    
    Args:
        params: 参数字典，来自 .actus.md 的 parameters 定义。
    
    Returns:
        dict: 执行结果，含 status/data/error 字段。
    """
    try:
        # 参数提取
        value = params.get("value", "")
        
        # 业务逻辑
        result = {"processed": value, "length": len(str(value))}
        
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


if __name__ == "__main__":
    # 从环境变量读取参数
    params = json.loads(os.environ.get("ACTUS_PARAMS", "{}")) if "ACTUS_PARAMS" in os.environ else {}
    if len(sys.argv) > 1:
        try:
            params = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            pass
    print(json.dumps(main(params), ensure_ascii=False))
''',
    },

    "python-api": {
        "name": "API 调用动作",
        "description": "调用外部 API 的模板，含错误处理和重试",
        "category": "template",
        "tags": ["python", "api", "http", "template"],
        "body": '''"""${action_name} — ${description}"""

import json
import os
import urllib.request
import urllib.error


def main(params: dict) -> dict:
    """调用外部 API。"""
    url = params.get("url", "")
    method = params.get("method", "GET")
    headers = params.get("headers", {})
    body = params.get("body", None)
    timeout = params.get("timeout", 30)
    
    if not url:
        return {"status": "failed", "error": "缺少 url 参数"}
    
    try:
        data = None
        if body:
            data = json.dumps(body).encode("utf-8")
        
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = resp.read().decode("utf-8")
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass
        
        return {"status": "ok", "data": {"response": result, "status_code": resp.status}}
    except urllib.error.HTTPError as e:
        return {"status": "failed", "error": f"HTTP {e.code}: {e.reason}", "error_code": "http_error"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


if __name__ == "__main__":
    params = json.loads(os.environ.get("ACTUS_PARAMS", "{}")) if "ACTUS_PARAMS" in os.environ else {}
    print(json.dumps(main(params), ensure_ascii=False))
''',
    },

    "shell-basic": {
        "name": "Shell 脚本动作",
        "description": "执行 Shell 命令的模板",
        "category": "template",
        "tags": ["shell", "basic", "template"],
        "body": '''#!/bin/bash
# ${action_name} — ${description}
# 用法: bash ${action_id}.sh <params_json>

PARAMS="$1"

# 解析参数（使用 python 辅助）
VALUE=$(echo "$PARAMS" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('value',''))" 2>/dev/null)

if [ -z "$VALUE" ]; then
    echo '{"status":"failed","error":"缺少 value 参数"}'
    exit 1
fi

# 业务逻辑
echo "处理: $VALUE"
RESULT=$(echo "$VALUE" | tr '[:lower:]' '[:upper:]')

echo "{\"status\":\"ok\",\"data\":{\"result\":\"$RESULT\"}}"
''',
    },

    "node-basic": {
        "name": "Node.js 动作",
        "description": "Node.js 脚本动作模板",
        "category": "template",
        "tags": ["node", "javascript", "template"],
        "body": '''#!/usr/bin/env node
/**
 * ${action_name} — ${description}
 * 用法: node ${action_id}.mjs '<params_json>'
 */

const params = JSON.parse(process.argv[2] || '{}');

function main(params) {
    try {
        const value = params.value || '';
        const result = { processed: value, length: value.length };
        return { status: 'ok', data: result };
    } catch (e) {
        return { status: 'failed', error: e.message };
    }
}

console.log(JSON.stringify(main(params)));
''',
    },

    "webhook-receiver": {
        "name": "Webhook 接收器",
        "description": "接收外部 webhook 并触发工作流",
        "category": "template",
        "tags": ["webhook", "http", "trigger", "template"],
        "body": '''"""${action_name} — ${description}"""

import json
import os
import hashlib
import hmac
from http.server import HTTPServer, BaseHTTPRequestHandler


WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        # 验证签名
        if WEBHOOK_SECRET:
            sig = self.headers.get("X-Signature", "")
            expected = hmac.new(
                WEBHOOK_SECRET.encode(), body, hashlib.sha256
            ).hexdigest()
            if sig != expected:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"签名无效"}')
                return
        
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw": body.decode("utf-8", errors="replace")}
        
        # 输出触发事件
        result = {"status": "ok", "data": {"triggered": True, "payload": payload}}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
    
    def log_message(self, format, *args):
        pass  # 静默日志


def main(params: dict) -> dict:
    port = params.get("port", 8080)
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"Webhook 接收器启动于端口 {port}")
    server.serve_forever()


if __name__ == "__main__":
    params = json.loads(os.environ.get("ACTUS_PARAMS", "{}")) if "ACTUS_PARAMS" in os.environ else {}
    print(json.dumps(main(params), ensure_ascii=False))
''',
    },

    "file-watcher": {
        "name": "文件监控动作",
        "description": "监控文件变化并触发回调",
        "category": "template",
        "tags": ["file", "watch", "monitor", "template"],
        "body": '''"""${action_name} — ${description}"""

import json
import os
import time
import hashlib
from pathlib import Path


def file_hash(path: str) -> str:
    """计算文件 MD5。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main(params: dict) -> dict:
    path = params.get("path", ".")
    pattern = params.get("pattern", "*")
    interval = params.get("interval", 5)
    
    if not os.path.exists(path):
        return {"status": "failed", "error": f"路径不存在: {path"}
    
    p = Path(path)
    if p.is_file():
        files = [str(p)]
    else:
        files = [str(f) for f in p.glob(pattern) if f.is_file()]
    
    snapshots = {}
    for f in files:
        snapshots[f] = file_hash(f)
    
    # 输出初始快照
    return {
        "status": "ok",
        "data": {
            "watched": len(files),
            "snapshots": snapshots,
            "message": f"监控 {len(files)} 个文件，间隔 {interval}s",
        }
    }


if __name__ == "__main__":
    params = json.loads(os.environ.get("ACTUS_PARAMS", "{}")) if "ACTUS_PARAMS" in os.environ else {}
    print(json.dumps(main(params), ensure_ascii=False))
''',
    },
}


def get_template(template_id: str) -> Optional[dict]:
    """获取模板。"""
    return BUILTIN_TEMPLATES.get(template_id)


def list_templates() -> List[dict]:
    """列出所有可用模板。"""
    return [
        {"id": k, "name": v["name"], "description": v["description"],
         "category": v["category"], "tags": v["tags"]}
        for k, v in BUILTIN_TEMPLATES.items()
    ]


def apply_template(template_id: str, action_id: str, name: str,
                   description: str = "") -> Optional[str]:
    """应用模板生成动作代码。

    参数:
        template_id: 模板 ID
        action_id: 动作 ID（如 category.action_name）
        name: 动作名称
        description: 动作描述

    返回:
        生成的动作代码字符串。
    """
    template = get_template(template_id)
    if not template:
        return None

    code = template["body"]
    code = code.replace("${action_id}", action_id)
    code = code.replace("${action_name}", name)
    code = code.replace("${description}", description or template["description"])
    return code


def create_action_from_template(template_id: str, action_id: str, name: str,
                                output_dir: str, description: str = "",
                                parameters: dict = None) -> Optional[str]:
    """从模板创建完整动作文件。

    参数:
        template_id: 模板 ID
        action_id: 动作 ID
        name: 动作名称
        output_dir: 输出目录
        description: 描述
        parameters: 参数定义

    返回:
        创建的文件路径，失败返回 None。
    """
    code = apply_template(template_id, action_id, name, description)
    if not code:
        return None

    # 构建 .actus.md 文件
    cfg = {
        "name": name,
        "version": "0.0.1",
        "category": action_id.split(".")[0] if "." in action_id else "custom",
        "author": "actus-template",
        "tags": get_template(template_id).get("tags", []),
        "description": description or get_template(template_id)["description"],
    }
    if parameters:
        cfg["parameters"] = parameters

    cfg_json = json.dumps(cfg, ensure_ascii=False, indent=2)

    # 确定文件扩展名
    if template_id.startswith("shell-"):
        ext = ".sh"
    elif template_id.startswith("node-"):
        ext = ".mjs"
    else:
        ext = ".py"

    # 写入文件
    out_path = Path(output_dir) / f"{action_id}{ext}"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"#!cfg\n```json\n{cfg_json}\n```\n\n{code}"
    out_path.write_text(content, encoding="utf-8")
    logger.info(f"动作已创建: {out_path}")
    return str(out_path)


__all__ = [
    'BUILTIN_TEMPLATES',
    'apply_template',
    'create_action_from_template',
    'get_template',
    'list_templates',
    'logger'
]
