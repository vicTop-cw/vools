"""聚合 MCP server（docs/06）：把动作仓库动态映射为 MCP tools，stdio JSON-RPC 2.0。

零第三方依赖（不装 mcp/fastmcp 也能被任意 MCP 客户端接入）：
- initialize / tools/list / tools/call / notifications/*；
- 每个有效动作 → 一个 tool（name = 动作 id 规范化），inputSchema 取自动作 args
  契约（docs/06 §1：禁止在执行核心之外二次维护参数定义）；
- 另暴露管理工具 actus_list / actus_info / actus_status / actus_preview /
  actus_confirm；
- audit 级动作未确认时返回 awaiting_confirmation（docs/07 §2 安全边界：
  MCP 只映射与转发，信任判定始终在执行核心）。

协议帧：按行分隔的 JSON（LSP-style Content-Length 头也兼容解析）。
"""

__all__ = ['serve', 'MCPServer']

import io
import json
import os
import re
import sys
from typing import Optional

PROTOCOL_VERSION = '2024-11-05'
SERVER_INFO = {'name': 'actus-mcp', 'version': '0.1.0'}

# 管理工具（固定映射）
ADMIN_TOOLS = ('actus_list', 'actus_info', 'actus_status', 'actus_preview',
               'actus_confirm', 'actus_scaffold', 'actus_author', 'actus_publish',
               'actus_deps', 'actus_dep_tree')


def _tool_name(action_id: str) -> str:
    """actus.hello → actus_hello（docs/06 §1 规范化）。"""
    return re.sub(r'[^a-zA-Z0-9_]', '_', action_id)


def text_result(payload: dict, is_error: bool = False) -> dict:
    """统一 MCP tool 调用返回格式。"""
    return {
        'content': [{'type': 'text',
                     'text': json.dumps(payload, ensure_ascii=False, indent=2)}],
        'isError': is_error,
    }


def _input_schema(brief: dict) -> dict:
    """动作 args 契约 → MCP inputSchema（未声明时宽松透传 object）。"""
    args = brief.get('args')
    if isinstance(args, dict) and args:
        return args
    return {
        'type': 'object',
        'properties': {
            'args': {'type': 'object', 'description': '传给动作的参数（透传）'},
        },
    }


