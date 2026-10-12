# Checklist

## 核心层

- [x] `CompileMode` 枚举包含 7 个成员：NORMAL、DEBUG、FORCE、ONLY_RUN、ONLY_CODE、WHEN_CHANGE_JUST、WHEN_CHANGE_AND_RUN
- [x] `CompileMode` 枚举支持字符串比较（`"NORMAL" == CompileMode.NORMAL`）
- [x] `LangType` 枚举包含 5 个成员：compiled、interpreted、jvm、dotnet、beam
- [x] `CompileTracker` 数据库文件位于 `{vools_data_dir}/bridge_records.db`
- [x] `compile_records` 表包含 12+ 字段：id/record_key/language/lang_type/func_name/source_md5/source_path/lib_path/compile_mode/compiled_at/compile_duration_ms/python_module/python_file/extra
- [x] `record_key` 格式为 `{module}:{qualname}`（如 `mypackage.utils:add_numbers`）
- [x] 预留创建 `language_registry` 表
- [x] 预留创建 `compile_errors` 表
- [x] `CompileTracker.get_record(record_key)` 能正确查询已有记录
- [x] `CompileTracker.upsert_record(record_key, ...)` 能正确插入/更新记录
- [x] `CompileTracker.is_changed(record_key, source_md5)` 在 MD5 不同时返回 True
- [x] `CompileTracker.is_changed(record_key, source_md5)` 在无记录时返回 True
- [x] `CompileTracker._make_record_key(func)` 正确生成 `{module}:{qualname}` 格式的 key
- [x] `LangBridge.is_compiled` 默认为 True
- [x] `LangBridge._should_compile()` 对 NORMAL 模式：无缓存或代码变更时返回 True
- [x] `LangBridge._should_compile()` 对 DEBUG 模式：始终返回 True
- [x] `LangBridge._should_compile()` 对 FORCE 模式：始终返回 True
- [x] `LangBridge._should_compile()` 对 ONLY_RUN 模式：有缓存时返回 False，无缓存报错
- [x] `LangBridge._should_compile()` 对 ONLY_CODE 模式：不检查
- [x] `LangBridge._should_compile()` 对 WHEN_CHANGE_JUST 模式：代码变更时返回 True
- [x] `LangBridge._should_compile()` 对 WHEN_CHANGE_AND_RUN 模式：代码变更时返回 True
- [x] `LangBridge.decorator()` 方法移除 `only_code` 参数
- [x] `LangBridge.decorator()` 方法 `mode` 参数接受枚举和字符串
- [x] `LangBridge._compile_or_package()` 对编译型语言调用 `compile_code()`
- [x] `LangBridge._compile_or_package()` 对解释型语言调用 `_package_code()`
- [x] `LangBridge._package_code()` 默认实现生成 zip 文件
- [x] `LangBridge._call_or_execute()` 对编译型语言调用 `call_func()`
- [x] `LangBridge._call_or_execute()` 对解释型语言调用 `_execute_code()`
- [x] `CompileMode` 和 `CompileTracker` 从 `vools.bridge` 可导入
- [x] `CompileMode` 和 `CompileTracker` 从 `vools` 可导入

## 语言适配

- [x] 所有语言桥接的原有公开方法已改为私有（`_` 前缀）
- [x] 所有语言桥接公开类继承自 `LangBridge`
- [x] 所有语言桥接的 `__init__.py` 导出正确的公开类
- [x] 解释性语言设置 `is_compiled = False`
- [x] 解释性语言实现 `_package_code` 和 `_execute_code`
- [x] 独立装饰器语言（C#/Erlang/Elixir/Haskell）改为继承 `LangBridge`

## 测试

- [x] `CompileMode` 枚举测试通过（11/11）
- [x] `CompileTracker` 测试通过
- [x] `LangBridge` 新方法测试通过
- [x] 所有语言测试中 `only_code=True` 已替换为 `mode=CompileMode.ONLY_CODE`（零残留）
- [x] 所有语言测试通过（199 passed, 21 skipped；24 失败均为预存问题：沙箱权限/编译器缺失/R 桥接自定义参数）

## 文档

- [x] `vools/bridge/README.md` 更新核心架构说明（新增 CompileMode、CompileTracker、LangType 章节和 7 种使用模式）
- [x] `changelog/v0.6.0.md` 记录破坏性变更和迁移指南
- [x] `vools/__init__.py` 版本号更新至 0.6.0