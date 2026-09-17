---
id: calculator
name: Calculator
version: 1.0.0
trust: sandbox
entry: main
description: A beautiful calculator with modern UI
author: vools
platform: desktop
tags: [calculator, gui, webview2, utility]
max_instances: 1
deprecated: false
---

# Calculator

A beautiful calculator with modern UI built with HTML/CSS/JavaScript and WebView2.

## Usage

```python
from vools.actus.actions import load_action

action = load_action("calculator")
result = action.execute()
```

## Implementation

```webview2 title="Calculator" width=400 height=600 resizable=false devtools=false
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calculator</title>
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
        
        .calculator {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
            width: 100%;
            max-width: 360px;
        }
        
        .display {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 30px;
            text-align: right;
        }
        
        .formula {
            color: rgba(255, 255, 255, 0.6);
            font-size: 14px;
            min-height: 20px;
            margin-bottom: 10px;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .result {
            color: #fff;
            font-size: 48px;
            font-weight: 300;
            min-height: 60px;
            overflow: hidden;
            text-overflow: ellipsis;
            word-break: break-all;
        }
        
        .buttons {
            padding: 20px;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }
        
        button {
            border: none;
            border-radius: 16px;
            font-size: 24px;
            font-weight: 500;
            height: 70px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        button:hover {
            transform: scale(1.05);
        }
        
        button:active {
            transform: scale(0.95);
        }
        
        .operator {
            background: linear-gradient(135deg, #ff9a44 0%, #ff6b35 100%);
            color: white;
        }
        
        .number {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            color: #333;
        }
        
        .function {
            background: linear-gradient(135deg, #e8e8e8 0%, #d0d0d0 100%);
            color: #333;
        }
        
        .equals {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            grid-column: span 2;
        }
        
        .zero {
            grid-column: span 2;
        }
        
        .history {
            max-height: 200px;
            overflow-y: auto;
            padding: 10px 20px;
            border-top: 1px solid #eee;
        }
        
        .history-item {
            padding: 8px;
            margin-bottom: 5px;
            background: #f8f9fa;
            border-radius: 8px;
            font-size: 14px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="calculator">
        <div class="display">
            <div class="formula" id="formula"></div>
            <div class="result" id="result">0</div>
        </div>
        <div class="buttons">
            <button class="function" onclick="clearAll()">AC</button>
            <button class="function" onclick="clearEntry()">CE</button>
            <button class="function" onclick="backspace()">⌫</button>
            <button class="operator" onclick="appendOperator('/')">÷</button>
            
            <button class="number" onclick="appendNumber('7')">7</button>
            <button class="number" onclick="appendNumber('8')">8</button>
            <button class="number" onclick="appendNumber('9')">9</button>
            <button class="operator" onclick="appendOperator('*')">×</button>
            
            <button class="number" onclick="appendNumber('4')">4</button>
            <button class="number" onclick="appendNumber('5')">5</button>
            <button class="number" onclick="appendNumber('6')">6</button>
            <button class="operator" onclick="appendOperator('-')">-</button>
            
            <button class="number" onclick="appendNumber('1')">1</button>
            <button class="number" onclick="appendNumber('2')">2</button>
            <button class="number" onclick="appendNumber('3')">3</button>
            <button class="operator" onclick="appendOperator('+')">+</button>
            
            <button class="number zero" onclick="appendNumber('0')">0</button>
            <button class="number" onclick="appendDecimal()">.</button>
            <button class="equals" onclick="calculate()">=</button>
        </div>
        <div class="history" id="history"></div>
    </div>

    <script>
        let currentInput = '0';
        let previousInput = '';
        let operation = null;
        let history = [];
        
        const resultEl = document.getElementById('result');
        const formulaEl = document.getElementById('formula');
        const historyEl = document.getElementById('history');
        
        function updateDisplay() {
            resultEl.textContent = currentInput;
            formulaEl.textContent = previousInput + (operation ? ' ' + operation : '');
        }
        
        function appendNumber(num) {
            if (currentInput === '0' && num !== '.') {
                currentInput = num;
            } else {
                currentInput += num;
            }
            updateDisplay();
        }
        
        function appendDecimal() {
            if (!currentInput.includes('.')) {
                currentInput += '.';
            }
            updateDisplay();
        }
        
        function appendOperator(op) {
            if (operation !== null) {
                calculate();
            }
            previousInput = currentInput;
            operation = op;
            currentInput = '0';
            updateDisplay();
        }
        
        function calculate() {
            if (operation === null || previousInput === '') return;
            
            const prev = parseFloat(previousInput);
            const current = parseFloat(currentInput);
            let result;
            
            switch (operation) {
                case '+':
                    result = prev + current;
                    break;
                case '-':
                    result = prev - current;
                    break;
                case '*':
                    result = prev * current;
                    break;
                case '/':
                    result = prev / current;
                    break;
                default:
                    return;
            }
            
            const formula = `${previousInput} ${operation} ${currentInput} = ${result}`;
            history.unshift(formula);
            if (history.length > 5) history.pop();
            
            updateHistory();
            
            currentInput = result.toString();
            operation = null;
            previousInput = '';
            updateDisplay();
        }
        
        function clearAll() {
            currentInput = '0';
            previousInput = '';
            operation = null;
            updateDisplay();
        }
        
        function clearEntry() {
            currentInput = '0';
            updateDisplay();
        }
        
        function backspace() {
            if (currentInput.length > 1) {
                currentInput = currentInput.slice(0, -1);
            } else {
                currentInput = '0';
            }
            updateDisplay();
        }
        
        function updateHistory() {
            historyEl.innerHTML = history.map(item => 
                `<div class="history-item">${item}</div>`
            ).join('');
        }
        
        // Keyboard support
        document.addEventListener('keydown', (e) => {
            if (e.key >= '0' && e.key <= '9') {
                appendNumber(e.key);
            } else if (e.key === '.') {
                appendDecimal();
            } else if (e.key === '+' || e.key === '-' || e.key === '*' || e.key === '/') {
                appendOperator(e.key);
            } else if (e.key === 'Enter' || e.key === '=') {
                calculate();
            } else if (e.key === 'Escape') {
                clearAll();
            } else if (e.key === 'Backspace') {
                backspace();
            }
        });
        
        updateDisplay();
    </script>
</body>
</html>
```

## Notes

- Supports keyboard input (0-9, +, -, *, /, Enter, Escape, Backspace)
- Shows calculation history
- Modern gradient design with smooth animations
- Responsive layout

## Permissions

```yaml
permissions:
  - gui:show
```