class MCPServer:
    """stdio JSON-RPC 2.0 server。handler 抽象便于测试与复用。"""

    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin or sys.stdin.buffer
        self.stdout = stdout or sys.stdout.buffer
        self._log_level = 'info'
        self._setup_event_forwarding()

    def _setup_event_forwarding(self):
        """设置事件总线到 MCP notification 的转发。"""
        try:
            from vools.actus.eventbus import EventType, get_event_bus
            bus = get_event_bus()
            
            def _on_action_completed(event):
                self._notify('actus/actionCompleted', {
                    'action_id': event.data.get('action_id'),
                    'exec_id': event.data.get('exec_id'),
                    'result': event.data.get('result'),
                })
            
            def _on_action_failed(event):
                self._notify('actus/actionFailed', {
                    'action_id': event.data.get('action_id'),
                    'exec_id': event.data.get('exec_id'),
                    'error': event.data.get('error'),
                })
            
            bus.subscribe(EventType.ACTION_COMPLETED, _on_action_completed)
            bus.subscribe(EventType.ACTION_FAILED, _on_action_failed)
        except Exception:
            pass  # 事件总线不可用时静默跳过

    # ── 协议层 ──
    def serve_forever(self) -> None:
        for line in self._read_messages():
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                self._write({'jsonrpc': '2.0', 'id': None, 'error': {
                    'code': -32700, 'message': f'Parse error: {e}'}})
                continue
            response = self.handle(msg)
            if response is not None:
                self._write(response)

    def _read_messages(self):
        """逐行读；兼容 LSP-style Content-Length 帧。"""
        pending_len = None
        while True:
            raw = self.stdin.readline()
            if not raw:
                return
            s = raw.decode('utf-8', errors='replace').strip()
            m = re.match(r'Content-Length:\s*(\d+)', s, re.IGNORECASE)
            if m:
                pending_len = int(m.group(1))
                continue
            if pending_len is not None:
                body = raw[:pending_len]
                pending_len = None
                yield body
                continue
            yield raw

    def _write(self, obj: dict) -> None:
        self.stdout.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))
        self.stdout.write(b'\n')
        self.stdout.flush()

    def _notify(self, method: str, params: dict):
        """发送 MCP notification 到客户端。"""
        self._write({'jsonrpc': '2.0', 'method': method, 'params': params})

    # ── 分发层 ──
    def handle(self, msg: dict) -> Optional[dict]:
        method = msg.get('method', '')
        msg_id = msg.get('id')
        params = msg.get('params') or {}

        if method.startswith('notifications/'):
            if method == 'notifications/initialized':
                self._log_level = 'info'
            return None  # 通知无需应答

        try:
            if method == 'initialize':
                result = {
                    'protocolVersion': PROTOCOL_VERSION,
                    'capabilities': {
                        'tools': {'listChanged': True},
                        'prompts': {'listChanged': True},
                        'resources': {'subscribe': False},
                        'logging': {},
                    },
                    'serverInfo': SERVER_INFO,
                }
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': self._list_tools()}
            elif method == 'tools/call':
                result = self._call_tool(params)
            elif method == 'prompts/list':
                result = {'prompts': self._list_prompts()}
            elif method == 'prompts/get':
                result = self._get_prompt(params)
            elif method == 'resources/list':
                result = {'resources': self._list_resources()}
            elif method == 'resources/read':
                result = self._read_resource(params)
            elif method == 'logging/setLevel':
                self._log_level = params.get('level', 'info').lower()
                result = {}
            elif method == 'completion/complete':
                result = self._complete(params)
            else:
                return self._err(msg_id, -32601, f'Method not found: {method}')
        except Exception as e:  # noqa: BLE001 —— 协议层收敛为 internal error
            return self._err(msg_id, -32603, str(e),
                             {'type': type(e).__name__})

        return {'jsonrpc': '2.0', 'id': msg_id, 'result': result}

    @staticmethod
    def _err(msg_id, code: int, message: str, data=None) -> dict:
        err = {'code': code, 'message': message}
        if data is not None:
            err['data'] = data
        return {'jsonrpc': '2.0', 'id': msg_id, 'error': err}

    # ── 工具层 ──
    def _list_tools(self) -> list:
        import vools.actus
        idx = actuscore.load_index()
        tools = []
        for aid, brief in idx['actions'].items():
            if aid.startswith('_invalid:') or brief.get('status') != 'valid':
                continue  # docs/05 §5.1：不合规动作自动下架
            desc = brief.get('description') or brief.get('name') or aid
            trust = brief.get('trust')
            if trust:
                desc = f'[{trust}] {desc}'
            # docs/10 §A.3：拼接 usage 字段，供 AI 理解用法
            usage = brief.get('usage')
            if usage:
                desc = f'{desc}\n\n【用法】\n{usage}'
            tools.append({
                'name': _tool_name(aid),
                'description': desc,
                'inputSchema': _input_schema(brief),
            })

        tools.extend([
            {'name': 'actus_list',
             'description': '列出全部可用动作（id/name/version/trust/tags）',
             'inputSchema': {'type': 'object', 'properties': {
                 'tag': {'type': 'string', 'description': '按标签过滤（逗号分隔）'}}}},
            {'name': 'actus_search',
             'description': '搜索动作（支持标签、关键词、作者过滤）',
             'inputSchema': {'type': 'object', 'properties': {
                 'query': {'type': 'string', 'description': '搜索关键词'},
                 'tag': {'type': 'string', 'description': '标签过滤（逗号分隔）'},
                 'author': {'type': 'string', 'description': '作者过滤'},
                 'limit': {'type': 'integer', 'description': '最大返回数', 'default': 20}}}},
            {'name': 'actus_recommend',
             'description': '根据任务描述推荐最相关的动作（语义匹配）',
             'inputSchema': {'type': 'object', 'properties': {
                'description': {'type': 'string', 'description': '任务描述（自然语言）'},
                'limit': {'type': 'integer', 'description': '最大推荐数'}}}},
            {'name': 'actus_info',
             'description': '查看动作元数据与依赖',
             'inputSchema': {'type': 'object', 'required': ['id'],
                             'properties': {'id': {'type': 'string'}}}},
            {'name': 'actus_status',
             'description': '查询执行状态（缺省 = 最近汇总；可传 exec_id）',
             'inputSchema': {'type': 'object',
                             'properties': {'exec_id': {'type': 'string'}}}},
            {'name': 'actus_preview',
             'description': '干跑：展示将执行的块/指令/依赖，不执行',
             'inputSchema': {'type': 'object', 'required': ['id'],
                             'properties': {'id': {'type': 'string'},
                                            'args': {'type': 'object'}}}},
            {'name': 'actus_confirm',
             'description': '人类确认通道：对 awaiting_confirmation 的 exec 放行重跑',
             'inputSchema': {'type': 'object', 'required': ['exec_id'],
                             'properties': {'exec_id': {'type': 'string'}}}},
            {'name': 'actus_scaffold',
             'description': 'AI 写动作：根据自然语言描述生成动作骨架（默认 trust=audit，需人类确认）',
             'inputSchema': {'type': 'object', 'required': ['description'],
                             'properties': {
                                 'description': {'type': 'string',
                                                  'description': '动作用途的自然语言描述'},
                                 'action_id': {'type': 'string',
                                               'description': '指定动作 id（缺省自动生成）'},
                                 'trust': {'type': 'string', 'enum': ['audit', 'trusted', 'sandbox'],
                                           'description': '信任级别（默认 audit）'},
                             }}},
            {'name': 'actus_author',
             'description': 'AI 改动作：根据自然语言指令修改已有动作的代码块或元数据',
             'inputSchema': {'type': 'object', 'required': ['action_id', 'instruction'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '要修改的动作 id'},
                                 'instruction': {'type': 'string',
                                                  'description': '修改指令（自然语言）'},
                             }}},
            {'name': 'actus_publish',
             'description': '发布动作：校验通过 → 入索引 → 上 MCP（audit 级需 --force 或人类确认）',
             'inputSchema': {'type': 'object', 'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '要发布的动作 id'},
                                 'force': {'type': 'boolean',
                                           'description': '强制发布（跳过人类确认，需配置 auto_promote）'},
                             }}},
            {'name': 'actus_workflow_run',
             'description': '运行工作流：根据工作流动作 id 触发 DAG 执行',
             'inputSchema': {'type': 'object', 'required': ['workflow_id'],
                             'properties': {
                                 'workflow_id': {'type': 'string',
                                                  'description': '要运行的工作流动作 id'},
                                 'params': {'type': 'object',
                                            'description': '工作流级参数（可选）'},
                                 'max_workers': {'type': 'integer',
                                                  'description': '并行执行线程数（默认 4）'},
                                 'confirmed': {'type': 'boolean',
                                               'description': '是否跳过人类确认（默认 true）'},
                             }}},
            {'name': 'actus_workflow_status',
             'description': '查询工作流执行状态：节点状态、输出、耗时',
             'inputSchema': {'type': 'object', 'required': ['workflow_id'],
                             'properties': {
                                 'workflow_id': {'type': 'string',
                                                  'description': '工作流动作 id'},
                             }}},
            {'name': 'actus_vault_set',
             'description': '存储密钥：加密保存 API key/密码/令牌到保险库',
             'inputSchema': {'type': 'object', 'required': ['key', 'value'],
                             'properties': {
                                 'key': {'type': 'string',
                                         'description': '密钥名称（如 MY_API_KEY）'},
                                 'value': {'type': 'string',
                                           'description': '密钥值（加密存储）'},
                                 'scope': {'type': 'string',
                                           'description': '作用域（默认 global）'},
                                 'description': {'type': 'string',
                                                 'description': '密钥描述（可选）'},
                             }}},
            {'name': 'actus_vault_get',
             'description': '获取密钥：从保险库解密读取密钥值',
             'inputSchema': {'type': 'object', 'required': ['key'],
                             'properties': {
                                 'key': {'type': 'string',
                                         'description': '密钥名称'},
                                 'scope': {'type': 'string',
                                           'description': '作用域（默认 global）'},
                             }}},
            {'name': 'actus_vault_list',
             'description': '列出密钥：显示所有已存储密钥的元数据（不含值）',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'scope': {'type': 'string',
                                           'description': '作用域过滤（可选）'},
                             }}},
            {'name': 'actus_vault_delete',
             'description': '删除密钥：从保险库中移除指定密钥',
             'inputSchema': {'type': 'object', 'required': ['key'],
                             'properties': {
                                 'key': {'type': 'string',
                                         'description': '密钥名称'},
                                 'scope': {'type': 'string',
                                           'description': '作用域（默认 global）'},
                             }}},
            {'name': 'actus_dep_tree',
             'description': '查看动作依赖树：递归展示动作的所有依赖及其状态',
             'inputSchema': {'type': 'object',
                             'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                             }}},
            {'name': 'actus_deps',
             'description': '检查动作依赖：验证动作的所有依赖是否满足，支持自动修复',
             'inputSchema': {'type': 'object',
                             'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                                 'auto_install': {'type': 'boolean',
                                                  'description': '是否自动安装缺失依赖（默认 false）'},
                             }}},
            {'name': 'actus_runtimes',
             'description': '列出所有可用的多语言运行时（python/shell/node/go/rust/ruby/php）',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_triggers_list',
             'description': '列出所有已注册的触发器（cron/watch/webhook/hotkey）',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '按动作 id 过滤（可选）'},
                             }}},
            {'name': 'actus_triggers_add',
             'description': '注册触发器：为动作添加 cron/watch/webhook/hotkey 触发器',
             'inputSchema': {'type': 'object',
                             'required': ['action_id', 'type'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '要触发的动作 id'},
                                 'type': {'type': 'string',
                                          'description': '触发器类型：cron/watch/webhook/hotkey/on_startup'},
                                 'expr': {'type': 'string',
                                          'description': 'cron 表达式（cron 类型必填）'},
                                 'path': {'type': 'string',
                                          'description': '监控路径（watch 类型必填）'},
                                 'events': {'type': 'array',
                                            'items': {'type': 'string'},
                                            'description': '监控事件（watch 类型，默认 create,modify）'},
                                 'recursive': {'type': 'boolean',
                                               'description': '是否递归监控子目录'},
                                 'key': {'type': 'string',
                                         'description': '热键组合（hotkey 类型必填）'},
                                 'args': {'type': 'object',
                                          'description': '触发时传递给动作的参数'},
                             }}},
            {'name': 'actus_triggers_remove',
             'description': '移除触发器：删除指定动作的触发器',
             'inputSchema': {'type': 'object',
                             'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                             }}},
            {'name': 'actus_triggers_status',
             'description': '查看触发器引擎状态（运行中的任务数、引擎状态）',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_execute',
             'description': '执行代码：直接在指定语言运行时中运行代码片段（python/shell/node/go/rust/ruby/php）',
             'inputSchema': {'type': 'object',
                             'required': ['language', 'code'],
                             'properties': {
                                 'language': {'type': 'string',
                                              'description': '语言：python/shell/node/go/rust/ruby/php'},
                                 'code': {'type': 'string',
                                          'description': '要执行的代码'},
                                 'args': {'type': 'string',
                                          'description': '命令行参数（可选）'},
                                 'stdin': {'type': 'string',
                                           'description': '标准输入（可选）'},
                                 'env': {'type': 'object',
                                         'description': '环境变量（可选）'},
                                 'timeout': {'type': 'integer',
                                             'description': '超时秒数（可选，默认 30）'},
                             }}},
            {'name': 'actus_records_list',
             'description': '列出执行记录：查看历史执行日志（支持按动作过滤、分页）',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '按动作 id 过滤（可选）'},
                                 'limit': {'type': 'integer',
                                           'description': '最多返回条数（默认 50）'},
                                 'offset': {'type': 'integer',
                                            'description': '跳过条数（默认 0）'},
                             }}},
            {'name': 'actus_records_export',
             'description': '导出执行记录：导出为 json/csv/summary 格式',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '按动作 id 过滤（可选）'},
                                 'format': {'type': 'string',
                                            'description': '输出格式：json/csv/summary（默认 json）'},
                                 'output': {'type': 'string',
                                            'description': '输出文件路径（可选）'},
                                 'limit': {'type': 'integer',
                                           'description': '最多导出条数（默认 100）'},
                             }}},
            {'name': 'actus_artifacts_list',
             'description': '列出产物：查看执行产生的文件/数据',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '按动作 id 过滤（可选）'},
                                 'exec_id': {'type': 'string',
                                            'description': '按执行 id 过滤（可选）'},
                                 'type': {'type': 'string',
                                          'description': '按产物类型过滤（可选）'},
                             }}},
            {'name': 'actus_artifacts_cleanup',
             'description': '清理产物：删除过期或过多的产物',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'max_age_days': {'type': 'integer',
                                                  'description': '保留天数（默认 30）'},
                                 'max_count': {'type': 'integer',
                                               'description': '最多保留条数（默认 1000）'},
                             }}},
            {'name': 'actus_evolve',
             'description': '自进化：根据自然语言描述自动生成动作→校验→测试→修复，直到通过',
             'inputSchema': {'type': 'object', 'required': ['description'],
                             'properties': {
                                 'description': {'type': 'string',
                                                  'description': '动作用途的自然语言描述'},
                                 'action_id': {'type': 'string',
                                               'description': '指定动作 id（缺省自动生成）'},
                                 'max_rounds': {'type': 'integer',
                                                'description': '最大修复轮次（默认 5）'},
                                 'expect': {'type': 'object',
                                            'description': '期望条件（exit_code, stdout_contains 等）'},
                             }}},
            {'name': 'actus_evolve_repair',
             'description': '修复已有动作：重新测试并自动修复',
             'inputSchema': {'type': 'object', 'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '要修复的动作 id'},
                                 'max_rounds': {'type': 'integer',
                                                'description': '最大修复轮次（默认 5）'},
                                 'expect': {'type': 'object',
                                            'description': '期望条件'},
                             }}},
            {'name': 'actus_evolve_status',
             'description': '查询进化状态：查看指定动作的进化进度和历史',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                             }}},
            {'name': 'actus_evolve_history',
             'description': '进化历史：查看指定动作的完整进化记录',
             'inputSchema': {'type': 'object', 'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                             }}},
            {'name': 'actus_evolve_rollback',
             'description': '回滚进化：将动作回滚到指定版本',
             'inputSchema': {'type': 'object',
                             'required': ['action_id', 'version'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                                 'version': {'type': 'integer',
                                             'description': '目标版本号'},
                             }}},
            {'name': 'actus_evolve_compare',
             'description': 'A/B 对比：对比动作的两个版本差异',
             'inputSchema': {'type': 'object',
                             'required': ['action_id', 'v1', 'v2'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                                 'v1': {'type': 'integer',
                                        'description': '版本 1'},
                                 'v2': {'type': 'integer',
                                        'description': '版本 2'},
                             }}},
            {'name': 'actus_evolve_list',
             'description': '列出所有有进化历史的动作',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_webhook_start',
             'description': '启动 Webhook 接收器（阻塞模式）',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'host': {'type': 'string',
                                          'description': '监听地址（默认 0.0.0.0）'},
                                 'port': {'type': 'integer',
                                          'description': '监听端口（默认 8765）'},
                                 'secret': {'type': 'string',
                                            'description': 'Webhook 密钥（HMAC-SHA256）'},
                                 'require_signature': {'type': 'boolean',
                                                       'description': '是否要求签名（默认 true）'},
                             }}},
            {'name': 'actus_webhook_start_background',
             'description': '启动 Webhook 接收器（后台非阻塞）',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'host': {'type': 'string',
                                          'description': '监听地址（默认 0.0.0.0）'},
                                 'port': {'type': 'integer',
                                          'description': '监听端口（默认 8765）'},
                                 'secret': {'type': 'string',
                                            'description': 'Webhook 密钥'},
                                 'require_signature': {'type': 'boolean',
                                                       'description': '是否要求签名（默认 true）'},
                             }}},
            {'name': 'actus_webhook_stop',
             'description': '停止 Webhook 接收器',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_webhook_status',
             'description': '查看 Webhook 运行状态和统计',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_webhook_register',
             'description': '注册事件路由',
             'inputSchema': {'type': 'object',
                             'required': ['event_type', 'action_id'],
                             'properties': {
                                 'event_type': {'type': 'string',
                                                'description': '事件类型（如 github.push）'},
                                 'action_id': {'type': 'string',
                                               'description': '触发的动作 id'},
                             }}},
            {'name': 'actus_webhook_unregister',
             'description': '移除事件路由',
             'inputSchema': {'type': 'object',
                             'required': ['event_type'],
                             'properties': {
                                 'event_type': {'type': 'string',
                                                'description': '事件类型'},
                             }}},
            {'name': 'actus_webhook_logs',
             'description': '查看 Webhook 请求日志',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'limit': {'type': 'integer',
                                           'description': '最大返回条数（默认 50）'},
                             }}},
            {'name': 'actus_project_load',
             'description': '加载项目定义文件',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'project_file': {'type': 'string',
                                                  'description': '项目定义文件路径（默认 .actus-project.json）'},
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录（默认当前目录）'},
                             }}},
            {'name': 'actus_project_detect',
             'description': '自动检测项目语言和模块',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录（默认当前目录）'},
                             }}},
            {'name': 'actus_project_build',
             'description': '执行项目构建流水线',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'project_file': {'type': 'string',
                                                  'description': '项目定义文件路径'},
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录'},
                                 'phase': {'type': 'string',
                                           'description': '指定阶段（build/test/deploy/lint）'},
                             }}},
            {'name': 'actus_project_test',
             'description': '执行项目测试',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'project_file': {'type': 'string',
                                                  'description': '项目定义文件路径'},
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录'},
                             }}},
            {'name': 'actus_project_status',
             'description': '查看项目流水线状态',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录'},
                             }}},
            {'name': 'actus_project_validate',
             'description': '验证项目定义',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'project_file': {'type': 'string',
                                                  'description': '项目定义文件路径'},
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录'},
                             }}},
            {'name': 'actus_project_add_module',
             'description': '添加模块到项目',
             'inputSchema': {'type': 'object',
                             'required': ['module_id', 'language', 'path'],
                             'properties': {
                                 'module_id': {'type': 'string',
                                               'description': '模块 id'},
                                 'language': {'type': 'string',
                                              'description': '编程语言'},
                                 'path': {'type': 'string',
                                          'description': '模块路径'},
                                 'build_cmd': {'type': 'string',
                                               'description': '构建命令'},
                                 'test_cmd': {'type': 'string',
                                              'description': '测试命令'},
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录'},
                             }}},
            {'name': 'actus_project_remove_module',
             'description': '从项目移除模块',
             'inputSchema': {'type': 'object',
                             'required': ['module_id'],
                             'properties': {
                                 'module_id': {'type': 'string',
                                               'description': '模块 id'},
                                 'work_dir': {'type': 'string',
                                              'description': '工作目录'},
                             }}},
            {'name': 'actus_visibility_get',
             'description': '查询动作可见性级别',
             'inputSchema': {'type': 'object', 'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                             }}},
            {'name': 'actus_visibility_set',
             'description': '设置动作可见性级别（public/unlisted/private/team）',
             'inputSchema': {'type': 'object',
                             'required': ['action_id', 'visibility'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                                 'visibility': {'type': 'string',
                                                'description': '可见性级别'},
                                 'team': {'type': 'string',
                                          'description': '团队名称（team 级别时必填）'},
                             }}},
            {'name': 'actus_registry_add',
             'description': '添加注册表',
             'inputSchema': {'type': 'object',
                             'required': ['name', 'url'],
                             'properties': {
                                 'name': {'type': 'string',
                                          'description': '注册表名称'},
                                 'url': {'type': 'string',
                                         'description': '注册表 URL'},
                                 'registry_type': {'type': 'string',
                                                   'description': '类型（http/git/private）'},
                                 'branch': {'type': 'string',
                                            'description': '分支（默认 main）'},
                                 'priority': {'type': 'integer',
                                              'description': '优先级（数字越小越优先）'},
                             }}},
            {'name': 'actus_registry_remove',
             'description': '移除注册表',
             'inputSchema': {'type': 'object', 'required': ['name'],
                             'properties': {
                                 'name': {'type': 'string',
                                          'description': '注册表名称'},
                             }}},
            {'name': 'actus_registry_list',
             'description': '列出所有注册表',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_private_list',
             'description': '列出私有动作',
             'inputSchema': {'type': 'object', 'properties': {}}},
            {'name': 'actus_private_add',
             'description': '添加私有动作',
             'inputSchema': {'type': 'object', 'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                                 'author': {'type': 'string',
                                            'description': '作者'},
                                 'path': {'type': 'string',
                                          'description': '本地路径'},
                             }}},
            {'name': 'actus_private_remove',
             'description': '移除私有动作',
             'inputSchema': {'type': 'object', 'required': ['action_id'],
                             'properties': {
                                 'action_id': {'type': 'string',
                                               'description': '动作 id'},
                             }}},
            {'name': 'actus_team_create',
             'description': '创建团队',
             'inputSchema': {'type': 'object',
                             'required': ['name', 'creator'],
                             'properties': {
                                 'name': {'type': 'string',
                                          'description': '团队名称'},
                                 'creator': {'type': 'string',
                                             'description': '创建者用户 id'},
                             }}},
            {'name': 'actus_team_add_member',
             'description': '添加团队成员',
             'inputSchema': {'type': 'object',
                             'required': ['team', 'user_id'],
                             'properties': {
                                 'team': {'type': 'string',
                                          'description': '团队名称'},
                                 'user_id': {'type': 'string',
                                             'description': '用户 id'},
                                 'role': {'type': 'string',
                                          'description': '角色（admin/member/viewer）'},
                             }}},
            {'name': 'actus_team_remove_member',
             'description': '移除团队成员',
             'inputSchema': {'type': 'object',
                             'required': ['team', 'user_id'],
                             'properties': {
                                 'team': {'type': 'string',
                                          'description': '团队名称'},
                                 'user_id': {'type': 'string',
                                             'description': '用户 id'},
                             }}},
            {'name': 'actus_team_list',
             'description': '列出团队',
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'team': {'type': 'string',
                                          'description': '团队名称（可选，不填列出所有）'},
                             }}},
            {'name': 'actus_preview',
             'description': '代码语法高亮预览（Shiki）',
             'inputSchema': {'type': 'object',
                             'required': ['code'],
                             'properties': {
                                 'code': {'type': 'string',
                                          'description': '要高亮的代码'},
                                 'lang': {'type': 'string',
                                          'description': '语言（默认 python）'},
                                 'theme': {'type': 'string',
                                           'description': '主题（默认 github-dark）'},
                                 'mode': {'type': 'string',
                                          'description': '输出模式：terminal 或 html（默认 terminal）'},
                             }}},
        ])
        return tools

    # ── Prompts ──

    def _list_prompts(self) -> list:
        """列出全部可用提示（docs/10 §A.2）。"""
        prompts = [
            {
                'name': 'actus_action_best_practice',
                'description': 'Actus 动作最佳调用提示：如何正确调用动作、处理错误、使用产物',
                'arguments': [],
            },
            {
                'name': 'actus_workflow_guide',
                'description': 'Actus 工作流编排指南：如何定义 DAG、节点重试、条件分支',
                'arguments': [],
            },
            {
                'name': 'actus_scaffold_guide',
                'description': 'Actus 动作骨架生成指南：如何从自然语言描述生成动作',
                'arguments': [
                    {'name': 'description', 'description': '动作用途描述', 'required': True},
                ],
            },
        ]
        return prompts

    def _get_prompt(self, params: dict) -> dict:
        """获取指定提示内容（docs/10 §A.2）。"""
        name = params.get('name', '')
        arguments = params.get('arguments', {})

        prompts = {
            'actus_action_best_practice': {
                'description': 'Actus 动作最佳调用提示',
                'messages': [
                    {
                        'role': 'assistant',
                        'content': {
                            'type': 'text',
                            'text': (
                                'Actus 动作调用最佳实践：\n'
                                '1. 先用 actus_list 查看可用动作\n'
                                '2. 用 actus_info 查看动作元数据和参数契约\n'
                                '3. 用 actus_preview 干跑预览，确认将要执行的块\n'
                                '4. 调用动作时传入正确的参数（符合 args schema）\n'
                                '5. 动作返回 status=ok 表示成功，result.data 包含输出数据\n'
                                '6. 动作返回 status=awaiting_confirmation 表示需要人类确认\n'
                                '7. 动作返回 status=failed 表示失败，检查 error 字段\n'
                                '8. 使用 actus_status 查询执行状态和留痕记录\n'
                                '9. 动作的产物存储在 _meta/artifacts.json 中，可通过 $node.artifacts.name 引用'
                            ),
                        },
                    }
                ],
            },
            'actus_workflow_guide': {
                'description': 'Actus 工作流编排指南',
                'messages': [
                    {
                        'role': 'assistant',
                        'content': {
                            'type': 'text',
                            'text': (
                                'Actus 工作流编排指南：\n'
                                '1. 工作流是一个 .actus.md 文件，元数据中包含 workflow 字段\n'
                                '2. workflow.nodes 定义 DAG 节点，每个节点引用一个动作\n'
                                '3. 节点间通过 depends 声明依赖关系\n'
                                '4. 支持并行执行（graph.parallel=true）和串行执行\n'
                                '5. 节点支持重试策略：retry.max_attempts、backoff_ms、backoff_multiplier\n'
                                '6. 支持条件分支：condition 字段（简单表达式求值）\n'
                                '7. 跨节点数据流转：$node.output.field 引用上游输出\n'
                                '8. 工作流级留痕存储在 _meta/workflows/ 目录'
                            ),
                        },
                    }
                ],
            },
            'actus_scaffold_guide': {
                'description': 'Actus 动作骨架生成指南',
                'messages': [
                    {
                        'role': 'assistant',
                        'content': {
                            'type': 'text',
                            'text': (
                                f'Actus 动作骨架生成指南：\n'
                                f'1. 使用 actus_scaffold 工具，传入自然语言描述\n'
                                f'2. 工具会根据描述关键词匹配合适的模板\n'
                                f'3. 生成的动作默认 trust=audit（需人类确认后才能执行）\n'
                                f'4. 生成后需要填充代码块（entry tag 指向的块）\n'
                                f'5. 填充完成后调用 actus_publish 发布\n'
                                f'6. 当前描述：{arguments.get("description", "")}'
                            ),
                        },
                    }
                ],
            },
        }

        if name not in prompts:
            from vools.actus.errors import ActionError
            raise ActionError('prompt_not_found', f'Prompt not found: {name}')

        return {'description': prompts[name]['description'],
                'messages': prompts[name]['messages']}

    # ── Resources ──

    def _list_resources(self) -> list:
        """列出全部可用资源（docs/10 §A.2）。"""
        import vools.actus
        resources = []

        # 索引资源
        resources.append({
            'uri': 'actus://index',
            'name': '动作索引',
            'description': '当前仓库的全部动作索引（只读）',
            'mimeType': 'application/json',
        })

        # 状态资源
        resources.append({
            'uri': 'actus://status',
            'name': '执行状态',
            'description': '最近执行状态汇总（只读）',
            'mimeType': 'application/json',
        })

        # 执行记录资源
        try:
            from vools.actus import records as rec
            status = rec.load_status(None)
            for eid in status.get('recent', [])[:10]:
                resources.append({
                    'uri': f'actus://runs/{eid}',
                    'name': f'执行记录 {eid}',
                    'description': f'执行记录 {eid} 的详细信息',
                    'mimeType': 'application/json',
                })
        except Exception:
            pass

        return resources

    def _read_resource(self, params: dict) -> dict:
        """读取指定资源（docs/10 §A.2）。"""
        uri = params.get('uri', '')

        if uri == 'actus://index':
            import vools.actus
            idx = actuscore.load_index()
            return {
                'contents': [{
                    'uri': uri,
                    'mimeType': 'application/json',
                    'text': json.dumps(idx, ensure_ascii=False, indent=2),
                }]
            }

        if uri == 'actus://status':
            from vools.actus import records as rec
            status = rec.load_status(None)
            return {
                'contents': [{
                    'uri': uri,
                    'mimeType': 'application/json',
                    'text': json.dumps(status, ensure_ascii=False, indent=2),
                }]
            }

        if uri.startswith('actus://runs/'):
            eid = uri.split('/')[-1]
            from vools.actus import records as rec
            record = rec.load_run_record(None, eid)
            if record is None:
                from vools.actus.errors import ActionError
                raise ActionError('resource_not_found', f'执行记录不存在: {eid}')
            return {
                'contents': [{
                    'uri': uri,
                    'mimeType': 'application/json',
                    'text': json.dumps(record, ensure_ascii=False, indent=2),
                }]
            }

        from vools.actus.errors import ActionError
        raise ActionError('resource_not_found', f'资源不存在: {uri}')

    # ── Logging ──

    def _complete(self, params: dict) -> dict:
        """参数补全（docs/10 §A.2 completion/complete）。"""
        ref = params.get('ref', {})
        arg_name = ref.get('name', '')
        arg_value = ref.get('value', '')

        # 简单的补全：根据 arg_name 返回建议值
        completions = {
            'trust': ['audit', 'trusted', 'sandbox'],
            'evolve_policy': ['confirm', 'auto', 'off'],
            'on_failure': ['abort', 'continue', 'fallback'],
        }

        values = completions.get(arg_name, [])
        if arg_value:
            values = [v for v in values if v.startswith(arg_value)]

        return {
            'completion': {
                'values': values,
                'total': len(values),
            }
        }

    def _call_tool(self, params: dict) -> dict:
        name = params.get('name', '')
        args = params.get('arguments') or {}
        import vools.actus

        def text_result(payload: dict, is_error: bool = False) -> dict:
            return {
                'content': [{'type': 'text',
                             'text': json.dumps(payload, ensure_ascii=False, indent=2)}],
                'isError': is_error,
            }

        if name == 'actus_list':
            idx = actuscore.load_index()
            tag_filter = args.get('tag')
            tags = tag_filter.split(',') if tag_filter else None
            rows = []
            for aid, b in idx['actions'].items():
                if aid.startswith('_invalid:'):
                    continue
                action_tags = b.get('tags', [])
                if tags and not any(t in action_tags for t in tags):
                    continue
                rows.append({'id': aid, 'name': b.get('name'), 'version': b.get('version'),
                             'trust': b.get('trust'), 'status': b.get('status'),
                             'tags': action_tags})
            return text_result({'status': 'ok', 'data': {'actions': rows}})

        if name == 'actus_search':
            idx = actuscore.load_index()
            query = (args.get('query') or '').lower()
            tag_filter = args.get('tag')
            tags = tag_filter.split(',') if tag_filter else None
            author = args.get('author')
            limit = args.get('limit', 20)
            rows = []
            for aid, b in idx['actions'].items():
                if aid.startswith('_invalid:'):
                    continue
                action_tags = b.get('tags', [])
                if tags and not any(t in action_tags for t in tags):
                    continue
                if author and b.get('author') != author:
                    continue
                if query and query not in aid.lower() and query not in b.get('name', '').lower() and query not in ' '.join(action_tags).lower():
                    continue
                rows.append({'id': aid, 'name': b.get('name'), 'version': b.get('version'),
                             'trust': b.get('trust'), 'status': b.get('status'),
                             'tags': action_tags})
            return text_result({'status': 'ok', 'data': {'actions': rows[:limit], 'total': len(rows)}})

        if name == 'actus_recommend':
            idx = actuscore.load_index()
            description = args.get('description', '')
            limit = args.get('limit', 5)
            
            # 使用 Intent Router 进行路由
            from vools.actus.intent import get_default_router
            from vools.actus.indexer import scan_actions
            
            router = get_default_router()
            actions = scan_actions(validate=False)
            
            # 注册所有可用动作到路由器
            for aid, a in actions.items():
                tags = a.meta.get('tags', [])
                desc = a.meta.get('description', '')
                usage = a.meta.get('usage', '')
                router.register_action(aid, desc, usage, tags)
            
            result = router.route(description)
            
            recommendations = []
            if result.get('action_id'):
                aid = result['action_id']
                if aid in idx['actions']:
                    b = idx['actions'][aid]
                    recommendations.append({
                        'id': aid,
                        'name': b.get('name'),
                        'score': result.get('confidence', 0),
                        'reason': result.get('reason', ''),
                        'description': b.get('description', ''),
                    })
            
            return text_result({'status': 'ok', 'data': {'recommendations': recommendations, 'total': len(recommendations)}})

        if name == 'actus_info':
            aid = args.get('id', '')
            try:
                action = actuscore.get_action(aid)
            except actuscore.ActionError as e:
                return text_result({'status': 'failed', 'error': e.to_payload()}, True)
            return text_result({'status': 'ok', 'data': action.brief()})

        if name == 'actus_status':
            from vools.actus import records as rec
            eid = args.get('exec_id')
            if eid:
                r = rec.load_run_record(None, eid)
                if r is None:
                    return text_result({'status': 'failed', 'error': {
                        'code': 'action_not_found',
                        'message': f'执行记录不存在: {eid}'}}, True)
                return text_result({'status': 'ok', 'data': r})
            return text_result({'status': 'ok', 'data': rec.load_status(None)})

        if name == 'actus_preview':
            aid = args.get('id', '')
            try:
                p = actuscore.preview(aid, args.get('args') or {})
            except actuscore.ActionError as e:
                return text_result({'status': 'failed', 'error': e.to_payload()}, True)
            return text_result({'status': 'ok', 'data': p})

        if name == 'actus_confirm':
            eid = args.get('exec_id', '')
            try:
                r = actuscore.confirm(eid)
            except actuscore.ActionError as e:
                return text_result({'status': 'failed', 'error': e.to_payload()}, True)
            return text_result(r)

        if name == 'actus_scaffold':
            from vools.actus.scaffold import scaffold_action
            desc = args.get('description', '')
            trust = args.get('trust', 'audit')
            aid = args.get('action_id')
            root = os.environ.get('ACTUS_REPO_ROOT')
            r = scaffold_action(desc, action_id=aid, trust=trust,
                                repo_root=root)
            return text_result(r, r.get('validation', {}).get('valid') is False)

        if name == 'actus_author':
            from vools.actus.author import author_action
            aid = args.get('action_id', '')
            instruction = args.get('instruction', '')
            root = os.environ.get('ACTUS_REPO_ROOT')
            try:
                r = author_action(aid, instruction, repo_root=root)
                return text_result(r, r.get('status') == 'failed')
            except actuscore.ActionError as e:
                return text_result({'status': 'failed', 'error': e.to_payload()}, True)

        if name == 'actus_publish':
            from vools.actus.author import publish_action
            aid = args.get('action_id', '')
            force = bool(args.get('force', False))
            root = os.environ.get('ACTUS_REPO_ROOT')
            try:
                r = publish_action(aid, repo_root=root, force=force)
                return text_result(r, r.get('status') != 'published')
            except actuscore.ActionError as e:
                return text_result({'status': 'failed', 'error': e.to_payload()}, True)

        if name == 'actus_workflow_run':
            from vools.actus.workflow import run_workflow
            wf_id = args.get('workflow_id', '')
            params = args.get('params', {}) or {}
            max_workers = int(args.get('max_workers', 4))
            confirmed = bool(args.get('confirmed', True))
            root = os.environ.get('ACTUS_REPO_ROOT', '')
            meta_dir = os.path.join(root, '_meta')
            try:
                r = run_workflow(wf_id, meta_dir=meta_dir,
                                 max_workers=max_workers, confirmed=confirmed)
                return text_result(r, r.get('status') == 'failed')
            except actuscore.ActionError as e:
                return text_result({'status': 'failed', 'error': e.to_payload()}, True)

        if name == 'actus_workflow_status':
            wf_id = args.get('workflow_id', '')
            root = os.environ.get('ACTUS_REPO_ROOT', '')
            meta_dir = os.path.join(root, '_meta')
            wf_path = os.path.join(meta_dir, 'workflows', f'{wf_id}.json')
            if not os.path.isfile(wf_path):
                return text_result({'status': 'not_found',
                                    'message': f'工作流执行记录不存在: {wf_id}'}, True)
            with open(wf_path, 'r', encoding='utf-8') as f:
                record = json.load(f)
            return text_result(record)

        if name == 'actus_vault_set':
            from vools.actus.vault import Vault
            key = args.get('key', '')
            value = args.get('value', '')
            scope = args.get('scope', 'global')
            description = args.get('description', '')
            root = os.environ.get('ACTUS_REPO_ROOT', '')
            meta_dir = os.path.join(root, '_meta')
            try:
                vault = Vault(meta_dir)
                r = vault.set(key, value, scope, description)
                return text_result(r)
            except Exception as e:
                return text_result({'status': 'failed', 'error': {'code': 'vault_error', 'message': str(e)}}, True)

        if name == 'actus_vault_get':
            from vools.actus.vault import Vault
            key = args.get('key', '')
            scope = args.get('scope', 'global')
            root = os.environ.get('ACTUS_REPO_ROOT', '')
            meta_dir = os.path.join(root, '_meta')
            try:
                vault = Vault(meta_dir)
                val = vault.get(key, scope)
                if val is None:
                    return text_result({'status': 'not_found', 'message': f'密钥不存在: {key}'}, True)
                return text_result({'status': 'ok', 'key': key, 'scope': scope, 'value': val})
            except Exception as e:
                return text_result({'status': 'failed', 'error': {'code': 'vault_error', 'message': str(e)}}, True)

        if name == 'actus_vault_list':
            from vools.actus.vault import Vault
            scope = args.get('scope')
            root = os.environ.get('ACTUS_REPO_ROOT', '')
            meta_dir = os.path.join(root, '_meta')
            try:
                vault = Vault(meta_dir)
                keys = vault.list(scope)
                return text_result({'status': 'ok', 'keys': keys})
            except Exception as e:
                return text_result({'status': 'failed', 'error': {'code': 'vault_error', 'message': str(e)}}, True)

        if name == 'actus_vault_delete':
            from vools.actus.vault import Vault
            key = args.get('key', '')
            scope = args.get('scope', 'global')
            root = os.environ.get('ACTUS_REPO_ROOT', '')
            meta_dir = os.path.join(root, '_meta')
            try:
                vault = Vault(meta_dir)
                deleted = vault.delete(key, scope)
                return text_result({'status': 'ok' if deleted else 'not_found',
                                    'deleted': deleted, 'key': key})
            except Exception as e:
                return text_result({'status': 'failed', 'error': {'code': 'vault_error', 'message': str(e)}}, True)

        if name == 'actus_runtimes':
            from vools.actus.runtimes import get_available_runtimes
            try:
                langs = get_available_runtimes()
                return text_result({'status': 'ok', 'available': langs})
            except Exception as e:
                return text_result({'status': 'failed', 'error': {'code': 'runtime_error', 'message': str(e)}}, True)

        if name == 'actus_deps':
            return _handle_deps_check(args)

        if name == 'actus_dep_tree':
            return _handle_dep_tree(args)

        if name == 'actus_triggers_list':
            return _handle_triggers_list(args)

        if name == 'actus_triggers_add':
            return _handle_triggers_add(args, meta_dir)

        if name == 'actus_triggers_remove':
            return _handle_triggers_remove(args)

        if name == 'actus_triggers_status':
            return _handle_triggers_status()

        if name == 'actus_execute':
            return _handle_execute(args)

        if name == 'actus_records_list':
            return _handle_records_list(args)

        if name == 'actus_records_export':
            return _handle_records_export(args)

        if name == 'actus_artifacts_list':
            return _handle_artifacts_list(args)

        if name == 'actus_artifacts_cleanup':
            return _handle_artifacts_cleanup(args)

        # 进化工具
        if name == 'actus_evolve':
            return _handle_evolve(args)
        if name == 'actus_evolve_repair':
            return _handle_evolve_repair(args)
        if name == 'actus_evolve_status':
            return _handle_evolve_status(args)
        if name == 'actus_evolve_history':
            return _handle_evolve_history(args)
        if name == 'actus_evolve_rollback':
            return _handle_evolve_rollback(args)
        if name == 'actus_evolve_compare':
            return _handle_evolve_compare(args)
        if name == 'actus_evolve_list':
            return _handle_evolve_list(args)

        # Webhook 工具
        if name == 'actus_webhook_start':
            return _handle_webhook_start(args)
        if name == 'actus_webhook_start_background':
            return _handle_webhook_start_background(args)
        if name == 'actus_webhook_stop':
            return _handle_webhook_stop(args)
        if name == 'actus_webhook_status':
            return _handle_webhook_status(args)
        if name == 'actus_webhook_register':
            return _handle_webhook_register(args)
        if name == 'actus_webhook_unregister':
            return _handle_webhook_unregister(args)
        if name == 'actus_webhook_logs':
            return _handle_webhook_logs(args)

        # Project 工具
        if name == 'actus_project_load':
            return _handle_project_load(args)
        if name == 'actus_project_detect':
            return _handle_project_detect(args)
        if name == 'actus_project_build':
            return _handle_project_build(args)
        if name == 'actus_project_test':
            return _handle_project_test(args)
        if name == 'actus_project_status':
            return _handle_project_status(args)
        if name == 'actus_project_validate':
            return _handle_project_validate(args)
        if name == 'actus_project_add_module':
            return _handle_project_add_module(args)
        if name == 'actus_project_remove_module':
            return _handle_project_remove_module(args)

        # Visibility 工具
        if name == 'actus_visibility_get':
            return _handle_visibility_get(args)
        if name == 'actus_visibility_set':
            return _handle_visibility_set(args)
        if name == 'actus_registry_add':
            return _handle_registry_add(args)
        if name == 'actus_registry_remove':
            return _handle_registry_remove(args)
        if name == 'actus_registry_list':
            return _handle_registry_list(args)
        if name == 'actus_private_list':
            return _handle_private_list(args)
        if name == 'actus_private_add':
            return _handle_private_add(args)
        if name == 'actus_private_remove':
            return _handle_private_remove(args)
        if name == 'actus_team_create':
            return _handle_team_create(args)
        if name == 'actus_team_add_member':
            return _handle_team_add_member(args)
        if name == 'actus_team_remove_member':
            return _handle_team_remove_member(args)
        if name == 'actus_team_list':
            return _handle_team_list(args)

        # Highlight 工具
        if name == 'actus_preview':
            return _handle_preview(args)

        # 动作工具：反查 action id
        import vools.actus as _a
        from vools.actus.indexer import load_index as _li
        target = None
        for aid in _li()['actions']:
            if _tool_name(aid) == name:
                target = aid
                break
        if target is None:
            return text_result({'status': 'failed', 'error': {
                'code': 'action_not_found', 'message': f'未知工具: {name}'}}, True)

        inner = args.get('args') if isinstance(args.get('args'), dict) else args
        try:
            r = actuscore.execute(target, inner or {})
        except actuscore.ActionError as e:
            return text_result({'status': 'failed', 'error': e.to_payload()}, True)
        return text_result(r, r.get('status') == 'failed')


