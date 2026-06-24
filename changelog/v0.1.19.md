# Changelog v0.1.19

> 发布日期：2026-06-22

## 📝 概述

vools 0.1.19 是一次重大的文档和类型注解完善版本，补充了约 400 个 API 的 docstring 和类型注解，同时进行了项目结构清理和 CI 改进。

---

## ✨ 主要更新

### 1. API 文档与类型注解完善（约 400 个 API）

#### 数据结构模块 `vools/data/`
- **seq.py**: SeqBase 和 Seq 类的所有公开方法补充 docstring + 类型注解（~47 个 API）
- **vlist.py**: VList 和 ListLikeMeta 类补充 docstring + 类型注解（~30 个 API）
- **vtext.py**: VText 类补充 docstring + 类型注解（~15 个 API）

#### 函数式编程模块 `vools/functional/`
- **box.py**: box 装饰器、Box 类、CallableDescriptor 补充完整文档（~15 个 API）
- **pipe_ops.py**: P 管道操作符类所有方法补充类型注解（~60 个 API）
- **funcs.py**: for_、foreach、build、build_text 等函数补充文档（~5 个 API）

#### 响应式编程模块 `vools/reactive/`
- **observable.py**: Observable 核心方法 + PipeBuilder 所有操作符代理方法（~100+ 个 API）
- **monitoring/**: 事件数据类（KeyData/MouseData/ClipData/FileData/FolderData）补充文档（~90 个 API）

#### 装饰器模块 `vools/decorators/`
- **curry_delay.py**: DelayCurried 类所有公开方法补充文档（~20 个 API）
- **selector.py**: Selector、Overloads 类补充文档（~10 个 API）
- **curry_core.py**: curry 函数和相关类补充文档（~10 个 API）

#### 日期时间模块 `vools/datetime/`
- **vdate_class.py**: VDate 类所有自定义方法补充文档（~32 个 API）
- **__init__.py**: 新增 VDate 导出

#### 其他模块
- **oop/mixer.py**: Mixer、Mixer_、attr_Enum 补充文档（~10 个 API）
- **utils/stuff.py**: Stuff 装饰器相关方法补充类型注解（~5 个 API）
- **recorder/gui.py**: GUI 相关方法补充文档

### 2. 项目结构清理

删除临时目录和文件：
- `Temp/` 目录（30+ 个临时脚本和备份文件）
- `debug/` 目录（10+ 个调试脚本）
- `db/` 目录（任务数据库文件）
- `_plan_writer.py`
- `requirements.txt`（合并到 pyproject.toml）
- `setup.py`（合并到 pyproject.toml）

### 3. 打包配置改进

**pyproject.toml**:
- 统一打包配置，删除 setup.py 和 requirements.txt
- 明确指定 `packages = ["vools"]`，排除非发布目录
- 升级 `build-system.requires` 到 `setuptools>=68`
- 更新 Python 版本要求：`requires-python = ">=3.9"`
- 添加 `Typing :: Typed` classifier

### 4. CI 工作流改进

**.github/workflows/ci.yml**:
- 测试矩阵从 `["3.11","3.12","3.13"]` 改为 `["3.9","3.10","3.11","3.12"]`
- 用 `-m "not integration and not windows_only"` 替代长串 `--ignore` 参数
- 新增 `type-check` job（mypy）
- coverage job 加上 `--cov-fail-under=60`

### 5. Guide 文档更新

更新 6 个 guide 文档：
- `guide/README.md`: 修正 Python 版本，更新模块概览
- `guide/core.md`: 完整重写，删除错误 API 引用
- `guide/functional.md`: 新增 curried 模块、pipe/compose、数学运算等
- `guide/reactive.md`: 精简结构，添加监控 Windows-only 提示
- `guide/extras.md`: 新增序列化章节，统一到 vools.serialize
- `guide/vic-classes.md`: 彻底重写，用真实 API 替换废弃内容

---

## 🐛 修复的问题

1. **curry_delay.py**: 修复 `Parameter` 类未导入导致的 `NameError`
2. **datetime/__init__.py**: 修复 `VDate` 未导出导致的 `ImportError`
3. **test_clipboard_direct.py**: 修复顶层代码在导入时执行的问题

---

## 📊 统计

| 类别 | 变更 |
|------|------|
| 新增 docstring | ~400 个 API |
| 新增类型注解 | ~400 个 API |
| 删除文件 | ~50 个临时文件 |
| 修改文件 | ~60 个源文件 |
| 代码行数 | +5660 / -13257 |
| 文档覆盖率 | 32.2% → 70%+ |

---

## 🔧 使用方式

```bash
# 安装
pip install vools==0.1.19

# 升级
pip install --upgrade vools
```

---

## 📄 许可证

Apache 2.0 License
