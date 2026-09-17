---
id: todo-list
name: Todo List
version: 1.0.0
trust: sandbox
entry: main
description: A beautiful todo list application with modern UI
author: vools
platform: desktop
tags: [todo, gui, webview2, productivity]
max_instances: 1
deprecated: false
---

# Todo List

A beautiful todo list application with modern UI built with HTML/CSS/JavaScript and WebView2.

## Usage

```python
from vools.actus.actions import load_action

action = load_action("todo-list")
result = action.execute()
```

## Implementation

```webview2 title="Todo List" width=500 height=700 resizable=false devtools=false
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Todo List</title>
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
        
        .app {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
            width: 100%;
            max-width: 460px;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            color: white;
        }
        
        .header h1 {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 5px;
        }
        
        .header .subtitle {
            font-size: 14px;
            opacity: 0.9;
        }
        
        .input-area {
            padding: 20px 30px;
            border-bottom: 1px solid #eee;
            display: flex;
            gap: 10px;
        }
        
        .input-area input {
            flex: 1;
            padding: 14px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .input-area input:focus {
            border-color: #667eea;
        }
        
        .input-area button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px 24px;
            border-radius: 12px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .input-area button:hover {
            transform: scale(1.05);
        }
        
        .filters {
            padding: 15px 30px;
            border-bottom: 1px solid #eee;
            display: flex;
            gap: 10px;
        }
        
        .filter-btn {
            padding: 8px 16px;
            border: none;
            border-radius: 20px;
            background: #f0f0f0;
            color: #666;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .filter-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .todo-list {
            flex: 1;
            overflow-y: auto;
            padding: 20px 30px;
            max-height: 500px;
        }
        
        .todo-item {
            display: flex;
            align-items: center;
            padding: 16px;
            background: #f8f9fa;
            border-radius: 12px;
            margin-bottom: 12px;
            transition: all 0.2s;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .todo-item:hover {
            background: #e9ecef;
        }
        
        .todo-item.completed {
            opacity: 0.6;
        }
        
        .todo-item.completed .todo-text {
            text-decoration: line-through;
        }
        
        .checkbox {
            width: 24px;
            height: 24px;
            border: 2px solid #667eea;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            justify-content: center;
            align-items: center;
            margin-right: 16px;
            transition: all 0.2s;
        }
        
        .checkbox.checked {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        
        .checkbox.checked::after {
            content: '✓';
            color: white;
            font-size: 16px;
        }
        
        .todo-text {
            flex: 1;
            font-size: 16px;
            color: #333;
        }
        
        .todo-time {
            font-size: 12px;
            color: #999;
            margin-right: 16px;
        }
        
        .delete-btn {
            background: none;
            border: none;
            color: #ff6b6b;
            font-size: 20px;
            cursor: pointer;
            padding: 4px;
            transition: transform 0.2s;
        }
        
        .delete-btn:hover {
            transform: scale(1.2);
        }
        
        .stats {
            padding: 20px 30px;
            border-top: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #f8f9fa;
        }
        
        .stats-item {
            text-align: center;
        }
        
        .stats-number {
            font-size: 24px;
            font-weight: 600;
            color: #667eea;
        }
        
        .stats-label {
            font-size: 12px;
            color: #999;
            margin-top: 4px;
        }
        
        .clear-completed {
            background: none;
            border: none;
            color: #ff6b6b;
            cursor: pointer;
            font-size: 14px;
            padding: 8px 16px;
            border-radius: 8px;
            transition: background 0.2s;
        }
        
        .clear-completed:hover {
            background: #ffe0e0;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #999;
        }
        
        .empty-state-icon {
            font-size: 64px;
            margin-bottom: 20px;
            opacity: 0.3;
        }
    </style>
</head>
<body>
    <div class="app">
        <div class="header">
            <h1>📝 My Tasks</h1>
            <div class="subtitle" id="todayDate"></div>
        </div>
        
        <div class="input-area">
            <input type="text" id="todoInput" placeholder="Add a new task..." autofocus>
            <button onclick="addTodo()">Add</button>
        </div>
        
        <div class="filters">
            <button class="filter-btn active" onclick="setFilter('all')">All</button>
            <button class="filter-btn" onclick="setFilter('active')">Active</button>
            <button class="filter-btn" onclick="setFilter('completed')">Completed</button>
        </div>
        
        <div class="todo-list" id="todoList"></div>
        
        <div class="stats">
            <div class="stats-item">
                <div class="stats-number" id="totalCount">0</div>
                <div class="stats-label">Total</div>
            </div>
            <div class="stats-item">
                <div class="stats-number" id="activeCount">0</div>
                <div class="stats-label">Active</div>
            </div>
            <div class="stats-item">
                <div class="stats-number" id="completedCount">0</div>
                <div class="stats-label">Completed</div>
            </div>
            <button class="clear-completed" onclick="clearCompleted()">Clear Completed</button>
        </div>
    </div>

    <script>
        let todos = [];
        let currentFilter = 'all';
        
        // Initialize
        document.getElementById('todayDate').textContent = new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
        
        // Load from localStorage
        function loadTodos() {
            const saved = localStorage.getItem('vools_todos');
            if (saved) {
                todos = JSON.parse(saved);
            }
            render();
        }
        
        // Save to localStorage
        function saveTodos() {
            localStorage.setItem('vools_todos', JSON.stringify(todos));
        }
        
        // Add new todo
        function addTodo() {
            const input = document.getElementById('todoInput');
            const text = input.value.trim();
            
            if (text) {
                todos.push({
                    id: Date.now(),
                    text: text,
                    completed: false,
                    createdAt: new Date().toISOString()
                });
                input.value = '';
                saveTodos();
                render();
            }
        }
        
        // Toggle completion
        function toggleTodo(id) {
            const todo = todos.find(t => t.id === id);
            if (todo) {
                todo.completed = !todo.completed;
                saveTodos();
                render();
            }
        }
        
        // Delete todo
        function deleteTodo(id) {
            todos = todos.filter(t => t.id !== id);
            saveTodos();
            render();
        }
        
        // Set filter
        function setFilter(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            render();
        }
        
        // Clear completed
        function clearCompleted() {
            todos = todos.filter(t => !t.completed);
            saveTodos();
            render();
        }
        
        // Render todos
        function render() {
            const list = document.getElementById('todoList');
            const filtered = todos.filter(t => {
                if (currentFilter === 'active') return !t.completed;
                if (currentFilter === 'completed') return t.completed;
                return true;
            });
            
            if (filtered.length === 0) {
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">✨</div>
                        <p>No tasks ${currentFilter === 'completed' ? 'completed yet' : 'yet'}</p>
                    </div>
                `;
            } else {
                list.innerHTML = filtered.map(todo => `
                    <div class="todo-item ${todo.completed ? 'completed' : ''}">
                        <div class="checkbox ${todo.completed ? 'checked' : ''}" onclick="toggleTodo(${todo.id})"></div>
                        <div class="todo-text">${todo.text}</div>
                        <div class="todo-time">${formatTime(todo.createdAt)}</div>
                        <button class="delete-btn" onclick="deleteTodo(${todo.id})">×</button>
                    </div>
                `).join('');
            }
            
            // Update stats
            document.getElementById('totalCount').textContent = todos.length;
            document.getElementById('activeCount').textContent = todos.filter(t => !t.completed).length;
            document.getElementById('completedCount').textContent = todos.filter(t => t.completed).length;
        }
        
        // Format time
        function formatTime(isoString) {
            const date = new Date(isoString);
            const now = new Date();
            const diff = now - date;
            
            if (diff < 60000) return 'Just now';
            if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
            if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
            return date.toLocaleDateString();
        }
        
        // Keyboard support
        document.getElementById('todoInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                addTodo();
            }
        });
        
        // Initialize
        loadTodos();
    </script>
</body>
</html>
```

## Notes

- Data persists in localStorage
- Supports keyboard input (Enter to add)
- Filter by All/Active/Completed
- Shows task statistics
- Modern gradient design with smooth animations

## Permissions

```yaml
permissions:
  - gui:show
  - storage:read
  - storage:write
```
