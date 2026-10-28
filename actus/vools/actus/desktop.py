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


def _resolve_repo_root() -> Path:
    """解析宿主仓库根。

    本模块已迁入 vools.actus（`…/vools/actus/vools/actus/`），所以
    `Path(__file__).parent.parent` 早已不是仓库根 —— 迁移后直接按包位置推导会拿到
    `…/vools/actus/vools`（不存在）。改为三档：
    1. `ACTUS_REPO_ROOT` 环境变量（Actus 侧 `_vools_bootstrap` 会设它）；
    2. 向上回溯找标记（`contracts/action.schema.json` 或 `engine/`）；
    3. 兜底返回 vools-actus 子项目根（`…/vools/actus`）。
    """
    env = os.environ.get('ACTUS_REPO_ROOT')
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for p in (here, here.parent, here.parent.parent, here.parent.parent.parent):
        if (p / 'contracts' / 'action.schema.json').exists() or (p / 'engine').is_dir():
            return p
    return here.parent.parent.parent


_REPO_ROOT = _resolve_repo_root()

# 引擎根目录
ENGINE_DIR = _REPO_ROOT / "engine"

# 创建 FastAPI 应用
app = FastAPI(title="Actus Desktop", version="0.1.0")

def _ensure_dir(path: Path, label: str) -> bool:
    """确保目录存在；**失败只记日志，绝不让 import 崩**。

    改前是裸 `mkdir(exist_ok=True)`：只读安装（site-packages 只读）下
    `import vools.actus.desktop` 直接 PermissionError —— 模块导入不应有写副作用。
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        logger.warning("无法创建 %s 目录 %s: %s（该能力可能不可用）", label, path, exc)
        return False


# 静态文件：**import 期不做任何 mkdir**（只读安装下 import 不许崩、也不许写）。
# 目录存在就挂上，不存在就跳过（页面样式内联在模板里，不依赖静态资源）。
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning("静态目录不存在，已跳过 /static 挂载: %s", STATIC_DIR)

# 模板：目录随包分发（templates/index.html），同样不在 import 期创建
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_repo_root() -> Path:
    """获取仓库根目录。"""
    return _REPO_ROOT


def _load_actions_index_checked():
    """加载动作索引，返回 (actions, error)。error 非空表示**加载失败**（不是"没有动作"）。"""
    try:
        return _load_actions_index(), ''
    except Exception as exc:  # noqa: BLE001 —— 端点层要把原因回给调用方
        return {}, '%s: %s' % (type(exc).__name__, exc)


def _load_actions_index() -> dict:
    """加载动作索引（失败返回空 dict；端点层请用 `_load_actions_index_checked`）。"""
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
    """主页。

    审计修复：改前用旧签名 `TemplateResponse("index.html", {...})` —— Starlette
    新签名要求 request 在首位，实际会把 context dict 当模板名 →
    `TypeError: unhashable type: 'dict'`，**首页 500，Web UI 从未跑通**。
    """
    actions, load_error = _load_actions_index_checked()
    return templates.TemplateResponse(request, "index.html", {
        "actions": actions,
        "action_count": len(actions),
        "load_error": load_error,
    })


@app.get("/api/actions")
async def api_actions():
    """API: 获取动作列表。加载失败 → 明确报错（改前静默返回空列表，看起来像"没有动作"）。"""
    actions, load_error = _load_actions_index_checked()
    if load_error:
        return JSONResponse({"status": "error", "error": load_error}, status_code=500)
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
    if not isinstance(params, dict):
        return JSONResponse({"status": "error",
                             "error": "params 必须是 JSON 对象，得到 %s" % type(params).__name__},
                            status_code=400)

    try:
        # executor.execute() **没有** repo_root 参数（改前传了它 → 本端点对任何
        # 动作都 500: TypeError）。仓库根由 ACTUS_REPO_ROOT/indexer 决定，无需传。
        # 也不再 `sys.path.insert(ENGINE_DIR)`：包里本来就能 import，且每个请求
        # 插一次会让 sys.path 无限增长（实测累积重复项）。
        from vools.actus.executor import execute
        result = execute(action_id, params=params)
    except Exception as e:  # noqa: BLE001 —— 引擎自身异常 → 5xx
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

    # 审计修复（假成功）：改前恒 `{"status":"ok"} + 200`，动作失败也报成功。
    # 现在外层 status 透传内层，HTTP 码按错误类别区分客户端/服务端错误。
    inner_status = (result or {}).get("status")
    if inner_status == "ok":
        return JSONResponse({"status": "ok", "data": result})
    err = (result or {}).get("error") or {}
    err_code = err.get("code") if isinstance(err, dict) else ""
    body_out = {"status": inner_status or "failed", "data": result}
    if inner_status == "awaiting_confirmation":
        # 正常业务态：还没执行，等人类确认（不是错误，也不是成功）
        return JSONResponse(body_out, status_code=202)
    if err_code == "action_not_found":
        return JSONResponse(body_out, status_code=404)
    if err_code in ("action_invalid", "param_invalid", "args_invalid", "trust_rejected",
                    "visibility_denied", "auth_required", "permission_denied",
                    "contract_invalid", "schema_invalid"):
        return JSONResponse(body_out, status_code=400)
    return JSONResponse(body_out, status_code=500)


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
    try:
        from vools.actus import __version__ as _actus_version
    except Exception:  # noqa: BLE001 —— 版本读不到不该让状态端点失败
        _actus_version = "unknown"
    return JSONResponse({
        "status": "ok",
        "data": {
            "action_count": len(actions),
            # 审计修复：改前硬编码 "Actus v0.8.0"，实际包版本 0.9.0 —— 状态端点会撒谎
            "engine": "Actus v%s" % _actus_version,
            "platform": sys.platform,
        }
    })


# ── 启动函数 ──

def start(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    """启动桌面服务器。"""
    import uvicorn
    import threading

    # 目录保障放在**启动时**（不是 import 时）：只读安装下这里失败也只记日志。
    _ensure_dir(STATIC_DIR, 'static')
    _ensure_dir(TEMPLATES_DIR, 'templates')
    
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
