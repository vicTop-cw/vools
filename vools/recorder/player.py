"""
vools-recorder 回放器
"""
from __future__ import annotations

import logging
import time as _time
import threading
from typing import Optional, List, Callable
from enum import Enum

from .typedefs import ActionType
from .actions import Action, Recording
__all__ = ['log', 'PlaybackState', 'Player']

# 尝试导入 reactive 模块
try:
    from vools.reactive.monitoring.keyboard import KeyboardDispatcher
    from vools.reactive.monitoring.mouse import MouseDispatcher
    from vools.reactive.clipboard import ClipboardDispatcher
    HAS_REACTIVE = True
except ImportError:
    HAS_REACTIVE = False

log = logging.getLogger(__name__)


class PlaybackState(Enum):
    """回放状态"""
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class Player:
    """键鼠操作回放器
    
    将 Recording 对象转换为系统 API 调用，按时间顺序执行。
    
    Args:
        keyboard_dispatcher: 键盘分发器（可选，如果不提供则自动创建）
        mouse_dispatcher: 鼠标分发器（可选，如果不提供则自动创建）
        clipboard_dispatcher: 剪贴板分发器（可选，如果不提供则自动创建）
    
    Example:
        >>> player = Player()
        >>> player.play(recording, speed=1.0)
        >>> # 或者使用上下文管理器
        >>> with Player() as player:
        ...     player.play(recording)
    """
    
    def __init__(
        self,
        keyboard_dispatcher: Optional[Any] = None,
        mouse_dispatcher: Optional[Any] = None,
        clipboard_dispatcher: Optional[Any] = None,
    ):
        if not HAS_REACTIVE:
            raise ImportError("需要安装 vools.reactive 模块")
        
        self._keyboard_dispatcher = keyboard_dispatcher
        self._mouse_dispatcher = mouse_dispatcher
        self._clipboard_dispatcher = clipboard_dispatcher
        
        # 状态管理
        self._state = PlaybackState.IDLE
        self._current_index = 0
        self._actions: List[Action] = []
        self._speed = 1.0
        
        # 线程同步
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()

    def __getstate__(self):
        return {'_state': self._state.value, '_speed': self._speed}
    def __setstate__(self, state):
        self._state = PlaybackState(state['_state']) if isinstance(state['_state'], str) else PlaybackState(state['_state'])
        self._speed = state['_speed']
        self._stop_event = threading.Event()
        self._play_thread = None
        self._key_dispatcher = None
        self._mouse_dispatcher = None
        self._clip_dispatcher = None
        self._play_thread: Optional[threading.Thread] = None
        
        # 回调
        self._on_action: Optional[Callable[[Action, int], None]] = None
        self._on_complete: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[Exception], None]] = None
        
        # 初始化分发器
        self._ensure_dispatchers()
    
    def _ensure_dispatchers(self) -> None:
        """确保分发器已初始化"""
        if self._keyboard_dispatcher is None:
            self._keyboard_dispatcher = KeyboardDispatcher(backend="win32")
            self._own_keyboard = True
        else:
            self._own_keyboard = False
        
        if self._mouse_dispatcher is None:
            self._mouse_dispatcher = MouseDispatcher(backend="win32")
            self._own_mouse = True
        else:
            self._own_mouse = False
        
        if self._clipboard_dispatcher is None:
            self._clipboard_dispatcher = ClipboardDispatcher(backend="auto")
            self._own_clipboard = True
        else:
            self._own_clipboard = False
    
    @property
    def is_playing(self) -> bool:
        """是否正在播放"""
        return self._state == PlaybackState.PLAYING
    
    @property
    def is_paused(self) -> bool:
        """是否暂停"""
        return self._state == PlaybackState.PAUSED
    
    @property
    def state(self) -> PlaybackState:
        """当前状态"""
        return self._state
    
    def set_callbacks(
        self,
        on_action: Optional[Callable[[Action, int], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """设置回调函数"""
        self._on_action = on_action
        self._on_complete = on_complete
        self._on_error = on_error
    
    def _execute_action(self, action: Action) -> None:
        """执行单个动作"""
        try:
            at = action.action_type
            params = action.params
            
            if at == ActionType.KEY_DOWN:
                self._keyboard_dispatcher.press(params.get('key', ''))
            elif at == ActionType.KEY_UP:
                self._keyboard_dispatcher.release(params.get('key', ''))
            elif at == ActionType.KEY_PRESS:
                key = params.get('key', '')
                self._keyboard_dispatcher.press(key)
                _time.sleep(0.01)
                self._keyboard_dispatcher.release(key)
            elif at == ActionType.TYPE:
                self._keyboard_dispatcher.type_text(params.get('text', ''))
            elif at == ActionType.HOTKEY:
                keys = params.get('keys', [])
                if keys:
                    self._keyboard_dispatcher.hotkey(*keys)
            elif at == ActionType.DELAY:
                ms = params.get('ms', 0)
                _time.sleep(ms / 1000.0)
            elif at == ActionType.MOVE_TO:
                x = params.get('x', 0)
                y = params.get('y', 0)
                self._mouse_dispatcher.move_to(x, y)
            elif at == ActionType.MOVE_REL:
                dx = params.get('dx', 0)
                dy = params.get('dy', 0)
                self._mouse_dispatcher.move_relative(dx, dy)
            elif at == ActionType.CLICK:
                button = params.get('button', 'left')
                self._mouse_dispatcher.click(button)
            elif at == ActionType.DBCLICK:
                button = params.get('button', 'left')
                self._mouse_dispatcher.double_click(button)
            elif at == ActionType.MOUSE_DOWN:
                button = params.get('button', 'left')
                self._mouse_dispatcher.mouse_down(button)
            elif at == ActionType.MOUSE_UP:
                button = params.get('button', 'left')
                self._mouse_dispatcher.mouse_up(button)
            elif at == ActionType.WHEEL:
                delta = params.get('delta', 0)
                self._mouse_dispatcher.scroll(delta)
            elif at == ActionType.HWHEEL:
                delta = params.get('delta', 0)
                self._mouse_dispatcher.h_scroll(delta)
            elif at == ActionType.SET_CLIP:
                text = params.get('text', '')
                self._clipboard_dispatcher.set_clipboard(text)
            elif at == ActionType.PASTE:
                self._keyboard_dispatcher.hotkey('Ctrl', 'V')
            
        except Exception as e:
            log.warning(f"执行动作失败 {action}: {e}")
            if self._on_error:
                self._on_error(e)
    
    def _play_loop(self) -> None:
        """回放循环"""
        try:
            self._keyboard_dispatcher.start()
            self._mouse_dispatcher.start()
            self._clipboard_dispatcher.start()
            
            last_timestamp = 0.0
            
            while self._current_index < len(self._actions) and not self._stop_event.is_set():
                # 等待恢复
                self._pause_event.wait()
                
                if self._stop_event.is_set():
                    break
                
                action = self._actions[self._current_index]
                
                # 计算等待时间
                wait_time = (action.timestamp - last_timestamp) / self._speed
                if wait_time > 0:
                    # 使用短睡眠来支持暂停检查
                    end_time = _time.time() + wait_time
                    while _time.time() < end_time:
                        if self._stop_event.is_set():
                            break
                        self._pause_event.wait(timeout=0.05)
                        if self._stop_event.is_set():
                            break
                
                if self._stop_event.is_set():
                    break
                
                # 执行动作
                self._execute_action(action)
                last_timestamp = action.timestamp
                
                if self._on_action:
                    self._on_action(action, self._current_index)
                
                self._current_index += 1
            
        except Exception as e:
            log.error(f"回放出错: {e}")
            if self._on_error:
                self._on_error(e)
        finally:
            self._keyboard_dispatcher.stop()
            self._mouse_dispatcher.stop()
            self._clipboard_dispatcher.stop()
            self._state = PlaybackState.STOPPED
            if self._on_complete:
                self._on_complete()
    
    def play(self, recording: Recording, speed: float = 1.0) -> None:
        """开始回放
        
        Args:
            recording: 录制结果对象
            speed: 播放速度 (0.1 - 10.0, 默认 1.0)
        """
        if self._state == PlaybackState.PLAYING:
            log.warning("已经在播放中")
            return
        
        if not isinstance(recording, Recording):
            raise TypeError("需要传入 Recording 对象")
        
        self._actions = recording.actions
        self._speed = max(0.1, min(10.0, speed))
        self._current_index = 0
        self._state = PlaybackState.PLAYING
        self._pause_event.clear()
        self._stop_event.clear()
        
        # 启动播放线程
        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._play_thread.start()
        
        log.info(f"开始回放，{len(self._actions)} 个动作，速度 {self._speed}x")
    
    def pause(self) -> None:
        """暂停回放"""
        if self._state != PlaybackState.PLAYING:
            return
        
        self._state = PlaybackState.PAUSED
        self._pause_event.clear()
        log.info("暂停回放")
    
    def resume(self) -> None:
        """恢复回放"""
        if self._state != PlaybackState.PAUSED:
            return
        
        self._state = PlaybackState.PLAYING
        self._pause_event.set()
        log.info("恢复回放")
    
    def stop(self) -> None:
        """停止回放"""
        self._stop_event.set()
        self._pause_event.set()  # 确保暂停的线程能退出
        
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.0)
        
        self._state = PlaybackState.STOPPED
        log.info("停止回放")
    
    def __enter__(self) -> Player:
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.stop()
    
    def __del__(self) -> None:
        """析构时清理"""
        try:
            self.stop()
        except Exception:
            pass