"""actus — Actus 命令行（docs/08 §6：validate 通过才入索引上 MCP）。

用法：
    python -m actus scan                       # 扫描并重建索引
    python -m actus list [--all]               # 列出动作（默认仅 valid）
    python -m actus validate [id]              # 校验动作/全仓库
    python -m actus info <id>                  # 查看动作元数据与依赖
    python -m actus preview <id> [json参数]     # 干跑：展示将执行的块
    python -m actus run <id> [json参数] [--confirm] [--yes]
    python -m actus status [exec_id]           # 查询执行状态
    python -m actus probe [--force-refresh] [--json] [--max-age N] [--verbose]  # 环境探测（ProbeReport）
    python -m actus mcp [--transport stdio|sse] [--port 8765]  # 启动聚合 MCP server
    python -m actus config <client>            # 生成 MCP 接入配置（claude/cursor/cline/vscode）
    python -m actus scaffold <description>     # AI：根据描述生成动作骨架
    python -m actus author <id> <instruction>  # AI：修改已有动作
    python -m actus vault set <key> <value> [--scope] [--desc]  # 存储密钥
    python -m actus vault get <key> [--scope]       # 获取密钥
    python -m actus vault list [--scope]            # 列出密钥（不含值）
    python -m actus vault delete <key> [--scope]    # 删除密钥
    python -m actus runtimes                        # 列出可用多语言运行时
    python -m actus execute --language <lang> --code <code>  # 执行代码片段
    python -m actus records list [--action-id] [--limit] [--offset]  # 列出执行记录
    python -m actus records export [--action-id] [--format json|csv|summary] [--output]  # 导出记录
    python -m actus artifacts list [--action-id] [--exec-id] [--type]  # 列出产物
    python -m actus artifacts cleanup [--max-age-days] [--max-count]  # 清理产物
    python -m actus triggers add <action_id> <type> [--expr] [--path] [--key]  # 注册触发器
    python -m actus triggers list               # 列出所有触发器
    python -m actus triggers status             # 引擎状态
    python -m actus triggers remove <action_id> # 移除触发器
"""
import json
import os
import re
import sys
import io
from pathlib import Path

__all__ = ['main']


def _out(obj):
    _ensure_utf8_stdout()
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# 子结果里算「成功」的 status 取值。刻意不包含 'partial' / 'needs_fix' /
# 'failed' / 'error'：对脚本来说顶层 status 是权威信号，业务未完成就不该是 ok。
_OPERATION_OK_STATUSES = ('ok', 'success', 'modified', 'skipped', 'noop')


def _out_result(result, status_field='status'):
    """输出「操作类」子命令结果，并**按其自身状态映射顶层 status / 退出码**。

    为什么需要：改前 scaffold / author / workflow 都是
    `_out({'status': 'ok', 'data': r}); return 0` —— 子结果是失败
    （`author` 实测 `status='needs_fix'`、`ai_applied=False`；`workflow`
    `status='partial'`/`failed`；`scaffold` `validation.valid=False`）时，
    顶层照样写 `status: ok` + exit 0，脚本据此判定"成功"。

    判定优先级：
      1. 结果体有 status 字段 → 在 `_OPERATION_OK_STATUSES` 里才算成功；
      2. 没有 status 但有 `validation.valid`（scaffold 的形状）→ 以其为准；
      3. 两者都没有（纯数据返回）→ 视为成功（查询本身没出错）。
    未知 status 一律按失败处理 —— 宁可让脚本看到非 0，也不假装成功。

    Args:
        result: 子命令返回的 dict。
        status_field: 状态字段名；传 None 表示「这是查询结果，其中 status 是
            被查询对象的状态（如 run record），不代表本次操作成败」。

    Returns:
        int: 进程退出码（0 = 成功，1 = 业务失败）。
    """
    if not isinstance(result, dict):
        ok = False
    elif status_field is None:
        ok = True
    elif status_field in result:
        ok = str(result.get(status_field) or '').lower() in _OPERATION_OK_STATUSES
    elif isinstance(result.get('validation'), dict):
        ok = bool(result['validation'].get('valid'))
    else:
        ok = True
    if not ok:
        hint = result.get('message') if isinstance(result, dict) else ''
        if hint:
            print('❌ %s' % hint, file=sys.stderr)
    _out({'status': 'ok' if ok else 'failed', 'data': result})
    return 0 if ok else 1


def _ensure_utf8_stdout():
    """CLI 输出统一 UTF-8（Windows 管道捕获时为 GBK → 下游按 UTF-8 读会解码失败）。

    Windows 上 Python 的管道 stdout 默认用 locale 编码（中文系统是 GBK），
    而测试/宿主按 UTF-8 读取（subprocess.run(encoding='utf-8')）→
    UnicodeDecodeError、拿到空输出（实测 test_link_chain 全挂）。
    这里 reconfigure 为 UTF-8；py3.6 无 reconfigure 时退化为 errors='replace' 缓冲。
    """
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        # py3.6 或 stdout 已被替换：包一层 UTF-8 缓冲（尽力而为）
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                                          errors='replace')
        except Exception:
            pass


def main(argv=None) -> int:
    """CLI 入口。"""
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(argv)

    # 无子命令时打印帮助并返回 2（argparse 惯例）。
    # 此前后续所有 `if args.command == ...` 全不命中，最终静默 return ——
    # 用户敲一个 `actus` 什么都看不到，连「该怎么用」都没有。
    if not getattr(args, 'command', None):
        parser.print_help()
        return 2

    if args.command == 'mcp':
        if args.transport == 'sse':
            from .mcp_sse import serve_sse
            serve_sse(port=args.port)
        else:
            from .mcp_server import serve
            serve()
        return 0

    try:
        return _dispatch(args)
    except Exception as e:
        _out({'status': 'failed', 'error': {
            'code': getattr(e, 'code', 'internal'), 'message': str(e)}})
        return 1


