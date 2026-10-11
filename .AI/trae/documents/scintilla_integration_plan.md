# Scintilla 控件集成到 FreeBASIC 桥接计划

## 一、现状分析

### 1.1 源端（VFB Scintilla 控件）
位置：`E:\VFB599\VisualFreeBasic599\Control\Scintilla\`

| 文件 | 说明 | 行数/大小 |
|---|---|---|
| `modScintilla.bi` | Scintilla 核心头文件，含 941 个 SCI_* 消息常量 | ~1300 行 |
| `modSciLexer.bi` | 词法分析器头文件，含 1539 个 SCLEX_* 常量 | ~2000 行 |
| `ClsScintilla.inc` | OOP 封装类（Class_Scintilla），封装常用属性/方法 | ~500+ 行 |
| `ClsScintilla_e.inc` | 事件封装 | - |
| `Scintilla64.dll` | 64 位 Scintilla 控件 DLL | - |
| `Scintilla32.dll` | 32 位 Scintilla 控件 DLL | - |
| `libscintilla64.a` | 64 位导入库 | - |
| `libscintilla32.a` | 32 位导入库 | - |
| `ProScintilla.dll` | VFB 增强版 Scintilla（含多国语言等） | - |
| `Languages.txt` | 多国语言配置 | - |

### 1.2 目标端（vools FreeBASIC 桥接）
位置：`e:\IDEProjects\AI\vools\vools\bridge\freebasic\`

**已有基础**：
- `libs/win64/gui/Scintilla.dll` + `libScintilla.a`（DLL 已有但无头文件）
- `manifest.json` 中 Scintilla 条目 `header: ""`（空的，未配置）
- 已有的模块模式：`modules/{name}_wrapper.bas`（sqlite3/cairo/sdl3 均有）
- loader 支持第三方 DLL 加载（get_fb_lib / list_fb_libs）

**缺失部分**：
- ❌ Scintilla 头文件（.bi）未放入 inc 目录
- ❌ Scintilla 封装模块（wrapper .bas）不存在
- ❌ manifest.json 中 header 路径未配置
- ❌ modules `__init__.py` 未注册 scintilla 的 inc_paths

---

## 二、集成目标

将 VFB 的 Scintilla 控件资源整合成 FreeBASIC 桥接可用的 API，分为三层：

### 2.1 底层：头文件层（C API）
- 将 `modScintilla.bi` + `modSciLexer.bi` 放入 `libs/win64/gui/inc/scintilla/`
- 用户可 `#include "scintilla/modScintilla.bi"` 使用完整 SCI_* 消息常量
- 直接通过 SendMessage / DirectFunction 与控件通信

### 2.2 中层：OOP 类封装（Class_Scintilla）
- 将 `ClsScintilla.inc` 放入 `libs/win64/gui/inc/scintilla/`
- 提供面向对象的 Scintilla 控件封装（属性/方法调用）
- 适合 VFB 用户迁移

### 2.3 上层：简化 wrapper（fb_scintilla_*）
- 创建 `modules/scintilla_wrapper.bas`
- 以 `fb_` 前缀导出常用函数，供 @fbc 装饰器直接使用
- 覆盖：文本操作、选择、折叠、书签、查找、样式等核心功能

---

## 三、文件变更清单

### 3.1 新增文件

| 目标路径 | 来源/说明 |
|---|---|
| `libs/win64/gui/inc/scintilla/modScintilla.bi` | 从 VFB 复制，核心消息常量 |
| `libs/win64/gui/inc/scintilla/modSciLexer.bi` | 从 VFB 复制，词法分析器常量 |
| `libs/win64/gui/inc/scintilla/ClsScintilla.inc` | 从 VFB 复制，OOP 封装类 |
| `libs/win64/gui/inc/scintilla/ClsScintilla_e.inc` | 从 VFB 复制，事件封装 |
| `modules/scintilla_wrapper.bas` | 新建，fb_ 前缀简化 API |

### 3.2 修改文件

| 文件 | 修改内容 |
|---|---|
| `libs/win64/manifest.json` | Scintilla 条目补全 header 路径 |
| `modules/__init__.py` | 注册 scintilla_wrapper，提供 inc_paths |

---

## 四、实施步骤

### 步骤 1：拷贝头文件到 inc 目录
- 从 VFB 复制 4 个 .bi/.inc 文件到 `libs/win64/gui/inc/scintilla/`
- 验证文件编码（VFB 文件可能是 GBK，需检查是否需要转码）

### 步骤 2：更新 manifest.json
- 将 Scintilla 的 `header` 字段从 `""` 改为 `"gui/inc/scintilla/modScintilla.bi"`
- 更新 `dependencies`（Scintilla 无外部依赖，保持空数组）

### 步骤 3：创建 scintilla_wrapper.bas
- 参考 sqlite3_wrapper.bas 的模式
- 提供常用功能的 fb_ 前缀函数：
  - 文本读写：`fb_scintilla_get_text`, `fb_scintilla_set_text`, `fb_scintilla_append_text`
  - 选择操作：`fb_scintilla_get_sel_start`, `fb_scintilla_set_sel`
  - 行操作：`fb_scintilla_get_line_count`, `fb_scintilla_goto_line`
  - 折叠操作：`fb_scintilla_fold_all`, `fb_scintilla_unfold_all`
  - 书签操作：`fb_scintilla_bookmark_toggle`, `fb_scintilla_bookmark_next`
  - 查找：`fb_scintilla_find_text`
  - 样式：`fb_scintilla_set_lexer`, `fb_scintilla_style_set_fore`
- 每个函数 Export，供 Python 侧调用

### 步骤 4：更新 modules/__init__.py
- 注册 `scintilla_wrapper` 模块
- 实现 `get_inc_paths('scintilla_wrapper')` 返回 gui/inc/scintilla/ 路径
- 确保 inc_paths / lib_paths 正确传递给 compiler

### 步骤 5：验证编译
- 编写测试脚本，用 @fbc 装饰器调用 fb_scintilla_* 函数
- 验证头文件包含正确、链接成功、DLL 加载正常
- 确认 OOP 类封装也可正常使用

---

## 五、潜在问题与风险

| 风险 | 影响 | 应对方案 |
|---|---|---|
| VFB 的 .bi 文件编码为 GBK | FreeBASIC 编译器可能无法识别中文注释 | 转换为 UTF-8 或移除中文注释 |
| ClsScintilla.inc 依赖 VFB 框架 | 可能引用了 VFB 特有的头文件/函数 | 剥离 VFB 依赖，保留纯 Scintilla 封装 |
| Scintilla.dll 版本不匹配 | 常量定义与实际 DLL 导出不一致 | 用 VFB 自带的 Scintilla64.dll 替换现有 DLL |
| 32 位支持缺失 | 目前只有 win64 目录 | 后续补充 win32 目录的 DLL 和 .a |
| DirectFunction 方式 | 需要窗口句柄才能使用 | wrapper 层需明确传入 hWnd 参数 |

---

## 六、验证标准

1. ✅ `#include "scintilla/modScintilla.bi"` 编译通过
2. ✅ `Class_Scintilla` 类可实例化并调用方法
3. ✅ `fb_scintilla_*` wrapper 函数可通过 @fbc 装饰器调用
4. ✅ DLL 加载无错误，运行时可正常收发 Scintilla 消息
5. ✅ `list_fb_libs()` 中 Scintilla 条目有正确的 header 路径
