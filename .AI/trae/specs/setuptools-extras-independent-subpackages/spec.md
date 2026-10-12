# vools 子包独立分发与 extras_require 整改 Spec

## Why
当前 `vools` 一个 distribution 通过 `setuptools.packages.find` 自动打包了 `vools/bridge` 和 `vools/reactive`，导致 `pip install vools` 也会安装这两个体积大、依赖外部编译器/运行时的子包。用户希望 PyPI 端支持按需安装：`vools` 仅含核心，`vools[rx]` 引入 reactive，`vools[bridges]` 引入 bridges，`vools[all]` 引入全部；同时 `vools-bridges` 和 `vools-rx` 能够独立分发，并且内部不依赖 `vools` 除基础兼容层外的其他 API。

## What Changes
- **BREAKING**: `vools` distribution 不再包含 `vools/bridge` 和 `vools/reactive` 子包代码。
- 新建 `vools-bridges` distribution，承载全部 `vools/bridge/*` 代码，通过 PEP 420 namespace package 以 `vools.bridge` 路径暴露。
- 新建 `vools-rx` distribution，承载全部 `vools/reactive/*` 代码，通过 PEP 420 namespace package 以 `vools.reactive` 路径暴露。
- 更新根目录 `pyproject.toml`：
  - `project.optional-dependencies` 新增 `rx`、`bridges`、`all`。
  - `rx` 依赖 `vools-rx=={version}`。
  - `bridges` 依赖 `vools-bridges=={version}`。
  - `all` 同时依赖 `vools-rx` 和 `vools-bridges`。
  - `tool.setuptools.packages.find` 排除 `vools.bridge*`、`vools.reactive*`。
- 新增 `bridges/pyproject.toml` 和 `rx/pyproject.toml`，支持独立构建与发布。
- 调整 `vools/__init__.py`：
  - 移除对 `vools.bridge` 的顶层 try/except 硬导入；改为通过 `__getattr__` 延迟转发或优雅降级。
  - 保留 `BRIDGE_AVAILABLE` / `REACTIVE_AVAILABLE` 标志，但仅在子包真实存在时设为 `True`。
- 清理 `vools/bridge` 和 `vools/reactive` 内部对 `vools.decorators`、`vools.functional`、`vools.data`、`vools.oop`、`vools.task` 等功能模块的耦合；允许仅依赖 `vools.core.*` 基础兼容层（`dataclass_compat`、`asyncio_compat`、`inspect_compat` 等）。
- 将原 `vools/bridge` 和 `vools/reactive` 目录物理迁移到 `bridges/vools/bridge/` 与 `rx/vools/reactive/`，根目录 `vools/` 中不再保留这两个子目录。

## Impact
- 受影响能力：PyPI 安装粒度、CI 构建流程、本地开发目录结构、namespace package 导入行为。
- 受影响代码：`pyproject.toml`、`vools/__init__.py`、整个 `vools/bridge` 与 `vools/reactive` 目录、所有引用这两个子包的内部 README/测试路径。

## ADDED Requirements

### Requirement: 子包可独立分发
`vools-bridges` 和 `vools-rx` 两个 distribution 必须能够脱离 `vools` 核心包单独构建并发布到 PyPI。

#### Scenario: 独立构建成功
- **WHEN** 在 `bridges/` 目录执行 `python -m build`
- **THEN** 成功生成 `vools-bridges-{version}-py3-none-any.whl` 和源码包

#### Scenario: 独立安装后路径正确
- **WHEN** 在干净虚拟环境中执行 `pip install vools-bridges`
- **THEN** 可以成功 `import vools.bridge`

### Requirement: extras_require 语义正确
PyPI 端安装命令与包含代码的对应关系必须如下：

| 命令 | 包含代码 | 等价依赖 |
|---|---|---|
| `pip install vools` | 核心包（不含 bridge/reactive） | `vools` |
| `pip install "vools[rx]"` | 核心 + reactive | `vools`, `vools-rx` |
| `pip install "vools[bridges]"` | 核心 + bridges | `vools`, `vools-bridges` |
| `pip install "vools[all]"` | 核心 + reactive + bridges | `vools`, `vools-rx`, `vools-bridges` |

#### Scenario: 基础安装不含子包
- **WHEN** 在干净虚拟环境中执行 `pip install vools`
- **THEN** `import vools.bridge` 抛出 `ModuleNotFoundError`
- **AND** `import vools.reactive` 抛出 `ModuleNotFoundError`

#### Scenario: all 安装包含子包
- **WHEN** 在干净虚拟环境中执行 `pip install "vools[all]"`
- **THEN** `import vools.bridge` 和 `import vools.reactive` 均成功

### Requirement: 子包内部不依赖 vools 其他 API
`vools-bridges` 与 `vools-rx` 的源码中不得再出现 `from vools.decorators...`、`from vools.data...`、`from vools.functional...`、`from vools.oop...`、`from vools.task...`、`from vools.utils...` 等引用；仅允许引用 `vools.core.*` 兼容层。

#### Scenario: reactive 解耦验证
- **WHEN** 在虚拟环境中仅安装 `vools-rx`（不安装 `vools`）
- **THEN** `import vools.reactive` 成功且核心功能可运行
- **AND** 不因为缺少 `vools.decorators` 等模块而报错

#### Scenario: bridges 解耦验证
- **WHEN** 在虚拟环境中仅安装 `vools-bridges`（不安装 `vools`）
- **THEN** `import vools.bridge` 成功
- **AND** 不因为缺少 `vools.decorators` / `vools.data` 等模块而报错

## MODIFIED Requirements

### Requirement: vools 核心包保持向后兼容
`vools` 核心包继续通过 `import vools` 暴露原有核心 API（`Seq`、`memorize`、`curry` 等）；仅在子包未安装时，`vools.bridge` / `vools.reactive` 不可访问。

#### Scenario: 核心 API 不变
- **GIVEN** 已安装 `vools`
- **WHEN** 执行 `import vools; print(vools.Seq, vools.curry, vools.memorize)`
- **THEN** 所有属性均可正常访问

#### Scenario: 子包缺失时优雅降级
- **GIVEN** 只安装了 `vools`
- **WHEN** 用户访问 `vools.bridge`
- **THEN** 抛出 `AttributeError` / `ModuleNotFoundError`，不导致 `import vools` 失败

## REMOVED Requirements

### Requirement: vools 单包包含全部子模块
**Reason**: 用户要求按需安装，bridge 和 reactive 不再随 `pip install vools` 默认分发。
**Migration**: 原 `vools/bridge` 和 `vools/reactive` 目录迁移到独立的 `bridges/` 和 `rx/` 子项目中；用户需通过 extras 或单独安装子包。
