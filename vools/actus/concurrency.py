"""concurrency.py — 动作并发执行控制器。"""

import threading
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class InstanceInfo:
    exec_id: str
    action_id: str
    params: dict
    started_at: float
    thread_id: int


@dataclass
class ActionSlot:
    action_id: str
    max_instances: int  # 0=无上限
    running: list = field(default_factory=list)


class ConcurrencyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._actions: Dict[str, ActionSlot] = {}
        self._meta_lock = threading.Lock()

    @classmethod
    def reset(cls):
        global _manager
        with cls._lock:
            cls._instance = None
            _manager = ConcurrencyManager()

    def register_action(self, action_id: str, max_instances: int = 0):
        with self._meta_lock:
            if action_id not in self._actions:
                self._actions[action_id] = ActionSlot(action_id=action_id, max_instances=max_instances)

    def unregister_action(self, action_id: str):
        with self._meta_lock:
            self._actions.pop(action_id, None)

    def can_run(self, action_id: str) -> Tuple[bool, str]:
        with self._meta_lock:
            slot = self._actions.get(action_id)
            if slot is None or slot.max_instances == 0:
                return True, "允许"
            current = len(slot.running)
            if current < slot.max_instances:
                return True, f"当前 {current}/{slot.max_instances}"
            return False, f"已达上限 {slot.max_instances}"

    def acquire_slot(self, action_id: str, exec_id: str, params: dict, timeout: float = 30.0) -> Tuple[bool, str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._meta_lock:
                slot = self._actions.get(action_id)
                if slot is None or slot.max_instances == 0:
                    if slot:
                        slot.running.append(InstanceInfo(exec_id, action_id, params, time.time(), threading.current_thread().ident))
                    return True, "无上限"
                if len(slot.running) < slot.max_instances:
                    slot.running.append(InstanceInfo(exec_id, action_id, params, time.time(), threading.current_thread().ident))
                    return True, f"获取成功 {len(slot.running)}/{slot.max_instances}"
            time.sleep(0.05)
        with self._meta_lock:
            slot = self._actions.get(action_id)
            current = len(slot.running) if slot else 0
        return False, f"等待超时 ({timeout}s)，当前 {current}"

    def release_slot(self, action_id: str, exec_id: str):
        with self._meta_lock:
            slot = self._actions.get(action_id)
            if slot is None:
                return
            slot.running = [r for r in slot.running if r.exec_id != exec_id]

    def get_running_count(self, action_id: str) -> int:
        with self._meta_lock:
            slot = self._actions.get(action_id)
            return len(slot.running) if slot else 0

    def get_waiting_count(self, action_id: str) -> int:
        return 0

    def get_running_instances(self, action_id: str) -> list:
        with self._meta_lock:
            slot = self._actions.get(action_id)
            if slot is None:
                return []
            return [{"exec_id": r.exec_id, "started_at": r.started_at, "duration": time.time() - r.started_at, "thread_id": r.thread_id} for r in slot.running]

    def get_status(self, action_id: str = None) -> dict:
        with self._meta_lock:
            if action_id:
                slot = self._actions.get(action_id)
                if slot is None:
                    return {"action_id": action_id, "registered": False}
                return {"action_id": action_id, "registered": True, "max_instances": slot.max_instances, "running": len(slot.running), "instances": [{"exec_id": r.exec_id, "started_at": r.started_at, "duration": time.time() - r.started_at} for r in slot.running]}
            return {"actions": {aid: {"max_instances": s.max_instances, "running": len(s.running)} for aid, s in self._actions.items()}, "total_registered": len(self._actions)}

    def set_max_instances(self, action_id: str, max_instances: int):
        with self._meta_lock:
            if action_id in self._actions:
                self._actions[action_id].max_instances = max_instances

    def is_registered(self, action_id: str) -> bool:
        with self._meta_lock:
            return action_id in self._actions


_manager = ConcurrencyManager()


def get_manager() -> ConcurrencyManager:
    return _manager


__all__ = [
    'ActionSlot',
    'ConcurrencyManager',
    'InstanceInfo',
    'get_manager'
]
