# vools 双版本（Python 3.6 + 3.13）并行测试执行计划

## 1. 目标与范围

### 1.1 核心目标
- **两个 Python 版本（3.6.8 + 3.13.14）所有非监控类测试全部通过**
- 启动两个子代理并行测试，同一份代码，双版本都通过才算通过

### 1.2 测试范围
**纳入测试（必测）：**
- 根目录测试文件（排除监控相关）
- `tests/core/` — core 模块测试
- `tests/functional/` — 函数式编程测试
- `tests/decorators/` — 装饰器测试
- `tests/curried/` — 柯里化测试
- `tests/data/` — 数据结构测试
- `tests/datetime/` — 日期时间测试
- `tests/oop/` — 面向对象测试
- `tests/serialize/` — 序列化测试
- `tests/task/` — 任务调度测试
- `tests/reactive/` — Reactive 核心测试（排除监控相关文件）
- `tests/other/` — 其他测试（排除监控相关文件）

**完全排除（监控类）：**
- `tests/monitoring/` 目录下所有文件（11 个）
- `tests/reactive/test_reactive_clipboard.py`
- `tests/reactive/test_reactive_file_watcher.py`
- `tests/reactive/test_reactive_folder_watcher.py`
- `tests/reactive/test_reactive_keyboard_mouse.py`
- `tests/other/test_clipboard_event_loss.py`
- `tests/other/test_shotcut.py`

**视环境可选（Bridge 类）：**
- `tests/bridge/` 目录下所有文件
- `tests/test_rust_*.py`
- `tests/test_csharp_bridge.py`
- `tests/test_r_bridge.py`

---

## 2. 环境配置

### 2.1 Python 3.13 环境
- **路径**：系统默认 `python`
- **版本**：Python 3.13.14
- **命令前缀**：`python -m pytest`
- **工作目录**：`e:\IDEProjects\AI\vools`

### 2.2 Python 3.6 环境
- **路径**：`e:\py36-venv\Scripts\python.exe`
- **版本**：Python 3.6.8
- **命令前缀**：`e:\py36-venv\Scripts\python.exe -m pytest`
- **工作目录**：`e:\IDEProjects\AI\vools`
- **预装依赖**：attrs, contextvars, typing_extensions, pytest

### 2.3 pytest 通用参数
```
--tb=short -q -p no:cacheprovider
```

---

## 3. 测试分组与执行顺序

### 第一组：核心基础测试
**包含目录/文件：**
- 根目录：test_vools.py, test_functional.py, test_functional_simple.py,
  test_stuff.py, test_box.py, test_import.py, test_main_import.py,
  test_encoding.py, test_itor.py, test_crypto.py, test_do.py,
  test_functions.py, test_new_features.py
- 子目录：tests/core/, tests/functional/, tests/decorators/,
  tests/curried/, tests/data/, tests/datetime/, tests/oop/,
  tests/serialize/, tests/task/
- other/ 筛选后：test_multiline.py, test_multiprocess.py,
  test_project_mode.py, test_sig_cache.py

**pytest 过滤表达式：**
```
tests/ --ignore=tests/monitoring --ignore=tests/bridge --ignore=tests/reactive
--ignore=tests/__rust__
-k "not (clipboard or file_watcher or folder_watcher or keyboard or mouse or shotcut or rust or csharp or r_bridge or mojo or fbc or cangjie)"
```

### 第二组：Reactive 核心测试
**包含文件（tests/reactive/ 下排除监控相关后）：**
- test_core.py
- test_operators_basic.py
- test_operators_advanced.py
- test_operators_time.py
- test_subject.py
- test_connectable.py
- test_pipebuilder.py
- test_rules.py
- test_stats_operators.py
- test_reactive.py
- test_reactive_comprehensive.py
- test_reactive_dispatch_workers.py

**pytest 过滤表达式：**
```
tests/reactive/
-k "not (clipboard or file_watcher or folder_watcher or keyboard or mouse)"
```

### 第三组：Bridge 测试（可选）
- 仅当对应编译器/运行时可用时执行
- 3.6 环境可能存在兼容性问题，可接受跳过

---

## 4. 子代理并行执行方案

### 子代理 A：Python 3.13 测试执行
**任务描述：**
在 Python 3.13 环境下，依次执行第一组（核心基础）和第二组（Reactive 核心）测试，记录完整测试结果。

**执行步骤：**
1. 验证环境：`python --version`，确认能 import vools
2. 运行第一组核心基础测试，输出完整结果摘要
3. 运行第二组 Reactive 核心测试，输出完整结果摘要
4. （可选）运行第三组 Bridge 测试
5. 汇总：通过数、失败数、跳过数、xfail 数、失败用例列表及错误信息

**返回内容：**
- 测试总体统计（passed/failed/skipped/xfailed/xpassed）
- 所有失败用例的完整错误信息
- 分组执行时间

---

