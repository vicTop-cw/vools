"""vools.actus.ai —— Actus 的 AI 决策层。

解决的问题：**Actus 有 109 个动作、零行 LLM 调用代码、五套互不知道对方
存在的关键词搜索器。**用户说「把这段 JSON 的 a.b 取出来」，Actus 自己
不知道该调哪个动作、参数怎么填。本包补的就是这一层。

它**不是**编码代理：那个位子已由 `actus.loop_prompt`（驱动外部 agent
CLI）占据；也不是任务状态机：那个位子由 FIST-MBT（147 个工具，Actus 侧
经 `actus.system.fist_mbt` 适配层调用）占据。

四件事：

| 模块 | 职责 |
|---|---|
| `catalog` | 动作索引 → LLM 工具目录（`ToolSpec` 直接吃动作 `args` schema，零转换） |
| `selector` | 意图 → 动作 + 参数填充（取代关键词打分器） |
| `gaps` | 造新动作前先查重（`find_similar`）+ 市场体检（`analyze_market`） |
| `planner` | 任务拆解协议（Actus `selfdrive.Decomposer` 的 `planner=` 插槽） |

Example:
    >>> from vools.actus.ai import build_catalog, analyze_market
    >>> market = analyze_market()          # doctest: +SKIP
    >>> len(market['duplicates']['exact']) > 0    # doctest: +SKIP
    True
"""

__all__ = [
    # 协议与模型
    'LLMClient', 'LLMResponse', 'Message', 'ToolSpec', 'ToolCall',
    'Role', 'StopReason', 'ErrorKind', 'ERROR_MAP', 'llm_error_code',
    # provider
    'register_provider', 'get_provider', 'available_providers', 'PRESETS',
    # 工具目录
    'ToolCatalog', 'CatalogEntry', 'build_catalog', 'load_catalog',
    'normalize_tool_name', 'detect_duplicates',
    # 查重
    'GapReport', 'find_similar', 'analyze_market', 'health_report',
    # 意图选择
    'Selector', 'Selection',
    # 拆解
    'Planner', 'LlmPlanner', 'Plan', 'PlanStep', 'plan_from_intent',
    # 会话
    'AgentSession', 'SessionEvent', 'session_path',
    # 用量记账（成本账本的写入通道）
    'usage_record_stats',
]

from .base import (
    LLMClient, LLMResponse, Message, ToolSpec, ToolCall,
    Role, StopReason, ErrorKind, ERROR_MAP, llm_error_code,
    usage_record_stats,
)
from .registry import register_provider, get_provider, available_providers, PRESETS
from .catalog import (
    ToolCatalog, CatalogEntry, build_catalog, load_catalog,
    normalize_tool_name, detect_duplicates,
)
from .gaps import GapReport, find_similar, analyze_market, health_report
from .selector import Selector, Selection
from .planner import Planner, LlmPlanner, Plan, PlanStep, plan_from_intent
from .session import AgentSession, SessionEvent, session_path