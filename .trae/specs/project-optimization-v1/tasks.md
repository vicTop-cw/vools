# vools 项目全面优化 v1 - The Implementation Plan (Decomposed and Prioritized Task List)

## [/] Task 1: 调整 pytest 配置，让核心测试默认可运行
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 调整 `pyproject.toml` 中的 pytest ignore 列表
  - 默认运行 functional、decorators、data、curried、oop 等纯 Python 核心测试
  - 保留对 bridge、reactive/monitoring、dll32、xl 等需要外部资源的测试的 ignore（或用 marker 控制）
  - 确保 `__rust__`、`__persist__`、`__pycache__` 等缓存目录仍被忽略
  - 更新注释说明默认运行哪些测试、如何运行全部测试
- **Acceptance Criteria Addressed**: AC-1, AC-6
- **Test Requirements**:
  - `programmatic` TR-1.1: 执行 `pytest` 能运行至少 500+ 个测试用例
  - `programmatic` TR-1.2: 所有默认运行的测试 100% 通过
  - `programmatic` TR-1.3: `pytest tests/bridge/` 等子目录命令仍然可以正常运行
  - `human-judgement` TR-1.4: pyproject.toml 中的注释清晰说明默认测试范围
- **Notes**: 这是最高优先级，因为当前 `pytest` 几乎跑不到任何测试，严重影响开发体验

## [x] Task 2: 清理 py36_test 目录
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将 `py36_test/` 目录下的文件与 `tests/` 下的对应文件对比
  - 确认内容是否重复或已过时
  - 如果确认重复，删除整个 `py36_test/` 目录
  - 如有独特内容，迁移到 `tests/` 或 `tests/archive/` 对应位置
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: 项目根目录不再有 `py36_test/` 目录
  - `programmatic` TR-2.2: 原有的 Python 3.6 测试功能不丢失（通过嵌入式解释器测试覆盖）
- **Notes**: Python 3.6 测试已通过 `vools/dll32/_python32/` 嵌入式解释器进行，不需要单独的 py36_test 目录

## [x] Task 3: 迁移生产代码中的测试文件到 tests/
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将 `vools/data/test_qax.py` 迁移到 `tests/data/test_qax.py`
  - 确保迁移后的测试能正常运行
  - 检查 `vools/` 下是否还有其他 `test_*.py` 文件
  - 更新 `pyproject.toml` 的 setuptools 配置，确保测试文件不会被打包进发布包
- **Acceptance Criteria Addressed**: AC-3, AC-6
- **Test Requirements**:
  - `programmatic` TR-3.1: `vools/data/` 下不再有 `test_qax.py`
  - `programmatic` TR-3.2: `tests/data/test_qax.py` 能正常运行
  - `programmatic` TR-3.3: `vools/` 目录下搜索不到任何 `test_*.py` 文件
  - `programmatic` TR-3.4: 构建 wheel 包后检查不包含测试文件
- **Notes**: 测试文件放在生产代码目录会被打包进发布包，增加包体积

## [x] Task 4: 统一缓存装饰器实现
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 详细对比 `vools/cache/` 包与 `vools/decorators/cache.py` 的实现差异
  - 修复 `decorators/curry_delay.py` 中的导入（改为从 `vools.cache` 导入）
  - 搜索所有从 `decorators.cache` 导入的地方，统一改为从 `cache` 导入
  - 确认 `decorators/cache.py` 无其他依赖后，先添加 deprecated 警告，后续版本移除
  - 或直接移除 `decorators/cache.py`（如果确认无外部依赖）
  - 确保所有缓存相关测试通过
- **Acceptance Criteria Addressed**: AC-2, AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-4.1: `grep "from .*decorators.cache import"` 无结果
  - `programmatic` TR-4.2: `grep "from .*decorators\.cache import"` 无结果
  - `programmatic` TR-4.3: memorize/once/persist 相关测试全部通过
  - `programmatic` TR-4.4: curry_delay 功能正常（其内部使用了 memorize）
  - `human-judgement` TR-4.5: 如保留 deprecated 警告，信息清晰且不影响正常使用
- **Notes**: 这是架构一致性的关键修复，确保只有一套缓存实现

