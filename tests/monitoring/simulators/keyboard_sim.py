"""Keyboard simulator subprocess for testing keyboard event monitoring.

This module simulates keyboard input events using Windows API keybd_event.
It reads commands from a control file and logs all actions to a log file.

Usage:
    python keyboard_sim.py <control_file> <log_file>

Compatible with Python 3.6+.
"""

from __future__ import absolute_import

import sys
import time
from ctypes import windll
from typing import Dict, Optional

from utils import log_event, read_control

# Windows API constants
KEYEVENTF_KEYUP = 0x0002

# Virtual key code mapping
VK_CODES: Dict[str, int] = {
    # A-Z: 0x41-0x5A
    **{chr(ord('A') + i): 0x41 + i for i in range(26)},
    # 0-9: 0x30-0x39
    **{str(i): 0x30 + i for i in range(10)},
    # Special keys
    'ENTER': 0x0D,
    'ESCAPE': 0x1B,
    'SPACE': 0x20,
    'TAB': 0x09,
    # Function keys F1-F12: 0x70-0x7B
    **{f'F{i}': 0x70 + i - 1 for i in range(1, 13)},
    # Modifier keys
    'SHIFT': 0x10,
    'CTRL': 0x11,
    'ALT': 0x12,
    # Arrow keys
    'LEFT': 0x25,
    'UP': 0x26,
    'RIGHT': 0x27,
    'DOWN': 0x28,
}


def vk_code(name: str) -> int:
    """Convert key name to virtual key code.

    Args:
        name: Key name (e.g., 'A', 'ENTER', 'F1')

    Returns:
        Virtual key code as integer.

    Raises:
        ValueError: If key name is not recognized.
    """
    name_upper = name.upper()
    if name_upper not in VK_CODES:
        raise ValueError(f"Unknown key name: {name}")
    return VK_CODES[name_upper]


def press_key(vk: int) -> None:
    """Simulate pressing and releasing a key.

    Uses keybd_event to simulate:
    1. Key down
    2. 50ms delay
    3. Key up
    4. 100ms delay

    Args:
        vk: Virtual key code.
    """
    # Key down
    windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)  # 50ms

    # Key up
    windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)  # 100ms


def main(control_file: str, log_file: str) -> None:
    """Main loop for keyboard simulator.

    Args:
        control_file: Path to control file for receiving commands.
        log_file: Path to log file for recording events.
    """
    while True:
        # Read control file
        data = read_control(control_file)

        if data is None:
            time.sleep(0.1)
            continue

        action = data.get('action')

        if action == 'start':
            # Get keys to press
            params = data.get('params', {})
            keys = params.get('keys', [])

            if keys:
                # Log start
                log_event(log_file, 'key_simulation_start', keys=keys)

                # Press each key
                for key in keys:
                    try:
                        vk = vk_code(key)
                        press_key(vk)
                        log_event(log_file, 'key_press', key=key, vk=vk)
                    except ValueError as e:
                        log_event(log_file, 'key_error', key=key, error=str(e))

                # Log completion
                log_event(log_file, 'key_simulation_complete', keys=keys)

            # Clear action by waiting for next command
            time.sleep(0.1)

        elif action == 'stop':
            # Exit on stop command
            log_event(log_file, 'simulator_stop')
            break

        else:
            # Unknown action, wait
            time.sleep(0.1)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <control_file> <log_file>", file=sys.stderr)
        sys.exit(1)

    control_file_path = sys.argv[1]
    log_file_path = sys.argv[2]

    main(control_file_path, log_file_path)