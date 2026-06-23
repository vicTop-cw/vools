# Checklist

## Phase 1: Python 3.6 语法降级 ✅ 已完成 (commit 4af3fc4)

### 语法兼容性
- [ ] 所有 .py 文件无 `list[` 语法（需 `List[`）
- [ ] 所有 .py 文件无 `dict[` 语法（需 `Dict[`）
- [ ] 所有 .py 文件无 `set[` 语法（需 `Set[`）
- [ ] 所有 .py 文件无 `tuple[` 语法（需 `Tuple[`）
- [ ] 所有 .py 文件无 `int | str` / `str | None` 语法（需 `Union` / `Optional`）
- [ ] 无 `from __future__ import annotations` 语句
- [ ] 所有 `typing` 模块导入完整（List, Dict, Set, Tuple, Union, Optional, Callable, etc.）

### 依赖清理
- [ ] `pyproject.toml` 中 `requires-python = ">=3.6"`
- [ ] `pyproject.toml` 中移除 `wrapt` 依赖
- [ ] `pyproject.toml` 中移除 `attrs` 依赖
- [ ] `classifiers` 包含 `Programming Language :: Python :: 3.6`、`3.7`、`3.8`
- [ ] 代码中无 `import wrapt`
- [ ] 代码中无 `import attrs`

### 功能验证
- [ ] `python -c "import vools"` 无报错
- [ ] `python -c "from vools import Seq; print(Seq(range(10)).filter(lambda x: x % 2 == 0).collect())"` 输出 `[0, 2, 4, 6, 8]`
- [ ] `python -c "from vools import md5, sha256; print(len(sha256('test')))"` 输出 `64`
- [ ] `python -c "from vools import Encoder, Decoder; print(Decoder(Encoder('hello').base64().data).base64().data)"` 输出 `hello`
- [ ] `python -c "from vools import curry; @curry def add(a, b): return a + b; print(add(1)(2))"` 输出 `3`

### 构建与打包
- [ ] `python -m build --wheel --outdir dist` 成功生成 whl
- [ ] whl 文件名包含 `py3-none-any` 或正确平台标签
- [ ] whl 可通过 `zipfile + sys.path` 方式正常 import
- [ ] whl 解压后目录可独立使用

---

## Phase 2: Nim 性能优化

### Nim 环境
- [x] `nim --version` 输出正常（Nim 2.0+）
- [x] `nim_core/` 目录存在且包含 .nim 源文件
- [x] `nim_core/` 包含 `vools_crypto.nim`、`vools_encoding.nim`、`vools_seq.nim`
- [x] DLL 存在于 `vools/lib/`：`vools_crypto.dll`、`vools_encoding.dll`、`vools_seq.dll`

### Nim 编译产物
- [x] `vools/lib/vools_crypto.dll`（Windows）
- [x] `vools/lib/vools_encoding.dll`（Windows）
- [x] `vools/lib/vools_seq.dll`（Windows）
- [x] DLL 可通过 `ctypes.CDLL()` 加载
- [x] DLL 导出的函数符号正确（MD5 验证通过）

### Python 桥接层
- [x] `vools/_nim_loader.py` 存在
- [x] `vools/_nim_crypto.py` 实现 Nim + Python 回退（MD5/SHA1 验证通过）
- [x] `vools/_nim_encoding.py` 实现 Nim + Python 回退
- [x] `vools/_nim_seq.py` 实现 Nim + Python 回退
- [ ] Nim 不可用时自动回退 Python，功能一致

### 待修复 Bug
- [x] **SHA256 非空输入输出正确**（✅ 空字符串和非空字符串均正确）
- [x] **SHA1 非空输入输出正确**（✅ 空字符串和非空字符串均正确）
- [ ] **MD5 非空输入通过 ctypes 调用输出错误**（⚠️ 独立测试正确，ctypes 调用错误）

### 性能基准
- [ ] Nim MD5 比 Python hashlib 快 5x 以上（100KB 数据）
- [ ] Nim SHA256 比 Python hashlib 快 3x 以上（100KB 数据）
- [ ] Nim Zlib 压缩比 Python zlib 快 2x 以上（1MB 数据）
- [ ] Nim seq.map 比 Python 内置快 2x 以上（10000 元素）

### 最终打包
- [ ] 含 Nim DLL 的 whl 大小合理（< 2MB）
- [ ] 纯 Python whl 可独立使用（无 Nim DLL 时自动回退）
- [ ] 两种 whl 在 Python 3.6 ~ 3.13 上均可正常导入