def _build_parser():
    """构建 argparse 解析器（供测试和 main() 使用）。"""
    import argparse
    parser = argparse.ArgumentParser(prog='actus', description='Actus — AI 动作执行平台 CLI')
    from . import __version__ as _actus_version
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + _actus_version,
                        help='显示版本号并退出')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('scan', help='扫描 actions/ 并重建 _meta/actions.index.json')

    p_list = sub.add_parser('list', help='列出动作')
    p_list.add_argument('--all', action='store_true', help='包含 invalid/conflict')
    p_list.add_argument('--kind', help='按执行类型过滤（exec/link/demo/template/alias/bundle/doc）')
    p_list.add_argument('--purpose', help='按用途过滤（source/sink/transform/.../utility）')
    p_list.add_argument('--industry', help='按行业过滤（devops/finance/.../general）')
    p_list.add_argument('--tag', help='按标签过滤（逗号分隔）')

    p_val = sub.add_parser('validate', help='校验动作')
    p_val.add_argument('action_id', nargs='?', help='动作 id（缺省 = 全仓库）')

    p_info = sub.add_parser('info', help='查看动作详情')
    p_info.add_argument('action_id')

    p_prev = sub.add_parser('preview', help='干跑：不执行代码，支持语法高亮')
    p_prev.add_argument('action_id')
    p_prev.add_argument('params', nargs='?', default='{}', help='JSON 入参')
    p_prev.add_argument('--html', action='store_true',
                        help='输出 HTML 高亮（默认终端 ANSI 高亮）')
    p_prev.add_argument('--theme', default='github-dark',
                        help='Shiki 主题（默认 github-dark）')
    p_prev.add_argument('--lang', default='python',
                        help='代码语言（默认 python）')
    p_prev.add_argument('--file', help='直接高亮指定文件（跳过动作预览）')

    p_run = sub.add_parser('run', help='执行动作')
    p_run.add_argument('action_id')
    p_run.add_argument('params', nargs='?', default='{}', help='JSON 入参')
    p_run.add_argument('--confirm', action='store_true',
                       help='audit 级动作：人类已确认，放行执行')
    p_run.add_argument('--yes', action='store_true',
                       help='非交互确认（等价 --confirm，语义同 docs/07 §2 回执）')
    p_run.add_argument('--allow-host', action='append', default=None,
                       help='远程动作源/入参的域名白名单（可重复；缺省禁止所有远程）')
    p_run.add_argument('--expect-digest', default=None,
                       help='远程动作源的期望 sha256 指纹（计划 §六.3：不匹配即拒绝执行）')
    p_run.add_argument('--require-signature', default=None,
                       help='远程动作源必须携带可用签名：给出本地可信公钥名（如 default），'
                            '下载同名 .sig 并验签，失败即拒绝（计划 §六.3）')
    p_run.add_argument('--allow-unverified-remote', action='store_true',
                       help='允许执行未经指纹校验的远程动作（默认拒绝，自担供应链风险）')

    p_status = sub.add_parser('status', help='查询执行状态')
    p_status.add_argument('exec_id', nargs='?', help='缺省 = 最近执行汇总')

    p_loop = sub.add_parser('loop', help='loop_prompt 死循环会话管理')
    loop_sub = p_loop.add_subparsers(dest='loop_command')
    p_loop_stop = loop_sub.add_parser('stop', help='请求停止：向会话项目目录写 stop 文件')
    p_loop_stop.add_argument('session', help='会话 id（loop-YYYYmmdd-HHMMSS）或其项目路径')
    p_loop_status = loop_sub.add_parser('status', help='查看会话进度（最新或指定会话）')
    p_loop_status.add_argument('session', nargs='?', help='缺省 = 最新会话')
    loop_sub.add_parser('list', help='列出全部会话')

    p_mcp = sub.add_parser('mcp', help='启动聚合 MCP server')
    p_mcp.add_argument('--transport', choices=['stdio', 'sse'], default='stdio',
                       help='传输协议（默认 stdio）')
    p_mcp.add_argument('--port', type=int, default=8765,
                       help='SSE 传输监听端口（默认 8765，仅 sse 有效）')

    # probe 子命令 — 环境探测器（analysis/PROBE_PLAN.md §9 Phase 3）
    p_probe = sub.add_parser('probe', help='环境探测器：一键探测本机能力，输出 ProbeReport')
    p_probe.add_argument('--force-refresh', '--force', action='store_true',
                         dest='force_refresh', help='强制刷新（忽略缓存）')
    p_probe.add_argument('--max-age', type=int, default=3600,
                         help='缓存有效期秒数（默认 3600）')
    p_probe.add_argument('--json', action='store_true', dest='as_json',
                         help='输出 JSON（机器消费）')
    p_probe.add_argument('--verbose', action='store_true',
                         help='打印每个探测器的详细进度')

    # dialog 子命令 — 快速调用 C# 弹窗
    p_dialog = sub.add_parser('dialog', help='弹出 C# 交互弹窗（alert/input/single/multi/form/wait）')
    p_dialog.add_argument('mode', choices=['alert', 'input', 'single', 'multi', 'form', 'wait'],
                          help='弹窗模式')
    p_dialog.add_argument('--message', '-m', help='提示文本')
    p_dialog.add_argument('--title', '-t', default='Actus', help='弹窗标题')
    p_dialog.add_argument('--options', help='选项列表（逗号分隔，single/multi 模式）')
    p_dialog.add_argument('--password', action='store_true', help='密码模式（input）')
    p_dialog.add_argument('--multiline', action='store_true', help='多行模式（input）')
    p_dialog.add_argument('--timeout', type=int, default=0, help='超时秒数（wait 模式）')
    p_dialog.add_argument('--fields', help='表单字段 JSON（form 模式）')

    p_config = sub.add_parser('config', help='生成 MCP 接入配置片段')
    p_config.add_argument('client', choices=['claude', 'cursor', 'cline', 'vscode'],
                          help='目标 AI 客户端类型')

    p_scaffold = sub.add_parser('scaffold', help='AI：根据自然语言描述生成动作骨架')
    p_scaffold.add_argument('description', help='动作用途的自然语言描述')
    p_scaffold.add_argument('--id', dest='action_id', help='指定动作 id（缺省自动生成）')
    p_scaffold.add_argument('--trust', choices=['audit', 'trusted', 'sandbox'],
                            default='audit', help='信任级别（默认 audit）')
    p_scaffold.add_argument('--force', action='store_true',
                            help='目标动作文件已存在时允许覆盖（默认拒绝，防数据丢失）')

    p_author = sub.add_parser('author',
                              help='记录修改指令（需接 AI 才会真正改代码；未接 AI 时 exit 1）')
    p_author.add_argument('action_id', help='要修改的动作 id')
    p_author.add_argument('instruction', help='修改指令（自然语言）')

    p_wf = sub.add_parser('workflow', help='运行 DAG 工作流')
    p_wf.add_argument('workflow_id', help='工作流动作 id')
    p_wf.add_argument('--params', default='{}', help='工作流级参数 JSON')
    p_wf.add_argument('--max-workers', type=int, default=4, dest='max_workers',
                      help='并行执行线程数（默认 4）')
    p_wf.add_argument('--confirmed', action='store_true',
                      help='跳过人类确认')

    # vault 子命令
    p_vault = sub.add_parser('vault', help='密钥保险库操作')
    vault_sub = p_vault.add_subparsers(dest='vault_command')

    p_vault_set = vault_sub.add_parser('set', help='存储密钥')
    p_vault_set.add_argument('key', help='密钥名称')
    p_vault_set.add_argument('value', help='密钥值')
    p_vault_set.add_argument('--scope', default='global', help='作用域')
    p_vault_set.add_argument('--desc', default='', help='密钥描述')

    p_vault_get = vault_sub.add_parser('get', help='获取密钥')
    p_vault_get.add_argument('key', help='密钥名称')
    p_vault_get.add_argument('--scope', default='global', help='作用域')

    p_vault_list = vault_sub.add_parser('list', help='列出密钥')
    p_vault_list.add_argument('--scope', help='作用域过滤')

    p_vault_delete = vault_sub.add_parser('delete', help='删除密钥')
    p_vault_delete.add_argument('key', help='密钥名称')
    p_vault_delete.add_argument('--scope', default='global', help='作用域')

    # runtimes 子命令
    sub.add_parser('runtimes', help='列出可用多语言运行时')

    # execute 子命令
    p_exec = sub.add_parser('execute', help='执行代码片段（多语言运行时）')
    p_exec.add_argument('--language', required=True, help='语言：python/shell/node/go/rust/ruby/php')
    p_exec.add_argument('--code', help='要执行的代码')
    p_exec.add_argument('--file', help='从文件读取代码')
    p_exec.add_argument('--args', help='命令行参数')
    p_exec.add_argument('--stdin', help='标准输入')
    p_exec.add_argument('--env', help='环境变量（JSON）')
    p_exec.add_argument('--timeout', type=int, default=30, help='超时秒数（默认 30）')

    # records 子命令
    p_records = sub.add_parser('records', help='执行记录管理')
    records_sub = p_records.add_subparsers(dest='records_command')

    p_records_list = records_sub.add_parser('list', help='列出执行记录')
    p_records_list.add_argument('--action-id', help='按动作 id 过滤')
    p_records_list.add_argument('--limit', type=int, default=50, help='最多返回条数')
    p_records_list.add_argument('--offset', type=int, default=0, help='跳过条数')

    p_records_export = records_sub.add_parser('export', help='导出执行记录')
    p_records_export.add_argument('--action-id', help='按动作 id 过滤')
    p_records_export.add_argument('--format', default='json', help='输出格式：json/csv/summary')
    p_records_export.add_argument('--output', help='输出文件路径')
    p_records_export.add_argument('--limit', type=int, default=100, help='最多导出条数')

    # artifacts 子命令
    p_artifacts = sub.add_parser('artifacts', help='产物管理')
    artifacts_sub = p_artifacts.add_subparsers(dest='artifacts_command')

    p_artifacts_list = artifacts_sub.add_parser('list', help='列出产物')
    p_artifacts_list.add_argument('--action-id', help='按动作 id 过滤')
    p_artifacts_list.add_argument('--exec-id', help='按执行 id 过滤')
    p_artifacts_list.add_argument('--type', help='按产物类型过滤')

    p_artifacts_cleanup = artifacts_sub.add_parser('cleanup', help='清理产物')
    p_artifacts_cleanup.add_argument('--max-age-days', type=int, default=30, help='保留天数')
    p_artifacts_cleanup.add_argument('--max-count', type=int, default=1000, help='最多保留条数')

    # triggers 子命令
    p_triggers = sub.add_parser('triggers', help='触发器引擎管理')
    triggers_sub = p_triggers.add_subparsers(dest='triggers_command')

    p_triggers_add = triggers_sub.add_parser('add', help='注册触发器')
    p_triggers_add.add_argument('action_id', help='要触发的动作 id')
    p_triggers_add.add_argument('type', help='触发器类型：cron/watch/webhook/hotkey')
    p_triggers_add.add_argument('--expr', help='cron 表达式')
    p_triggers_add.add_argument('--path', help='监控路径')
    p_triggers_add.add_argument('--events', nargs='+', default=['create', 'modify'],
                                 help='监控事件')
    p_triggers_add.add_argument('--recursive', action='store_true', help='递归监控')
    p_triggers_add.add_argument('--key', help='热键组合')
    p_triggers_add.add_argument('--args', default='{}', help='传递给动作的参数（JSON）')

    triggers_sub.add_parser('list', help='列出所有触发器')
    triggers_sub.add_parser('status', help='引擎状态')

    p_triggers_remove = triggers_sub.add_parser('remove', help='移除触发器')
    p_triggers_remove.add_argument('action_id', help='动作 id')

    # registry 子命令（动作市场）
    p_registry = sub.add_parser('registry', help='动作注册表管理')
    registry_sub = p_registry.add_subparsers(dest='registry_command')

    p_registry_build = registry_sub.add_parser('build', help='构建当前仓库的注册表索引')
    p_registry_build.add_argument('--output', help='输出路径（默认 .actus.registry.json）')

    p_registry_validate = registry_sub.add_parser('validate', help='校验注册表索引')
    p_registry_validate.add_argument('--index', help='索引文件路径')

    p_registry_info = registry_sub.add_parser('info', help='查看注册表信息')
    p_registry_info.add_argument('--index', help='索引文件路径')

    # install 子命令
    p_install = sub.add_parser('install', help='从 Git 仓库安装动作')
    p_install.add_argument('url', help='Git 仓库 URL（如 git@github.com:user/repo.git）')
    p_install.add_argument('--branch', default='main', help='分支名（默认 main）')
    p_install.add_argument('--tag', help='标签名')
    p_install.add_argument('--commit', help='commit hash')
    p_install.add_argument('--scope', help='权限范围（trusted/community/sandbox）')
    p_install.add_argument('--dir', help='安装目录（默认 ~/.actus/actions）')

    # uninstall 子命令
    p_uninstall = sub.add_parser('uninstall', help='卸载已安装的动作仓库')
    p_uninstall.add_argument('--url', help='仓库 URL')
    p_uninstall.add_argument('--name', help='安装名称')

    # publish 子命令
    p_publish = sub.add_parser('publish', help='生成注册表索引并打印发布步骤')
    p_publish.add_argument('--registry', help='注册表索引文件路径')
    p_publish.add_argument('--sign', action='store_true', help='签名所有动作（ed25519，复用 actus sign）')
    p_publish.add_argument('--key', default='default', help='--sign 使用的签名密钥名（默认 default）')
    p_publish.add_argument('--dry-run', action='store_true', help='仅验证不发布')

    # search 子命令
    p_search = sub.add_parser('search', help='搜索动作')
    p_search.add_argument('query', nargs='?', help='搜索关键词')
    p_search.add_argument('--category', help='分类过滤')
    p_search.add_argument('--author', help='作者过滤')
    p_search.add_argument('--tag', help='标签过滤（多个用逗号分隔，如 "file,network"）')
    p_search.add_argument('--source', help='搜索来源（local/installed/url）', default='local')
    p_search.add_argument('--url', help='远程仓库 URL（source=url 时使用）')
    p_search.add_argument('--limit', type=int, default=20, help='最大返回数')

    # deps 子命令
    p_deps = sub.add_parser('deps', help='检查动作依赖（编译产物、Python/npm 包、系统命令）')
    p_deps.add_argument('action_id', help='动作 id（如 actus.system.dialog_alert）')
    p_deps.add_argument('--auto-install', action='store_true', dest='auto_install',
                        help='尝试自动安装缺失依赖（pip install / dotnet build）')

    # dep-tree 子命令
    p_dep_tree = sub.add_parser('dep-tree', help='递归展示动作的依赖树')
    p_dep_tree.add_argument('action_id', help='动作 id')

    # desktop 子命令
    p_desktop = sub.add_parser('desktop', help='启动 Actus Desktop Web UI')
    p_desktop.add_argument('--host', default='127.0.0.1', help='监听地址 (默认 127.0.0.1)')
    p_desktop.add_argument('--port', type=int, default=8765, help='监听端口 (默认 8765)')
    p_desktop.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')

    # events 子命令
    p_events = sub.add_parser('events', help='查看事件流（读 _meta/events.jsonl，跨进程可见）')
    p_events.add_argument('--type', help='过滤事件类型')
    p_events.add_argument('--limit', type=int, default=50, help='返回最近 N 条（默认 50）')
    p_events.add_argument('--json', action='store_true', dest='as_json',
                          help='机器可读 JSON 输出')

    # selfheal 子命令
    p_selfheal = sub.add_parser('selfheal', help='自愈引擎状态管理')
    p_selfheal.add_argument('action', choices=['status', 'reset', 'patterns'],
                            help='status=查看状态 / reset=重置 / patterns=错误模式')

    # template 子命令
    p_template = sub.add_parser('template', help='动作模板管理')
    p_template.add_argument('action', choices=['list', 'apply'],
                            help='list=列出模板 / apply=应用模板')
    p_template.add_argument('--id', help='模板 ID')
    p_template.add_argument('--action-id', help='目标动作 ID')
    p_template.add_argument('--name', help='动作名称')
    p_template.add_argument('--output', help='输出目录')

    # export 子命令
    p_export = sub.add_parser('export', help='导出动作执行历史')
    p_export.add_argument('--format', choices=['json', 'csv', 'markdown', 'md', 'html'],
                          default='json', help='导出格式')
    p_export.add_argument('--limit', type=int, default=0, help='记录数限制')
    p_export.add_argument('--output', help='输出文件路径')

    # project 子命令
    p_project = sub.add_parser('project', help='项目导入导出')
    p_project.add_argument('action', choices=['export', 'import', 'validate'],
                           help='export=导出 / import=导入 / validate=验证')
    p_project.add_argument('--file', help='.actus 文件路径')
    p_project.add_argument('--output', help='输出路径')
    p_project.add_argument('--meta', action='store_true', help='包含元数据')

    # viz 子命令
    p_viz = sub.add_parser('viz', help='工作流可视化')
    p_viz.add_argument('--format', choices=['ascii', 'mermaid', 'dot', 'html'],
                       default='ascii', help='输出格式')
    p_viz.add_argument('--output', help='输出文件路径')
    p_viz.add_argument('--action', help='指定动作 ID（可视化其工作流）')
    p_viz.add_argument('--sample', action='store_true',
                       help='无工作流定义时渲染内置示例（会明确标注是示例）')

    # replay 子命令
    p_replay = sub.add_parser('replay', help='重放历史执行')
    p_replay.add_argument('--run-id', help='执行记录 ID（run_id / id / exec_id 任一）')
    p_replay.add_argument('--dry-run', action='store_true', help='仅打印不执行')
    p_replay.add_argument('--limit', type=int, default=10,
                          help='最多重放最近 N 条（0=全部；--dry-run 同样遵守）')

    # notify 子命令
    p_notify = sub.add_parser('notify', help='通知系统管理')
    p_notify.add_argument('action', choices=['test', 'history', 'stats'],
                          help='test=测试通知 / history=历史 / stats=统计')

    # health 子命令
    p_health = sub.add_parser('health', help='系统健康检查')
    p_health.add_argument('--json', action='store_true', help='JSON 格式输出')
    p_health.add_argument('--check', help='只运行指定检查项')

    # sync 子命令
    p_sync = sub.add_parser('sync', help='同步已安装的动作仓库')
    p_sync.add_argument('--url', help='指定仓库 URL（默认全部）')
    p_sync.add_argument('--name', help='指定安装名称')
    p_sync.add_argument('--force', action='store_true', help='强制重新安装')

    # list-installed 子命令
    p_list_inst = sub.add_parser('list-installed', help='列出已安装的仓库')

    # rollback 子命令
    p_rollback = sub.add_parser('rollback', help='回滚已安装的仓库到指定版本')
    p_rollback.add_argument('--url', help='仓库 URL')
    p_rollback.add_argument('--name', help='安装名称')
    p_rollback.add_argument('--version', type=int, required=True, help='回滚版本号（1=上一版本）')

    # check-update 子命令
    p_check = sub.add_parser('check-update', help='检查已安装仓库是否有可用更新')
    p_check.add_argument('--url', help='仓库 URL')
    p_check.add_argument('--name', help='安装名称')

    # keygen 子命令
    p_keygen = sub.add_parser('keygen', help='生成签名密钥对')
    p_keygen.add_argument('--name', default='default', help='密钥名称')
    p_keygen.add_argument('--output', help='输出目录（默认 ~/.actus/keys）')

    # sign 子命令
    p_sign = sub.add_parser('sign', help='签名动作文件')
    p_sign.add_argument('path', help='动作文件路径')
    p_sign.add_argument('--key', default='default', help='密钥名称')

    # verify 子命令
    p_verify = sub.add_parser('verify', help='验证动作文件签名')
    p_verify.add_argument('path', help='动作文件路径')
    p_verify.add_argument('--key', default='default', help='公钥名称')

    # approve 子命令
    p_approve = sub.add_parser('approve', help='审批动作')
    p_approve.add_argument('action_id', help='动作 id')
    p_approve.add_argument('--reject', action='store_true', help='拒绝而非批准')
    p_approve.add_argument('--reason', default='', help='拒绝原因')

    # pending 子命令
    p_pending = sub.add_parser('pending', help='列出待审批的动作')

    # evolve 子命令
    p_evolve = sub.add_parser('evolve', help='自进化循环：AI 写动作→测试→修复直到通过')
    p_evolve.add_argument('description', nargs='?', help='动作用途的自然语言描述')
    p_evolve.add_argument('--action-id', help='指定动作 id（修复已有动作）')
    p_evolve.add_argument('--max-rounds', type=int, default=5, help='最大修复轮次（默认 5）')
    p_evolve.add_argument('--expect', help='期望条件 JSON')
    p_evolve.add_argument('--repair', action='store_true', help='修复已有动作模式')
    p_evolve.add_argument('--status', metavar='ACTION_ID', help='查询进化状态')
    p_evolve.add_argument('--history', metavar='ACTION_ID', help='查看进化历史')
    p_evolve.add_argument('--rollback', metavar='ACTION_ID', help='回滚到指定版本')
    p_evolve.add_argument('--version', type=int, help='回滚目标版本号')
    p_evolve.add_argument('--compare', metavar='ACTION_ID', help='A/B 对比两个版本')
    p_evolve.add_argument('--v1', type=int, help='对比版本 1')
    p_evolve.add_argument('--v2', type=int, help='对比版本 2')
    p_evolve.add_argument('--list', action='store_true', help='列出所有进化任务')

    # webhook 子命令
    p_webhook = sub.add_parser('webhook', help='Webhook 接收器管理')
    p_webhook.add_argument('--port', type=int, default=8765, help='监听端口（默认 8765）')
    p_webhook.add_argument('--host', default='0.0.0.0', help='监听地址（默认 0.0.0.0）')
    p_webhook.add_argument('--secret', default='', help='Webhook 密钥')
    p_webhook.add_argument('--no-signature', action='store_true', help='禁用签名验证')
    p_webhook.add_argument('--register', nargs=2, metavar=('EVENT', 'ACTION_ID'),
                           help='注册事件路由（事件类型 动作id）')
    p_webhook.add_argument('--unregister', metavar='EVENT', help='移除事件路由')
    p_webhook.add_argument('--status', action='store_true', help='查看运行状态')
    p_webhook.add_argument('--logs', type=int, metavar='LIMIT', help='查看请求日志')
    p_webhook.add_argument('--stop', action='store_true', help='停止接收器')

    # project-mgmt 子命令（多语言项目管理，避免与 project 导入导出冲突）
    p_project_mgmt = sub.add_parser('project-mgmt', help='多语言项目管理')
    p_project_mgmt.add_argument('--work-dir', default='.', help='工作目录（默认当前目录）')
    p_project_mgmt.add_argument('--project-file', default='.actus-project.json',
                                help='项目定义文件路径')
    p_project_mgmt.add_argument('--detect', action='store_true', help='自动检测语言和模块')
    p_project_mgmt.add_argument('--build', action='store_true', help='执行构建')
    p_project_mgmt.add_argument('--test', action='store_true', help='执行测试')
    p_project_mgmt.add_argument('--status', action='store_true', help='查看状态')
    p_project.add_argument('--validate', action='store_true', help='验证项目定义')
    p_project.add_argument('--phase', help='指定阶段（build/test/deploy/lint）')
    p_project.add_argument('--add-module', nargs=3,
                           metavar=('ID', 'LANG', 'PATH'),
                           help='添加模块（id 语言 路径）')
    p_project.add_argument('--remove-module', metavar='ID', help='移除模块')

    # visibility 子命令
    p_visibility = sub.add_parser('visibility', help='动作可见性管理')
    visibility_sub = p_visibility.add_subparsers(dest='visibility_command')

    p_vis_get = visibility_sub.add_parser('get', help='查询动作可见性')
    p_vis_get.add_argument('action_id', help='动作 id')

    p_vis_set = visibility_sub.add_parser('set', help='设置动作可见性')
    p_vis_set.add_argument('action_id', help='动作 id')
    p_vis_set.add_argument('--level', required=True,
                           choices=['public', 'unlisted', 'private', 'team'],
                           help='可见性级别')
    p_vis_set.add_argument('--team', help='团队名称（team 级别时必填）')

    # reg 子命令（多注册表管理）
    p_reg = sub.add_parser('reg', help='多注册表管理')
    reg_sub = p_reg.add_subparsers(dest='reg_command')

    p_reg_add = reg_sub.add_parser('add', help='添加注册表')
    p_reg_add.add_argument('name', help='注册表名称')
    p_reg_add.add_argument('url', help='注册表 URL')
    p_reg_add.add_argument('--type', default='http',
                       choices=['http', 'git', 'private'],
                       help='注册表类型（默认 http）')
    p_reg_add.add_argument('--branch', default='main', help='分支（默认 main）')
    p_reg_add.add_argument('--priority', type=int, default=50, help='优先级')

    p_reg_rm = reg_sub.add_parser('remove', help='移除注册表')
    p_reg_rm.add_argument('name', help='注册表名称')

    reg_sub.add_parser('list', help='列出所有注册表')

    # private 子命令
    p_priv = sub.add_parser('private', help='私有动作管理')
    priv_sub = p_priv.add_subparsers(dest='private_command')

    priv_sub.add_parser('list', help='列出私有动作')

    p_priv_add = priv_sub.add_parser('add', help='添加私有动作')
    p_priv_add.add_argument('action_id', help='动作 id')
    p_priv_add.add_argument('--author', default='', help='作者')
    p_priv_add.add_argument('--path', default='', help='本地路径')

    p_priv_rm = priv_sub.add_parser('remove', help='移除私有动作')
    p_priv_rm.add_argument('action_id', help='动作 id')

    # team 子命令
    p_team = sub.add_parser('team', help='团队管理')
    team_sub = p_team.add_subparsers(dest='team_command')

    p_team_create = team_sub.add_parser('create', help='创建团队')
    p_team_create.add_argument('name', help='团队名称')
    p_team_create.add_argument('--creator', required=True, help='创建者用户 id')

    p_team_add = team_sub.add_parser('add-member', help='添加团队成员')
    p_team_add.add_argument('--team', required=True, help='团队名称')
    p_team_add.add_argument('--user', required=True, help='用户 id')
    p_team_add.add_argument('--role', default='member',
                            choices=['admin', 'member', 'viewer'],
                            help='角色（默认 member）')

    p_team_rm = team_sub.add_parser('remove-member', help='移除团队成员')
    p_team_rm.add_argument('--team', required=True, help='团队名称')
    p_team_rm.add_argument('--user', required=True, help='用户 id')

    p_team_list = team_sub.add_parser('list', help='列出团队')
    p_team_list.add_argument('--team', help='团队名称（可选，不填列出所有）')

    # omega 子命令
    p_omega = sub.add_parser('omega', help='Ω-gate 验证引擎')
    omega_sub = p_omega.add_subparsers(dest='omega_command')

    p_omega_verify = omega_sub.add_parser('verify', help='验证动作输出')
    p_omega_verify.add_argument('action_id', help='动作 ID')
    p_omega_verify.add_argument('--output', required=True, help='实际输出 JSON 字符串或文件路径')
    p_omega_verify.add_argument('--spec', help='spec 文件路径（可选，自动查找）')
    p_omega_verify.add_argument('--loop', action='store_true', help='启用 Ω-loop 修复循环')
    p_omega_verify.add_argument('--diff', action='store_true', help='显示差异报告')

    p_omega_template = omega_sub.add_parser('template', help='生成 spec 模板')
    p_omega_template.add_argument('action_id', help='动作 ID')
    p_omega_template.add_argument('--example', required=True, help='输出示例 JSON')

    p_omega_learn = omega_sub.add_parser('learn', help='从历史执行推断 spec')
    p_omega_learn.add_argument('--action-id', help='动作 ID（可选）')
    p_omega_learn.add_argument('--limit', type=int, default=100, help='历史记录数量')

    p_omega_batch = omega_sub.add_parser('batch', help='批量验证')
    p_omega_batch.add_argument('--spec', required=True, help='spec 文件路径')
    p_omega_batch.add_argument('--inputs', required=True, help='输入 JSON 数组文件')

    p_omega_format = omega_sub.add_parser('format', help='格式化验证报告')
    p_omega_format.add_argument('--report', required=True, help='验证报告 JSON')

    # concurrency 子命令
    p_concurrency = sub.add_parser('concurrency', help='动作并发执行控制')
    concurrency_sub = p_concurrency.add_subparsers(dest='concurrency_command')

    p_conc_status = concurrency_sub.add_parser('status', help='查看并发状态')
    p_conc_status.add_argument('--action', help='动作 ID（可选，不填列出所有）')

    p_conc_set = concurrency_sub.add_parser('set', help='设置并发上限')
    p_conc_set.add_argument('--action', required=True, help='动作 ID')
    p_conc_set.add_argument('--max', type=int, required=True, help='最大实例数（0=无上限）')

    p_conc_reset = concurrency_sub.add_parser('reset', help='清除并发状态')
    p_conc_reset.add_argument('--action', help='动作 ID（可选，不填清除所有）')

    p_conc_list = concurrency_sub.add_parser('list', help='列出运行中实例')
    p_conc_list.add_argument('--action', help='动作 ID（可选）')

    return parser


