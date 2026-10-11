# vools Python 3.6 降级 + Nim 性能优化 Spec

## Why

vools 当前依赖 Python 3.9+，但生产环境要求 Python 3.6 兼容，且部分核心模块（加密、编码、数据处理）有显著性能优化空间。通过 Nim 语言重写底层核心，可获得 5-10x 性能提升，同时保持 Python 3.6+ 全版本兼容。

## What Changes

分两阶段实施：

### Phase 1: Python 3.6 语法降级
- 将所有 `list[str]` → `List[str]`
- 将所有 `dict[str, ...]` → `Dict[str, ...]`
- 将所有 `int | str` → `Union[int, str]`
- 将所有 `Optional[str]` 兼容写法统一
- 去掉 `from __future__ import annotations`（3.6 无需）
- 替换 `wrapt` / `attrs` 依赖为自实现或直接移除
- 更新 `pyproject.toml` 的 `requires-python = ">=3.6"`
- 确保 Python 3.6/3.7/3.8/3.9/3.10/3.11/3.12/3.13 全部可用

### Phase 2: Nim 性能优化
- 新增 `nim_core/` 目录，存放 Nim 源码
- 编译为 Windows DLL（`.pyd`），通过 `ctypes` 调用
- Python 层实现自动检测：Nim DLL 存在用 Nim，不存在回退 Python
- 支持的 Nim 加速模块：
  - `crypto`（MD5/SHA1/SHA256/HMAC）
  - `encoding`（Base64/Zlib/GZip/Lzma）
  - `seq_core`（map/filter/reduce/sort）
  - `datetime`（日期计算）
  - `curried`（数学/集合运算）

## Impact

- **影响的文件**：`vools/` 下所有 `.py` 文件、`pyproject.toml`
- **新增文件**：`nim_core/`（Nim 源码）、`_nim_loader.py`（加载器）
- **兼容性**：Python 3.6 ~ 3.13 全覆盖
- **性能**：加密/压缩/大数据处理场景 5-10x 加速
- **BREAKING**：去除 `wrapt`/`attrs` 依赖，相关高级特性移除

## ADDED Requirements

### Requirement: Nim DLL 加载器
系统 SHALL 提供 `_nim_loader.py`，实现：
- 首次导入时检测 Nim DLL 是否存在
- 存在则通过 `ctypes` 加载并缓存函数引用
- 不存在则静默回退到纯 Python 实现
- 提供统一调用接口，对上层透明

#### Scenario: Nim DLL 存在
- **WHEN** 导入 `vools.crypto` 且 `vools_nim.pyd` 存在于包目录
- **THEN** 自动使用 Nim 实现的哈希函数，性能提升 5-10x

#### Scenario: Nim DLL 不存在
- **WHEN** 导入 `vools.crypto` 且 `vools_nim.pyd` 不存在
- **THEN** 自动使用纯 Python 实现，功能完全一致

### Requirement: Nim 编译脚本
系统 SHALL 提供 `build_nim.py`，实现：
- 调用 `nim c --app:lib --out:build/lib.vools_nim.pyd nim_core/*.nim`
- 编译产物放入 `vools/lib/` 目录
- Windows 平台自动处理 `.pyd` 后缀

## MODIFIED Requirements

### Requirement: pyproject.toml 兼容性
**原始**：要求 `requires-python = ">=3.9"`
**修改为**：`requires-python = ">=3.6"`
- 移除 `wrapt` / `attrs` 硬性依赖
- 更新 `classifiers` 支持 Python 3.6/3.7/3.8

### Requirement: 类型注解语法
**原始**：使用 Python 3.9+ 类型标注（`list[int]`, `X | Y`）
**修改为**：统一使用 `typing` 模块写法（`List[int]`, `Union[X, Y]`, `Optional[X]`）
- 保持 Python 3.6 ~ 3.13 全部兼容
- `from __future__ import annotations` 移除

## REMOVED Requirements

### Requirement: wrapt 依赖的高级特性
**原因**：`wrapt` 库不支持 Python 3.6 的某些边缘场景，且在纯 Python 实现中非必需
**迁移**：相关高级装饰器功能保留 Python 实现，移除对 `wrapt` 的依赖

### Requirement: attrs 依赖的高级特性
**原因**：减少外部依赖，纯 Python 可实现等价功能
**迁移**：相关 dataclass 兼容功能保留 Python 实现，移除 `attrs` 依赖

## Phase 依赖关系

```
Phase 1 (语法降级)
    │
    └─ 完成并验证后 ──→ Phase 2 (Nim 优化)
                            │
                            ├── nim_core/ 源码开发
                            ├── Python ctypes 桥接
                            └── 混合性能验证
```

## 验收标准

1. Python 3.6 环境能正常 `import vools`
2. Python 3.6 ~ 3.13 全部通过基础功能测试
3. Nim DLL 存在时性能测试提升 5x 以上
4. Nim DLL 不存在时功能完全回退到 Python 实现
5. whl 包大小不显著增加（纯 Python 约 500KB）

## 当前进度

### Phase 1: Python 3.6 语法降级 ✅ 已完成
- **Commit**: `4af3fc4 refactor: Python 3.6 语法降级 - 类型注解和依赖清理`
- 所有类型注解已降级为 Python 3.6 兼容写法
- `wrapt`/`attrs` 依赖已移除并用纯 Python 实现替代
- `pyproject.toml` 已更新 `requires-python = ">=3.6"`

### Phase 2: Nim 性能优化 🔄 进行中

#### 已完成
- ✅ `nim_core/vools_crypto.nim` - SHA1/SHA256 验证通过，MD5 独立测试正确（ctypes 调用有问题）
- ✅ `nim_core/vools_encoding.nim` - Base64/RLE 已编译
- ✅ `nim_core/vools_seq.nim` - map/filter/reduce 已编译
- ✅ `vools/_nim_loader.py` - DLL 检测与加载
- ✅ `vools/_nim_crypto.py` - Nim + Python 回退
- ✅ `vools/_nim_encoding.py` - Nim + Python 回退
- ✅ `vools/_nim_seq.py` - Nim + Python 回退

#### 待完成
- ⚠️ **MD5 bug**: 非空输入通过 ctypes 调用时输出错误
- ⏳ `nim_core/datetime.nim` - 日期计算
- ⏳ `nim_core/curried.nim` - 数学/集合运算
- ⏳ 更新 `vools/__init__.py` 整合 Nim 桥接层
- ⏳ 更新 `pyproject.toml` 包含 Nim 构建步骤
- ⏳ 性能基准测试
- ⏳ 最终打包
