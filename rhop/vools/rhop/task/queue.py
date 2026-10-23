"""vools.rhop.task.queue - 通用任务队列主流程（提交 / DAG / 领取 / 执行 / 回写）

对齐 ``vools.pyk.look_upon`` 的表结构与流转，但去掉 P0..P3 跳板角色：

* **A 侧**：``submit()`` 把任务（含依赖）写进队列，载荷以加密 JSON 落库
  （"A 给 B 传的加密 JSON"）；``status()`` 直接看同一份状态。
* **B 侧**：``run_once()`` / ``run_resident()`` 领取 → 解密 → 白名单派发执行 →
  回写结果（可加密）→ 失败按 ``max_retries`` 进 RETRY_PENDING，超限落 FAILED。
* **依赖**：``deps`` 用 task_name 列表表达，只有全部 COMPLETED 才可领取；
  ``submit`` 时做 DAG 校验（依赖缺失 / 成环直接抛 DagValidationError）。
* **落点无关**：全程只通过 TaskStore 抽象读写，因此共享单一库 / 双方各自持库
  （配 TaskSync）/ 将来 PostgreSQL 都走同一份流程代码。
"""

from __future__ import absolute_import

import hashlib
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .config import TaskConfig
from .errors import DagValidationError, ExecDenied, PayloadError, RhopTaskError, SecretError
from .exec import ExecPolicy, HANDLERS, run_payload
from .models import (
    DEFINITION_FIELDS,
    TaskRecord,
    TaskState,
    iso_add_seconds,
    utcnow_iso,
)
from .store import create_store

log = logging.getLogger("vools.rhop.task.queue")

#: 任务 dict 里可直接内联的「指令」键（等价于 payload 子 dict）
INSTRUCTION_KEYS = ("action", "cli", "handler", "args", "payload")

#: 非重试型失败（确定性错误，重试没意义）
_NON_RETRYABLE_PREFIX = ("载荷", "执行被白名单拒绝", "无法识别指令", "指令", "workdir", "处理器")

#: 结果文件命名规则（``_maybe_offload_result`` / ``_write_file_ref`` 写出）：
#: ``<UTC时间戳>-<内容sha前8位>.json``。``cleanup_result_files`` 只认这个模式，
#: 避免误删同目录里的其它文件（BUG-296 收口）。结果与载荷共用同一命名规则。
RESULT_FILE_RE = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{8}\.json$")

#: 载荷落文件的引用信封标记（payload_enc 里用它区分「加密载荷」与「引用信封」）
PAYLOAD_FILE_KIND = "rhop-payload-file"