## [x] Task 5: 清理 tests/misc 目录
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 将 `tests/misc/` 下的调试脚本（debug_curry.py、compare_rxpy_vools.py 等）移动到 `scripts/` 目录
  - 将 .md 文档移动到 `docs/` 或相应的模块目录
  - 将 .txt 数据文件移动到 `tests/fixtures/` 或删除
  - 清理空的 misc/ 目录或保留说明
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-5.1: `tests/misc/` 下没有非测试文件
  - `programmatic` TR-5.2: `pytest` 不会收集到 misc 目录下的非测试文件
  - `human-judgement` TR-5.3: 移动后的脚本和文档放在合理的位置
- **Notes**: tests/ 目录应该只放测试文件，其他文件会干扰 pytest 收集

## [/] Task 6: 清理生产代码中的测试/调试代码
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 检查并清理 `vools/__init__.py` 末尾的演示/测试代码
  - 检查并清理 `decorators/rself.py` 末尾的测试代码
  - 扫描其他模块末尾的 `if __name__ == "__main__":` 测试块
  - 有价值的测试代码迁移到 `tests/` 对应目录
  - 纯调试用的代码直接删除
- **Acceptance Criteria Addressed**: AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-6.1: `vools/__init__.py` 中没有演示用的 print 和示例函数
  - `programmatic` TR-6.2: `decorators/rself.py` 末尾没有测试代码
  - `programmatic` TR-6.3: `import vools` 不会产生任何输出
  - `human-judgement` TR-6.4: 有价值的测试已迁移到 tests/ 对应位置
- **Notes**: 保持生产代码整洁，导入包时不应该有任何副作用

## [/] Task 7: 修复硬编码的用户特定路径
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 搜索 `vools/` 下所有硬编码的用户特定路径（`C:\Users\victo`、`/home/vic` 等）
  - 使用 `os.path.expanduser('~')` 或环境变量替代
  - 确保路径探测逻辑在不同机器上都能正常工作
  - 保持向后兼容（如果用户已配置特定路径，应保留配置能力）
- **Acceptance Criteria Addressed**: AC-4, AC-7
- **Test Requirements**:
  - `programmatic` TR-7.1: `grep "C:\\\\Users\\\\victo"` 在 vools/ 生产代码中无结果
  - `programmatic` TR-7.2: `grep "/home/vic"` 在 vools/ 生产代码中无结果
  - `programmatic` TR-7.3: bridge manager 的路径探测功能正常
  - `human-judgement` TR-7.4: 代码可读性良好，路径配置逻辑清晰
- **Notes**: 硬编码路径影响代码可移植性，是技术债务

## [x] Task 8: 整理 xl 模块测试
- **Priority**: medium
- **Depends On**: Task 1
- **Description**:
  - 检查 `tests/xl/` 下的所有文件
  - 将脚本式 demo 改写为标准 pytest 测试（添加 `test_` 函数和断言）
  - 性能测试文件（perf_*.py）移到 `tests/benchmarks/` 或独立 `benchmarks/` 目录
  - 确保 xl 测试可以通过 marker 控制是否运行（如 `windows_only`）
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-8.1: `pytest tests/xl/` 能发现并运行测试
  - `programmatic` TR-8.2: xl 核心功能测试通过
  - `human-judgement` TR-8.3: 测试用例有清晰的断言，不是只 print
- **Notes**: xl 模块依赖 libxl.dll，属于 Windows 特定功能，应用 marker 标记

## [x] Task 9: 统一测试风格（移除冗余 sys.path.insert）
- **Priority**: low
- **Depends On**: Task 1
- **Description**:
  - 扫描所有测试文件，移除不必要的 `sys.path.insert`
  - 确认 pytest 能自动处理路径（通过 pyproject.toml 的 testpaths 或 conftest.py）
  - 减少测试中的 print 语句，改用 pytest 断言
  - 保持测试文件风格一致
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-9.1: 核心测试目录下没有 `sys.path.insert`
  - `programmatic` TR-9.2: 所有测试仍然能正常运行
  - `human-judgement` TR-9.3: 测试代码简洁，没有冗余的路径处理
- **Notes**: 低优先级，主要是代码整洁度提升

## 任务依赖图
```
Task 1 (pytest 配置)
  └──> Task 8 (xl 测试整理)
  └──> Task 9 (测试风格统一)

Task 2 (py36_test 清理)  -- 独立
Task 3 (测试文件迁移)    -- 独立
Task 4 (缓存统一)        -- 独立
Task 5 (misc 清理)       -- 独立
Task 6 (生产代码清理)    -- 独立
Task 7 (硬编码路径修复)  -- 独立
```

大部分任务可以并行执行，只有 Task 8 和 Task 9 依赖 Task 1 的 pytest 配置调整。