# ── Visibility 处理函数 ──

def _handle_visibility_get(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    action_id = args.get('action_id', '')
    priv = engine.get_private_action(action_id)
    if priv:
        return text_result(engine.get_action_permissions(
            action_id, priv.get('visibility', 'private')))
    return text_result({'status': 'not_found',
                        'message': f'未找到动作: {action_id}'}, True)

def _handle_visibility_set(args):
    from vools.actus.visibility import VISIBILITY_PUBLIC, VISIBILITY_UNLISTED, VISIBILITY_PRIVATE, VISIBILITY_TEAM
    action_id = args.get('action_id', '')
    visibility = args.get('visibility', '')
    if visibility not in ('public', 'unlisted', 'private', 'team'):
        return text_result({'status': 'invalid',
                            'message': f'无效的可见性级别: {visibility}'}, True)
    team = args.get('team', '')
    if visibility == 'team' and not team:
        return text_result({'status': 'invalid',
                            'message': 'team 级别需要指定 team 参数'}, True)
    return text_result({'status': 'ok', 'action_id': action_id,
                        'visibility': visibility, 'team': team})

def _handle_registry_add(args):
    from vools.actus.visibility import RegistryConfig, get_visibility_engine
    engine = get_visibility_engine()
    reg = RegistryConfig(
        name=args.get('name', ''),
        url=args.get('url', ''),
        registry_type=args.get('registry_type', 'http'),
        branch=args.get('branch', 'main'),
        priority=args.get('priority', 50),
    )
    engine.registry.add_registry(reg)
    return text_result({'status': 'ok', 'registry': reg.to_dict()})

def _handle_registry_remove(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    name = args.get('name', '')
    removed = engine.registry.remove_registry(name)
    if removed:
        return text_result({'status': 'ok', 'removed': name})
    return text_result({'status': 'not_found',
                        'message': f'注册表不存在: {name}'}, True)

def _handle_registry_list(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    regs = engine.registry.list_registries()
    return text_result({'status': 'ok', 'registries': [r.to_dict() for r in regs]})

def _handle_private_list(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    actions = engine.list_private_actions()
    return text_result({'status': 'ok', 'actions': actions, 'count': len(actions)})

def _handle_private_add(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    action_id = args.get('action_id', '')
    author = args.get('author', '')
    path = args.get('path', '')
    engine.add_private_action(action_id, {'author': author, 'path': path})
    return text_result({'status': 'ok', 'action_id': action_id})

def _handle_private_remove(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    action_id = args.get('action_id', '')
    removed = engine.remove_private_action(action_id)
    if removed:
        return text_result({'status': 'ok', 'removed': action_id})
    return text_result({'status': 'not_found',
                        'message': f'私有动作不存在: {action_id}'}, True)

def _handle_team_create(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    name = args.get('name', '')
    creator = args.get('creator', '')
    team = engine.teams.create_team(name, creator)
    return text_result({'status': 'ok', 'team': team.to_dict()})

def _handle_team_add_member(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    team = args.get('team', '')
    user_id = args.get('user_id', '')
    role = args.get('role', 'member')
    ok = engine.teams.add_member(team, user_id, role=role)
    if ok:
        return text_result({'status': 'ok', 'team': team, 'user': user_id, 'role': role})
    return text_result({'status': 'failed',
                        'message': f'添加成员失败: {team}/{user_id}'}, True)

def _handle_team_remove_member(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    team = args.get('team', '')
    user_id = args.get('user_id', '')
    ok = engine.teams.remove_member(team, user_id)
    if ok:
        return text_result({'status': 'ok', 'removed': user_id})
    return text_result({'status': 'failed',
                        'message': f'移除成员失败: {team}/{user_id}'}, True)

def _handle_team_list(args):
    from vools.actus.visibility import get_visibility_engine
    engine = get_visibility_engine()
    team = args.get('team')
    if team:
        t = engine.teams.get_team(team)
        if t:
            return text_result({'status': 'ok', 'team': t.to_dict()})
        return text_result({'status': 'not_found',
                            'message': f'团队不存在: {team}'}, True)
    teams = engine.teams.list_teams()
    return text_result({'status': 'ok', 'teams': teams, 'count': len(teams)})

def _handle_preview(args):
    from vools.actus.highlight import highlight_code, check_shiki_available
    if not check_shiki_available():
        return text_result({'status': 'failed', 'error': {
            'code': 'shiki_unavailable',
            'message': 'Shiki 未安装或不可用。请运行: npm install shiki'
        }}, True)

    code = args.get('code', '')
    lang = args.get('lang', 'python')
    theme = args.get('theme', 'github-dark')
    mode = args.get('mode', 'terminal')

    highlighted = highlight_code(code, lang, theme=theme, mode=mode)
    return text_result({'status': 'ok', 'highlighted': highlighted,
                        'lang': lang, 'theme': theme, 'mode': mode})


def serve() -> None:
    """入口：stdio 服务（Ctrl/Closed stdin 退出）。"""
    MCPServer().serve_forever()


# ── 触发器处理器 ──

def _get_trigger_engine(meta_dir: str = ''):
    """获取或创建触发器引擎（进程级单例）。"""
    import vools.actus as _a
    if not hasattr(_a, '_trigger_engine'):
        root = os.environ.get('ACTUS_REPO_ROOT', '')
        md = meta_dir or os.path.join(root, '_meta')

        def _executor(trigger, event=None):
            """触发器回调：执行关联动作。"""
            try:
                _a.execute(trigger.action_id, trigger.args or {})
            except Exception:
                pass

        engine = _a.TriggerEngine(_executor, md)
        _a._trigger_engine = engine
    return _a._trigger_engine


def _handle_triggers_list(args: dict):
    """列出所有已注册的触发器。"""
    engine = _get_trigger_engine()
    action_id = args.get('action_id')

    result = {}
    for aid, triggers in engine._triggers.items():
        if action_id and aid != action_id:
            continue
        result[aid] = [t.config for t in triggers]

    return text_result({'status': 'ok', 'triggers': result})


def _handle_triggers_add(args: dict, meta_dir: str = ''):
    """注册触发器。"""
    from vools.actus.triggers import Trigger, validate_trigger

    action_id = args.get('action_id', '')
    ttype = args.get('type', '')

    config = {'type': ttype}
    for field in ('expr', 'path', 'events', 'recursive', 'key', 'args'):
        if field in args:
            config[field] = args[field]

    errors = validate_trigger(config)
    if errors:
        return text_result({'status': 'failed', 'error': {
            'code': 'validation_error', 'message': '; '.join(errors)
        }}, True)

    trigger = Trigger(action_id, config)
    engine = _get_trigger_engine(meta_dir)
    engine.add_trigger(trigger)

    # 持久化到触发器注册表
    _save_trigger_registry(engine)

    return text_result({'status': 'ok', 'action_id': action_id, 'type': ttype})


def _handle_triggers_remove(args: dict):
    """移除触发器。"""
    action_id = args.get('action_id', '')
    engine = _get_trigger_engine()
    engine.remove_trigger(action_id)
    _save_trigger_registry(engine)
    return text_result({'status': 'ok', 'removed': action_id})


def _handle_triggers_status():
    """查看触发器引擎状态。"""
    engine = _get_trigger_engine()
    status = engine.status()
    status['running'] = engine._cron._running or engine._watcher._running
    return text_result({'status': 'ok', 'engine': status})


def _save_trigger_registry(engine):
    """持久化触发器注册表到磁盘。"""
    root = os.environ.get('ACTUS_REPO_ROOT', '')
    meta_dir = os.path.join(root, '_meta')
    registry_path = os.path.join(meta_dir, 'triggers.json')

    data = {}
    for aid, triggers in engine._triggers.items():
        data[aid] = [t.config for t in triggers]

    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _handle_deps_check(args: dict):
    """检查动作依赖。"""
    from vools.actus.dependency import check_action_deps
    action_id = args.get('action_id')
    auto_install = args.get('auto_install', False)
    if not action_id:
        return text_result({'status': 'failed', 'error': {'code': 'missing_param', 'message': '需要 action_id'}}, True)
    try:
        result = check_action_deps(action_id, auto_install=auto_install)
        return text_result(result)
    except Exception as e:
        return text_result({'status': 'failed', 'error': {'code': 'deps_error', 'message': str(e)}}, True)


def _handle_dep_tree(args: dict):
    """查看动作依赖树。"""
    from vools.actus.dependency import get_resolver
    action_id = args.get('action_id')
    if not action_id:
        return text_result({'status': 'failed', 'error': {'code': 'missing_param', 'message': '需要 action_id'}}, True)
    try:
        resolver = get_resolver()
        tree = resolver.get_dep_tree(action_id)
        return text_result({'status': 'ok', 'tree': tree})
    except Exception as e:
        return text_result({'status': 'failed', 'error': {'code': 'deps_error', 'message': str(e)}}, True)


def _handle_execute(args: dict):
    """执行代码片段。"""
    from vools.actus.runtimes import execute_block, get_available_runtimes

    language = args.get('language', '')
    code = args.get('code', '')

    if not language:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_language', 'message': '请指定语言：python/shell/node/go/rust/ruby/php'
        }}, True)

    if not code:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_code', 'message': '请提供要执行的代码'
        }}, True)

    # 检查语言是否可用
    available = get_available_runtimes()
    if language not in available:
        return text_result({'status': 'failed', 'error': {
            'code': 'unsupported_language',
            'message': f'不支持的语言: {language}。可用: {", ".join(available)}'
        }}, True)

    # 构建执行上下文
    context = {}
    if 'args' in args:
        context['args'] = args['args']
    if 'stdin' in args:
        context['stdin'] = args['stdin']
    if 'env' in args and isinstance(args['env'], dict):
        context['env'] = args['env']

    timeout = args.get('timeout', 30)

    try:
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError(f'执行超时（{timeout} 秒）')

        # Windows 不支持 signal.SIGALRM，使用替代方案
        if hasattr(signal, 'SIGALRM'):
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            try:
                stdout, stderr, exit_code = execute_block(language, code, context)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows: 使用线程级超时（简化处理）
            stdout, stderr, exit_code = execute_block(language, code, context)

        return text_result({
            'status': 'ok',
            'language': language,
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': exit_code,
        })
    except TimeoutError as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'timeout', 'message': str(e)
        }}, True)
    except RuntimeError as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'runtime_error', 'message': str(e)
        }}, True)
    except Exception as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'execution_error', 'message': f'{type(e).__name__}: {e}'
        }}, True)


