#!/usr/bin/env python
"""Clipboard simulator subprocess for integration tests.

This script simulates clipboard operations by:
1. Reading control file for start/stop commands
2. Executing clipboard operations (text set, clear) via Windows API
3. Logging events to a log file

Usage:
    python clipboard_sim.py --control <control_file> --log <log_file>

Control file format (JSON):
    {"action": "start", "params": {"operations": [...]}}  # Start execution
    {"action": "stop"}                                    # Stop and exit

Operations format:
    {"type": "text", "content": "hello"}  # Set clipboard text
    {"type": "clear"}                     # Clear clipboard
"""

from __future__ import absolute_import, print_function

import ctypes
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Windows API constants
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
GHND = GMEM_MOVEABLE | GMEM_ZEROINIT
CF_UNICODETEXT = 13

# Load Windows DLLs with proper type safety
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

# Set proper argument types and return types for 64-bit Windows
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_int
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p

user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.restype = ctypes.c_int
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = ctypes.c_int
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = ctypes.c_int
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p


def log_event(log_file: str, event_type: str, **data: Any) -> None:
    """Append a JSON log event to a file.

    Args:
        log_file: Path to the log file.
        event_type: Type identifier for the event.
        **data: Additional event data.
    """
    event = {
        'type': event_type,
        'timestamp': datetime.now().isoformat(),
    }
    event.update(data)

    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    except Exception:
        pass


def read_control(control_file: str) -> Optional[Dict[str, Any]]:
    """Read a JSON control file.

    Args:
        control_file: Path to the control file.

    Returns:
        Parsed JSON dict, or None if file doesn't exist or is invalid.
    """
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def set_clipboard_text(text: str, max_retries: int = 10) -> bool:
    """Set clipboard text using Windows API.

    Uses GlobalAlloc + GlobalLock + memcpy to create clipboard data handle.

    Args:
        text: Text to set in clipboard.
        max_retries: Maximum number of retries if clipboard is locked.

    Returns:
        True if successful, False otherwise.
    """
    # Encode text as UTF-16-LE with null terminator
    text_bytes = text.encode('utf-16-le') + b'\x00\x00'

    for attempt in range(max_retries):
        # Try to open clipboard
        if not user32.OpenClipboard(0):
            time.sleep(0.05)
            continue

        try:
            # Empty clipboard
            user32.EmptyClipboard()

            # Allocate memory for text
            h_mem = kernel32.GlobalAlloc(GHND, len(text_bytes))
            if not h_mem:
                return False

            # Lock memory and copy data
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                kernel32.GlobalFree(h_mem)
                return False

            ctypes.memmove(p_mem, text_bytes, len(text_bytes))
            kernel32.GlobalUnlock(h_mem)

            # Set clipboard data
            result = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            if not result:
                kernel32.GlobalFree(h_mem)
                return False

            return True

        finally:
            user32.CloseClipboard()

    return False


def clear_clipboard(max_retries: int = 10) -> bool:
    """Clear clipboard contents.

    Args:
        max_retries: Maximum number of retries if clipboard is locked.

    Returns:
        True if successful, False otherwise.
    """
    for attempt in range(max_retries):
        if not user32.OpenClipboard(0):
            time.sleep(0.05)
            continue

        try:
            user32.EmptyClipboard()
            return True
        finally:
            user32.CloseClipboard()

    return False


def execute_operation(op: Dict[str, Any], log_file: str) -> bool:
    """Execute a single clipboard operation.

    Args:
        op: Operation dict with 'type' and optional 'content'.
        log_file: Path to log file.

    Returns:
        True if successful, False otherwise.
    """
    op_type = op.get('type')

    if op_type == 'text':
        content = op.get('content', '')
        content_preview = content[:50] if content else ''

        success = set_clipboard_text(content)

        log_event(log_file, 'clipboard_op',
                  op_type=op_type,
                  content_preview=content_preview,
                  success=success)

        return success

    elif op_type == 'clear':
        success = clear_clipboard()

        log_event(log_file, 'clipboard_op',
                  op_type=op_type,
                  success=success)

        return success

    else:
        log_event(log_file, 'clipboard_op',
                  op_type=op_type,
                  success=False,
                  error='Unknown operation type')
        return False


def main(control_file: str, log_file: str) -> None:
    """Main loop: wait for start command, execute operations, then exit.

    Args:
        control_file: Path to control file.
        log_file: Path to log file.
    """
    log_event(log_file, 'simulator_start', pid=os.getpid())

    # Wait for start command
    while True:
        control = read_control(control_file)

        if control:
            action = control.get('action')

            if action == 'start':
                # Get operations list
                params = control.get('params', {})
                operations: List[Dict[str, Any]] = params.get('operations', [])

                log_event(log_file, 'operations_start',
                          count=len(operations))

                # Execute each operation
                for i, op in enumerate(operations):
                    execute_operation(op, log_file)
                    time.sleep(0.1)  # Small delay between operations

                log_event(log_file, 'operations_done',
                          count=len(operations))
                break

            elif action == 'stop':
                log_event(log_file, 'simulator_stop', reason='stop_command')
                return

        time.sleep(0.1)

    log_event(log_file, 'simulator_stop', reason='completed')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Clipboard simulator subprocess')
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
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)