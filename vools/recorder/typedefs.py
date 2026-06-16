"""
vools-recorder 类型定义
"""
from __future__ import annotations
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import time as _time
import json

class ActionType(Enum):
    """操作动作类型，参考 Quicker InputScript"""
    # 键盘命令
    KEY_DOWN = "keydown"
    KEY_UP = "keyup"
    KEY_PRESS = "keypress"
    TYPE = "type"           # 输入文本
    HOTKEY = "hotkey"       # 快捷键
    DELAY = "delay"         # 延迟
    
    # 鼠标命令
    MOVE_TO = "moveto"      # 移动到绝对坐标
    MOVE_REL = "move"       # 相对移动
    CLICK = "click"         # 点击
    DBCLICK = "dbclick"     # 双击
    MOUSE_DOWN = "down"     # 按下鼠标键
    MOUSE_UP = "up"         # 抬起鼠标键
    WHEEL = "wheel"         # 垂直滚动
    HWHEEL = "hwheel"       # 水平滚动
    
    # 剪贴板命令
    SET_CLIP = "setclip"    # 设置剪贴板内容
    PASTE = "paste"         # 粘贴
    
    # 组合命令
    REPEAT = "repeat"       # 重复

class MouseButton(Enum):
    """鼠标按键"""
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"
    X1 = "x1"
    X2 = "x2"

# 快捷键修饰符
MOD_SHIFT = 1
MOD_CTRL = 2
MOD_ALT = 4
MOD_WIN = 8