def _handle_records_list(args: dict):
    """列出执行记录。"""
    from vools.actus.records import list_run_records

    action_id = args.get('action_id')
    limit = args.get('limit', 50)
    offset = args.get('offset', 0)

    try:
        records = list_run_records(None, action_id, limit, offset)
        return text_result({'status': 'ok', 'total': len(records), 'records': records})
    except Exception as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'records_error', 'message': str(e)
        }}, True)


def _handle_records_export(args: dict):
    """导出执行记录。"""
    from vools.actus.records import export_records

    action_id = args.get('action_id')
    fmt = args.get('format', 'json')
    output = args.get('output')
    limit = args.get('limit', 100)

    if fmt not in ('json', 'csv', 'summary'):
        return text_result({'status': 'failed', 'error': {
            'code': 'invalid_format', 'message': '输出格式必须是 json/csv/summary'
        }}, True)

    try:
        result = export_records(None, action_id, fmt, output, limit)
        return text_result({'status': 'ok', **result})
    except Exception as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'export_error', 'message': str(e)
        }}, True)


def _handle_artifacts_list(args: dict):
    """列出产物。"""
    from vools.actus.records import list_artifacts

    action_id = args.get('action_id')
    exec_id = args.get('exec_id')
    artifact_type = args.get('type')

    try:
        artifacts = list_artifacts(None, action_id, exec_id, artifact_type)
        return text_result({'status': 'ok', 'total': len(artifacts), 'artifacts': artifacts})
    except Exception as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'artifacts_error', 'message': str(e)
        }}, True)


