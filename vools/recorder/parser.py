"""
vools-recorder 脚本解析器
"""
from __future__ import annotations

import re
import logging
from typing import List, Optional, Tuple, Dict, Any

from .typedefs import ActionType, MouseButton
from .actions import Action, Recording

log = logging.getLogger(__name__)


class ParserError(Exception):
    """解析错误"""
    pass


class Parser:
    """Quicker InputScript 格式解析器
    
    解析 Quicker InputScript 格式的脚本字符串，转换为 Action 列表。
    
    Example:
        >>> parser = Parser()
        >>> actions = parser.parse('''
        ...     moveto:100,200
        ...     click:left
        ...     type:hello
        ...     delay:1000
        ... ''')
        >>> print(f"解析了 {len(actions)} 个动作")
    """
    
    # 按键名称映射（与 Windows VK_CODE 对应）
    KEY_ALIASES = {
        'enter': 'Enter',
        'return': 'Enter',
        'tab': 'Tab',
        'space': 'Space',
        'escape': 'Escape',
        'esc': 'Escape',
        'backspace': 'Back',
        'bs': 'Back',
        'delete': 'Delete',
        'del': 'Delete',
        'home': 'Home',
        'end': 'End',
        'pageup': 'PageUp',
        'pagedown': 'PageDown',
        'up': 'Up',
        'down': 'Down',
        'left': 'Left',
        'right': 'Right',
        'ctrl': 'Ctrl',
        'control': 'Ctrl',
        'alt': 'Alt',
        'shift': 'Shift',
        'win': 'Win',
        'meta': 'Win',
        'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
        'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8',
        'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
        'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E',
        'f': 'F', 'g': 'G', 'h': 'H', 'i': 'I', 'j': 'J',
        'k': 'K', 'l': 'L', 'm': 'M', 'n': 'N', 'o': 'O',
        'p': 'P', 'q': 'Q', 'r': 'R', 's': 'S', 't': 'T',
        'u': 'U', 'v': 'V', 'w': 'W', 'x': 'X', 'y': 'Y',
        'z': 'Z',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
        '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
    }
    
    # 鼠标按钮别名
    BUTTON_ALIASES = {
        'l': 'left',
        'r': 'right', 
        'm': 'middle',
        'x1': 'x1',
        'x2': 'x2',
    }
    
    def __init__(self):
        pass
    
    def _normalize_key(self, key: str) -> str:
        """规范化按键名称"""
        key_lower = key.lower().strip()
        return self.KEY_ALIASES.get(key_lower, key.capitalize())
    
    def _normalize_button(self, button: str) -> str:
        """规范化鼠标按钮"""
        btn_lower = button.lower().strip()
        return self.BUTTON_ALIASES.get(btn_lower, btn_lower)
    
    def _parse_coordinate(self, coord_str: str) -> Tuple[float, float]:
        """解析坐标字符串，支持百分比形式
        
        Returns:
            (x, y) 元组
        """
        coord_str = coord_str.strip()
        
        # 检查百分比形式
        if '%' in coord_str:
            # moveto:50%,50%
            parts = coord_str.replace('%', '').split(',')
            if len(parts) != 2:
                raise ParserError(f"无效的百分比坐标: {coord_str}")
            try:
                x_pct = float(parts[0].strip())
                y_pct = float(parts[1].strip())
                # 后续在执行时转换为屏幕坐标
                return (x_pct, y_pct)  # 保留百分比标记
            except ValueError:
                raise ParserError(f"无效的百分比值: {coord_str}")
        
        # 普通坐标
        parts = coord_str.split(',')
        if len(parts) != 2:
            raise ParserError(f"无效的坐标: {coord_str}")
        try:
            return (float(parts[0].strip()), float(parts[1].strip()))
        except ValueError:
            raise ParserError(f"无效的坐标值: {coord_str}")
    
    def _parse_hotkey(self, keys_str: str) -> List[str]:
        """解析快捷键字符串
        
        例如: "Ctrl+Shift+A" -> ["Ctrl", "Shift", "A"]
        """
        keys = []
        parts = keys_str.replace(' ', '').split('+')
        for part in parts:
            part = part.strip()
            if part:
                # 数字键特殊处理: D1 -> 1
                if part.startswith('D') and len(part) == 2 and part[1].isdigit():
                    keys.append(part[1])
                else:
                    keys.append(self._normalize_key(part))
        return keys
    
    def _parse_line(self, line: str, timestamp: float) -> Optional[Action]:
        """解析单行脚本
        
        Args:
            line: 脚本行
            timestamp: 相对时间戳（毫秒）
        
        Returns:
            Action 对象或 None（空行/注释）
        """
        line = line.strip()
        
        # 跳过空行和注释
        if not line or line.startswith('//') or line.startswith('#'):
            return None
        
        # 分割命令和参数
        if ':' in line:
            cmd, arg = line.split(':', 1)
            cmd = cmd.strip().lower()
            arg = arg.strip()
        else:
            cmd = line.lower()
            arg = ''
        
        # 解析命令
        if cmd == 'delay':
            # delay:1000
            try:
                ms = int(arg)
            except ValueError:
                raise ParserError(f"无效的延迟值: {arg}")
            return Action(ActionType.DELAY, timestamp, {'ms': ms})
        
        elif cmd == 'keydown':
            # keydown:A 或 keydown:F1
            return Action(ActionType.KEY_DOWN, timestamp, {'key': self._normalize_key(arg)})
        
        elif cmd == 'keyup':
            # keyup:A
            return Action(ActionType.KEY_UP, timestamp, {'key': self._normalize_key(arg)})
        
        elif cmd == 'keypress':
            # keypress:A
            return Action(ActionType.KEY_PRESS, timestamp, {'key': self._normalize_key(arg)})
        
        elif cmd == 'type':
            # type:hello world
            return Action(ActionType.TYPE, timestamp, {'text': arg})
        
        elif cmd == 'sendkeys':
            # sendkeys:{LEFT 2} - 简单实现，只支持基本按键
            # 注意：完整实现需要解析 SendKeys 语法
            match = re.search(r'\{([^}]+)\}', arg)
            if match:
                inner = match.group(1)
                if ' ' in inner:
                    key_name, count = inner.split()
                    try:
                        count = int(count)
                    except ValueError:
                        count = 1
                else:
                    key_name = inner
                    count = 1
                return Action(ActionType.KEY_PRESS, timestamp, {'key': self._normalize_key(key_name), 'repeat': count})
            return Action(ActionType.KEY_PRESS, timestamp, {'key': self._normalize_key(arg)})
        
        elif cmd == 'hotkey':
            # hotkey:Ctrl+S
            keys = self._parse_hotkey(arg)
            return Action(ActionType.HOTKEY, timestamp, {'keys': keys})
        
        elif cmd == 'moveto':
            # moveto:100,200 或 moveto:50%,50%
            x, y = self._parse_coordinate(arg)
            return Action(ActionType.MOVE_TO, timestamp, {'x': x, 'y': y, 'is_percent': '%' in arg})
        
        elif cmd == 'move':
            # move:10,-10
            parts = arg.split(',')
            if len(parts) != 2:
                raise ParserError(f"无效的移动参数: {arg}")
            try:
                dx = float(parts[0].strip())
                dy = float(parts[1].strip())
            except ValueError:
                raise ParserError(f"无效的移动值: {arg}")
            return Action(ActionType.MOVE_REL, timestamp, {'dx': dx, 'dy': dy})
        
        elif cmd == 'click':
            # click:left
            button = self._normalize_button(arg) if arg else 'left'
            return Action(ActionType.CLICK, timestamp, {'button': button})
        
        elif cmd == 'dbclick':
            # dbclick:left
            button = self._normalize_button(arg) if arg else 'left'
            return Action(ActionType.DBCLICK, timestamp, {'button': button})
        
        elif cmd == 'down':
            # down:left
            button = self._normalize_button(arg) if arg else 'left'
            return Action(ActionType.MOUSE_DOWN, timestamp, {'button': button})
        
        elif cmd == 'up':
            # up:left
            button = self._normalize_button(arg) if arg else 'left'
            return Action(ActionType.MOUSE_UP, timestamp, {'button': button})
        
        elif cmd == 'wheel':
            # wheel:3
            try:
                delta = int(arg)
            except ValueError:
                raise ParserError(f"无效的滚动值: {arg}")
            return Action(ActionType.WHEEL, timestamp, {'delta': delta})
        
        elif cmd == 'wheeldelta':
            # wheeldelta:120
            try:
                delta = int(arg) // 120  # 转换为 wheel 的单位
            except ValueError:
                raise ParserError(f"无效的滚动值: {arg}")
            return Action(ActionType.WHEEL, timestamp, {'delta': delta})
        
        elif cmd == 'hwheel':
            # hwheel:-2
            try:
                delta = int(arg)
            except ValueError:
                raise ParserError(f"无效的滚动值: {arg}")
            return Action(ActionType.HWHEEL, timestamp, {'delta': delta})
        
        elif cmd == 'setclip':
            # setclip:hello world
            return Action(ActionType.SET_CLIP, timestamp, {'text': arg})
        
        elif cmd == 'paste':
            # paste
            return Action(ActionType.PASTE, timestamp, {})
        
        elif cmd == 'pastefile':
            # pastefile:path (简化处理)
            return Action(ActionType.SET_CLIP, timestamp, {'text': arg, 'is_file': True})
        
        elif cmd == 'pasteimage':
            # pasteimage:path (简化处理)
            return Action(ActionType.SET_CLIP, timestamp, {'text': arg, 'is_image': True})
        
        elif cmd == 'repeat':
            # repeat:3
            try:
                count = int(arg)
            except ValueError:
                raise ParserError(f"无效的重复次数: {arg}")
            return Action(ActionType.REPEAT, timestamp, {'count': count})
        
        else:
            log.warning(f"未知命令: {cmd}")
            return None
    
    def parse(self, script: str, start_timestamp: float = 0.0) -> List[Action]:
        """解析 Quicker InputScript 格式字符串
        
        Args:
            script: 脚本内容
            start_timestamp: 起始时间戳（毫秒）
        
        Returns:
            Action 列表
        
        Raises:
            ParserError: 解析错误
        """
        actions = []
        current_time = start_timestamp
        last_action_time = start_timestamp
        
        lines = script.replace(';;', '\n').split('\n')
        
        for line in lines:
            action = self._parse_line(line, current_time)
            if action:
                actions.append(action)
                # 更新时间戳（基于前一个动作的时间）
                if action.timestamp > last_action_time:
                    last_action_time = action.timestamp
        
        return actions
    
    def parse_file(self, path: str, encoding: str = 'utf-8') -> List[Action]:
        """从文件解析脚本
        
        Args:
            path: 文件路径
            encoding: 文件编码
        
        Returns:
            Action 列表
        """
        with open(path, 'r', encoding=encoding) as f:
            content = f.read()
        return self.parse(content)
    
    def to_script(self, actions: List[Action]) -> str:
        """将 Action 列表转换为 Quicker InputScript 格式
        
        Args:
            actions: Action 列表
        
        Returns:
            Quicker InputScript 格式的字符串
        """
        lines = []
        
        for action in actions:
            at = action.action_type
            params = action.params
            
            if at == ActionType.DELAY:
                ms = params.get('ms', 0)
                lines.append(f"delay:{ms}")
            elif at == ActionType.KEY_DOWN:
                lines.append(f"keydown:{params.get('key', '')}")
            elif at == ActionType.KEY_UP:
                lines.append(f"keyup:{params.get('key', '')}")
            elif at == ActionType.KEY_PRESS:
                lines.append(f"keypress:{params.get('key', '')}")
            elif at == ActionType.TYPE:
                lines.append(f"type:{params.get('text', '')}")
            elif at == ActionType.HOTKEY:
                keys = params.get('keys', [])
                lines.append(f"hotkey:{'+'.join(keys)}")
            elif at == ActionType.MOVE_TO:
                x, y = params.get('x', 0), params.get('y', 0)
                if params.get('is_percent'):
                    lines.append(f"moveto:{x}%,{y}%")
                else:
                    lines.append(f"moveto:{int(x)},{int(y)}")
            elif at == ActionType.MOVE_REL:
                dx, dy = params.get('dx', 0), params.get('dy', 0)
                lines.append(f"move:{int(dx)},{int(dy)}")
            elif at == ActionType.CLICK:
                lines.append(f"click:{params.get('button', 'left')}")
            elif at == ActionType.DBCLICK:
                lines.append(f"dbclick:{params.get('button', 'left')}")
            elif at == ActionType.MOUSE_DOWN:
                lines.append(f"down:{params.get('button', 'left')}")
            elif at == ActionType.MOUSE_UP:
                lines.append(f"up:{params.get('button', 'left')}")
            elif at == ActionType.WHEEL:
                lines.append(f"wheel:{params.get('delta', 0)}")
            elif at == ActionType.HWHEEL:
                lines.append(f"hwheel:{params.get('delta', 0)}")
            elif at == ActionType.SET_CLIP:
                lines.append(f"setclip:{params.get('text', '')}")
            elif at == ActionType.PASTE:
                lines.append("paste")
            elif at == ActionType.REPEAT:
                lines.append(f"repeat:{params.get('count', 1)}")
        
        return '\n'.join(lines)
    
    def recording_to_script(self, recording: Recording) -> str:
        """将 Recording 转换为 Quicker InputScript 格式
        
        Args:
            recording: Recording 对象
        
        Returns:
            Quicker InputScript 格式的字符串
        """
        return self.to_script(recording.actions)