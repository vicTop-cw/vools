# 交接摘要 — vools 核心包体积优化与发布

> 生成时间: 2026-08-10
> 前一阶段: 已将 `dll32`, `xl`, `bridge`, `reactive` 独立为子包 (`vools-dll32`, `vools-xl`, `vools-bridges`, `vools-rx`)
> 本阶段目标: 清理重复二进制文件 → 测试通过 → push → 发布到 PyPI → 本地全部重新安装后所有 API 可用

---

## 一、已完成

### 1.1 清理重复二进制文件

**问题**: `vools/oop/lib/` 和 `vools/lib/` 下存在重复的 Nim 编译产物 (`.dll` / `.so`)，额外占用约 1 MB。

**操作**:
- 将 `vools/oop/lib/` 下的文件合并到 `vools/lib/` 对应平台目录:
  - `vools/oop/lib/libstdc++-6.dll` → `vools/lib/windows/libstdc++-6.dll`
  - `vools/oop/lib/libgcc_s_seh-1.dll` → `vools/lib/windows/libgcc_s_seh-1.dll`
  - `vools/oop/lib/libwinpthread-1.dll` → `vools/lib/windows/libwinpthread-1.dll`
  - `vools/oop/lib/linux/*.so` → `vools/lib/linux/` (已存在则跳过)
- 删除整个 `vools/oop/lib/` 目录

**效果**: 核心包源码体积从 ~7 MB → ~6 MB (消除 1 MB 重复)，无重复二进制文件。

**最终 `vools/lib/` 结构**:
```
vools/lib/
  windows/
    libstdc++-6.dll       (2.14 MB)
    libgcc_s_seh-1.dll    (0.11 MB)
    libwinpthread-1.dll   (0.05 MB)
    vools_seq.dll         (0.24 MB)
    vools_curried.dll     (0.23 MB)
    vools_encoding.dll    (0.20 MB)
    vools_datetime.dll    (0.17 MB)
    vools_crypto.dll      (0.15 MB)
  linux/
    libvools_bridge_safe_eval.so  (0.38 MB)
    libvools_seq.so               (0.17 MB)
    libvools_curried.so           (0.16 MB)
    libvools_datetime.so          (0.11 MB)
    libvools_encoding.so          (0.10 MB)
    libvools_crypto.so            (0.10 MB)
```

### 1.2 已安装本地开发环境

所有 5 个包已通过 `pip install -e` 以 editable 模式安装:
```
vools           0.7.2  (核心，路径: e:\IDEProjects\AI\vools)
vools-bridges   0.7.2  (路径: e:\IDEProjects\AI\vools\bridges)
vools-rx        0.7.2  (路径: e:\IDEProjects\AI\vools\rx)
vools-dll32     0.7.2  (路径: e:\IDEProjects\AI\vools\dll32)
vools-xl        0.7.2  (路径: e:\IDEProjects\AI\vools\xl)
```

注意: 当前 Python 环境的 pip 升级到了 26.2.1，需要 `--no-build-isolation` 才能用 editable 模式安装 (因为隔离环境无法导入 `setuptools.build_meta`)。

### 1.3 测试结果

运行 `python -m pytest tests/ -v --tb=short -m "not integration and not windows_only" -q`:

```
832 passed, 2 failed, 2 skipped, 1 deselected, 17 errors
```

---

## 二、待处理

### 2.1 测试失败 (2 个 FAILED)

#### 失败 1: `test_curry_class_method` (tests/decorators/test_decorators.py:85)

```python
@classmethod
@curry
def class_add(cls, a, b):
    return a + b

assert Calculator.class_add(1)(2) == 3  # 失败
```

**现象**: `curry` 装饰器在 `@classmethod` 包裹的方法上，参数收集后 `is_ready=False`，没有自动执行。`CurriedMethod.__call__` 中 `self.required_params` 包含了 `cls` 参数名，导致始终认为参数未收集完。

**判断**: 这是 **已有问题**，与本次 lib 清理无关。`curry` 装饰器内层 `curry_class` 的 `CurriedMethod` 没有处理 `@classmethod` 的 `cls` 参数自动填充。

