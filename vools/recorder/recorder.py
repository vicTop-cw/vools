"""
vools-recorder 录制器
"""
from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from threading import Event

from .typedefs import ActionType, MOD_SHIFT, MOD_CTRL, MOD_ALT, MOD_WIN
from .actions import Action, Recording
__all__ = ['log', 'Recorder']

# 尝试导入 reactive 模块
try:
    from vools.reactive.monitoring.keyboard import KeySubject, KeyEventType
    from vools.reactive.monitoring.mouse import MouseSubject, MouseEventType
    from vools.reactive.clipboard import ClipSubject as ClipboardSubject, ClipChangeType
    HAS_REACTIVE = True
except ImportError:
    HAS_REACTIVE = False

log = logging.getLogger(__name__)


class Recorder:
    """键鼠操作录制器
    
    同时监听键盘、鼠标、剪贴板事件，记录为结构化的 Action 序列。
    
    Args:
        record_keyboard: 是否录制键盘事件 (默认 True)
        record_mouse: 是否录制鼠标事件 (默认 True)  
        record_clipboard: 是否录制剪贴板事件 (默认 True)
        deduplicate_interval: 相同事件去重间隔（秒，默认 0.05）
        mouse_move_threshold: 鼠标移动事件触发阈值（像素，默认 5）
    
    Example:
        >>> recorder = Recorder()
        >>> recorder.start()
        >>> # 执行一些键鼠操作...
        >>> recording = recorder.stop()
        >>> print(f"录制了 {len(recording)} 个动作")
        >>> recording.to_yaml_file("output.yaml")
    """
    
    def __init__(
        self,
        record_keyboard: bool = True,
        record_mouse: bool = True,
        record_clipboard: bool = True,
        deduplicate_interval: float = 0.05,
        mouse_move_threshold: float = 5.0,
    ):
        if not HAS_REACTIVE:
            raise ImportError("需要安装 vools.reactive 模块，请确保 vools 包完整安装")
        
        self._record_keyboard = record_keyboard
        self._record_mouse = record_mouse
        self._record_clipboard = record_clipboard
        self._deduplicate_interval = deduplicate_interval
        self._mouse_move_threshold = mouse_move_threshold
        
        # 录制状态
        self._is_recording = False
        self._start_time: Optional[datetime] = None
        self._actions: List[Action] = []
        
        # 订阅管理
        self._key_subscription = None
        self._mouse_subscription = None
        self._clip_subscription = None
        self._key_subject: Optional[KeySubject] = None
        self._mouse_subject: Optional[MouseSubject] = None
        self._clip_subject: Optional[ClipboardSubject] = None
        
        # 去重状态
        self._last_key_event: Dict[str, Any] = {}
        self._last_mouse_pos: Optional[tuple] = None
        
        # 录制钩子（可选的回调）
        self._on_action: Optional[Callable[[Action], None]] = None
    
    @property
    def is_recording(self) -> bool:
        """是否正在录制"""
        return self._is_recording
    
    def set_action_hook(self, callback: Callable[[Action], None]) -> None:
        """设置动作回调钩子，每次录制到动作时调用"""
        self._on_action = callback
    
    def _relative_time(self) -> float:
        """获取相对于录制开始的时间（毫秒）"""
        if self._start_time is None:
            return 0.0
        delta = datetime.now() - self._start_time
        return delta.total_seconds() * 1000
    
    def _add_action(self, action_type: ActionType, **params) -> None:
        """添加动作"""
        if not self._is_recording:
            return
        
        action = Action(
            action_type=action_type,
            timestamp=self._relative_time(),
            params=params,
        )
        self._actions.append(action)
        
        if self._on_action:
            self._on_action(action)
    
    def _should_emit_key_event(self, key: str, event_type: str) -> bool:
        """检查是否应该发射键盘事件（去重）"""
        key_id = f"{key}:{event_type}"
        now = _time.time()
        
        if key_id in self._last_key_event:
            last_time = self._last_key_event[key_id]
            if now - last_time < self._deduplicate_interval:
                return False
        
        self._last_key_event[key_id] = now
        return True
    
    def _should_emit_mouse_move(self, x: float, y: float) -> bool:
        """检查是否应该发射鼠标移动事件（去重+阈值）"""
        if self._last_mouse_pos is None:
            self._last_mouse_pos = (x, y)
            return True
        
        # 计算距离
        dx = x - self._last_mouse_pos[0]
        dy = y - self._last_mouse_pos[1]
        distance = (dx * dx + dy * dy) ** 0.5
        
        now = _time.time()
        
        # 检查时间间隔
        if hasattr(self, '_last_mouse_time'):
            if now - self._last_mouse_time < self._deduplicate_interval:
                if distance < self._mouse_move_threshold * 2:
                    return False
        
        # 检查距离阈值
        if distance < self._mouse_move_threshold:
            return False
        
        self._last_mouse_pos = (x, y)
        self._last_mouse_time = now
        return True
    
    def _on_key_event(self, key_data: Any) -> None:
        """处理键盘事件"""
        try:
            # 检查去重
            if not self._should_emit_key_event(key_data.key_name, str(key_data.event_type)):
                return
            
            if key_data.event_type == KeyEventType.KEY_DOWN:
                # 检查是否有修饰键
                modifiers = []
                if key_data.modifiers & MOD_SHIFT:
                    modifiers.append('Shift')
                if key_data.modifiers & MOD_CTRL:
                    modifiers.append('Ctrl')
                if key_data.modifiers & MOD_ALT:
                    modifiers.append('Alt')
                if key_data.modifiers & MOD_WIN:
                    modifiers.append('Win')
                
                if modifiers:
                    # 快捷键
                    self._add_action(
                        ActionType.HOTKEY,
                        keys=[*modifiers, key_data.key_name],
                        key_code=key_data.key_code,
                    )
                else:
                    self._add_action(
                        ActionType.KEY_DOWN,
                        key=key_data.key_name,
                        key_code=key_data.key_code,
                    )
            elif key_data.event_type == KeyEventType.KEY_UP:
                self._add_action(
                    ActionType.KEY_UP,
                    key=key_data.key_name,
                    key_code=key_data.key_code,
                )
        except Exception as e:
            log.warning(f"处理键盘事件失败: {e}")
    
    def _on_mouse_event(self, mouse_data: Any) -> None:
        """处理鼠标事件"""
        try:
            et = mouse_data.event_type
            
            if et == MouseEventType.MOVE:
                if self._should_emit_mouse_move(mouse_data.x, mouse_data.y):
                    self._add_action(
                        ActionType.MOVE_TO,
                        x=int(mouse_data.x),
                        y=int(mouse_data.y),
                    )
            elif et == MouseEventType.LEFT_DOWN:
                self._add_action(ActionType.MOUSE_DOWN, button='left')
            elif et == MouseEventType.LEFT_UP:
                self._add_action(ActionType.MOUSE_UP, button='left')
            elif et == MouseEventType.RIGHT_DOWN:
                self._add_action(ActionType.MOUSE_DOWN, button='right')
            elif et == MouseEventType.RIGHT_UP:
                self._add_action(ActionType.MOUSE_UP, button='right')
            elif et == MouseEventType.MIDDLE_DOWN:
                self._add_action(ActionType.MOUSE_DOWN, button='middle')
            elif et == MouseEventType.MIDDLE_UP:
                self._add_action(ActionType.MOUSE_UP, button='middle')
            elif et == MouseEventType.SCROLL:
                self._add_action(ActionType.WHEEL, delta=int(mouse_data.delta))
        except Exception as e:
            log.warning(f"处理鼠标事件失败: {e}")
    
    def _on_clip_event(self, clip_data: Any) -> None:
        """处理剪贴板事件"""
        try:
            if clip_data.change_type == ClipChangeType.TEXT:
                text = clip_data.text
                if text:
                    self._add_action(ActionType.SET_CLIP, text=text)
            elif clip_data.change_type == ClipChangeType.FILES:
                if clip_data.files:
                    # 第一个文件作为示例
                    self._add_action(ActionType.SET_CLIP, text=clip_data.files[0], is_file=True)
        except Exception as e:
            log.warning(f"处理剪贴板事件失败: {e}")
    
    def start(self) -> None:
        """开始录制"""
        if self._is_recording:
            log.warning("已经在录制中")
            return
        
        self._is_recording = True
        self._start_time = datetime.now()
        self._actions = []
        self._last_key_event = {}
        self._last_mouse_pos = None
        
        # 创建并启动 Subject
        if self._record_keyboard:
            self._key_subject = KeySubject(backend="auto", filter_self=False)
            self._key_subscription = self._key_subject.subscribe(on_next=self._on_key_event)
            self._key_subject.start()
        
        if self._record_mouse:
            self._mouse_subject = MouseSubject(backend="auto", filter_self=False)
            self._mouse_subscription = self._mouse_subject.subscribe(on_next=self._on_mouse_event)
            self._mouse_subject.start()
        
        if self._record_clipboard:
            self._clip_subject = ClipboardSubject(backend="auto", filter_self=False)
            self._clip_subscription = self._clip_subject.subscribe(on_next=self._on_clip_event)
            self._clip_subject.start()
        
        log.info("开始录制")
    
    def stop(self) -> Recording:
        """停止录制并返回 Recording 对象"""
        if not self._is_recording:
            log.warning("未在录制中")
            return Recording(
                start_time=datetime.now(),
                end_time=datetime.now(),
                actions=[],
            )
        
        # 停止所有 Subject
        if self._key_subject:
            self._key_subject.stop()
        if self._mouse_subject:
            self._mouse_subject.stop()
        if self._clip_subject:
            self._clip_subject.stop()
        
        # 取消订阅
        if self._key_subscription:
            self._key_subscription.unsubscribe()
        if self._mouse_subscription:
            self._mouse_subscription.unsubscribe()
        if self._clip_subscription:
            self._clip_subscription.unsubscribe()
        
        self._is_recording = False
        end_time = datetime.now()
        
        # 优化动作序列（合并相邻的 delay）
        self._actions = self._optimize_actions(self._actions)
        
        recording = Recording(
            start_time=self._start_time,
            end_time=end_time,
            actions=self._actions,
            tags={'source': 'vools-recorder'},
        )
        
        log.info(f"停止录制，{len(recording)} 个动作，{recording.duration:.1f}ms")
        return recording
    
    def _optimize_actions(self, actions: List[Action]) -> List[Action]:
        """优化动作序列：合并相邻的 delay，移除过短的间隔"""
        if not actions:
            return actions
        
        optimized = []
        pending_delay = 0.0
        
        for action in actions:
            if action.action_type == ActionType.DELAY:
                pending_delay += action.params.get('ms', 0)
            else:
                # 如果有pending的delay，添加它
                if pending_delay > 10:  # 只保留超过10ms的delay
                    optimized.append(Action(
                        action_type=ActionType.DELAY,
                        timestamp=action.timestamp - pending_delay,
                        params={'ms': int(pending_delay)},
                    ))
                pending_delay = 0
                optimized.append(action)
        
        return optimized
    
    def __enter__(self) -> Recorder:
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        if self._is_recording:
            self.stop()
    

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def record(self) -> Recording:
        """录制一段操作并返回 Recording（便捷方法）"""
        self.start()
        try:
            input("按 Enter 停止录制...")
        except KeyboardInterrupt:
            pass
        return self.stop()