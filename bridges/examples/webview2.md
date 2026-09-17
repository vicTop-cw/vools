# WebView2 示例 (Chromium 内核) v2.0

Markdown 中嵌入 **WebView2 (Chromium)** 控件，渲染 GUI 并支持事件交互。

> **重要区别**：这不是旧的 IE WebBrowser，而是 **Edge Chromium 内核**！

## 新功能 v2.0

- ✅ **完整双向通信**：JS ↔ Python
- ✅ **窗口生命周期回调**：ready, close, error
- ✅ **开发者工具支持**：`devtools=true`
- ✅ **内置主题**：light, dark, blue, minimal
- ✅ **回调机制**：支持异步回调

## 基本用法

使用 ` ```webview2 ` 包裹 HTML 代码：

```webview2 title="简单示例" width=400 height=300
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>简单示例</title>
    <style>
        body { font-family: sans-serif; padding: 20px; }
        button { padding: 10px 20px; font-size: 16px; }
    </style>
</head>
<body>
    <h1>WebView2 示例</h1>
    <button onclick="sendToPython('event', '按钮被点击了！')">点击我</button>
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

## 交互式计数器

```webview2 title="计数器" width=500 height=400
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>计数器</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 40px; }
        .counter { font-size: 48px; margin: 20px; }
        button { padding: 10px 20px; font-size: 16px; margin: 5px; }
    </style>
</head>
<body>
    <h1>计数器</h1>
    <div class="counter" id="count">0</div>
    <button onclick="decrement()">-</button>
    <button onclick="reset()">重置</button>
    <button onclick="increment()">+</button>
    <script>
        let count = 0;
        function update() {
            document.getElementById('count').textContent = count;
            sendToPython('update', count);
        }
        function increment() { count++; update(); }
        function decrement() { count--; update(); }
        function reset() { count = 0; update(); }
        function sendToPython(type, data) {
            if (window.chrome && window.chrome.webview) {
                window.chrome.webview.postMessage({ type: type, data: data });
            }
        }
    </script>
</body>
</html>
```

## 双向通信示例 (Python → JS)

```webview2 title="双向通信" width=500 height=400
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>双向通信</title>
    <style>
        body { font-family: sans-serif; padding: 20px; }
        #log { height: 200px; border: 1px solid #ccc; padding: 10px; overflow-y: auto; }
    </style>
</head>
<body>
    <h1>双向通信</h1>
    <button onclick="sendMessage()">发送消息到 Python</button>
    <button onclick="requestData()">请求数据</button>
    <div id="log"></div>
    <script>
        const log = document.getElementById('log');
        
        function addLog(msg) {
            log.innerHTML += '<div>' + msg + '</div>';
            log.scrollTop = log.scrollHeight;
        }
        
        // 发送消息到 Python
        function sendMessage() {
            sendToPython('message', 'Hello from JS!');
            addLog('发送: Hello from JS!');
        }
        
        // 带回调的消息
        function requestData() {
            sendToPython('request', { action: 'getData' }, function(response) {
            addLog('收到回调: ' + JSON.stringify(response));
            });
            addLog('请求数据...');
        }
        
        // 接收来自 Python 的消息
        window.onPythonMessage = function(data) {
            addLog('收到 Python: ' + JSON.stringify(data));
        };
        
        // 页面就绪通知
        sendToPython('ready', { status: 'loaded' });
    </script>
</body>
</html>
```

## 开发者工具

启用开发者工具进行调试：

```webview2 title="调试示例" width=800 height=600 devtools=true
<!DOCTYPE html>
<html>
<body>
    <h1>开发者工具示例</h1>
    <p>打开 F12 查看控制台</p>
    <script>
        console.log('这是调试信息');
        console.log('window.isWebView2 =', window.isWebView2);
    </script>
</body>
</html>
```

## 主题示例

### 暗色主题

```webview2 title="暗色主题" theme=dark width=500 height=300
<h1>暗色主题</h1>
<p>这是一个暗色主题的示例</p>
<button>按钮</button>
```

### 蓝色主题

```webview2 title="蓝色主题" theme=blue width=500 height=300
<h1>蓝色主题</h1>
<p>这是一个蓝色渐变主题的示例</p>
<button>按钮</button>
```

## 窗口事件

