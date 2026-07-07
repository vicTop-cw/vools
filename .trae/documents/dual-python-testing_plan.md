# vools 双版本（3.6 + 3.13）并行测试计划

## 1. 仓库调研结论

### 1.1 Python 环境
- **Python 3.13.14**：系统默认 Python（当前 PATH 中的 python）
- **Python 3.6.8**：位于 `E:\Python36\python.exe`，虚拟环境 `e:\py36-venv\Scripts\python.exe`
- 项目路径：`e:\IDEProjects\AI\vools`

### 1.2 测试目录结构
```
tests/
├── bridge/            # 多语言桥接测试（需外部编译器）
├── core/              # core 模块测试
├── curried/           # 柯里化测试
├── data/              # 数据结构测试
├── datetime/          # 日期时间测试
├── decorators/        # 装饰器测试
├── functional/        # 函数式编程测试
├── monitoring/        # 监控类测试（需排除）
├── oop/               # 面向对象测试
├── other/             # 其他测试（部分监控相关需排除）
├── reactive/          # 响应式测试（部分监控相关需排除）
├── serialize/         # 序列化测试
├── task/              # 任务调度测试
└── 根目录测试文件      # 各类独立测试
```

### 1.3 需排除的监控类测试
**完全排除目录：**
- `tests/monitoring/` — 全部 11 个测试文件

**排除的单文件：**
- `tests/reactive/test_reactive_clipboard.py`
- `tests/reactive/test_reactive_file_watcher.py`
- `tests/reactive/test_reactive_folder_watcher.py`
- `tests/reactive/test_reactive_keyboard_mouse.py`
- `tests/other/test_clipboard_event_loss.py`
- `tests/other/test_shotcut.py`

**可选排除（需外部编译器/运行时，视环境而定）：**
- `tests/bridge/` 下所有文件
- `tests/test_rust_*.py`
- `tests/test_csharp_bridge.py`
- `tests/test_r_bridge.py`

### 1.4 已确认的兼容性问题
- 已修复：`dataclass` 兼容（core/dataclass_compat.py）
- 已修复：`asyncio.get_running_loop` / `asyncio.run` 兼容（core/asyncio_compat.py）
- 已修复：`cached_property` 兼容（utils/stuff.py）
- 已修复：`itertools.pairwise` 兼容（functional/pipe_ops.py）
- 已修复：模块级 `__getattr__` 3.6 不支持（__init__.py）
- 已修复：`contextvars` backport（需 pip install contextvars）
- 已修复：`OrderedDict` 泛型下标语法
- 已修复：`Literal` / `Protocol` 3.6 不支持
- 已修复：BridgeSigCache id 复用 bug

---

## 2. 测试分组与范围

### 第一组：核心基础测试（必测）
**文件列表：**
- 根目录：test_vools.py, test_functional.py, test_functional_simple.py, test_stuff.py, test_box.py, test_import.py, test_main_import.py, test_encoding.py, test_itor.py, test_crypto.py, test_do.py, test_functions.py, test_new_features.py
- 子目录：core/, functional/, decorators/, curried/, data/, datetime/, oop/, serialize/, task/
- other/ 排除监控相关后：test_multiline.py, test_multiprocess.py, test_project_mode.py, test_sig_cache.py

**预估用例数：** ~400+

### 第二组：Reactive 核心测试（必测）
**文件列表：**
- test_core.py, test_operators_basic.py, test_operators_advanced.py, test_subject.py
- test_connectable.py, test_pipebuilder.py, test_rules.py, test_stats_operators.py
- test_operators_time.py, test_reactive.py, test_reactive_comprehensive.py
- test_reactive_dispatch_workers.py

**预估用例数：** ~300+

### 第三组：Bridge 测试（可选，视环境）
**文件列表：** tests/bridge/ 下 Rust/FreeBasic/Mojo/Cangjie 等测试
**说明：** 需要对应语言编译器已安装，3.6 环境可能存在编译兼容问题