def _handle_artifacts_cleanup(args: dict):
    """清理产物。"""
    from vools.actus.records import cleanup_artifacts

    max_age_days = args.get('max_age_days', 30)
    max_count = args.get('max_count', 1000)

    try:
        result = cleanup_artifacts(None, max_age_days, max_count)
        return text_result({'status': 'ok', **result})
    except Exception as e:
        return text_result({'status': 'failed', 'error': {
            'code': 'cleanup_error', 'message': str(e)
        }}, True)


if __name__ == '__main__':
    serve()


# ── 进化 handler ──

def _handle_evolve(args: dict):
    """自进化：根据自然语言描述自动生成动作并修复直到通过。"""
    from vools.actus.evolution import EvolutionEngine, EvolutionConfig

    description = args.get('description', '')
    if not description:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_description', 'message': 'description 是必需的'}
        }, True)

    action_id = args.get('action_id')
    max_rounds = args.get('max_rounds', 5)
    expect = args.get('expect', {})

    config = EvolutionConfig(max_rounds=max_rounds, auto_promote=False)
    engine = EvolutionEngine(config=config)
    result = engine.evolve(description, action_id=action_id, expect=expect)

    return text_result(result)


def _handle_evolve_repair(args: dict):
    """修复已有动作。"""
    from vools.actus.evolution import EvolutionEngine, EvolutionConfig

    action_id = args.get('action_id', '')
    if not action_id:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_action_id', 'message': 'action_id 是必需的'}
        }, True)

    max_rounds = args.get('max_rounds', 5)
    expect = args.get('expect', {})

    config = EvolutionConfig(max_rounds=max_rounds, auto_promote=False)
    engine = EvolutionEngine(config=config)
    result = engine.repair(action_id, expect=expect)

    return text_result(result)


