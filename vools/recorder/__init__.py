"""
vools-recorder: 键鼠操作录制与回放模块

提供操作录制和回放功能，支持 Quicker InputScript 格式。

主要类:
    Recorder: 录制器，用于录制键鼠操作
    Player: 回放器，用于回放录制的操作
    Parser: 脚本解析器，用于解析 Quicker InputScript 格式
    RecorderGUI: GUI 录制工具

Example:
    # 录制操作
    from vools.recorder import Recorder, Recording
    
    recorder = Recorder()
    recorder.start()
    # 执行一些键鼠操作...
    recording = recorder.stop()
    recording.to_yaml_file("output.yaml")
    
    # 回放操作
    from vools.recorder import Player
    
    player = Player()
    player.play(recording)
    
    # 解析 Quicker 脚本
    from vools.recorder import Parser
    
    parser = Parser()
    actions = parser.parse("moveto:100,200\nclick:left\ntype:hello")
    
    # 使用 GUI
    from vools.recorder import RecorderGUI
    
    gui = RecorderGUI()
    gui.run()
"""
from __future__ import annotations

# 修复：项目根目录的 datetime/ 子包遮蔽标准库 datetime
import sys as _sys, os as _os
_saved_sp = list(_sys.path)
_sys.path = [p for p in _sys.path if not (
    _os.path.isdir(_os.path.join(p or '.', 'datetime'))
)]

from .typedefs import (
    ActionType,
    MouseButton,
    MOD_SHIFT,
    MOD_CTRL,
    MOD_ALT,
    MOD_WIN,
)

from .actions import (
    Action,
    Recording,
)

from .recorder import Recorder
from .player import Player, PlaybackState
from .parser import Parser, ParserError

# GUI 工具（可选导入）
try:
    from .gui import RecorderGUI
    HAS_GUI = True
except ImportError:
    HAS_GUI = False
    RecorderGUI = None

# 版本信息
__version__ = "0.1.0"

# 恢复 sys.path（后续其他模块可能依赖原始路径顺序）
_sys.path = _saved_sp

# 公开导出
__all__ = [
    # 版本
    "__version__",
    # 类型
    "ActionType",
    "MouseButton",
    # 数据类
    "Action",
    "Recording",
    # 录制器
    "Recorder",
    # 回放器
    "Player",
    "PlaybackState",
    # 解析器
    "Parser",
    "ParserError",
    # GUI
    "RecorderGUI",
    "HAS_GUI",
    # 常量
    "MOD_SHIFT",
    "MOD_CTRL",
    "MOD_ALT",
    "MOD_WIN",
]
