"""vools.actus — Actus 动作引擎核心。

迁移自 Actus engine/actuscore/，提供：
- 动作数据模型（Action）
- 元数据解析（parse_cfg）
- 错误类型（ActionError）
- 平台常量（TRUST_LEVELS, PLATFORMS）
- Frontmatter 剥离
- 依赖解析
- 执行器、工作流、注册表等核心功能

性能说明：本包 __init__ 采用惰性加载（PEP 562 模块级 __getattr__）。
仅 errors/constants/frontmatter/model/dependency 等轻量基座立即导入，
executor/workflow/webhook/triggers 等重型子模块在首次访问对应符号时才按需导入，
避免 `import vools.actus`（如 CLI -help 路径）加载全家桶拖慢启动。
"""

import importlib as _importlib

from .errors import ActionError, ERROR_CODES
from .constants import TRUST_LEVELS, PLATFORMS, PERMISSIONS, ALLOWED_PLATFORM_DIRS, SCOPE_LEVELS
from .frontmatter import strip_frontmatter
from .model import Action, parse_cfg, parse_cfg_from_file
from .dependency import Dependency, DependencyResolver, get_resolver

# 惰性符号表：{导出名: 子模块名}，首次访问时才 import 对应子模块并取属性
_LAZY = {
    # executor
    'execute': '.executor', 'preview': '.executor', 'new_exec_id': '.executor',
    # validate
    'validate_action': '.validate', 'validate_graph': '.validate',
    # trust
    'decide': '.trust', 'check_permissions': '.trust',
    # vault
    'Vault': '.vault', 'set_key': '.vault', 'get_key': '.vault',
    'delete_key': '.vault', 'list_keys': '.vault', 'resolve_secrets': '.vault',
    # runtimes
    'RuntimeRegistry': '.runtimes', 'execute_block': '.runtimes',
    'get_available_runtimes': '.runtimes',
    # workflow
    'Workflow': '.workflow', 'WorkflowExecutor': '.workflow',
    'DAGScheduler': '.workflow', 'run_workflow': '.workflow',
    # registry
    'ActionRegistry': '.registry', 'RegistryEntry': '.registry',
    'build_registry': '.registry', 'search_registry': '.registry',
    # indexer
    'scan_actions': '.indexer', 'load_index': '.indexer',
    'get_action': '.indexer', '_repo_root': '.indexer',
    # records
    'write_run_record': '.records', 'append_log': '.records',
    'load_run_record': '.records', 'load_status': '.records',
    # omega
    'verify_output': '.omega', 'compute_output_fingerprint': '.omega',
    # concurrency
    'get_manager': '.concurrency',
    # eventbus
    'EventBus': '.eventbus', 'EventType': '.eventbus', 'get_event_bus': '.eventbus',
    # sandbox
    'prepare': '.sandbox', 'sandbox_env': '.sandbox',
    'guard_write': '.sandbox', 'cleanup': '.sandbox',
    # scaffold
    'scaffold_action': '.scaffold', 'match_template': '.scaffold',
    # trust_model
    'TrustEvaluator': '.trust_model', 'KeyManager': '.trust_model',
    'SignatureVerifier': '.trust_model', 'ScopeEnforcer': '.trust_model',
    # visibility
    'VisibilityEngine': '.visibility',
    # security
    'SecurityScanner': '.security', 'AuditLogger': '.security',
    'SensitiveInfoDetector': '.security',
    # adapter
    'AdapterSpec': '.adapter', 'CLIAdapter': '.adapter', 'HTTPAdapter': '.adapter',
    'QuickerAdapter': '.adapter', 'MCPAdapter': '.adapter',
    # installer / evolution
    'ActionInstaller': '.installer', 'EvolutionEngine': '.evolution',
    # selfheal
    'SelfHealingEngine': '.selfheal',
    # template（list_templates 最终语义来自 template 模块，与旧版后导入覆盖一致）
    'create_action_from_template': '.template', 'list_templates': '.template',
    # export
    'export_history': '.export',
    # project / project_io
    'ProjectOrchestrator': '.project', 'ProjectConfig': '.project',
    'detect_and_init': '.project',
    'export_project': '.project_io', 'import_project': '.project_io',
    # viz
    'visualize_workflow': '.viz',
    # notify
    'NotificationManager': '.notify', 'get_notification_manager': '.notify',
    # health
    'run_health_check': '.health', 'HealthChecker': '.health',
    # highlight
    'highlight_code': '.highlight',
    # importsys
    'ImportResolver': '.importsys', 'resolve_imports_for_action': '.importsys',
    'check_imports_available': '.importsys',
    # jump
    'push': '.jump', 'pull': '.jump', 'sync': '.jump',
    'compute_sync_plan': '.jump',
    # webhook
    'WebhookReceiver': '.webhook', 'create_receiver': '.webhook',
    'start_webhook': '.webhook',
    # triggers
    'TriggerEngine': '.triggers', 'CronScheduler': '.triggers',
    'FileWatcher': '.triggers', 'parse_triggers': '.triggers',
    'validate_trigger': '.triggers',
    # intent
    'IntentRouter': '.intent',
    # author
    'author_action': '.author', 'publish_action': '.author',
    'Pipeline': '.author', 'run_pipeline': '.author',
    # loophelpers
    'fingerprint': '.loophelpers', 'clipboard_write': '.loophelpers',
    'clipboard_clear': '.loophelpers', 'focus_window': '.loophelpers',
    'run_playback': '.loophelpers',
}


def __getattr__(name):
    # sigma：docs/41 主题 A，sigma-Law 规范引擎以子包形式导出（vools.actus.sigma）
    if name == 'sigma':
        return _importlib.import_module('.sigma', __name__)
    mod_name = _LAZY.get(name)
    if mod_name:
        module = _importlib.import_module(mod_name, __name__)
        attr = getattr(module, name, None)
        if attr is not None:
            return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY) | {'sigma'})


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
# docs/41 主题 A：sigma-Law 规范引擎以子包形式导出（vools.actus.sigma）。
# 只挂名字、不批量 re-export 其符号，避免 `sigma` 这类通用名污染 vools.actus 命名空间。
_sigma = [
    'sigma',
]

__all__ = (
    _base + _model + _exec + _workflow + _registry + _records
    + _concurrency + _sandbox + _trust + _security + _adapter
    + _install + _selfheal + _project + _notify + _health
    + _jump + _webhook + _intent + _sigma
)