def _handle_evolve_status(args: dict):
    """查询进化状态。"""
    from vools.actus.evolution import EvolutionEngine

    action_id = args.get('action_id', '')
    engine = EvolutionEngine()
    result = engine.get_status(action_id)
    return text_result(result)


def _handle_evolve_history(args: dict):
    """查看进化历史。"""
    from vools.actus.evolution import EvolutionEngine

    action_id = args.get('action_id', '')
    if not action_id:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_action_id', 'message': 'action_id 是必需的'}
        }, True)

    engine = EvolutionEngine()
    history = engine.get_history(action_id)
    return text_result({'status': 'ok', 'action_id': action_id, 'history': history})


def _handle_evolve_rollback(args: dict):
    """回滚到指定版本。"""
    from vools.actus.evolution import EvolutionEngine

    action_id = args.get('action_id', '')
    version = args.get('version')
    if not action_id or version is None:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_params', 'message': 'action_id 和 version 是必需的'}
        }, True)

    engine = EvolutionEngine()
    result = engine.rollback(action_id, int(version))
    return text_result(result)


def _handle_evolve_compare(args: dict):
    """A/B 对比两个版本。"""
    from vools.actus.evolution import EvolutionEngine

    action_id = args.get('action_id', '')
    v1 = args.get('v1')
    v2 = args.get('v2')
    if not action_id or v1 is None or v2 is None:
        return text_result({'status': 'failed', 'error': {
            'code': 'missing_params', 'message': 'action_id, v1, v2 是必需的'}
        }, True)

    engine = EvolutionEngine()
    result = engine.compare_versions(action_id, int(v1), int(v2))
    return text_result(result)


