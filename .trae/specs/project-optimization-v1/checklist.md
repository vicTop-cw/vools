# vools 项目全面优化 v1 - Verification Checklist

## 整体验证

- [x] 所有现有测试仍然通过（与优化前对比，通过率不下降）
- [x] 向后兼容性：公共 API 没有破坏性变更
- [x] Python 3.6 - 3.13 全版本兼容
- [x] 可以正常构建 sdist 和 wheel 包
- [x] `twine check` 验证通过

## Task 1: pytest 配置调整

- [x] `pytest` 命令默认能运行至少 500+ 个测试用例
- [x] 默认运行的测试 100% 通过
- [x] functional、decorators、data、curried、oop 等核心模块测试默认运行
- [x] bridge、dll32、xl、reactive/monitoring 等需要外部资源的测试默认不运行
- [x] `__rust__`、`__persist__`、`__pycache__` 等缓存目录被正确忽略
- [x] `pytest tests/bridge/` 等指定子目录的命令仍然正常工作
- [x] `pytest -m windows_only` 等 marker 过滤正常工作
- [x] pyproject.toml 中的注释清晰说明默认测试范围

## Task 2: py36_test 目录清理

- [x] 项目根目录不再有 `py36_test/` 目录
- [x] 原有的独特测试内容已迁移到合适位置（如确认有价值）
- [x] Python 3.6 兼容性测试功能不丢失（通过嵌入式解释器覆盖）
- [x] .gitignore 中如有相关配置已更新

## Task 3: 生产代码中的测试文件迁移

- [x] `vools/data/test_qax.py` 已迁移到 `tests/data/`
- [x] 迁移后的测试能正常运行
- [x] `vools/` 目录下搜索不到任何 `test_*.py` 文件
- [x] 构建 wheel 包后检查不包含测试文件
- [x] `vools/dll32/tests/` 已处理（迁移或明确保留的理由）

## Task 4: 缓存装饰器实现统一

- [x] 所有模块都从 `vools.cache` 导入缓存装饰器
- [x] `decorators/curry_delay.py` 中的导入已修正
- [x] 代码中不再有 `from .decorators.cache import` 或类似导入
- [x] `decorators/cache.py` 已移除或添加 deprecated 警告
- [x] memorize 功能测试全部通过
- [x] once 功能测试全部通过
- [x] persist 功能测试全部通过
- [x] curry_delay 功能正常（内部使用了 memorize）
- [x] 向后兼容：`vools.decorators.memorize` 等仍然可用

## Task 5: tests/misc 目录清理

- [x] `tests/misc/` 下没有非测试文件
- [x] 调试脚本已移动到 `scripts/` 或其他合适位置
- [x] .md 文档已移动到 `docs/` 或相应位置
- [x] 数据文件已移动到 `tests/fixtures/` 或删除
- [x] `pytest` 不会收集到 misc 目录下的非测试文件
- [x] 移动后的文件仍然可以正常使用（如需要）

## Task 6: 生产代码中的测试/调试代码清理

- [x] `vools/__init__.py` 末尾没有演示/测试代码
- [x] `decorators/rself.py` 末尾没有测试代码
- [x] `import vools` 不会产生任何输出
- [x] 有价值的测试代码已迁移到 `tests/` 对应位置
- [x] 其他模块中的 `if __name__ == "__main__":` 测试块已处理
- [x] 生产代码中没有遗留的 print 调试语句

## Task 7: 硬编码用户路径修复

- [x] `vools/` 生产代码中没有 `C:\Users\victo` 硬编码路径
- [x] `vools/` 生产代码中没有 `/home/vic` 硬编码路径
- [x] 使用 `os.path.expanduser('~')` 或环境变量替代
- [x] bridge manager 的路径探测功能正常
- [x] 保持向后兼容（用户自定义配置仍然有效）
- [x] 代码可读性良好，路径配置逻辑清晰

## Task 8: xl 模块测试整理

- [x] `pytest tests/xl/` 能发现并运行测试
- [x] xl 核心功能测试通过
- [x] 测试用例有清晰的断言（不是只 print）
- [x] 性能测试文件已移到 benchmarks/ 或其他合适位置
- [x] xl 测试使用了正确的 marker（如 `windows_only`）
- [x] 默认 pytest 运行不会尝试执行 xl 测试（除非指定）

## Task 9: 测试风格统一

- [x] 核心测试目录下没有 `sys.path.insert`
- [x] 所有测试仍然能正常运行
- [x] 测试代码简洁，没有冗余的路径处理
- [x] 测试风格基本一致（pytest 函数式为主）
- [x] 减少了不必要的 print 语句

## 发布前检查

- [ ] CHANGELOG 已更新（如果这次优化作为版本发布）
- [ ] 版本号已更新（如适用）
- [ ] 文档（README 等）已同步更新
- [ ] 所有验证检查点已完成
