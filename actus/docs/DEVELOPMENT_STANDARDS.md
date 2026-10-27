# Actus 开发操作规范（DEVELOPMENT_STANDARDS）

> 本文件是新增 target 形态 / 新增 kind 的操作规范，作为 ACTUS_REFACTOR_PLAN 的配套文档。

---

## 一、新增 target 形态

Target 形态指 `resolve_target()` 可识别的动作来源。当前支持的形态：`path`、`id`、`https`。

### 操作流程

| 步骤 | 动作 | 产出 | 验收 |
|------|------|------|------|
| **1** | **写 resolver 优先级链**：在 `actus/vools/actus/resolver.py` 新增形态检测函数（如 `_is_xxx_url()`）和解析函数（如 `_resolve_xxx()`），并在 `resolve_target()` 的优先级链中按序插入 | 新增形态的检测 + 解析函数 | `pytest actus/tests/test_resolver_cli.py -q` 绿 |
| **2** | **写回归用例**：在 `actus/tests/test_resolver_cli.py` 新增 `test_resolve_target_<形态>_form()`，覆盖：合法输入解析正确、非法输入抛 `ActionError('action_invalid')`、路径不存在时抛 `ActionError('action_not_found')` | 新测试用例 | `pytest actus/tests/test_resolver_cli.py -q` 绿 |
| **3** | **接入 CLI**：若新形态需要新参数（如 `--xxx-url`），在 `actus/vools/actus/cli.py` 的 `_build_parser()` 中添加 argparse 子命令/选项，并在 `_cmd_run()` 中调用 resolver | CLI 参数面 | `pytest actus/tests/test_cli_surface.py -q` 绿 |
| **4** | **更新索引**：若新形态产生新的路径类型，确认 `actus/vools/actus/indexer.py` 的 `build_index()` 能收录 | 索引覆盖 | `actus validate --all` 无缺失 |

### 优先级链原则

- `path` > `id` > `https`：本地路径优先，避免误命中远端
- 新增形态插入位置按"确定性从高到低"排序
- 每个形态函数返回 `None`（未命中）或 `(source, action_id)` 元组，不抛异常

---

## 二、新增 kind

Kind 指动作的执行分类。当前支持的 kind：`exec`、`link`、`demo`、`template`、`alias`、`bundle`、`doc`。

### 操作流程

| 步骤 | 动作 | 产出 | 验收 |
|------|------|------|------|
| **1** | **注册 KIND_LEVELS**：在 `actus/vools/actus/constants.py` 的 `KIND_LEVELS` 字典中新增条目，定义 trust 等级与默认权限 | 新 kind 的常量 | `from vools.actus.constants import KIND_LEVELS; assert '<新kind>' in KIND_LEVELS` |
| **2** | **更新 schema**：在 `actus/vools/actus/schemas/action.schema.json` 的 `kind` 枚举列表中添加新值 | JSON Schema 更新 | `jsonschema.validate(...)` 通过 |
| **3** | **写 verify 规则**：在 `actus/vools/actus/validate.py` 的 `verify_action()` 中为新 kind 添加专项校验逻辑（如 `kind=bundle` 必须有 `bundle.actions` 字段） | 校验函数 | `pytest actus/tests/test_validate.py -q` 绿 |
| **4** | **落地 executor 分支**：在 `actus/vools/actus/executor.py` 的 `execute()` 主流程中新增 `kind == '<新kind>'` 的分支处理 | executor 分支 | `pytest actus/tests/test_executor_kind.py::test_<newkind>_dispatch -q` 绿 |
| **5** | **补种子动作**：在 `actus/vools/actus/actions/` 下新增一个 `.actus.schema.md` 种子文件，front-matter 声明 `kind: <新kind>`，并生成合法 `.sig` 签名 | 种子 + 签名 | `pytest actus/tests/test_seed_signatures.py -q` 绿 |
| **6** | **文档同步**：在 `docs/actus/03-动作规范.md` 的 §2 分类体系章节补充新 kind 的说明 | 文档更新 | 人工 review |

### kind 新增原则

- 单一职责：每个 kind 对应一种执行语义，不重叠
- 向后兼容：新 kind 不影响旧 kind 的现有行为
- 最小权限：新 kind 的默认权限从最低（sandbox）开始，按需提升

---

## 三、通用约束

- **不许跳过回归用例**：任何形态/kind 新增必须有对应测试，且测试在 CI 通过
- **不许破坏已有签名**：种子动作的 `.sig` 文件是安全凭证，重新生成需同步更新 `~/.actus/keys/` 密钥对
- **版本号同步**：修改 `pyproject.toml` 版本号时，同步检查 `actus/vools/actus/__init__.py` 的兜底值是否一致
- **PYTHONPATH 隔离**：CLI 测试子进程必须显式设置 `PYTHONPATH` 指向源码树（`actus/vools/`），避免 import 系统旧装

---

## 四、相关文档

- `docs/actus/03-动作规范.md`：动作分类体系与元数据规范
- `actus/vools/actus/resolver.py`：target 形态解析实现
- `actus/vools/actus/constants.py`：KIND_LEVELS 常量
- `actus/vools/actus/validate.py`：verify 规则实现
- `actus/vools/actus/executor.py`：kind 分发实现
