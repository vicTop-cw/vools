# vools 项目开发规则（AI 辅助开发参考）

本文档定义 vools 项目的代码规范和约束，供 AI 开发助手（如 AtomCode）和人类开发者共同遵守。

---

## 1. `__all__` 规则

**每个 `.py` 文件（非 `__init__.py`）必须显式定义 `__all__`。**

```python
# ✅ 正确
__all__ = ['TaskQueue', 'WorkerPool']

# ❌ 错误 — 无 __all__
# ❌ 错误 — __all__ 包含本模块未定义的符号
```

- `__all__` 应只包含本模块**实际定义**的公开类、函数、变量
- `__all__` 不应包含从其他模块 import 进来的符号
- `__init__.py` 可选（有 `__all__` 可精确控制 `from pkg import *` 的行为）

**检查命令：**
```bash
python -c "import os, ast; base='vools'; \
missing=[os.path.relpath(os.path.join(r,f),base).replace('\\\\','/') \
for r,_,fs in os.walk(base) for f in fs if f.endswith('.py') \
and '__all__' not in open(os.path.join(r,f),encoding='utf-8').read() \
and not os.path.join(r,f).endswith('__init__.py') \
and not any(d in r for d in ['__pycache__','.git','.pytest_cache','Temp'])]; \
print(f'missing __all__: {len(missing)}'); [print(f'  {m}') for m in sorted(missing)]"
```

---

## 2. README 规则

**每个子包（含 `__init__.py` 的目录）必须有 `README.md`。**

```
vools/subpkg/
├── __init__.py
├── README.md          # ✅ 必须
├── core/
│   ├── __init__.py
│   ├── README.md      # ✅ 每个子包都要
│   └── ...
└── rules/
    ├── __init__.py
    ├── README.md      # ✅ 每个子包都要
    └── ...
```

README 至少包含：
- 包功能简述
- 核心类/函数表格（名称、类型、说明）
- 简单使用示例

---

## 3. 文档字符串规则

**所有公开 API 必须有完善的 docstring。**

### 模块级 docstring

```python
"""
模块功能简述

详细说明（可选）。

示例:
    >>> from vools.xxx import yyy
    >>> yyy(1, 2)
    3
"""
```

### 函数/方法 docstring（Google style）

```python
def submit(self, func: Callable, *args, **kwargs) -> int:
    """
    提交任务到队列

    Args:
        func: 要执行的函数
        *args: 传递给 func 的位置参数
        **kwargs: 关键字参数:
            - priority: 任务优先级（默认 0）
            - max_retries: 最大重试次数（默认 3）
            - depends_on: 依赖的任务 ID 集合（可选）

    Returns:
        任务 ID

    Raises:
        DagValidationError: 检测到循环依赖时抛出
        ValueError: 函数无法序列化时抛出
    """
```

### 类 docstring

```python
class TaskQueue:
    """任务队列管理器

    支持任务提交、状态查询、结果获取和 DAG 依赖编排。

    Args:
        db_path: SQLite 数据库路径（默认 "tasks.db"）

    Example:
        >>> queue = TaskQueue("tasks.db")
        >>> task_id = queue.submit(add, 1, 2)
        >>> queue.get_result(task_id)
        3
    """
```

**需要 docstring 的位置：**
- 所有模块文件（顶部）
- 所有公开类
- 所有公开方法（含 `@property`）
- 所有公开函数
- 复杂的私有方法（必要时）

---

## 4. 类型注解规则

**所有函数参数和返回值必须有类型注解。**

```python
# ✅ 正确
def submit(self, func: Callable, *args: Any, **kwargs: Any) -> int:
    ...

def evaluate(self, context: Dict[str, Any]) -> Result:
    ...

# ❌ 错误 — 无注解
# def submit(self, func, *args, **kwargs):
#     ...

# ❌ 错误 — 缺少返回值注解
# def submit(self, func: Callable, *args, **kwargs):
#     ...
```

### 常用类型

| 场景 | 注解 |
|------|------|
| 函数参数 | `Callable[[ArgType], ReturnType]` |
| 可选值 | `Optional[str]` |
| 集合 | `List[int]`, `Set[str]`, `Dict[str, Any]` |
| 联合 | `Union[int, str]`, `Optional[int]` = `Union[int, None]` |
| 任意 | `Any` |
| 返回值 | `-> None`, `-> int`, `-> Result` |
| 字面量 | `Literal["thread", "process"]` |

---

## 5. 更新规则

**当新增或修改 API 时，以下内容必须同步更新：**

| 变更类型 | 必须同步更新的文件 |
|----------|-------------------|
| 新增模块 | `__all__` + `README.md` + 模块 docstring |
| 新增类/函数 | 类型注解 + docstring + 父包 `__init__.py` 导出 |
| 修改函数签名 | 类型注解 + docstring 参数说明 |
| 新增子包 | 父包 `README.md` 子包索引 + 新子包 `README.md` |
| 修改行为 | docstring 示例 + 依赖该 API 的调用方 |
| **修改源码** | **检查并更新对应的 `tests/test_*.py` 测试文件** |

> 修改任何源码后，必须运行相关测试并确保通过。如果测试文件没有覆盖改动，可能需要新增测试用例。

---

## 6. 导入规范

### 优先使用本地兼容层

```python
# ✅ 正确 — 使用本地 dataclass 兼容层
from vools.core.dataclass_compat import dataclass, field

# ❌ 错误 — 直接使用标准库（在 Python < 3.7 会报错）
from dataclasses import dataclass
```

### 避免回环导入

```python
# ❌ 危险 — config.py 在 vools.core.__init__ 加载期间引用 vools.core
from vools.core import dataclass

# ✅ 安全 — 直接导入具体模块
from .dataclass_compat import dataclass
from vools.core.dataclass_compat import dataclass
```

