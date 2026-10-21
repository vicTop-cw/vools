# Round 5 (2026-10-18, post-reboot)

## 完成的 bug 修复

### BUG-85 (FIXED, commit 573d0fb, RED-GREEN proven)
- ZeroDivisionError in `benchmark_parse/generate/to_html/full_pipeline/report` and `memoize_cmd.benchmark` when `iterations=0`
- 修法：所有 benchmark 函数入口加 `if iterations <= 0: raise ValueError(...)`
- RED-GREEN：去掉守卫 → 3 测试 ZeroDivisionError；恢复 → 8 通过

### BUG-86 (FIXED, commit 83fd468)
- `extract_metadata` 改用 `parse_yaml` 后 date 值从 str 变为 datetime.date 对象
- 修法：新增 `_normalize_metadata` 递归归一化（datetime.date/datetime → isoformat）
- 回归锁：test_metadata_date_stays_string, test_metadata_nested_datetime_normalized

### BUG-87 (FIXED, commit 410a66d, RED-GREEN proven)
- `_yaml_parse_with_pyyaml` 把 PyYAML 的 None 值强制转为空字符串（注释声称"与简单解析器一致"但实际相反）
- 空/注释-only 输入时 PyYAML 返回 None，函数透传违反 Dict 返回契约
- 修法：移除 None→'' 转换；`result is None` 或非 dict 返回 `{}`；`parse_yaml` 空文本直接返回 `{}`
- 回归锁：test_metadata_empty_frontmatter_returns_dict, test_metadata_null_value_preserved, test_parse_yaml_empty_returns_dict

## 测试状态
- md 测试套件：274 passed
- 全局：~850 passed, 7 failed（全部在 tests/test_sys_dll.py，其他 agent 假设 vools.sys.dll 是模块但实际是函数）
- 账本：BUG-80 保留 OPEN（pyk py3.6 lazy loading，刻意不修）

## 协作
- 其他 agent 在本轮提交了 `94f9037 fix(bridges): 修补 perl/ruby/php args_json 单引号字面量代码注入`
- 未触碰其他 agent WIP（actus/, bridges/, vools/md/generator.py/parser.py/html.py/__init__.py 等）