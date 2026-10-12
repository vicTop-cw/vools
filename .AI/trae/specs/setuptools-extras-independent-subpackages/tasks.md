# vools 子包独立分发与 extras_require 整改任务

## [x] Task 1: 解耦 reactive 对 vools 功能模块的依赖
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 扫描 `vools/reactive/**/*.py` 中所有 `from vools...` 与 `from ...xxx` 引用。
  - `vools/reactive/core/observable.py` 当前依赖 `vools.decorators.curry` / `lazy`；将这两个装饰器的最小实现内联到 `vools/reactive/_compat.py` 或复制到 `vools/reactive/core/_compat.py`，并替换引用。
  - 确保 reactive 内部不再引用 `vools.decorators`、`vools.functional`、`vools.data`、`vools.oop`、`vools.task`、`vools.utils`。
- **Acceptance Criteria**: reactive 解耦验证场景通过；`grep` 无禁用引用。
- **Test Requirements**:
  - `python -c "from vools.reactive.core.observable import Observable; print(Observable.of(1,2,3).to_list().to_blocking())` 在仅安装 `vools-rx` 的虚拟环境中成功。

## [x] Task 2: 解耦 bridges 对 vools 功能模块的依赖
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 扫描 `vools/bridge/**/*.py` 中所有 `from vools...` 与 `from ...xxx` 引用。
  - 确认 bridge 仅引用 `vools.core.*` 兼容层；如存在对 `vools.decorators` 等引用，需迁移到 bridge 内部实现或 `vools.core`。
  - 将 `vools/core/dataclass_compat.py`、`vools/core/asyncio_compat.py`、`vools/core/inspect_compat.py` 等被 bridge 使用的兼容层评估是否需要复制到 `vools/bridge/core/compat/`。
- **Acceptance Criteria**: bridges 解耦验证场景通过；`grep` 无禁用引用（`vools.core` 除外）。
- **Test Requirements**:
  - `python -c "import vools.bridge; print(vools.bridge.manager.list_languages())"` 在仅安装 `vools-bridges` 的虚拟环境中成功。

## [x] Task 3: 迁移 vools/bridge 到 bridges/ 子项目
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 创建 `bridges/vools/bridge/` 目录结构。
  - 将 `vools/bridge/*` 全部迁移到 `bridges/vools/bridge/*`。
  - 删除原 `vools/bridge/` 目录。
  - 在 `bridges/` 下创建 `pyproject.toml`：name=`vools-bridges`，version 与 `vools.__version__` 保持一致（动态读取或硬编码），packages 包含 `vools.bridge`。
- **Acceptance Criteria**: 独立构建成功；独立安装后 `import vools.bridge` 成功。
- **Test Requirements**:
  - `cd bridges && python -m build` 退出码为 0。
  - `pip install bridges/dist/vools_bridges-*.whl` 后 `import vools.bridge` 成功。

## [x] Task 4: 迁移 vools/reactive 到 rx/ 子项目
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 创建 `rx/vools/reactive/` 目录结构。
  - 将 `vools/reactive/*` 全部迁移到 `rx/vools/reactive/*`。
  - 删除原 `vools/reactive/` 目录。
  - 在 `rx/` 下创建 `pyproject.toml`：name=`vools-rx`，version 与 `vools.__version__` 保持一致。
- **Acceptance Criteria**: 独立构建成功；独立安装后 `import vools.reactive` 成功。
- **Test Requirements**:
  - `cd rx && python -m build` 退出码为 0。
  - `pip install rx/dist/vools_rx-*.whl` 后 `import vools.reactive` 成功。

## [x] Task 5: 更新 vools 核心包的 pyproject.toml
- **Priority**: P0
- **Depends On**: Task 3, Task 4
- **Description**:
  - 在根目录 `pyproject.toml` 的 `[project.optional-dependencies]` 中新增：
    - `rx = ["vools-rx=={version}"]`
    - `bridges = ["vools-bridges=={version}"]`
    - `all = ["vools-rx=={version}", "vools-bridges=={version}"]`
  - 在 `[tool.setuptools.packages.find]` 中排除 `vools.bridge*`、`vools.reactive*`。
  - 可选：删除现有的 `nim`、`freebasic`、`mojo`、`rust` 等不再属于核心包的 optional-dependencies（或保留为空列表作为占位）。