### 子代理 B：Python 3.6 测试执行
**任务描述：**
在 Python 3.6 虚拟环境下，依次执行第一组（核心基础）和第二组（Reactive 核心）测试，记录完整测试结果。遇到失败时，先尝试判断是测试用例语法问题还是源码问题。

**执行步骤：**
1. 验证环境：`e:\py36-venv\Scripts\python.exe --version`，确认能 import vools
2. 运行第一组核心基础测试，输出完整结果摘要
3. 运行第二组 Reactive 核心测试，输出完整结果摘要
4. 汇总：通过数、失败数、跳过数、xfail 数、失败用例列表及错误信息

**注意事项：**
- 3.6 不支持的语法（如海象运算符、f-string = 等）需在测试中兼容
- 异步相关测试可能需要兼容处理
- 序列化测试需注意 3.6 与高版本的差异

**返回内容：**
- 测试总体统计（passed/failed/skipped/xfailed/xpassed）
- 所有失败用例的完整错误信息
- 分组执行时间
- 失败原因初步分类（源码问题 / 测试用例问题 / 环境依赖问题）

---

## 5. 主代理协调流程

### 阶段 1：环境预检查
- 验证两个 Python 版本可用
- 验证都能 import vools
- 确认 3.6 环境依赖齐全

### 阶段 2：并行测试第一轮
- 同时启动子代理 A（3.13）和子代理 B（3.6）
- 各自运行第一组 + 第二组测试
- 收集两个版本的测试结果

### 阶段 3：失败分析与修复
- 对比两个版本的失败用例
- **共同失败** → 大概率是代码问题，优先修复源码
- **仅 3.13 失败** → 可能是高版本兼容性问题，检查 deprecation / 移除特性
- **仅 3.6 失败** → 可能是低版本语法/库缺失，添加兼容层或修改测试
- 修复后重新运行对应失败用例

### 阶段 4：回归验证
- 修复后，两个版本重新运行完整测试套件
- 确认没有引入新的失败
- 循环直到两个版本所有测试均通过

### 阶段 5：最终报告
- 输出双版本测试通过确认
- 统计总用例数、通过率
- 记录修复的问题清单

---

## 6. pytest 执行命令参考

### 3.13 环境 - 第一组核心基础测试
```bash
python -m pytest tests/ --ignore=tests/monitoring --ignore=tests/bridge --ignore=tests/reactive --ignore=tests/__rust__ -k "not (clipboard or file_watcher or folder_watcher or keyboard or mouse or shotcut or rust or csharp or r_bridge or mojo or fbc or cangjie or multiprocess)" --tb=short -q
```

### 3.13 环境 - 第二组 Reactive 核心测试
```bash
python -m pytest tests/reactive/ -k "not (clipboard or file_watcher or folder_watcher or keyboard or mouse)" --tb=short -q
```

### 3.6 环境 - 第一组核心基础测试
```bash
e:\py36-venv\Scripts\python.exe -m pytest tests/ --ignore=tests/monitoring --ignore=tests/bridge --ignore=tests/reactive --ignore=tests/__rust__ -k "not (clipboard or file_watcher or folder_watcher or keyboard or mouse or shotcut or rust or csharp or r_bridge or mojo or fbc or cangjie or multiprocess)" --tb=short -q
```

### 3.6 环境 - 第二组 Reactive 核心测试
```bash
e:\py36-venv\Scripts\python.exe -m pytest tests/reactive/ -k "not (clipboard or file_watcher or folder_watcher or keyboard or mouse)" --tb=short -q
```

---

## 7. 已知兼容点清单（需验证）

### 已修复的兼容问题（需验证仍有效）
- [x] `dataclass_compat` — attrs backport
- [x] `asyncio_compat` — get_running_loop / run
- [x] `inspect_compat` — 统一 inspect 接口
- [x] `datetime_compat` — fromisoformat 兼容
- [x] `cached_property` 兼容
- [x] `itertools.pairwise` 兼容
- [x] 模块级 `__getattr__` 兼容
- [x] `contextvars` backport
- [x] `Protocol` / `Literal` 兼容
- [x] BridgeSigCache id 复用 bug
- [x] SQLite `RETURNING` 语法兼容
- [x] `object.__getstate__` 检测兼容

### 需重点关注的测试区域
1. **序列化测试** — pickle 协议版本差异
2. **异步测试** — asyncio API 差异
3. **装饰器测试** — signature 处理差异
4. **Reactive 测试** — 调度器、异步操作差异
5. **Task 测试** — 并发原语差异

---

## 8. 成功标准

**两个 Python 版本同时满足以下条件：**
- ✅ 第一组核心基础测试：全部通过（允许 xfail）
- ✅ 第二组 Reactive 核心测试：全部通过（允许 xfail）
- ❌ 监控类测试：全部排除，不计入结果
- ⚠️ Bridge 测试：可选，有环境则需通过

**最终交付：**
- 双版本测试通过确认
- 测试统计数据（总用例数、通过数、跳过数、xfail 数）
- 修复问题清单（如有）