def _handle_evolve_list(args: dict):
    """列出所有有进化历史的动作。"""
    from vools.actus.evolution import EvolutionEngine

    engine = EvolutionEngine()
    actions = engine.list_evolved_actions()
    return text_result({'status': 'ok', 'actions': actions, 'total': len(actions)})


# ── Webhook handler ──

# 全局接收器实例（供 MCP handler 共享）
_webhook_receiver: dict = {"instance": None}


def _handle_webhook_start(args: dict):
    """启动 Webhook 接收器（后台模式）。"""
    from vools.actus.webhook import create_receiver

    host = args.get('host', '0.0.0.0')
    port = args.get('port', 8765)
    secret = args.get('secret', '')
    require_signature = args.get('require_signature', True)

    receiver = create_receiver(
        host=host, port=port, secret=secret,
        require_signature=require_signature
    )
    receiver.start_background()
    _webhook_receiver["instance"] = receiver
    return text_result({'status': 'ok', 'message': f'Webhook receiver started on {host}:{port}'})


def _handle_webhook_start_background(args: dict):
    """启动 Webhook 接收器（后台模式，同 start）。"""
    return _handle_webhook_start(args)


def _handle_webhook_stop(args: dict):
    """停止 Webhook 接收器。"""
    receiver = _webhook_receiver.get("instance")
    if receiver and receiver.is_running:
        receiver.stop()
        _webhook_receiver["instance"] = None
        return text_result({'status': 'ok', 'message': 'Webhook receiver stopped'})
    return text_result({'status': 'error', 'message': 'No webhook receiver running'}, True)


