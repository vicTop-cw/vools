"""vools.actus — Actus 动作引擎核心。

迁移自 Actus engine/actuscore/，提供：
- 动作数据模型（Action）
- 元数据解析（parse_cfg）
- 错误类型（ActionError）
- 平台常量（TRUST_LEVELS, PLATFORMS）
- Frontmatter 剥离
- 依赖解析
- 执行器、工作流、注册表等核心功能
"""

from .errors import ActionError, ERROR_CODES
from .constants import TRUST_LEVELS, PLATFORMS, PERMISSIONS, ALLOWED_PLATFORM_DIRS, SCOPE_LEVELS
from .frontmatter import strip_frontmatter
from .model import Action, parse_cfg, parse_cfg_from_file
from .dependency import Dependency, DependencyResolver, get_resolver
from .executor import execute, preview, new_exec_id
from .validate import validate_action, validate_graph
from .trust import decide, check_permissions
from .vault import Vault, set_key, get_key, delete_key, list_keys, resolve_secrets
from .runtimes import RuntimeRegistry, execute_block, get_available_runtimes
from .workflow import Workflow, WorkflowExecutor, DAGScheduler, run_workflow
from .registry import ActionRegistry, RegistryEntry, build_registry, search_registry
from .indexer import scan_actions, load_index, get_action, _repo_root
from .records import write_run_record, append_log, load_run_record, load_status
from .omega import verify_output, compute_output_fingerprint
from .concurrency import get_manager
from .eventbus import EventBus, EventType, get_event_bus
from .sandbox import prepare, sandbox_env, guard_write, cleanup
from .scaffold import scaffold_action, list_templates, match_template
from .trust_model import TrustEvaluator, KeyManager, SignatureVerifier, ScopeEnforcer
from .visibility import VisibilityEngine
from .security import SecurityScanner, AuditLogger, SensitiveInfoDetector
from .adapter import AdapterSpec, CLIAdapter, HTTPAdapter, QuickerAdapter, MCPAdapter
from .installer import ActionInstaller
from .evolution import EvolutionEngine
from .selfheal import SelfHealingEngine
from .template import create_action_from_template, list_templates
from .export import export_history
from .project import ProjectOrchestrator, ProjectConfig, detect_and_init
from .project_io import export_project, import_project
from .viz import visualize_workflow
from .notify import NotificationManager, get_notification_manager
from .health import run_health_check, HealthChecker
from .highlight import highlight_code
from .importsys import ImportResolver, resolve_imports_for_action, check_imports_available
from .jump import push, pull, sync, compute_sync_plan
from .webhook import WebhookReceiver, create_receiver, start_webhook
from .triggers import TriggerEngine, CronScheduler, FileWatcher, parse_triggers, validate_trigger
from .intent import IntentRouter
from .author import author_action, publish_action, Pipeline, run_pipeline
from .loophelpers import fingerprint, clipboard_write, clipboard_clear, focus_window, run_playback

# 分组导出（便于维护，__all__ 在下方聚合）
_base = [
    'ActionError', 'ERROR_CODES',
    'TRUST_LEVELS', 'PLATFORMS', 'PERMISSIONS', 'ALLOWED_PLATFORM_DIRS', 'SCOPE_LEVELS',
    'strip_frontmatter',
]
_model = [
    'Action', 'parse_cfg', 'parse_cfg_from_file',
    'Dependency', 'DependencyResolver', 'get_resolver',
]
_exec = [
    'execute', 'preview', 'new_exec_id',
    'validate_action', 'validate_graph',
    'decide', 'check_permissions',
    'Vault', 'set_key', 'get_key', 'delete_key', 'list_keys', 'resolve_secrets',
    'RuntimeRegistry', 'execute_block', 'get_available_runtimes',
]
_workflow = [
    'Workflow', 'WorkflowExecutor', 'DAGScheduler', 'run_workflow',
]
_registry = [
    'ActionRegistry', 'RegistryEntry', 'build_registry', 'search_registry',
    'scan_actions', 'load_index', 'get_action',
]
_records = [
    'write_run_record', 'append_log', 'load_run_record', 'load_status',
    'verify_output', 'compute_output_fingerprint',
]
_concurrency = [
    'get_manager',
    'EventBus', 'EventType', 'get_event_bus',
]
_sandbox = [
    'prepare', 'sandbox_env', 'guard_write', 'cleanup',
]
_trust = [
    'TrustEvaluator', 'KeyManager', 'SignatureVerifier', 'ScopeEnforcer',
]
_security = [
    'VisibilityEngine',
    'SecurityScanner', 'AuditLogger', 'SensitiveInfoDetector',
]
_adapter = [
    'AdapterSpec', 'CLIAdapter', 'HTTPAdapter', 'QuickerAdapter', 'MCPAdapter',
]
_install = [
    'ActionInstaller',
    'EvolutionEngine',
]
_selfheal = [
    'SelfHealingEngine',
    'create_action_from_template', 'list_templates',
]
_project = [
    'export_history',
    'ProjectOrchestrator', 'ProjectConfig', 'detect_and_init',
    'export_project', 'import_project',
]
_notify = [
    'visualize_workflow',
    'NotificationManager', 'get_notification_manager',
]
_health = [
    'run_health_check', 'HealthChecker',
    'highlight_code',
]
_jump = [
    'push', 'pull', 'sync', 'compute_sync_plan',
]
_webhook = [
    'WebhookReceiver', 'create_receiver', 'start_webhook',
]
_intent = [
    'IntentRouter',
]

__all__ = (
    _base + _model + _exec + _workflow + _registry + _records
    + _concurrency + _sandbox + _trust + _security + _adapter
    + _install + _selfheal + _project + _notify + _health
    + _jump + _webhook + _intent
)
