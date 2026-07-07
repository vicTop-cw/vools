# Checklist - vools 性能跃迁计划（修订版）

## 阶段 1: 基础设施验证

- [ ] `vools/decorators/bridge_decorator.py` 文件存在且可导入
- [ ] `BridgeRegistry` 单例可正常实例化
- [ ] `is_available('nim')` / `is_available('rust')` 等返回布尔值
- [ ] `get_bridge(lang, symbol)` 可正常调用（桥接不存在时返回 None）
- [ ] `@bridge` 装饰器不修改原函数 `__name__`、`__doc__`
- [ ] `benchmark/bridge_benchmark.py` 可正常运行（无 import 错误）
- [ ] `get_all_suites()` 返回包含 6 个套件名称的列表

## 阶段 2: Tier 1 Nim 验证

### serialize.codec
- [ ] `vools/bridge/nim/serialize.nim` 源码存在
- [ ] `vools/bridge/nim/serialize_shim.py` 存在且可导入
- [ ] Windows: `vools/lib/serialize.dll` 存在（或在 `lib/nim/` 下）
- [ ] Linux: `vools/lib/linux/serialize.so` 存在（或在 `lib/nim/` 下）
- [ ] `pickle_encode` 函数存在且可调用
- [ ] `pickle_decode` 函数存在且可调用
- [ ] 在无 .dll/.so 环境下，`pickle_encode` 回退到纯 Python 实现
- [ ] 在无 .dll/.so 环境下，`pickle_decode` 回退到纯 Python 实现
- [ ] 速度提升 ≥5x（通过 benchmark 测量）

### security.hash
- [ ] `vools/bridge/nim/hash.nim` 源码存在
- [ ] `vools/bridge/nim/hash_shim.py` 存在且可导入
- [ ] `sha256_hex` 函数存在且返回值与 hashlib 一致
- [ ] `md5_hex` 函数存在且返回值与 hashlib 一致
- [ ] 回退机制正常（无桥接库时使用纯 Python）
- [ ] 速度提升 ≥3x（通过 benchmark 测量）

### data.seq Base64
- [ ] `vools/bridge/nim/base64.nim` 源码存在
- [ ] `vools/bridge/nim/base64_shim.py` 存在且可导入
- [ ] `base64_encode` 返回值与 base64.b64encode 一致
- [ ] `base64_decode` 返回值与 base64.b64decode 一致
- [ ] 速度提升 ≥3x（通过 benchmark 测量）

## 阶段 3: Tier 2 Nim/Rust 验证

### serialize.json
- [ ] `vools/bridge/nim/json.nim` 源码存在
- [ ] `vools/bridge/nim/json_shim.py` 存在且可导入
- [ ] `dumps` / `loads` 返回值与 json 模块一致
- [ ] 速度提升 ≥2x（通过 benchmark 测量）

### cache.sigcache（循环导入风险）
- [ ] `vools/bridge/nim/sigcache.nim` 源码存在
- [ ] `vools/bridge/nim/sigcache_shim.py` 存在且通过独立 shim 中转
- [ ] `sigcache.py` 中无直接 `from vools.bridge` 导入
- [ ] `hash_signature` 回退机制正常
- [ ] 速度提升 ≥3x（通过 benchmark 测量）

## 阶段 4: Tier 3 平台验证

### sys.env PowerShell/Shell
- [ ] `vools/bridge/powershell/get_env.ps1` 存在
- [ ] `vools/bridge/shell/get_env.sh` 存在
- [ ] Windows: PowerShell 版 `get_env` 返回正确的环境变量值
- [ ] Linux: Shell 版 `get_env` 返回正确的环境变量值
- [ ] 平台自动检测功能正常

### data.seq compress/decompress
- [ ] `vools/bridge/nim/compress.nim` 源码存在
- [ ] `vools/bridge/nim/compress_shim.py` 存在且可导入
- [ ] `compress` / `decompress` 返回值与 zlib 一致
- [ ] 速度提升 ≥3x（通过 benchmark 测量）

## 阶段 5: Rust 验证

### security.safe_eval
- [ ] `vools/bridge/rust/safe_eval/src/main.rs` 源码存在
- [ ] Rust 编译产物存在（.pyd / .so）
- [ ] `safe_eval_shim.py` 存在且无循环导入（不引用 vools 子包）
- [ ] 超时控制功能正常
- [ ] 恶意代码注入防护测试通过（`__import__('os').system('rm -rf')` 应被拒绝）

## 阶段 6: 分发与通用

- [ ] `vools/lib/` 下 .dll 文件存在（或在 `lib/nim/` 下）
- [ ] `vools/lib/linux/` 下 .so 文件存在（或在 `lib/nim/` 下）
- [ ] 未安装桥接库时，纯 Python 实现完全正常工作（零破坏性）
- [ ] Python 3.6 和 3.13 两个版本均测试通过
- [ ] 无循环导入问题（通过 `python -c "import vools"` 验证）
- [ ] 所有优化函数保持原有 API 不变（函数签名未变）
- [ ] changelog 记录了本次性能跃迁版本
- [ ] 代码变更已 commit 并 push 到仓库
