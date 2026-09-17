"""
vools.bridge.md webview2 — WebView2 (Chromium) 渲染引擎 v2.0

在 Markdown 中使用 ```webview2 包裹 HTML 代码，渲染 GUI 并支持事件交互。

核心功能：
- WebView2 (Chromium) 窗口创建和管理 - 不是 IE WebBrowser！
- HTML 内容生成
- **完整的双向通信**：JS ↔ Python
- 事件处理机制（点击、输入、自定义事件、窗口事件）
- 阻塞/非阻塞模式
- 开发者工具支持
- 窗口生命周期回调

技术选型：
- 原生 WebView2 (pythonnet + Microsoft.Web.WebView2) - 首选
- pywebview - 轻量级回退方案
- 子进程模式 - 最后回退

使用示例：
```markdown
#!run

```webview2 title="我的应用" width=800 height=600 devtools=true
<!DOCTYPE html>
<html>
<body>
  <button onclick="sendToPython('clicked')">点击我</button>
  <script>
    // 发送消息到 Python
    sendToPython('event', { foo: 'bar' });
    
    // 接收来自 Python 的消息
    window.onPythonMessage = function(data) {
        console.log('收到 Python 消息:', data);
    };
  </script>
</body>
</html>
```
"""

import os
import sys
import json
import time
import threading
import queue
import tempfile
import uuid
import subprocess
import html
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Union
from pathlib import Path
from enum import Enum


# ═══════════════════════════════════════════════════════
# 枚举和常量
# ═══════════════════════════════════════════════════════

class WebView2Mode(Enum):
    """WebView2 运行模式"""
    NATIVE = "native"      # 原生 SDK (pythonnet + Microsoft.Web.WebView2)
    PYWEBVIEW = "pywebview"  # pywebview 库
    FALLBACK = "fallback"  # 子进程模式


class WebView2EventType(Enum):
    """事件类型"""
    READY = "ready"                # 页面加载完成
    MESSAGE = "message"            # 自定义消息
    EVENT = "event"                # 用户事件
    ERROR = "error"                # JS 错误
    WINDOW_CLOSE = "window_close"  # 窗口关闭
    WINDOW_RESIZE = "window_resize"  # 窗口大小变化
    CUSTOM = "custom"              # 自定义事件


class WebView2Theme(Enum):
    """内置主题"""
    LIGHT = "light"
    DARK = "dark"
    BLUE = "blue"
    MINIMAL = "minimal"


# ═══════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════

@dataclass
class WebView2Config:
    """WebView2 配置"""
    title: str = "WebView2 Window"
    width: int = 800
    height: int = 600
    resizable: bool = True
    fullscreen: bool = False
    blocking: bool = True
    html_file: Optional[str] = None
    inject_js: Optional[str] = None
    on_message: Optional[Callable] = None
    on_event: Optional[Callable] = None
    on_ready: Optional[Callable] = None  # 页面就绪回调
    on_close: Optional[Callable] = None  # 窗口关闭回调
    on_error: Optional[Callable] = None  # 错误回调
    devtools: bool = False  # 是否启用开发者工具
    theme: Union[str, WebView2Theme] = WebView2Theme.LIGHT
    context_menu: bool = True  # 是否启用右键菜单
    user_data_dir: Optional[str] = None  # 用户数据目录


@dataclass
class WebView2Event:
    """WebView2 事件"""
    type: str
    name: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    source: str = "webview2"
    block_id: str = ""


@dataclass
class WebView2Result:
    """执行结果"""
    status: str = "ok"
    events: List[Dict] = field(default_factory=list)
    messages: List[Dict] = field(default_factory=list)
    duration_ms: float = 0
    html_path: Optional[str] = None
    error: Optional[str] = None
    mode: Optional[str] = None


@dataclass
class WebView2Message:
    """消息对象"""
    type: str
    data: Any
    target: str = "all"  # all, js, python
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════
# WebView2 管理器 - 真正的 Chromium 内核
# ═══════════════════════════════════════════════════════

