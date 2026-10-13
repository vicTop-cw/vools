# vools.actus.ai —— Actus 的 AI 决策层

## 这个包解决什么

Actus 有 **110 个动作、零行 LLM 调用代码、五套互不知道对方存在的关键词搜索器**。

用户说「把这段 JSON 的 a.b 取出来」，Actus 自己不知道该调哪个动作、参数怎么填。本包补的就是这一层。

### 它**不是**什么

| 不是什么 | 那个位子归谁 |
|---|---|
| 编码代理（aider 式读写文件 + git commit） | `actus.loop_prompt` —— 已驱动外部 agent CLI（atomcode/hermes）做这件事 |
| 任务状态机 / 看门狗 / 成本预算 / DAG 调度 | FIST-MBT（147 个工具），Actus 侧经 `actus.system.fist_mbt` 适配层调用。其 `ARCHITECTURE.md:77` 明写「绝不让 LLM 自评」 |
| 向量检索 / embedding | 刻意不做。体检必须纯离线可跑、结果可复现 |

## 四件事

| 模块 | 职责 | 关键入口 |
|---|---|---|
| `catalog` | 动作索引 → LLM 工具目录 + 重复检测 | `build_catalog()` `detect_duplicates()` `grep()` |
| `selector` | 意图 → 动作 + 参数填充 | `Selector.select()` `validate_params()` |
| `gaps` | 造新动作前先查重 + 市场体检 | `find_similar()` `analyze_market()` `health_report()` |
| `planner` | 任务拆解（接 `selfdrive` 的 `planner=` 插槽） | `LlmPlanner.decompose()` |
| `base` | 协议与数据模型 | `LLMClient` `ToolSpec` `Message` `LLMResponse` |
| `registry` + `providers` | provider 注册表与实现 | `get_provider()` `PRESETS` |
| `session` | 会话状态 / token 预算 / 事件流 | `AgentSession` |

## 快速上手

### 查重：造动作之前先问一遍

```python
>>> from vools.actus.ai import find_similar
>>> rep = find_similar('把 Markdown 转成 docx',
...                    catalog=build_catalog(meta_dir='<Actus仓库>/_meta'))
>>> rep.verdict
'compose'          # reuse=直接复用 / compose=建议 workflow 组合 / gap=确实缺
>>> rep.advice
'有 2 个相似动作（最高 cli.pandoc，相似度 0.90），建议用 workflow 组合而不是新造。'
```

### 体检：看看市场上有哪些重复

```python
>>> from vools.actus.ai import analyze_market, health_report
>>> print(health_report())
动作市场体检（110 个动作）
一、同能力多实现：8 组
  [cli.curl] actus.cli.curl / cli.curl
  [cli.jq] actus.cli.jq / cli.jq
  ...
```

### 选动作：意图 → 动作 + 参数

```python
>>> from vools.actus.ai import Selector, get_provider, build_catalog
>>> sel = Selector(get_provider('deepseek'), build_catalog(meta_dir=META))
>>> got = sel.select('取 json 里的 a.b 字段')
>>> got.action_id, got.arguments, got.needs_confirm
('cli.jq', {'input': '...', 'filter': '.a.b'}, False)
```

### 拆解：替换 selfdrive 的硬编码模板

```python
>>> from vools.actus.ai import LlmPlanner
>>> from vools.actus import selfdrive
>>> planner = LlmPlanner(get_provider('deepseek'))
>>> plan = planner.decompose('给 REST API 加上鉴权', max_steps=4)
>>> for s in plan.steps:
...     print(s.id, s.title, s.target_action, s.verify)
```

下游接线写法（Actus 仓库侧，本包不碰）：

```python
selfdrive.Decomposer(planner=LlmPlanner(...).decompose).decompose(goal)
```

## ⚠️ 调用前必读：meta_dir 要显式传

**vools-actus 自己没有 `actions/` 目录** —— 动作全在 Actus 仓库里。所以
`indexer.load_index()` 用默认 `_repo_root()` 会扫到空目录（实测返回 0 个动作）。

必须显式传入 Actus 仓库的 `_meta`：

```python
>>> from vools.actus.ai import build_catalog
>>> len(build_catalog())                       # 没传 → 0，本仓库没有 actions/
0
>>> len(build_catalog(meta_dir='E:/…/Actus/_meta'))
110
```

`find_similar()` / `analyze_market()` 不传 catalog 时会惰性调用 `load_catalog()`，
同样吃这个限制。

## 两条安全边界（不要为了「聪明」而放松）

1. **候选集有上限**（`Selector(max_candidates=24)`）。先把 110 个工具全塞进
   prompt 既贵又会稀释注意力，所以先 `catalog.grep()` 粗筛再交给模型。
2. **模型给的 `action_id` 必须回查目录**。模型会编造不存在的动作 id ——
   当成有效选择返回，等于把「调用不存在的东西」这件事说成了真的。
   命中目录外会返回 `error='hallucinated'` 并降级为候选。

另有一条：`confidence < threshold` 时返回 `needs_confirm=True` 且 `candidates` 非空，
**不许瞎猜一个动作**。

## 错误码约定

LLM 侧语义**归一到 `vools.actus.errors.ERROR_CODES` 里既有的 13 个码**，本包不新增：

| LLM 错误类别 | ActionError.code |
|---|---|
| 密钥缺失 / 401 / 403 | `auth_required` |
| 429 / 配额耗尽 | `dependency_missing` |
| DNS / 连接失败 / 超时 | `dependency_missing` |
| 非 JSON / 缺 choices / 形状不符 | `internal` |
| 参数不合法（如 `stream=True` 未实现） | `param_invalid` |
| provider 名未登记 | `param_invalid` |

契约上 **`complete()` 永不抛异常**：失败一律编码成
`LLMResponse(stop_reason='error')`，错误类别与码放在 `resp.raw['error_kind'/'code']`。
`available()` 同样不得抛 —— doctor 与动作前置校验会无保护调用它。

## 本期不做（防越界）

| 不做 | 理由 |
|---|---|
| 第三方 LLM SDK（openai/anthropic/httpx） | 只用标准库 urllib。vools-actus 的依赖面不容许为 AI 层加重 SDK |
| 流式 token 输出 | Actus 执行模型是「跑完 → 打印一次 JSON」，无增量通道。`stream=True` 显式报未实现，不静默降级 |
| embedding / 向量检索 | 确定性算法够用，且体检必须离线可跑 |
| 改 `indexer.py` / `registry.py` / `errors.py` | 本包只在 `ai/` 内活动。缺能力写 adapter 层 |
| 接 `selfdrive.Decomposer` | 属 Actus 仓库的事，本包只提供协议与实现 |

## 测试

```powershell
python -m pytest tests/test_ai_catalog.py tests/test_ai_registry.py `
    tests/test_ai_selector.py tests/test_ai_gaps.py tests/test_ai_session.py -v
```

全程**不依赖网络与 API key**，用假 client。依赖真实 Actus 索引的用例在找不到
`_meta` 时自动 skip（不硬编码机器路径，可用环境变量 `ACTUS_ACTUS_META_DIR` 指定）。

> `tests/_ai_local_bootstrap.py` 解决一个**仓库既有的环境问题**：`vools` 是
> namespace package，已安装的 wheel 排在本地源码树之前，导致 `import vools.actus`
> 拿到的是发布版而非本地代码（实测既有测试 `test_actions_direct.py` 连收集都失败）。
> 该模块把手工装成 editable 等效的 `__path__`，**不改环境**。
> 设 `VOOLS_ACTUS_NO_BOOTSTRAP=1` 可关闭。
