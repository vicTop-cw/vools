# VB.NET API TLB 桥接模块 - 实现计划

## [x] Task 1: 技术选型验证与核心框架搭建
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 验证 win32com.client vs VB.NET 包装层两种方案的可行性
  - 选定实现方案（推荐方案 A: win32com.client 直接调用，简单高效）
  - 创建 api 子包目录结构和基础文件
  - 实现 COM 对象创建/缓存的基础工具类
  - 实现可用性检测函数 `is_api_available()`
- **Acceptance Criteria Addressed**: AC-1, AC-7, AC-9
- **Test Requirements**:
  - `programmatic` TR-1.1: 导入 vools.bridge.vbnet.api 不报错
  - `programmatic` TR-1.2: is_api_available() 在有 API.dll 时返回 True，无则返回 False
  - `programmatic` TR-1.3: 能成功创建 API.Window 等 COM 对象
  - `human-judgement` TR-1.4: 代码结构符合 vools.bridge 现有模块风格
- **Notes**: 方案 A (win32com.client) 更直接，符合 Python 生态习惯；如后续性能不满足再考虑 VB.NET 包装层

## [x] Task 2: Window 模块封装
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 封装 _Window 接口的常用方法：FindWindow, FindWindowEx, GetWindowText, SetWindowText, GetWindowRect, MoveWindow, ShowWindow, CloseWindow 等
  - 封装属性访问（Hwnd 等）
  - 实现 Pythonic 的类包装（Window 类）
  - 处理返回值类型转换（RECT 结构体转 tuple/dict）
- **Acceptance Criteria Addressed**: AC-2, AC-7, AC-8
- **Test Requirements**:
  - `programmatic` TR-2.1: Window.FindWindow 能通过类名/标题找到窗口
  - `programmatic` TR-2.2: Window.GetWindowText 返回正确的窗口标题
  - `programmatic` TR-2.3: Window.GetWindowRect 返回 (left, top, right, bottom) 元组
  - `programmatic` TR-2.4: 窗口不存在时抛出明确的异常

## [x] Task 3: Mouse 模块封装
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 封装 _Mouse 接口的方法：MouseMove, LeftDown, LeftUp, LeftClick, RightDown, RightUp, RightClick, MiddleClick, DoubleClick, MouseWheel 等
  - 提供坐标参数（相对屏幕坐标）
- **Acceptance Criteria Addressed**: AC-3, AC-8
- **Test Requirements**:
  - `programmatic` TR-3.1: MouseMove(x, y) 不抛出异常
  - `programmatic` TR-3.2: LeftClick() 不抛出异常
  - `programmatic` TR-3.3: 所有鼠标方法签名正确，参数类型匹配

## [x] Task 4: Keyboard 模块封装
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 封装 _Keyboard 接口的方法：SendKeys, KeyDown, KeyUp, KeyDownUp, GetKeyPressed, GetKeyOpened 等
  - 支持虚拟键码和字符串两种输入方式
  - 修饰键（Ctrl/Alt/Shift）状态检测
- **Acceptance Criteria Addressed**: AC-4, AC-8
- **Test Requirements**:
  - `programmatic` TR-4.1: SendKeys 能发送字符串
  - `programmatic` TR-4.2: KeyDown/KeyUp 支持虚拟键码
  - `programmatic` TR-4.3: GetKeyPressed 等状态检测方法返回 bool

## [x] Task 5: Image 模块封装
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 封装 _Image 接口的方法：ScreenCapture, OpenImage, SaveImage, GetPixelColor, SetPixelColor, ChangeSize, CropImage, RotateFlip 等
  - 截图功能返回 PIL.Image 对象（如果 PIL 可用）或 bytes
  - 图像处理方法的参数类型转换
- **Acceptance Criteria Addressed**: AC-5, AC-8
- **Test Requirements**:
  - `programmatic` TR-5.1: ScreenCapture() 返回非空图像数据
  - `programmatic` TR-5.2: 截图能保存为文件且文件有效
  - `programmatic` TR-5.3: GetPixelColor 返回颜色值（整数或 RGB 元组）

## [x] Task 6: FileSystem 模块封装
- **Priority**: medium
- **Depends On**: Task 1
- **Description**: 
  - 封装 _FileSystem 接口的方法：CreateDirectory, DeleteDirectory, DeleteFile, ReadAllText, WriteAllText, FileExists, DirectoryExists, CopyFile, MoveFile, RenameFile 等
  - 路径参数支持 Python 路径对象
  - 返回值类型转换（bool 等）
- **Acceptance Criteria Addressed**: AC-6, AC-8
- **Test Requirements**:
  - `programmatic` TR-6.1: FileExists/DirectoryExists 返回正确的 bool
  - `programmatic` TR-6.2: ReadAllText/WriteAllText 读写正确
  - `programmatic` TR-6.3: 创建/删除目录操作正确

## [x] Task 7: Process 和 Network 模块封装
- **Priority**: medium
- **Depends On**: Task 1
- **Description**: 
  - Process 模块：Start, Shell, GetProcesses, GetProcessesByName, Kill, WaitForExit 等
  - Network 模块：NetworkIsAvailable, DownloadFile, GetWebSourceCode, UrlEncode, UrlDecode 等
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-7.1: Process.Start 能启动进程
  - `programmatic` TR-7.2: Network.NetworkIsAvailable 返回 bool
  - `programmatic` TR-7.3: UrlEncode/UrlDecode 正确编解码

## [x] Task 8: 统一 API 入口与模块整合
- **Priority**: high
- **Depends On**: Task 1-7
- **Description**: 
  - 在 vools.bridge.vbnet.__init__.py 中导出 api 模块
  - 在 vools.bridge.__init__.py 的延迟加载机制中添加 api 相关导出
  - 提供便捷的顶层访问方式
  - 编写 __init__.py docstring 和模块说明
- **Acceptance Criteria Addressed**: AC-7, AC-9
- **Test Requirements**:
  - `programmatic` TR-8.1: from vools.bridge.vbnet import api 正常工作
  - `programmatic` TR-8.2: api.Window, api.Mouse 等子模块可访问
  - `human-judgement` TR-8.3: 导出结构与其他子包一致

## [x] Task 9: 文档与测试
- **Priority**: medium
- **Depends On**: Task 1-8
- **Description**: 
  - 编写 api 子包的 README.md
  - 编写单元测试（mock COM 对象，避免实际操作影响测试环境）
  - 编写使用示例和最佳实践
  - 更新 vools.bridge.vbnet 的 README.md
- **Acceptance Criteria Addressed**: AC-9, AC-10
- **Test Requirements**:
  - `programmatic` TR-9.1: 单元测试覆盖率覆盖主要模块
  - `human-judgement` TR-9.2: README 包含安装说明、API 列表、使用示例
  - `human-judgement` TR-9.3: 文档风格与其他子包一致
