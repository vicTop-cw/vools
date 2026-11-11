# 0.9.1 版本发布材料（R111，统帅轮-16时备料）

> 性质：**备料，不擅自发版**。发布动作需主人拍板后执行。
> 背景：Unreleased 段积累 7 轮统帅轮改动（09时-15时），全部为测试/修复/文档，
> 零破坏性产品变更（唯一产品代码改动是 WSL bash 特判——纯探测层跳过，无行为变化）。

## 一、版本号同步核对（DEVELOPMENT_STANDARDS 版本号同步纪律）

| 位置 | 当前值 | 发 0.9.1 需改 |
|---|---|---|
| `actus/pyproject.toml` `version = "0.9.0"` | 0.9.0 | "0.9.1" |
| `actus/vools/actus/__init__.py` `__version__ = '0.9.0'`（兜底值） | 0.9.0 | '0.9.1' |
| 最近 tag | v0.9.0 | 待打 v0.9.1 |

双处一致（当前 0.9.0/0.9.0），发版时**必须同步改**——纪律见
DEVELOPMENT_STANDARDS「版本号同步」。`__init__.py:28` 有一段旧注释（0.8.0 旧
wheel 冲突导致 test_cli_version_flag 失败的历史）——发 0.9.1 后该注释可清理
（历史教训已沉淀在历史 commit）。

## 二、0.9.1 发布说明候选（Unreleased 六轮聚合）

### 🚀 性能
- **probe 性能大优化**：WSL bash 转发器特判（runtimes 5.1s→256ms，-95%），
  probe 全量墙钟 5.4s→1.04s 首进 1 秒档。修复 system32\bash.EXE 被误当
  开发运行时 version 信号源的问题（WSL 网关跳过 + extra 标注）。

### 🐛 修复
- **SIP 探测安全语义反转**：`"enabled" in stdout` 在 SIP disabled 时同样命中
  （disabled ⊃ enabled）→ 关闭态误报开启态。判据改 `"status: enabled"` + 4 回归。

### ✅ 测试基建
- GUI 契约测试环境守卫（tkdialog/panel 真 Tk() 探测防半可用环境 ERROR）
- 基线修复 5 处（pkg_resources/locale 环境分档、desktop fastapi skip）
- **R105 覆盖审计三批 150 新用例**（sigma 门禁 Law I-XVII 44 + constants 谓词族 69
  + model 安全白名单 14 + visibility gated 5 + check_path_target 5 + filter_by_dimension 4
  + WSL 回归 4 + 其余）——校验门禁面从零覆盖转全覆盖
- 测试头注释 py3.6→py3.8+ 口径对齐（20 文件）

### 🗂 仓储治理
- Find_BUG 14 repro 全景甄别（全部已修，转证据存档 + STALE 头注释）
- HANDOFF（2026-08）三点复查全清
- reports/ 门禁目录归位、STALE 存档、三本账实测对齐（REFACTOR §六.1/§六.4、
  PROBE_PLAN §984）
- 覆盖审计假阴性核实反转（12 全确认零覆盖，审计口径经受对抗复核）

### 🔍 审计/决策备料（未拍板项）
- API 收敛评审备料 R110（7 个降级候选确认 + get_default_router 保留）
- installer/publisher 覆盖判定统一备料（errors.py docstring 订正：installer
  是「存在即 rmtree 重装 + 配置快照/还原」，非幂等 no-op）
- 版本号决策：本条材料（0.9.1 候选）

## 三、发布动作清单（拍板后执行）

1. 改 `pyproject.toml` version + `__init__.py` __version__ → 0.9.1
2. CHANGELOG：Unreleased 六轮条目整体移入 `## [0.9.1] - <日期>` 段，
   保留条目结构
3. commit（release 组）→ tag `v0.9.1`
4. wheel 构建（setuptools.build_meta 直构绕过带伤 pip）+ 核验
5. push（GitCode VictorTop/vools —— 需主人授权）

## 四、拍板动线

主人回复其一：
- 「发 0.9.1」→ 按第三节清单执行（tag+wheel+push 需再确认）
- 「再攒一轮」→ 本材料留档，15时/16时 条目继续入 Unreleased
- 「不发版，保持现状」→ 材料作历史记录</think>