# Tasks - vools 性能跃迁计划（修订版）

## 阶段 1: 基础设施（已完成，待验证）

- [ ] Task 1.1: `@bridge` 装饰器验证
  - [ ] SubTask 1.1.1: 确认 `vools/decorators/bridge_decorator.py` 存在且语法正确
  - [ ] SubTask 1.1.2: 确认 BridgeRegistry 单例、is_available()、get_bridge() 方法
  - [ ] SubTask 1.1.3: 验证三种执行路径：桥接可用 / 不可用 / 异常

- [ ] Task 1.2: 基准测试框架验证
  - [ ] SubTask 1.2.1: 运行 `python benchmark/bridge_benchmark.py` 确认无报错
  - [ ] SubTask 1.2.2: 确认 6 个测试套件可被正确加载（serialize, hash, base64, json, compress, sigcache）

## 阶段 2: Tier 1 Nim 优化（源码已就绪，待编译验证）

- [ ] Task 2.1: `serialize.codec` 序列化 Nim 优化
  - [ ] SubTask 2.1.1: 确认 `vools/bridge/nim/serialize.nim` 源码存在
  - [ ] SubTask 2.1.2: 编译 serialize.nim → serialize.dll / serialize.so（需 gcc）
  - [ ] SubTask 2.1.3: 确认 Python shim `vools/bridge/nim/serialize_shim.py` 存在
  - [ ] SubTask 2.1.4: 验证 `pickle_encode` 和 `pickle_decode` 回退机制正常

- [ ] Task 2.2: `security.hash` 哈希 Nim 优化
  - [ ] SubTask 2.2.1: 确认 `vools/bridge/nim/hash.nim` 源码存在
  - [ ] SubTask 2.2.2: 编译 hash.nim → hash.dll / hash.so（需 gcc）
  - [ ] SubTask 2.2.3: 确认 Python shim 存在
  - [ ] SubTask 2.2.4: 验证 sha256_hex / md5_hex 回退机制正常

- [ ] Task 2.3: `data.seq` Base64 Nim 优化
  - [ ] SubTask 2.3.1: 确认 `vools/bridge/nim/base64.nim` 源码存在
  - [ ] SubTask 2.3.2: 编译 base64.nim → base64.dll / base64.so
  - [ ] SubTask 2.3.3: 确认 Python shim 存在
  - [ ] SubTask 2.3.4: 验证 base64_encode / base64_decode 回退机制正常

## 阶段 3: Tier 2 Nim/Rust 优化

- [ ] Task 3.1: `serialize.json` JSON Nim 优化
  - [ ] SubTask 3.1.1: 确认 `vools/bridge/nim/json.nim` 源码存在
  - [ ] SubTask 3.1.2: 编译 json.nim → json.dll / json.so
  - [ ] SubTask 3.1.3: 确认 Python shim 存在
  - [ ] SubTask 3.1.4: 验证 dumps / loads 回退机制正常

- [ ] Task 3.2: `cache.sigcache` 签名哈希 Nim 优化（**高循环导入风险**）
  - [ ] SubTask 3.2.1: 分析 sigcache.py 当前实现，确认无直接引用桥接模块
  - [ ] SubTask 3.2.2: 确认 `vools/bridge/nim/sigcache.nim` 源码存在
  - [ ] SubTask 3.2.3: 通过独立 shim 中转（不得直接在 sigcache.py 中 import）
  - [ ] SubTask 3.2.4: 验证 hash_signature 回退机制正常

## 阶段 4: Tier 3 平台特定优化

- [ ] Task 4.1: `sys.env` PowerShell/Shell 优化
  - [ ] SubTask 4.1.1: 确认 `vools/bridge/powershell/get_env.ps1` 存在
  - [ ] SubTask 4.1.2: 确认 `vools/bridge/shell/get_env.sh` 存在
  - [ ] SubTask 4.1.3: 验证 Windows PowerShell 版返回环境变量
  - [ ] SubTask 4.1.4: 验证 Linux Shell 版返回环境变量

- [ ] Task 4.2: `data.seq` compress/decompress Nim 优化
  - [ ] SubTask 4.2.1: 确认 `vools/bridge/nim/compress.nim` 源码存在
  - [ ] SubTask 4.2.2: 编译 compress.nim → compress.dll / compress.so
  - [ ] SubTask 4.2.3: 验证 compress / decompress 回退机制正常

## 阶段 5: Rust 安全沙箱

- [ ] Task 5.1: `security.safe_eval` Rust VM
  - [ ] SubTask 5.1.1: 确认 `vools/bridge/rust/safe_eval/src/main.rs` 存在
  - [ ] SubTask 5.1.2: 确认 Rust 栈式 VM 通过 shim 间接调用（无循环导入）
  - [ ] SubTask 5.1.3: 验证超时控制功能
  - [ ] SubTask 5.1.4: 验证恶意代码注入防护

## 阶段 6: 验证与分发

- [ ] Task 6.1: 性能基准测试
  - [ ] SubTask 6.1.1: 运行所有 6 个测试套件的基准测试
  - [ ] SubTask 6.1.2: 记录每个函数的实际速度提升倍数
  - [ ] SubTask 6.1.3: 确认提升达到声明指标（≥2x 或内存≥20%）

- [ ] Task 6.2: 分发验证
  - [ ] SubTask 6.2.1: 确认 `vools/lib/` 下 .dll 文件存在
  - [ ] SubTask 6.2.2: 确认 `vools/lib/linux/` 下 .so 文件存在
  - [ ] SubTask 6.2.3: 纯 Python 回退机制在无桥接库时正常工作

## Task Dependencies

- Task 2.1 ~ 2.3 依赖 gcc 编译器环境
- Task 3.2 必须在 Task 2 完成后进行（避免循环导入冲突）
- Task 6.1 依赖 Task 1 ~ 5 所有编译结果