```webview2 title="窗口事件" width=500 height=400
<!DOCTYPE html>
<html>
<body>
    <h1>窗口事件</h1>
    <div id="events"></div>
    <script>
        const events = document.getElementById('events');
        
        // 页面加载完成
        sendToPython('ready', { url: location.href });
        
        // 窗口大小变化
        window.addEventListener('resize', function() {
            events.innerHTML += '<div>窗口大小: ' + window.innerWidth + 'x' + window.innerHeight + '</div>';
        });
        
        // 监听 Python 消息
        window.onPythonMessage = function(data) {
            events.innerHTML += '<div>收到: ' + JSON.stringify(data) + '</div>';
        };
    </script>
</body>
</html>
```

## 表单交互

```webview2 title="用户表单" width=600 height=500
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>用户表单</title>
    <style>
        body { font-family: sans-serif; padding: 20px; }
        .form-group { margin: 10px 0; }
        label { display: inline-block; width: 100px; }
        input, select { padding: 5px; width: 200px; }
        button { padding: 10px 20px; margin-top: 10px; }
        #result { margin-top: 20px; padding: 10px; background: #f0f0f0; }
    </style>
</head>
<body>
    <h1>用户信息</h1>
    <div class="form-group">
        <label>姓名:</label>
        <input type="text" id="name" placeholder="请输入姓名">
    </div>
    <div class="form-group">
        <label>年龄:</label>
        <input type="number" id="age" min="0" max="150">
    </div>
    <div class="form-group">
        <label>城市:</label>
        <select id="city">
            <option value="">请选择</option>
            <option value="beijing">北京</option>
            <option value="shanghai">上海</option>
            <option value="guangzhou">广州</option>
            <option value="shenzhen">深圳</option>
        </select>
    </div>
    <button onclick="submit()">提交</button>
    <div id="result"></div>
    <script>
        function submit() {
            const data = {
                name: document.getElementById('name').value,
                age: parseInt(document.getElementById('age').value) || 0,
                city: document.getElementById('city').value
            };
            sendToPython('submit', data);
            document.getElementById('result').innerHTML = 
                '<p>已发送: ' + JSON.stringify(data) + '</p>';
        }
        function sendToPython(type, data) {
            if (window.chrome && window.chrome.webview) {
                window.chrome.webview.postMessage({ type: type, data: data });
            }
        }
    </script>
</body>
</html>
```

## 指令说明

| 指令 | 说明 | 默认值 |
|------|------|--------|
| `title` | 窗口标题 | "WebView2 Window" |
| `width` | 窗口宽度 | 800 |
| `height` | 窗口高度 | 600 |
| `resizable` | 是否可调整大小 | true |
| `blocking` | 是否阻塞等待 | true |
| `devtools` | 是否启用开发者工具 | false |
| `theme` | 主题 (light/dark/blue/minimal) | light |
| `html` | 外部 HTML 文件 | - |
| `inject` | 注入的 JS 代码 | - |

## JS API (内置)

### 发送消息到 Python

```javascript
// 基本发送
sendToPython('event', { foo: 'bar' });

// 带回调的发送
sendToPython('request', { id: 1 }, function(response) {
    console.log('收到回调:', response);
});
```

### 接收来自 Python 的消息

```javascript
// 方式 1: 回调函数
window.onPythonMessage = function(data) {
    console.log('收到:', data);
};

// 方式 2: 事件监听
window.addEventListener('pythonMessage', function(e) {
    console.log('收到:', e.detail);
});
```

### 便捷 API

```javascript
// 触发事件
triggerEvent('click', { x: 100, y: 200 });

// 等待页面就绪
window.webview.ready().then(function() {
    console.log('页面已就绪');
});

// 发送消息（别名）
window.webview.send('message', data);
window.webview.onMessage(callback);
window.webview.trigger('eventName', data);
```

## 事件类型

| 事件类型 | 说明 |
|---------|------|
| `ready` | 页面加载完成 |
| `message` | 自定义消息 |
| `event` | 用户事件 |
| `error` | JS 错误 |
| `window_close` | 窗口关闭 |
| `window_resize` | 窗口大小变化 |

## 依赖安装

要使用原生 WebView2 SDK（推荐）：

```bash
pip install pythonnet
```

或使用轻量级方案：

```bash
pip install pywebview
```

> **注意**：Windows 10/11 已预装 WebView2 运行时。
