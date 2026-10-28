"""resolver.py — 多形态目标解析器（ACTUS_REFACTOR_PLAN.md §3.1）。

把 CLI 传入的 `<target>` 字符串解析为统一的「动作定位结果」，供后续管线消费。
解析优先级（首命中即返回）：
  1. is_scattered_path() → 本地 .actus.md 文件 / .actus/ 目录
  2. 含 "." 且不含 "/"、不匹配 hex32、不匹配 URL → action_id
  3. 32 位 hex → 按指纹查索引
  4. http:// 或 https:// 前缀 → URL 动作源
  5. 其余 → 按 name 查索引

解析结果（ResolvedTarget）：
  source: "id" | "name" | "md5" | "path" | "url"
  action_id: 解析后可得的标准 id
  path: 本地文件路径（path/url 已落盘后）
  raw: 原始输入串
  ambiguous: 多命中时的候选列表
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from .errors import ActionError
from .indexer import load_index, scan_actions

# 32 位 hex 指纹正则（MD5 / SHA-256 前 16 字节）
_HEX32_RE = re.compile(r'^[0-9a-fA-F]{32}$')
# URL 前缀判定
_URL_PREFIXES = ('http://', 'https://')
# 临时下载目录（URL 动作源落盘）
_DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), 'actus_remote')


@dataclass
class ResolvedTarget:
    """解析结果（ACTUS_REFACTOR_PLAN.md §3.1）。"""
    source: str = ''          # "id" | "name" | "md5" | "path" | "url"
    action_id: str = ''       # 解析后可得的标准 id
    path: str = ''            # 本地文件路径
    raw: str = ''             # 原始输入串
    ambiguous: List[str] = field(default_factory=list)  # 多命中候选
    url: str = ''             # 原始 URL（source=url 时）
    downloaded: bool = False  # 是否已落盘
    sha256: str = ''          # 下载内容的 sha256（source=url 时）
    digest_verified: bool = False  # 是否已通过期望指纹校验（计划 §六.3）
    signature_verified: bool = False  # 是否已通过签名校验（计划 §六.3）

    def to_dict(self) -> dict:
        return {
            'source': self.source,
            'action_id': self.action_id,
            'path': self.path,
            'raw': self.raw,
            'ambiguous': self.ambiguous,
            'url': self.url,
            'downloaded': self.downloaded,
            'sha256': self.sha256,
            'digest_verified': self.digest_verified,
            'signature_verified': self.signature_verified,
        }


def _is_url(target: str) -> bool:
    """判定是否为 http/https URL。"""
    t = target.strip().lower()
    return t.startswith(_URL_PREFIXES)


def _is_hex32(target: str) -> bool:
    """判定是否为 32 位十六进制指纹。"""
    return bool(_HEX32_RE.match(target.strip()))


def _is_action_id(target: str) -> bool:
    """判定是否为反域名风格的动作 id（含 "." 且不含 "/"）。"""
    t = target.strip()
    if '/' in t or '\\' in t:
        return False
    if '.' not in t:
        return False
    if _is_hex32(t):
        return False
    if _is_url(t):
        return False
    return True


def _lookup_by_md5(md5_hex: str, index: dict) -> Optional[str]:
    """按 32 位 hex 指纹查索引，返回命中的 action_id 或 None。"""
    # 先查索引中的 by_md5 反向索引
    by_md5 = index.get('by_md5') or {}
    exact = by_md5.get(md5_hex.lower())
    if exact:
        return exact[0] if isinstance(exact, list) else exact
    # 回退：逐个比对 brief.md5 字段
    for aid, brief in (index.get('actions') or {}).items():
        if aid.startswith('_invalid:'):
            continue
        if (brief.get('md5') or '').lower() == md5_hex.lower():
            return aid
    # 再回退：逐个比对文件 sha256 前缀（兼容截断指纹）
    for aid, brief in (index.get('actions') or {}).items():
        if aid.startswith('_invalid:'):
            continue
        sha = brief.get('sha256') or ''
        if sha.lower().startswith(md5_hex.lower()):
            return aid
    return None


def _lookup_by_name(name: str, index: dict) -> List[str]:
    """按人类可读名称查索引，返回所有命中的 action_id 列表。"""
    name_lower = name.strip().lower()
    # 先查索引中的 by_name 反向索引
    by_name = index.get('by_name') or {}
    cached = by_name.get(name_lower)
    if cached:
        return cached if isinstance(cached, list) else [cached]
    # 回退：逐个比对 brief.name 字段
    hits = []
    for aid, brief in (index.get('actions') or {}).items():
        if aid.startswith('_invalid:'):
            continue
        if (brief.get('name') or '').strip().lower() == name_lower:
            hits.append(aid)
    return hits


def _assert_host_allowed(url: str, allow_hosts: List[str] = None) -> None:
    """远程下载的主机白名单门禁——**默认拒绝所有远程**。

    此前两处下载函数都写成 `if allow_hosts:`，把「空列表 / None」当成
    「不校验」⇒ 任何 URL 都能下载，与文档『空列表表示禁止所有远程』相反
    （SSRF 风险）。现在空白名单即拒，要放行必须显式给 --allow-host。
    """
    host = (urlparse(url).hostname or '').lower()
    allowed = [str(h).strip().lower() for h in (allow_hosts or []) if str(h).strip()]
    if not allowed:
        raise ActionError(
            'remote_host_denied',
            f'未配置 --allow-host，默认禁止下载远程资源（目标主机 {host!r}）',
            {'url': url, 'host': host, 'allow_hosts': []})
    if host not in allowed:
        raise ActionError(
            'remote_host_denied',
            f'远程主机 "{host}" 不在 --allow-host 白名单内（白名单：{allowed}）',
            {'url': url, 'host': host, 'allow_hosts': allowed})


def _download_url(url: str, allow_hosts: List[str] = None) -> str:
    """下载 URL 动作源到临时目录，返回本地路径。

    安全约束：
    - **默认禁止所有远程**：allow_hosts 为空即拒（要放行须显式给 --allow-host）
    - SSL 证书校验保持开启（防中间人替换动作源）
    - 文件大小上限 10 MiB
    - 超时 30 秒
    """
    parsed = urlparse(url)
    _assert_host_allowed(url, allow_hosts)
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'Actus-Resolver/1.0'})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()
            if len(data) > 10 * 1024 * 1024:  # 10 MiB
                raise ActionError(
                    'remote_too_large',
                    f'远程动作源过大（{len(data)} 字节 > 10 MiB 上限）',
                    {'url': url, 'size': len(data)},
                )
    except ActionError:
        raise
    except Exception as e:
        raise ActionError(
            'remote_download_failed',
            f'下载远程动作源失败: {type(e).__name__}: {e}',
            {'url': url},
        ) from e

    # 落盘
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(parsed.path) or 'action')
    os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
    local_path = os.path.join(_DOWNLOAD_DIR, f'{url_hash}_{safe_name}')
    with open(local_path, 'wb') as f:
        f.write(data)

    # 验证落盘文件是合法的动作文件
    with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
        header = f.read(1024)
    # 简单验证：包含 id 或 #!cfg 或 YAML front-matter
    if 'id' not in header and '#!cfg' not in header and '---' not in header[:200]:
        # 不删除，由调用方决定是否执行，但给出警告
        pass

    return local_path


def _known_index() -> dict:
    """只读取索引：存在 → 直接读；缺失/为空 → 内存扫描（不写缓存/不建索引）。"""
    from .indexer import load_index, scan_actions
    index = load_index(build=False)
    if index.get('actions'):
        return index
    scanned = scan_actions(validate=False, write_cache=False)
    return {'actions': {aid: action.brief() for aid, action in scanned.items()}}


def _known_action_ids() -> dict:
    return _known_index().get('actions') or {}


def resolve_target(target: str, allow_hosts: List[str] = None,
                   expect_digest: Optional[str] = None,
                   expect_signature_key: Optional[str] = None) -> ResolvedTarget:
    """⚠️ **本函数可能写盘**：action_id / md5 分支不建索引（缺失时内存扫描，
    write_cache=False）；**URL 分支会 `_download_url` 下载到磁盘**（远程动作源
    解析固有行为，白名单/指纹/签名由调用方负责）。

    解析目标字符串为 ResolvedTarget（ACTUS_REFACTOR_PLAN.md §3.1 优先级链）。

    Args:
        target: CLI 传入的 <target> 字符串
        allow_hosts: URL 下载白名单（空列表表示禁止所有远程）

    Returns:
        ResolvedTarget 解析结果

    Raises:
        ActionError: 无法解析时抛出结构化错误
    """
    from .scattered import is_scattered_path

    raw = target.strip()
    result = ResolvedTarget(raw=raw)

    # 优先级 1: 本地零散路径
    if is_scattered_path(raw):
        result.source = 'path'
        result.path = os.path.abspath(raw)
        # 零散路径：解析后取 id
        from .scattered import resolve_scattered, _apply_scattered_defaults
        from .model import parse_cfg_from_file
        try:
            sc = resolve_scattered(raw)
            action = parse_cfg_from_file(sc.path)
            _apply_scattered_defaults(action, sc)
            result.action_id = action.meta.get('id', '')
            result.path = sc.path
        except Exception:
            # 零散路径但未解析出 id —— 路径形态成立但内容非法，
            # 让后续校验阶段报具体错误，这里只标记 source
            pass
        return result

    # 优先级 2: action_id（反域名风格）
    if _is_action_id(raw):
        result.source = 'id'
        result.action_id = raw
        # 验证 id 是否存在（只读：索引缺失时内存扫描，不落盘）
        known = _known_action_ids()
        if raw not in known:
            raise ActionError(
                'action_not_found',
                f'动作 id 不存在: {raw}',
                {'source': 'id', 'known': sorted(known.keys())[:20]},
            )
        return result

    # 优先级 3: 32 位 hex 指纹
    if _is_hex32(raw):
        aid = _lookup_by_md5(raw, _known_index())
        if aid:
            result.source = 'md5'
            result.action_id = aid
            return result
        raise ActionError(
            'action_not_found',
            f'未找到指纹匹配的动作: {raw}',
            {'source': 'md5', 'md5': raw},
        )

    # 优先级 4: URL 动作源
    if _is_url(raw):
        local_path = _download_url(raw, allow_hosts=allow_hosts)
        result.source = 'url'
        result.url = raw
        result.path = local_path
        result.downloaded = True
        # 指纹校验（计划 §六.3）：远程动作「下载即执行」的供应链风险——
        # 白名单只挡主机、SSL 只挡传输层，白名单域名内被替换内容仍会执行，
        # 所以必须比对内容哈希。给了 expect_digest 就必须匹配，否则拒绝。
        import hashlib
        try:
            with open(local_path, 'rb') as fh:
                result.sha256 = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            result.sha256 = ''
        if expect_digest:
            want = str(expect_digest).strip().lower()
            got = str(result.sha256).lower()
            if want != got:
                raise ActionError(
                    'remote_digest_mismatch',
                    f'远程动作指纹不匹配（期望 {want}，实际 {got}）——拒绝执行',
                    {'url': raw, 'expected': want, 'actual': got})
            result.digest_verified = True
        if expect_signature_key:
            # 签名校验（计划 §六.3）：指纹只能证明「内容没变」，不能证明
            # 「谁发的」——白名单域名被攻破时攻击者可以连指纹一起换掉。
            # 这里下载同名 .sig 并用本地可信公钥验签，失败即拒绝。
            sig_url = raw + '.sig'
            try:
                local_sig = _download_url(sig_url, allow_hosts=allow_hosts)
            except Exception as exc:
                raise ActionError(
                    'remote_signature_missing',
                    f'远程动作缺少可用的签名文件（{sig_url}）：{exc}',
                    {'url': raw, 'sig_url': sig_url})
            from .trust_model import SignatureVerifier
            vres = SignatureVerifier().verify_file(
                local_path, sig_path=local_sig, key_name=expect_signature_key)
            if vres.get('status') != 'ok':
                raise ActionError(
                    'remote_signature_invalid',
                    f"远程动作签名校验失败：{vres.get('message')}",
                    {'url': raw, 'sig_url': sig_url, 'verify': vres})
            result.signature_verified = True
        # 尝试解析出 id
        try:
            from .model import parse_cfg_from_file
            action = parse_cfg_from_file(local_path)
            result.action_id = action.meta.get('id', '')
        except Exception:
            pass
        return result

    # 优先级 5: 按 name 查索引
    index = load_index()
    name_hits = _lookup_by_name(raw, index)
    if len(name_hits) == 1:
        result.source = 'name'
        result.action_id = name_hits[0]
        return result
    elif len(name_hits) > 1:
        result.source = 'name'
        result.ambiguous = name_hits
        # 多命中：报错并附候选列表
        raise ActionError(
            'action_ambiguous',
            f'名称 "{raw}" 匹配到多个动作，请使用更精确的名称或直接用 id',
            {'source': 'name', 'ambiguous': name_hits, 'count': len(name_hits)},
        )

    # 所有形态均未命中：最终回退尝试 id（看起来像 id 的串走 id 路径）
    # 这条路径处理「含点但不在索引中」的串—— 可能是拼写错误的 id
    if '.' in raw and '/' not in raw:
        result.source = 'id'
        result.action_id = raw
        raise ActionError(
            'action_not_found',
            f'动作 id 不存在: {raw}',
            {'source': 'id', 'known': sorted((index.get('actions') or {}).keys())[:20]},
        )

    raise ActionError(
        'action_not_found',
        f'无法解析目标: {raw}（尝试形态: 路径/指纹/URL/名称/id 均未命中）',
        {'raw': raw},
    )


def find_action_file(action_id: str, actions_root: str) -> Optional[str]:
    """按 id 在动作根下查找动作文件——**按解析后的 meta['id'] 比对，格式无关**。

    计划 §六.6：此前有三套查找逻辑（resolver / author / dependency 各一份），
    其中 dependency 用字符串搜 `"id": "xxx"` 判断身份 —— 只认旧格式 JSON，
    新格式 YAML front-matter 的 `.actus.schema.md` 全部找不到（实测 4 个
    种子动作在 dependency 里全部返回 None）。这里统一为单一实现，供各模块复用。
    """
    if not action_id or not actions_root or not os.path.isdir(actions_root):
        return None
    from .constants import is_action_file
    from .model import parse_cfg_from_file
    for root, _dirs, files in os.walk(actions_root):
        for fname in files:
            if not is_action_file(fname):
                continue
            path = os.path.join(root, fname)
            try:
                action = parse_cfg_from_file(path)
            except Exception:
                continue
            if action.meta.get('id') == action_id:
                return path
    return None


def resolve_params_extended(params_str: str, allow_hosts: List[str] = None,
                            max_action_depth: int = 3) -> dict:
    """扩展入参解析器（ACTUS_REFACTOR_PLAN.md §3.2）。

    支持：
    - JSON 字面量（原逻辑）
    - @file 本地 JSON 文件（原逻辑）
    - - stdin（原逻辑）
    - @https://… / https://…/*.json URL 下载
    - @action:<action_id> 递归引用
    """
    s = (params_str or '').strip()

    # 空参数
    if not s or s == '{}':
        return {}

    # 递归引用: @action:<action_id>
    if s.startswith('@action:'):
        target_id = s[8:].strip()
        return _resolve_action_ref(target_id, allow_hosts=allow_hosts,
                                  max_depth=max_action_depth, _depth=0, _visited=set())

    # URL 入参: @https://… 或裸 https://…
    if s.startswith('@https://') or s.startswith('@http://'):
        url = s[1:] if s.startswith('@') else s
        return _download_json_url(url, allow_hosts=allow_hosts)
    if s.startswith('https://') or s.startswith('http://'):
        return _download_json_url(s, allow_hosts=allow_hosts)

    # 本地文件: @file（原逻辑）
    if s.startswith('@') and not s.startswith('@action:') and not s.startswith('@http'):
        file_path = s[1:].strip()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                v = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f'入参文件不是合法 JSON: {e}') from e
        except OSError as e:
            raise ValueError(f'无法读取入参文件 {file_path}: {e}') from e
        if not isinstance(v, dict):
            raise ValueError('入参必须是 JSON object')
        return v

    # stdin: -
    if s == '-':
        import sys
        v = json.load(sys.stdin)
        if not isinstance(v, dict):
            raise ValueError('入参必须是 JSON object')
        return v

    # JSON 字面量（原逻辑）
    try:
        v = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f'入参不是合法 JSON: {e}') from e
    if not isinstance(v, dict):
        raise ValueError('入参必须是 JSON object')
    return v


def _download_json_url(url: str, allow_hosts: List[str] = None) -> dict:
    """下载 URL 指向的 JSON 文件并解析。

    **默认禁止所有远程**（allow_hosts 为空即拒）；SSL 证书校验保持开启。
    """
    parsed = urlparse(url)
    _assert_host_allowed(url, allow_hosts)
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'Actus-Resolver/1.0'})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()
            if len(data) > 5 * 1024 * 1024:  # 5 MiB
                raise ActionError(
                    'remote_too_large',
                    f'远程 JSON 过大（{len(data)} 字节 > 5 MiB 上限）',
                    {'url': url, 'size': len(data)},
                )
            text = data.decode('utf-8')
    except ActionError:
        raise
    except Exception as e:
        raise ActionError(
            'remote_download_failed',
            f'下载远程 JSON 失败: {type(e).__name__}: {e}',
            {'url': url},
        ) from e
    try:
        v = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f'远程 JSON 解析失败: {e}') from e
    if not isinstance(v, dict):
        raise ValueError('入参必须是 JSON object')
    return v


def _resolve_action_ref(action_id: str, allow_hosts: List[str] = None,
                        max_depth: int = 3, _depth: int = 0,
                        _visited: set = None) -> dict:
    """递归解析 @action: 引用，取其出参作为本动作入参。"""
    if _visited is None:
        _visited = set()
    if _depth >= max_depth:
        raise ActionError(
            'action_ref_depth_exceeded',
            f'@action: 递归深度超过上限 {max_depth}',
            {'action_id': action_id, 'depth': _depth, 'max_depth': max_depth},
        )
    if action_id in _visited:
        raise ActionError(
            'action_ref_cycle',
            f'@action: 递归引用成环: {action_id}',
            {'action_id': action_id, 'visited': sorted(_visited)},
        )
    _visited.add(action_id)

    from .executor import execute
    result = execute(action_id, {}, confirmed=True)
    if result.get('status') != 'ok':
        raise ActionError(
            'action_ref_failed',
            f'@action: 引用动作 {action_id} 执行失败: {result.get("error", {})}',
            {'action_id': action_id, 'result': result},
        )
    data = result.get('data')
    if not isinstance(data, dict):
        # data 非 dict 时包装为 {"output": ...}
        data = {'output': data}
    return data


import json  # 确保 json 在模块级可用（用于 resolve_params_extended 内的字面量解析）
