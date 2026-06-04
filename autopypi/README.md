# vools 自动化发布脚本使用说明

## 概述

本项目提供了一套基于 Fabric 的自动化发布脚本，用于简化 vools 项目的发布流程。

## 目录结构

```
autopypi/
├── __init__.py           # 模块初始化
├── config.py             # 配置管理
├── logger.py             # 日志记录
├── environment.py        # 环境检查
├── packaging.py          # 打包功能
├── versioning.py         # 版本控制
├── publishing.py         # 发布功能
├── release.py            # 发布管理器
└── fabfile.py            # 命令行入口
```

## 安装依赖

```bash
# 安装 Fabric 和其他依赖
pip install fabric build twine pytest
```

## 使用方法

### 基础命令

```bash
# 进入 autopypi 目录
cd autopypi

# 显示帮助信息
python fabfile.py --help
```

### 检查环境

```bash
python fabfile.py check
```

### 显示/更新版本

```bash
# 显示当前版本
python fabfile.py version --show

# 递增版本号（patch/minor/major）
python fabfile.py version --bump patch
```

### 配置管理

```bash
# 初始化配置文件
python fabfile.py config --init

# 显示当前配置
python fabfile.py config --show
```

### 执行完整发布

```bash
# 默认发布（patch 版本）
python fabfile.py release

# 指定版本递增级别
python fabfile.py release --bump minor
python fabfile.py release --bump major

# 发布到测试 PyPI
python fabfile.py release --test

# 跳过测试
python fabfile.py release --skip-tests

# 组合使用
python fabfile.py release --bump minor --test --skip-tests
```

## 发布流程

发布脚本执行以下步骤：

1. **环境检查**
   - 检查 Python 版本（>= 3.6）
   - 检查核心依赖是否安装
   - 检查 Git 仓库状态
   - 检查 PyPI 配置

2. **版本准备**
   - 获取当前版本
   - 计算新版本号
   - 更新版本文件
   - 创建更新日志

3. **运行测试**
   - 执行 pytest 测试套件
   - 测试失败时提示是否继续

4. **构建包**
   - 清理旧的构建产物
   - 使用 build 工具构建 sdist 和 wheel
   - 使用 twine 验证包完整性

5. **版本控制**
   - 添加变更到 Git
   - 提交变更
   - 创建版本标签

6. **发布确认**
   - 交互式确认是否发布

7. **发布到 PyPI**
   - 使用 twine 上传包

8. **同步到 GitHub**
   - 推送代码到远程仓库
   - 推送版本标签

## 配置说明

配置文件位于 `autopypi/config.json`，包含以下选项：

```json
{
  "project": {
    "name": "vools",
    "version_file": "vools/__init__.py",
    "changelog_dir": "changelog",
    "dist_dir": "dist"
  },
  "pypi": {
    "repository": "https://upload.pypi.org/legacy/",
    "test_repository": "https://test.pypi.org/legacy/",
    "pypirc_path": "~/.pypirc",
    "use_test_pypi": false
  },
  "git": {
    "remote_name": "origin",
    "main_branch": "main",
    "create_tag": true,
    "push_tag": true
  },
  "testing": {
    "run_tests": true,
    "test_dir": "tests",
    "test_command": "pytest"
  },
  "logging": {
    "log_file": "release.log",
    "log_level": "INFO",
    "log_format": "%(asctime)s - %(levelname)s - %(message)s"
  }
}
```

### 配置项说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| project.name | 项目名称 | vools |
| project.version_file | 版本文件路径 | vools/__init__.py |
| project.changelog_dir | 更新日志目录 | changelog |
| project.dist_dir | 构建产物目录 | dist |
| pypi.repository | 正式 PyPI 仓库地址 | https://upload.pypi.org/legacy/ |
| pypi.test_repository | 测试 PyPI 仓库地址 | https://test.pypi.org/legacy/ |
| pypi.pypirc_path | PyPI 配置文件路径 | ~/.pypirc |
| git.remote_name | Git 远程仓库名称 | origin |
| git.main_branch | 主分支名称 | main |
| git.create_tag | 是否创建标签 | true |
| git.push_tag | 是否推送标签 | true |
| testing.run_tests | 是否运行测试 | true |
| testing.test_dir | 测试目录 | tests |
| testing.test_command | 测试命令 | pytest |
| logging.log_file | 日志文件 | release.log |
| logging.log_level | 日志级别 | INFO |

## PyPI 配置

在发布前，需要配置 PyPI 凭证。有两种方式：

### 方式 1：使用 .pypirc 文件

创建或编辑 `~/.pypirc` 文件：

```ini
[pypi]
username = __token__
password = pypi-你的API令牌
```

### 方式 2：使用环境变量

设置环境变量：

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-你的API令牌
```

## 日志记录

发布过程会记录到 `release.log` 文件，同时输出到控制台。日志级别可通过配置文件调整。

## 错误处理

脚本包含完整的错误处理机制：
- 每一步骤都有成功/失败检查
- 失败时记录详细错误信息
- 关键步骤失败时提示用户确认是否继续
- 异常情况捕获并记录

## 安全注意事项

1. **不要提交敏感信息**：确保 `.pypirc` 文件不在版本控制中
2. **使用 API Token**：推荐使用 PyPI API Token 而非密码
3. **测试环境**：先使用 `--test` 参数测试发布流程
4. **确认机制**：发布前会提示确认，避免误操作

## 示例

```bash
# 完整发布流程示例
cd autopypi

# 1. 检查环境
python fabfile.py check

# 2. 确认当前版本
python fabfile.py version --show

# 3. 执行发布（minor 版本）
python fabfile.py release --bump minor

# 发布完成后查看日志
cat release.log
```