def _dispatch(args) -> int:
    import vools.actus as actuscore
    # vools.actus 包没有把 indexer.build_index 转出来（Actus 侧 actuscore/__init__.py 有），
    # 直取子模块，否则 scan / validate 两条命令一调用就 AttributeError。
    from vools.actus.indexer import build_index

    if args.command == 'scan':
        idx = build_index()
        n = sum(1 for a in idx['actions'].values() if a.get('status') == 'valid')
        _out({'status': 'ok', 'data': {
            'total': len(idx['actions']), 'valid': n,
            'index': '_meta/actions.index.json'}})
        return 0

    if args.command == 'list':
        idx = actuscore.load_index()
        # 分类体系 v2.0（docs/03 §2）：kind/purpose/industry/tag 过滤
        kind_f = (getattr(args, 'kind', None) or '').strip().lower() or None
        purpose_f = (getattr(args, 'purpose', None) or '').strip().lower() or None
        industry_f = (getattr(args, 'industry', None) or '').strip().lower() or None
        tag_f = (getattr(args, 'tag', None) or '').strip().lower() or None
        tags = tag_f.split(',') if tag_f else None
        rows = []
        for aid, a in idx['actions'].items():
            if aid.startswith('_invalid:') and not args.all:
                continue
            if a.get('status') != 'valid' and not args.all:
                continue
            if kind_f and (a.get('kind') or 'exec') != kind_f:
                continue
            if purpose_f and purpose_f not in (a.get('purpose') or ['utility']):
                continue
            if industry_f and industry_f not in (a.get('industry') or ['general']):
                continue
            if tags and not any(t in (a.get('tags') or []) for t in tags):
                continue
            rows.append({k: a.get(k) for k in
                         ('id', 'name', 'version', 'trust', 'status', 'description',
                          'kind', 'purpose', 'industry', 'tags')})
        _out({'status': 'ok', 'data': {'actions': rows, 'count': len(rows)}})
        return 0

    if args.command == 'validate':
        if not args.action_id:
            idx = build_index()
            bad = {aid: a.get('errors') for aid, a in idx['actions'].items()
                   if a.get('status') != 'valid'}
            _out({'status': 'ok', 'data': {'valid': not bad, 'invalid': bad}})
            return 0 if not bad else 1
        action = actuscore.get_action(args.action_id)
        errs = actuscore.validate_action(action)
        _out({'status': 'ok' if not errs else 'failed',
              'data': {'id': args.action_id, 'errors': errs}})
        return 0 if not errs else 1

    if args.command == 'info':
        action = actuscore.get_action(args.action_id)
        _out({'status': 'ok', 'data': action.brief()})
        return 0

    if args.command == 'preview':
        # 文件高亮模式
        if args.file:
            from vools.actus.highlight import highlight_file
            mode = "html" if args.html else "terminal"
            result = highlight_file(args.file, theme=args.theme, mode=mode)
            print(result)
            return 0

        # 动作预览 + 代码高亮
        p = actuscore.preview(args.action_id, _parse_params(args.params))
        if args.html:
            from vools.actus.highlight import highlight_code
            # 对预览结果中的代码块进行高亮
            if 'code_blocks' in p.get('data', {}):
                for block in p['data']['code_blocks']:
                    block['highlighted'] = highlight_code(
                        block.get('code', ''),
                        block.get('language', args.lang),
                        theme=args.theme,
                        mode='html'
                    )
        _out({'status': 'ok', 'data': p})
        return 0

    if args.command == 'run':
        confirmed = args.confirm or args.yes
        # ── ACTUS_REFACTOR_PLAN 阶段1：接入 resolver ──
        # <target> 支持 id / name / md5 / path / url 六形态。
        # 此前直接把参数当 action_id 传给 execute，resolver.py 写完从未被
        # 任何模块调用 ⇒ 六种 target 形态与七种入参形态全部不生效。
        target = args.action_id
        _scattered_action = None
        try:
            from .resolver import resolve_target
            resolved = resolve_target(
                target,
                allow_hosts=getattr(args, 'allow_host', None),
                expect_digest=getattr(args, 'expect_digest', None),
                expect_signature_key=getattr(args, 'require_signature', None))
            if resolved.ambiguous:
                _out({'status': 'failed',
                      'error': {'code': 'ambiguous',
                                'message': f"目标 {target!r} 命中多个动作，请用完整 id 指定",
                                'details': {'candidates': resolved.ambiguous}}})
                return 1
            # 计划 §六.3：远程动作「下载即执行」的供应链风险 ⇒ 默认拒绝未校验远程
            if resolved.source == 'url' and not resolved.digest_verified \
                    and not getattr(args, 'allow_unverified_remote', False):
                _out({'status': 'failed',
                      'error': {'code': 'remote_unverified',
                                'message': '拒绝执行未经指纹校验的远程动作：请用 '
                                           '--expect-digest <sha256> 指定期望指纹，'
                                           '或显式 --allow-unverified-remote 自担风险',
                                'details': {'url': resolved.url,
                                            'sha256': resolved.sha256}}})
                return 1
            if resolved.source == 'path' and resolved.path:
                # 散落动作不在索引里：解析成 Action 走 preparsed_action 通道
                from .scattered import resolve_scattered, _apply_scattered_defaults
                from .model import parse_cfg_from_file
                sc = resolve_scattered(resolved.path)
                action = parse_cfg_from_file(sc.path)
                _apply_scattered_defaults(action, sc)
                _scattered_action = action
                target = resolved.action_id or action.meta.get('id') or target
            elif resolved.action_id:
                target = resolved.action_id
        except Exception:
            # 解析失败不阻断旧路径（零回归）：原值交给 execute，给出原有错误文案
            pass
        try:
            from .resolver import resolve_params_extended
            params = resolve_params_extended(args.params)
        except Exception:
            params = _parse_params(args.params)
        r = actuscore.execute(target, params, confirmed=confirmed,
                              preparsed_action=_scattered_action)
        _out(r)
        if r['status'] == 'awaiting_confirmation':
            print(f"待人类确认：再次执行并加 --confirm / --yes 放行（exec: {r['exec_id']}）",
                  file=sys.stderr)
        return 0 if r['status'] == 'ok' else 1

    if args.command == 'status':
        from vools.actus import records as rec
        if args.exec_id:
            r = rec.load_run_record(None, args.exec_id)
            if r is None:
                _out({'status': 'failed', 'error': {
                    'code': 'action_not_found', 'message': f'执行记录不存在: {args.exec_id}'}})
                return 1
            # 查询语义：缓存/记录里的 status 描述的是「被执行的那次运行」，
            # 不是「本次查询的成败」——所以传 status_field=None 让它恒为 ok
            # （查询失败已在上面 return 1）。不能直接套操作类映射，否则
            # `status <失败的 exec_id>` 会把一次成功的查询报成 CLI 失败。
            return _out_result(r, status_field=None)
        return _out_result(rec.load_status(None), status_field=None)

    if args.command == 'loop':
        return _dispatch_loop(args)

    if args.command == 'config':
        return _gen_config(args.client)

    if args.command == 'scaffold':
        from vools.actus.scaffold import scaffold_action
        from vools.actus.errors import ActionError
        from vools.actus.indexer import _repo_root
        try:
            # 显式传 repo_root：scaffold 内部推断的默认目录恰好等于 _repo_root()，
            # 所以默认行为不变；但显式传入后 ACTUS_REPO_ROOT 才真正生效
            # （测试/多仓库场景需要把写入重定向到临时仓库），也与 viz/author
            # 等命令的「仓库由 _repo_root() 决定」口径一致。
            r = scaffold_action(args.description, action_id=args.action_id,
                                trust=args.trust, repo_root=_repo_root(),
                                force=getattr(args, 'force', False))
        except ActionError as exc:
            # 撞已有动作文件：明确失败并 rc≠0。改前这里会静默覆盖用户动作、
            # 还打印 status=ok —— 用户看到"生成成功"根本不知道文件被替换了。
            _out({'status': 'failed',
                  'error': {'code': exc.code, 'message': exc.message,
                            'details': exc.details}})
            print(f'❌ {exc.message}', file=sys.stderr)
            return 1
        # scaffold 的返回体没有 status，靠 validation.valid 判定（helper 内处理）：
        # 改前 scaffold 生成后校验不过也报 status=ok + exit 0。
        return _out_result(r)

    if args.command == 'author':
        from vools.actus.author import author_action
        r = author_action(args.action_id, args.instruction)
        # 改前：恒 `_out({'status': 'ok', ...}); return 0` —— CLI 不注入 ai_edit，
        # 实现只往动作文件追加一行 `# AI-MODIFIED` 注释（代码一字未改、
        # ai_applied=False），顶层却报 ok/exit 0。现在由子结果映射：
        # 未接 AI / 校验不过 → status: failed + exit 1（消息打到 stderr）。
        return _out_result(r)

    if args.command == 'workflow':
        from vools.actus.workflow import run_workflow
        repo_root = os.environ.get('ACTUS_REPO_ROOT', '')
        meta_dir = os.path.join(repo_root, '_meta')
        r = run_workflow(args.workflow_id, meta_dir=meta_dir,
                         max_workers=args.max_workers, confirmed=args.confirmed)
        # workflow 的 status ∈ ok / failed / partial；只有 ok 才是成功。
        return _out_result(r)

    if args.command == 'vault':
        return _dispatch_vault(args)

    if args.command == 'runtimes':
        from vools.actus.runtimes import get_available_runtimes
        langs = get_available_runtimes()
        _out({'status': 'ok', 'available': langs})
        return 0

    if args.command == 'execute':
        return _dispatch_execute(args)

    if args.command == 'records':
        return _dispatch_records(args)

    if args.command == 'artifacts':
        return _dispatch_artifacts(args)

    if args.command == 'triggers':
        return _dispatch_triggers(args)

    # 动作市场命令
    if args.command == 'registry':
        return _cmd_registry(args)

    # 多注册表 / 团队 / 私有动作 / 可见性（改前 parser 声明了但这里没有分支，
    # 实测 rc=2 + 零输出 → 用户敲 `actus team` 什么都看不到）
    if args.command == 'reg':
        return _cmd_reg(args)

    if args.command == 'team':
        return _cmd_team(args)

    if args.command == 'private':
        return _cmd_private(args)

    if args.command == 'visibility':
        return _cmd_visibility(args)

    if args.command == 'install':
        return _cmd_install(args)

    if args.command == 'uninstall':
        return _cmd_uninstall(args)

    if args.command == 'publish':
        return _cmd_publish(args)

    if args.command == 'search':
        return _cmd_search(args)

    if args.command == 'sync':
        return _cmd_sync(args)

    if args.command == 'list-installed':
        return _cmd_list_installed(args)

    if args.command == 'rollback':
        return _cmd_rollback(args)

    if args.command == 'check-update':
        return _cmd_check_update(args)

    # 信任模型命令
    if args.command == 'keygen':
        return _cmd_keygen(args)

    if args.command == 'sign':
        return _cmd_sign(args)

    if args.command == 'verify':
        return _cmd_verify(args)

    if args.command == 'approve':
        return _cmd_approve(args)

    if args.command == 'pending':
        return _cmd_pending(args)

    # 进化命令
    if args.command == 'evolve':
        return _cmd_evolve(args)

    # Dialog 命令
    if args.command == 'dialog':
        return _cmd_dialog(args)

    # Webhook 命令
    if args.command == 'webhook':
        return _cmd_webhook(args)

    # Project 命令
    if args.command == 'project':
        return _cmd_project_io(args)

    # Project-mgmt 命令
    if args.command == 'project-mgmt':
        return _cmd_project(args)

    # Omega 命令
    if args.command == 'omega':
        return _cmd_omega(args)

    # Concurrency 命令
    if args.command == 'concurrency':
        return _cmd_concurrency(args)

    # Deps 命令
    if args.command == 'deps':
        return _cmd_deps(args)

    # Dep-tree 命令
    if args.command == 'dep-tree':
        return _cmd_dep_tree(args)

    # Desktop 命令
    if args.command == 'desktop':
        return _cmd_desktop(args)

    # Events 命令
    if args.command == 'events':
        return _cmd_events(args)

    # Selfheal 命令
    if args.command == 'selfheal':
        return _cmd_selfheal(args)

    # Template 命令
    if args.command == 'template':
        return _cmd_template(args)

    # Export 命令
    if args.command == 'export':
        return _cmd_export(args)

    # Viz 命令
    if args.command == 'viz':
        return _cmd_viz(args)

    # Replay 命令
    if args.command == 'replay':
        return _cmd_replay(args)

    # Notify 命令
    if args.command == 'notify':
        return _cmd_notify(args)

    # Health 命令
    if args.command == 'health':
        return _cmd_health(args)

    # Probe 命令（环境探测器，PROBE_PLAN.md §9 Phase 3）
    if args.command == 'probe':
        return _cmd_probe(args)

    return 2


