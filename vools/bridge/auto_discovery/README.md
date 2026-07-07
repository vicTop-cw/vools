# vools.bridge.auto_discovery - 编译器自动发现与配置

`vools.bridge.auto_discovery` 模块提供一键发现本机和 WSL 环境中所有已安装编程语言编译器的功能，无需手动配置 PATH 环境变量。

---

## 目录

- [功能概述](#功能概述)
- [快速开始](#快速开始)
- [核心 API](#核心-api)
- [使用示例](#使用示例)
- [WSL 支持](#wsl-支持)

---

## 功能概述

### 解决的问题

- **PATH 未配置**：部分编译器未加入系统 PATH，无法被 `shutil.which()` 发现
- **WSL 环境**：Windows 上的 WSL 发行版中安装了独立编译器
- **手动配置繁琐**：每种语言都需要手动查找安装路径并配置

### 解决方案

- **多源探测**：系统 PATH + 注册表 + 常见安装路径 + WSL 环境
- **通配符支持**：支持 `C:\Program Files\Java\jdk*\bin` 等路径模式
- **一键配置**：自动将发现的编译器路径配置到 BridgeManager

---

## 快速开始

```python
from vools.bridge.auto_discovery import discover_all

# 一键发现所有环境
result = discover_all()

# 查看本机可用语言
print('本机可用:', result['local'].available_languages())

# 查看 WSL 可用语言
for wsl in result['wsl']:
    print(f'{wsl.host} 可用:', wsl.available_languages())

# 打印报告
print(result['report'])
```

---

## 核心 API

### discover_all()

一键发现所有环境中的编译器。

```python
def discover_all(
    languages: Optional[List[str]] = None,
    configure_manager: bool = True,
    include_wsl: bool = True,
) -> Dict[str, Any]
```

**参数：**
- `languages`: 指定要探测的语言列表，None 表示全部 27 种语言
- `configure_manager`: 是否自动配置到 BridgeManager（默认 True）
- `include_wsl`: 是否包含 WSL 环境（默认 True）

**返回值：**
```python
{
    'local': ProbeReport,           # 本机探测报告
    'wsl': List[ProbeReport],      # WSL 各发行版探测报告
    'discovered': dict,            # {环境名: [可用语言列表]}
    'report': str,                 # 格式化报告文本
}
```

### discover_local()

仅发现本机编译器，不探测 WSL。

```python
def discover_local(languages: Optional[List[str]] = None) -> Dict[str, Any]
```

### discover_wsl()

仅发现 WSL 环境中的编译器。

```python
def discover_wsl(languages: Optional[List[str]] = None) -> List[ProbeReport]
```

### get_discovery_report()

生成完整的发现报告文本（不配置 manager）。

```python
def get_discovery_report(languages: Optional[List[str]] = None) -> str
```

### configure_from_discovery()

从探测结果配置 BridgeManager。

```python
def configure_from_discovery(
    report: Optional[ProbeReport] = None,
    include_wsl: bool = True,
) -> int
```

**返回值：** 成功配置的语言数量

---

## 使用示例

### 示例 1：查看所有可用编译器

```python
from vools.bridge.auto_discovery import get_discovery_report

report = get_discovery_report()
print(report)
```

**输出示例：**
```
======================================================================
  vools.bridge 编译器自动发现报告
======================================================================

【本机环境】
  平台: Windows
  架构: AMD64
  Python: 3.13.2

  已安装编译器:
    C/C++ (MSVC)     C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.40.33807\bin\HostX64\x64\cl.exe
    Nim              C:\Users\username\.nimble\bin\nim.exe
    Rust (Cargo)     C:\Users\username\.cargo\bin\cargo.exe
    Go               C:\Go\bin\go.exe
    ...

======================================================================
  总计: 15/27 种语言可用
======================================================================
```

### 示例 2：仅发现特定语言

```python
from vools.bridge.auto_discovery import discover_all

# 仅探测 Nim、Rust、Go
result = discover_all(languages=['nim', 'rust', 'go'])
print('发现:', result['discovered'])
```

### 示例 3：自动配置 BridgeManager

```python
from vools.bridge.auto_discovery import discover_all
from vools.bridge import manager

# 发现并配置
result = discover_all(configure_manager=True)

# 使用配置的编译器
from vools.bridge import nim
```

### 示例 4：WSL 混合环境发现

```python
from vools.bridge.auto_discovery import discover_all

# 发现本机 + 所有 WSL 发行版
result = discover_all(include_wsl=True)

for wsl_report in result['wsl']:
    print(f'{wsl_report.host}:', wsl_report.available_languages())
```

---

## WSL 支持

### 工作原理

1. 列出所有已安装的 WSL 发行版：`wsl --list --quiet`
2. 对每个发行版执行编译器探测命令
3. 自动识别 Linux 特有的编译器安装路径

### 支持的 WSL 发行版

- Ubuntu（所有版本）
- Debian
- Kali Linux
- Arch Linux
- openSUSE
- Fedora
- 以及其他主流 WSL 发行版

### 示例输出

```
【WSL: Ubuntu-22.04】
  平台: Linux
  架构: x86_64

  已安装编译器:
    GCC              /usr/bin/gcc
    Clang            /usr/bin/clang
    Rust (Cargo)     /root/.cargo/bin/cargo
    Go               /usr/local/go/bin/go
    ...
```

---

## 依赖模块

- `vools.bridge.probe`: 核心探测引擎
- `vools.bridge.manager`: 编译器配置管理
- `vools.bridge.auto_discovery`: 本模块（一键发现）

## 相关链接

- [Bridge 框架总览](../README.md)
- [probe 模块文档](./probe/README.md)
- [manager 模块文档](./manager/README.md)
