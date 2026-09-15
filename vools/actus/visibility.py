"""visibility.py —— 私有动作与可见性控制引擎（docs/24 §F0-1）。

支持：
- 四级可见性：public / unlisted / private / team
- 多注册表管理（公共/团队/个人/自定义）
- 团队成员管理
- 安装时的可见性检查
- 私有动作执行隔离
- 密钥使用审计
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ── 可见性级别 ──

VISIBILITY_PUBLIC = "public"
VISIBILITY_UNLISTED = "unlisted"
VISIBILITY_PRIVATE = "private"
VISIBILITY_TEAM = "team"

ALL_VISIBILITIES = [VISIBILITY_PUBLIC, VISIBILITY_UNLISTED, VISIBILITY_PRIVATE, VISIBILITY_TEAM]


# ── 数据结构 ──

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
        return cls(
            name=d.get("name", ""),
            url=d.get("url", ""),
            registry_type=d.get("type", "http"),
            branch=d.get("branch", "main"),
            auth=d.get("auth", ""),
            priority=d.get("priority", 0),
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
        return cls(
            user_id=d.get("id", ""),
            role=d.get("role", "member"),
            public_key=d.get("public_key", ""),
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
        members = [TeamMember.from_dict(m) for m in d.get("members", [])]
        return cls(
            name=d.get("team", ""),
            members=members,
            default_trust=d.get("default_trust", "community"),
            require_signature=d.get("require_signature", True),
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

    def load_team(self, team_name: str) -> Optional[TeamConfig]:
        """加载团队配置。"""
        team_file = os.path.join(self._teams_dir, f"{team_name}.json")
        if os.path.isfile(team_file):
            try:
                with open(team_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                team = TeamConfig.from_dict(data)
                self._teams[team_name] = team
                return team
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def save_team(self, team: TeamConfig):
        """保存团队配置。"""
        os.makedirs(self._teams_dir, exist_ok=True)
        team_file = os.path.join(self._teams_dir, f"{team.name}.json")
        with open(team_file, "w", encoding="utf-8") as f:
            json.dump(team.to_dict(), f, ensure_ascii=False, indent=2)
        self._teams[team.name] = team

    def create_team(self, name: str, creator_user_id: str) -> TeamConfig:
        """创建团队。"""
        team = TeamConfig(name=name, members=[TeamMember(user_id=creator_user_id, role="admin")])
        self.save_team(team)
        return team

    def delete_team(self, name: str):
        """删除团队。"""
        self._teams.pop(name, None)
        team_file = os.path.join(self._teams_dir, f"{name}.json")
        if os.path.isfile(team_file):
            os.remove(team_file)

    def add_member(self, team_name: str, user_id: str, role: str = "member",
                   public_key: str = "") -> bool:
        """添加团队成员。"""
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
        """列出所有团队。"""
        if not os.path.isdir(self._teams_dir):
            return []
        teams = []
        for f in os.listdir(self._teams_dir):
            if f.endswith(".json"):
                teams.append(f[:-5])
        return sorted(teams)


# ── 可见性控制引擎 ──

class VisibilityEngine:
    """可见性控制引擎。

    核心职责：
    - 检查动作的可见性级别
    - 验证用户是否有权限访问/安装/执行动作
    - 管理私有动作列表
    """

    def __init__(self, config_dir: str = None, current_user: str = ""):
        self._config_dir = config_dir or os.path.join(os.path.expanduser("~"), ".actus")
        self._current_user = current_user or os.environ.get("ACTUS_USER", os.getlogin() if hasattr(os, "getlogin") else "default")
        self._registry_manager = RegistryManager(config_dir)
        self._team_manager = TeamManager(config_dir)
        self._private_index_file = os.path.join(self._config_dir, "private", "index.json")
        self._private_actions: Dict[str, dict] = {}
        self._load_private_index()

    @property
    def current_user(self) -> str:
        return self._current_user

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
        """添加私有动作到索引。"""
        self._private_actions[action_id] = {
            **metadata,
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
                         expected_user: str = None) -> Tuple[bool, str]:
        """检查用户是否有权限访问该可见性级别的动作。

        参数:
            action_id: 动作 id。
            visibility: 可见性级别。
            expected_user: 期望的用户（默认当前用户）。

        返回:
            (是否允许, 拒绝原因)
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
            if author and author != user:
                return False, f"Action '{action_id}' is private (author: {author})"
            return True, ""

        if visibility == VISIBILITY_TEAM:
            # 需要检查团队
            team_name = action.get("team", "") if (action := self._find_action(action_id)) else ""
            if not team_name:
                return False, f"No team associated with action: {action_id}"
            team = self._team_manager.get_team(team_name)
            if not team:
                return False, f"Team not found: {team_name}"
            if not team.is_member(user):
                return False, f"User '{user}' is not a member of team '{team_name}'"
            return True, ""

        return False, f"Unknown visibility level: {visibility}"

    def _find_action(self, action_id: str) -> Optional[dict]:
        """在所有注册表中查找动作。"""
        # 先检查私有索引
        if action_id in self._private_actions:
            return self._private_actions[action_id]
        return None

    def can_install(self, action_id: str, visibility: str,
                    registry_name: str = "public") -> Tuple[bool, str]:
        """检查是否允许安装动作。"""
        if visibility == VISIBILITY_PRIVATE:
            return self.check_visibility(action_id, visibility)
        return True, ""

    def can_execute(self, action_id: str, visibility: str) -> Tuple[bool, str]:
        """检查是否允许执行动作。"""
        return self.check_visibility(action_id, visibility)

    # ── 注册表代理 ──

    @property
    def registry(self) -> RegistryManager:
        return self._registry_manager

    @property
    def teams(self) -> TeamManager:
        return self._team_manager

    # ── 综合权限查询 ──

    def get_action_permissions(self, action_id: str,
                               visibility: str) -> dict:
        """获取动作的综合权限信息。"""
        can_view = False
        can_install = False
        can_execute = False

        if visibility == VISIBILITY_PUBLIC:
            can_view = can_install = can_execute = True
        elif visibility == VISIBILITY_UNLISTED:
            can_view = can_install = can_execute = True
        elif visibility == VISIBILITY_PRIVATE:
            ok, _ = self.check_visibility(action_id, visibility)
            can_view = can_install = can_execute = ok
        elif visibility == VISIBILITY_TEAM:
            ok, _ = self.check_visibility(action_id, visibility)
            can_view = can_install = can_execute = ok

        return {
            "action_id": action_id,
            "visibility": visibility,
            "current_user": self._current_user,
            "can_view": can_view,
            "can_install": can_install,
            "can_execute": can_execute,
        }


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


# ── 便捷函数 ──

def check_visibility(action_id: str, visibility: str,
                     current_user: str = "") -> Tuple[bool, str]:
    """便捷函数：检查可见性。"""
    engine = VisibilityEngine(current_user=current_user)
    return engine.check_visibility(action_id, visibility)


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


__all__ = [
    'ALL_VISIBILITIES',
    'RegistryConfig',
    'RegistryManager',
    'SecretAuditor',
    'TeamConfig',
    'TeamManager',
    'TeamMember',
    'VISIBILITY_PRIVATE',
    'VISIBILITY_PUBLIC',
    'VISIBILITY_TEAM',
    'VISIBILITY_UNLISTED',
    'VisibilityEngine',
    'add_private_action',
    'check_visibility',
    'create_team',
    'get_visibility_engine',
    'list_private_actions'
]