def _dispatch_loop(args) -> int:
    """loop_prompt 会话管理（docs/25 §6.5）：stop / status / list。

    stop 语义：向会话项目目录写 .loop_prompt.stop 信号文件，
    循环在下一个 tick 内退出并删除该文件（非硬杀，保证留痕完整）。
    """
    import glob as _glob
    import os
    from vools.actus.indexer import _repo_root

    _meta_base = os.environ.get('ACTUS_META_DIR') or os.path.join(_repo_root(), '_meta')
    loops_dir = os.path.join(_meta_base, 'loops')
    sessions = sorted(_glob.glob(os.path.join(loops_dir, 'loop-*.json')))

    if args.loop_command == 'list':
        rows = []
        for p in sessions:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    s = json.load(f)
            except (OSError, ValueError):
                continue
            rows.append({
                'session_id': s.get('session_id'),
                'project_dir': s.get('project_dir'),
                'started_at': s.get('started_at'),
                'finished_at': s.get('finished_at'),
                'exit_reason': s.get('exit_reason'),
                'rounds_delivered': len(s.get('rounds') or []),
            })
        _out({'status': 'ok', 'data': {'sessions': rows, 'count': len(rows)}})
        return 0

    if args.loop_command == 'status':
        if args.session:
            matches = [p for p in sessions
                       if os.path.basename(p).startswith(args.session)]
            if not matches:
                _out({'status': 'failed', 'error': {
                    'code': 'action_not_found',
                    'message': f'会话不存在: {args.session}'}})
                return 1
            path = matches[-1]
        else:
            if not sessions:
                _out({'status': 'failed', 'error': {
                    'code': 'action_not_found', 'message': '尚无 loop_prompt 会话'}})
                return 1
            path = sessions[-1]
        try:
            with open(path, 'r', encoding='utf-8') as f:
                s = json.load(f)
        except (OSError, ValueError) as e:
            _out({'status': 'failed', 'error': {'code': 'internal',
                                                'message': str(e)}})
            return 1
        ticks_path = path[:-len('.json')] + '.ticks.jsonl'
        recent = []
        if os.path.exists(ticks_path):
            with open(ticks_path, 'r', encoding='utf-8') as f:
                for line in f.readlines()[-5:]:
                    try:
                        recent.append(json.loads(line))
                    except ValueError:
                        pass
        _out({'status': 'ok', 'data': {'session': s, 'recent_ticks': recent}})
        return 0

    if args.loop_command == 'stop':
        target = args.session
        proj_dir = None
        for p in sessions:
            if os.path.basename(p).startswith(target):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        s = json.load(f)
                except (OSError, ValueError):
                    continue
                if s.get('finished_at'):
                    _out({'status': 'failed', 'error': {
                        'code': 'param_invalid',
                        'message': f"会话已结束（exit_reason={s.get('exit_reason')}）"}})
                    return 1
                proj_dir = s.get('project_dir')
                break
        if proj_dir is None and os.path.isdir(target):
            proj_dir = target  # 也接受直接给项目路径
        if proj_dir is None:
            _out({'status': 'failed', 'error': {
                'code': 'action_not_found',
                'message': f'找不到进行中的会话或有效项目目录: {target}'}})
            return 1
        stop_path = os.path.join(proj_dir, '.loop_prompt.stop')
        with open(stop_path, 'w', encoding='utf-8') as f:
            f.write('')
        _out({'status': 'ok', 'data': {
            'stop_file': stop_path.replace(os.sep, '/'),
            'hint': '循环将在下一个 tick 内退出并清理 stop 文件'}})
        return 0

    _out({'status': 'failed', 'error': {
        'code': 'param_invalid', 'message': '用法: actus loop stop|status|list'}})
    return 1


def _dispatch_vault(args) -> int:
    """密钥保险库子命令分发。"""
    from vools.actus.vault import Vault
    import os as _os

    repo_root = _os.environ.get('ACTUS_REPO_ROOT', '')
    meta_dir = _os.path.join(repo_root, '_meta')
    vault = Vault(meta_dir)

    if args.vault_command == 'set':
        r = vault.set(args.key, args.value, args.scope, args.desc)
        _out(r)
        return 0
    elif args.vault_command == 'get':
        val = vault.get(args.key, args.scope)
        if val is None:
            _out({'status': 'not_found', 'message': f'密钥不存在: {args.key}'})
            return 1
        _out({'status': 'ok', 'key': args.key, 'scope': args.scope, 'value': val})
        return 0
    elif args.vault_command == 'list':
        keys = vault.list(args.scope)
        _out({'status': 'ok', 'keys': keys})
        return 0
    elif args.vault_command == 'delete':
        deleted = vault.delete(args.key, args.scope)
        _out({'status': 'ok' if deleted else 'not_found', 'deleted': deleted})
        return 0 if deleted else 1
    else:
        _out({'status': 'failed', 'error': {'code': 'invalid_command',
                                            'message': 'vault 子命令: set/get/list/delete'}})
        return 2


def _dispatch_triggers(args) -> int:
    """触发器引擎子命令分发。"""
    import os as _os
    from vools.actus.triggers import Trigger, validate_trigger, TriggerEngine

    repo_root = _os.environ.get('ACTUS_REPO_ROOT', '')
    meta_dir = _os.path.join(repo_root, '_meta')

    def _executor(trigger, event=None):
        import vools.actus as actuscore
        try:
            actuscore.execute(trigger.action_id, trigger.args or {})
        except Exception:
            pass

    engine = TriggerEngine(_executor, meta_dir)

    if args.triggers_command == 'add':
        config = {'type': args.type}
        if args.expr:
            config['expr'] = args.expr
        if args.path:
            config['path'] = args.path
        if args.events:
            config['events'] = args.events
        if args.recursive:
            config['recursive'] = True
        if args.key:
            config['key'] = args.key
        try:
            trigger_args = json.loads(args.args) if args.args else {}
            config['args'] = trigger_args
        except json.JSONDecodeError:
            pass

        errors = validate_trigger(config)
        if errors:
            _out({'status': 'failed', 'error': {'code': 'validation_error',
                                                'message': '; '.join(errors)}})
            return 1

        trigger = Trigger(args.action_id, config)
        engine.add_trigger(trigger)
        _out({'status': 'ok', 'action_id': args.action_id, 'type': args.type})
        return 0

    elif args.triggers_command == 'list':
        result = {}
        for aid, triggers in engine._triggers.items():
            result[aid] = [t.config for t in triggers]
        _out({'status': 'ok', 'triggers': result})
        return 0

    elif args.triggers_command == 'status':
        status = engine.status()
        _out({'status': 'ok', 'engine': status})
        return 0

    elif args.triggers_command == 'remove':
        engine.remove_trigger(args.action_id)
        _out({'status': 'ok', 'removed': args.action_id})
        return 0

    else:
        _out({'status': 'failed', 'error': {'code': 'invalid_command',
                                            'message': 'triggers 子命令: add/list/status/remove'}})
        return 2


def _dispatch_execute(args) -> int:
    """执行代码段子命令分发。"""
    from vools.actus.runtimes import execute_block, get_available_runtimes

    # 获取代码
    code = args.code
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            code = f.read()
    if not code:
        _out({'status': 'failed', 'error': {'code': 'missing_code',
                                            'message': '请通过 --code 或 --file 提供代码'}})
        return 1

    # 检查语言是否可用
    available = get_available_runtimes()
    if args.language not in available:
        _out({'status': 'failed', 'error': {
            'code': 'unsupported_language',
            'message': f'不支持的语言: {args.language}。可用: {", ".join(available)}'
        }})
        return 1

    # 构建执行上下文
    context = {}
    if args.args:
        context['args'] = args.args
    if args.stdin:
        context['stdin'] = args.stdin
    if args.env:
        try:
            context['env'] = json.loads(args.env)
        except json.JSONDecodeError:
            pass

    try:
        stdout, stderr, exit_code = execute_block(args.language, code, context)
        _out({'status': 'ok', 'language': args.language,
              'stdout': stdout, 'stderr': stderr, 'exit_code': exit_code})
        return exit_code
    except Exception as e:
        _out({'status': 'failed', 'error': {'code': 'execution_error',
                                            'message': f'{type(e).__name__}: {e}'}})
        return 1


def _dispatch_records(args) -> int:
    """执行记录子命令分发。"""
    from vools.actus.records import list_run_records, export_records

    if args.records_command == 'list':
        records = list_run_records(None, args.action_id, args.limit, args.offset)
        _out({'status': 'ok', 'total': len(records), 'records': records})
        return 0
    elif args.records_command == 'export':
        if args.format not in ('json', 'csv', 'summary'):
            _out({'status': 'failed', 'error': {'code': 'invalid_format',
                                                'message': '输出格式必须是 json/csv/summary'}})
            return 1
        result = export_records(None, args.action_id, args.format,
                                args.output, args.limit)
        _out({'status': 'ok', **result})
        return 0
    else:
        _out({'status': 'failed', 'error': {'code': 'invalid_command',
                                            'message': 'records 子命令: list/export'}})
        return 2


def _dispatch_artifacts(args) -> int:
    """产物管理子命令分发。"""
    from vools.actus.records import list_artifacts, cleanup_artifacts

    if args.artifacts_command == 'list':
        artifacts = list_artifacts(None, args.action_id, args.exec_id, args.type)
        _out({'status': 'ok', 'total': len(artifacts), 'artifacts': artifacts})
        return 0
    elif args.artifacts_command == 'cleanup':
        result = cleanup_artifacts(None, args.max_age_days, args.max_count)
        _out({'status': 'ok', **result})
        return 0
    else:
        _out({'status': 'failed', 'error': {'code': 'invalid_command',
                                            'message': 'artifacts 子命令: list/cleanup'}})
        return 2


def _gen_config(client: str) -> int:
    """生成指定 AI 客户端的 MCP server 配置片段（docs/10 §A.4）。"""
    import os
    import sys

    # 自动检测 Python 解释器路径与仓库根
    python_path = sys.executable
    # 仓库根 = engine 的上两级目录
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(engine_dir))

    mcp_args = json.dumps(["-m", "actus", "mcp"])
    env_block = json.dumps({
        "PYTHONPATH": repo_root + "/engine",
        "PYTHONIOENCODING": "utf-8"
    }, indent=4)

    configs = {
        'claude': (
            '将以下配置添加到 Claude Desktop 的 claude_desktop_config.json：\n'
            '(菜单 → File → Settings → Developer → Edit Config → mcpServers)\n\n'
            '```json\n'
            '{\n'
            '  "mcpServers": {\n'
            '    "actus": {\n'
            f'      "command": {json.dumps(python_path)},\n'
            f'      "args": {mcp_args},\n'
            f'      "env": {env_block}\n'
            '    }\n'
            '  }\n'
            '}\n'
            '```'
        ),
        'cursor': (
            '将以下配置添加到 Cursor 的 .cursor/mcp.json（项目级）或全局设置：\n\n'
            '```json\n'
            '{\n'
            '  "mcpServers": {\n'
            '    "actus": {\n'
            f'      "command": {json.dumps(python_path)},\n'
            f'      "args": {mcp_args},\n'
            f'      "env": {env_block}\n'
            '    }\n'
            '  }\n'
            '}\n'
            '```'
        ),
        'cline': (
            '将以下配置添加到 Cline / Continue 的 MCP 设置：\n\n'
            '```json\n'
            '{\n'
            '  "mcpServers": {\n'
            '    "actus": {\n'
            f'      "command": {json.dumps(python_path)},\n'
            f'      "args": {mcp_args},\n'
            f'      "env": {env_block}\n'
            '    }\n'
            '  }\n'
            '}\n'
            '```'
        ),
        'vscode': (
            '将以下配置添加到 VS Code 的 settings.json（.vscode/settings.json）：\n\n'
            '```json\n'
            '{\n'
            '  "mcp.servers": {\n'
            '    "actus": {\n'
            '      "type": "stdio",\n'
            f'      "command": {json.dumps(python_path)},\n'
            f'      "args": {mcp_args},\n'
            f'      "env": {env_block}\n'
            '    }\n'
            '  }\n'
            '}\n'
            '```'
        ),
    }

    print(configs[client])
    print()
    print('提示：配置生效可能需要重启 AI 客户端。')
    return 0


def _parse_params(s: str) -> dict:
    if not s or s == '{}':
        return {}
    try:
        v = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f'入参不是合法 JSON: {e}') from e
    if not isinstance(v, dict):
        raise ValueError('入参必须是 JSON object')
    return v


# ── 动作市场命令 ──

# ── 多注册表 / 团队 / 私有动作 / 可见性（visibility.py 的 CLI 接线）──
# 改前这四个命令族在 parser 里声明了，但 _dispatch 里**没有任何分支**：
# 实测 `actus team` 等一律 rc=2 + 零输出 —— 连「命令不存在」都不说一声，
# 是本项目假功能家族里最阴的一种（静默失联）。
# 支撑能力一直在 vools/actus/visibility.py（RegistryManager / TeamManager /
# VisibilityEngine），本轮把这些能力真正接到 CLI 上。


def _vis_config_dir():
    """visibility 家族的配置目录：默认 ~/.actus，可用 ACTUS_CONFIG_DIR 覆盖。"""
    return os.environ.get('ACTUS_CONFIG_DIR') or None


