# asyncio.run() 兼容性修复计划

## 目标
修复 Python 3.6 环境下测试文件的 asyncio.run() 兼容性问题，将 `asyncio.run()` 替换为 `vools.core.asyncio_compat` 中的 `run` 函数。

## 修改文件列表

### 1. tests/reactive/test_reactive.py

**添加 import：**
- 位置：文件顶部 import 区域（第 13 行 `from vools.reactive import ...` 之后）
- 内容：`from vools.core.asyncio_compat import run as asyncio_run`

**替换 asyncio.run()：**
- 第 293 行：`asyncio.run(test())` → `asyncio_run(test())`
- 第 310 行：`asyncio.run(test_debounce())` → `asyncio_run(test_debounce())`
- 第 320 行：`asyncio.run(test_throttle())` → `asyncio_run(test_throttle())`

**共 3 处替换**

---

### 2. tests/reactive/test_reactive_comprehensive.py

**添加 import：**
- 位置：文件顶部 import 区域（第 20 行 `from vools.reactive.core.connectable import ...` 之后）
- 内容：`from vools.core.asyncio_compat import run as asyncio_run`

**替换 asyncio.run()：**
- 第 505 行：`asyncio.run(run())` → `asyncio_run(run())` （test_interval_basic）
- 第 515 行：`asyncio.run(run())` → `asyncio_run(run())` （test_timer_single）
- 第 527 行：`asyncio.run(run())` → `asyncio_run(run())` （test_timer_periodic）
- 第 538 行：`asyncio.run(run())` → `asyncio_run(run())` （test_debounce_basic）
- 第 549 行：`asyncio.run(run())` → `asyncio_run(run())` （test_throttle_first_basic）
- 第 627 行：`asyncio.run(run())` → `asyncio_run(run())` （test_asyncio_scheduler）

**共 6 处替换**

---

### 3. tests/functional/test_only_code_mode.py

**添加 import：**
- 位置：文件顶部 import 区域（第 14 行 `from vools.bridge.freebasic import FbcBridge` 之后）
- 内容：`from vools.core.asyncio_compat import run as asyncio_run`

**替换 asyncio.run()：**
- 第 307 行：`code = asyncio.run(run_test())` → `code = asyncio_run(run_test())` （test_async_only_code）
- 第 336 行：`result = asyncio.run(run_test())` → `result = asyncio_run(run_test())` （test_async_only_code_with_file）

**共 2 处替换**

---

## 验证步骤
修改完成后，对每个文件执行语法验证：
```bash
python -c "import ast; ast.parse(open('FILE').read())"
```

## 总计
- 修改文件：3 个
- 添加 import：3 处
- 替换 asyncio.run()：11 处
