# Changelog — vools-actus

本文件记录 `vools-actus` 包的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循语义化版本。

> **依赖提示**：`vools-actus` 依赖 `vools` 与 `vools-bridges`。三者的版本通常同步发布；
> 只升级 actus 而不升级依赖，可能拿到不含对应修复的底层实现。

## [0.9.0] - 2026-10-27

这一版是**以「验收 + 缺陷围剿」为主题的版本**：从 0.8.0（10-17）之后累计 600+ 次提交，
其中 actus 包内 59 次、`bridges`（解析层）26 次、`vools` 核心 433 次。

### ✨ 新增能力（Actus 引擎）

- **无源码动作族全部落地**（`docs/actus/03-动作规范.md` §3.3）：`exec` / `link` / `demo` /
  `template` / `alias` / `bundle` / `doc` 七种 kind 均有执行语义。
  - `link`：按 `target` 转发并做参数合并；新增 `meta['merge'] = 'deep'` 递归合并
    （默认 `shallow` 保持零回归，规则与用例见 `tests/test_link_merge.py`）。
  - `alias`：直接转发；与 `link` 共用深度守卫与成环检测。
  - `demo`：演示模式——执行入口块并把全部代码块按 only-code 展开。
  - `template`：按声明调用 `scaffold` 生成动作文件。
  - `bundle`：列出成员动作清单（不执行成员）。
  - `doc`：仅渲染，不执行任何代码。
- **`resolver` 六形态 target + 七形态入参**：动作 id / 可读名 / 内容 md5 / 本地文件路径 /
  本地目录 / `http(s)` URL；入参支持 JSON 字面量 / `@file` / `-`(stdin) / `@url` / `@action:<id>`。
- **MCP 工具接入 resolver**：`actus_info` / `actus_preview` 的 `id` 参数现在真正走解析器
  （此前直接当 action_id 用），工具描述里写清六种形态。
- **远程动作信任四件套**（`docs/actus` §六.3）：
  - 域名白名单——**默认拒绝所有远程**（配置 `--allow-host` 才放行）；
  - SSL 证书校验（此前被 `CERT_NONE` 关闭）；
  - 内容指纹 `--expect-digest <sha256>`；
  - 签名验签 `--require-signature <公钥名>`（复用种子动作的 ed25519 `.sig` 机制）。
- **CLI**：新增 `--version`；`actus` 无子命令时打印用法（此前静默退出）。

### 🐛 修复（25 个 actus 内缺陷 + 解析层 6 个）

**高危**

- `CronExpr` 的星期字段**整体偏移一天**：docstring 与 cron 标准都是 0=周日，代码却拿
  `time.struct_time.tm_wday`（0=周一）比对，导致所有按星期配置的触发器错一天且完全静默。
- `CircuitBreaker(recovery_timeout<0)` 被接受 → 恢复判据恒为真，断路器永远停在半开、
  **再也不熔断**（保护静默失效）。
- 远程下载 SSL 证书校验被禁用（`CERT_NONE`）；白名单语义反转（空白名单被当成"不校验"，SSRF）。
- `cli.py` 的 `if __name__ == '__main__'` 守卫**写在文件中间**（原第 2034 行）：`python -m
  vools.actus.cli <cmd>` 下 omega / concurrency / deps / dep-tree / desktop / events / viz /
  replay / notify / project 导入导出 / export / probe / health / selfheal / template 等
  **15 个子命令全部 `NameError`**；安装态 console script 走 import 路径，模块体先完整执行
  再调 `main()`，因此长期未暴露。已把守卫移到文件末尾（`cli.py:2574`，共 2575 行）。
  诊断记录见 `docs/INFRA_DIAGNOSTIC.md` §5.6 D10。

**中危**

- 空 `user_id` 被当成合法团队成员（`is_member('')` 为真）；`role` 拼错静默收下（权限静默消失）。
- 心跳/缓存类：`DAG` 缺失依赖被**静默丢边**，本该串行的节点并发执行。
- `md5` 指纹缺失：新格式 `.actus.schema.md` 的动作 `Action.md5` 恒为空 ⇒ md5 target 形态失效。
- 动作文件查找存在**五份**独立实现，其中依赖/安装/自进化/omega 四份用「字符串搜 id」判断身份，
  **认不出新格式 YAML 的 `id: xxx`**（连种子动作都返回 None）；已统一收口到
  `resolver.find_action_file` 单一实现，并加 lint 式守卫禁止回流。