def _cmd_reg(args) -> int:
    """reg 子命令：多注册表管理（visibility.RegistryManager）。"""
    from vools.actus.visibility import RegistryManager, RegistryConfig

    manager = RegistryManager(_vis_config_dir())
    command = getattr(args, 'reg_command', None)

    if command is None:
        print('用法: actus reg <add|remove|list>', file=sys.stderr)
        return 1

    if command == 'list':
        registries = manager.list_registries()
        if not registries:
            print('📭 暂无注册表配置')
            return 0
        print(f'📚 已配置注册表 ({len(registries)}):')
        for registry in registries:
            print(f'   - {registry.name} [{registry.registry_type}] {registry.url} '
                  f'(branch={registry.branch}, priority={registry.priority})')
        return 0

    if command == 'add':
        if manager.get_registry(args.name) is not None:
            print(f'❌ 注册表已存在: {args.name}', file=sys.stderr)
            return 1
        manager.add_registry(RegistryConfig(
            name=args.name, url=args.url, registry_type=args.type,
            branch=args.branch, priority=args.priority))
        print(f'✅ 已添加注册表: {args.name} ({args.url})')
        return 0

    if command == 'remove':
        if manager.remove_registry(args.name) is None:
            print(f'❌ 注册表不存在: {args.name}', file=sys.stderr)
            return 1
        print(f'✅ 已移除注册表: {args.name}')
        return 0

    print(f'❌ 未知的 reg 子命令: {command}', file=sys.stderr)
    return 1


def _cmd_team(args) -> int:
    """team 子命令：团队管理（visibility.TeamManager）。"""
    from vools.actus.visibility import TeamManager

    manager = TeamManager(_vis_config_dir())
    command = getattr(args, 'team_command', None)

    if command is None:
        print('用法: actus team <create|list|add-member|remove-member>', file=sys.stderr)
        return 1

    if command == 'list':
        wanted = getattr(args, 'team', None)
        if wanted:
            team = manager.get_team(wanted)
            if team is None:
                print(f'❌ 团队不存在: {wanted}', file=sys.stderr)
                return 1
            print(f'👥 团队 {team.name} ({len(team.members)} 名成员):')
            for member in team.members:
                print(f'   - {member.user_id} ({member.role})')
            return 0
        names = manager.list_teams()
        if not names:
            print('📭 暂无团队')
            return 0
        print(f'👥 团队 ({len(names)}):')
        for name in names:
            team = manager.get_team(name)
            print(f'   - {name} ({len(team.members) if team else 0} 名成员)')
        return 0

    if command == 'create':
        if manager.get_team(args.name) is not None:
            print(f'❌ 团队已存在: {args.name}', file=sys.stderr)
            return 1
        team = manager.create_team(args.name, args.creator)
        print(f'✅ 已创建团队: {team.name}（创建者 {args.creator} 为 admin）')
        return 0

    if command == 'add-member':
        if manager.add_member(args.team, args.user, args.role):
            print(f'✅ 已添加成员: {args.user} → {args.team} ({args.role})')
            return 0
        print(f'❌ 添加失败: 团队不存在或成员已在团队里（{args.team} / {args.user}）',
              file=sys.stderr)
        return 1

    if command == 'remove-member':
        if manager.remove_member(args.team, args.user):
            print(f'✅ 已移除成员: {args.user} ← {args.team}')
            return 0
        print(f'❌ 移除失败: 团队不存在或该成员不在团队里（{args.team} / {args.user}）',
              file=sys.stderr)
        return 1

    print(f'❌ 未知的 team 子命令: {command}', file=sys.stderr)
    return 1


def _cmd_private(args) -> int:
    """private 子命令：私有动作管理（visibility.VisibilityEngine）。"""
    from vools.actus.visibility import VisibilityEngine

    engine = VisibilityEngine(config_dir=_vis_config_dir())
    command = getattr(args, 'private_command', None)

    if command is None:
        print('用法: actus private <add|remove|list>', file=sys.stderr)
        return 1

    if command == 'list':
        actions = engine.list_private_actions()
        if not actions:
            print('📭 暂无私有动作')
            return 0
        print(f'🔒 私有动作 ({len(actions)}):')
        for entry in actions:
            action_id = entry.get('action_id') or entry.get('id') or '?'
            author = entry.get('author') or ''
            path = entry.get('path') or ''
            extra = ''
            if author:
                extra += f' (author={author})'
            if path:
                extra += f' → {path}'
            print(f'   - {action_id}{extra}')
        return 0

    if command == 'add':
        metadata = {}
        if getattr(args, 'author', ''):
            metadata['author'] = args.author
        if getattr(args, 'path', ''):
            metadata['path'] = args.path
        engine.add_private_action(args.action_id, metadata)
        print(f'✅ 已登记私有动作: {args.action_id}')
        return 0

    if command == 'remove':
        if engine.remove_private_action(args.action_id):
            print(f'✅ 已移除私有动作: {args.action_id}')
            return 0
        print(f'❌ 私有动作不存在: {args.action_id}', file=sys.stderr)
        return 1

    print(f'❌ 未知的 private 子命令: {command}', file=sys.stderr)
    return 1


# 动作文件里的 ```json #!cfg 元数据块（与 adapter.py 的解析口径一致）
_CFG_BLOCK_RE = re.compile(r"(```json\s*#!cfg\s*\n)(.*?)(```)", re.DOTALL)


def _write_action_visibility(action_path: str, level: str):
    """把动作 `#!cfg` 块里的 visibility 改成 level，返回 (ok, message)。

    只动这一个标量：块里已有 "visibility" 就替换它的值，没有就插到块首。
    **写完立刻重新解析整份动作文件**校验，不通过就把原文写回去并报错 ——
    宁可失败也不留一份解析不了的动作文件（本仓库的 scaffolder 曾整体覆盖过
    动作文件，这里不想重演那次事故）。
    """
    try:
        with open(action_path, 'r', encoding='utf-8') as handle:
            original = handle.read()
    except OSError as exc:
        return False, f'读取动作文件失败: {exc}'

    match = _CFG_BLOCK_RE.search(original)
    if match is None:
        return False, '动作文件里找不到 ```json #!cfg``` 元数据块'

    block = match.group(2)
    if re.search(r'"visibility"\s*:\s*"[^"]*"', block):
        new_block = re.sub(r'("visibility"\s*:\s*)"[^"]*"',
                           lambda m: m.group(1) + '"%s"' % level, block, count=1)
    else:
        brace = block.find('{')
        if brace < 0:
            return False, '#!cfg 块不是 JSON 对象'
        new_block = (block[:brace + 1]
                     + '\n  "visibility": "%s",' % level
                     + block[brace + 1:])

    updated = original[:match.start(2)] + new_block + original[match.end(2):]
    try:
        with open(action_path, 'w', encoding='utf-8') as handle:
            handle.write(updated)
        from vools.actus.model import parse_cfg_from_file
        parsed = parse_cfg_from_file(action_path)
        if (parsed.meta.get('visibility') or '').strip().lower() != level:
            raise ValueError('写回后 visibility 校验不一致')
    except Exception as exc:
        try:
            with open(action_path, 'w', encoding='utf-8') as handle:
                handle.write(original)          # 回滚到原文
        except OSError:
            pass
        return False, f'{type(exc).__name__}: {exc}（已回滚原文件）'
    return True, ''


def _cmd_visibility(args) -> int:
    """visibility 子命令：动作可见性查询 / 设置。

    get 读真实来源（私有动作索引 / 动作文件 #!cfg 的 visibility 字段）；
    set 用 `_write_action_visibility` 定点改写 #!cfg 里的可见性并校验回滚。
    """
    from vools.actus.visibility import VisibilityEngine

    engine = VisibilityEngine(config_dir=_vis_config_dir())
    command = getattr(args, 'visibility_command', None)

    if command is None:
        print('用法: actus visibility <get|set>', file=sys.stderr)
        return 1

    if command == 'get':
        if engine.get_private_action(args.action_id) is not None:
            print(f'🔒 {args.action_id}: private（私有动作索引）')
            return 0
        try:
            import vools.actus as actuscore
            action = actuscore.get_action(args.action_id)
        except Exception as exc:
            print(f'❌ 无法读取动作 {args.action_id}: {exc}', file=sys.stderr)
            return 1
        level = (action.meta.get('visibility') or 'public').strip().lower()
        print(f'👁️  {args.action_id}: {level}')
        return 0

    if command == 'set':
        level = args.level
        if level == 'team':
            if not args.team:
                print('❌ --level team 需要同时用 --team 指定团队名', file=sys.stderr)
                return 1
            from vools.actus.visibility import TeamManager
            if TeamManager(_vis_config_dir()).get_team(args.team) is None:
                print(f'❌ 团队不存在: {args.team}', file=sys.stderr)
                return 1
        try:
            import vools.actus as actuscore
            action = actuscore.get_action(args.action_id)
        except Exception as exc:
            print(f'❌ 无法读取动作 {args.action_id}: {exc}', file=sys.stderr)
            return 1

        action_path = getattr(action, 'path', '') or ''
        if not action_path or not os.path.isfile(action_path):
            print(f'❌ 找不到动作文件: {args.action_id}', file=sys.stderr)
            return 1

        old_level = (action.meta.get('visibility') or 'public').strip().lower()
        ok, message = _write_action_visibility(action_path, level)
        if not ok:
            print(f'❌ 设置可见性失败: {message}', file=sys.stderr)
            return 1
        print(f'✅ 可见性已更新: {args.action_id} {old_level} → {level}')
        if level == 'team':
            print(f'   团队: {args.team}')
        return 0

    print(f'❌ 未知的 visibility 子命令: {command}', file=sys.stderr)
    return 1


def _cmd_registry(args) -> int:
    """registry 子命令：构建/校验/查看注册表索引。"""
    from vools.actus.registry import ActionRegistry

    reg = ActionRegistry()

    if args.registry_command == 'build':
        repo_dir = os.getcwd()
        index = reg.build_from_directory(repo_dir)
        output = args.output or os.path.join(repo_dir, '.actus.registry.json')
        print(f'✅ 注册表索引已构建: {output}')
        print(f'   动作数量: {len(index.get("actions", []))}')
        return 0

    elif args.registry_command == 'validate':
        index_path = args.index or os.path.join(os.getcwd(), '.actus.registry.json')
        if not os.path.isfile(index_path):
            print(f'❌ 索引文件不存在: {index_path}')
            return 1
        index = reg.load_from_file(index_path)
        repo_dir = os.path.dirname(os.path.abspath(index_path))
        actions = index.get('actions', [])
        valid_count = 0
        for raw in actions:
            entry = raw if isinstance(raw, dict) else raw.to_dict() if hasattr(raw, 'to_dict') else {}
            # 简单校验
            aid = entry.get('id', '')
            if aid:
                valid_count += 1
        print(f'✅ 注册表校验通过: {valid_count}/{len(actions)} 个动作有效')
        return 0

    elif args.registry_command == 'info':
        index_path = args.index or os.path.join(os.getcwd(), '.actus.registry.json')
        if not os.path.isfile(index_path):
            print(f'❌ 索引文件不存在: {index_path}')
            return 1
        index = reg.load_from_file(index_path)
        print(f'📦 注册表: {index.get("name", "unknown")}')
        print(f'   版本: {index.get("version", "?")}')
        print(f'   作者: {index.get("author", "?")}')
        print(f'   描述: {index.get("description", "?")}')
        print(f'   动作数: {len(index.get("actions", []))}')
        for a in index.get('actions', []):
            print(f'   - {a.get("id", "?")} ({a.get("version", "?")})')
        return 0

    else:
        print('请指定子命令: build / validate / info')
        return 1


def _cmd_install(args) -> int:
    """install 子命令：从 Git 仓库安装动作。"""
    from vools.actus.installer import ActionInstaller

    kwargs = {'repo_url': args.url}
    if args.branch:
        kwargs['branch'] = args.branch
    if args.tag:
        kwargs['tag'] = args.tag
    if args.commit:
        kwargs['commit'] = args.commit
    if args.scope:
        kwargs['scope'] = args.scope
    if args.dir:
        kwargs['install_dir'] = args.dir

    installer = ActionInstaller()
    result = installer.install(**kwargs)

    if result.get('status') == 'ok':
        print(f'✅ 安装成功: {result.get("name")}')
        print(f'   路径: {result.get("path")}')
        print(f'   动作数: {result.get("action_count", 0)}')
        for aid in result.get('actions', []):
            print(f'   - {aid}')
        return 0
    else:
        print(f'❌ 安装失败: {result.get("message", "未知错误")}')
        return 1


def _cmd_uninstall(args) -> int:
    """uninstall 子命令：卸载已安装的动作仓库。"""
    from vools.actus.installer import ActionInstaller

    installer = ActionInstaller()
    result = installer.uninstall(repo_url=args.url, name=args.name)

    if result.get('status') == 'ok':
        print(f'✅ 已卸载: {result.get("removed")}')
        return 0
    else:
        print(f'❌ 卸载失败: {result.get("message", "未知错误")}')
        return 1


def _publish_sign_actions(index: dict, repo_dir: str, key_name: str):
    """签名索引里的每个动作文件，返回 (已签名列表, 失败列表)。

    复用 `actus sign` 同一条链路（trust_model.SignatureVerifier.sign_file），
    不另写签名实现。失败项带可读原因，调用方决定退出码。
    """
    from vools.actus.trust_model import SignatureVerifier

    verifier = SignatureVerifier()
    signed = []
    failures = []
    for entry in index.get('actions', []) or []:
        if not isinstance(entry, dict):
            continue
        action_id = entry.get('id', '?')
        rel_path = entry.get('path') or ''
        fpath = os.path.join(repo_dir, rel_path) if rel_path else ''
        if not fpath or not os.path.isfile(fpath):
            failures.append((action_id, f'找不到动作文件: {rel_path or "<path 缺失>"}'))
            continue
        result = verifier.sign_file(fpath, key_name=key_name)
        if result.get('status') == 'ok':
            signed.append((action_id, result.get('output', '')))
        else:
            failures.append((action_id, result.get('message', '未知错误')))
    return signed, failures


