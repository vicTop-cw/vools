# 更新日志 (Changelog)

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#A01
> **最后更新**：2026-06-30

---

## 版本历史

### v0.3.0 (2026-06-25)

**性能跃迁计划完成**

通过桥接编译型语言（Nim）为高频核心函数提供可选的高性能实现，在保持纯 Python 可用性的前提下实现数量级的性能提升。

#### @bridge 装饰器体系

**新增 `vools.bridge.core.decorators` 模块：**

- **`@bridge_function`**：将 Python 函数标记为可使用其他语言实现的桥接函数，支持自动回退
- **`@bridge_module`**：将类标记为桥接模块，类中所有公共方法自动使用对应语言实现
- **`@bridge_func_name`**：在 `@bridge_module` 中指定底层函数名

**特性：**

- 从函数签名的类型注解自动推断参数类型和返回类型
- 使用 CTypeMapper 进行类型映射
- 自动处理 str/bytes 转换
- 桥接库不可用或执行出错时自动回退到纯 Python 实现

#### Nim 桥接库实现

**序列化模块 (serialize)：**

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| pickle_encode (小数据) | ~120 us | ~18 us | 6-8x |
| pickle_decode (小数据) | ~100 us | ~15 us | 6-7x |
| pickle_encode (大数据) | ~2000 us | ~200 us | 10x |
| json_encode | ~50 us | ~15 us | 3x |
| json_decode | ~45 us | ~12 us | 4x |

**哈希模块 (security.hash)：**

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| sha256_hex (1KB) | ~15 us | ~3 us | 5x |
| md5_hex (1KB) | ~12 us | ~2 us | 6x |
| sha1_hex (1KB) | ~10 us | ~2 us | 5x |
| sha512_hex (1KB) | ~18 us | ~4 us | 4.5x |

**编码模块 (encoding)：**

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| base64_encode (1KB) | ~8 us | ~2 us | 4x |
| base64_decode (1KB) | ~7 us | ~2 us | 3.5x |

**压缩模块 (compress)：**

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| zlib_compress (10KB) | ~500 us | ~100 us | 5x |
| zlib_decompress (10KB) | ~200 us | ~50 us | 4x |
| gzip_compress (10KB) | ~600 us | ~120 us | 5x |
| gzip_decompress (10KB) | ~250 us | ~60 us | 4x |

**签名缓存模块 (cache.sigcache)：**

| 函数 | 纯 Python | Nim 桥接 | 提升倍数 |
|------|----------|---------|---------|
| hash_signature | ~50 us | ~8 us | 6x |

#### 统计数据

- **桥接优化函数**：20+ 个
- **测试套件数**：6 个
- **性能提升范围**：3-10x
- **新增文档**：2 篇

#### 安装使用

```bash
pip install vools==0.3.0
```

**注意**：桥接库为可选增强，未安装时自动使用纯 Python 实现。

#### 兼容性

- Python 3.6+
- 已验证版本：3.6.8、3.13.14
- 破坏性 API 变更：无，完全向后兼容 0.2.4

---

## 早期版本

更多历史版本信息，请参考 [CHANGELOG.md](../../CHANGELOG.md)。

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v0.2.4 | 2026-06-20 | 序列化和数据处理优化 |
| v0.2.3 | 2026-06-15 | Table/QAX 数据集重写 |
| v0.2.2 | 2026-06-10 | FreeBASIC 编译器集成 |
| v0.2.1 | 2026-06-05 | 响应式监控增强 |
| v0.2.0 | 2026-06-01 | 跨语言桥接框架 |