- 格式检测只看后缀 ⇒ `*.demo.actus.md` 等新格式后缀全部解析失败（4 个 demo 文件实测中招）。
- `build_index(actions_dir=…)` 写默认缓存路径 ⇒ 污染主索引、测试出现顺序依赖。
- `IntentRouter` / `Decomposer` / `export` / `viz` 等公开入口**零校验**，其中
  `tags='abc'`、`template='abc'`、`ready_ids='abc'` 会被**逐字符展开**。
- `export_history(format_='zzz')`、`visualize_workflow(format_='zzz')` **静默回退**到默认格式。
- `run_case({})` 抛 `KeyError: 'file'` 等裸错 → 改为带字段名的可读错误。

**解析层（`vools-bridges`）**

- 围栏解析只认**列 0 的反引号**：`~~~` 波浪号围栏、缩进 ≤3 空格的围栏（两者都是合法
  CommonMark）被整块漏掉，4 反引号围栏还会提前闭合且丢语言。
- 裸 `key=value` 指令的引号值被空格截断、引号从不剥离（种子动作 `title` 解析出 `'"Calculator"'`）。
- `validate.check_block_languages()` 走 `vools.bridge.md.runner.is_routable`（单一真源）。

### ✅ 验收与证据

- **`pytest tests` → 691 passed, 1 skipped**（69 个测试文件）。
- 全量逐文件校验 **11 个动作文件 0 失败**；`actus validate` 批量 `valid=true, invalid={}`。
- 4 个种子动作 **签名 4/4 通过**；7 种语言入口（python/bash/shell/powershell/pwsh/cmd/node）
  端到端实跑通过。
- 计划完成度核验报告：`docs/REFACTOR_COMPLETION.md`（逐条映射到证据文件）。

### 🔧 工程改进

- 新增开发规范 `docs/DEVELOPMENT_STANDARDS.md`。
- 新增 lint 式守卫：禁止"字符串搜 id"判断动作身份、禁止单复数分裂的错误码、仓库内动作文件必须可解析。
- 错误码从 63 个收敛（消除 `missing_param`/`missing_params` 单复数分裂），并新增
  `dag_missing_dep` / `dag_cycle` / `remote_*` 系列结构化错误。

### ⚠️ 升级注意

- **远程动作默认拒绝**：此前未配置白名单时会直接下载，现在必须显式 `--allow-host`。
- **`bundle` 空成员**现在报 `param_invalid`（此前返回 `status=ok` 的空清单）。
- **`link` 深链**（>5 跳）与**成环**现在分别报 `param_invalid`（深度超限）与
  `action_ref_cycle`（真环，附完整链路），此前统一报"疑似环"。
- **cron 星期语义修正**：升级后按星期配置的触发器会**提前/推迟一天**触发——这是修正，
  不是回归；依赖旧行为的配置需重新核对。
- CLI 退出码约定：用法错误 `2`、运行期失败 `1`、成功 `0`。

## [0.8.0] - 2026-10-17

该版本已发布到 PyPI，但**当时未写 CHANGELOG 条目**（文档缺口，此处补记）。
据提交记录（121 次提交），主要内容为合规与启动性能：

- 大批模块补 `__all__` 与子包 `README.md`（`bridges` 92 个模块、`actus.probe` 12 个等）。
- **惰性导入**：`bridge.md` 内置语言惰性注册，消除 import 期 WSL 探测 22–37s；
  `webview2` 改 PEP 562 惰性导出，`md.parser` 冷启动 **1.68s → 0.25s**。
- `wsl.check_wsl_command` 增加负缓存 TTL；`bridges/md` 补 Python <3.7 兜底。
- 修 `vDate/VDate` 紧凑日期+时间分支崩溃、`_GroupedObserver` 回调内退订漏通知等。

## [0.7.9] - 2026-10-13

详见仓库根 `CHANGELOG.md`（当时三包同步发布）。要点：`sigma` / `scattered` / `repo` /
`publisher` 四个模块首次进入 wheel；`bridge.md.runner` 新增语言可路由性单一真源。