def _cmd_publish(args) -> int:
    """publish 子命令：生成注册表索引并打印发布步骤（不自动发布）。

    改前两处「假」：
    1. `--sign` 只打印「✏️  签名动作（待实现）...」，紧接着照样打印
       「✅ 注册表索引已生成」并 exit 0 —— 用户以为签名成功了；
    2. 帮助文案写「发布当前仓库到动作市场」，实现只生成索引 + 打印 4 步手工 git。
    现在 --sign 真正签名（复用 actus sign 的 trust_model 链路），任何签名失败
    都打到 stderr 且 exit 1，**不再输出任何"✅ 成功"字样**。
    """
    from vools.actus.registry import ActionRegistry

    repo_dir = os.getcwd()
    reg = ActionRegistry()

    # 构建索引：**只在内存构建，不落盘**（write=False）。
    # 改前这里直接 `build_from_directory(repo_dir)`，而该方法内部顺手把
    # .actus.registry.json 写盘 —— 于是 `--dry-run` 的「不实际发布」是假的：
    # 干跑照样创建/改写了仓库里的索引文件（实测删掉后跑 dry-run，文件又出现）。
    index = reg.build_from_directory(repo_dir, write=False)

    if args.dry_run:
        print('🔍 干跑模式（不实际发布）:')
        print(f'   动作数: {len(index.get("actions", []))}')
        for a in index.get('actions', []):
            print(f'   - {a.get("id", "?")} ({a.get("version", "?")})')
        return 0

    if args.sign:
        signed, failures = _publish_sign_actions(
            index, repo_dir, getattr(args, 'key', 'default'))
        if failures:
            for action_id, reason in failures:
                print(f'❌ 签名失败: {action_id}: {reason}', file=sys.stderr)
            print(f'❌ {len(failures)} 个动作签名失败（成功 {len(signed)} 个），未完成发布准备',
                  file=sys.stderr)
            if any('Private key not found' in reason for _a, reason in failures):
                print('   提示：先运行 `actus keygen --name %s` 生成签名密钥'
                      % getattr(args, 'key', 'default'), file=sys.stderr)
            # 失败路径：索引从来没落过盘，不会留下半成品文件
            return 1
        if signed:
            print(f'✍️  已签名 {len(signed)} 个动作:')
            for action_id, output in signed:
                try:
                    shown = os.path.relpath(output, repo_dir)
                except ValueError:
                    shown = output
                print(f'   - {action_id} → {shown}')
        else:
            print('ℹ️  仓库里没有可签名的动作')

    # 所有可能失败的步骤都过了，才真正落盘（失败不留半成品）
    registry_path = reg.write_index(index, repo_dir)
    print(f'✅ 注册表索引已生成: {registry_path}')
    print(f'   动作数: {len(index.get("actions", []))}')
    print()
    print('📋 发布步骤:')
    print('   1. git add .actus.registry.json')
    print('   2. git commit -m "update registry"')
    print('   3. git push origin main')
    print('   4. （可选）提交 PR 到官方市场')
    return 0


def _cmd_search(args) -> int:
    """search 子命令：搜索动作。"""
    from vools.actus.registry import ActionRegistry

    reg = ActionRegistry()

    if args.source == 'local':
        reg.load_from_repo(os.getcwd())
    elif args.source == 'installed':
        # 加载所有已安装仓库
        from vools.actus.installer import ActionInstaller
        installer = ActionInstaller()
        for manifest in installer.list_installed():
            local_path = manifest.get('local_path')
            if local_path and os.path.isdir(local_path):
                reg.load_from_repo(local_path)
    elif args.source == 'url' and args.url:
        # 尝试从缓存加载
        cached = reg.load_cached_index(args.url)
        if cached:
            for raw in cached.get('actions', []):
                pass  # 已缓存
        else:
            print(f'⚠️  远程搜索需要缓存索引，请先安装: actus install {args.url}')
            return 1

    tags = args.tag.split(',') if args.tag else None
    results = reg.search(
        query=args.query,
        category=args.category,
        author=args.author,
        tags=tags,
        limit=args.limit
    )

    if not results:
        print('🔍 未找到匹配的动作')
        return 0

    print(f'🔍 找到 {len(results)} 个动作:')
    for entry in results:
        print(f'   [{entry.trust_level:10s}] {entry.id} ({entry.version})')
        print(f'   {"":12s} {entry.description[:60]}')
        print(f'   {"":12s} 作者: {entry.author} | 分类: {entry.category} | 标签: {", ".join(entry.tags)}')
        print()
    return 0


def _cmd_sync(args) -> int:
    """sync 子命令：同步已安装的动作仓库。"""
    from vools.actus.installer import ActionInstaller

    installer = ActionInstaller()

    if args.force:
        # 强制重新安装
        manifests = installer.list_installed()
        for m in manifests:
            url = m.get('url')
            if url:
                installer.install(repo_url=url, branch=m.get('branch', 'main'))
        print('✅ 强制同步完成')
        return 0

    if args.url or args.name:
        result = installer.update(repo_url=args.url, name=args.name)
        if result.get('status') == 'ok':
            print(f'✅ 更新成功: {result.get("name")}')
            return 0
        else:
            print(f'❌ 更新失败: {result.get("message", "未知错误")}')
            return 1
    else:
        results = installer.sync_all()
        print(f'🔄 同步 {len(results)} 个仓库:')
        for r in results:
            status = r.get('result', {}).get('status', 'unknown')
            symbol = '✅' if status == 'ok' else '❌'
            print(f'   {symbol} {r.get("url", r.get("name", "?"))}')
        return 0


def _cmd_list_installed(args) -> int:
    """list-installed 子命令：列出已安装的仓库。"""
    from vools.actus.installer import ActionInstaller

    installer = ActionInstaller()
    manifests = installer.list_installed()

    if not manifests:
        print('📦 未安装任何动作仓库')
        print('   安装命令: actus install <url>')
        return 0

    print(f'📦 已安装 {len(manifests)} 个仓库:')
    for m in manifests:
        print(f'   📁 {m.get("cache_key", "?")}')
        print(f'      URL: {m.get("url", "?")}')
        print(f'      分支: {m.get("branch", "?")}')
        print(f'      路径: {m.get("local_path", "?")}')
        print(f'      动作数: {len(m.get("actions", []))}')
        print()
    return 0


def _cmd_rollback(args) -> int:
    """rollback 子命令：回滚已安装的仓库到指定版本。"""
    from vools.actus.installer import ActionInstaller

    installer = ActionInstaller()
    result = installer.rollback(repo_url=args.url, name=args.name, version=args.version)

    if result.get('status') == 'ok':
        print(f"✅ 回滚成功:")
        print(f"   提交: {result.get('commit')}")
        print(f"   消息: {result.get('message')}")
        return 0
    else:
        print(f"❌ 回滚失败: {result.get('message')}")
        return 1


def _cmd_check_update(args) -> int:
    """check-update 子命令：检查已安装仓库是否有可用更新。"""
    from vools.actus.installer import ActionInstaller

    installer = ActionInstaller()
    result = installer.check_update(repo_url=args.url, name=args.name)

    if result.get('status') == 'ok':
        if result.get('has_update'):
            print(f"🔄 有新版本可用:")
            print(f"   本地: {result.get('local_commit', '?')[:8]}")
            print(f"   远程: {result.get('remote_commit', '?')[:8]}")
            print(f"   更新命令: actus sync")
        else:
            print(f"✅ 已是最新版本")
            print(f"   提交: {result.get('local_commit', '?')[:8]}")
        return 0
    else:
        print(f"❌ 检查失败: {result.get('message')}")
        return 1


# ── 信任模型命令 ──

def _cmd_keygen(args) -> int:
    """keygen 子命令：生成签名密钥对。"""
    from vools.actus.trust_model import KeyManager

    km = KeyManager(keys_dir=args.output)
    priv_path, pub_path = km.generate_keypair(args.name)
    print(f'✅ 密钥对已生成:')
    print(f'   私钥: {priv_path}')
    print(f'   公钥: {pub_path}')
    return 0


def _cmd_sign(args) -> int:
    """sign 子命令：签名动作文件。"""
    from vools.actus.trust_model import SignatureVerifier

    verifier = SignatureVerifier()
    result = verifier.sign_file(args.path, key_name=args.key)

    if result.get('status') == 'ok':
        print(f'✅ 签名成功:')
        print(f'   文件: {args.path}')
        print(f'   签名: {result.get("output")}')
        print(f'   摘要: {result.get("signature")}')
        return 0
    else:
        print(f'❌ 签名失败: {result.get("message", "未知错误")}')
        return 1


def _cmd_verify(args) -> int:
    """verify 子命令：验证动作文件签名。"""
    from vools.actus.trust_model import SignatureVerifier

    verifier = SignatureVerifier()
    result = verifier.verify_file(args.path, key_name=args.key)

    if result.get('status') == 'ok':
        print(f'✅ 签名验证通过:')
        print(f'   文件: {args.path}')
        print(f'   签名者: {result.get("signer", "?")}')
        print(f'   算法: {result.get("algorithm", "?")}')
        return 0
    else:
        print(f'❌ 验证失败: {result.get("message", "未知错误")}')
        return 1


def _cmd_approve(args) -> int:
    """approve 子命令：审批或拒绝动作。"""
    from vools.actus.trust_model import ApprovalManager

    am = ApprovalManager()

    if args.reject:
        record = am.reject(args.action_id, reason=args.reason)
        if record:
            print(f'❌ 已拒绝: {args.action_id}')
            if args.reason:
                print(f'   原因: {args.reason}')
            return 0
        else:
            print(f'⚠️  未找到审批记录: {args.action_id}')
            return 1
    else:
        record = am.approve(args.action_id)
        if record:
            print(f'✅ 已批准: {args.action_id}')
            return 0
        else:
            print(f'⚠️  未找到审批记录（可能需要先安装动作）: {args.action_id}')
            return 1


def _cmd_pending(args) -> int:
    """pending 子命令：列出待审批的动作。"""
    from vools.actus.trust_model import ApprovalManager

    am = ApprovalManager()
    pending = am.list_pending()

    if not pending:
        print('📋 没有待审批的动作')
        return 0

    print(f'📋 待审批 {len(pending)} 个动作:')
    for p in pending:
        print(f'   ⏳ {p.get("action_id", "?")}')
        print(f'      来源: {p.get("source_url", "?")}')
        print(f'      权限: {", ".join(p.get("permissions", []))}')
        print()
    return 0


# ── 进化命令 ──

def _cmd_dialog(args) -> int:
    """dialog 子命令：调用 C# 弹窗。"""
    import json
    import os
    import subprocess
    import sys

    exe = os.path.join(os.path.dirname(__file__), '..', '..', 'actions', 'system', 'cs_forms', 'build', 'Dialogs', 'net8.0-windows', 'actus-dialogs.exe')
    if not os.path.exists(exe):
        print(f'❌ actus-dialogs.exe 未编译')
        print(f'   请先运行: cd actions/system/cs_forms && scripts/hot_reload.bat build')
        return 1

    req = {"mode": args.mode, "title": args.title}
    if args.message:
        req["message"] = args.message
    if args.options:
        req["options"] = [o.strip() for o in args.options.split(',')]
    if args.password:
        req["password"] = True
    if args.multiline:
        req["multiline"] = True
    if args.timeout:
        req["timeout"] = args.timeout
    if args.fields:
        try:
            req["fields"] = json.loads(args.fields)
        except json.JSONDecodeError as e:
            print(f'❌ fields JSON 解析失败: {e}')
            return 1

    try:
        r = subprocess.run([exe, json.dumps(req, ensure_ascii=False)], capture_output=True, text=True, timeout=(args.timeout or 120) + 30)
        if r.returncode != 0:
            print(f'❌ 弹窗进程退出码 {r.returncode}')
            if r.stderr:
                print(r.stderr)
            return 1
        result = json.loads(r.stdout.strip())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok') else 1
    except subprocess.TimeoutExpired:
        print('❌ 弹窗超时')
        return 1
    except json.JSONDecodeError:
        print(f'❌ 无法解析输出: {r.stdout[:200]}')
        return 1


