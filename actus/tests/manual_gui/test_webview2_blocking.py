# -*- coding: utf-8 -*-
"""
真正测试 WebView2 渲染 - 阻塞模式显示窗口
"""

import sys
import importlib.util

# 导入 webview2
spec = importlib.util.spec_from_file_location(
    'webview2',
    r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\webview2.py'
)

import importlib.util as iu

spec_dirs = iu.spec_from_file_location('directives', r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\directives.py')
dirs_mod = iu.module_from_spec(spec_dirs)
spec_dirs.loader.exec_module(dirs_mod)

spec_cfg = iu.spec_from_file_location('config', r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\config.py')
cfg_mod = iu.module_from_spec(spec_cfg)
spec_cfg.loader.exec_module(cfg_mod)

webview2 = iu.module_from_spec(spec)
spec.loader.exec_module(webview2)

render_webview2 = webview2.render_webview2


def test_calculator_blocking():
    """测试计算器 WebView2 - 阻塞模式（窗口会保持显示）"""
    html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Calculator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .calculator {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 24px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 360px;
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
            text-align: center;
            font-size: 28px;
        }
        .display {
            background: #1a1a2e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: right;
        }
        .result {
            color: white;
            font-size: 36px;
            font-weight: 300;
        }
        .buttons {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }
        button {
            border: none;
            border-radius: 12px;
            padding: 18px;
            font-size: 20px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: scale(1.05);
        }
        .number {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            color: #333;
        }
        .operator {
            background: linear-gradient(135deg, #ff9a44 0%, #ff6b35 100%);
            color: white;
        }
        .equals {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            grid-column: span 2;
        }
    </style>
</head>
<body>
    <div class="calculator">
        <h1>Calculator</h1>
        <div class="display">
            <div class="result" id="result">0</div>
        </div>
        <div class="buttons">
            <button class="operator" onclick="clearAll()">AC</button>
            <button class="operator" onclick="backspace()">⌫</button>
            <button class="operator" onclick="appendOperator('/')">÷</button>
            <button class="operator" onclick="appendOperator('*')">×</button>
            
            <button class="number" onclick="appendNumber('7')">7</button>
            <button class="number" onclick="appendNumber('8')">8</button>
            <button class="number" onclick="appendNumber('9')">9</button>
            <button class="operator" onclick="appendOperator('-')">-</button>
            
            <button class="number" onclick="appendNumber('4')">4</button>
            <button class="number" onclick="appendNumber('5')">5</button>
            <button class="number" onclick="appendNumber('6')">6</button>
            <button class="operator" onclick="appendOperator('+')">+</button>
            
            <button class="number" onclick="appendNumber('1')">1</button>
            <button class="number" onclick="appendNumber('2')">2</button>
            <button class="number" onclick="appendNumber('3')">3</button>
            <button class="equals" onclick="calculate()" style="grid-row: span 2;">=</button>
            
            <button class="number" onclick="appendNumber('0')" style="grid-column: span 2;">0</button>
            <button class="number" onclick="appendDecimal()">.</button>
        </div>
    </div>
    <script>
        let currentInput = '0';
        let previousInput = '';
        let operation = null;
        
        const resultEl = document.getElementById('result');
        
        function updateDisplay() {
            resultEl.textContent = currentInput;
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
            if (operation !== null) calculate();
            previousInput = currentInput;
            operation = op;
            currentInput = '0';
            updateDisplay();
        }
        
        function calculate() {
            if (operation === null) return;
            const prev = parseFloat(previousInput);
            const current = parseFloat(currentInput);
            let result;
            switch (operation) {
                case '+': result = prev + current; break;
                case '-': result = prev - current; break;
                case '*': result = prev * current; break;
                case '/': result = prev / current; break;
                default: return;
            }
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
        
        function backspace() {
            if (currentInput.length > 1) {
                currentInput = currentInput.slice(0, -1);
            } else {
                currentInput = '0';
            }
            updateDisplay();
        }
        
        // Keyboard support
        document.addEventListener('keydown', (e) => {
            if (e.key >= '0' && e.key <= '9') appendNumber(e.key);
            else if (e.key === '.') appendDecimal();
            else if (e.key === '+' || e.key === '-' || e.key === '*' || e.key === '/') appendOperator(e.key);
            else if (e.key === 'Enter' || e.key === '=') calculate();
            else if (e.key === 'Escape') clearAll();
            else if (e.key === 'Backspace') backspace();
        });
        
        updateDisplay();
    </script>
</body>
</html>'''
    
    print("="*60)
    print("测试 Calculator WebView2 - 阻塞模式")
    print("="*60)
    print("\n注意: 这将弹出一个窗口，请查看窗口内容")
    print("关闭窗口后测试将继续...\n")
    
    result = render_webview2(
        html,
        title="Calculator - Beautiful UI",
        width=400,
        height=600,
        blocking=True,  # 阻塞模式，窗口会保持显示
        devtools=False
    )
    
    print(f"\n窗口已关闭")
    print(f"结果: {result.status}")
    return result.status == "ok"


def main():
    success = test_calculator_blocking()
    
    print("\n" + "="*60)
    if success:
        print("✓ WebView2 窗口测试成功！")
    else:
        print("✗ WebView2 窗口测试失败")
    print("="*60)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
