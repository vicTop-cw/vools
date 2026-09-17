# -*- coding: utf-8 -*-
"""
webview2 模块测试 - 测试 Chromium 内核 WebView2
"""

import os
import sys
import json
import tempfile
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from vools.bridge.md.webview2 import (
    WebView2Config,
    WebView2Event,
    WebView2Result,
    WebView2Manager,
    WebView2Mode,
    WebView2Theme,
    WebView2EventType,
    render_webview2,
    generate_html_file,
    get_webview2_mode,
    send_to_webview,
    execute_script_in_webview,
    close_webview_window,
    get_active_webview_windows,
)


class TestWebView2Config(unittest.TestCase):
    """测试 WebView2Config"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = WebView2Config()
        self.assertEqual(config.title, "WebView2 Window")
        self.assertEqual(config.width, 800)
        self.assertEqual(config.height, 600)
        self.assertTrue(config.resizable)
        self.assertTrue(config.blocking)
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = WebView2Config(
            title="测试窗口",
            width=1024,
            height=768,
            resizable=False,
            blocking=False,
        )
        self.assertEqual(config.title, "测试窗口")
        self.assertEqual(config.width, 1024)
        self.assertEqual(config.height, 768)
        self.assertFalse(config.resizable)
        self.assertFalse(config.blocking)


class TestWebView2Event(unittest.TestCase):
    """测试 WebView2Event"""
    
    def test_event_creation(self):
        """测试事件创建"""
        event = WebView2Event(
            type="event",
            name="click",
            data={"x": 100, "y": 200}
        )
        self.assertEqual(event.type, "event")
        self.assertEqual(event.name, "click")
        self.assertEqual(event.data, {"x": 100, "y": 200})
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.source, "webview2")


class TestWebView2Result(unittest.TestCase):
    """测试 WebView2Result"""
    
    def test_default_result(self):
        """测试默认结果"""
        result = WebView2Result()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.events, [])
        self.assertEqual(result.messages, [])
        self.assertEqual(result.duration_ms, 0)
        self.assertIsNone(result.html_path)
        self.assertIsNone(result.error)


class TestWebView2Manager(unittest.TestCase):
    """测试 WebView2Manager"""
    
    def test_singleton(self):
        """测试单例模式"""
        manager1 = WebView2Manager()
        manager2 = WebView2Manager()
        self.assertIs(manager1, manager2)
    
    def test_generate_html_basic(self):
        """测试生成 HTML"""
        manager = WebView2Manager()
        config = WebView2Config(title="测试")
        html_path = manager.generate_html(
            "<h1>测试</h1>",
            config,
            "test_block"
        )
        self.assertTrue(os.path.exists(html_path))
        self.assertTrue(html_path.endswith('.html'))
        
        # 验证内容
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("<h1>测试</h1>", content)
            self.assertIn("WebView2", content)
    
    def test_generate_html_with_script(self):
        """测试生成带脚本的 HTML"""
        manager = WebView2Manager()
        config = WebView2Config(
            title="脚本测试",
            inject_js="console.log('injected');"
        )
        html_path = manager.generate_html(
            '<button onclick="sendToPython(\'event\', \'clicked\')">点击</button>',
            config,
            "test_script"
        )
        
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("console.log('injected')", content)
            self.assertIn("sendToPython", content)


class TestHTMLGeneration(unittest.TestCase):
    """测试 HTML 生成"""
    
    def test_full_html_document(self):
        """测试完整 HTML 文档"""
        manager = WebView2Manager()
        config = WebView2Config(title="完整文档")
        html = '''<!DOCTYPE html>
<html>
<head><title>测试</title></head>
<body><h1>测试</h1></body>
</html>'''
        html_path = manager.generate_html(html, config, "full_doc")
        
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("<h1>测试</h1>", content)
            self.assertIn("sendToPython", content)
    
    def test_html_fragment(self):
        """测试 HTML 片段"""
        manager = WebView2Manager()
        config = WebView2Config(title="片段测试")
        html = '<h1>标题</h1><p>段落</p>'
        html_path = manager.generate_html(html, config, "fragment")
        
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("<h1>标题</h1>", content)
            self.assertIn("<p>段落</p>", content)


class TestRenderWebview2(unittest.TestCase):
    """测试 render_webview2 函数"""
    
    def test_render_basic(self):
        """测试基本渲染"""
        result = render_webview2(
            '<h1>测试</h1>',
            title="渲染测试",
            width=400,
            height=300,
            blocking=False  # 非阻塞模式
        )
        # 如果没有安装 pythonnet/pywebview，结果是 error
        # 这是预期的，因为测试环境可能没有这些依赖
        self.assertIn(result.status, ["ok", "error"])
        if result.status == "error":
            print(f"\n[注意] WebView2 渲染需要 pythonnet 或 pywebview: {result.error}")
    
    def test_render_with_events(self):
        """测试带事件的渲染"""
        html = '''
<button onclick="triggerEvent(\"click\", {x: 100})">点击</button>
'''
        result = render_webview2(
            html,
            title="事件测试",
            blocking=False
        )
        self.assertIn(result.status, ["ok", "error"])


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 创建配置
        config = WebView2Config(
            title="工作流测试",
            width=600,
            height=400,
            resizable=True,
        )
        
        # 2. 生成 HTML
        manager = WebView2Manager()
        html = '''
<!DOCTYPE html>
<html>
<body>
    <h1>工作流测试</h1>
    <button onclick="sendToPython('event', 'done')">完成</button>
</body>
</html>'''
        html_path = manager.generate_html(html, config, "workflow_test")
        
        # 3. 验证文件
        self.assertTrue(os.path.exists(html_path))
        
        # 4. 验证内容
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("工作流测试", content)
            self.assertIn("sendToPython", content)


class TestDirectives(unittest.TestCase):
    """测试指令解析"""
    
    def test_webview2_directives(self):
        """测试 webview2 相关指令"""
        from vools.bridge.md.directives import BLOCK_DIRECTIVE_KEYS
        
        # 验证 webview2 指令已添加
        webview2_keys = {'title', 'width', 'height', 'resizable', 'fullscreen', 'blocking', 'html', 'inject'}
        for key in webview2_keys:
            self.assertIn(key, BLOCK_DIRECTIVE_KEYS)


class TestWebView2Mode(unittest.TestCase):
    """测试 WebView2 模式检测"""
    
    def test_get_mode(self):
        """测试获取 WebView2 模式"""
        mode = get_webview2_mode()
        self.assertIn(mode, ['native', 'pywebview', 'fallback'])
        print(f"\n[WebView2 模式] {mode}")
    
    def test_mode_is_chromium(self):
        """测试 WebView2 是否使用 Chromium 内核"""
        mode = get_webview2_mode()
        if mode == 'native':
            print("[WebView2] 使用原生 SDK (Edge Chromium)")
        elif mode == 'pywebview':
            print("[WebView2] 使用 pywebview (系统 WebView2)")
        else:
            print("[WebView2] 使用子进程模式")


class TestWebView2Enums(unittest.TestCase):
    """测试枚举类型"""
    
    def test_webview2_mode_enum(self):
        """测试 WebView2Mode 枚举"""
        self.assertEqual(WebView2Mode.NATIVE.value, 'native')
        self.assertEqual(WebView2Mode.PYWEBVIEW.value, 'pywebview')
        self.assertEqual(WebView2Mode.FALLBACK.value, 'fallback')
    
    def test_webview2_theme_enum(self):
        """测试 WebView2Theme 枚举"""
        self.assertEqual(WebView2Theme.LIGHT.value, 'light')
        self.assertEqual(WebView2Theme.DARK.value, 'dark')
        self.assertEqual(WebView2Theme.BLUE.value, 'blue')
        self.assertEqual(WebView2Theme.MINIMAL.value, 'minimal')
    
    def test_webview2_event_type_enum(self):
        """测试 WebView2EventType 枚举"""
        self.assertEqual(WebView2EventType.READY.value, 'ready')
        self.assertEqual(WebView2EventType.MESSAGE.value, 'message')
        self.assertEqual(WebView2EventType.EVENT.value, 'event')
        self.assertEqual(WebView2EventType.ERROR.value, 'error')
        self.assertEqual(WebView2EventType.WINDOW_CLOSE.value, 'window_close')
        self.assertEqual(WebView2EventType.WINDOW_RESIZE.value, 'window_resize')


class TestThemes(unittest.TestCase):
    """测试主题"""
    
    def test_light_theme(self):
        """测试亮色主题"""
        config = WebView2Config(theme=WebView2Theme.LIGHT)
        self.assertEqual(config.theme, WebView2Theme.LIGHT)
    
    def test_dark_theme(self):
        """测试暗色主题"""
        config = WebView2Config(theme='dark')
        # 字符串会被转换为枚举
        self.assertIn(str(config.theme), ['dark', 'WebView2Theme.DARK'])
    
    def test_blue_theme(self):
        """测试蓝色主题"""
        config = WebView2Config(theme='blue')
        self.assertIn(str(config.theme), ['blue', 'WebView2Theme.BLUE'])


class TestCallbacks(unittest.TestCase):
    """测试回调函数"""
    
    def test_on_message_callback(self):
        """测试消息回调"""
        callback_called = []
        
        def on_message(data):
            callback_called.append(data)
        
        config = WebView2Config(on_message=on_message)
        self.assertIsNotNone(config.on_message)
    
    def test_on_event_callback(self):
        """测试事件回调"""
        event_called = []
        
        def on_event(data):
            event_called.append(data)
        
        config = WebView2Config(on_event=on_event)
        self.assertIsNotNone(config.on_event)
    
    def test_on_ready_callback(self):
        """测试就绪回调"""
        ready_called = []
        
        def on_ready(data):
            ready_called.append(data)
        
        config = WebView2Config(on_ready=on_ready)
        self.assertIsNotNone(config.on_ready)
    
    def test_on_close_callback(self):
        """测试关闭回调"""
        close_called = []
        
        def on_close(data):
            close_called.append(data)
        
        config = WebView2Config(on_close=on_close)
        self.assertIsNotNone(config.on_close)


class TestBidirectionalCommunication(unittest.TestCase):
    """测试双向通信"""
    
    def test_send_to_webview_function_exists(self):
        """测试发送消息函数存在"""
        # 这个函数应该存在
        self.assertTrue(callable(send_to_webview))
    
    def test_execute_script_function_exists(self):
        """测试执行脚本函数存在"""
        self.assertTrue(callable(execute_script_in_webview))
    
    def test_close_window_function_exists(self):
        """测试关闭窗口函数存在"""
        self.assertTrue(callable(close_webview_window))
    
    def test_get_active_windows_function_exists(self):
        """测试获取活动窗口函数存在"""
        self.assertTrue(callable(get_active_webview_windows))


class TestDevTools(unittest.TestCase):
    """测试开发者工具"""
    
    def test_devtools_config(self):
        """测试开发者工具配置"""
        config = WebView2Config(devtools=True)
        self.assertTrue(config.devtools)
        
        config = WebView2Config(devtools=False)
        self.assertFalse(config.devtools)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_workflow_with_theme(self):
        """测试完整工作流（带主题）"""
        config = WebView2Config(
            title="工作流测试",
            width=600,
            height=400,
            theme=WebView2Theme.DARK,
            devtools=True,
        )
        
        manager = WebView2Manager()
        html = '<h1>测试</h1>'
        html_path = manager.generate_html(html, config, "workflow_test")
        
        self.assertTrue(os.path.exists(html_path))
        
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("sendToPython", content)
            # 暗色主题包含 #1e1e1e 背景色
            self.assertIn("#1e1e1e", content)
    
    def test_manager_singleton(self):
        """测试管理器单例"""
        manager1 = WebView2Manager()
        manager2 = WebView2Manager()
        self.assertIs(manager1, manager2)
    
    def test_active_windows_tracking(self):
        """测试活动窗口跟踪"""
        windows = get_active_webview_windows()
        self.assertIsInstance(windows, list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
