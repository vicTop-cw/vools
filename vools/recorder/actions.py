"""
vools-recorder 动作和录制结果定义
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import time as _time

from .typedefs import ActionType, MouseButton
__all__ = ['Action', 'Recording']

@dataclass
class Action:
    """单个操作动作"""
    action_type: ActionType
    timestamp: float  # 相对于录制开始的时间（毫秒）
    params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'action_type': self.action_type.value,
            'timestamp': self.timestamp,
            'params': self.params,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Action:
        """从字典创建"""
        return cls(
            action_type=ActionType(data['action_type']),
            timestamp=data['timestamp'],
            params=data.get('params', {}),
        )
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> Action:
        """从 JSON 字符串创建"""
        return cls.from_dict(json.loads(json_str))
    
    def __repr__(self) -> str:
        params_str = ', '.join(f'{k}={v!r}' for k, v in self.params.items())
        return f"Action({self.action_type.value}, {self.timestamp:.1f}ms, {params_str})"


@dataclass
class Recording:
    """录制结果"""
    start_time: datetime
    end_time: datetime
    actions: List[Action] = field(default_factory=list)
    tags: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        """录制时长（毫秒）"""
        if self.actions:
            return self.actions[-1].timestamp
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_ms': self.duration,
            'actions': [a.to_dict() for a in self.actions],
            'tags': self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Recording:
        """从字典创建"""
        return cls(
            start_time=datetime.fromisoformat(data['start_time']),
            end_time=datetime.fromisoformat(data['end_time']),
            actions=[Action.from_dict(a) for a in data.get('actions', [])],
            tags=data.get('tags', {}),
        )
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> Recording:
        """从 JSON 字符串创建"""
        return cls.from_dict(json.loads(json_str))
    
    def to_yaml(self) -> str:
        """转换为 YAML 字符串"""
        import yaml
        return yaml.dump(self.to_dict(), allow_unicode=True, default_flow_style=False)
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> Recording:
        """从 YAML 字符串创建"""
        import yaml
        return cls.from_dict(yaml.safe_load(yaml_str))
    
    @classmethod
    def from_yaml_file(cls, path: str) -> Recording:
        """从 YAML 文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_yaml(f.read())
    
    def to_yaml_file(self, path: str) -> None:
        """保存为 YAML 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_yaml())
    
    @classmethod
    def from_json_file(cls, path: str) -> Recording:
        """从 JSON 文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_json(f.read())
    
    def to_json_file(self, path: str) -> None:
        """保存为 JSON 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
    
    def to_quicker_script(self) -> str:
        """生成 Quicker InputScript 格式"""
        lines = []
        for action in self.actions:
            cmd = action.action_type.value
            params = action.params
            
            if cmd == 'delay':
                lines.append(f"delay:{params.get('ms', 0)}")
            elif cmd == 'keydown':
                lines.append(f"keydown:{params.get('key', '')}")
            elif cmd == 'keyup':
                lines.append(f"keyup:{params.get('key', '')}")
            elif cmd == 'keypress':
                lines.append(f"keypress:{params.get('key', '')}")
            elif cmd == 'type':
                lines.append(f"type:{params.get('text', '')}")
            elif cmd == 'hotkey':
                keys = params.get('keys', [])
                lines.append(f"hotkey:{'+'.join(keys)}")
            elif cmd == 'moveto':
                x, y = params.get('x', 0), params.get('y', 0)
                lines.append(f"moveto:{x},{y}")
            elif cmd == 'move':
                dx, dy = params.get('dx', 0), params.get('dy', 0)
                lines.append(f"move:{dx},{dy}")
            elif cmd == 'click':
                lines.append(f"click:{params.get('button', 'left')}")
            elif cmd == 'dbclick':
                lines.append(f"dbclick:{params.get('button', 'left')}")
            elif cmd == 'down':
                lines.append(f"down:{params.get('button', 'left')}")
            elif cmd == 'up':
                lines.append(f"up:{params.get('button', 'left')}")
            elif cmd == 'wheel':
                lines.append(f"wheel:{params.get('delta', 0)}")
            elif cmd == 'hwheel':
                lines.append(f"hwheel:{params.get('delta', 0)}")
            elif cmd == 'setclip':
                lines.append(f"setclip:{params.get('text', '')}")
            elif cmd == 'paste':
                lines.append("paste")
        
        return '\n'.join(lines)
    
    def __repr__(self) -> str:
        return f"Recording({len(self.actions)} actions, {self.duration:.1f}ms)"
    
    def __len__(self) -> int:
        return len(self.actions)