def _handle_webhook_status(args: dict):
    """查看 Webhook 运行状态和统计。"""
    receiver = _webhook_receiver.get("instance")
    if receiver:
        return text_result(receiver.get_status())
    return text_result({'running': False, 'message': 'No webhook receiver started'})


def _handle_webhook_register(args: dict):
    """注册事件路由。"""
    receiver = _webhook_receiver.get("instance")
    if not receiver:
        return text_result({'status': 'error',
                            'message': 'No webhook receiver running. Start first.'}, True)

    event_type = args.get('event_type', '')
    action_id = args.get('action_id', '')
    receiver.register_route(event_type, action_id)
    return text_result({'status': 'ok', 'event_type': event_type,
                        'action_id': action_id, 'registered': True})


def _handle_webhook_unregister(args: dict):
    """移除事件路由。"""
    receiver = _webhook_receiver.get("instance")
    if not receiver:
        return text_result({'status': 'error',
                            'message': 'No webhook receiver running.'}, True)

    event_type = args.get('event_type', '')
    removed = receiver.unregister_route(event_type)
    return text_result({'status': 'ok', 'event_type': event_type,
                        'removed': removed is not None, 'action_id': removed})


def _handle_webhook_logs(args: dict):
    """查看 Webhook 请求日志。"""
    receiver = _webhook_receiver.get("instance")
    if not receiver:
        return text_result({'status': 'error',
                            'message': 'No webhook receiver running.'}, True)

    limit = args.get('limit', 50)
    logs = receiver.get_logs(limit=limit)
    return text_result({'status': 'ok', 'logs': logs, 'total': len(logs)})


# ── Project handler ──

_project_orchestrators: dict = {}  # work_dir -> ProjectOrchestrator


def _get_orchestrator(work_dir: str) -> 'ProjectOrchestrator':
    """获取或创建指定工作目录的编排器。"""
    from vools.actus.project import ProjectOrchestrator
    if work_dir not in _project_orchestrators:
        _project_orchestrators[work_dir] = ProjectOrchestrator(work_dir=work_dir)
    return _project_orchestrators[work_dir]


def _handle_project_load(args: dict):
    """加载项目定义文件。"""
    from vools.actus.project import load_project

    project_file = args.get('project_file', '.actus-project.json')
    work_dir = args.get('work_dir', '.')

    try:
        orch = load_project(project_file, work_dir)
        _project_orchestrators[work_dir] = orch
        return text_result({
            'status': 'ok',
            'project': orch.config.name,
            'modules': list(orch.config.modules.keys()),
            'languages': orch.config.languages,
        })
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)


def _handle_project_detect(args: dict):
    """自动检测项目语言和模块。"""
    from vools.actus.project import ProjectOrchestrator, detect_modules, detect_languages

    work_dir = args.get('work_dir', '.')

    try:
        modules = detect_modules(work_dir)
        languages = detect_languages(work_dir)
        return text_result({
            'status': 'ok',
            'modules': {k: v.to_dict() for k, v in modules.items()},
            'languages': languages,
            'total_modules': len(modules),
        })
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)


def _handle_project_build(args: dict):
    """执行项目构建流水线。"""
    from vools.actus.project import load_project

    project_file = args.get('project_file', '.actus-project.json')
    work_dir = args.get('work_dir', '.')
    phase = args.get('phase')

    try:
        orch = load_project(project_file, work_dir)
        _project_orchestrators[work_dir] = orch
        result = orch.run_pipeline(phase=phase)
        return text_result(result)
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)


def _handle_project_test(args: dict):
    """执行项目测试。"""
    from vools.actus.project import load_project

    project_file = args.get('project_file', '.actus-project.json')
    work_dir = args.get('work_dir', '.')

    try:
        orch = load_project(project_file, work_dir)
        _project_orchestrators[work_dir] = orch
        result = orch.run_pipeline(phase='test')
        return text_result(result)
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)


def _handle_project_status(args: dict):
    """查看项目流水线状态。"""
    work_dir = args.get('work_dir', '.')
    orch = _get_orchestrator(work_dir)
    return text_result(orch.get_status())


def _handle_project_validate(args: dict):
    """验证项目定义。"""
    from vools.actus.project import load_project

    project_file = args.get('project_file', '.actus-project.json')
    work_dir = args.get('work_dir', '.')

    try:
        orch = load_project(project_file, work_dir)
        valid, errors = orch.validate()
        return text_result({
            'status': 'ok' if valid else 'invalid',
            'valid': valid,
            'errors': errors,
        })
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)


def _handle_project_add_module(args: dict):
    """添加模块到项目。"""
    from vools.actus.project import ModuleConfig

    work_dir = args.get('work_dir', '.')
    orch = _get_orchestrator(work_dir)

    try:
        module = ModuleConfig(
            id=args.get('module_id', ''),
            language=args.get('language', ''),
            path=args.get('path', ''),
            build_cmd=args.get('build_cmd', ''),
            test_cmd=args.get('test_cmd', ''),
        )
        orch.add_module(module)
        return text_result({'status': 'ok', 'module_id': module.id})
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)


def _handle_project_remove_module(args: dict):
    """从项目移除模块。"""
    work_dir = args.get('work_dir', '.')
    orch = _get_orchestrator(work_dir)

    try:
        module_id = args.get('module_id', '')
        orch.remove_module(module_id)
        return text_result({'status': 'ok', 'removed': module_id})
    except Exception as e:
        return text_result({'status': 'error', 'message': str(e)}, True)
