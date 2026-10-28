"""统一错误类型：所有失败都收敛为 ActionError，携带 docs/08 §5 的结构化错误码。"""

__all__ = ['ActionError', 'ERROR_CODES',
           'OPERATION_OK_STATUSES', 'is_failure_status']

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

