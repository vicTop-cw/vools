---
id: text-editor
name: Text Editor
version: 1.0.0
trust: sandbox
entry: main
description: A beautiful text editor with modern UI
author: vools
platform: desktop
tags: [editor, gui, webview2, productivity]
max_instances: 1
deprecated: false
---

# Text Editor

A beautiful text editor with modern UI built with HTML/CSS/JavaScript and WebView2.

## Usage

```python
from vools.actus.actions import load_action

action = load_action("text-editor")
result = action.execute()
```

## Implementation

```webview2 title="Text Editor" width=800 height=600 resizable=true devtools=false
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Text Editor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .editor {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
            width: 100%;
            max-width: 900px;
            height: 90vh;
            max-height: 700px;
            display: flex;
            flex-direction: column;
        }
        
        .toolbar {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 15px 20px;
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .toolbar-title {
            color: white;
            font-size: 18px;
            font-weight: 600;
            margin-right: auto;
        }
        
        .toolbar-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .toolbar-btn:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.05);
        }
        
        .toolbar-btn:active {
            transform: scale(0.95);
        }
        
        .format-bar {
            background: #f8f9fa;
            padding: 10px 20px;
            display: flex;
            gap: 8px;
            border-bottom: 1px solid #e0e0e0;
            flex-wrap: wrap;
        }
        
        .format-btn {
            background: white;
            border: 1px solid #e0e0e0;
            padding: 8px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .format-btn:hover {
            background: #f0f0f0;
        }
        
        .format-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
        }
        
        .editor-area {
            flex: 1;
            display: flex;
            overflow: hidden;
        }
        
        .sidebar {
            width: 200px;
            background: #f8f9fa;
            border-right: 1px solid #e0e0e0;
            padding: 20px;
            overflow-y: auto;
        }
        
        .file-list-title {
            font-size: 12px;
            color: #999;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .file-item {
            padding: 12px;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 8px;
            transition: all 0.2s;
            font-size: 14px;
        }
        
        .file-item:hover {
            background: #e9ecef;
        }
        
        .file-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .content-area {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        
        .file-tabs {
            background: #f8f9fa;
            padding: 0 20px;
            display: flex;
            gap: 5px;
            border-bottom: 1px solid #e0e0e0;
            overflow-x: auto;
        }
        
        .tab {
            padding: 12px 20px;
            background: white;
            border: 1px solid #e0e0e0;
            border-bottom: none;
            border-radius: 8px 8px 0 0;
            cursor: pointer;
            font-size: 14px;
            white-space: nowrap;
            transition: all 0.2s;
        }
        
        .tab.active {
            background: white;
            border-bottom: 2px solid #667eea;
        }
        
        .tab-close {
            margin-left: 8px;
            opacity: 0.5;
            cursor: pointer;
        }
        
        .tab-close:hover {
            opacity: 1;
        }
        
        .textarea-container {
            flex: 1;
            position: relative;
        }
        
        textarea {
            width: 100%;
            height: 100%;
            padding: 30px;
            border: none;
            outline: none;
            resize: none;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 14px;
            line-height: 1.8;
            color: #333;
            background: white;
        }
        
        .status-bar {
            background: #f8f9fa;
            padding: 10px 20px;
            border-top: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: #999;
        }
        
        .status-item {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .modal.show {
            display: flex;
        }
        
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 16px;
            max-width: 400px;
            width: 90%;
        }
        
        .modal-title {
            font-size: 20px;
            margin-bottom: 20px;
            color: #333;
        }
        
        .modal-input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            outline: none;
            margin-bottom: 20px;
        }
        
        .modal-input:focus {
            border-color: #667eea;
        }
        
        .modal-buttons {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
        }
        
        .modal-btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
        }
        
        .modal-btn.primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .modal-btn.secondary {
            background: #e0e0e0;
            color: #333;
        }
    </style>
</head>
<body>
    <div class="editor">
        <div class="toolbar">
            <div class="toolbar-title">📝 Text Editor</div>
            <button class="toolbar-btn" onclick="newFile()">+ New</button>
            <button class="toolbar-btn" onclick="openFile()">📂 Open</button>
            <button class="toolbar-btn" onclick="saveFile()">💾 Save</button>
            <button class="toolbar-btn" onclick="saveAsFile()">💾 Save As</button>
        </div>
        
        <div class="format-bar">
            <button class="format-btn" onclick="formatText('bold')"><b>B</b></button>
            <button class="format-btn" onclick="formatText('italic')"><i>I</i></button>
            <button class="format-btn" onclick="formatText('underline')"><u>U</u></button>
            <button class="format-btn" onclick="formatText('heading')">H1</button>
            <button class="format-btn" onclick="formatText('list')">• List</button>
            <button class="format-btn" onclick="formatText('numbered')">1. List</button>
            <button class="format-btn" onclick="formatText('code')">{'<>'}</button>
            <button class="format-btn" onclick="formatText('quote')">"</button>
        </div>
        
        <div class="editor-area">
            <div class="sidebar">
                <div class="file-list-title">Files</div>
                <div id="fileList"></div>
            </div>
            <div class="content-area">
                <div class="file-tabs" id="fileTabs"></div>
                <div class="textarea-container">
                    <textarea id="editor" placeholder="Start typing..."></textarea>
                </div>
            </div>
        </div>
        
        <div class="status-bar">
            <div class="status-item">
                <span id="charCount">0 characters</span>
                <span id="wordCount">0 words</span>
            </div>
            <div class="status-item">
                <span id="fileType">Plain Text</span>
                <span id="saveStatus">Saved</span>
            </div>
        </div>
    </div>
    
    <div class="modal" id="newFileModal">
        <div class="modal-content">
            <div class="modal-title">Create New File</div>
            <input type="text" class="modal-input" id="newFileName" placeholder="File name...">
            <div class="modal-buttons">
                <button class="modal-btn secondary" onclick="closeModal('newFileModal')">Cancel</button>
                <button class="modal-btn primary" onclick="createFile()">Create</button>
            </div>
        </div>
    </div>
    
    <script>
        let files = [
            { name: 'welcome.txt', content: 'Welcome to Text Editor!\n\nStart writing something amazing...', active: true }
        ];
        let currentFile = 0;
        
        const editor = document.getElementById('editor');
        const fileList = document.getElementById('fileList');
        const fileTabs = document.getElementById('fileTabs');
        
        function renderFileList() {
            fileList.innerHTML = files.map((file, index) => `
                <div class="file-item ${index === currentFile ? 'active' : ''}" onclick="switchFile(${index})">
                    ${file.name}
                </div>
            `).join('');
            
            fileTabs.innerHTML = files.map((file, index) => `
                <div class="tab ${index === currentFile ? 'active' : ''}" onclick="switchFile(${index})">
                    ${file.name}
                    <span class="tab-close" onclick="closeFile(${index})">×</span>
                </div>
            `).join('');
        }
        
        function switchFile(index) {
            currentFile = index;
            editor.value = files[index].content;
            renderFileList();
            updateStats();
        }
        
        function closeFile(index) {
            if (files.length <= 1) {
                alert('Cannot close the last file');
                return;
            }
            files.splice(index, 1);
            if (currentFile >= files.length) {
                currentFile = files.length - 1;
            }
            switchFile(currentFile);
        }
        
        function newFile() {
            openModal('newFileModal');
            document.getElementById('newFileName').focus();
        }
        
        function createFile() {
            const name = document.getElementById('newFileName').value.trim();
            if (name) {
                files.push({ name: name, content: '', active: false });
                currentFile = files.length - 1;
                closeModal('newFileModal');
                renderFileList();
                switchFile(currentFile);
            }
        }
        
        function openFile() {
            const input = document.createElement('input');
            input.type = 'file';
            input.onchange = (e) => {
                const file = e.target.files[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        files.push({ name: file.name, content: e.target.result, active: false });
                        currentFile = files.length - 1;
                        renderFileList();
                        switchFile(currentFile);
                    };
                    reader.readAsText(file);
                }
            };
            input.click();
        }
        
        function saveFile() {
            const content = editor.value;
            files[currentFile].content = content;
            showSaveStatus();
        }
        
        function saveAsFile() {
            const content = editor.value;
            const blob = new Blob([content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = files[currentFile].name;
            a.click();
            URL.revokeObjectURL(url);
            showSaveStatus();
        }
        
        function showSaveStatus() {
            const status = document.getElementById('saveStatus');
            status.textContent = 'Saving...';
            setTimeout(() => {
                status.textContent = 'Saved';
            }, 500);
        }
        
        function formatText(format) {
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            const selected = editor.value.substring(start, end);
            let formatted = selected;
            
            switch (format) {
                case 'bold':
                    formatted = `**${selected}**`;
                    break;
                case 'italic':
                    formatted = `*${selected}*`;
                    break;
                case 'underline':
                    formatted = `<u>${selected}</u>`;
                    break;
                case 'heading':
                    formatted = `# ${selected}\n`;
                    break;
                case 'list':
                    formatted = selected.split('\n').map(line => `- ${line}`).join('\n');
                    break;
                case 'numbered':
                    formatted = selected.split('\n').map((line, i) => `${i + 1}. ${line}`).join('\n');
                    break;
                case 'code':
                    formatted = `\`\`\`\n${selected}\n\`\`\``;
                    break;
                case 'quote':
                    formatted = `> ${selected}`;
                    break;
            }
            
            editor.value = editor.value.substring(0, start) + formatted + editor.value.substring(end);
            editor.focus();
            updateStats();
        }
        
        function updateStats() {
            const content = editor.value;
            const chars = content.length;
            const words = content.trim() ? content.trim().split(/\s+/).length : 0;
            
            document.getElementById('charCount').textContent = `${chars} characters`;
            document.getElementById('wordCount').textContent = `${words} words`;
        }
        
        function openModal(id) {
            document.getElementById(id).classList.add('show');
        }
        
        function closeModal(id) {
            document.getElementById(id).classList.remove('show');
        }
        
        // Event listeners
        editor.addEventListener('input', () => {
            files[currentFile].content = editor.value;
            updateStats();
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                if (e.key === 'n') {
                    e.preventDefault();
                    newFile();
                } else if (e.key === 's') {
                    e.preventDefault();
                    saveFile();
                } else if (e.key === 'o') {
                    e.preventDefault();
                    openFile();
                }
            }
        });
        
        // Initialize
        renderFileList();
        switchFile(0);
    </script>
</body>
</html>
```

## Notes

- Supports multiple files/tabs
- File open and save functionality
- Text formatting (bold, italic, underline, headings, lists, code, quotes)
- Character and word count
- Keyboard shortcuts (Ctrl+N, Ctrl+S, Ctrl+O)
- Modern gradient design with smooth animations

## Permissions

```yaml
permissions:
  - gui:show
  - filesystem:read
  - filesystem:write
```
