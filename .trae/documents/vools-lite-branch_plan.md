# vools-lite 分支实施计划

> **For agentic workers:** 本计划移除桥接/reactive/dll32 等子包与全部第三方依赖，仅用 Python 标准库，并将保留模块的类型注解重写为 Python 3.14 风格。步骤使用 `- [ ]` 复选框跟踪。

**Goal:** 在 `vools-lite` 分支上产出一个仅依赖 Python 3.14 标准库的精简版 vools，移除 bridge/reactive/dll32/api/sql/xl 等子包及所有第三方库，保留核心装饰器/函数式/数据/日期/task/oop/security/serialize(encoding-only)/sys(精简)/utils/cache/curried/crypto 模块并将其注解现代化。

**Architecture:**
- 分支策略：从当前 `main`（HEAD `35ad7e7` v0.4.9）拉出 `vools-lite` 分支，保留完整 git 历史便于后续 cherry-pick 主线修复。
- 依赖策略：`requires-python = ">=3.14"`，`dependencies = []`，移除所有 `[project.optional-dependencies]` 中的第三方包（typer/fire/msgpack/orjson/pyspark/psycopg2/pandas/PyYAML/attrs/setuptools-pkg_resources/mkdocs 等）。
- 移除策略：第三方依赖子包整包删除（api/sql/xl/bridge/reactive/dll32）；仅"代码路径"依赖第三方的模块，删除第三方路径后保留模块（security/safe_eval 去 rust、security/hash 去 nim、encoding 去 nim、serialize 去 msgpack/orjson/bridge、data/table 去 pandas、core/config 去 yaml、utils/tools 用 importlib.metadata、sys 去 fire/dll_cmd/bridge）。
- 重写策略：所有保留模块的类型注解迁移到 PEP 695（`def f[T](x: T) -> T`、`type Alias = ...`）、PEP 696（TypeVar 默认值）、PEP 702（`@typing.deprecated`）、PEP 742（`TypeIs`）、PEP 649（移除 `from __future__ import annotations`）、内建泛型（`list[T]`/`X | None`/`dict[str, Any]`）、`typing.override`；删除所有 `sys.version_info` 兼容分支与 `*_compat.py` 垫片。

**Tech Stack:** Python 3.14 标准库（argparse、json、pickle、tomllib、sqlite3 不再用、hashlib、hmac、base64、zlib、gzip、lzma、importlib.metadata、typing、dataclasses、asyncio、concurrent.futures、inspect、functools、itertools、collections、ctypes 等）。

---

## 决策记录（已与用户确认）

1. **处理策略 = 全部移除**：依赖第三方库的子包/模块整包移除（api、sql、xl、serialize 高级后端、core/config 的 yaml、sys/fire_app、core/dataclass_compat、utils/tools 的 pkg_resources）；仅"加速路径"依赖第三方的，删除该路径后保留模块。
2. **分支 = 基于 main，命名 `vools-lite`**：保留 git 历史。
3. **重写 = 所有保留模块，主要是注解，3.14 特性均可用。**
4. **sqlite 判定**：用户选择"全部移除"，sql 整包删除（含 sqlite 后端），不再保留 SQL 能力。
5. **plan 文件位置**：`.trae/documents/vools-lite-branch_plan.md`（项目既有约定）。

---

## 文件结构总览

### 整包删除（目录/子包）
- `vools/bridge/` — 跨语言桥接（27 语言）
- `vools/reactive/` — 响应式（core/monitoring/operators）
- `vools/dll32/` — 32 位嵌入式 Python 桥接
- `vools/api/` — typer CLI（依赖 typer/typing_extensions）
- `vools/sql/` — SQL 框架（postgres/spark/sqlite，整包移除）
- `vools/xl/` — Excel（依赖 libxl DLL + pandas）
- `vools/data/itor.nim`、`vools/data/itor_nim.py` — Nim 加速迭代器
- `nim_core/` — Nim 编译产物（项目根，非 vools 运行时）
- `__rust__/` — Rust cargo 缓存产物（项目根）