def _canonical_json(data: Any) -> str:
    """稳定 JSON 文本（sha256 幂等/完整性校验用，两侧一致）。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _first_present(sources: Any, key: str, cast: Any, fallback: Any) -> Any:
    """按顺序取第一个「显式给出且非 None」的值，再转换类型。

    必须这样写而不是 ``a or b or c``：``max_retries=0`` / ``retry_delay_min=0``
    是合法且常用的取值（不重试 / 立即重试），用 ``or`` 会把 0 吃掉换成兜底值。
    """
    for source in sources:
        if isinstance(source, dict) and key in source and source[key] is not None:
            try:
                return cast(source[key])
            except (TypeError, ValueError):
                continue
    return fallback


def _shrink_result_to_bytes(data: Any, budget: int) -> str:
    """把结果压到 ``budget`` 字节以内（BUG-283 收口：真正的硬上限）。

    两步降级，保证最终落库文本不超预算：
    1. 字段级裁剪：结果里的 ``stdout`` / ``stderr`` 各裁到 2000 字符，其它结构保留；
    2. 仍超预算 ⇒ 退化为**紧凑摘要**：只留结构类型、字符数、开头片段与提示，正文不再整条入库。

    Args:
        data:   要编码的结果（dict 或任意值）
        budget: 目标字节上限

    Returns:
        str: 落库用的 JSON 文本（长度 ≤ budget，除非预算小到连最小摘要都放不下）
    """
    node = dict(data) if isinstance(data, dict) else {"result": data}
    node["truncated"] = True
    node["truncate_hint"] = (
        "结果超过 result_max_bytes，已截断；大结果请写文件并用 payload 里的引用路径回传。")
    inner = node.get("result")
    if isinstance(inner, dict):
        inner = dict(inner)
        for key in ("stdout", "stderr"):
            value = inner.get(key)
            if isinstance(value, str) and len(value) > 2000:
                inner[key] = value[:2000] + "\n...[截断]"
        node["result"] = inner

    text = _canonical_json(node)
    if len(text.encode("utf-8")) <= budget:
        return text

    head = str(node.get("result") if isinstance(node, dict) else node)
    summary = {
        "truncated": True,
        "truncate_hint": node.get("truncate_hint"),
        "result_kind": type(node.get("result")).__name__,
        "result_chars": len(head),
        "result_head": head[: max(0, budget - 200)],
    }
    while True:
        text = _canonical_json(summary)
        if len(text.encode("utf-8")) <= budget:
            return text
        if not summary.get("result_head"):
            return text          # 已是能表达的最小形态
        summary["result_head"] = summary["result_head"][: len(summary["result_head"]) // 2]


def payload_sha(payload: Any) -> str:
    """明文载荷的 sha256（写入 payload_sha，B 解密后可比对）。"""
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class TaskQueue(object):
    """任务队列（A/B 共用同一个类，行为由配置里的方向决定）。"""

    def __init__(self, config: TaskConfig, store: Optional[Any] = None,
                 crypto: Optional[Any] = None, heartbeat: Optional[Any] = None,
                 handlers: Optional[Dict[str, Callable]] = None,
                 syncer: Optional[Any] = None, logger: Optional[Any] = None):
        self.config = config
        self._owns_store = store is None
        self.store = store if store is not None else config.build_store()
        self.crypto = crypto if crypto is not None else config.build_crypto()
        self.heartbeat = heartbeat if heartbeat is not None else config.build_heartbeat()
        self.handlers = dict(handlers if handlers is not None else HANDLERS)
        self.syncer = syncer
        self.policy = ExecPolicy.from_cfg(self.config.exec)
        self.log = logger or log
        self._stop_requested = False

    # ------------------------------------------------------------------
    # 加密 / 结果编解码
    # ------------------------------------------------------------------

    def _require_crypto(self, what: str):
        if self.crypto is None:
            raise RhopTaskError(
                "%s 需要密钥：请在配置里提供 key（明文 / key.env / key.cipher）。" % what)
        return self.crypto

    def encrypt_payload(self, payload: Any) -> Dict[str, Any]:
        """把明文载荷加密成可入库的 (payload_enc, payload_sha)。

        **大载荷载荷侧落文件**（advance 轮新增，默认关闭）：``file_channel.payload_max_bytes > 0``
        且载荷超过阈值时，把**已加密的载荷**写进结果文件目录，``payload_enc`` 只存引用信封
        ``{"kind": "rhop-payload-file", "file_ref": {...}}``——这样 A 侧的大指令不会整条进队列与
        同步文档；B 端解密时按引用读回并校验完整性。文件里存的是密文，共享目录不会泄露明文。
        """
        if payload is None or payload == {}:
            return {"payload_enc": None, "payload_sha": None}
        crypto = self._require_crypto("加密任务载荷")
        encrypted = crypto.encrypt_json(payload)
        ref = self._maybe_offload_payload(encrypted)
        if ref is not None:
            return {"payload_enc": json.dumps(
                        {"kind": PAYLOAD_FILE_KIND, "file_ref": ref}, ensure_ascii=False),
                    "payload_sha": payload_sha(payload)}
        return {"payload_enc": encrypted, "payload_sha": payload_sha(payload)}

    def _maybe_offload_payload(self, encrypted_text: str) -> Optional[Dict[str, Any]]:
        """载荷（已加密）超过 ``file_channel.payload_max_bytes`` 时落文件并返回引用。"""
        fc = self.config.queue.get("file_channel") or {}
        threshold = int(fc.get("payload_max_bytes") or 0)
        if threshold <= 0 or len(encrypted_text.encode("utf-8")) <= threshold:
            return None
        return self._write_file_ref(encrypted_text)

    def _payload_file_ref(self, text: str) -> Optional[Dict[str, Any]]:
        """``payload_enc`` 是否是「载荷落文件」的引用信封（不是普通密文）。"""
        stripped = str(text).lstrip()
        if not stripped.startswith("{"):
            return None
        try:
            node = json.loads(stripped)
        except (ValueError, TypeError):
            return None
        if isinstance(node, dict) and node.get("kind") == PAYLOAD_FILE_KIND:
            ref = node.get("file_ref")
            return ref if isinstance(ref, dict) else None
        return None

    def _read_payload_file(self, ref: Dict[str, Any], task_name: str) -> str:
        """按引用读回**已加密**的载荷文本；失效时抛可读的 ``PayloadError``。"""
        path = ref.get("path")
        if not path or not os.path.isfile(path):
            raise PayloadError(
                "任务 %s 载荷文件缺失：%s（大载荷落文件需双方共享 file_channel.dir）"
                % (task_name, path))
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise PayloadError("任务 %s 载荷文件不可读：%s（%s）" % (task_name, path, exc))
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if ref.get("sha256") and actual != ref.get("sha256"):
            raise PayloadError(
                "任务 %s 载荷文件完整性校验失败：期望 %s 实际 %s"
                % (task_name, ref.get("sha256"), actual))
        return text

    def decrypt_payload(self, record: TaskRecord) -> dict:
        """解密任务载荷并按 payload_sha 校验完整性。

        支持大载荷载荷侧落文件：``payload_enc`` 可能是引用信封，此时按引用读回已加密的载荷
        再解密；引用失效（文件缺失/不可读/sha 不匹配）抛可读的 ``PayloadError``。
        """
        if not record.payload_enc:
            return {}
        crypto = self._require_crypto("解密任务载荷(%s)" % record.task_name)
        text = str(record.payload_enc)
        ref = self._payload_file_ref(text)
        encrypted = self._read_payload_file(ref, record.task_name) if ref is not None else text
        result = crypto.decrypt_verify(encrypted)
        if not result.ok:
            raise PayloadError(
                "任务 %s 载荷解密失败：%s（密钥是否一致？密文是否被篡改？）" % (
                    record.task_name, result.reason))
        payload = result.payload if isinstance(result.payload, dict) else {}
        if record.payload_sha:
            actual = payload_sha(payload)
            if actual != record.payload_sha:
                raise PayloadError(
                    "任务 %s 载荷完整性校验失败：payload_sha 不匹配（期望 %s，实际 %s）" % (
                        record.task_name, record.payload_sha, actual))
        return payload

    def encode_result(self, data: Any) -> Optional[str]:
        """把结果编码入库（按配置决定是否加密 + **落库硬上限**截断，BUG-283 收口）。

        ``result_max_bytes`` 是**落库文本**的硬上限：
        - 明文存储时，落库文本 ≤ 上限；
        - 结果加密时，Fernet 信封有固定开销（版本/时间戳/IV/HMAC + base64，约 600B），
          因此先按 ``limit - 600`` 给明文预算，保证加密后的落库文本也 ≤ 上限。

        压不下来时退化为紧凑摘要（保留结构类型 / 字符数 / 开头片段 / 提示），不再整条入库。

        另外支持**大载荷文件通道**（``queue.file_channel.enabled``，默认关闭）：
        结果超过 ``file_channel.max_bytes`` 时把完整结果落文件，信封里只回
        ``file_ref``（路径 + sha256 + 字节数），B 端按引用读回——这样既守住
        ``result_max_bytes`` 的落库上限，又不会丢掉大结果的内容。
        """
        if data is None:
            return None
        limit = int(self.config.queue.get("result_max_bytes") or 0)
        want_encrypt = bool(self.config.queue.get("encrypt_result", True)) \
            and self.crypto is not None
        body = _canonical_json(data)

        file_ref = self._maybe_offload_result(data, body)
        if file_ref is not None:
            node = dict(data) if isinstance(data, dict) else {"result": data}
            node["file_ref"] = file_ref
            node["truncated"] = True
            node["truncate_hint"] = (
                "结果超过 file_channel.max_bytes，已落文件；完整内容请按 file_ref 读取。")
            body = _canonical_json(node)
        elif limit > 0:
            budget = max(128, limit - 600) if want_encrypt else limit
            if len(body.encode("utf-8")) > budget:
                body = _shrink_result_to_bytes(data, budget)
        if want_encrypt:
            return self.crypto.encrypt_json(json.loads(body))
        return body

    # ------------------------------------------------------------------
    # 大载荷文件通道（advance 轮新增）
    # ------------------------------------------------------------------

    def _write_file_ref(self, body: str) -> Dict[str, Any]:
        """把 body 原子写入结果文件目录并返回 file_ref（结果与载荷共用）。

        落点取 ``file_channel.dir``（缺省 base_dir 下的 ``rhop-files``），**双方必须共享**
        （否则对端按引用读不到）；写入用「临时文件 + rename」保证原子性；文件名含内容 sha，
        因此同内容并发写会落到同一个文件（幂等，见语料 F2）。
        """
        directory = self._result_file_dir()
        name = "%s-%s.json" % (
            time.strftime("%Y%m%dT%H%M%S", time.gmtime()),
            hashlib.sha256(body.encode("utf-8")).hexdigest()[:8])
        final = os.path.join(directory, name)
        tmp = final + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, final)
        return {"path": final, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "bytes": os.path.getsize(final), "kind": "rhop-result-file"}

    def _maybe_offload_result(self, data: Any, body: str) -> Optional[Dict[str, Any]]:
        """结果超过阈值且通道开启时落文件，返回引用；否则返回 None。"""
        fc = self.config.queue.get("file_channel") or {}
        if not fc.get("enabled"):
            return None
        threshold = int(fc.get("max_bytes") or 0)
        if threshold <= 0 or len(body.encode("utf-8")) <= threshold:
            return None
        return self._write_file_ref(body)

    def _allowed_file_roots(self) -> List[str]:
        """允许写结果文件的根目录（绝对路径 + realpath 归一，去掉重复与空值）。"""
        roots = []
        for candidate in (self.config.base_dir, getattr(self.config, "shared_write", None),
                          getattr(self.config, "shared_read", None)):
            if not candidate:
                continue
            real = os.path.realpath(os.path.abspath(candidate))
            if real not in roots:
                roots.append(real)
        return roots

    def _result_file_dir(self) -> str:
        """结果文件目录（建目录、返回绝对路径；**带路径校验**，BUG-295 收口）。

        ``file_channel.dir`` 先相对 ``base_dir`` 解析为绝对路径，再 realpath 归一，
        **必须落在 base_dir 或 shared 路径之内**——否则抛 ``SecretError`` 拒绝开启文件通道。
        这样配置写错（或配置来自不可信来源）时不会把任务结果写到项目/共享目录之外。
        """
        fc = self.config.queue.get("file_channel") or {}
        raw = fc.get("dir") or "rhop-files"
        base = self.config.base_dir or "."
        directory = os.path.realpath(os.path.abspath(os.path.join(base, raw)))
        roots = self._allowed_file_roots()
        if roots and not any(directory == r or directory.startswith(r + os.sep) for r in roots):
            raise SecretError(
                "file_channel.dir=%r 解析为 %s，不在允许的根目录内（%s）。"
                "为防止结果文件写到项目/共享目录之外，请把 dir 设成 base_dir 或 shared 路径下的子目录。"
                % (raw, directory, "、".join(roots)))
        os.makedirs(directory, exist_ok=True)
        return directory

    def _read_result_file(self, ref: Any) -> Any:
        """按 file_ref 读回完整结果；缺文件/校验失败返回带原因的标记（不抛错）。"""
        if not isinstance(ref, dict):
            return {"__file_ref_invalid__": ref}
        path = ref.get("path")
        if not path or not os.path.isfile(path):
            return {"__file_missing__": path}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return {"__file_unreadable__": "%s: %s" % (path, exc)}
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if ref.get("sha256") and actual != ref.get("sha256"):
            return {"__file_sha_mismatch__": "期望 %s 实际 %s" % (ref.get("sha256"), actual)}
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return {"__file_not_json__": path}

    def cleanup_result_files(self, now: Optional[str] = None) -> int:
        """清理过期的结果文件（按 ``file_channel.keep_days``，缺省 7 天）。

        **只删本通道写出的结果文件**（文件名匹配 ``RESULT_FILE_RE``，BUG-296 收口）——
        同目录里的其它文件（运维说明、配置副本、别的程序的产物）一律不碰；
        每次删除记一条 info 日志便于审计。返回删除数；目录不存在返回 0。
        """
        fc = self.config.queue.get("file_channel") or {}
        raw = fc.get("dir") or "rhop-files"
        base = self.config.base_dir or "."
        directory = os.path.realpath(os.path.abspath(os.path.join(base, raw)))
        if not os.path.isdir(directory):
            return 0
        keep_days = float(fc.get("keep_days") or 7)
        cutoff_ts = time.time() - keep_days * 86400.0
        removed = 0
        for name in os.listdir(directory):
            if not RESULT_FILE_RE.match(name):
                continue                       # 不认文件身份 ⇒ 不删
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            try:
                if os.path.getmtime(path) < cutoff_ts:
                    os.remove(path)
                    removed += 1
                    self.log.info("清理过期结果文件: %s", path)
            except OSError:
                continue
        return removed

    def decode_result(self, raw: Any) -> Any:
        """把库里的结果解出来（密文自动解密；失败返回 None 而不是抛错）。

        若信封里带 ``file_ref``（大载荷文件通道），按引用读回完整结果；
        引用失效时返回带原因的标记字典（``__file_missing__`` / ``__file_sha_mismatch__`` …），
        而不是抛错——调用方仍能区分「结果为空」与「结果读不回来」。
        """
        if raw is None or raw == "":
            return None
        text = str(raw)
        if text.lstrip().startswith("{"):
            try:
                node = json.loads(text)
            except (ValueError, TypeError):
                return None
            if isinstance(node, dict) and node.get("alg") == "fernet" and node.get("ct"):
                if self.crypto is None:
                    return {"__encrypted__": True}
                result = self.crypto.decrypt_verify(text)
                payload = result.payload if result.ok else {"__decrypt_failed__": result.reason}
                if isinstance(payload, dict) and payload.get("file_ref"):
                    return self._read_result_file(payload["file_ref"])
                return payload
            if isinstance(node, dict) and node.get("file_ref"):
                return self._read_result_file(node["file_ref"])
            return node
        return text

    # ------------------------------------------------------------------
    # A 侧：提交 / 查询
    # ------------------------------------------------------------------

    def normalize_tasks(self, tasks: List[Any],
                        defaults: Optional[Dict[str, Any]] = None) -> List[TaskRecord]:
        """把 str / dict 任务归一为 TaskRecord 列表。"""
        defaults = dict(defaults or {})
        queue_cfg = self.config.queue
        out = []  # type: List[TaskRecord]
        for item in tasks or []:
            if isinstance(item, str):
                data = {"task_name": item, "value": item}
            elif isinstance(item, dict):
                data = dict(item)
                if not data.get("task_name") and data.get("name"):
                    data["task_name"] = data["name"]
                if not data.get("task_name"):
                    raise DagValidationError("任务 dict 必须包含 task_name（或 name）")
            else:
                raise DagValidationError("任务只能是 str 或 dict，收到 %s" % type(item).__name__)

            known = set(DEFINITION_FIELDS) | {"task_name", "value", "payload",
                                              "deps", "state", "priority", "max_retries"}
            inline = {k: data[k] for k in INSTRUCTION_KEYS if k in data
                      and k not in ("payload",) and data[k] is not None}
            payload = data.get("payload")
            if payload is None and inline:
                payload = inline

            record = TaskRecord(
                task_name=data["task_name"],
                task_type=_first_present((data, defaults, queue_cfg), "task_type", str, "CLI"),
                value=data.get("value", data["task_name"]),
                deps=data.get("deps") or [],
                priority=_first_present((data, defaults, queue_cfg), "priority", int, 0),
                timeout_min=_first_present((data, defaults, queue_cfg), "timeout_min", float, 60.0),
                retry_delay_min=_first_present((data, defaults, queue_cfg), "retry_delay_min",
                                               float, 5.0),
                max_retries=_first_present((data, defaults, queue_cfg), "max_retries", int, 3),
                scheduled_at=data.get("scheduled_at"),
                tags=data.get("tags") or [],
                queue=data.get("queue", defaults.get("queue", "")) or "",
                owner=data.get("owner", defaults.get("owner", "")) or "",
                team=data.get("team", defaults.get("team", "")) or "",
                group_name=data.get("group_name", defaults.get("group_name", "")) or "",
                extra_desc=data.get("extra_desc"),
            )
            if payload is not None:
                record.payload_enc = None
                record.payload_sha = None
                self._attach_payload(record, payload)
            out.append(record)
            unknown = set(data) - known
            if unknown:
                self.log.debug("任务 %s 含未识别字段（已忽略）: %s",
                               record.task_name, ", ".join(sorted(unknown)))
        return out

    def _attach_payload(self, record: TaskRecord, payload: Any) -> None:
        encoded = self.encrypt_payload(payload)
        record.payload_enc = encoded["payload_enc"]
        record.payload_sha = encoded["payload_sha"]

    def submit(self, tasks: List[Any], deps: Optional[Dict[str, List[str]]] = None,
               validate_dag: bool = True, **defaults) -> Dict[str, Any]:
        """提交一批任务（幂等：同 task_name 重复提交不会产生新行）。

        Args:
            tasks:       任务列表（str 简写或 dict 完整字段；dict 可内联 action/cli/handler）
            deps:        可选 {task_name: [依赖 task_name, ...]}（dict 内的 deps 优先）
            validate_dag: 是否做依赖存在性 + 成环校验（默认 True）
            **defaults:  缺省字段（task_type / priority / timeout_min / retry_delay_min /
                         max_retries / queue / owner / team / group）

        Returns:
            {"submitted": n, "skipped": m, "total": N, "task_names": [...], "store": {...}}
        """
        records = self.normalize_tasks(list(tasks or []), defaults=defaults)
        deps = deps or {}
        for record in records:
            if not record.deps and record.task_name in deps:
                record.deps = [str(x) for x in (deps[record.task_name] or [])]
        if not records:
            return {"submitted": 0, "skipped": 0, "total": 0, "task_names": [],
                    "store": self.store.describe()}
        if validate_dag:
            self.validate_dag(records)
        before = set(self.store.all_task_names())
        inserted = self.store.insert_tasks(records)
        skipped = len(records) - inserted
        if self.syncer is not None and inserted:
            try:
                self.syncer.push_tasks([r for r in records if r.task_name not in before])
            except Exception as exc:
                self.log.warning("提交后推送同步包失败（本地库已写入）: %s", exc)
        return {"submitted": inserted, "skipped": skipped, "total": len(records),
                "task_names": [r.task_name for r in records],
                "store": self.store.describe()}

    def validate_dag(self, records: List[TaskRecord]) -> None:
        """校验依赖存在性与无环（跨"已有任务 + 本批新任务"整体校验）。"""
        deps_map: Dict[str, List[str]] = {}
        for name in self.store.all_task_names():
            rec = self.store.get_task(name)
            deps_map[name] = list(rec.deps) if rec is not None else []
        for record in records:
            deps_map[record.task_name] = list(record.deps)

        known = set(deps_map.keys())
        for name, dep_names in deps_map.items():
            for dep in dep_names:
                if dep not in known:
                    raise DagValidationError(
                        "任务 %s 依赖的任务 %s 不存在（依赖必须已提交或同批出现）" % (name, dep))
                if dep == name:
                    raise DagValidationError("任务 %s 依赖了自己" % name)

        visiting = set()
        visited = set()

        def _dfs(node: str, chain: List[str]) -> None:
            if node in visiting:
                cycle = " -> ".join(chain + [node])
                raise DagValidationError("检测到循环依赖: %s" % cycle)
            if node in visited:
                return
            visiting.add(node)
            for dep in deps_map.get(node, []):
                _dfs(dep, chain + [node])
            visiting.discard(node)
            visited.add(node)

        for name in sorted(deps_map.keys()):
            _dfs(name, [])

    def get_task(self, task_name: str) -> Optional[TaskRecord]:
        """读一条任务。"""
        return self.store.get_task(task_name)

    def status(self, state: Optional[str] = None, limit: int = 200,
               decrypt_result: bool = True, include_payload: bool = False) -> List[Dict[str, Any]]:
        """列出任务状态（结果默认解密展示；载荷默认不回显明文）。"""
        out = []  # type: List[Dict[str, Any]]
        for rec in self.store.list_tasks(state=state, limit=limit):
            row = {
                "task_name": rec.task_name,
                "task_type": rec.task_type,
                "state": rec.state,
                "deps": rec.deps,
                "priority": rec.priority,
                "retry_count": rec.retry_count,
                "max_retries": rec.max_retries,
                "worker_id": rec.worker_id,
                "scheduled_at": rec.scheduled_at,
                "start_time": rec.start_time,
                "end_time": rec.end_time,
                "updated_at": rec.updated_at,
                "last_err": rec.last_err,
                "has_payload": bool(rec.payload_enc),
                "version": rec.version,
            }
            if decrypt_result:
                row["result"] = self.decode_result(rec.back_info)
            else:
                row["result_enc"] = rec.back_info
            if include_payload:
                try:
                    row["payload"] = self.decrypt_payload(rec)
                except Exception as exc:
                    row["payload_error"] = str(exc)
            out.append(row)
        return out

    def summary(self) -> Dict[str, Any]:
        """队列概览（状态计数 + 存储自描述 + 心跳）。"""
        data = {
            "role": self.config.role_short(),
            "name": self.config.name,
            "counts": self.store.count_by_state(),
            "store": self.store.describe(),
            "all_done": self.store.is_all_done(),
        }
        if self.heartbeat is not None:
            data["heartbeat"] = self.heartbeat.read()
        return data

    def is_all_done(self) -> bool:
        """是否已无待办任务。"""
        return self.store.is_all_done()

    # ------------------------------------------------------------------
    # 运维操作（双方都可调；共享库场景天然可见）
    # ------------------------------------------------------------------

    def cancel(self, task_name: str) -> Dict[str, Any]:
        """取消任务：PENDING/LOCKED 直接 CANCELLED；RUNNING 打取消标记等其收尾。

        **与 reset 的优先级（BUG-290 收口）**：`cancel` 只作用于「尚未结束」的任务
        （PENDING / LOCKED / RETRY_PENDING / RUNNING）；对已经终态（COMPLETED/FAILED/
        CANCELLED）的任务是**幂等 no-op**，并且会打一条 warning 留痕——否则「看起来取消了、
        实际没变」在运维侧无从发现。而 `requeue`/`retry_failed` 的重置意图（resets 通道）
        是**执行意图**，优先级高于取消：B 端先应用 cancels 再应用 resets，因此
        「已完成任务先取消后重置」与「先重置后取消」都会收敛到重置后的状态（PENDING，待重跑）。
        """
        rec = self.store.require_task(task_name)
        now = utcnow_iso()
        if rec.state in (TaskState.PENDING, TaskState.LOCKED, TaskState.RETRY_PENDING):
            self.store.set_state(task_name, TaskState.CANCELLED, force=True, now=now,
                                 end_time=now, worker_id=None, lock_time=None)
            self._sync("push")  # 本地库模式：把取消请求推给 B
            return {"task_name": task_name, "state": TaskState.CANCELLED, "pending": False}
        if rec.state == TaskState.RUNNING:
            self.store.set_cancel_requested(task_name, True, now=now)
            self._sync("push")
            return {"task_name": task_name, "state": rec.state, "pending": True}
        log.warning("取消请求被忽略：任务 %s 已处于终态 %s（reset 意图优先于 cancel，"
                    "见 docs/task-queue.md §14）", task_name, rec.state)
        return {"task_name": task_name, "state": rec.state, "pending": False,
                "reason": "任务已处于终态（%s），未做改动" % rec.state}

    def requeue(self, task_name: str) -> bool:
        """把单个任务强制重置回 PENDING（清锁、清取消标记）。

        本地库模式（挂了 syncer）下**不在本地改状态**：重置意图走 ``TaskSync.resets`` 通道，
        由 B 端真正重跑并回推状态。否则 A 本地 version+1 会把 B 的较新状态永久挡在
        ``apply_state`` 的版本单调门之外，双方发散、A 永远等不到完成（BUG-280）。
        """
        if self.syncer is not None:
            info = self.syncer.request_reset(task_name)
            return bool(info.get("ok"))
        return bool(self.store.requeue(task_name))

    def retry_failed(self, state: Optional[str] = None) -> int:
        """把 FAILED（或指定状态）重置回 PENDING，返回影响行数。

        本地库模式下同样只登记重置意图（交由 B 端重跑），不直接改本地状态。
        """
        if state and str(state).upper() not in (TaskState.FAILED, TaskState.CANCELLED):
            names = [r.task_name for r in self.store.list_tasks(state=state)]
            for name in names:
                if self.syncer is not None:
                    self.syncer.request_reset(name)
                else:
                    self.store.requeue(name)
            return len(names)
        if self.syncer is not None:
            names = [r.task_name for r in self.store.list_tasks(state=TaskState.FAILED)]
            for name in names:
                self.syncer.request_reset(name)
            return len(names)
        return int(self.store.reset_failed())

    # ------------------------------------------------------------------
    # 租约续期（BUG-289 收口）
    # ------------------------------------------------------------------

    def renew_lock(self, task_name: str, worker_id: Optional[str] = None,
                   now: Optional[str] = None) -> bool:
        """刷新任务租约（BUG-289 收口）：任务仍在 RUNNING 且持有者匹配时，
        把 ``lock_time`` / ``expire_time`` 推到现在，避免被 ``clean_stale_locks``
        判死回收后又被别的 worker 重复领取执行。

        Args:
            task_name: 任务名
            worker_id: 持有者（worker 循环里传自己的 id，防止已被回收的任务被旧 worker 续活）
            now: 刷新时间（缺省当前时间）

        Returns:
            bool: 是否刷新成功（任务不存在 / 不在 RUNNING / 持有者不匹配都返回 False）
        """
        return bool(self.store.touch_lock(task_name, worker_id=worker_id, now=now))

    def _start_renewal(self, record: TaskRecord, worker_id: str) -> Optional[Any]:
        """按配置启动后台续期线程；未开启或不需要时返回 None。

        只在 ``queue.renew_lock=true`` 时启用（默认关闭，零回归）：长任务（执行时长可能
        超过锁 TTL）需要周期性刷新租约，否则会被判死回收后重复执行。间隔取
        ``renew_interval_sec``（缺省 = 锁 TTL 的一半，且不超过 TTL）。
        """
        if not self.config.queue.get("renew_lock"):
            return None
        ttl = max(1.0, float(self.config.queue.get("lock_ttl_sec") or 900))
        interval = float(self.config.queue.get("renew_interval_sec") or (ttl / 2.0))
        interval = max(0.5, min(interval, ttl))
        stop = threading.Event()

        def _loop():
            while not stop.wait(interval):
                try:
                    self.renew_lock(record.task_name, worker_id=worker_id)
                except Exception as exc:
                    self.log.warning("租约续期失败(%s): %s", record.task_name, exc)

        threading.Thread(target=_loop, name="rhop-lease-renew", daemon=True).start()
        return stop

    # ------------------------------------------------------------------
    # B 侧：执行
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """请求常驻循环退出（信号处理 / 外部调用）。"""
        self._stop_requested = True

    def run_once(self, worker_id: Optional[str] = None) -> Dict[str, Any]:
        """跑一轮：回收失效锁 → 领取 → 解密 → 执行 → 回写。

        Returns:
            {"action": "completed"|"failed"|"retried"|"cancelled"|"idle"|"stop", ...}
        """
        wid = worker_id or self.config.worker_id()
        now = utcnow_iso()

        if self.heartbeat is not None and self.heartbeat.enabled \
                and self.heartbeat.is_close_requested():
            return {"action": "stop", "reason": "closed", "worker_id": wid}

        # 本地库模式：先拉对端同步包，保证依赖/状态是最新的
        sync_info = self._sync("pull")

        reclaimed = self.store.clean_stale_locks()
        record = self.store.claim_next(wid)
        if record is None:
            return {"action": "idle", "worker_id": wid, "reclaimed": reclaimed, "sync": sync_info}

        if record.cancel_requested:
            self.store.set_state(record.task_name, TaskState.CANCELLED, force=True,
                                 now=now, end_time=now, worker_id=None, lock_time=None)
            self._sync("push")
            return {"action": "cancelled", "task_name": record.task_name, "worker_id": wid}

        self.store.set_state(record.task_name, TaskState.RUNNING, now=now,
                             start_time=now, worker_id=wid)

        try:
            payload = self.decrypt_payload(record)
        except PayloadError as exc:
            result = self._finish_failure(record, str(exc), wid, retryable=False)
            self._sync("push")
            return result

        if not isinstance(payload, dict):
            payload = {}
        # 与 look_upon 的 ctx 语义对齐：任务自身的 value / task_name / task_type
        # 带进执行载荷，供 cli.stdin_from_value、处理器与动作读取。
        payload.setdefault("value", record.value)
        payload.setdefault("task_name", record.task_name)
        payload.setdefault("task_type", record.task_type)

        # 租约续期（BUG-289 收口）：默认关闭（queue.renew_lock=false，零回归）；
        # 开启后后台线程按间隔刷新 lock_time/expire_time，使执行时长可能超过锁 TTL
        # 的长任务不会被 clean_stale_locks 判死回收、再被别的 worker 重复执行。
        renewal = self._start_renewal(record, wid)
        try:
            # BUG-324: timeout_min 必须接入执行器——原实现只写进任务记录、
            # 从未传给 run_payload，命令超时只受 exec.timeout_sec（默认 1 小时）
            # 约束。租约却按 max(lock_ttl, timeout_min×60) 计算 ⇒ 租约先过期、
            # 命令仍在跑 ⇒ 被 clean_stale_locks 回收、重复领取执行。
            # 现在把 timeout_min×60 作为 timeout_sec 传给 run_payload。
            _task_timeout_sec = float(record.timeout_min or 60) * 60.0
            outcome = run_payload(payload, policy=self.policy,
                                  action_cfg=self.config.rhop.action_cfg(),
                                  task_type=record.task_type, handlers=self.handlers,
                                  timeout_sec=_task_timeout_sec)
        except ExecDenied as exc:
            result = self._finish_failure(record, str(exc), wid, retryable=False)
            self._sync("push")
            return result
        except Exception as exc:  # 执行通道自身异常 → 可按策略重试
            result = self._finish_failure(record, "执行异常: %s" % exc, wid, retryable=True)
            self._sync("push")
            return result
        finally:
            if renewal is not None:
                renewal.set()

        if outcome.get("ok"):
            result = self._finish_success(record, outcome, wid)
        else:
            retryable = not str(outcome.get("error") or "").startswith(_NON_RETRYABLE_PREFIX)
            result = self._finish_failure(record, outcome.get("error") or "执行失败", wid,
                                          retryable=retryable, detail=outcome)
        self._sync("push")
        return result

    def _sync(self, direction: str) -> Any:
        """本地库模式的增量同步（无 syncer 时直接跳过）。

        pull 由 TaskSync 按本端方向决定读哪个文档；
        push 时 A 推任务定义、B 推状态快照。
        """
        if self.syncer is None:
            return None
        try:
            if direction == "pull":
                return self.syncer.pull()
            if self.config.role == "SEND":
                return self.syncer.push_tasks()
            return self.syncer.push_states()
        except Exception as exc:
            self.log.warning("同步(%s)失败（不影响本地状态）: %s", direction, exc)
            return {"error": str(exc)}

    def pull_sync(self) -> Any:
        """显式拉一次对端同步包（A 端查状态前调用，保证看到最新）。"""
        return self._sync("pull")

    def _finish_success(self, record: TaskRecord, outcome: Dict[str, Any],
                        worker_id: str) -> Dict[str, Any]:
        """成功：写 COMPLETED + 结果（可加密）。

        BUG-329: 若任务在执行期间被 cancel，终态应是 CANCELLED 而非
        COMPLETED——取消标记只在领取期被读一次，执行期间与收尾时都不再看它，
        导致 cancel RUNNING 任务后命令跑完被记为 COMPLETED，取消语义不完整。
        """
        now = utcnow_iso()
        # BUG-329: 收尾前检查 cancel_requested。record 对象在领取时创建，
        # cancel 请求是在执行期间通过 set_cancel_requested 落库的，
        # record.cancel_requested 可能仍是 False——必须从库重新读取最新值。
        latest = self.store.get_task(record.task_name)
        cancelled = bool(latest and latest.cancel_requested)
        if cancelled:
            self.store.set_state(record.task_name, TaskState.CANCELLED, now=now,
                                 end_time=now, last_err=None,
                                 back_info=self.encode_result({
                                     "channel": outcome.get("channel"),
                                     "name": outcome.get("name"),
                                     "result": outcome.get("result"),
                                     "cancelled": True,
                                     "finished_at": now,
                                     "worker_id": worker_id,
                                 }), worker_id=worker_id)
            self.log.info("任务 %s 已取消（命令跑完后收尾落 CANCELLED）",
                          record.task_name)
            return {"action": "cancelled", "task_name": record.task_name,
                    "worker_id": worker_id}
        info = {
            "channel": outcome.get("channel"),
            "name": outcome.get("name"),
            "result": outcome.get("result"),
            "error": None,
            "finished_at": now,
            "worker_id": worker_id,
        }
        self.store.set_state(record.task_name, TaskState.COMPLETED, now=now, end_time=now,
                             last_err=None, back_info=self.encode_result(info),
                             worker_id=worker_id)
        self.log.info("任务 %s 完成（channel=%s, name=%s）",
                      record.task_name, info["channel"], info["name"])
        return {"action": "completed", "task_name": record.task_name,
                "worker_id": worker_id, "channel": info["channel"]}

    def _finish_failure(self, record: TaskRecord, message: str, worker_id: str,
                        retryable: bool = True,
                        detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """失败：按重试策略落 RETRY_PENDING 或 FAILED。

        BUG-329: 若任务在执行期间被 cancel，终态应是 CANCELLED 而非
        RETRY_PENDING/FAILED——取消优先级高于重试策略。
        """
        now = utcnow_iso()
        # BUG-329: 收尾前检查 cancel_requested。record 对象在领取时创建，
        # cancel 请求是在执行期间通过 set_cancel_requested 落库的，
        # record.cancel_requested 可能仍是 False——必须从库重新读取最新值。
        latest = self.store.get_task(record.task_name)
        cancelled = bool(latest and latest.cancel_requested)
        if cancelled:
            self.store.set_state(record.task_name, TaskState.CANCELLED, now=now,
                                 end_time=now, last_err=message,
                                 back_info=self.encode_result({
                                     "error": message,
                                     "cancelled": True,
                                     "finished_at": now,
                                     "worker_id": worker_id,
                                 }), worker_id=None, lock_time=None)
            self.log.info("任务 %s 已取消（命令失败后收尾落 CANCELLED）",
                          record.task_name)
            return {"action": "cancelled", "task_name": record.task_name,
                    "worker_id": worker_id}
        attempts = int(record.retry_count) + 1
        will_retry = bool(retryable) and int(record.retry_count) < int(record.max_retries)
        state = TaskState.RETRY_PENDING if will_retry else TaskState.FAILED
        scheduled = None
        if will_retry:
            scheduled = iso_add_seconds(now, max(0.0, float(record.retry_delay_min or 0)) * 60.0)
        info = {
            "error": message,
            "channel": (detail or {}).get("channel"),
            "name": (detail or {}).get("name"),
            "detail": detail,
            "finished_at": now,
            "worker_id": worker_id,
        }
        self.store.set_state(record.task_name, state, now=now, end_time=now,
                             last_err=message, back_info=self.encode_result(info),
                             retry_count=attempts, scheduled_at=scheduled,
                             worker_id=None, lock_time=None)
        action = "retried" if will_retry else "failed"
        self.log.warning("任务 %s %s：%s（第 %d/%d 次）",
                         record.task_name, action, message, attempts, record.max_retries)
        return {"action": action, "task_name": record.task_name, "worker_id": worker_id,
                "state": state, "attempt": attempts, "error": message,
                "retry_at": scheduled}

    def run_until_done(self, worker_id: Optional[str] = None,
                       interval: Optional[float] = None,
                       max_iterations: Optional[int] = None,
                       max_idle: Optional[int] = None) -> Dict[str, Any]:
        """阻塞跑到全部任务终结（或达到上限）。

        Args:
            worker_id:      worker 标识
            interval:       idle 时的轮询间隔（秒，缺省取配置 poll_interval_sec）
            max_iterations: 最多轮数（None = 不限）
            max_idle:       连续 idle 上限（None = 不限；设为 1 可做"只跑一次"）
        """
        wid = worker_id or self.config.worker_id()
        sleep_sec = float(interval if interval is not None else self.config.poll_interval())
        stats = {"completed": 0, "failed": 0, "retried": 0, "cancelled": 0,
                 "iterations": 0, "idle": 0, "worker_id": wid}
        factor = 0.05  # 测试可用很小的 interval；保证真实等待下限不夸张
        wait = max(sleep_sec * factor, 0.01)

        while True:
            stats["iterations"] += 1
            if max_iterations is not None and stats["iterations"] > int(max_iterations):
                stats["reason"] = "max-iterations"
                break
            result = self.run_once(wid)
            action = result.get("action")
            if action == "idle":
                if self.is_all_done():
                    stats["reason"] = "all-done"
                    break
                stats["idle"] += 1
                if max_idle is not None and stats["idle"] >= int(max_idle):
                    stats["reason"] = "idle-timeout"
                    break
                time.sleep(wait)
                continue
            if action == "stop":
                stats["reason"] = result.get("reason") or "stop"
                break
            stats["idle"] = 0
            if action in stats:
                stats[action] += 1
            if action == "retried":
                # 立刻重排的任务要给它时间到点
                time.sleep(wait)
        stats["counts"] = self.store.count_by_state()
        stats["all_done"] = self.store.is_all_done()
        return stats

    def run_resident(self, worker_id: Optional[str] = None,
                     interval: Optional[float] = None,
                     should_stop: Optional[Callable[[], bool]] = None,
                     max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """常驻：队列空了也不退出，一直轮询新任务。

        退出条件（任一）：``request_stop()``、``should_stop()`` 为真、
        心跳文件被写成 ``closed``（运维停机指令）。
        """
        wid = worker_id or self.config.worker_id()
        sleep_sec = float(interval if interval is not None else self.config.poll_interval())
        wait = max(sleep_sec * 0.05, 0.01)
        stats = {"iterations": 0, "completed": 0, "failed": 0, "retried": 0,
                 "cancelled": 0, "idle": 0, "worker_id": wid, "reason": None}

        while True:
            stats["iterations"] += 1
            if max_iterations is not None and stats["iterations"] > int(max_iterations):
                stats["reason"] = "max-iterations"
                break
            if self._stop_requested:
                stats["reason"] = "stop-requested"
                break
            if should_stop is not None and should_stop():
                stats["reason"] = "should-stop"
                break
            result = self.run_once(wid)
            action = result.get("action")
            if action == "stop":
                stats["reason"] = result.get("reason") or "stop"
                break
            if action == "idle":
                stats["idle"] += 1
                time.sleep(wait)
                continue
            if action in stats:
                stats[action] += 1
        stats["counts"] = self.store.count_by_state()
        return stats

    # ------------------------------------------------------------------

    def describe(self) -> Dict[str, Any]:
        """自描述（诊断 / CLI）。"""
        return {
            "name": self.config.name,
            "role": self.config.role_short(),
            "worker_id": self.config.worker_id(),
            "store": self.store.describe(),
            "heartbeat": (self.heartbeat.describe() if self.heartbeat is not None else None),
            "exec": self.policy.describe(),
            "sync_mode": (None if self.syncer is None else "sqlite-local"),
            "has_crypto": self.crypto is not None,
        }

    def close(self) -> None:
        """释放自有存储（外部注入的 store 由注入方负责关闭）。"""
        if self._owns_store and self.store is not None:
            self.store.close()


__all__ = ["TaskQueue", "payload_sha", "INSTRUCTION_KEYS"]