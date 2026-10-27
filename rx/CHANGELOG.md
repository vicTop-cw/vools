# Changelog — vools-rx

本文件记录 `vools-rx` 的变更。版本号遵循语义化版本。

> **统一版本线**：vools 生态（`vools` / `vools-bridges` / `vools-actus` /
> `vools-rhop` / `vools-rx` / `vools-dll32` / `vools-pyk` / `vools-xl`）
> 自 0.9.0 起**版本号对齐**，同一版本号代表互相兼容的一组。

## [0.9.0] - 2026-10-27

vools-rx 统一并入 0.9.0 版本线。

### 🔧 变更

- **版本对齐**：本包版本号对齐到 0.9.0（此前为 0.7.6），与 vools 生态其余包一致。
- **依赖下限抬齐**：`vools` 依赖下限由 `vools>=0.7.1` 提升到 `vools>=0.9.0`，
  确保安装时拿到与本版配套的核心实现，而不是更早的 0.7.x/0.8.x。

### ✅ 验证

- wheel `twine check` 通过
- 干净目录 `pip install` 后导入正常、CLI（若有）可用
- vools 核心同版本 0.9.0 全量测试 691 passed（本包自身用例见其 tests/）