- **Acceptance Criteria**: extras_require 语义正确场景通过。
- **Test Requirements**:
  - `python -m build` 生成的 wheel 中不包含 `vools/bridge` 和 `vools/reactive`。
  - `pip install dist/vools-*.whl` 后 `import vools` 成功但 `import vools.bridge` 失败。

## [x] Task 6: 调整 vools/__init__.py 对子包的导入逻辑
- **Priority**: P0
- **Depends On**: Task 5
- **Description**:
  - 移除 `vools/__init__.py` 中 `try...from . import bridge...BRIDGE_AVAILABLE` 的硬导入代码。
  - 保留 `BRIDGE_AVAILABLE`、`REACTIVE_AVAILABLE` 变量，默认设为 `False`。
  - 在 `__getattr__` 中增加对 `bridge`、`reactive` 的延迟转发：如果子包已安装则动态导入，否则抛出 `AttributeError`。
  - 确保 `import vools` 本身不再因为子包缺失而失败。
- **Acceptance Criteria**: 核心 API 不变场景、子包缺失时优雅降级场景通过。
- **Test Requirements**:
  - `python -c "import vools; print(vools.Seq, vools.curry)"` 成功。
  - `python -c "import vools; vools.bridge"` 抛出 `AttributeError`（仅安装核心时）。

## [x] Task 7: 调整测试与 CI 路径
- **Priority**: P1
- **Depends On**: Task 3, Task 4, Task 6
- **Description**:
  - 将 `tests/bridge` 迁移到 `bridges/tests/` 或调整 pytest 路径，使其作为 `vools-bridges` 的测试运行。
  - 将 `tests/reactive` 迁移到 `rx/tests/` 或调整 pytest 路径。
  - 更新根目录 `pyproject.toml` 中 pytest 的 `--ignore` 路径，移除对已迁移目录的忽略。
  - 更新 CI / GitHub Actions（如有）以支持多包构建与测试。
- **Acceptance Criteria**: 核心测试、bridge 测试、reactive 测试均可在各自目录独立运行并通过。
- **Test Requirements**:
  - `pytest tests/core tests/data tests/functional ...` 通过。
  - `cd bridges && pytest tests/` 通过。
  - `cd rx && pytest tests/` 通过。

## [ ] Task 8: 验证 extras 安装组合
- **Priority**: P0
- **Depends On**: Task 3, Task 4, Task 5, Task 6
- **Description**:
  - 在干净虚拟环境中分别验证：
    1. `pip install dist/vools-*.whl`
    2. `pip install "dist/vools-*.whl[rx]"`
    3. `pip install "dist/vools-*.whl[bridges]"`
    4. `pip install "dist/vools-*.whl[all]"`
  - 每种情况都检查 `import vools.bridge` 和 `import vools.reactive` 是否按预期可用/不可用。
- **Acceptance Criteria**: 基础安装不含子包场景、all 安装包含子包场景通过。
- **Test Requirements**:
  - 每个组合都执行导入断言脚本并退出码为 0。

## [x] Task 9: 修复已发现的相关错误
- **Priority**: P1
- **Depends On**: None
- **Description**:
  - 在本次整改过程中，修复当前已确认的真 bug：
    - `vools/data/itor.py` 条件插队死锁与 `send(None, jump_when=...)` 处理错误（已在上一回合修复，需在本任务中确认状态）。
    - `vools/__init__.py` 中的 subprocess 编码补丁保持幂等。
  - 清理不再需要的测试副作用文件（如 `tests/decorators/__persist__/*.json` 的意外修改）。
- **Acceptance Criteria**: `tests/data/test_itor.py` 全部通过；核心测试无回归。
- **Test Requirements**:
  - `pytest tests/data/test_itor.py -q` 退出码 0。
  - `pytest tests/core tests/functional tests/oop tests/reactive tests/serialize tests/task -q` 退出码 0。

# Task Dependencies
- Task 3 depends on Task 2
- Task 4 depends on Task 1
- Task 5 depends on Task 3, Task 4
- Task 6 depends on Task 5
- Task 7 depends on Task 3, Task 4, Task 6
- Task 8 depends on Task 3, Task 4, Task 5, Task 6
- Task 9 可与其他任务并行，但需在最终验证前完成