**回环导入检测：** 如果 `python -c "from vools.xxx import yyy"` 报 `ImportError: cannot import name ... from partially initialized module`，说明存在回环。

---

## 7. 函数式风格（推荐，非强制）

项目设计偏向函数式风格，但不强制。能靠上尽量靠：

```python
# ✅ 推荐 — 纯函数，返回 Result
def validate(ctx: Dict[str, Any]) -> Result:
    try:
        return Result.success(ctx.get("value", 0) > 0)
    except Exception as e:
        return Result.failure(e)

# ✅ 推荐 — 不可变数据
@dataclass(frozen=True)
class Rule:
    name: str
    ...

# ✅ 推荐 — 管道组合
result = data | Ops.filter(pred) | Ops.map(func) | Ops.sum()
```

**例外情况不强制：**
- 内部实现细节（私有方法）
- 性能敏感的 hot path
- 与外部库交互的桥接代码

---

## 8. 修改前先同步

**在任何代码修改、新增、重构之前，必须先同步仓库到最新状态：**

```bash
git pull --rebase
```

避免基于过期版本做修改导致合并冲突。

---

## 9. 快速验证

提交前运行：

```bash
# 1. 检查 __all__ 完整性
python -c "..."  # 见第 1 节命令

# 2. 检查导入
python -c "from vools import *; print('OK')"

# 3. 运行核心测试
python -m pytest tests/test_task_queue.py tests/test_task_complete.py -v --tb=short

# 4. 检查 README 覆盖率
python -c "import os; base='vools'; \
pkg=set(); [pkg.add(os.path.relpath(r,base).replace('\\\\','/')) \
for r,_,f in os.walk(base) for f in f if '__init__.py' in f]; \
missing=[p for p in sorted(pkg) if not os.path.exists(os.path.join(base,p.replace('/','\\\\'),'README.md'))]; \
[print(f'MISS: {p}') for p in missing]; print(f'total: {len(pkg)}, missing: {len(missing)}')"
```

---

## 9. 目录规范约定

### 源码目录

所有正式模块代码放在 `vools/` 下，按子包组织。

### 辅助检查与工具脚本

代码合规检查、项目维护脚本放在 `dev_tools/` 目录。

```
dev_tools/
├── check_all.py                  # 全量检查入口
├── check_docs.py                 # docstring/注解完整性检查
├── check_duplicate_names.py      # 重名检查
├── analyze_duplicates.py         # 重复代码分析
├── verify_duplicates.py          # 重复验证
├── test_all_features.py          # 功能完整性测试
├── split_guide.py               # 拆分指南
└── curry_*_optimized.py         # 性能优化实验（可演化为正式代码）
```

**规则：** `dev_tools/` 下的脚本可以引用 `vools` 包，但不被 `vools` 包引用。它们不是发布的一部分。

### 临时/实验性代码

不确定是否合入主库的代码、一次性的分析脚本、原型验证，放在 `Temp/` 目录。

```
Temp/
├── Backup/                       # 旧版本备份
├── Test/                         # 临时测试
│   ├── benchmark.py
│   └── ...
├── stuff_benchmark/
├── _build_new_files.py           # 批量创建文件的辅助脚本
├── test_*.py                     # 各种临时测试文件
└── ...
```

**规则：**
- `Temp/` 下的代码不纳入 `vools` 包——不参与发布、不参与 pytest 测试集
- `Temp/` 可以包含独立的 `__main__` 测试或临时试验
- 所有自动化的合规检查命令（`__all__` 扫描等）应**跳过** `Temp/` 目录
- 当临时代码成熟后，迁入 `vools/` 相应子包 + `tests/` 正式测试

### 临时测试

临时测试放在 `Temp/tests/` 目录（注意与正式 `tests/` 区分）。

```
Temp/tests/
├── test_xxx.py                  # 某个功能的临时验证
└── ...
```

**规则：**
- `Temp/tests/` 不纳入 pytest 自动发现（pytest 只扫 `tests/`）
- 临时测试可以依赖 `vools` 包和标准库
- 临时测试通过后，应迁移为 `tests/test_xxx.py` 正式测试

---

## 10. 代码同步方向规则（重要！）

**禁止从仓库直接覆盖本地代码。所有代码变更必须由本地开发环境推送到仓库。**

### 正向流程（允许）

```
本地代码修改 → git add → git commit → git push → 远程仓库
```

### 反向流程（禁止）

```
远程仓库 → git pull / git fetch + git reset / 任何直接覆盖本地的操作 ❌
```

**具体约束：**

| 操作 | 允许？ | 说明 |
|------|--------|------|
| `git push` | ✅ 允许 | 本地代码推送到远程 |
| `git pull --rebase` | ⚠️ 仅查看 | 仅用于同步远程信息到本地**参考分支**，不得覆盖本地工作代码 |
| `git fetch` | ⚠️ 仅查看 | 拉取远程引用用于 diff 对比，不改变本地工作区 |
| `git pull`（merge） | ❌ 禁止 | 会直接合并远程代码到本地工作分支 |
| `git reset --hard origin/main` | ❌ 禁止 | 直接丢弃本地修改 |
| `git checkout origin/main -- <file>` | ❌ 禁止 | 用远程仓库文件覆盖本地文件 |
| 任何将远程文件直接同步覆盖到本地的操作 | ❌ 禁止 | 本地是唯一可信代码源 |

### 原因

- 远程仓库应作为**备份与分发中心**，而非代码权威来源
- 所有代码变更必须经由本地开发环境测试验证后，再推送到远程
- 避免远程非预期变更破坏本地开发环境
