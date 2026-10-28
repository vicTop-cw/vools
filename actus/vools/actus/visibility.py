"""visibility.py —— 私有动作与可见性控制引擎（docs/24 §F0-1，docs/41 §B 扩展）。

支持：
- 六级可见性：public / unlisted / private / team / gated（新增）/ internal（新增）
- 多注册表管理（公共/团队/个人/自定义）
- 团队成员管理
- 安装时的可见性检查
- 私有动作执行隔离
- gated 授权式公开：仓级/动作级密钥，只存摘要、可轮换可撤销（GatedKeyStore）
- 密钥使用审计
"""

import json
import os
import time
import hmac
import secrets
import hashlib
import re
from vools.core.dataclass_compat import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ── 可见性级别 ──

VISIBILITY_PUBLIC = "public"
VISIBILITY_UNLISTED = "unlisted"
VISIBILITY_PRIVATE = "private"
VISIBILITY_TEAM = "team"

#: docs/41 §B1 新增两级。
#:   gated    授权式公开：不进公开搜索结果，持 `gated_key` 即可安装并执行（给密钥即用）。
#:            签名与 trust 校验照旧执行 —— 授权 ≠ 免审（docs/41:94）。
#:   internal 仅引擎/授权流程可见可执行；不走市场/索引/签名链路，
#:            默认 `trust=trusted`，物理落位 `actions/system/_internal/`（docs/41:90-93）。
VISIBILITY_GATED = "gated"
VISIBILITY_INTERNAL = "internal"

ALL_VISIBILITIES = [
    VISIBILITY_PUBLIC, VISIBILITY_UNLISTED, VISIBILITY_PRIVATE, VISIBILITY_TEAM,
    VISIBILITY_GATED, VISIBILITY_INTERNAL,
]

#: 允许出现在公开搜索结果里的级别（docs/41 §B2.6：gated 不进公开结果）。
PUBLISHABLE_VISIBILITIES = [
    VISIBILITY_PUBLIC, VISIBILITY_UNLISTED, VISIBILITY_PRIVATE, VISIBILITY_TEAM,
]

#: internal 动作的物理落位标记（docs/41 §B1）。
INTERNAL_DIR_MARKER = "_internal"

#: 错误语义串（供上层映射到 actus 错误码 auth_required / action_invalid）。
AUTH_REQUIRED = "auth_required"

#: 团队名白名单（防路径逃逸：禁 '/'、'\\'、盘符、'..' 跳转；见 TeamManager._team_file_path）。
_TEAM_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')


def is_internal_path(path: str) -> bool:
    """路径是否落在 internal 目录（`.../system/_internal/...`）。

    审计修复（越权绕过）：改前按**大小写敏感**比较，而 Windows/macOS 文件系统
    不区分大小写 —— 把动作放进 `.../system/_INTERNAL/` 就能让 `_internal` 判定
    返回 False（实测 `system/_INTERNAL/x` → False），从而绕过 executor 的
    「internal 动作仅引擎内部可执行」门禁。现在统一小写后再比对（fail-closed）。
    """
    if not path:
        return False
    norm = os.path.abspath(path).replace("\\", "/").lower()
    return f"/{INTERNAL_DIR_MARKER}/" in norm


# ── gated 密钥仓储（存摘要，不存明文） ──────────────────────────────────