### 单文件删除
- `vools/serialize/backends/msgpack_backend.py` — msgpack 后端
- `vools/sys/fire_app.py` — fire CLI
- `vools/sys/dll_cmd.py` — 依赖 `bridge.core.loader`
- `vools/core/dataclass_compat.py` — attrs 降级垫片
- `vools/core/asyncio_compat.py` — 旧 asyncio 兼容垫片
- `vools/core/contextvars_compat.py` — 旧 contextvars 兼容垫片
- `vools/core/datetime_compat.py` — 旧 datetime 兼容垫片
- `vools/core/inspect_compat.py` — 旧 inspect 兼容垫片
- `vools/decorators/bridge_decorator.py` — `@bridge` 装饰器（依赖 bridge 子包）
- `mkdocs.yml` — mkdocs 第三方构建配置（docs/*.md 保留为纯文档）

### 修改（删除第三方/bridge 代码路径，保留模块）
- `vools/__init__.py` — 去 bridge try/except、去 reactive _lazy_modules 条目、去 sql/xl/api 引用、删 `< (3,7)` 兼容块
- `vools/__main__.py` — 去 `api` 子命令（typer）、去 `sys dll` 子命令（dll_cmd）
- `vools/core/__init__.py` — 去 compat 导入
- `vools/core/config.py` — yaml `load_from_file` 改用 `tomllib`（标准库 3.11+）
- `vools/security/safe_eval.py` — 删 `from ..bridge.rust import safe_eval_shim`（唯一硬依赖）
- `vools/security/hash.py` — 删 `from ..bridge.nim import ...` try/except 块
- `vools/encoding/__init__.py` — 删 `from vools.bridge.nim.compress_shim import ...` try/except 块
- `vools/serialize/codec.py` — 删 `from ..decorators.bridge_decorator import bridge` 与 `bridge.nim` try/except
- `vools/serialize/backends/json_backend.py` — 删 `import orjson`、删 `bridge.nim` 延迟导入、删 `bridge_decorator` 导入
- `vools/serialize/backends/__init__.py` — 删 msgpack_backend 导入
- `vools/sys/__init__.py` — 删 `fire_app` 导入、删 `dll_cmd` 导入
- `vools/sys/env.py` — 删 `bridge.powershell`/`bridge.shell` 延迟导入
- `vools/sys/env_cmd.py` — 删 `bridge.core.loader` 导入
- `vools/decorators/__init__.py` — 删 `from .bridge_decorator import ...` 及 `__all__` 条目
- `vools/data/table.py` — 删 `to_dataframe`（pandas）方法
- `vools/utils/tools.py` — `pkg_resources` → `importlib.metadata`
- `pyproject.toml` — 清空 optional-dependencies、`requires-python=">=3.14"`、删 dll32/xl/lib package-data、简化包发现、更新 classifiers、修 pytest addopts

### 测试清理
- 删 `tests/bridge/`、`tests/dll32/`、`tests/reactive/`、`tests/monitoring/`、`tests/xl/`、`tests/benchmarks/`
- 删 `tests/functional/test_only_code_mode.py`、`tests/other/test_project_mode.py`、`tests/archive/test_task9_units.py`、`tests/benchmarks/benchmark_reactive.py`、`tests/benchmarks/perf_xl_*.py`、`tests/benchmarks/test_curried_performance.py`（若依赖移除模块）
- 改 `tests/serialize/test_serialize*.py` — 去 msgpack/orjson 用例
- 改 `pyproject.toml` 的 `addopts` — 删已不存在的 `--ignore` 路径

### 文档/Meta 清理
- 删 `docs/bridge/`、`docs/reactive/`、`docs/sql/`、`docs/appendix/platform.md`（保留为空或删桥接章节）
- 删 `mkdocs.yml`、`.pre-commit-config.yaml` 中第三方 hook（保留 pyproject 即可）
- 可选：删 `.trae/specs/` 中已废特性 spec（bridge-subpackage、dll32-subpackage、fbc-dll-integration、vbnet-api-tlb-bridge、vools-sys-bridge-ext、bridge-c-first、libxl-sqlcel-integration、xl-engine-adapter-and-sqlcel-integration、clipboard-monitor-dispatcher、file-watcher-dispatcher、folder-watcher-dispatcher、keyboard_mouse、recorder-player）

### 注解重写（PEP 695/696/702/742/649，所有保留模块）
统一模式（每模块套用）：
- `from typing import List, Dict, Tuple, Set, Optional, Union, Callable, TypeVar, TypeAlias, Generic` → 内建泛型 + `from typing import Callable, Never, NoReturn, ClassVar, Final, deprecated, override` + `from collections.abc import Callable as Callable`（按需）
- `T = TypeVar("T")` + `def f(x: T) -> T:` → `def f[T](x: T) -> T:`
- `T = TypeVar("T", bound=...)` → `def f[T: ...](x: T) -> T:`
- `TypeAlias`/`Union` 别名 → `type Alias = ...`
- `Optional[X]`/`Union[X, Y]` → `X | None` / `X | Y`
- `TypeGuard[X]` → `TypeIs[X]`（PEP 742，语义更严格，按需替换）
- `from __future__ import annotations` → 删除（3.14 PEP 649 默认惰性求值）
- `if sys.version_info < (3, x):` 分支 → 删除低版本分支，保留 3.14 实现
- 弃用 API 加 `@deprecated("use X instead")`（PEP 702）
- 子类重写父类方法加 `@override`

涉及模块（逐个重写）：
`vools/__init__.py`、`vools/__main__.py`、`vools/core/{base,config,exceptions}.py`、`vools/cache/{memorize,once,persist,sigcache}.py`、`vools/crypto/core.py`、`vools/curried/{collection,composition,core,iteration,math,predicate,string}.py`、`vools/data/{seq,table,vlist,vtext,qax,itor}.py`、`vools/datetime/{dates_format,utils,vdate_class}.py`、`vools/decorators/{cache,control,curry_core,curry_decorator,curry_delay,curried,lazy,overload,overloads,overcurry,rself,selector,shotcut,trd}.py`、`vools/encoding/core.py`、`vools/functional/{arrow_func,box,funcs,iif,pipe_ops,placeholder,placeholder_impl,result}.py`、`vools/oop/{calltype,extend,fusion,method_extend,mixer,selector}.py`、`vools/security/{safe_eval,hash,_constants,expression_handler}.py`、`vools/serialize/{codec,config,context,core,decorators,sentinel,type_registry}.py`、`vools/serialize/backends/{base,json_backend,pickle_backend}.py`、`vools/serialize/callable/{decorator_handler,functional_handler}.py`、`vools/sys/{cmd,compile_cmd,env,env_cmd,exe,run_cmd,dll}.py`、`vools/task/core/{models,queue,storage,worker}.py`、`vools/task/decorators/task_decorator.py`、`vools/task/rules/{dag,engine,rule}.py`、`vools/utils/{hoder,stuff,tools}.py`、各 `__init__.py`。

---

## 阶段 0：创建分支

### Task 0.1：创建 vools-lite 分支

**Files:** 无（git 操作）

- [ ] **Step 1: 确认工作区干净**

Run: `git -C /workspace status --short`
Expected: 无输出（干净）

- [ ] **Step 2: 从 main 创建并切换分支**

Run: `git -C /workspace checkout -b vools-lite`
Expected: `Switched to a new branch 'vools-lite'`

- [ ] **Step 3: 验证分支**

Run: `git -C /workspace branch --show-current`
Expected: `vools-lite`

---

## 阶段 1：整包删除子包

### Task 1.1：删除 bridge / reactive / dll32 子包

**Files:**
- Delete: `vools/bridge/`（整目录）
- Delete: `vools/reactive/`（整目录）
- Delete: `vools/dll32/`（整目录，含 _python32/python.exe 等大文件）

- [ ] **Step 1: 删除三个子包目录**

Run:
```
rm -rf /workspace/vools/bridge /workspace/vools/reactive /workspace/vools/dll32
```

- [ ] **Step 2: 验证目录已删**

Run: `ls /workspace/vools/ | grep -E 'bridge|reactive|dll32' || echo "OK: removed"`
Expected: `OK: removed`

### Task 1.2：删除 api / sql / xl 子包

**Files:**
- Delete: `vools/api/`（typer CLI）
- Delete: `vools/sql/`（postgres/spark/sqlite，整包）
- Delete: `vools/xl/`（libxl + pandas）

- [ ] **Step 1: 删除三个子包目录**

Run:
```
rm -rf /workspace/vools/api /workspace/vools/sql /workspace/vools/xl
```

- [ ] **Step 2: 验证**

Run: `ls /workspace/vools/ | grep -E '^(api|sql|xl)$' || echo "OK: removed"`
Expected: `OK: removed`

### Task 1.3：删除 Nim/Rust 构建产物与 Nim 加速文件

**Files:**
- Delete: `vools/data/itor.nim`
- Delete: `vools/data/itor_nim.py`
- Delete: `nim_core/`（项目根）
- Delete: `__rust__/`（项目根）

- [ ] **Step 1: 删除文件与目录**

Run:
```
rm -f /workspace/vools/data/itor.nim /workspace/vools/data/itor_nim.py
rm -rf /workspace/nim_core /workspace/__rust__
```

- [ ] **Step 2: 验证**

Run: `ls /workspace/vools/data/itor* 2>/dev/null; ls -d /workspace/nim_core /workspace/__rust__ 2>/dev/null; echo "done"`
Expected: 仅 `done`（无残留）

- [ ] **Step 3: 检查 data 包是否仍引用 itor_nim**

Run: `grep -rn "itor_nim\|itor\.nim" /workspace/vools/data/ /workspace/tests/data/ 2>/dev/null || echo "OK: no refs"`
Expected: `OK: no refs`（若有引用，记录到 Task 3.x 处理）

### Task 1.4：提交阶段 1

- [ ] **Step 1: 暂存并提交**

Run:
```
git -C /workspace add -A
git -C /workspace commit -m "chore(lite): remove bridge/reactive/dll32/api/sql/xl subpackages and nim/rust artifacts"
```
Expected: 提交成功

---

## 阶段 2：删除第三方依赖单文件

### Task 2.1：删除 serialize msgpack 后端

**Files:**
- Delete: `vools/serialize/backends/msgpack_backend.py`

- [ ] **Step 1: 删除文件**

Run: `rm -f /workspace/vools/serialize/backends/msgpack_backend.py`

- [ ] **Step 2: 删除 backends/__init__.py 中的 msgpack 导入**

Read `vools/serialize/backends/__init__.py`，删除所有引用 `msgpack_backend`/`MsgpackBackend` 的行。

- [ ] **Step 3: 验证**

Run: `python3 -c "import ast; ast.parse(open('/workspace/vools/serialize/backends/__init__.py').read()); print('OK')"`
Expected: `OK`

### Task 2.2：删除 sys/fire_app.py 与 sys/dll_cmd.py

**Files:**
- Delete: `vools/sys/fire_app.py`（fire）
- Delete: `vools/sys/dll_cmd.py`（依赖 `bridge.core.loader`）

- [ ] **Step 1: 删除文件**

Run: `rm -f /workspace/vools/sys/fire_app.py /workspace/vools/sys/dll_cmd.py`

- [ ] **Step 2: 修改 `vools/sys/__init__.py`，移除对 fire_app/dll_cmd 的导入与导出**

Read `vools/sys/__init__.py`，删除：
- `from .fire_app import SysCLI`（及 try/except 包装）
- `from .dll_cmd import ...`
- `__all__` 中 `SysCLI`、`dll_cmd` 等条目

保留：`cmd`、`exe`、`dll`、`get_env`、`get_env_with_default` 等纯 Python 导出。

- [ ] **Step 3: 验证 sys 包可导入**

Run: `cd /workspace && python3 -c "import vools.sys; print('OK')"` 
Expected: `OK`（若报错，记录缺失符号到 Task 3.x）

### Task 2.3：删除 core 兼容垫片

**Files:**
- Delete: `vools/core/dataclass_compat.py`（attrs）
- Delete: `vools/core/asyncio_compat.py`
- Delete: `vools/core/contextvars_compat.py`
- Delete: `vools/core/datetime_compat.py`
- Delete: `vools/core/inspect_compat.py`

- [ ] **Step 1: 删除五个垫片文件**

Run:
```
rm -f /workspace/vools/core/dataclass_compat.py \
      /workspace/vools/core/asyncio_compat.py \
      /workspace/vools/core/contextvars_compat.py \
      /workspace/vools/core/datetime_compat.py \
      /workspace/vools/core/inspect_compat.py
```

- [ ] **Step 2: 修改 `vools/core/__init__.py`，移除对垫片的导入**

Read `vools/core/__init__.py`，删除所有 `from .xxx_compat import ...` 与对应 `__all__` 条目。若其它保留模块（如 task/cache）通过 `vools.core.asyncio_compat` 导入，记录到 Task 3.x 一并改为标准库 `asyncio`/`contextvars`/`inspect`。

- [ ] **Step 3: 全局扫描残留引用**

Run: `grep -rn "asyncio_compat\|contextvars_compat\|datetime_compat\|inspect_compat\|dataclass_compat" /workspace/vools/ || echo "OK: no refs"`
Expected: `OK: no refs`（若有，记录文件清单到 Task 3.x）

### Task 2.4：删除 decorators/bridge_decorator.py

**Files:**
- Delete: `vools/decorators/bridge_decorator.py`

- [ ] **Step 1: 删除文件**

Run: `rm -f /workspace/vools/decorators/bridge_decorator.py`

- [ ] **Step 2: 修改 `vools/decorators/__init__.py`**

删除：
- `from .bridge_decorator import bridge, BridgeRegistry`
- `__all__` 中的 `'bridge'`、`'BridgeRegistry'`

- [ ] **Step 3: 扫描其它模块对 `bridge` 装饰器的使用**

Run: `grep -rn "from ..decorators.bridge_decorator\|from .bridge_decorator\|@bridge\b\|decorators\.bridge" /workspace/vools/ || echo "OK: no refs"`
Expected: 命中 `vools/serialize/codec.py:14`、`vools/serialize/backends/json_backend.py:8`（记录到 Task 3.4/3.5 处理）

### Task 2.5：删除 mkdocs.yml

**Files:**
- Delete: `mkdocs.yml`（mkdocs 第三方构建）

- [ ] **Step 1: 删除**

Run: `rm -f /workspace/mkdocs.yml`

- [ ] **Step 2: 保留 docs/*.md 作为纯文档，无需改动**

### Task 2.6：提交阶段 2

- [ ] **Step 1: 提交**

Run:
```
git -C /workspace add -A
git -C /workspace commit -m "chore(lite): remove msgpack backend, fire/dll_cmd, core compat shims, bridge_decorator, mkdocs"
```

---

## 阶段 3：清理保留模块中的第三方/bridge 代码路径

> 通用验证命令（每个 Task 末尾运行）：`cd /workspace && python3 -c "import vools.<sub>; print('OK')"`

### Task 3.1：core/config.py — yaml → tomllib

**Files:** Modify `vools/core/config.py`

- [ ] **Step 1: 定位 yaml 用法**

Run: `grep -n "import yaml\|yaml\." /workspace/vools/core/config.py`
Expected: 命中 `load_from_file` 方法内 `import yaml` 与 `yaml.safe_load`

- [ ] **Step 2: 改写 load_from_file 使用 tomllib**

将 `import yaml` + `yaml.safe_load` 替换为：
```python
import tomllib  # 标准库 3.11+
```
读取逻辑改为 `tomllib.load(f)`（二进制模式 `open(path, "rb")`）。若原方法支持 `.json`/`.yaml` 多格式，则按扩展名分流：`.toml` → tomllib，`.json` → json，其余报错。删除 PyYAML 路径。

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "from vools.core.config import ConfigManager; print('OK')"`
Expected: `OK`

### Task 3.2：security/safe_eval.py — 删除 bridge.rust 硬依赖

**Files:** Modify `vools/security/safe_eval.py`（第 209-210 行）

- [ ] **Step 1: 删除模块级裸导入**

删除：
```python
from ..bridge.rust import safe_eval_shim as _safe_eval_shim
```

- [ ] **Step 2: 调整调用点**

搜索 `_safe_eval_shim` 的所有调用点，改为纯 Python 实现（保留 `safe_eval` 的标准库 `ast` + `eval` 路径，删除 Rust 加速分支）。若存在 `_safe_eval_shim is not None` 判断，改为 `False`。

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "from vools.security import safe_eval; print(safe_eval('1+2'))"`
Expected: `3`

### Task 3.3：security/hash.py 与 encoding/__init__.py — 删除 bridge.nim 加速路径

**Files:** Modify `vools/security/hash.py`（第 31-40 行）、`vools/encoding/__init__.py`（第 99-113 行）

- [ ] **Step 1: hash.py — 删除 nim 导入块**

删除：
```python
try:
    from ..bridge.nim import sha256 as _nim_sha256_impl
    from ..bridge.nim import md5 as _nim_md5_impl
    from ..bridge.nim import sha1 as _nim_sha1_impl
    _nim_available = True
except ImportError:
    ...
```
将 `_nim_available` 直接置 `False`（或删除所有 `_nim_available` 分支，保留标准库 `hashlib` 路径）。

- [ ] **Step 2: encoding/__init__.py — 删除 nim compress_shim 导入块**

删除 `try: from vools.bridge.nim.compress_shim import ... except ImportError: pass` 整块，保留标准库 `gzip`/`zlib`/`lzma` 实现作为唯一路径。

- [ ] **Step 3: 验证**

Run:
```
cd /workspace && python3 -c "from vools.security import hash as h; print(h.sha256('x'))" && python3 -c "from vools.encoding import gzip_compress, gzip_decompress; print(len(gzip_compress(b'x')))"
```
Expected: 两个均输出非空

### Task 3.4：serialize/codec.py — 删除 bridge_decorator 与 bridge.nim

**Files:** Modify `vools/serialize/codec.py`（第 14、388-396 行）

- [ ] **Step 1: 删除 bridge_decorator 导入**

删除：`from ..decorators.bridge_decorator import bridge`

- [ ] **Step 2: 删除 bridge.nim try/except 块**

删除：
```python
try:
    from ..bridge.nim import nim_pickle_encode as _nim_encode
    ...
except ImportError:
    pass
```
保留标准库 `pickle` 路径作为唯一编解码实现。

- [ ] **Step 3: 删除 `@bridge(...)` 装饰器用法**

搜索 `@bridge(` 用法，删除该装饰器（保留被装饰函数的纯 Python 实现）。

- [ ] **Step 4: 验证**

Run: `cd /workspace && python3 -c "from vools.serialize import codec; print('OK')"`
Expected: `OK`

### Task 3.5：serialize/backends/json_backend.py — 删除 orjson 与 bridge.nim

**Files:** Modify `vools/serialize/backends/json_backend.py`（第 8、13、40、50、60、66 行）

- [ ] **Step 1: 删除 orjson 导入**

删除 `import orjson` 与 `_HAS_ORJSON` 分支，统一用标准库 `json`。

- [ ] **Step 2: 删除 bridge_decorator 与 bridge.nim 延迟导入**

删除：
- `from ...decorators.bridge_decorator import bridge`
- `_json_encode_bridge` / `_json_decode_bridge` 函数内的 `from ...bridge.nim import nim_json_*`
- `@bridge("nim", ...)` 装饰器

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "from vools.serialize.backends.json_backend import dumps, loads; print(loads(dumps({'a':1})))"`
Expected: `{'a': 1}`

### Task 3.6：sys/env.py 与 sys/env_cmd.py — 删除 bridge 引用

**Files:** Modify `vools/sys/env.py`（第 31-54 行）、`vools/sys/env_cmd.py`（第 83 行）

- [ ] **Step 1: env.py — 删除 powershell/shell bridge 延迟导入**

删除 `_get_powershell_bridge` 与 `_get_shell_bridge` 中 `from vools.bridge.powershell import ...` / `from vools.bridge.shell import ...` 的 try/except 块。两个函数改为返回 `None`（或删除函数，若调用方仅做"有则用"判断）。

- [ ] **Step 2: env_cmd.py — 删除 bridge.core.loader 导入**

删除 `from ..bridge.core.loader import _LIB_DIR`，相关 nim 命令处理改为不输出 lib 路径或删除该分支。

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "from vools.sys import env, env_cmd; print('OK')"`
Expected: `OK`

### Task 3.7：data/table.py — 删除 pandas to_dataframe

**Files:** Modify `vools/data/table.py`（第 1763 行附近）

- [ ] **Step 1: 删除 to_dataframe 方法**

删除 `def to_dataframe(self, ...):` 方法及其内 `import pandas as pd`。

- [ ] **Step 2: 扫描其它 pandas 引用**

Run: `grep -n "pandas\|import pd\|pd\." /workspace/vools/data/ || echo "OK"`
Expected: `OK`（若有残留，删除对应方法/分支）

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "from vools.data import table; print('OK')"`
Expected: `OK`

### Task 3.8：utils/tools.py — pkg_resources → importlib.metadata

**Files:** Modify `vools/utils/tools.py`（第 393 行附近）

- [ ] **Step 1: 替换导入**

将：
```python
try:
    from importlib.metadata import distribution, PackageNotFoundError
except ImportError:
    import pkg_resources
    ...
```
改为直接：
```python
from importlib.metadata import distribution, PackageNotFoundError
```
删除 `pkg_resources` 回退分支。

- [ ] **Step 2: 调整调用点**

将 `pkg_resources` API 调用改为 `importlib.metadata` 等价 API（如 `pkg_resources.get_distribution(x).version` → `distribution(x).version`）。

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "from vools.utils import tools; print('OK')"`
Expected: `OK`

### Task 3.9：vools/__init__.py — 清理顶层导出

**Files:** Modify `vools/__init__.py`

- [ ] **Step 1: 删除 bridge try/except 块**

删除第 251-259 行：
```python
try:
    from . import bridge
    BRIDGE_AVAILABLE = True
except Exception:
    BRIDGE_AVAILABLE = False
```
删除 `BRIDGE_AVAILABLE` 变量。

- [ ] **Step 2: 删除 _lazy_modules 中的 reactive 条目**

删除第 190-197 行：
```python
    'reactive': '.reactive',
    'Observable': '.reactive',
    'Subject': '.reactive',
    'BehaviorSubject': '.reactive',
    'ReplaySubject': '.reactive',
    'AsyncSubject': '.reactive',
    'ops': '.reactive',
```

- [ ] **Step 3: 删除 `< (3,7)` 兼容块**

删除第 491-525 行（`if _sys.version_info < (3, 7):` 整块）。

- [ ] **Step 4: 扫描 __all__ 中的 sql/xl/api/bridge/reactive/dll32 条目**

Run: `grep -nE "'(sql|xl|api|bridge|reactive|dll32|BRIDGE_AVAILABLE|REACTIVE_AVAILABLE)" /workspace/vools/__init__.py || echo "OK"`
Expected: `OK`（若有，删除对应 `__all__` 条目）

- [ ] **Step 5: 验证主包导入**

Run: `cd /workspace && python3 -c "import vools; print(vools.__version__)"`
Expected: `0.4.9`（或更新后的版本号）

### Task 3.10：vools/__main__.py — 清理 CLI

**Files:** Modify `vools/__main__.py`

- [ ] **Step 1: 删除 api 子命令**

删除第 15-26 行 `if sys.argv[1] == "api":` 整块（typer）。

- [ ] **Step 2: 删除 sys dll 子命令**

删除：
- `dll_parser = sys_subparsers.add_parser("dll", ...)` 及其 `--list/--dll/--func/--args` 参数
- `if args.sys_command == "dll":` 处理分支
- `from vools.sys import dll_cmd, ...` 中 `dll_cmd`（改为 `from vools.sys import compile_cmd, run_cmd, env_cmd`）

- [ ] **Step 3: 验证 CLI**

Run: `cd /workspace && python3 -m vools version`
Expected: `vools version 0.4.9` + Python 版本

### Task 3.11：提交阶段 3

- [ ] **Step 1: 提交**

Run:
```
git -C /workspace add -A
git -C /workspace commit -m "refactor(lite): strip bridge/nim/rust/yaml/pandas/pkg_resources code paths from kept modules"
```

---

## 阶段 4：更新 pyproject.toml

### Task 4.1：重写 pyproject.toml

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: 更新 [project] 元数据**

- `requires-python = ">=3.14"`
- classifiers 删除 3.6-3.13，添加 `"Programming Language :: Python :: 3.14"`
- `dependencies = []`（保持空）

- [ ] **Step 2: 清空 [project.optional-dependencies]**

删除 `serialize`/`nim`/`freebasic`/`mojo`/`rust`/`cli`/`docs`/`dev` 中所有第三方包。`dev` 仅保留纯 Python 工具（若需保留 pytest，单独说明；但 pytest 也是第三方——按"仅用标准库"，dev 工具也移除，改用 `unittest`）。最终 `[project.optional-dependencies]` 为空表或删除该节。

- [ ] **Step 3: 清理 [tool.setuptools]**

- `[tool.setuptools.packages.find]` 的 `exclude` 删除 `vools.dll32.*` 条目
- `[tool.setuptools.package-data]` 删除 `"vools"` 下的 `lib/*.dll`、`lib/*.so`、`xl/_dlls/*.dll` 等；删除整个 `"vools.dll32"` 节
- 删除 `[tool.setuptools.exclude-package-data]`

- [ ] **Step 4: 更新 [tool.pytest] 节**

若移除 pytest，删除整个 `[tool.pytest.ini_options]` 与 `[tool.coverage]` 节。若保留 pytest（作为开发期可选），更新 `addopts`：删除已不存在的 `--ignore=tests/bridge`、`tests/dll32`、`tests/xl`、`tests/monitoring`、`tests/reactive/monitoring`、`tests/__rust__` 等。

- [ ] **Step 5: 删除第三方 lint 工具配置**

删除 `[tool.black]`、`[tool.isort]`、`[tool.flake8]`、`[tool.mypy]`（均为第三方）。`python_version = "3.9"` 不再适用。

- [ ] **Step 6: 验证 pyproject 可解析**

Run: `cd /workspace && python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('OK')"`
Expected: `OK`

### Task 4.2：提交阶段 4

- [ ] **Step 1: 提交**

Run:
```
git -C /workspace add -A
git -C /workspace commit -m "build(lite): require Python 3.14, drop all third-party deps and tool configs"
```

---

## 阶段 5：测试清理

### Task 5.1：删除依赖移除模块的测试目录

**Files:**
- Delete: `tests/bridge/`、`tests/dll32/`、`tests/reactive/`、`tests/monitoring/`、`tests/xl/`、`tests/benchmarks/`

- [ ] **Step 1: 删除目录**

Run:
```
rm -rf /workspace/tests/bridge /workspace/tests/dll32 /workspace/tests/reactive \
       /workspace/tests/monitoring /workspace/tests/xl /workspace/tests/benchmarks
```

- [ ] **Step 2: 删除散落的依赖移除模块的测试文件**

Run:
```
rm -f /workspace/tests/functional/test_only_code_mode.py \
      /workspace/tests/other/test_project_mode.py \
      /workspace/tests/archive/test_task9_units.py \
      /workspace/tests/other/test_clipboard_event_loss.py \
      /workspace/tests/other/test_multiline.py 2>/dev/null
```
（`test_multiline`、`test_clipboard_event_loss` 若 import reactive/monitoring 则删，否则保留——逐个 grep 确认）

- [ ] **Step 3: grep 确认无残留 import**

Run: `grep -rln "vools\.bridge\|vools\.reactive\|vools\.dll32\|vools\.api\|vools\.sql\|vools\.xl\|import reactive\|from reactive" /workspace/tests/ || echo "OK"`
Expected: `OK`（若有命中，删除对应文件或剔除用例）

### Task 5.2：清理 serialize 测试中的 msgpack/orjson 用例

**Files:** Modify `tests/serialize/test_serialize.py`、`tests/serialize/test_serialize_types.py`

- [ ] **Step 1: 删除 msgpack/orjson 相关测试用例**

删除 `test_msgpack*`、`test_orjson*` 函数，以及 `pytest.mark.parametrize` 中 `msgpack`/`orjson` 参数项。

- [ ] **Step 2: 验证**

Run: `cd /workspace && python3 -m pytest tests/serialize/ -q 2>&1 | tail -5`（若仍用 pytest）或 `python3 -m unittest discover tests/serialize 2>&1 | tail -5`
Expected: 全部通过

### Task 5.3：更新/删除 conftest.py 与 _serialize_helpers

**Files:** Modify `tests/conftest.py`、`tests/_serialize_helpers.py`

- [ ] **Step 1: 检查 conftest 是否引用移除模块**

Run: `grep -n "bridge\|reactive\|dll32\|msgpack\|orjson\|pandas\|pyspark\|psycopg\|typer\|fire\|yaml" /workspace/tests/conftest.py /workspace/tests/_serialize_helpers.py || echo "OK"`
Expected: `OK` 或仅命中标准库 `yaml`（无）——若有第三方引用，删除对应 fixture/import

### Task 5.4：提交阶段 5

- [ ] **Step 1: 提交**

Run:
```
git -C /workspace add -A
git -C /workspace commit -m "test(lite): remove tests for bridge/reactive/dll32/xl/sql and msgpack/orjson backends"
```

---

## 阶段 6：文档与 meta 清理

### Task 6.1：删除已废功能文档

**Files:**
- Delete: `docs/bridge/`、`docs/reactive/`、`docs/sql/`
- Modify: `docs/index.md`、`docs/appendix/platform.md`（删除桥接/响应式/SQL 章节引用）

- [ ] **Step 1: 删除目录**

Run: `rm -rf /workspace/docs/bridge /workspace/docs/reactive /workspace/docs/sql`

- [ ] **Step 2: 更新 docs/index.md 导航**

删除对 bridge/reactive/sql 的链接与简介段落。

- [ ] **Step 3: 更新 README.md / USER_GUIDE.md / README_FOR_AI.md**

删除桥接/reactive/dll32/sql/xl/api 相关章节，添加 lite 版说明（仅标准库、3.14+）。

### Task 6.2：清理 .pre-commit-config.yaml

**Files:** Modify `.pre-commit-config.yaml`

- [ ] **Step 1: 删除第三方 hook**

删除 black/isort/flake8/mypy 等第三方 pre-commit hook。若文件仅含第三方 hook，整体删除文件。

### Task 6.3：清理 .github/workflows

**Files:** Modify `.github/workflows/ci.yml`

- [ ] **Step 1: 更新 CI**

删除 bridge/dll32/xl/reactive 相关测试步骤；将 Python 版本矩阵改为仅 `3.14`；移除 `pip install` 第三方依赖步骤。

### Task 6.4：可选 — 清理 .trae/specs 已废特性

**Files:** Delete `.trae/specs/{bridge-subpackage,dll32-subpackage,fbc-dll-integration,vbnet-api-tlb-bridge,vools-sys-bridge-ext,bridge-c-first,libxl-sqlcel-integration,xl-engine-adapter-and-sqlcel-integration,clipboard-monitor-dispatcher,file-watcher-dispatcher,folder-watcher-dispatcher,keyboard_mouse,recorder-player}/`

- [ ] **Step 1: 删除已废特性 spec 目录**

Run:
```
rm -rf /workspace/.trae/specs/bridge-subpackage /workspace/.trae/specs/dll32-subpackage \
       /workspace/.trae/specs/fbc-dll-integration /workspace/.trae/specs/vbnet-api-tlb-bridge \
       /workspace/.trae/specs/vools-sys-bridge-ext /workspace/.trae/specs/bridge-c-first \
       /workspace/.trae/specs/libxl-sqlcel-integration /workspace/.trae/specs/xl-engine-adapter-and-sqlcel-integration \
       /workspace/.trae/specs/clipboard-monitor-dispatcher /workspace/.trae/specs/file-watcher-dispatcher \
       /workspace/.trae/specs/folder-watcher-dispatcher /workspace/.trae/specs/keyboard_mouse \
       /workspace/.trae/specs/recorder-player
```

### Task 6.5：提交阶段 6

- [ ] **Step 1: 提交**

Run:
```
git -C /workspace add -A
git -C /workspace commit -m "docs(lite): drop bridge/reactive/sql docs, update README/CI for stdlib-only 3.14"
```

---

## 阶段 7：注解重写为 Python 3.14（按子包）

> 每个子包一个 Task。每个 Task 的统一模式：
> 1. grep 当前 `typing` 旧式导入与 `TypeVar`/`Optional`/`Union`/`List`/`Dict`/`Tuple`/`from __future__ import annotations`/`sys.version_info` 分支
> 2. 按下述规则重写
> 3. `python3 -c "import vools.<sub>"` 验证
> 4. `python3 -m py_compile` 全子包文件
>
> 重写规则（统一）：
> - `from __future__ import annotations` → 删除
> - `from typing import List,Dict,Tuple,Set,Optional,Union,TypeVar,Generic,TypeAlias,Callable` → `List`→`list`、`Dict`→`dict`、`Tuple`→`tuple`、`Set`→`set`、`Optional[X]`→`X | None`、`Union[X,Y]`→`X | Y`；`Callable` 改用 `from collections.abc import Callable`；保留需要的 `typing` 名：`Never`/`NoReturn`/`ClassVar`/`Final`/`deprecated`/`override`/`TypeIs`/`Protocol`/`runtime_checkable`
> - `T = TypeVar("T")` + 用处 → PEP 695 `def f[T](...):` / `class C[T]:`
> - `T = TypeVar("T", bound=X)` → `def f[T: X](...):`
> - `TypeAlias` 别名 → `type Alias = ...`（PEP 695）
> - `TypeGuard[X]` → `TypeIs[X]`（PEP 742，按需）
> - `if sys.version_info < (3, x):` → 删除低版本分支，保留 3.14 实现
> - 已弃用 API 加 `@deprecated("use X instead")`（PEP 702，`from typing import deprecated`）
> - 子类重写加 `@override`（`from typing import override`）

### Task 7.1：core 子包注解重写

**Files:** `vools/core/{__init__,base,config,exceptions}.py`

- [ ] **Step 1: grep 旧式注解**

Run: `grep -nE "from __future__|from typing import|TypeVar|Optional\[|Union\[|List\[|Dict\[|Tuple\[|sys\.version_info" /workspace/vools/core/*.py`

- [ ] **Step 2: 按统一规则重写四个文件**

示例（`base.py`）：
```python
# before
from typing import Any, Optional, TypeVar, Generic
T = TypeVar("T")
class VoolsBase(Generic[T]):
    def get(self, key: str, default: Optional[T] = None) -> T: ...

# after
from typing import override
class VoolsBase[T]:
    def get(self, key: str, default: T | None = None) -> T: ...
```

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "import vools.core; print('OK')" && python3 -m py_compile /workspace/vools/core/*.py`
Expected: `OK`，无编译错误

### Task 7.2：cache 子包注解重写

**Files:** `vools/cache/{__init__,memorize,once,persist,sigcache}.py`

- [ ] **Step 1-3:** grep → 重写（统一规则）→ `python3 -c "import vools.cache; print('OK')"`

### Task 7.3：crypto 子包注解重写

**Files:** `vools/crypto/{__init__,core}.py`

- [ ] **Step 1-3:** grep → 重写 → `python3 -c "import vools.crypto; print('OK')"`

### Task 7.4：curried 子包注解重写

**Files:** `vools/curried/{__init__,collection,composition,core,iteration,math,predicate,string}.py`

- [ ] **Step 1-3:** grep → 重写（注意 `Curried[T]` 用 PEP 695 类泛型）→ `python3 -c "import vools.curried; print('OK')"`

### Task 7.5：data 子包注解重写

**Files:** `vools/data/{__init__,seq,table,vlist,vtext,qax,itor}.py`

- [ ] **Step 1-3:** grep → 重写（`Seq[T]`、`VList[T]`、`VText` 用 PEP 695）→ `python3 -c "import vools.data; print('OK')"`

### Task 7.6：datetime 子包注解重写

**Files:** `vools/datetime/{__init__,dates_format,utils,vdate_class}.py`

- [ ] **Step 1-3:** grep → 重写 → `python3 -c "import vools.datetime; print('OK')"`

### Task 7.7：decorators 子包注解重写

**Files:** `vools/decorators/{__init__,cache,control,curry_core,curry_decorator,curry_delay,curried,lazy,overload,overloads,overcurry,rself,selector,shotcut,trd}.py`

- [ ] **Step 1-3:** grep → 重写（`OverloadManager`、装饰器签名用 PEP 695；弃用装饰器加 `@deprecated`）→ `python3 -c "import vools.decorators; print('OK')"`

### Task 7.8：encoding 子包注解重写

**Files:** `vools/encoding/{__init__,core}.py`

- [ ] **Step 1-3:** grep → 重写 → `python3 -c "import vools.encoding; print('OK')"`

### Task 7.9：functional 子包注解重写

**Files:** `vools/functional/{__init__,arrow_func,box,funcs,iif,pipe_ops,placeholder,placeholder_impl,result}.py`

- [ ] **Step 1-3:** grep → 重写（`Box[T]`、`Result[T,E]` 用 PEP 695 双参数泛型 `class Result[T, E]:`）→ `python3 -c "import vools.functional; print('OK')"`

### Task 7.10：oop 子包注解重写

**Files:** `vools/oop/{__init__,calltype,extend,fusion,method_extend,mixer,selector}.py`

- [ ] **Step 1-3:** grep → 重写（`Mixer`、`Selector` 用 PEP 695；方法重写加 `@override`）→ `python3 -c "import vools.oop; print('OK')"`

### Task 7.11：security 子包注解重写

**Files:** `vools/security/{__init__,safe_eval,hash,_constants,expression_handler}.py`

- [ ] **Step 1-3:** grep → 重写（`safe_eval` 类型守护用 `TypeIs`；`@deprecated` 标记旧 API）→ `python3 -c "import vools.security; print('OK')"`

### Task 7.12：serialize 子包注解重写

**Files:** `vools/serialize/{__init__,codec,config,context,core,decorators,sentinel,type_registry}.py`、`vools/serialize/backends/{__init__,base,json_backend,pickle_backend}.py`、`vools/serialize/callable/{__init__,decorator_handler,functional_handler}.py`

- [ ] **Step 1-3:** grep → 重写（`Serializer[T]`、`TypeRegistry` 用 PEP 695）→ `python3 -c "import vools.serialize; print('OK')"`

### Task 7.13：sys 子包注解重写

**Files:** `vools/sys/{__init__,cmd,compile_cmd,env,env_cmd,exe,run_cmd,dll}.py`

- [ ] **Step 1-3:** grep → 重写 → `python3 -c "import vools.sys; print('OK')"`

### Task 7.14：task 子包注解重写

**Files:** `vools/task/__init__.py`、`vools/task/core/{__init__,models,queue,storage,worker}.py`、`vools/task/decorators/{__init__,task_decorator}.py`、`vools/task/rules/{__init__,dag,engine,rule}.py`、`vools/task/utils/__init__.py`

- [ ] **Step 1-3:** grep → 重写（`Task[T]`、`TaskQueue` 用 PEP 695）→ `python3 -c "import vools.task; print('OK')"`

### Task 7.15：utils 子包注解重写

**Files:** `vools/utils/{__init__,hoder,stuff,tools}.py`

- [ ] **Step 1-3:** grep → 重写（`Stuff[T]` 用 PEP 695）→ `python3 -c "import vools.utils; print('OK')"`

### Task 7.16：顶层 __init__.py 与 __main__.py 注解重写

**Files:** `vools/__init__.py`、`vools/__main__.py`

- [ ] **Step 1: 重写 `__init__.py`**

将 `_lazy_modules: dict[str, str]`、`__getattr__(name: str) -> Any`、`__dir__() -> list` 等用内建泛型与 PEP 695；`from typing import Any` 保留。

- [ ] **Step 2: 重写 `__main__.py`**

`main() -> None`、argparse 类型用内建泛型。

- [ ] **Step 3: 验证**

Run: `cd /workspace && python3 -c "import vools; print(vools.__version__)" && python3 -m py_compile /workspace/vools/__init__.py /workspace/vools/__main__.py`
Expected: 版本号，无编译错误

### Task 7.17：提交阶段 7（按子包分批提交，避免大 diff）

- [ ] **Step 1: 分批提交**

逐子包：
```
git -C /workspace add vools/core && git -C /workspace commit -m "refactor(lite,core): modernize annotations to PEP 695/702/742 for 3.14"
git -C /workspace add vools/cache && git -C /workspace commit -m "refactor(lite,cache): modernize annotations to PEP 695"
# ... 依次对 crypto/curried/data/datetime/decorators/encoding/functional/oop/security/serialize/sys/task/utils
git -C /workspace add vools/__init__.py vools/__main__.py && git -C /workspace commit -m "refactor(lite,toplevel): modernize __init__/__main__ annotations"
```

---

## 阶段 8：全量验证与收尾

### Task 8.1：全量导入验证

- [ ] **Step 1: 导入主包与全部保留子包**

Run:
```
cd /workspace && python3 -c "
import vools
for sub in ['core','cache','crypto','curried','data','datetime','decorators','encoding','functional','oop','security','serialize','sys','task','utils']:
    __import__(f'vools.{sub}')
print('all OK', vools.__version__)
"
```
Expected: `all OK 0.4.9`（或新版本号）

- [ ] **Step 2: 验证常用 API 可用**

Run:
```
cd /workspace && python3 -c "
from vools import curry, memorize, Ops, Seq, iif, Box
@curry
def add(a, b): return a+b
assert add(2)(3) == 5
assert list(range(5) | Ops.map(lambda x: x*2)) == [0,2,4,6,8]
print('API OK')
"
```
Expected: `API OK`

### Task 8.2：确认零第三方依赖

- [ ] **Step 1: 扫描 vools/ 下所有 import**

Run:
```
cd /workspace && python3 - <<'EOF'
import ast, pathlib, sys, sysconfig
stdlib = set(sys.stdlib_module_names)  # 3.10+
third = set()
for p in pathlib.Path('vools').rglob('*.py'):
    tree = ast.parse(p.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split('.')[0]
                if top != 'vools' and top not in stdlib:
                    third.add((str(p), top))
        elif isinstance(n, ast.ImportFrom):
            if n.module is None: continue
            top = n.module.split('.')[0]
            if top != 'vools' and not n.level and top not in stdlib:
                third.add((str(p), top))
print('THIRD-PARTY:', third or 'NONE')
EOF
```
Expected: `THIRD-PARTY: NONE`

- [ ] **Step 2: 确认 pyproject 无第三方**

Run: `cd /workspace && python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print('deps:', d['project'].get('dependencies')); print('opt:', d['project'].get('optional-dependencies', {}))"`
Expected: `deps: []`，`opt: {}`

### Task 8.3：运行保留测试套件

- [ ] **Step 1: 用 unittest 运行（纯标准库）**

Run: `cd /workspace && python3 -m unittest discover -s tests -p 'test_*.py' 2>&1 | tail -15`
Expected: 全部通过（或仅剩与移除模块无关的失败，记录并修复）

- [ ] **Step 2: 若保留 pytest，运行 pytest**

Run: `cd /workspace && python3 -m pytest tests/ -q 2>&1 | tail -15`
Expected: 通过

### Task 8.4：最终提交与分支状态

- [ ] **Step 1: 确认工作区干净**

Run: `git -C /workspace status --short`
Expected: 空

- [ ] **Step 2: 查看分支提交历史**

Run: `git -C /workspace log --oneline main..vools-lite`
Expected: 阶段 1-7 的提交列表

---

## Self-Review 自检（计划作者已执行）

1. **Spec 覆盖**：
   - 移除 bridge/reactive/dll32 → 阶段 1.1 ✓
   - 移除全部第三方库 → 阶段 1.2/2.x/3.x/4.1/8.2 ✓（api/sql/xl/serialize 高级后端/fire/attrs/yaml/pandas/pkg_resources/msgpack/orjson/mkdocs 全覆盖）
   - 仅用标准库 → 阶段 4.1 + 8.2 验证 ✓
   - Python 3.14 特性 → 阶段 7（PEP 695/696/702/742/649）✓
   - 分支 `vools-lite` 基于 main → 阶段 0 ✓
   - 重写所有模块注解 → 阶段 7.1-7.16 覆盖全部保留子包 ✓

2. **占位符扫描**：无 TBD/TODO；每步含具体命令或代码片段。

3. **类型一致性**：`vools-lite` 分支名、`requires-python=">=3.14"`、`tomllib`、`importlib.metadata`、`TypeIs`、`@deprecated`、`@override`、PEP 695 `[T]` 语法在多 Task 间一致。

4. **已知风险/待执行时确认**：
   - 阶段 3 各 Task 的"删除调用点"可能牵连未列出的次要符号，执行时以 grep 实测为准。
   - `core/config.py` 的 yaml→tomllib 是"重写"而非"删除"，与"全部移除"略有出入——但 config 是 __main__ 依赖的核心，删 yaml 改 tomllib 是保留功能的最小改动；若用户坚持删除 config，需同步删 __main__ 的 `config` 命令与 __init__ 的 `ConfigManager` 导出（可作为备选）。
   - `sys/dll.py`、`sys/exe.py`、`sys/compile_cmd.py`、`sys/run_cmd.py` 未发现第三方依赖，保留；若执行时发现 ctypes 调用 DLL 的代码路径，需确认仅用标准库 `ctypes`（允许）。
   - `tests/` 部分文件去留需逐个 grep 确认（阶段 5 已注明）。
   - dev 工具（pytest/black/mypy）按"仅用标准库"应移除，测试改用 `unittest`；若用户希望保留 pytest 作为开发期可选，阶段 4.1 Step 2 与 8.3 需调整。
