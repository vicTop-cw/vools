"""Mouse simulator subprocess for monitoring tests.

This module simulates mouse operations (move, click, scroll) controlled
by a JSON control file, using Windows user32 API via ctypes.

Usage:
    python mouse_sim.py <control_file> <log_file>
"""

from __future__ import absolute_import

import json
import sys
import time
from ctypes import windll, c_long, c_ulong, Structure, POINTER, byref
from typing import Any, Dict, List

# Windows API constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800


# ============================================================================
# Windows API Setup
# ============================================================================

# Define POINT structure for GetCursorPos
class POINT(Structure):
    _fields_ = [
        ('x', c_long),
        ('y', c_long),
    ]


def get_cursor_pos() -> tuple:
    """Get current cursor position.

    Returns:
        Tuple of (x, y) coordinates.
    """
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return (pt.x, pt.y)


def set_cursor_pos(x: int, y: int) -> bool:
    """Set cursor position.

    Args:
        x: X coordinate.
        y: Y coordinate.

    Returns:
        True if successful.
    """
    return windll.user32.SetCursorPos(x, y) != 0


def mouse_event(dw_flags: int, dx: int = 0, dy: int = 0, dw_data: int = 0, dw_extra_info: int = 0) -> None:
    """Simulate mouse event.

    Args:
        dw_flags: Event flags (e.g., MOUSEEVENTF_LEFTDOWN).
        dx: X movement or position.
        dy: Y movement or position.
        dw_data: Wheel delta or other data.
        dw_extra_info: Additional info.
    """
    windll.user32.mouse_event(dw_flags, dx, dy, dw_data, dw_extra_info)


# ============================================================================
# Mouse Operations
# ============================================================================

def mouse_move(x: int, y: int) -> None:
    """Move mouse cursor to specified position.

    Args:
        x: X coordinate.
        y: Y coordinate.
    """
    set_cursor_pos(x, y)


def mouse_click(button: str, x: int, y: int) -> None:
    """Perform mouse click at specified position.

    Args:
        button: Button type ('left' or 'right').
        x: X coordinate.
        y: Y coordinate.
    """
    # Move to position
    set_cursor_pos(x, y)
    time.sleep(0.01)  # Small delay to ensure position is set

    # Perform click based on button type
    if button == 'left':
        mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)  # 50ms delay as per requirements
        mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    elif button == 'right':
        mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)  # 50ms delay
        mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def mouse_scroll(delta: int) -> None:
    """Perform mouse scroll.

    Args:
        delta: Scroll delta (positive for scroll up, negative for scroll down).
    """
    mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)


# ============================================================================
# Control File Management
# ============================================================================

def read_control(path: str) -> Dict[str, Any]:
    """Read JSON control file.

    Args:
        path: Path to control file.

    Returns:
        Parsed JSON dict, or empty dict if file doesn't exist or is invalid.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {}


def log_event(log_file: str, event_type: str, **data: Any) -> None:
    """Append a JSON log event to a file.

    Args:
        log_file: Path to the log file.
        event_type: Type identifier for the event.
        **data: Additional event data.
    """
    event = {
        'type': event_type,
        'timestamp': time.time(),
    }
    event.update(data)

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')


# ============================================================================
# Operation Execution
# ============================================================================

def execute_operations(operations: List[Dict[str, Any]], log_file: str) -> None:
    """Execute a list of mouse operations.

    Args:
        operations: List of operation dicts.
        log_file: Path to log file.
    """
    for op in operations:
        op_type = op.get('type')

        if op_type == 'move':
            x = op.get('x', 0)
            y = op.get('y', 0)
            mouse_move(x, y)
            log_event(log_file, 'mouse_op', type='move', x=x, y=y)

        elif op_type == 'click':
            button = op.get('button', 'left')
            x = op.get('x', 0)
            y = op.get('y', 0)
            mouse_click(button, x, y)
            log_event(log_file, 'mouse_op', type='click', button=button, x=x, y=y)

        elif op_type == 'scroll':
            delta = op.get('delta', 0)
            mouse_scroll(delta)
            log_event(log_file, 'mouse_op', type='scroll', delta=delta)

        # Small delay between operations
        time.sleep(0.05)


# ============================================================================
# Main Loop
# ============================================================================

def main(control_file: str, log_file: str) -> None:
    """Main loop for mouse simulator.

    Args:
        control_file: Path to control file.
        log_file: Path to log file.
    """
    while True:
        # Read control file
        data = read_control(control_file)
        action = data.get('action', '')

        if action == 'start':
            # Get operations from params
            params = data.get('params', {})
            operations = params.get('operations', [])

            if operations:
                execute_operations(operations, log_file)

            # Clear action after processing
            # Write back with empty action to signal completion
            data['action'] = 'completed'
            with open(control_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        elif action == 'stop':
            # Exit the simulator
            break

        # Polling interval
        time.sleep(0.1)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Mouse simulator subprocess')
    parser.add_argument('--control', required=True, help='Path to control file')
    parser.add_argument('--log', required=True, help='Path to log file')
    parser.add_argument('args', nargs='*', help='Additional positional arguments (ignored)')

    args = parser.parse_args()

    control_file = args.control
    log_file = args.log

    try:
        main(control_file, log_file)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)