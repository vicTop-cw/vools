# Changelog

All notable changes to this project will be documented in this file.

## [0.4.4] - 2026-07-02

### 🐛 兼容性修复

- **修复 attrs 旧版本兼容性问题** - `dataclass_compat` 模块兼容 attrs 17.4.0 等旧版本
  - 问题：`TypeError: attrib() got an unexpected keyword argument 'factory'`
  - 原因：attrs 19.2 以下版本不支持 `factory=` 关键字参数
  - 修复：
    1. 新增 `_detect_attr_capabilities()` 自动检测 attrs 版本支持的特性
    2. 旧版本 attrs 使用 `attr.Factory(callable)` 替代 `factory=` 参数
    3. 同时兼容 `auto_attribs` 和 `frozen` 参数在旧版本中的缺失

## [0.4.3] - 2026-06-29

### 🐛 紧急修复

- **修复 dll32 模块返回 None 的问题** - wheel 包中缺少 DLL 文件和 32 位 Python 运行时
  - 问题：`vb6plus.base64_encode_utf8('Hello')` 返回 None
  - 原因：`pyproject.toml` 配置错误，setuptools 把 `_python32/Lib/site-packages/` 当作 Python 子包发现，导致 DLL 和核心运行时文件未正确打包
  - 修复：
    1. 在 `packages.find` 中排除 `vools.dll32._python32` 和 `vools.dll32._dlls` 子包
    2. 在 `package-data` 中精确指定需要打包的 DLL 和 32 位 Python 运行时文件
    3. wheel 包大小从 63MB 精简到 19MB（仅包含必要的运行时文件）

- **修复 xl 模块无法导入** - wheel 包中缺少 `libxl.dll`
  - 添加 `xl/_dlls/*.dll` 到 `package-data` 配置

## [0.4.2] - 2026-06-29

**已撤回（yanked）** - 存在 wheel 打包问题，dll32 和 xl 模块无法正常工作

## [0.4.1] - 2026-06-28

- 未发布（存在 wheel 打包问题）

## [0.4.0] - 2026-06-28

### ✨ 新增功能

#### Table / QAX 数据集重写（重大更新）

- **Row 类重写** - 继承 `Seq` 并使用 `@rself` 装饰器，支持行级链式操作（map/filter/where/select/take/skip 等）
- **Column 类重写** - 继承 `Seq` 并使用 `@rself` 装饰器，支持列级链式操作，保留 sum/avg/min/max/count/distinct 等聚合方法
- **Table 类重写** - 继承 `Seq` 并使用 `@rself` 装饰器，复用 Seq 的 20+ 链式操作方法，所有原有 API 完全向后兼容
- **四种迭代方式** - `iter_rows()` / `iter_cols()` / `iter_cells_row_major()` / `iter_cells_col_major()`，支持按行、按列、先行后列、先列后行四种遍历视角
- **Qax 类（新增）** - 继承 `Table` 并使用 `@rself` 装饰器，提供 **60+ SqlCel QAX 风格 API**（PascalCase 命名）
  - 创建类：`QAX()`, `ArrayToQax()`, `FileToQax()`, `ExcelToQAX()`
  - 信息类：`QAXRows()`, `QAXCols()`, `QAXColNames()`, `QAXName()`, `SetQaxName()`
  - 访问类：`GetCell()`, `GetCell2()`, `GetRow()`, `GetCol()`, `GetCols()`
  - 修改类：`SetCell()`, `SetCell2()`, `DelRow()`, `DelCol()`, `NewRow()`, `AddCol()`, `InsertRow()`, `InsertCol()`
  - 数据操作：`QAXSelect()`, `QAXSort()`, `QAXDistinct()`, `QAXFilter()`, `QAXTop()`
  - 聚合类：`QAXSum()`, `QAXAvg()`, `QAXCount()`, `QAXMax()`, `QAXMin()`, `QaxGroup()`, `QAXCompute()`
  - 连接合并：`QaxJoin()`, `QAXMerge()`
  - 更新类：`QAXUpdate()`, `QAXReplace()`, `QAXClear()`
  - 字符串类：`QAXSubstr()`, `QAXSplit()`, `QAXConcat()`
  - 转换类：`QAXToArray()`, `QAXToFile()`, `showQax()`, `QAXToDictList()`
  - 列操作：`QAXColToDate()`, `QAXColToNum()`, `QAXColToStr()`, `SetColName()`, `SetOrdinal()`
- **`__from_parent__` 机制** - 所有子类（Row/Column/Table/Qax）实现类型自动转换，Seq 操作结果自动转回正确的子类类型

#### FreeBASIC 编译器集成

- **内置 FreeBASIC 编译器** - 开箱即用的 32/64 位 FreeBASIC 编译器（`compiler/` 目录），无需手动安装
- **9 个第三方 DLL 库** - 内置 SQLite3、libmysql、Cairo、SDL3(+image/mixer/ttf)、Scintilla、mCtrl 等常用库到 `libs/win64/` 目录
- **loader 扩展 API** - `get_fb_lib()`, `list_fb_libs()`, `FbLibraryLoader` 类等
- **Python 端 SQLite3 shim** - `freebasic.is_sqlite3_available()`, `freebasic.connect()` 等
- **.bas 封装模块**（`modules/`） - 三个简化封装层（`sqlite3_wrapper`, `cairo_wrapper`, `sdl3_wrapper`），统一以 `fb_` 前缀命名
- **编译参数注入** - `compile_and_run` 新增 `extra_includes` / `inc_paths` / `lib_paths` 参数
- **运行时 DLL 依赖解析** - 通过 `os.add_dll_directory` 自动解决第三方 DLL 的传递依赖