class GatedKeyStore:
    """`gated_key` 的授权仓储（docs/41 §B2.2 / §B2.5）。

    设计要点：
      * **只落摘要**（sha256 hex），明文密钥仅在 grant 成功那一次返回给调用方；
        因此本文件即使外泄也交不出可用密钥（docs/41 §9「密钥入 vault、禁止落日志」）。
      * 支持**动作级**与**仓级**两档粒度：仓级密钥对该仓全部 gated 动作共用，
        对同仓的 public/unlisted 动作无任何影响。
      * **轮换即撤销**：同一作用域再次 grant 会整体替换旧摘要集合，旧密钥当场失效，
        已安装方必须重新 `actus install --key`/`actus update` 拿新钥续期。
      * 比对用 `hmac.compare_digest`（定长摘要，避免按位早退的时间侧信道）。
      * 授权记录（谁在何时的哪个作用域上通过）另记审计行，**不含密钥值**。
    """

    CURRENT = "current"

    def __init__(self, config_dir: str = None):
        base = config_dir or os.path.join(os.path.expanduser("~"), ".actus")
        self.path = os.path.join(base, "gated_keys.json")
        self.audit_path = os.path.join(base, "gated_audit.jsonl")
        self._data: Dict[str, dict] = {}
        self._load()

    # 内部

    def _load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                # 仓储不可读时**不得**当成「没有任何授权」之外的状态：显式抛出，
                # 让调用方拒绝放行，而不是静默降级成 fail-open。
                raise RuntimeError(
                    f"gated 密钥仓储损坏或不可读：{self.path}（拒绝放行，不静默降级）")
        else:
            self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass                      # Windows 上 chmod 语义有限，摘要文件本身不含明文

    @staticmethod
    def digest_of(key: str) -> str:
        return hashlib.sha256((key or "").encode("utf-8")).hexdigest()

    @staticmethod
    def generate() -> str:
        """生成一把新授权密钥（只在返回时是明文，此后只存摘要）。"""
        return "actus-gk-" + secrets.token_urlsafe(32)

    def scope_id(self, action_id: str = "", repo: str = "") -> str:
        if action_id:
            return f"action:{action_id}"
        if repo:
            return f"repo:{repo}"
        raise ValueError("gated 密钥需要 action_id 或 repo 之一")

    # 对外

    def grant(self, action_id: str = "", repo: str = "",
              key: str = "") -> dict:
        """生成/设定（并轮换）某作用域的 gated 密钥。返回明文一次。"""
        sid = self.scope_id(action_id, repo)
        new_key = key or self.generate()
        if not new_key:
            raise ValueError("key 不能为空")
        digest = self.digest_of(new_key)
        previous = list((self._data.get(sid) or {}).get(self.CURRENT, []))
        self._data[sid] = {
            self.CURRENT: [digest],          # 整体替换 → 旧密钥立即失效（§B2.5）
            "rotated_at": time.time(),
            "rotations": int((self._data.get(sid) or {}).get("rotations", 0)) + 1,
            "superseded": previous + list((self._data.get(sid) or {}).get("superseded", [])),
        }
        self._save()
        self._audit("grant", sid, bool(previous))
        return {"scope": sid, "key": new_key, "digest": digest,
                "rotated": bool(previous),
                "warning": "密钥仅此一次明文返回，之后只存 sha256 摘要"}

    def verify(self, key: str, action_id: str = "", repo: str = "") -> bool:
        """校验密钥是否被该作用域授权（动作级优先，其次仓级共用）。"""
        if not key:
            return False
        digest = self.digest_of(key)
        candidates = [f"action:{action_id}"] if action_id else []
        if repo:
            candidates.append(f"repo:{repo}")
        for sid in candidates:
            entry = self._data.get(sid)
            if not entry:
                continue
            for stored in entry.get(self.CURRENT, []):
                if hmac.compare_digest(stored, digest):
                    self._audit("verify-ok", sid, False)
                    return True
        self._audit("verify-deny", ", ".join(candidates) or "-", False)
        return False

    def has_gate(self, action_id: str = "", repo: str = "") -> bool:
        """该作用域是否已设定过密钥（未设定 = 没有任何人能装）。"""
        return bool(self._data.get(self.scope_id(action_id, repo), {})
                    .get(self.CURRENT))

    def revoke(self, action_id: str = "", repo: str = "") -> bool:
        """撤销该作用域的全部授权。"""
        sid = self.scope_id(action_id, repo)
        if sid in self._data:
            del self._data[sid]
            self._save()
            self._audit("revoke", sid, False)
            return True
        return False

    def list_scopes(self) -> List[dict]:
        out = []
        for sid, entry in self._data.items():
            out.append({"scope": sid,
                        "configured": bool(entry.get(self.CURRENT)),
                        "key_count": len(entry.get(self.CURRENT, [])),
                        "rotations": entry.get("rotations", 0),
                        "rotated_at": entry.get("rotated_at")})
        return out

    def _audit(self, event: str, scope: str, rotated: bool) -> None:
        """审计行：只记事件/作用域/时间，绝记密钥值。"""
        try:
            os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.time(), "event": event,
                                    "scope": scope, "rotated": rotated},
                                   ensure_ascii=False) + "\n")
        except OSError:
            pass                      # 审计落盘失败不改变授权判定结果（判定已在上面完成）



# ── 数据结构 ──

#: 团队成员合法角色（拼错会静默失去权限，故必须白名单校验）
MEMBER_ROLES = frozenset({"admin", "member", "viewer"})


def _require_str(value, what: str) -> str:
    """字段必须是字符串（bool/int/None 一律拒绝，避免污染配置）。"""
    if not isinstance(value, str):
        raise ValueError(f"{what} 必须是字符串，得到 {type(value).__name__}: {value!r}")
    return value


@dataclass
class RegistryConfig:
    """注册表配置。"""
    name: str
    url: str
    registry_type: str = "http"  # http | git | private
    branch: str = "main"
    auth: str = ""  # ssh | token | ""
    priority: int = 0  # 搜索优先级（数字越小优先级越高）

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "type": self.registry_type,
            "branch": self.branch,
            "auth": self.auth,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RegistryConfig":
        if not isinstance(d, dict):
            raise ValueError(
                f"RegistryConfig 需要 dict，得到 {type(d).__name__}")
        priority = d.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError(
                f"RegistryConfig.priority 必须是整数，得到 {priority!r}")
        return cls(
            name=_require_str(d.get("name", ""), "RegistryConfig.name"),
            url=_require_str(d.get("url", ""), "RegistryConfig.url"),
            registry_type=_require_str(d.get("type", "http"), "RegistryConfig.type"),
            branch=_require_str(d.get("branch", "main"), "RegistryConfig.branch"),
            auth=_require_str(d.get("auth", ""), "RegistryConfig.auth"),
            priority=priority,
        )