**修复方向**: 在 `vools/decorators/curry_decorator.py` 的 `curry_class` (第 155 行) 中，检测到被装饰的是 `classmethod` 时，`required_params` 应排除第一个参数 (cls)。或者修改测试，将装饰器顺序改为 `@curry` 在 `@classmethod` 之前。

#### 失败 2: `test_none_with_msgpack_backend` (tests/serialize/test_serialize.py)

```
ValueError: Backend 'msgpack' is not available. Install msgpack: pip install msgpack
```

**原因**: 环境未安装 `msgpack`。这不是 bug，是缺少可选依赖。

**修复**: `pip install msgpack` 或给该测试加 `skipIf`。

### 2.2 测试错误 (17 个 ERROR)

全部来自 `tests/data/test_itor_nim.py::TestNimItor`，原因是 `vools/data/itor.dll` (Nim 编译产物) 不存在。

```python
# 文件: tests/data/test_itor_nim.py:11
assert use_nim(True), "Nim DLL not available"
```

`use_nim()` 在 `vools/data/itor.py:823` 中尝试加载 `vools/data/itor_nim.py` → `NimItor._load_dll()` 查找 `vools/data/itor.dll`，找不到则返回 False。

**判断**: 这是已有问题，与本次 lib 清理无关。这些测试需要 Nim 编译器编译 `itor.nim` 生成 `itor.dll`。

**修复方向**: 给 `TestNimItor` 加 `pytest.mark.skipif` 或 `pytest.mark.nim` 标记，CI 中跳过。

### 2.3 待执行步骤

按顺序执行:

1. **修复测试** (可选，看是否接受当前状态):
   - `test_curry_class_method`: 修复 `curry_class` 对 `@classmethod` 的支持，或直接改测试
   - `test_none_with_msgpack_backend`: 安装 msgpack 或加 skip
   - `test_itor_nim.py`: 加 `pytest.mark.nim` 并在 CI 中排除

2. **构建所有包**:
   ```bash
   # 在项目根目录
   python -m build
   cd bridges && python -m build && cd ..
   cd rx && python -m build && cd ..
   cd dll32 && python -m build && cd ..
   cd xl && python -m build && cd ..
   ```

3. **Push 代码**:
   ```bash
   git add -A
   git commit -m "cleanup: remove duplicate lib binaries from oop/lib/, consolidate into vools/lib/"
   git push
   ```

4. **发布到 PyPI** (两种方式):

   **方式 A — GitHub Actions (推荐)**:
   - 触发 `publish.yml` workflow (在 GitHub Release 页面发布新 release 或手动 dispatch)
   - 注意: PyPI 有频率限制，之前 vools-rx 因 429 失败，可能需要等限制窗口过去

   **方式 B — 本地手动上传**:
   ```bash
   pip install twine
   python -m twine upload dist/*0.7.2*
   python -m twine upload bridges/dist/*0.7.2*
   python -m twine upload rx/dist/*0.7.2*
   python -m twine upload dll32/dist/*0.7.2*
   python -m twine upload xl/dist/*0.7.2*
   ```

5. **本地验证全部 API 可用**:
   ```bash
   pip uninstall vools vools-bridges vools-rx vools-dll32 vools-xl -y
   pip install vools[all]==0.7.2
   python -c "
   import vools
   print(vools.__version__)
   # 核心 API
   from vools import memorize, curry, Seq, Pipe, Box, stuff
   # 延迟加载子包
   import vools.bridge; print('bridge OK')
   import vools.reactive; print('reactive OK')
   import vools.dll32; print('dll32 OK')
   import vools.xl; print('xl OK')
   print('All APIs OK')
   "
   ```

---

## 三、关键文件清单

### 本次修改的文件
| 文件 | 变更 | 说明 |
|------|------|------|
| `vools/oop/lib/` | **删除** | 整个目录删除，内容合并到 `vools/lib/` |
| `vools/lib/windows/` | **新增文件** | 新增 `libstdc++-6.dll`, `libgcc_s_seh-1.dll`, `libwinpthread-1.dll` |
| `vools/lib/linux/` | **新增文件** | 新增 `libvools_seq.so` 等 5 个 .so 文件 |