---

## 3. 执行步骤

### 阶段 1：环境验证
1. 验证 Python 3.13 环境：`python --version`
2. 验证 Python 3.6 虚拟环境：`e:\py36-venv\Scripts\python.exe --version`
3. 验证两个环境都能 import vools（3.6 环境用 `pip install -e .` 安装开发版本）
4. 验证 3.6 环境依赖：attrs, contextvars, typing_extensions 等

### 阶段 2：3.13 测试（子代理 A）
在 Python 3.13 上依次运行：
1. 第一组核心基础测试
2. 第二组 Reactive 核心测试
3. （可选）第三组 Bridge 测试
4. 记录通过率、失败用例、错误信息

### 阶段 3：3.6 测试（子代理 B）
在 Python 3.6 上依次运行：
1. 第一组核心基础测试
2. 第二组 Reactive 核心测试（预期 asyncio 相关测试可能需要跳过）
3. 记录通过率、失败用例、错误信息

### 阶段 4：结果汇总与修复
1. 对比两个版本的测试结果
2. 分析失败用例，判断是代码问题还是测试问题
3. 优先改测试文件（如测试用了高版本语法）
4. 必要时修改源代码兼容性
5. 修复后重新运行失败用例验证
6. 循环直到两个版本所有测试均通过

---

## 4. 子代理分工

### 子代理 A：Python 3.13 测试
- **任务**：在当前 Python 3.13 环境运行所有非监控类测试
- **命令前缀**：`python -m pytest`
- **输出**：测试结果摘要，失败用例详情

### 子代理 B：Python 3.6 测试
- **任务**：在 Python 3.6 虚拟环境运行所有非监控类测试
- **命令前缀**：`e:\py36-venv\Scripts\python.exe -m pytest`
- **注意**：需确保 3.6 环境已安装 vools 开发版及兼容依赖
- **输出**：测试结果摘要，失败用例详情

---

## 5. 潜在依赖与注意事项

### 5.1 Python 3.6 依赖
必须确保 3.6 虚拟环境安装了以下兼容包：
- `attrs` — dataclass_compat 依赖
- `contextvars` — 3.6 无 contextvars 标准库
- `typing_extensions` — 扩展 typing 支持
- `pytest` — 测试框架
- 其他项目依赖（参考 pyproject.toml）

### 5.2 3.6 已知限制
- 不支持 `asyncio.get_running_loop()` → 已用 compat 层解决
- 不支持 `asyncio.run()` → 已用 compat 层解决
- 响应式模块中部分异步功能可能受限 → 可接受跳过
- dataclass 使用 attrs backport → 已解决

### 5.3 测试执行顺序
- 先跑核心基础测试，再跑 Reactive
- 监控类完全排除
- Bridge 测试视环境可选

---

## 6. 风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|----------|
| 3.6 环境缺少依赖 | 导入失败 | 先安装兼容依赖再测试 |
| 3.6 语法不兼容 | 运行时报错 | 修改源码或跳过对应测试 |
| 测试用例用了高版本语法 | 收集阶段失败 | 修改测试文件兼容 3.6 |
| Reactive 异步测试在 3.6 异常 | 部分测试失败 | 标记 xfail 或 skip |
| Bridge 测试缺少编译器 | 测试跳过 | 跳过即可，不算失败 |
| 缓存状态污染（id 复用） | 偶发失败 | 已修复 sigcache，如再遇则清理缓存 |

---

## 7. 成功标准

**两个 Python 版本均满足以下条件才算通过：**
- ✅ 核心基础测试：全部通过（允许 xfail）
- ✅ Reactive 核心测试：全部通过（允许 xfail）
- ❌ 监控类测试：全部排除，不计入结果
- ⚠️ Bridge 测试：视环境可选，有编译器则需通过

最终输出：双版本测试报告，包含通过数、跳过数、预期失败数、失败详情。
