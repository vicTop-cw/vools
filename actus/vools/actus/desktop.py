"""desktop/app.py —— Actus Desktop Server (Phase I1)。

基于 FastAPI 的桌面应用后端，提供 Web UI。
启动: actus desktop
"""

import os
import sys
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# 引擎根目录
ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"

# 创建 FastAPI 应用
app = FastAPI(title="Actus Desktop", version="0.1.0")

# 静态文件
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 模板
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_repo_root() -> Path:
    """获取仓库根目录。"""
    return Path(__file__).resolve().parent.parent


def _load_actions_index() -> dict:
    """加载动作索引。"""
    try:
        sys.path.insert(0, str(ENGINE_DIR))
        from vools.actus.indexer import scan_actions
        actions = scan_actions(validate=False)
        return {
            aid: {
                "id": aid,
                "name": a.meta.get("name", aid),
                "description": a.meta.get("description", ""),
                "category": a.meta.get("category", ""),
                "tags": a.meta.get("tags", []),
                "version": a.meta.get("version", "0.0.1"),
            }
            for aid, a in actions.items()
        }
    except Exception as e:
        logger.warning(f"加载动作索引失败: {e}")
        return {}


# ── API 路由 ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页。"""
    actions = _load_actions_index()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "actions": actions,
        "action_count": len(actions),
    })


@app.get("/api/actions")
async def api_actions():
    """API: 获取动作列表。"""
    actions = _load_actions_index()
    return JSONResponse({"status": "ok", "data": list(actions.values())})


@app.get("/api/actions/{action_id}")
async def api_action_detail(action_id: str):
    """API: 获取动作详情。"""
    actions = _load_actions_index()
    action = actions.get(action_id)
    if not action:
        return JSONResponse({"status": "error", "error": "未找到动作"}, status_code=404)
    return JSONResponse({"status": "ok", "data": action})


@app.post("/api/actions/{action_id}/run")
async def api_action_run(action_id: str, request: Request):
    """API: 运行动作。"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    params = body.get("params", {})
    
    try:
        sys.path.insert(0, str(ENGINE_DIR))
        from vools.actus.executor import execute
        repo_root = _get_repo_root()
        result = execute(action_id, params=params, repo_root=repo_root)
        return JSONResponse({"status": "ok", "data": result})
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/events")
async def api_events(event_type: str = None, limit: int = 50):
    """API: 获取事件历史。"""
    try:
        sys.path.insert(0, str(ENGINE_DIR))
        from vools.actus.eventbus import get_event_bus
        bus = get_event_bus()
        events = bus.get_history(event_type=event_type, limit=limit)
        return JSONResponse({"status": "ok", "data": events})
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/status")
async def api_status():
    """API: 系统状态。"""
    actions = _load_actions_index()
    return JSONResponse({
        "status": "ok",
        "data": {
            "action_count": len(actions),
            "engine": "Actus v0.8.0",
            "platform": sys.platform,
        }
    })


# ── 启动函数 ──

def start(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    """启动桌面服务器。"""
    import uvicorn
    import threading
    
    if open_browser:
        def _open():
            import time
            time.sleep(1.0)
            try:
                import webbrowser
                webbrowser.open(f"http://{host}:{port}")
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()
    
    uvicorn.run(app, host=host, port=port, log_level="info")


__all__ = [
    'ENGINE_DIR',
    'STATIC_DIR',
    'TEMPLATES_DIR',
    'api_action_detail',
    'api_action_run',
    'api_actions',
    'api_events',
    'api_status',
    'app',
    'index',
    'logger',
    'start',
    'templates'
]