### 之前已修改的关键文件 (本会话早期)
| 文件 | 用途 |
|------|------|
| `vools/__init__.py` | 核心入口，`DLL32_AVAILABLE`/`XL_AVAILABLE` 标志，延迟导入 |
| `pyproject.toml` | 核心包配置，排除 dll32/xl/bridge/reactive，extras 定义 |
| `dll32/pyproject.toml` | vools-dll32 子包配置 |
| `xl/pyproject.toml` | vools-xl 子包配置 |
| `bridges/pyproject.toml` | vools-bridges 子包配置 |
| `rx/pyproject.toml` | vools-rx 子包配置 |
| `vools/data/table.py` | `read_excel`/`write_excel` 中 xl 缺失时的友好提示 |
| `.github/workflows/publish.yml` | 5 包子包并行发布 |
| `.github/workflows/ci.yml` | CI 测试矩阵含 dll32/xl 测试 |

---

## 四、当前项目包结构

```
vools/                          # 核心包 (vools)
├── vools/
│   ├── __init__.py             # 命名空间入口 + 延迟加载
│   ├── lib/                    # 二进制动态库 (4.31 MB)
│   │   ├── windows/            # Windows .dll
│   │   └── linux/              # Linux .so
│   ├── core/                   # 基础类/异常/配置
│   ├── decorators/             # 装饰器 (curry, overload, memorize...)
│   ├── functional/             # 函数式工具 (Pipe, Seq, Box, placeholder...)
│   ├── data/                   # 数据结构 (Table, Seq, Itor, VList, VText...)
│   ├── datetime/               # 日期时间 (VDate, utils...)
│   ├── oop/                    # OOP 扩展 (Selector, Mixer...)
│   ├── concurrent/             # 并发工具
│   ├── sql/                    # SQL 构建器
│   ├── serialize/              # 序列化
│   ├── task/                   # 任务调度
│   ├── security/               # 安全 (safe_eval)
│   ├── crypto/                 # 加密 (md5, sha256, hmac...)
│   ├── encoding/               # 编码 (base64, zlib, gzip...)
│   ├── sys/                    # 系统工具 (DLL 调用, cmd...)
│   ├── cache/                  # 缓存 (memorize, once, persist...)
│   ├── curried/                # 预柯里化函数
│   ├── api/                    # CLI 入口
│   └── utils/                  # 通用工具 (stuff, hoder...)
│
├── bridges/                    # 子包: vools-bridges
│   └── vools/bridge/           # 多语言桥接 (Rust, Nim, Go, Java...)
│
├── rx/                         # 子包: vools-rx
│   └── vools/reactive/         # 响应式编程 (Observable, Subject...)
│
├── dll32/                      # 子包: vools-dll32
│   └── vools/dll32/            # 32位 DLL/COM 互操作
│
├── xl/                         # 子包: vools-xl
│   └── vools/xl/               # Excel 操作
│
├── tests/                      # 核心包测试
├── pyproject.toml              # 核心包构建配置
└── .github/workflows/          # CI/CD
    ├── ci.yml
    └── publish.yml
```

### Extras 依赖关系
```
pip install vools[bridges]  → vools + vools-bridges
pip install vools[rx]       → vools + vools-rx
pip install vools[dll32]    → vools + vools-dll32
pip install vools[xl]       → vools + vools-xl
pip install vools[all]      → vools + 全部 4 个子包
```

---

## 五、环境信息

- OS: Windows
- Python: 3.10.11 (路径: `C:\Users\victo\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe`)
- pip: 26.2.1 (注意: 安装 editable 包需要 `--no-build-isolation`)
- 项目路径: `e:\IDEProjects\AI\vools`
- 当前分支: 需要 `git status` 确认
- PyPI: 已配置 Trusted Publishing (OIDC)，GitHub Actions 可自动发布