@dataclass
class TeamMember:
    """团队成员。"""
    user_id: str
    role: str = "member"  # admin | member | viewer
    public_key: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.user_id,
            "role": self.role,
            "public_key": self.public_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TeamMember":
        if not isinstance(d, dict):
            raise ValueError(
                f"TeamMember 需要 dict，得到 {type(d).__name__}: {d!r}")
        user_id = d.get("id", "")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError(
                f"TeamMember.id 必须是非空字符串，得到 {user_id!r}"
                f"（空 id 会让 is_member('') 命中）")
        role = d.get("role", "member")
        if role not in MEMBER_ROLES:
            raise ValueError(
                f"TeamMember.role 必须是 {sorted(MEMBER_ROLES)} 之一，"
                f"得到 {role!r}（拼错会静默失去权限）")
        return cls(
            user_id=user_id,
            role=role,
            public_key=_require_str(d.get("public_key", ""), "TeamMember.public_key"),
        )


@dataclass
class TeamConfig:
    """团队配置。"""
    name: str
    members: List[TeamMember] = field(default_factory=list)
    default_trust: str = "community"
    require_signature: bool = True

    def to_dict(self) -> dict:
        return {
            "team": self.name,
            "members": [m.to_dict() for m in self.members],
            "default_trust": self.default_trust,
            "require_signature": self.require_signature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TeamConfig":
        if not isinstance(d, dict):
            raise ValueError(
                f"TeamConfig 需要 dict，得到 {type(d).__name__}")
        raw_members = d.get("members", [])
        if not isinstance(raw_members, (list, tuple)):
            raise ValueError(
                f"TeamConfig.members 必须是列表，得到 {type(raw_members).__name__}"
                f"（字符串会被逐字符迭代）")
        members = [TeamMember.from_dict(m) for m in raw_members]
        require_signature = d.get("require_signature", True)
        if not isinstance(require_signature, bool):
            raise ValueError(
                f"TeamConfig.require_signature 必须是布尔，得到 {require_signature!r}")
        return cls(
            name=_require_str(d.get("team", ""), "TeamConfig.team"),
            members=members,
            default_trust=_require_str(d.get("default_trust", "community"),
                                       "TeamConfig.default_trust"),
            require_signature=require_signature,
        )

    def is_member(self, user_id: str) -> bool:
        return any(m.user_id == user_id for m in self.members)

    def get_role(self, user_id: str) -> Optional[str]:
        for m in self.members:
            if m.user_id == user_id:
                return m.role
        return None

    def is_admin(self, user_id: str) -> bool:
        return self.get_role(user_id) == "admin"


# ── 注册表管理器 ──

class RegistryManager:
    """多注册表管理器。

    管理公共、团队、个人和自定义注册表。
    """

    DEFAULT_REGISTRIES = {
        "public": RegistryConfig(
            name="public",
            url="https://registry.actus.dev/public/index.json",
            registry_type="http",
            priority=100,
        ),
        "private": RegistryConfig(
            name="private",
            url="",
            registry_type="private",
            priority=0,
        ),
    }

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.join(os.path.expanduser("~"), ".actus")
        self._config_file = os.path.join(self._config_dir, "config.json")
        self._registries: Dict[str, RegistryConfig] = {}
        self._private_dir = os.path.join(self._config_dir, "private")
        self._load_config()

    def _load_config(self):
        """加载配置。"""
        self._registries = dict(self.DEFAULT_REGISTRIES)
        if os.path.isfile(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for name, reg_data in data.get("registries", {}).items():
                    self._registries[name] = RegistryConfig.from_dict(reg_data)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_config(self):
        """保存配置。"""
        os.makedirs(self._config_dir, exist_ok=True)
        data = {
            "registries": {name: reg.to_dict() for name, reg in self._registries.items()}
        }
        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_registry(self, config: RegistryConfig):
        """添加注册表。"""
        self._registries[config.name] = config
        self._save_config()

    def remove_registry(self, name: str) -> Optional[RegistryConfig]:
        """移除注册表。"""
        reg = self._registries.pop(name, None)
        if reg:
            self._save_config()
        return reg

    def get_registry(self, name: str) -> Optional[RegistryConfig]:
        """获取注册表配置。"""
        return self._registries.get(name)

    def list_registries(self) -> List[RegistryConfig]:
        """列出所有注册表（按优先级排序）。"""
        return sorted(self._registries.values(), key=lambda r: r.priority)

    def get_private_dir(self) -> str:
        """获取私有目录路径。"""
        os.makedirs(self._private_dir, exist_ok=True)
        return self._private_dir


# ── 团队管理器 ──

class TeamManager:
    """团队成员与权限管理。"""

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.join(os.path.expanduser("~"), ".actus")
        self._teams_dir = os.path.join(self._config_dir, "teams")
        self._teams: Dict[str, TeamConfig] = {}

    def _team_file_path(self, team_name: str) -> str:
        """团队名 → 团队文件绝对路径（**两道**校验）。

        审计修复（路径逃逸 P1）：改前 `os.path.join(self._teams_dir, f"{name}.json")`
        完全不校验 name，实测：
          * `create_team('../../escaped_team', ...)` 把文件写到配置目录**外**；
          * `delete_team('../victim')` **删掉了目录外的任意 .json**（比写入更危险）。
        现在：
          1. 白名单：只允许 `[A-Za-z0-9._-]`，且不得含 `..`（挡掉 '/'、'\\'、盘符、相对跳转）；
          2. 归一化兜底：`realpath` 后必须仍落在 `realpath(_teams_dir)` 之内
             （白名单是第一道，realpath 是第二道 —— 防止将来有人放宽白名单）。
        非法名抛 ValueError；只读入口（load_team/delete_team）自行降级为 None/False。
        """
        if (not isinstance(team_name, str) or not team_name
                or not _TEAM_NAME_RE.match(team_name) or '..' in team_name):
            raise ValueError(
                f"非法团队名: {team_name!r}（只允许字母/数字/._-，且不得含 '..'）")
        team_file = os.path.abspath(os.path.join(self._teams_dir, team_name + ".json"))
        base = os.path.realpath(self._teams_dir)
        real = os.path.realpath(team_file)
        if real != base and not real.startswith(base + os.sep):
            raise ValueError(f"团队路径越界（已拒绝）: {team_name!r}")
        return team_file

    def load_team(self, team_name: str) -> Optional[TeamConfig]:
        """加载团队配置。非法团队名 → None（拒绝访问，不抛穿）。"""
        try:
            team_file = self._team_file_path(team_name)
        except ValueError:
            return None
        if os.path.isfile(team_file):
            try:
                with open(team_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                team = TeamConfig.from_dict(data)
                self._teams[team_name] = team
                return team
            except (ValueError, KeyError):
                # 审计修复：TeamConfig.from_dict 对非法成员会抛 ValueError
                # （空 id / 非法 role），改前只 catch JSONDecodeError/KeyError
                # → 团队文件一旦被写坏，get_team/check_visibility 直接崩（拒绝服务）。
                # 现在统一降级为 None（调用方按"团队不存在"处理 = fail-closed）。
                return None
        return None

    def save_team(self, team: TeamConfig):
        """保存团队配置。团队名非法 → 抛 ValueError（不写盘）。"""
        team_file = self._team_file_path(team.name)
        os.makedirs(self._teams_dir, exist_ok=True)
        with open(team_file, "w", encoding="utf-8") as f:
            json.dump(team.to_dict(), f, ensure_ascii=False, indent=2)
        self._teams[team.name] = team

    def create_team(self, name: str, creator_user_id: str) -> TeamConfig:
        """创建团队。团队名非法 → 抛 ValueError（由 save_team 的校验把关）。"""
        team = TeamConfig(name=name, members=[TeamMember(user_id=creator_user_id, role="admin")])
        self.save_team(team)
        return team

    def delete_team(self, name: str) -> bool:
        """删除团队。返回是否真的删了；非法团队名 → False（**不删除任何文件**）。"""
        try:
            team_file = self._team_file_path(name)
        except ValueError:
            return False
        self._teams.pop(name, None)
        if os.path.isfile(team_file):
            os.remove(team_file)
            return True
        return False

    def add_member(self, team_name: str, user_id: str, role: str = "member",
                   public_key: str = "") -> bool:
        """添加团队成员（写侧校验与 from_dict 对齐）。

        审计修复：改前不校验 user_id/role —— 实测 `add_member(t, '')` 返回 True
        并把空 id 写进团队文件，之后 `TeamConfig.from_dict` 抛 ValueError，
        `get_team`/`check_visibility` 全部崩溃（团队级动作永远判定失败）；
        `role='superadmin'` 同样能写进去。现在写侧直接拒绝（fail-closed）。
        """
        if not isinstance(user_id, str) or not user_id.strip():
            return False
        if role not in MEMBER_ROLES:
            return False
        team = self.load_team(team_name)
        if not team:
            return False
        if team.is_member(user_id):
            return False
        team.members.append(TeamMember(user_id=user_id, role=role, public_key=public_key))
        self.save_team(team)
        return True

    def remove_member(self, team_name: str, user_id: str) -> bool:
        """移除团队成员。"""
        team = self.load_team(team_name)
        if not team:
            return False
        original_len = len(team.members)
        team.members = [m for m in team.members if m.user_id != user_id]
        if len(team.members) < original_len:
            self.save_team(team)
            return True
        return False

    def get_team(self, team_name: str) -> Optional[TeamConfig]:
        """获取团队配置。"""
        return self.load_team(team_name)

    def list_teams(self) -> List[str]:
        """列出所有团队（只列白名单内的合法名字，跳过可疑文件）。"""
        if not os.path.isdir(self._teams_dir):
            return []
        teams = []
        for f in os.listdir(self._teams_dir):
            if not f.endswith(".json"):
                continue
            name = f[:-5]
            if not _TEAM_NAME_RE.match(name) or '..' in name:
                continue
            teams.append(name)
        return sorted(teams)


# ── 可见性控制引擎 ──

class VisibilityEngine:
    """可见性控制引擎。

    核心职责：
    - 检查动作的可见性级别
    - 验证用户是否有权限访问/安装/执行动作
    - 管理私有动作列表
    """

    def __init__(self, config_dir: str = None, current_user: str = "",
                 gated_store: "GatedKeyStore" = None):
        self._config_dir = config_dir or os.path.join(os.path.expanduser("~"), ".actus")
        self._current_user = current_user or os.environ.get("ACTUS_USER", os.getlogin() if hasattr(os, "getlogin") else "default")
        self._registry_manager = RegistryManager(config_dir)
        self._team_manager = TeamManager(config_dir)
        self._private_index_file = os.path.join(self._config_dir, "private", "index.json")
        self._private_actions: Dict[str, dict] = {}
        self._gated_store = gated_store
        self._load_private_index()

    @property
    def current_user(self) -> str:
        return self._current_user

    @property
    def gated_keys(self) -> "GatedKeyStore":
        """gated 密钥仓储（惰性建：非 gated 路径不受其损坏影响）。"""
        if self._gated_store is None:
            self._gated_store = GatedKeyStore(self._config_dir)
        return self._gated_store

    # ── 私有动作索引 ──

    def _load_private_index(self):
        """加载私有动作索引。"""
        if os.path.isfile(self._private_index_file):
            try:
                with open(self._private_index_file, "r", encoding="utf-8") as f:
                    self._private_actions = json.load(f)
            except (json.JSONDecodeError, KeyError):
                self._private_actions = {}

    def _save_private_index(self):
        """保存私有动作索引。"""
        os.makedirs(os.path.dirname(self._private_index_file), exist_ok=True)
        with open(self._private_index_file, "w", encoding="utf-8") as f:
            json.dump(self._private_actions, f, ensure_ascii=False, indent=2)

    def add_private_action(self, action_id: str, metadata: dict):
        """添加私有动作到索引。

        审计修复（配合 check_visibility 的 fail-closed）：
        写入时**补全 author**（缺省 = 当前用户）—— 否则条目没有归属者，
        访问判定只能一律拒绝（作者自己也进不去）；补全后"仅作者可见"才成立，
        而手工/外部写坏的索引（无 author）仍会被拒绝（不 fail-open）。
        """
        meta = dict(metadata or {})
        if not str(meta.get("author") or "").strip():
            meta["author"] = self._current_user
        self._private_actions[action_id] = {
            **meta,
            "action_id": action_id,
            "visibility": VISIBILITY_PRIVATE,
            "added_at": time.time(),
        }
        self._save_private_index()

    def remove_private_action(self, action_id: str) -> bool:
        """移除私有动作。"""
        if action_id in self._private_actions:
            del self._private_actions[action_id]
            self._save_private_index()
            return True
        return False

    def list_private_actions(self) -> List[dict]:
        """列出所有私有动作。"""
        return list(self._private_actions.values())

    def get_private_action(self, action_id: str) -> Optional[dict]:
        """获取私有动作元数据。"""
        return self._private_actions.get(action_id)

    # ── 可见性检查 ──

    def check_visibility(self, action_id: str, visibility: str,
                         expected_user: str = None, key: str = "",
                         repo: str = "", internal_caller: bool = False
                         ) -> Tuple[bool, str]:
        """检查用户是否有权限访问该可见性级别的动作。

        参数:
            action_id: 动作 id。
            visibility: 可见性级别。
            expected_user: 期望的用户（默认当前用户）。
            key: gated 授权密钥明文（仅 `visibility == "gated"` 用；docs/41 §B2）。
            repo: 仓名（gated 的**仓级**密钥粒度，docs/41 §B2.2）。
            internal_caller: 调用方是否为引擎内部路由（`visibility == "internal"`
                的唯一放行通道，docs/41 §B1「仅引擎/授权流程」）。

        返回:
            (是否允许, 拒绝原因)。拒绝原因里 gated 未授权固定以 `auth_required:`
            开头，供上层直接映射成错误码；其余级别沿用既有文案。
        """
        user = expected_user or self._current_user

        if visibility == VISIBILITY_PUBLIC:
            return True, ""

        if visibility == VISIBILITY_UNLISTED:
            # 知道 ID 即可访问
            return True, ""

        if visibility == VISIBILITY_PRIVATE:
            # 仅作者可访问
            action = self._private_actions.get(action_id)
            if not action:
                return False, f"Private action not found: {action_id}"
            author = action.get("author", "")
            # 审计修复（fail-open）：改前 `if author and author != user` ——
            # 私有动作元数据**没有 author 字段**（或 author 为空串）时直接
            # `return True`，等于对所有人放行。实测：add_private_action('x', {})
            # 后 check_visibility('x', private, user='bob') → (True, '')。
            # 私有语义是"仅作者可见"，作者缺失时无法确认 → 拒绝（fail-closed）。
            if not isinstance(author, str) or not author.strip():
                return False, (f"Action '{action_id}' is private 但缺少 author 元数据，"
                               f"无法确认归属（已按拒绝处理）")
            if author != user:
                return False, f"Action '{action_id}' is private (author: {author})"
            return True, ""

        if visibility == VISIBILITY_TEAM:
            # 需要检查团队（不用海象运算符，保持 py3.6 兼容）
            action = self._find_action(action_id)
            team_name = action.get("team", "") if action else ""
            if not team_name:
                return False, f"No team associated with action: {action_id}"
            team = self._team_manager.get_team(team_name)
            if not team:
                return False, f"Team not found: {team_name}"
            if not team.is_member(user):
                return False, f"User '{user}' is not a member of team '{team_name}'"
            return True, ""

        if visibility == VISIBILITY_GATED:
            # 授权式公开：持有效密钥即可，与身份无关（docs/41 §B2.1）。
            if not key:
                return False, (f"{AUTH_REQUIRED}: 动作 '{action_id}' 为 gated，"
                               f"安装/执行需带 --key <gated_key>")
            try:
                store = self.gated_keys
            except RuntimeError as exc:
                # 仓储损坏 → 拒绝放行（fail-closed），绝不静默当无门禁
                return False, f"{AUTH_REQUIRED}: {exc}"
            if store.verify(key, action_id=action_id, repo=repo):
                return True, ""
            return False, (f"{AUTH_REQUIRED}: 密钥对动作 '{action_id}' 无效或已被"
                           f"轮换撤销（作者轮换后需重新获取）")

        if visibility == VISIBILITY_INTERNAL:
            # 仅引擎/授权流程；普通用户路径一律拒，即使本人是作者（docs/41 §B1）。
            if internal_caller:
                return True, ""
            return False, (f"internal 动作 '{action_id}' 仅限引擎内部路由执行，"
                           f"不经市场/索引/搜索分发")

        return False, f"Unknown visibility level: {visibility}"

    def _find_action(self, action_id: str) -> Optional[dict]:
        """查找动作的可见性相关元数据（team / visibility / author）。

        **查找优先级（这里写死，别处不要再猜）**：
          1. **私有动作索引**（`add_private_action` 登记的元数据）—— 显式登记，
             可能携带动作文件里没有的字段（远端动作、仓级登记）；
          2. 回退到**动作文件的 `#!cfg`**（本地动作的真实来源，`visibility set`
             写的就是这里）。
        两者都没有 → None（调用方 fail-closed）。

        审计修（本轮）：改前**只查私有索引**，于是 `visibility set --level team --team X`
        把团队名写进 cfg 之后，`check_visibility(team)` 仍恒返回
        `No team associated with action` —— 团队名落盘了却没有任何判定方能用，
        等于这条可见性规则不存在。现在两种来源都认，优先级如上。
        """
        entry = self._private_actions.get(action_id)
        if entry:
            return entry
        try:
            import vools.actus as _actus
            action = _actus.get_action(action_id)
        except Exception:
            return None
        meta = getattr(action, 'meta', None) or {}
        picked = {}
        for key in ('team', 'visibility', 'author'):
            value = meta.get(key)
            if value:
                picked[key] = value
        return picked or None

    def can_install(self, action_id: str, visibility: str,
                    registry_name: str = "public", key: str = "",
                    repo: str = "") -> Tuple[bool, str]:
        """检查是否允许安装动作。

        docs/41 的收紧点：`internal` 永不可安装（只随引擎走），`gated` 必须带有效
        密钥。其余既有级别行为不变（public/unlisted/team 仍放行，private 走作者校验）。
        """
        if visibility == VISIBILITY_INTERNAL:
            return False, (f"internal 动作 '{action_id}' 不经安装分发"
                           f"（随仓库落位 actions/system/_internal/）")
        if visibility == VISIBILITY_GATED:
            return self.check_visibility(action_id, visibility, key=key, repo=repo)
        if visibility == VISIBILITY_PRIVATE:
            return self.check_visibility(action_id, visibility)
        return True, ""

    def can_execute(self, action_id: str, visibility: str, key: str = "",
                    repo: str = "", internal_caller: bool = False) -> Tuple[bool, str]:
        """检查是否允许执行动作。"""
        return self.check_visibility(action_id, visibility, key=key, repo=repo,
                                     internal_caller=internal_caller)

    def is_searchable(self, visibility: str) -> bool:
        """该级别是否出现在公开搜索结果里（docs/41 §B1 / §B2.6）。

        gated / internal 均不进公开结果；安装 gated 动作需显式给出完整 id + 密钥，
        这与 unlisted 的「知道 ID 即可」不同 —— gated 是「知道 ID 还不够」。
        """
        return visibility in (VISIBILITY_PUBLIC, VISIBILITY_UNLISTED,
                              VISIBILITY_PRIVATE, VISIBILITY_TEAM)

    # ── 注册表代理 ──

    @property
    def registry(self) -> RegistryManager:
        return self._registry_manager

    @property
    def teams(self) -> TeamManager:
        return self._team_manager

    # ── 综合权限查询 ──

    def get_action_permissions(self, action_id: str, visibility: str,
                               key: str = "", repo: str = "",
                               internal_caller: bool = False) -> dict:
        """获取动作的综合权限信息。

        未知级别显式落到 else 分支并带上 `unknown_visibility=True`：原先没有 else，
        未知值与「有级别但被拒」在返回值上不可区分，调用方没法分辨是配置写错还是
        确实没权限。
        """
        can_view = False
        can_install = False
        can_execute = False
        reason = ""
        unknown = visibility not in ALL_VISIBILITIES

        if visibility == VISIBILITY_PUBLIC:
            can_view = can_install = can_execute = True
        elif visibility == VISIBILITY_UNLISTED:
            can_view = can_install = can_execute = True
        elif visibility == VISIBILITY_PRIVATE:
            ok, reason = self.check_visibility(action_id, visibility)
            can_view = can_install = can_execute = ok
        elif visibility == VISIBILITY_TEAM:
            ok, reason = self.check_visibility(action_id, visibility)
            can_view = can_install = can_execute = ok
        elif visibility == VISIBILITY_GATED:
            # 不可搜索；持密钥才可安装/执行（docs/41 §B1 表）
            can_view = False
            ok, reason = self.check_visibility(action_id, visibility,
                                               key=key, repo=repo)
            can_install = can_execute = ok
        elif visibility == VISIBILITY_INTERNAL:
            # 不可搜索、不可安装、仅内部路由可执行
            can_view = False
            can_install = False
            can_execute, reason = self.check_visibility(
                action_id, visibility, internal_caller=internal_caller)

        result = {
            "action_id": action_id,
            "visibility": visibility,
            "current_user": self._current_user,
            "can_view": can_view,
            "can_install": can_install,
            "can_execute": can_execute,
            "searchable": self.is_searchable(visibility),
        }
        if reason:
            result["reason"] = reason
        if unknown:
            result["unknown_visibility"] = True
            result["allowed_values"] = list(ALL_VISIBILITIES)
        return result


# ── 密钥审计 ──

class SecretAuditor:
    """密钥使用审计。

    记录密钥被哪些动作使用（不记录密钥值）。
    """

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.join(os.path.expanduser("~"), ".actus")
        self._audit_file = os.path.join(self._config_dir, "vault", "audit.jsonl")

    def record_usage(self, key_name: str, action_id: str, visibility: str):
        """记录密钥使用。"""
        os.makedirs(os.path.dirname(self._audit_file), exist_ok=True)
        entry = {
            "timestamp": time.time(),
            "key_name": key_name,
            "action_id": action_id,
            "visibility": visibility,
        }
        with open(self._audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_audit(self, key_name: str, limit: int = 50) -> List[dict]:
        """获取密钥使用审计记录。"""
        if not os.path.isfile(self._audit_file):
            return []
        entries = []
        with open(self._audit_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("key_name") == key_name:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries[-limit:]

    def get_all_audits(self, limit: int = 100) -> List[dict]:
        """获取所有审计记录。"""
        if not os.path.isfile(self._audit_file):
            return []
        entries = []
        with open(self._audit_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return entries[-limit:]

    def record_visibility(self, action_id: str, visibility: str,
                          exec_id: str = "", granted: bool = True) -> None:
        """记录一次可见性判定（docs/41 §B2.4：授权过程要留痕，但**不留密钥值**）。

        与 record_usage 同文件同形状，多带 visibility/exec_id/granted 三列，
        这样 `internal` 内部路由与 `gated` 密钥放行都能事后追溯是哪一个 exec、
        判定结果如何 —— 而行里绝不出现密钥（审计外泄不等于授权泄漏）。
        """
        os.makedirs(os.path.dirname(self._audit_file), exist_ok=True)
        entry = {
            "timestamp": time.time(),
            "event": "visibility",
            "action_id": action_id,
            "visibility": visibility,
            "exec_id": exec_id,
            "granted": bool(granted),
        }
        with open(self._audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── 便捷函数 ──

def check_visibility(action_id: str, visibility: str,
                     current_user: str = "") -> Tuple[bool, str]:
    """便捷函数：检查可见性。"""
    engine = VisibilityEngine(current_user=current_user)
    return engine.check_visibility(action_id, visibility)


def grant_gated_key(action_id: str = "", repo: str = "", key: str = "",
                    config_dir: str = None) -> dict:
    """便捷函数：生成/轮换 gated 授权密钥（明文只在此返回一次）。"""
    return GatedKeyStore(config_dir).grant(action_id=action_id, repo=repo, key=key)


def revoke_gated_key(action_id: str = "", repo: str = "",
                     config_dir: str = None) -> bool:
    """便捷函数：撤销 gated 授权。"""
    return GatedKeyStore(config_dir).revoke(action_id=action_id, repo=repo)


def add_private_action(action_id: str, metadata: dict,
                       config_dir: str = None) -> bool:
    """便捷函数：添加私有动作。"""
    engine = VisibilityEngine(config_dir=config_dir)
    try:
        engine.add_private_action(action_id, metadata)
        return True
    except Exception:
        return False


def list_private_actions(config_dir: str = None) -> List[dict]:
    """便捷函数：列出私有动作。"""
    engine = VisibilityEngine(config_dir=config_dir)
    return engine.list_private_actions()


def create_team(name: str, creator: str, config_dir: str = None) -> TeamConfig:
    """便捷函数：创建团队。"""
    tm = TeamManager(config_dir)
    return tm.create_team(name, creator)


def get_visibility_engine(config_dir: str = None,
                          current_user: str = "") -> VisibilityEngine:
    """便捷函数：获取可见性引擎实例。"""
    return VisibilityEngine(config_dir=config_dir, current_user=current_user)


# ── 动作可见性「真写」实现（CLI 与 MCP 的唯一真源）──
# 动作的可见性只存在于动作文件的 ```json #!cfg``` 块里（executor/installer/quality
# 都读 `action.meta['visibility']`），引擎本身不存这个级别 —— 所以「设置可见性」
# 必须定点改写动作文件。这段逻辑最初写在 cli.py 的 `_write_action_visibility()`，
# 审计发现 MCP 的 `actus_visibility_set` 只校验+回显、**不落盘**（假成功：
# set 报成功、get 读不到）。把实现移到这里，CLI 与 MCP 共用同一份，避免两套分叉。
_CFG_BLOCK_RE = re.compile(r"(```json\s*#!cfg\s*\n)(.*?)(```)", re.DOTALL)


def _set_cfg_scalar(block: str, key: str, value: str):
    """在 cfg JSON 文本里设置/替换一个字符串标量，不动其它内容；失败返回 None。"""
    pattern = re.compile(r'("%s"\s*:\s*)"[^"]*"' % re.escape(key))
    if pattern.search(block):
        return pattern.sub(lambda m: m.group(1) + '"%s"' % value, block, count=1)
    brace = block.find('{')
    if brace < 0:
        return None
    return (block[:brace + 1]
            + '\n  "%s": "%s",' % (key, value)
            + block[brace + 1:])


def _remove_cfg_scalar(block: str, key: str) -> str:
    """从 cfg JSON 文本里删除一个字符串标量成员（连相邻逗号一起处理）。"""
    escaped = re.escape(key)
    for pattern in (r',\s*"%s"\s*:\s*"[^"]*"' % escaped,
                    r'"%s"\s*:\s*"[^"]*"\s*,\s*' % escaped,
                    r'"%s"\s*:\s*"[^"]*"' % escaped):
        match = re.search(pattern, block)
        if match:
            return block[:match.start()] + block[match.end():]
    return block


def write_action_visibility(action_path: str, level: str,
                            team: str = None) -> Tuple[bool, str]:
    """把动作 `#!cfg` 块里的可见性写成 level（team 级同时写团队名）。

    只动 `visibility` / `team` 两个标量，其余内容原样保留。
    **写完立刻重新解析整份动作文件**校验，不通过就把原文写回去并报错 ——
    宁可失败也不留一份解析不了的动作文件（本仓库的 scaffolder 曾整体覆盖过
    动作文件，这里不想重演那次事故）。

    参数:
        action_path: 动作文件路径。
        level: public / unlisted / private / team。
        team: `level == 'team'` 时**必填**的团队名。

    规则（审计裁决：team 级不记团队名 = 规则无法被判定方使用）：
      * `level='team'` 缺 team → 直接失败，不静默写一个"无团队的 team 级动作"；
      * `level='team'` → cfg 里同时落 `"visibility"` 与 `"team"`；
      * 切到 public/unlisted/private → **删掉 cfg 里残留的 `"team"` 键**
        （否则旧团队名留着，将来切回 team 会用到错误的团队）。
    """
    level = (level or '').strip().lower()
    if level not in ('public', 'unlisted', 'private', 'team'):
        return False, f'无效的可见性级别: {level!r}'
    team = (team or '').strip() if team else ''
    if level == 'team' and not team:
        return False, 'team 级别必须提供团队名（否则这条可见性规则无法被判定方使用）'

    try:
        with open(action_path, 'r', encoding='utf-8') as handle:
            original = handle.read()
    except OSError as exc:
        return False, f'读取动作文件失败: {exc}'

    match = _CFG_BLOCK_RE.search(original)
    if match is None:
        return False, '动作文件里找不到 ```json #!cfg``` 元数据块'

    block = match.group(2)
    new_block = _set_cfg_scalar(block, 'visibility', level)
    if new_block is None:
        return False, '#!cfg 块不是 JSON 对象'
    if level == 'team':
        new_block = _set_cfg_scalar(new_block, 'team', team)
        if new_block is None:
            return False, '#!cfg 块不是 JSON 对象'
    else:
        new_block = _remove_cfg_scalar(new_block, 'team')

    updated = original[:match.start(2)] + new_block + original[match.end(2):]
    try:
        with open(action_path, 'w', encoding='utf-8') as handle:
            handle.write(updated)
        from .model import parse_cfg_from_file
        parsed = parse_cfg_from_file(action_path)
        written_level = (parsed.meta.get('visibility') or '').strip().lower()
        if written_level != level:
            raise ValueError('写回后 visibility 校验不一致（期望 %r，实得 %r）'
                             % (level, written_level))
        written_team = (parsed.meta.get('team') or '').strip()
        if level == 'team' and written_team != team:
            raise ValueError('写回后 team 校验不一致（期望 %r，实得 %r）'
                             % (team, written_team))
        if level != 'team' and written_team:
            raise ValueError('切出 team 级别后 cfg 里仍残留 team 键: %r' % written_team)
    except Exception as exc:
        try:
            with open(action_path, 'w', encoding='utf-8') as handle:
                handle.write(original)          # 回滚到原文
        except OSError:
            pass
        return False, f'{type(exc).__name__}: {exc}（已回滚原文件）'
    return True, ''


__all__ = [
    'ALL_VISIBILITIES',
    'AUTH_REQUIRED',
    'GatedKeyStore',
    'INTERNAL_DIR_MARKER',
    'PUBLISHABLE_VISIBILITIES',
    'RegistryConfig',
    'RegistryManager',
    'SecretAuditor',
    'TeamConfig',
    'TeamManager',
    'TeamMember',
    'VISIBILITY_GATED',
    'VISIBILITY_INTERNAL',
    'VISIBILITY_PRIVATE',
    'VISIBILITY_PUBLIC',
    'VISIBILITY_TEAM',
    'VISIBILITY_UNLISTED',
    'VisibilityEngine',
    'add_private_action',
    'check_visibility',
    'create_team',
    'get_visibility_engine',
    'grant_gated_key',
    'is_internal_path',
    'list_private_actions',
    'revoke_gated_key',
    'write_action_visibility',
]
