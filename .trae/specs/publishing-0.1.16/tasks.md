# vools 0.1.16 发布计划 - 实施计划

## [/] Task 1: 提交并推送本地更改到远程仓库
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 添加未跟踪的文件（docs/）
  - 暂存所有更改（tests/test_rself.py, vools/decorators/rself.py, vools/reactive/core/observable.py）
  - 创建提交，提交信息包含版本号和主要变更
  - 推送到 GitHub (origin) 和 GitCode (gitcode)
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: git status 显示工作目录干净，无未提交更改
  - `programmatic` TR-1.2: git log 显示最新提交已推送（origin/main 和 gitcode/main 均包含最新提交）
- **Notes**: 之前 GitHub 推送因网络问题失败，需要确保网络连接正常

## [ ] Task 2: 运行完整测试套件
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 运行 pytest 测试套件，排除编码损坏的集成测试文件
  - 验证所有测试通过（目标：777+ 测试）
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: pytest 退出码为 0
  - `programmatic` TR-2.2: 测试报告显示通过测试数 >= 777
- **Notes**: 需要排除以下文件：
  - tests/test_clipboard_debug.py
  - tests/test_clipboard_direct.py
  - tests/test_clipboard_event_loss.py
  - tests/test_clipboard_monitor.py
  - tests/test_clipboard_simple.py
  - tests/test_clipboard_single.py
  - tests/test_file_observer_integration.py
  - tests/test_folder_observer_integration.py
  - tests/test_key_observer_integration.py
  - tests/test_keyboard_observer_integration.py
  - tests/test_mouse_observer_integration.py

## [ ] Task 3: 构建发布包
- **Priority**: P0
- **Depends On**: Task 2
- **Description**: 
  - 安装 build 工具（如果未安装）
  - 执行 python -m build 生成 .whl 和 .tar.gz 文件
  - 验证 dist/ 目录下生成了正确的包文件
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: build 命令退出码为 0
  - `programmatic` TR-3.2: dist/ 目录包含 vools-0.1.16-py3-none-any.whl
  - `programmatic` TR-3.3: dist/ 目录包含 vools-0.1.16.tar.gz
- **Notes**: 需要确保 pyproject.toml 配置正确，版本号为 0.1.16

## [ ] Task 4: 发布到 PyPI
- **Priority**: P0
- **Depends On**: Task 3
- **Description**: 
  - 安装 twine（如果未安装）
  - 执行 twine upload dist/* 上传到 PyPI
  - 验证上传成功
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: twine upload 命令成功执行，无错误
  - `programmatic` TR-4.2: 可通过 pip install vools==0.1.16 安装并验证版本
- **Notes**: 需要有效的 PyPI 凭据配置

## [ ] Task 5: 发布后验证
- **Priority**: P1
- **Depends On**: Task 4
- **Description**: 
  - 通过 pip 安装 vools==0.1.16
  - 验证安装成功并可正常导入
  - 验证版本号正确显示为 0.1.16
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-5.1: pip install vools==0.1.16 成功
  - `programmatic` TR-5.2: python -c "import vools; print(vools.__version__)" 输出 "0.1.16"
- **Notes**: 建议在虚拟环境中进行测试，避免影响现有安装