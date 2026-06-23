# Tasks

## Phase 1: Python 3.6 语法降级 ✅ 已完成

### 阶段 1.1: 环境准备与扫描
- [x] 1.1.1: 扫描项目所有 .py 文件，列出所有需要修改的语法点
- [x] 1.1.2: 创建备份分支 `git checkout -b py36-downgrade`
- [ ] 1.1.3: 安装 Python 3.6/3.7/3.8/3.9 多版本测试环境（如可行）

### 阶段 1.2: 类型注解语法降级
- [x] 1.2.1: 替换所有 `list[str]` → `List[str]`
- [x] 1.2.2: 替换所有 `dict[str, ...]` → `Dict[str, ...]`
- [x] 1.2.3: 替换所有 `set[str]` → `Set[str]`
- [x] 1.2.4: 替换所有 `tuple[str, ...]` → `Tuple[str, ...]`
- [x] 1.2.5: 替换所有 `int | str` / `str | None` → `Union[int, str]` / `Optional[str]`
- [x] 1.2.6: 统一 `Callable[[T], R]` 等泛型写法

### 阶段 1.3: 依赖清理
- [x] 1.3.1: 移除 `from __future__ import annotations`（如存在）
- [x] 1.3.2: 移除 `wrapt` 依赖，替换为纯 Python 实现
- [x] 1.3.3: 移除 `attrs` 依赖，替换为纯 Python 实现
- [x] 1.3.4: 更新 `pyproject.toml` 的 `requires-python = ">=3.6"`
- [x] 1.3.5: 更新 `classifiers` 添加 Python 3.6/3.7/3.8

### 阶段 1.4: 语法兼容性验证
- [x] 1.4.1: 用 Python 3.6 语法检查（`python -m py_compile`）
- [x] 1.4.2: 运行基础导入测试 `python -c "import vools; print(vools.__version__)"`
- [x] 1.4.3: 运行核心功能测试（crypto, encoding, seq, curried）

### 阶段 1.5: 构建与打包
- [x] 1.5.1: 构建 whl 包 `python -m build --wheel`
- [x] 1.5.2: 验证 whl 可通过 `zipfile + sys.path` 方式正常导入
- [x] 1.5.3: 提交 Phase 1 代码 `git add + commit` (commit: `4af3fc4`)

---

## Phase 2: Nim 性能优化 🔄 进行中

### 阶段 2.1: Nim 开发环境准备
- [x] 2.1.1: 验证 Nim 编译器可用 `nim --version`
- [x] 2.1.2: 创建 `nim_core/` 目录结构
- [x] 2.1.3: 编写 `build_nim.py` 编译脚本（如有）

### 阶段 2.2: Nim 核心模块开发
- [x] 2.2.1: 实现 `nim_core/vools_crypto.nim`（MD5/SHA1/SHA256/HMAC）✅
- [x] 2.2.2: 实现 `nim_core/vools_encoding.nim`（Base64/RLE）✅
- [x] 2.2.3: 实现 `nim_core/vools_seq.nim`（map/filter/reduce，**使用 Nim 泛型重构**）✅
- [x] 2.2.4: 实现 `nim_core/vools_datetime.nim`（日期计算）✅
- [x] 2.2.5: 实现 `nim_core/vools_curried.nim`（数学/统计/集合操作，使用泛型）✅

### 阶段 2.3: Python ctypes 桥接层
- [x] 2.3.1: 实现 `vools/_nim_loader.py`（DLL 检测与加载 + MinGW 运行时路径）✅
- [x] 2.3.2: 实现 `vools/_nim_crypto.py`（Nim + Python 回退）✅
- [x] 2.3.3: 实现 `vools/_nim_encoding.py`（Nim + Python 回退）✅
- [x] 2.3.4: 实现 `vools/_nim_seq.py`（Nim + Python 回退）✅
- [x] 2.3.5: 实现 `vools/_nim_datetime.py`（Nim + Python 回退）✅
- [x] 2.3.6: 实现 `vools/_nim_curried.py`（Nim + Python 回退）✅

### 阶段 2.4: 编译与集成
- [x] 2.4.1: 编译所有 Nim DLL（crypto/encoding/seq/datetime/curried）✅
- [x] 2.4.2: DLL 复制到 `vools/lib/` 目录（含 MinGW 运行时）✅
- [x] 2.4.3: 更新 `vools/__init__.py` 导入逻辑 + NIM_*_AVAILABLE 标志 ✅
- [x] 2.4.4: 更新 `pyproject.toml` 包含 Nim DLL 作为 package-data ✅
- [x] 2.4.5: 创建 `build_nim.py` 一键编译脚本 ✅

### 阶段 2.5: 性能验证
- [x] 2.5.1: 创建 `benchmark.py` Nim vs Python 性能基准 ✅
- [x] 2.5.2: 实测结果：datetime range 5x 加速；其他 cstring 互转开销 > 计算开销 ✅
- [x] 2.5.3: 验证回退机制：移除 DLL 后 vools 仍可正常导入和工作 ✅

### 阶段 2.6: 最终打包
- [x] 2.6.1: 打包含 Nim DLL + MinGW 运行时的 whl（5.19 MB）✅
- [x] 2.6.2: 打包纯 Python whl（不含 Nim DLL）— 已支持，DLL 缺失时自动回退 ✅
- [x] 2.6.3: 验证两种包均可正常使用 ✅
- [ ] 2.6.4: 提交 Phase 2 代码 `git add + commit`（待用户确认）

---

## 剩余任务优先级

### P0 - 阻塞性问题
1. **修复 MD5 bug**：非空输入通过 ctypes 调用 DLL 时输出错误
   - 独立测试 `test_md5.nim` 正确
   - 通过 ctypes 调用 DLL (`md5_hash("hello")`) 输出错误

### P1 - 核心功能
2. 实现 `datetime.nim` + `curried.nim`
3. 更新 `vools/__init__.py` 整合 Nim 桥接层
4. 更新 `pyproject.toml` 包含 Nim 构建步骤

### P2 - 验证
5. 性能基准测试
6. 回退机制验证

### P3 - 发布
7. 打包发布

---

## Task Dependencies

```
Phase 1: ✅ 完成 (commit 4af3fc4)

Phase 2:
  P0: MD5 Bug 修复 (2.2.1 修复)
         ↓
  P1: datetime.nim/curried.nim (2.2.4, 2.2.5) ←→ 2.4.3, 2.4.4 可并行
         ↓
  P2: 性能验证 (2.5.1 ~ 2.5.4)
         ↓
  P3: 打包发布 (2.6.1 ~ 2.6.4)
```