### 🔧 架构优化

- **统一继承体系** - Row/Column/Table/Qax 全部基于 Seq + @rself 架构，减少重复代码，提升可维护性
- **双向引用保持** - Row 和 Column 始终持有所属 Table 的引用，支持数据同步修改
- **向后兼容保证** - Table 所有公开 API 签名不变，现有代码零迁移成本

### 🐛 修复

- 修复 fbc 链接器在缺少 .a 导入库时的失败问题（已为所有内置 DLL 预生成 `lib<name>.a`）
- 修复 xl 测试文件路径设置问题，确保使用本地开发版本而非已安装版本

### 🔧 项目优化与清理 (v0.4.0 附带)

#### 测试组织规范化

- **调整 pytest 配置** - 默认运行 functional、decorators、data、curried、oop、core、serialize、task、datetime、utils、reactive 等核心测试
- **新增 `scripts/` 目录** - 存放调试、对比、探索等辅助脚本
- **新增 `docs/` 目录** - 存放技术文档和分析报告
- **清理 `tests/misc/`** - 将调试脚本移到 scripts/，文档移到 docs/
- **清理 `py36_test/`** - 删除重复测试文件

#### 架构一致性

- **统一缓存装饰器实现** - `vools/cache/` 为唯一官方实现，`decorators/cache.py` 改为 re-export + deprecated 警告
- **迁移生产代码测试** - `vools/data/test_qax.py` 迁移到 `tests/data/`
- **xl 测试标准化** - 33 个标准 pytest 测试

#### 代码质量提升

- **清理生产代码测试块** - 清理 19 个模块中的 `if __name__ == "__main__":` 测试/调试代码
- **移除冗余 sys.path.insert** - 88 个测试文件移除冗余路径设置
- **修复硬编码路径** - 17 处用户特定路径改为 `os.path.expanduser('~')`
- **消除 import 副作用** - `import vools` 不再产生任何输出

#### 文档完善

- **更新 data/README.md** - 添加 Row、Column、Qax 类的完整 API 文档

### 🔄 依赖变更

- **废弃 `vools.decorators.cache`** - 该模块改为 re-export，导入时会发出 DeprecationWarning，建议迁移到 `vools.cache`

### ✅ 测试

- **1000+ 核心测试** 默认运行，全部通过
- **向后兼容** - 公共 API 完全不变

## [0.3.0] - 2026-06-25

### ✨ 新增功能

- **编译器自动发现辅助包** - 新增 `vools.bridge` 子包的自动发现功能
  - 支持 27 种编程语言编译器/解释器自动探测
  - 多源路径发现：系统 PATH、常见安装路径、Windows 注册表
  - WSL 环境编译器自动发现（支持所有 WSL 发行版）
  - 通配符路径展开（如 `C:\Program Files\Java\jdk*\bin`）
  - 一键发现并配置：`discover_all()` / `auto_discover()`
  - 格式化发现报告：`get_discovery_report()`
  - 配置持久化：保存/加载编译器配置到 JSON 文件

### 🔧 核心模块

#### `vools.bridge.probe` - 编译器探测模块
- `probe_environment()` - 探测当前环境所有支持的编译器
- `probe_with_extra_paths()` - 带额外路径的探测
- `probe_all_wsl()` / `probe_wsl()` - WSL 环境探测
- `search_windows_registry()` - Windows 注册表搜索
- `expand_wildcard_paths()` - 通配符路径展开
- `list_wsl_distributions()` - 列出所有 WSL 发行版
- `print_report()` - 生成格式化报告
- `get_available_languages()` - 获取可用语言列表

#### `vools.bridge.manager` - 配置管理模块
- `BridgeManager.auto_discover()` - 自动发现并配置编译器
- `BridgeManager.save_config()` / `load_config()` - 配置持久化
- `BridgeManager.register()` / `unregister()` - 语言配置注册
- `BridgeManager.get_status()` / `is_available()` - 状态查询
- `BridgeManager.clear_cache()` - 清除缓存
- `LanguageCompilerHelper` - 语言编译器辅助类

#### `vools.bridge.auto_discovery` - 一键发现入口
- `discover_all()` - 发现本机和 WSL 所有编译器
- `discover_local()` - 仅发现本机编译器
- `discover_wsl()` - 仅发现 WSL 编译器
- `get_discovery_report()` - 获取格式化发现报告
- `configure_from_discovery()` - 从探测结果配置管理器

### 🐛 修复与优化

- 修复 Windows 环境下 `which` 命令缺失问题（改用 `shutil.which`）
- 修复 WSL 子进程输出编码问题（支持 UTF-8/GBK/Latin-1 多编码容错）
- 修复通配符路径未实际展开的问题
- 增强跨平台兼容性（Windows / Linux / WSL）

### 📝 支持的语言

Python, Nim, C, C++, C#, Java, Kotlin, Scala, Go, Rust, Ruby, PHP, Perl, Lua, Julia, R, Dart, Swift, Zig, TypeScript, JavaScript, Mojo, MoonBit, FreeBASIC, VBScript, PowerShell, Shell, 苍颉 (Cangjie)

### ✅ 测试

- 新增 35+ 个综合测试用例
- 覆盖 probe / manager / auto_discovery 三个模块
- 集成测试：发现 → 配置 → 保存 → 加载 完整流程
- Python 3.10 / 3.13 双版本验证通过
- Windows / WSL (Linux) 双平台验证通过