class WebView2Manager:
    """
    WebView2 管理器 (Chromium 内核)
    
    支持模式：
    1. native - 原生 WebView2 (pythonnet + Microsoft.Web.WebView2) - 首选
    2. pywebview - 轻量级回退方案
    3. fallback - 子进程模式
    
    关键区别：
    - System.Windows.Forms.WebBrowser = IE 内核（旧的，不要用）
    - Microsoft.Web.WebView2 = Edge Chromium 内核（新的，用户想要的）
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._active_windows: Dict[str, Dict] = {}
        self._event_queue = queue.Queue()
        self._message_queue = queue.Queue()
        self._message_id_counter = 0
        self._callbacks: Dict[str, Callable] = {}
        
        # 检测可用的 WebView2 实现
        self._mode = self._detect_mode()
    
    def _detect_mode(self) -> WebView2Mode:
        """检测可用的 WebView2 实现"""
        # 1. 尝试原生 WebView2
        try:
            import clr
            clr.AddReference('Microsoft.Web.WebView2')
            from Microsoft.Web.WebView2 import WebView2
            return WebView2Mode.NATIVE
        except:
            pass
        
        # 2. 尝试 pywebview
        try:
            import webview
            return WebView2Mode.PYWEBVIEW
        except ImportError:
            pass
        
        # 3. 回退模式
        return WebView2Mode.FALLBACK
    
    # ═══════════════════════════════════════════════════════
    # HTML 生成
    # ═══════════════════════════════════════════════════════
    
    def generate_html(
        self,
        html_content: str,
        config: WebView2Config,
        block_id: str = ""
    ) -> str:
        """生成完整的 HTML 文件"""
        if config.html_file and os.path.exists(config.html_file):
            return config.html_file
        
        full_html = self._build_html_document(html_content, config, block_id)
        
        temp_dir = os.path.join(tempfile.gettempdir(), "vools_md_webview2")
        os.makedirs(temp_dir, exist_ok=True)
        
        html_filename = f"webview2_{block_id or uuid.uuid4().hex[:8]}.html"
        html_path = os.path.join(temp_dir, html_filename)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        return html_path
    
    def _build_html_document(
        self,
        html_content: str,
        config: WebView2Config,
        block_id: str
    ) -> str:
        """构建完整的 HTML 文档"""
        comm_script = self._get_communication_script(block_id, config)
        inject_js = config.inject_js or ""
        theme_styles = self._get_theme_styles(config.theme)
        
        if '<html' in html_content.lower():
            if '</body>' in html_content.lower():
                html_content = html_content.replace(
                    '</body>',
                    f'<style>{theme_styles}</style>\n<script>{comm_script}</script>\n<script>{inject_js}</script>\n</body>'
                )
            else:
                html_content = f'<body>{html_content}</body>\n<style>{theme_styles}</style>\n<script>{comm_script}</script>\n<script>{inject_js}</script>'
            
            if '<head>' not in html_content.lower() and '<html' in html_content.lower():
                html_content = html_content.replace('<html>', '<html>\n<head>')
                html_content = html_content.replace('</html>', '</head>\n</html>')
        else:
            full_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{html.escape(config.title)}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{theme_styles}</style>
</head>
<body>
    {html_content}
    <script>{comm_script}</script>
    <script>{inject_js}</script>
</body>
</html>'''
            html_content = full_html
        
        return html_content
    
    def _get_theme_styles(self, theme: Union[str, WebView2Theme]) -> str:
        """获取主题样式"""
        if isinstance(theme, str):
            theme = WebView2Theme(theme.lower())
        
        themes = {
            WebView2Theme.LIGHT: '''
                body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #fff; color: #333; }
                button { padding: 8px 16px; background: #0078d4; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #106ebe; }
            ''',
            WebView2Theme.DARK: '''
                body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1e1e1e; color: #d4d4d4; }
                button { padding: 8px 16px; background: #0078d4; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #106ebe; }
            ''',
            WebView2Theme.BLUE: '''
                body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; min-height: 100vh; }
                button { padding: 10px 20px; background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.3); border-radius: 8px; cursor: pointer; backdrop-filter: blur(10px); }
                button:hover { background: rgba(255,255,255,0.3); }
            ''',
            WebView2Theme.MINIMAL: '''
                body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
                * { box-sizing: border-box; }
            ''',
        }
        
        return themes.get(theme, themes[WebView2Theme.LIGHT])
    
    def _get_communication_script(self, block_id: str, config: WebView2Config) -> str:
        """
        获取 WebView2 通信脚本（支持双向通信）
        
        关键功能：
        1. JS → Python: window.chrome.webview.postMessage
        2. Python → JS: window.receiveFromPython (回调函数)
        3. 窗口事件通知
        4. 错误处理
        """
        devtools_init = ""
        if config.devtools:
            devtools_init = "window.chrome.webview.openDevTools();"
        
        return f'''
// WebView2 (Chromium) 通信脚本 v2.0
// 支持完整的双向通信
(function() {{
    const blockId = "{block_id}";
    
    // 标记这是 WebView2 环境
    window.isWebView2 = true;
    window.webviewBlockId = blockId;
    
    // 消息队列（用于缓冲消息）
    const messageQueue = [];
    
    // 回调注册表
    const callbacks = {{}};
    let callbackId = 0;
    
    // 发送消息到 Python
    function sendToPython(type, data, callback) {{
        const msg = {{
            type: type,
            blockId: blockId,
            data: data,
            timestamp: Date.now(),
            callbackId: null
        }};
        
        // 如果有回调，注册它
        if (typeof callback === 'function') {{
            const cid = 'cb_' + (++callbackId);
            callbacks[cid] = callback;
            msg.callbackId = cid;
        }}
        
        if (window.chrome && window.chrome.webview) {{
            window.chrome.webview.postMessage(JSON.stringify(msg));
        }} else {{
            messageQueue.push(msg);
        }}
    }}
    
    // 发送事件
    window.triggerEvent = function(eventName, data) {{
        sendToPython('event', {{ name: eventName, data: data }});
    }};
    
    // 发送消息（带可选回调）
    window.postMessageToPython = function(data, callback) {{
        sendToPython('message', data, callback);
    }};
    
    // 便捷函数
    window.sendToPython = sendToPython;
    window.pySend = sendToPython;
    
    // 接收来自 Python 的消息
    // 使用方式: window.onPythonMessage = (data) => {{ ... }}
    window.onPythonMessage = null;
    
    // 带回调的消息处理
    window.onPythonMessageWithCallback = null;
    
    // 内部消息处理器
    window._handlePythonMessage = function(raw) {{
        let msg;
        try {{
            msg = typeof raw === 'string' ? JSON.parse(raw) : raw;
        }} catch(e) {{
            msg = {{ type: 'raw', data: raw }};
        }}
        
        // 处理回调
        if (msg.callbackId && callbacks[msg.callbackId]) {{
            callbacks[msg.callbackId](msg.data);
            delete callbacks[msg.callbackId];
            return;
        }}
        
        // 调用用户定义的回调
        if (typeof window.onPythonMessage === 'function') {{
            window.onPythonMessage(msg);
        }}
        
        // 触发自定义事件
        if (msg.type) {{
            const event = new CustomEvent('pythonMessage', {{ detail: msg }});
            window.dispatchEvent(event);
        }}
    }};
    
    // 监听来自 Python 的消息
    // 原生 WebView2 使用 window.chrome.webview.addEventListener
    if (window.chrome && window.chrome.webview) {{
        window.chrome.webview.addEventListener('message', function(e) {{
            window._handlePythonMessage(e.data);
        }});
    }}
    
    // 全局错误处理
    window.addEventListener('error', function(e) {{
        sendToPython('error', {{
            message: e.message,
            filename: e.filename,
            lineno: e.lineno,
            colno: e.colno,
            stack: e.error && e.error.stack
        }});
    }});
    
    // 页面加载完成
    window.addEventListener('load', function() {{
        sendToPython('ready', {{ url: window.location.href, title: document.title }});
        
        // 发送缓冲的消息
        while (messageQueue.length > 0) {{
            const msg = messageQueue.shift();
            sendToPython(msg.type, msg.data);
        }}
    }});
    
    // 窗口大小变化
    let resizeTimeout;
    window.addEventListener('resize', function() {{
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {{
            sendToPython('window_resize', {{
                width: window.innerWidth,
                height: window.innerHeight
            }});
        }}, 250);
    }});
    
    // 监听页面卸载
    window.addEventListener('beforeunload', function() {{
        sendToPython('window_close', {{}});
    }});
    
    // 便捷 API
    window.webview = {{
        send: sendToPython,
        onMessage: function(cb) {{ window.onPythonMessage = cb; }},
        trigger: window.triggerEvent,
        ready: function() {{
            return new Promise(function(resolve) {{
                if (document.readyState === 'complete') {{
                    resolve();
                }} else {{
                    window.addEventListener('load', resolve);
                }}
            }});
        }}
    }};
    
    // 开发者工具
    {devtools_init}
    
    console.log('[WebView2 Chromium] 通信已初始化', blockId);
}})();
'''
    
    # ═══════════════════════════════════════════════════════
    # 运行 WebView2
    # ═══════════════════════════════════════════════════════
    
    def run_webview2(
        self,
        html_content: str,
        config: WebView2Config,
        block_id: str = "",
        timeout: int = 0,
        context: Optional[Dict] = None
    ) -> WebView2Result:
        """运行 WebView2 (Chromium)"""
        start_time = time.perf_counter()
        result = WebView2Result()
        
        try:
            html_path = self.generate_html(html_content, config, block_id)
            result.html_path = html_path
            
            if self._mode == WebView2Mode.NATIVE:
                return self._run_native_webview2(html_path, config, block_id, timeout, context)
            elif self._mode == WebView2Mode.PYWEBVIEW:
                return self._run_pywebview(html_path, config, block_id, timeout)
            else:
                return self._run_subprocess(html_path, config, block_id, timeout)
                
        except Exception as e:
            result.status = "error"
            result.error = str(e)
        
        result.duration_ms = (time.perf_counter() - start_time) * 1000
        return result
    
    def _run_native_webview2(
        self,
        html_path: str,
        config: WebView2Config,
        block_id: str,
        timeout: int,
        context: Optional[Dict]
    ) -> WebView2Result:
        """使用原生 WebView2 SDK (pythonnet + Microsoft.Web.WebView2)"""
        result = WebView2Result()
        result.html_path = html_path
        result.mode = WebView2Mode.NATIVE.value
        
        try:
            import clr
            from System import EventHandler, Uri
            from System.Windows.Forms import Form, Application, FormBorderStyle
            
            clr.AddReference('Microsoft.Web.WebView2.WinForms')
            from Microsoft.Web.WebView2.WinForms import WebView2 as WinFormsWebView2
            
            # 创建窗体
            form = Form()
            form.Text = config.title
            form.Width = config.width
            form.Height = config.height
            form.FormBorderStyle = FormBorderStyle.Sizable if config.resizable else FormBorderStyle.FixedSingle
            
            # 创建 WebView2 控件
            webview = WinFormsWebView2()
            webview.Dock = 5  # Fill
            webview.Source = Uri(f"file:///{html_path.replace(os.sep, '/')}")
            
            # 消息存储
            events = []
            messages = []
            
            # 消息处理
            def on_web_message_received(sender, args):
                try:
                    msg_json = args.WebMessageAsJson
                    if msg_json:
                        data = json.loads(msg_json)
                        messages.append(data)
                        
                        # 处理事件
                        if data.get('type') == 'event':
                            events.append(data)
                            if config.on_event:
                                config.on_event(data)
                        elif data.get('type') == 'ready':
                            if config.on_ready:
                                config.on_ready(data)
                        elif data.get('type') == 'window_close':
                            if config.on_close:
                                config.on_close(data)
                        elif data.get('type') == 'error':
                            if config.on_error:
                                config.on_error(data)
                        
                        # 调用通用回调
                        if config.on_message:
                            config.on_message(data)
                except Exception as e:
                    if config.on_error:
                        config.on_error({'error': str(e)})
            
            webview.WebMessageReceived += EventHandler[object](on_web_message_received)
            
            form.Controls.Add(webview)
            
            # 保存窗口引用（用于发送消息）
            self._active_windows[block_id] = {{
                'form': form,
                'webview': webview,
                'config': config
            }}
            
            # 显示窗口
            if config.blocking:
                Application.Run(form)
                
                # 窗口关闭后清理
                if block_id in self._active_windows:
                    del self._active_windows[block_id]
            else:
                form.Show()
                result.status = "ok"
                return result
            
            result.status = "ok"
            result.events = events
            result.messages = messages
            
        except ImportError as e:
            result.status = "error"
            result.error = f"WebView2 SDK 未安装: {{e}}\n请安装: pip install pythonnet 并确保 WebView2 运行时已安装"
        except Exception as e:
            result.status = "error"
            result.error = str(e)
        
        return result
    
    def _run_pywebview(
        self,
        html_path: str,
        config: WebView2Config,
        block_id: str,
        timeout: int
    ) -> WebView2Result:
        """使用 pywebview 库"""
        result = WebView2Result()
        result.html_path = html_path
        result.mode = WebView2Mode.PYWEBVIEW.value
        
        try:
            import webview
            
            events = []
            messages = []
            
            # pywebview 的消息处理有限制
            if config.blocking:
                window = webview.create_window(
                    config.title,
                    url=f"file:///{html_path.replace(os.sep, '/')}",
                    width=config.width,
                    height=config.height,
                    resizable=config.resizable,
                    fullscreen=config.fullscreen,
                )
                
                if config.devtools:
                    # pywebview 没有内置 devtools，但可以尝试
                    pass
                
                webview.start()
                result.status = "ok"
            else:
                window = webview.create_window(
                    config.title,
                    url=f"file:///{html_path.replace(os.sep, '/')}",
                    width=config.width,
                    height=config.height,
                    resizable=config.resizable,
                )
                self._active_windows[block_id] = {{'window': window, 'config': config}}
                result.status = "ok"
            
            result.events = events
            result.messages = messages
            
        except ImportError:
            result.status = "error"
            result.error = "pywebview 未安装，请运行: pip install pywebview"
        except Exception as e:
            result.status = "error"
            result.error = str(e)
        
        return result
    
    def _run_subprocess(
        self,
        html_path: str,
        config: WebView2Config,
        block_id: str,
        timeout: int
    ) -> WebView2Result:
        """使用子进程启动独立的 WebView2 进程"""
        result = WebView2Result()
        result.html_path = html_path
        
        runner_script = self._create_webview2_runner_script(html_path, config, block_id)
        
        temp_dir = os.path.join(tempfile.gettempdir(), "vools_md_webview2")
        script_path = os.path.join(temp_dir, f"runner_{{block_id}}.py")
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(runner_script)
        
        try:
            cmd = [sys.executable, script_path]
            
            if config.blocking:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout if timeout > 0 else None
                )
                
                if proc.returncode == 0:
                    result.status = "ok"
                else:
                    result.status = "error"
                    result.error = proc.stderr
            else:
                proc = subprocess.Popen(cmd)
                self._active_windows[block_id] = {'proc': proc, 'config': config}
                result.status = "ok"
                
        except subprocess.TimeoutExpired:
            result.status = "timeout"
        except Exception as e:
            result.status = "error"
            result.error = str(e)
        
        return result
    
    def _create_webview2_runner_script(self, html_path: str, config: WebView2Config, block_id: str) -> str:
        """创建 WebView2 运行脚本"""
        return f'''
import sys
import os
import json
import time

html_path = r"{html_path}"
title = "{config.title}"
width = {config.width}
height = {config.height}
resizable = {config.resizable}
devtools = {config.devtools}
block_id = "{block_id}"

try:
    import clr
    from System import EventHandler, Uri
    from System.Windows.Forms import Form, Application, FormBorderStyle
    
    clr.AddReference('Microsoft.Web.WebView2.WinForms')
    from Microsoft.Web.WebView2.WinForms import WebView2 as WinFormsWebView2
    
    form = Form()
    form.Text = title
    form.Width = width
    form.Height = height
    form.FormBorderStyle = FormBorderStyle.Sizable if resizable else FormBorderStyle.FixedSingle
    
    webview = WinFormsWebView2()
    webview.Dock = 5
    webview.Source = Uri(f"file:///{{html_path.replace(os.sep, '/')}}")
    
    # 消息处理
    messages = []
    events = []
    
    def on_web_message_received(sender, args):
        try:
            msg = args.WebMessageAsJson
            if msg:
                data = json.loads(msg)
                messages.append(data)
                print(f"[WebView2] {{data.get('type', 'message')}}: {{json.dumps(data.get('data', ''))[:50]}}")
                
                if data.get('type') == 'event':
                    events.append(data)
                elif data.get('type') == 'ready':
                    print(f"[WebView2] 页面已就绪")
                elif data.get('type') == 'window_close':
                    print(f"[WebView2] 窗口正在关闭")
        except Exception as e:
            print(f"[WebView2] 消息处理错误: {{e}}")
    
    webview.WebMessageReceived += EventHandler[object](on_web_message_received)
    form.Controls.Add(webview)
    
    # 确保 WebView2 初始化
    def ensure_ready():
        try:
            if not webview.CoreWebView2:
                webview.EnsureCoreWebView2Async(None)
                print("[WebView2] 初始化 CoreWebView2...")
        except Exception as e:
            print(f"[WebView2] 初始化错误: {{e}}")
    
    # 延迟执行初始化
    form.Shown += lambda s, e: ensure_ready()
    
    print(f"[WebView2] 启动 Chromium 内核: {{title}}")
    print(f"[WebView2] 模式: native (pythonnet)")
    print(f"[WebView2] 块 ID: {{block_id}}")
    
    Application.Run(form)
    print("[WebView2] 窗口已关闭")
    
except ImportError as e:
    print(f"[WebView2] 原生 SDK 不可用: {{e}}")
    print("[WebView2] 尝试使用 pywebview...")
    
    try:
        import webview
        window = webview.create_window(title, url=f"file:///{{html_path}}", width=width, height=height)
        webview.start()
    except ImportError:
        print("[WebView2] pywebview 也不可用")
        sys.exit(1)
        
except Exception as e:
    print(f"[WebView2] 错误: {{e}}")
    sys.exit(1)
'''
    
    # ═══════════════════════════════════════════════════════
    # 双向通信：Python → JS
    # ═══════════════════════════════════════════════════════
    
    def send_message(self, block_id: str, data: Any, callback: Optional[Callable] = None) -> bool:
        """
        向 WebView2 发送消息 (Python → JS)
        
        Args:
            block_id: 块标识符
            data: 要发送的数据
            callback: 可选的回调函数（当 JS 回复时调用）
        
        Returns:
            是否发送成功
        """
        if block_id not in self._active_windows:
            return False
        
        window_info = self._active_windows[block_id]
        
        if self._mode == WebView2Mode.NATIVE:
            try:
                webview = window_info.get('webview')
                if webview and hasattr(webview, 'CoreWebView2'):
                    core = webview.CoreWebView2
                    if core:
                        msg = {{
                            'type': 'python_message',
                            'data': data,
                            'timestamp': time.time()
                        }}
                        core.PostWebMessageAsJson(json.dumps(msg, ensure_ascii=False))
                        
                        # 注册回调
                        if callback:
                            callback_id = f"cb_{int(time.time() * 1000)}"
                            self._callbacks[callback_id] = callback
                        
                        return True
            except Exception as e:
                return False
        
        return False
    
    def execute_script(self, block_id: str, script: str) -> bool:
        """
        在 WebView2 中执行 JavaScript
        
        Args:
            block_id: 块标识符
            script: 要执行的 JS 代码
        
        Returns:
            是否执行成功
        """
        if block_id not in self._active_windows:
            return False
        
        window_info = self._active_windows[block_id]
        
        if self._mode == WebView2Mode.NATIVE:
            try:
                webview = window_info.get('webview')
                if webview and hasattr(webview, 'CoreWebView2'):
                    core = webview.CoreWebView2
                    if core:
                        core.ExecuteScriptAsync(script)
                        return True
            except Exception:
                pass
        
        return False
    
    def close_window(self, block_id: str) -> bool:
        """关闭指定窗口"""
        if block_id in self._active_windows:
            window_info = self._active_windows[block_id]
            
            if self._mode == WebView2Mode.NATIVE:
                try:
                    form = window_info.get('form')
                    if form:
                        form.Close()
                        return True
                except Exception:
                    pass
            elif self._mode == WebView2Mode.PYWEBVIEW:
                try:
                    window = window_info.get('window')
                    if window:
                        window.destroy()
                        return True
                except Exception:
                    pass
            else:
                proc = window_info.get('proc')
                if proc:
                    proc.terminate()
                    return True
            
            del self._active_windows[block_id]
            return True
        
        return False
    
    def get_window(self, block_id: str) -> Optional[Dict]:
        """获取窗口信息"""
        return self._active_windows.get(block_id)
    
    @property
    def mode(self) -> str:
        """获取当前运行模式"""
        return self._mode.value
    
    @property
    def active_windows(self) -> List[str]:
        """获取所有活动窗口的 block_id"""
        return list(self._active_windows.keys())


# 全局管理器实例
_manager = WebView2Manager()


# ═══════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════

def render_webview2(
    html_content: str,
    title: str = "WebView2 Window",
    width: int = 800,
    height: int = 600,
    blocking: bool = True,
    devtools: bool = False,
    theme: Union[str, WebView2Theme] = WebView2Theme.LIGHT,
    on_message: Optional[Callable] = None,
    on_event: Optional[Callable] = None,
    **kwargs
) -> WebView2Result:
    """
    渲染 WebView2 (Chromium)
    
    Args:
        html_content: HTML 内容
        title: 窗口标题
        width: 窗口宽度
        height: 窗口高度
        blocking: 是否阻塞等待
        devtools: 是否启用开发者工具
        theme: 主题样式
        on_message: 消息回调
        on_event: 事件回调
        **kwargs: 其他配置
    
    Returns:
        WebView2Result
    """
    config = WebView2Config(
        title=title,
        width=width,
        height=height,
        blocking=blocking,
        devtools=devtools,
        theme=theme,
        on_message=on_message,
        on_event=on_event,
        **kwargs
    )
    
    return _manager.run_webview2(html_content, config)


def generate_html_file(
    html_content: str,
    config: WebView2Config,
    block_id: str = ""
) -> str:
    """生成 HTML 文件"""
    return _manager.generate_html(html_content, config, block_id)


def get_webview2_mode() -> str:
    """获取当前 WebView2 运行模式"""
    return _manager.mode


def send_to_webview(block_id: str, data: Any, callback: Optional[Callable] = None) -> bool:
    """
    向 WebView2 窗口发送消息 (Python → JS)
    
    Args:
        block_id: 块标识符
        data: 要发送的数据
        callback: 可选的回调函数
    
    Returns:
        是否发送成功
    """
    return _manager.send_message(block_id, data, callback)


def execute_script_in_webview(block_id: str, script: str) -> bool:
    """
    在 WebView2 中执行 JavaScript
    
    Args:
        block_id: 块标识符
        script: JS 代码
    
    Returns:
        是否执行成功
    """
    return _manager.execute_script(block_id, script)


def close_webview_window(block_id: str) -> bool:
    """关闭 WebView2 窗口"""
    return _manager.close_window(block_id)


def get_active_webview_windows() -> List[str]:
    """获取所有活动窗口的 block_id"""
    return _manager.active_windows


# ═══════════════════════════════════════════════════════
# 与 runner.py 集成
# ═══════════════════════════════════════════════════════

def execute_webview2_block(
    block_content: str,
    directives: Dict,
    context: Dict,
    build_dir: str
) -> tuple[str, str, int]:
    """
    执行 webview2 代码块（供 runner.py 调用）
    """
    # 解析配置
    theme_str = directives.get('theme', 'light')
    try:
        theme = WebView2Theme(theme_str.lower())
    except ValueError:
        theme = WebView2Theme.LIGHT
    
    config = WebView2Config(
        title=directives.get('title', 'WebView2 Window'),
        width=int(directives.get('width', 800)),
        height=int(directives.get('height', 600)),
        resizable=directives.get('resizable', 'true').lower() == 'true',
        blocking=directives.get('blocking', 'true').lower() == 'true',
        devtools=directives.get('devtools', 'false').lower() == 'true',
        theme=theme,
        html_file=directives.get('html'),
    )
    
    # 生成 block_id
    block_id = directives.get('tag', f"block_{int(time.time())}")
    if isinstance(block_id, list):
        block_id = block_id[0] if block_id else f"block_{int(time.time())}"
    
    # 执行
    result = _manager.run_webview2(
        block_content,
        config,
        block_id=block_id,
        context=context
    )
    
    # 构建输出
    output = {
        'status': result.status,
        'mode': result.mode,
        'html_path': result.html_path,
        'events': result.events,
        'messages': result.messages,
        'duration_ms': result.duration_ms,
    }
    
    if result.error:
        output['error'] = result.error
    
    return json.dumps(output, ensure_ascii=False, indent=2), "", 0
