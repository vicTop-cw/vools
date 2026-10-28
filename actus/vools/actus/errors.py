"""统一错误类型：所有失败都收敛为 ActionError，携带 docs/08 §5 的结构化错误码。"""

__all__ = ['ActionError', 'ERROR_CODES',
           'OPERATION_OK_STATUSES', 'is_failure_status',
           'check_path_target', 'ensure_within']

# ── 业务结果状态 → 成败（CLI 与 MCP 共用同一份判据）──
# 为什么放这里：`cli._out_result` 与 `mcp_server.text_result` 都要判"这次操作
# 算不算失败"，各写一份必然漂移（实测 MCP 只认 'failed'，于是 author 的
# needs_fix、workflow 的 partial 在 MCP 侧全被当成成功）。errors.py 无重依赖，
# 是两者的共同祖先，适合放共用判据。
OPERATION_OK_STATUSES = (
    'ok', 'success', 'modified', 'skipped', 'noop', 'published',
)


def is_failure_status(status) -> bool:
    """业务结果的状态是否代表**失败**（CLI / MCP 共用）。

    判据：
      * 空 / None → **不算失败**：纯数据结果（如查询返回的记录体）没有成败声明；
      * 命中 `OPERATION_OK_STATUSES` → 不算失败；
      * 其余**任何值（含未知值）→ 失败**。

    最后一条是"假 ok"审计的产物：未知状态宁可让调用方看到错误，也不要假装成功。
    注意语义：这些都不是"错误码"，而是**操作结果的状态**（`needs_fix` 表示
    AI 改了但校验没过、`partial` 表示工作流部分节点失败、`awaiting_confirmation`
    表示动作还没真正执行 —— 三者对调用方都不是"做完了"）。

    Example:
        >>> is_failure_status('ok'), is_failure_status('needs_fix')
        (False, True)
        >>> is_failure_status(None), is_failure_status('whatever')
        (False, True)
    """
    text = str(status or '').strip().lower()
    if not text:
        return False
    return text not in OPERATION_OK_STATUSES


# docs/08 §5 结构化错误码
ERROR_CODES = [
    'action_not_found', 'action_invalid', 'param_invalid',
    'dependency_missing', 'dependency_cycle', 'trust_rejected',
    'permission_denied', 'confirmation_timeout', 'timeout',
    'language_unavailable', 'visibility_denied', 'auth_required',
    'internal',
    # 09-28 给 executor 补的"入口块一个字节都没打 ⇒ 不许记 ok"这条行为发的是
    # entry_no_output，名单当时没同步 ⇒ 按这份名单分派的调用方会漏掉它。
    # （docs/38 §1；executor.py 属禁改区，这里只补登记，不动行为。）
    'entry_no_output',
    # 2026-10 执行路径审计：块失败（用户代码抛异常/非零退出/超时）从 `internal`
    # 分流出来 —— `internal` 只表示**引擎自身**异常，调用方靠此区分"我的代码错"
    # 还是"引擎错"（executor._run_blocks 的失败分支发这个码）。
    'block_failed',
    # 覆盖保护：目标已存在且调用方没有显式 force。scaffold 一直在用这个码，
    # 本轮把它登记进来（此前只在代码里出现、名单里没有）。
    'action_exists',
]

class ActionError(Exception):
    """携带结构化错误码的统一异常。

    message: 人类可读说明（中文）
    code:    docs/08 §5 错误码
    details: 附加结构化信息（字段错误、环路径等）
    """

    def __init__(self, code: str, message: str, details=None) -> None:
        """构造 ActionError。

        code:    docs/08 §5 结构化错误码
        message: 人类可读说明（中文）
        details: 附加结构化信息（字段错误、环路径等）
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details if details is not None else {}

    def to_payload(self) -> dict:
        """转为 docs/03 §7.2 的 error 载荷。"""
        return {'code': self.code, 'message': self.message, 'details': self.details}


# ── 跨模块共用的两条「写之前先判」规则 ──
# 为什么放这里：这两条判断此前在 scaffold / installer / publisher / template /
# project / importsys / bugreport 里各写了一份（或干脆漏写）。errors.py 无重依赖，
# 是这些模块的共同祖先，适合放共用判断。

def check_path_target(path: str, force: bool = False, what: str = '目标',
                      code: str = 'action_exists') -> str:
    """写入前检查目标：已存在且未显式 force → 抛 ActionError(code)；否则原样返回 path。

    共用范围（本轮）：
      * `scaffold.scaffold_action()` —— 与这里等价（它原本就是这套语义）；
      * `template.create_action_from_template()` —— 本轮改为调用本函数（此前**没有**保护）。
    `installer` / `publisher` 的覆盖判定暂时**没有**合并：它们还带「内容相同则幂等
    no-op」的语义（installer 还带用户配置快照/还原），语义比"存在即拒绝"宽；
    将来要统一，应当给本函数加 `idempotent_if_same=` 之类的参数，而不是各写一份。
    """
    import os
    if force or not os.path.exists(path):
        return path
    raise ActionError(
        code,
        '%s已存在，拒绝覆盖: %s（如需覆盖请用 force=True / CLI 的 --force）'
        % (what, path),
        {'path': path})


def ensure_within(base: str, candidate: str, what: str = '路径',
                  error_cls=ValueError) -> str:
    """`candidate` 解析后必须**严格落在** `base` 之内；越界抛 `error_cls`。

    返回 `realpath(candidate)`。与 `installer._inside_install_dir` 是同一把尺子
    （realpath 之后再比，顺带挡住软链/junction 指向外面）；抽到公共模块是因为
    `project.load/save_project`、`importsys` 的 `#!import` 路径、`bugreport._check_source`
    都需要同一个判断 —— 此前各自手写（或干脆没有）。

    `error_cls` 让调用方保持自己的异常约定（如 bugreport 传 `BugreportError`）。
    """
    import os
    try:
        root = os.path.realpath(base)
        real = os.path.realpath(candidate)
    except (OSError, ValueError) as exc:
        raise error_cls('%s无法解析: %r（%s）' % (what, candidate, exc))
    if real.startswith(root + os.sep):
        return real
    raise error_cls('%s会越出允许目录，已拒绝: %r（基准 %r）'
                    % (what, candidate, base))