def _cmd_evolve(args) -> int:
    """evolve 子命令：自进化循环。"""
    from vools.actus.evolution import EvolutionEngine, EvolutionConfig

    config = EvolutionConfig(max_rounds=args.max_rounds, auto_promote=False)
    engine = EvolutionEngine(config=config)

    # --list
    if args.list:
        actions = engine.list_evolved_actions()
        if not actions:
            print('🧬 没有进化记录')
            return 0
        print(f'🧬 {len(actions)} 个动作有进化历史:')
        for a in actions:
            print(f'   - {a}')
        return 0

    # --status
    if args.status:
        result = engine.get_status(args.status)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # --history
    if args.history:
        history = engine.get_history(args.history)
        if not history:
            print(f'📜 无进化历史: {args.history}')
            return 0
        print(f'📜 进化历史 ({len(history)} 条):')
        for h in history:
            print(f'   Round {h.get("round_num")}: {h.get("phase")} - {h.get("status")}')
            print(f'      {h.get("message", "")}')
        return 0

    # --rollback
    if args.rollback:
        if args.version is None:
            print('❌ 需要 --version 参数')
            return 1
        result = engine.rollback(args.rollback, args.version)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # --compare
    if args.compare:
        if args.v1 is None or args.v2 is None:
            print('❌ 需要 --v1 和 --v2 参数')
            return 1
        result = engine.compare_versions(args.compare, args.v1, args.v2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # --repair 模式
    if args.repair:
        if not args.action_id:
            print('❌ 需要 --action-id 参数')
            return 1
        expect = _parse_expect(args.expect) if args.expect else {}
        print(f'🔧 开始修复 {args.action_id}...')
        result = engine.repair(args.action_id, expect=expect)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 进化新模式（description 必需）
    if not args.description:
        print('❌ 需要自然语言描述（或 --repair/--status/--list 等子选项）')
        return 1

    expect = _parse_expect(args.expect) if args.expect else {}
    print(f'🧬 开始进化: {args.description[:60]}...')
    print(f'   最大轮次: {args.max_rounds}')
    print()

    result = engine.evolve(args.description, action_id=args.action_id, expect=expect)

    print(f'状态: {result.get("status")}')
    print(f'动作 ID: {result.get("action_id")}')
    print(f'轮次: {result.get("rounds")}')
    if result.get('path'):
        print(f'路径: {result["path"]}')
    if result.get('reason'):
        print(f'原因: {result["reason"]}')
    print()
    print('进化历史:')
    for h in result.get('history', []):
        symbol = '✅' if h.get('status') == 'pass' else '❌'
        print(f'   {symbol} Round {h.get("round_num")}: {h.get("phase")} - {h.get("status")}')
        if h.get('message'):
            print(f'      {h["message"][:80]}')

    return 0 if result.get('status') == 'ok' else 1


def _parse_expect(s: str) -> dict:
    """解析期望条件 JSON。"""
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


# ── Webhook 命令 ──

def _cmd_webhook(args) -> int:
    """webhook 子命令：Webhook 接收器管理。"""
    from vools.actus.webhook import WebhookReceiver, create_receiver

    # 使用全局接收器实例（简化状态管理）
    receiver = getattr(_cmd_webhook, '_receiver', None)

    # --stop
    if args.stop:
        if receiver and receiver.is_running:
            receiver.stop()
            _cmd_webhook._receiver = None
            print("⏹️  Webhook 接收器已停止")
        else:
            print("⚠️  没有运行中的 Webhook 接收器")
        return 0

    # --status
    if args.status:
        if receiver and receiver.is_running:
            status = receiver.get_status()
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print("⚠️  Webhook 接收器未运行")
        return 0

    # --logs
    if args.logs:
        if receiver:
            logs = receiver.get_logs(limit=args.logs)
            print(f"📋 最近 {len(logs)} 条请求日志:")
            for log in logs:
                ts = log.get('timestamp', 0)
                from datetime import datetime
                ts_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                print(f"   [{ts_str}] {log.get('client_ip')} "
                      f"{log.get('event_type')} -> {log.get('action_id', '(无路由)')}")
        else:
            print("⚠️  Webhook 接收器未运行")
        return 0

    # --register
    if args.register:
        event_type, action_id = args.register
        if not receiver or not receiver.is_running:
            print("⚠️  请先启动接收器: actus webhook")
            return 1
        receiver.register_route(event_type, action_id)
        print(f"✅ 路由注册: {event_type} -> {action_id}")
        return 0

    # --unregister
    if args.unregister:
        if not receiver or not receiver.is_running:
            print("⚠️  Webhook 接收器未运行")
            return 1
        removed = receiver.unregister_route(args.unregister)
        if removed:
            print(f"✅ 路由移除: {args.unregister} -> {removed}")
        else:
            print(f"⚠️  路由不存在: {args.unregister}")
        return 0

    # 默认启动（前台阻塞模式）
    secret = args.secret or os.environ.get('ACTUS_WEBHOOK_SECRET', '')
    require_signature = not args.no_signature

    receiver = create_receiver(
        host=args.host,
        port=args.port,
        secret=secret,
        require_signature=require_signature
    )
    _cmd_webhook._receiver = receiver
    print(f"🚀 启动 Webhook 接收器: http://{args.host}:{args.port}")
    receiver.start()  # 阻塞
    _cmd_webhook._receiver = None
    return 0


# ── Project 命令 ──

def _cmd_project(args) -> int:
    """project 子命令：多语言项目管理。"""
    from vools.actus.project import (
        ProjectOrchestrator, load_project, detect_modules,
        detect_languages, ModuleConfig
    )

    work_dir = args.work_dir or '.'
    project_file = args.project_file or '.actus-project.json'

    # --detect
    if args.detect:
        modules = detect_modules(work_dir)
        languages = detect_languages(work_dir)
        print(f"🔍 检测到 {len(modules)} 个模块:")
        for mid, mod in modules.items():
            print(f"   - {mid}: {mod.language} ({mod.path})")
        print(f"   语言: {', '.join(languages)}")
        return 0

    # --validate
    if args.validate:
        try:
            orch = load_project(project_file, work_dir)
            valid, errors = orch.validate()
            if valid:
                print("✅ 项目定义有效")
            else:
                print(f"❌ 项目定义无效 ({len(errors)} 个错误):")
                for e in errors:
                    print(f"   - {e}")
        except Exception as e:
            print(f"❌ 加载失败: {e}")
        return 0

    # --status
    if args.status:
        try:
            orch = load_project(project_file, work_dir)
            status = orch.get_status()
            print(json.dumps(status, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"❌ 加载失败: {e}")
        return 0

    # --add-module
    if args.add_module:
        mid, lang, path = args.add_module
        try:
            orch = load_project(project_file, work_dir)
            mod = ModuleConfig(id=mid, language=lang, path=path)
            orch.add_module(mod)
            orch.save_project(project_file)
            print(f"✅ 模块添加: {mid} ({lang})")
        except Exception as e:
            print(f"❌ 添加失败: {e}")
        return 0

    # --remove-module
    if args.remove_module:
        try:
            orch = load_project(project_file, work_dir)
            orch.remove_module(args.remove_module)
            orch.save_project(project_file)
            print(f"✅ 模块移除: {args.remove_module}")
        except Exception as e:
            print(f"❌ 移除失败: {e}")
        return 0

    # --test
    if args.test:
        try:
            orch = load_project(project_file, work_dir)
            print("🧪 执行测试...")
            result = orch.run_pipeline(phase='test')
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get('status') == 'ok' else 1
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return 1

    # --build (默认)
    try:
        orch = load_project(project_file, work_dir)
        phase = args.phase or 'build'
        print(f"🔨 开始 {phase} ...")
        result = orch.run_pipeline(phase=phase)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('status') == 'ok' else 1
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        return 1




# ── Omega 命令 ──

def _cmd_omega(args) -> int:
    """omega 子命令：Ω-gate 验证引擎。"""
    from vools.actus.omega import (
        verify_output, load_spec, generate_spec_template,
        learn_spec_from_history, batch_verify, format_report,
        generate_diff_report, run_gate, compute_output_fingerprint,
        _find_omega_spec, clear_spec_cache
    )
    # 审计修复：records.py 没有 load_records（导出名是 list_run_records），
    # 原写法让 `omega verify` 恒崩在 ImportError 上。
    from vools.actus.records import list_run_records

    # verify 子命令
    if args.omega_command == 'verify':
        # 解析输出
        output_str = args.output
        if os.path.isfile(output_str):
            with open(output_str, 'r', encoding='utf-8') as f:
                output = json.load(f)
        else:
            output = json.loads(output_str)

        # 查找 spec
        spec_path = args.spec
        if not spec_path:
            idx = {}
            try:
                from vools.actus.indexer import scan_actions
                idx = scan_actions()
            except Exception:
                pass
            actions_dir = idx.get('_actions_dir', 'actions')
            spec_path = _find_omega_spec(args.action_id, actions_dir)

        if not spec_path or not os.path.isfile(spec_path):
            print(f"❌ 未找到 spec 文件: {args.action_id}")
            return 1

        report = verify_output(spec_path, output, enable_loop=args.loop)
        print(format_report(report))

        if args.diff:
            spec = load_spec(spec_path)
            diff = generate_diff_report(spec, output)
            print(f"\n差异报告: {diff['status']}")
            if diff['missing_fields']:
                print(f"  缺失: {diff['missing_fields']}")
            if diff['extra_fields']:
                print(f"  多余: {diff['extra_fields']}")
            if diff['type_mismatches']:
                for mm in diff['type_mismatches']:
                    print(f"  类型不匹配: {mm['field']} (期望 {mm['expected']}, 实际 {mm['actual']})")

        return 0 if report.get('status') == 'pass' else 1

    # template 子命令
    elif args.omega_command == 'template':
        example = json.loads(args.example)
        spec = generate_spec_template(args.action_id, example)
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0

    # learn 子命令
    elif args.omega_command == 'learn':
        records = list_run_records(limit=args.limit)
        if args.action_id:
            records = [r for r in records if r.get('action_id') == args.action_id]
        spec = learn_spec_from_history(records)
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0

    # batch 子命令
    elif args.omega_command == 'batch':
        spec = load_spec(args.spec)
        with open(args.inputs, 'r', encoding='utf-8') as f:
            inputs = json.load(f)
        result = batch_verify(args.spec, inputs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('failed', 0) == 0 else 1

    # format 子命令
    elif args.omega_command == 'format':
        report = json.loads(args.report)
        print(format_report(report))
        return 0

    else:
        print("请指定子命令: verify / template / learn / batch / format")
        return 2


# ── Concurrency 命令 ──

def _cmd_concurrency(args) -> int:
    """concurrency 子命令：动作并发执行控制。"""
    from vools.actus.concurrency import get_manager, ConcurrencyManager

    mgr = get_manager()

    if args.concurrency_command == 'status':
        action_id = args.action if hasattr(args, 'action') else None
        status = mgr.get_status(action_id)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    elif args.concurrency_command == 'set':
        action_id = args.action
        max_inst = args.max
        mgr.register_action(action_id, max_inst)
        print(f"✅ 设置 {action_id} 并发上限: {max_inst}")
        return 0

    elif args.concurrency_command == 'reset':
        action_id = args.action if hasattr(args, 'action') else None
        if action_id:
            mgr.unregister_action(action_id)
            print(f"✅ 清除 {action_id} 并发状态")
        else:
            ConcurrencyManager.reset()
            print("✅ 清除所有并发状态")
        return 0

    elif args.concurrency_command == 'list':
        action_id = args.action if hasattr(args, 'action') else None
        if action_id:
            instances = mgr.get_running_instances(action_id)
            print(json.dumps({
                "action_id": action_id,
                "running": mgr.get_running_count(action_id),
                "waiting": mgr.get_waiting_count(action_id),
                "instances": instances,
            }, ensure_ascii=False, indent=2))
        else:
            status = mgr.get_status()
            print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    else:
        print("请指定子命令: status / set / reset / list")
        return 2


def _cmd_deps(args) -> int:
    """deps 子命令：检查动作依赖。"""
    from vools.actus.dependency import check_action_deps
    result = check_action_deps(args.action_id, auto_install=getattr(args, 'auto_install', False))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') else 1


def _cmd_dep_tree(args) -> int:
    """dep-tree 子命令：递归展示动作依赖树。"""
    from vools.actus.dependency import get_resolver
    resolver = get_resolver()
    tree = resolver.get_dep_tree(args.action_id)
    print(json.dumps(tree, ensure_ascii=False, indent=2))
    return 0


def _cmd_desktop(args) -> int:
    """desktop 子命令：启动 Actus Desktop Web UI。"""
    # 本模块迁移进 vools.actus 后（f060d16「独立成包」+ e03f24a「引擎根按包位置推导」），
    # start 位于 vools.actus.desktop 顶层；旧写法 `from desktop.app import start`
    # 既没有 top-level desktop 包、app 也只是 FastAPI 实例（非子模块）——
    # 实测 ImportError 恒为「No module named 'desktop'」，会走到下面的 except 打印
    # "pip install fastapi" 误导提示并 return 1，即使 fastapi/uvicorn 已装也起不来。
    # 改为正确的模块路径：ImportError 只在桌面依赖真缺席时触发，提示才名副其实。
    try:
        from vools.actus.desktop import start
    except ImportError as e:
        print(f'❌ 需要安装桌面依赖: pip install fastapi uvicorn jinja2（{e}）')
        return 1
    
    host = args.host
    port = args.port
    open_browser = not args.no_browser
    
    print(f'🚀 Actus Desktop 启动中...')
    print(f'   URL: http://{host}:{port}')
    print(f'   按 Ctrl+C 停止')
    
    start(host=host, port=port, open_browser=open_browser)
    return 0


def _cmd_events(args) -> int:
    """events 子命令：查看事件流。

    改前只读**进程内** EventBus 历史 —— CLI 每次都是新进程，内存历史必然为空，
    于是这个命令**结构上永远**打印「📭 暂无事件」并 rc=0：用户分不清「真的没有
    事件」和「历史根本不落盘」。

    现在读 `<meta_dir>/events.jsonl`（`eventbus.publish()` 追加落盘，best-effort）。
    语义区分：
      * 文件不存在 → 「从未有事件落盘」（事件流从未启用过 / 没跑过任何动作）
      * 文件存在但无事件 → 「事件流为空」
      * 有损坏行 → 明确报「N 行无法解析（已跳过）」，不静默吞
    本命令**纯读**：文件不存在不创建（`test_cli_no_side_effects` 要求零写入）。
    """
    from vools.actus import eventbus

    limit = getattr(args, 'limit', 50)
    if not isinstance(limit, int) or limit < 0:
        limit = 50

    snapshot = eventbus.read_persisted_events(limit=limit, event_type=args.type)
    events = snapshot['events']
    source = 'file'

    # 同进程内（测试/嵌入式调用）可能还有内存事件：文件没有时补上，
    # 保持 `_cmd_events` 在进程内的旧有用性（CLI 新进程时这里恒为空）。
    if not events:
        memory_events = eventbus.get_event_bus().get_history(
            event_type=args.type, limit=limit)
        if memory_events:
            events = memory_events
            source = 'memory'

    if getattr(args, 'as_json', False):
        _out({
            'status': 'ok',
            'source': source if events else 'none',
            'path': snapshot['path'],
            'history_exists': snapshot['exists'],
            'count': len(events),
            'total_in_file': snapshot['total'],
            'skipped_lines': snapshot['skipped'],
            # 这些计数是**本进程**的（读命令通常为 0），不是文件累计值 ——
            # 键名带 this_process 就是为了避免审计把它误读成事件流总量。
            'persist_this_process': eventbus.get_event_bus().persistence_stats(),
            'events': events,
        })
        return 0

    if not events:
        if not snapshot['exists']:
            print(f'📭 从未有事件落盘（事件流文件不存在: {snapshot["path"]}）')
            print('   事件总线是内存实现，publish() 时才会追加到该文件；'
                  '跑一个动作或 emit() 一条事件后再来看。')
        else:
            print(f'📭 事件流为空（文件存在但没有事件: {snapshot["path"]}）')
        if snapshot['skipped']:
            print(f'   ⚠️  另有 {snapshot["skipped"]} 行无法解析（已跳过）')
        return 0

    suffix = '，来源: 内存' if source == 'memory' else ''
    print(f'📋 事件流 (共 {len(events)} 条{suffix}):')
    for event in events:
        timestamp = event.get('timestamp', 0)
        try:
            shown_ts = '%.3f' % float(timestamp)
        except (TypeError, ValueError):
            shown_ts = str(timestamp)
        type_ = event.get('type', '?')
        source_name = event.get('source', '')
        data = event.get('data', {})
        print(f'   [{shown_ts}] {type_} (来源: {source_name})')
        if isinstance(data, dict) and data:
            for key, value in data.items():
                print(f'      {key}: {value}')
    if snapshot['skipped']:
        print(f'   ⚠️  另有 {snapshot["skipped"]} 行无法解析（已跳过）')
    return 0


# viz 的内置示例工作流。只允许由显式 --sample 触发 —— 改前它被当成
# 「没有工作流定义」时的默认输出（exit 0），用户/AI 会误以为是本项目的工作流。
_VIZ_SAMPLE_WORKFLOW = {
    "nodes": [
        {"id": "trigger", "label": "触发器", "type": "trigger"},
        {"id": "action1", "label": "动作 A"},
        {"id": "action2", "label": "动作 B"},
        {"id": "end", "label": "完成"},
    ],
    "edges": [
        ("trigger", "action1"),
        ("trigger", "action2"),
        ("action1", "end"),
        ("action2", "end"),
    ],
}


def _cmd_viz(args) -> int:
    """viz 子命令：工作流可视化。

    改前「找不到 .actus.workflow.json」时会把一段**硬编码示例**
    （trigger/action1/action2/end）当结果输出并 exit 0，加 --output 还会把它
    落盘成文件 —— 用户和 AI 调用方会把它当成「本项目的工作流」写进报告，
    属于闭环假数据。现在：找不到定义就明确报错 exit 1；示例只由显式
    `--sample` 触发，且 stderr 标注「这是示例」。
    """
    from vools.actus.viz import visualize_workflow, visualize_action_workflow
    from vools.actus.indexer import _repo_root
    from vools.actus.model import parse_cfg_from_file
    import os

    root = _repo_root()

    if args.action:
        # 可视化指定动作的工作流。
        # 审计修复：改前按「文件名 == <action> + '.actus.md'」猜路径 —— 本仓库
        # 动作文件是 foo.actus.md、id 是 actus.test.foo，于是 `viz --action
        # actus.test.foo` 永远「动作不存在」。改为用索引 + resolver 的单一查找
        # 实现（find_action_file 按解析后的 meta['id'] 比对，与文件名无关）：
        #   1) 索引按 id 直取 path；2) 按 name 反查 id 再取；3) 兜底走
        #   find_action_file 在两个动作根里扫。
        from vools.actus.resolver import find_action_file
        from vools.actus.indexer import load_index

        action_roots = [os.path.join(root, "actions")]
        try:
            from vools.actus import __file__ as _pkg_file
            pkg_actions = os.path.join(os.path.dirname(os.path.abspath(_pkg_file)), "actions")
            if os.path.isdir(pkg_actions) and pkg_actions not in action_roots:
                action_roots.append(pkg_actions)
        except Exception:
            pass

        index = load_index()
        actions_index = index.get("actions") or {}
        action_id = args.action
        action_path = None

        entry = actions_index.get(action_id) or {}
        indexed_path = entry.get("path")
        if indexed_path:
            candidate = indexed_path if os.path.isabs(indexed_path) \
                else os.path.join(root, indexed_path)
            if os.path.exists(candidate):
                action_path = candidate
        if action_path is None and action_id not in actions_index:
            # 允许传可读 name（子命令帮助里写的是「指定动作 ID」，name 是便利增强）
            for aid in (index.get("by_name") or {}).get(action_id) or []:
                action_id = aid
                break
        if action_path is None:
            for actions_root in action_roots:
                action_path = find_action_file(action_id, actions_root)
                if action_path:
                    break
        if not action_path:
            print(f'❌ 动作不存在: {args.action}')
            return 1
        # 审计修复：`Action` 没有 from_file()（真源是 model.parse_cfg_from_file），
        # 原写法让 `actus viz --action <存在文件>` 恒崩 AttributeError。
        action = parse_cfg_from_file(action_path)
        result = visualize_action_workflow(action.meta, args.format)
    else:
        # 可视化项目级工作流（如果有）
        wf_path = os.path.join(root, ".actus.workflow.json")
        if os.path.exists(wf_path):
            import json
            with open(wf_path, encoding="utf-8") as f:
                wf = json.load(f)
            result = visualize_workflow(wf, args.format)
        elif getattr(args, 'sample', False):
            print('ℹ️  注意：以下是 --sample 的内置**示例**工作流，'
                  '不是你项目的工作流', file=sys.stderr)
            result = visualize_workflow(_VIZ_SAMPLE_WORKFLOW, args.format)
        else:
            print(f'❌ 未找到工作流定义: {wf_path}', file=sys.stderr)
            print('   想看示例请加 --sample；想可视化单个动作请用 --action <id>',
                  file=sys.stderr)
            return 1

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(result, encoding="utf-8")
        print(f'✅ 已保存到: {args.output}')
    else:
        print(result)
    return 0


def _replay_action_id(record: dict) -> str:
    """取记录里的动作 id（历史记录两种写法都有：action_id 与旧格式 action）。"""
    for key in ('action_id', 'action'):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _replay_record_matches(record: dict, wanted: str) -> bool:
    """--run-id 匹配：run_id / id / exec_id 任一命中即可。

    改前是 `r.get('run_id') == r.get('id') == args.run_id` —— Python 的链式比较
    等价于 `run_id == id and id == wanted`，而历史记录里 run_id 与 id 是
    **二选一**出现的两个键（build/audit/tmp_meta/runs/history.json 实测：一条只有
    run_id=run-A1，另一条只有 id=run-B2），两者永不相等 ⇒ 任何 --run-id 都匹配不上。
    执行器自己写的记录用的又是 exec_id，所以三个键都要认。
    """
    return any(record.get(key) == wanted
               for key in ('run_id', 'id', 'exec_id'))


def _parse_replay_params(raw):
    """把记录里的 params 归一成 (dict, error)。

    历史记录的 params 形态并不统一：可能是 dict、JSON 字符串，也可能是
    Python repr（`"{'message': 'hello'}"`，单引号 —— build/audit/tmp_meta 实测）。
    解析失败返回可读原因，由调用方跳过并计入失败清单，绝不静默当空参重放。
    """
    import ast
    import json

    if raw is None:
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if not isinstance(raw, str):
        return {}, f'params 类型不支持（{type(raw).__name__}）'
    text = raw.strip()
    if not text:
        return {}, None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return {}, f'无法解析为 JSON 或 Python 字面量: {text[:60]!r}'
    if not isinstance(parsed, dict):
        return {}, f'params 解析结果不是对象（{type(parsed).__name__}）'
    return parsed, None


def _cmd_replay(args) -> int:
    """replay 子命令：重放历史执行。

    改前是假功能（本轮修复）：
    1. 非 --dry-run 分支固定打印「(重放执行待实现)」，**从不执行**；
    2. `run_id == id == args.run_id` 是链式比较 bug，--run-id 恒匹配不上。

    现在非 dry-run 真正调用现有执行入口 `vools.actus.execute(...)`（与
    `actus exec` 同一条路径，不另造执行器），单条失败不中断整批，
    结尾汇总「成功 N / 失败 M」，有失败时退出码 1。
    """
    from vools.actus.export import load_run_history, RunHistoryCorruptError
    from vools.actus.indexer import _repo_root
    import os

    root = _repo_root()
    meta_dir = os.environ.get('ACTUS_META_DIR') or os.path.join(root, '_meta')
    try:
        records = load_run_history(meta_dir)
    except RunHistoryCorruptError as exc:
        print(f'❌ 历史文件损坏: {exc}', file=sys.stderr)
        return 1

    if not records:
        print('📭 暂无执行历史')
        return 0

    if args.run_id:
        records = [r for r in records if _replay_record_matches(r, args.run_id)]
        if not records:
            print(f'❌ 未找到执行记录: {args.run_id}')
            return 1

    limit = getattr(args, 'limit', None)
    if limit is None or limit < 0:
        limit = 10
    if limit and len(records) > limit:
        print(f'ℹ️  历史共 {len(records)} 条，本次只处理最近 {limit} 条'
              f'（--limit 0 可全部处理）')
        records = records[:limit]

    print(f'🔁 重放 {len(records)} 条执行记录:')
    succeeded = 0
    failures = []          # [(记录标识, 原因)]

    for r in records:
        ts = r.get('timestamp', '')
        action = _replay_action_id(r)
        status = r.get('status', '')
        raw_params = r.get('params', {})
        label = r.get('run_id') or r.get('id') or r.get('exec_id') or ts or '<无标识>'
        print(f'   [{ts}] {action or "<缺少 action_id>"} ({status})')
        if raw_params:
            print(f'      参数: {raw_params}')

        if args.dry_run:
            print(f'      (dry-run，跳过)')
            continue

        # ── 预检：无法重放的记录给出可读理由后跳过（不中断整批）──
        if not action:
            reason = '记录缺少 action_id/action 字段，无法确定要重放哪个动作'
            failures.append((label, reason))
            print(f'      ⏭️  跳过: {reason}')
            continue

        params, param_error = _parse_replay_params(raw_params)
        if param_error:
            failures.append((label, f'params 解析失败: {param_error}'))
            print(f'      ⏭️  跳过: params 解析失败 —— {param_error}')
            continue

        # ── 真正执行：复用 vools.actus.execute（与 exec 子命令同一入口）──
        try:
            import vools.actus as actuscore
            result = actuscore.execute(action, params, meta_dir=meta_dir)
        except Exception as exc:          # 执行入口自身抛异常也不许中断整批
            reason = f'{type(exc).__name__}: {exc}'
            failures.append((label, reason))
            print(f'      ❌ 重放失败: {reason}')
            continue

        if isinstance(result, dict) and result.get('status') == 'ok':
            succeeded += 1
            data = result.get('data') if isinstance(result.get('data'), dict) else {}
            exec_ref = result.get('exec_id') or data.get('exec_id') or ''
            # 把动作真实产出的回显打出来 —— 这是「真的执行了」的证据，
            # exec_id 由执行器盖章，不是这里编的。
            output = data.get('result', data.get('output'))
            detail = f'exec: {exec_ref}' if exec_ref else 'ok'
            if output not in (None, ''):
                detail += f'，输出: {str(output)[:100]}'
            print(f'      ✅ 重放成功 ({detail})')
        else:
            error = (result or {}).get('error') or {}
            code = error.get('code') or (result or {}).get('status') or 'error'
            message = error.get('message') or '执行未成功'
            failures.append((label, f'{code}: {message}'))
            print(f'      ❌ 重放失败: {message}')

    if args.dry_run:
        return 0

    print()
    print(f'📊 重放结果: 成功 {succeeded} / 失败 {len(failures)}')
    for label, reason in failures:
        print(f'   ❌ [{label}] {reason}')
    return 0 if not failures else 1


def _cmd_notify(args) -> int:
    """notify 子命令：通知系统管理。"""
    from vools.actus.notify import get_notification_manager, NotifyLevel
    manager = get_notification_manager()

    if args.action == 'test':
        manager.notify(
            title="Actus 测试通知",
            body="这是一条测试通知",
            level=NotifyLevel.INFO,
        )
        print('✅ 已发送测试通知')
        return 0

    elif args.action == 'history':
        history = manager.get_history()
        if not history:
            print('📭 暂无通知历史')
            return 0
        print(f'📋 通知历史 (共 {len(history)} 条):')
        for h in history:
            level = h.get('level', 'info')
            title = h.get('title', '')
            body = h.get('body', '')
            ts = h.get('timestamp', '')
            print(f'   [{ts}] ({level}) {title}: {body}')
        return 0

    elif args.action == 'stats':
        stats = manager.stats()
        print('📊 通知系统统计:')
        print(f'   总发送: {stats["total_sent"]}')
        print(f'   规则数: {stats["rules_count"]}')
        print(f'   渠道: {", ".join(stats["channels"])}')
        return 0

    return 0


def _cmd_project_io(args) -> int:
    """project 子命令：项目导入导出。"""
    from vools.actus.project_io import export_project, import_project, validate_project
    from vools.actus.indexer import _repo_root

    root = _repo_root()

    if args.action == 'export':
        output = args.output or f"{root.name}.actus"
        result = export_project(root, output, include_meta=args.meta)
        if result:
            print(f'✅ 项目已导出: {result}')
            return 0
        print('❌ 导出失败')
        return 1

    elif args.action == 'import':
        if not args.file:
            print('❌ 缺少 --file 参数')
            return 1
        stats = import_project(root, args.file)
        if stats:
            print(f'✅ 导入完成: {stats["imported"]} 个文件')
            return 0
        print('❌ 导入失败')
        return 1

    elif args.action == 'validate':
        if not args.file:
            print('❌ 缺少 --file 参数')
            return 1
        result = validate_project(args.file)
        if result['valid']:
            print(f'✅ 项目有效 ({result["manifest"].get("actions_count", 0)} 个动作)')
        else:
            print('❌ 项目无效:')
            for e in result['errors']:
                print(f'   - {e}')
        return 0 if result['valid'] else 1

    return 0


def _cmd_export(args) -> int:
    """export 子命令：导出动作执行历史。

    改前 `result is None and args.output` 直接打印「✅ 已导出到: <path>」并 exit 0，
    但 result 为 None 恰恰意味着 **export_history 根本没写文件**（没有历史记录）。
    实测文件不存在却报成功，脚本/CI 拿 exit 0 当成功，随后 FileNotFoundError。
    现在：
      * 写了文件 → export_history 返回写入路径，再核对文件确实存在才报 ✅；
      * 无历史 + --output → stderr 报「未生成文件」并 exit 1；
      * 历史文件损坏 → 报「历史文件损坏: <path>」并 exit 1（不再伪装成「暂无」）。
    """
    from vools.actus.export import export_history, RunHistoryCorruptError
    from vools.actus.indexer import _repo_root
    import os

    meta_dir = os.environ.get('ACTUS_META_DIR') or os.path.join(_repo_root(), '_meta')
    try:
        result = export_history(meta_dir, args.output, args.format, args.limit)
    except RunHistoryCorruptError as exc:
        print(f'❌ 历史文件损坏: {exc}', file=sys.stderr)
        return 1

    if args.output:
        if isinstance(result, str) and result and os.path.exists(result):
            print(f'✅ 已导出到: {result}')
            return 0
        print(f'❌ 没有可导出的执行历史，未生成文件: {args.output}', file=sys.stderr)
        return 1

    if result:
        print(result)
        return 0
    print('📭 暂无执行历史')
    return 0


def _cmd_probe(args) -> int:
    """probe 子命令：一键探测本机环境，输出 ProbeReport（PROBE_PLAN.md §9 Phase 3）。

    人类可读模式走 format_summary；--json 输出完整结构化报告（机器消费）。
    缓存控制：--force-refresh 强制全量重探测；--max-age 自定义缓存有效期。
    """
    from vools.actus.probe import probe, format_summary

    report = probe(force_refresh=args.force_refresh,
                   max_age=args.max_age, verbose=args.verbose)
    if args.as_json:
        _out(report.to_dict())
    else:
        print(format_summary(report))
    return 0


def _cmd_health(args) -> int:
    """health 子命令：系统健康检查。"""
    from vools.actus.health import run_health_check, HealthChecker
    import json as _json

    if args.check:
        # 只运行指定检查项
        checker = HealthChecker()
        for name, func in checker._checks:
            if args.check.lower() in name.lower():
                result = func()
                result.name = name
                if args.json:
                    _json.dump({"name": result.name, "status": result.status,
                                "message": result.message, "suggestion": result.suggestion},
                               sys.stdout, ensure_ascii=False, indent=2)
                else:
                    icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}.get(result.status, "❓")
                    print(f"{icon} [{result.status.upper()}] {result.name}: {result.message}")
                    if result.suggestion:
                        print(f"   建议: {result.suggestion}")
                return 0
        print(f"未找到检查项: {args.check}")
        return 1

    report = run_health_check()

    if args.json:
        _json.dump({
            "overall": report.overall,
            "total_duration": report.total_duration,
            "summary": report.status_counts,
            "results": [{"name": r.name, "status": r.status, "message": r.message,
                         "suggestion": r.suggestion, "duration": r.duration}
                        for r in report.results],
        }, sys.stdout, ensure_ascii=False, indent=2)
    else:
        # 审计修复：HealthReport 没有 report_text()（只有 summary()/results），
        # 原写法让人类可读的 `actus health` 恒崩 AttributeError（--json 正常）。
        print(report.summary())
        for r in report.results:
            print(f"  [{r.status.upper()}] {r.name}: {r.message}"
                  + (f"  建议: {r.suggestion}" if r.suggestion else ""))

    return 0 if report.overall == "ok" else 1


def _cmd_selfheal(args) -> int:
    """selfheal 子命令：查看/重置自愈引擎状态。"""
    from vools.actus.selfheal import get_self_healing_engine
    engine = get_self_healing_engine()

    if args.action == 'status':
        stats = engine.stats()
        print('⚡ 自愈引擎状态:')
        print(f'   总执行: {stats["total"]}')
        print(f'   成功: {stats["success"]}')
        print(f'   失败: {stats["failed"]}')
        print(f'   重试: {stats["retried"]}')
        print(f'   熔断拒绝: {stats["rejected"]}')
        print(f'   断路器数: {stats["active_breakers"]}')
        print(f'   错误模式: {stats["learner"]["total_patterns"]}')
        return 0

    elif args.action == 'reset':
        engine.reset()
        print('🔄 自愈引擎已重置')
        return 0

    elif args.action == 'patterns':
        patterns = engine.learner.get_top_patterns(20)
        if not patterns:
            print('📭 暂无错误模式')
            return 0
        print('📊 错误模式:')
        for p in patterns:
            print(f'   [{p["count"]}次] {p["code"]}: {p["message"]}')
            if p.get('resolution'):
                print(f'      修复建议: {p["resolution"]}')
        return 0

    return 0


def _cmd_template(args) -> int:
    """template 子命令：管理动作模板。"""
    from vools.actus.template import list_templates, apply_template, create_action_from_template

    if args.action == 'list':
        templates = list_templates()
        print(f'📋 可用模板 ({len(templates)} 个):')
        for t in templates:
            print(f'   {t["id"]}: {t["name"]}')
            print(f'      {t["description"]}')
            print(f'      标签: {", ".join(t["tags"])}')
        return 0

    elif args.action == 'apply':
        if not args.id:
            print('❌ 缺少 --id 参数（模板 ID）')
            return 1
        if not args.action_id:
            print('❌ 缺少 --action-id 参数（目标动作 ID）')
            return 1

        name = args.name or args.action_id.split('.')[-1]
        output_dir = args.output or 'actions/custom'

        path = create_action_from_template(args.id, args.action_id, name, output_dir)
        if path:
            print(f'✅ 动作已创建: {path}')
            return 0
        else:
            print(f'❌ 模板应用失败')
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
