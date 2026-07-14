"""Utility functions for managing test simulators.

This module provides helpers for:
- Control file management (JSON-based IPC)
- Event logging
- Process lifecycle management
- Temporary file cleanup

Compatible with Python 3.6+.
"""

from __future__ import absolute_import

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Type alias for subprocess.Popen (Python 3.6 compatibility)
if sys.version_info >= (3, 9):
    PopenType = subprocess.Popen[Any]
else:
    PopenType = subprocess.Popen


# ============================================================================
# Control File Management
# ============================================================================

def write_control(path: str, data: Dict[str, Any]) -> None:
    """Write a JSON control file.

    Args:
        path: Path to the control file.
        data: Dictionary to write as JSON.
    """
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_control(path: str) -> Optional[Dict[str, Any]]:
    """Read a JSON control file.

    Args:
        path: Path to the control file.

    Returns:
        Parsed JSON dict, or None if file doesn't exist or is invalid.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def wait_for_control(path: str, expected_action: str, timeout: float = 10.0) -> bool:
    """Wait for a specific control action to appear in the control file.

    Polls the control file until the 'action' field matches expected_action
    or timeout expires.

    Args:
        path: Path to the control file.
        expected_action: The action value to wait for.
        timeout: Maximum time to wait in seconds.

    Returns:
        True if action matched, False if timeout.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        data = read_control(path)
        if data is not None and data.get('action') == expected_action:
            return True
        time.sleep(0.1)
    return False


# ============================================================================
# Event Logging
# ============================================================================

def log_event(log_file: str, event_type: str, **data: Any) -> None:
    """Append a JSON log event to a file.

    Each event is written as a single line of JSON.

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


def read_log(log_file: str) -> List[Dict[str, Any]]:
    """Read all log records from a log file.

    Args:
        log_file: Path to the log file.

    Returns:
        List of parsed JSON event dictionaries.
    """
    if not os.path.exists(log_file):
        return []

    events = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    # Skip malformed lines
                    pass
    return events


# ============================================================================
# Process Management
# ============================================================================

def start_simulator(
    name: str,
    control_file: str,
    log_file: str,
    **kwargs: Any
) -> PopenType:
    """Start a simulator subprocess.

    Launches a Python subprocess with the given simulator name, passing
    control and log file paths.

    Args:
        name: Simulator name (used to find the script).
        control_file: Path to the control file for IPC.
        log_file: Path to the log file for event output.
        **kwargs: Additional arguments passed as command-line args.

    Returns:
        subprocess.Popen object for the started process.
    """
    # Find the simulator script relative to this module
    simulators_dir = Path(__file__).parent
    script_path = simulators_dir / f'{name}.py'

    if not script_path.exists():
        raise FileNotFoundError(f"Simulator script not found: {script_path}")

    cmd = [
        sys.executable,
        str(script_path),
        '--control', control_file,
        '--log', log_file,
    ]

    # Add additional arguments
    for key, value in kwargs.items():
        cmd.extend([f'--{key}', str(value)])

    # On Windows, avoid showing console window
    startupinfo = None
    creationflags = 0
    if sys.platform == 'win32':
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    return proc


def stop_simulator(
    proc: PopenType,
    control_file: str,
    timeout: float = 5.0
) -> None:
    """Stop a simulator process.

    First writes a 'stop' action to the control file for graceful shutdown,
    then waits for the process to exit. If it doesn't exit within timeout,
    terminates it forcefully.

    Args:
        proc: The subprocess.Popen object to stop.
        control_file: Path to the control file for IPC.
        timeout: Maximum time to wait for graceful shutdown.
    """
    if proc.poll() is not None:
        # Already terminated
        return

    # Try graceful shutdown via control file
    try:
        write_control(control_file, {'action': 'stop'})
    except (IOError, OSError):
        pass

    # Wait for graceful exit
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Force kill if still running
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()


# ============================================================================
# Temporary File Management
# ============================================================================

def get_test_paths(test_name: str) -> Tuple[Path, Path, Path]:
    """Get standard paths for a test.

    Creates a temporary directory with standardized paths for control file,
    log file, and the temp directory itself.

    Args:
        test_name: Name of the test, used for directory naming.

    Returns:
        Tuple of (control_file_path, log_file_path, temp_dir_path).
    """
    # Use system temp directory
    import tempfile

    temp_dir = Path(tempfile.gettempdir()) / f'vools_sim_{test_name}'
    temp_dir.mkdir(parents=True, exist_ok=True)

    control_file = temp_dir / 'control.json'
    log_file = temp_dir / 'events.log'

    return control_file, log_file, temp_dir


def cleanup_test_files(
    control_file: Path,
    log_file: Path,
    temp_dir: Path
) -> None:
    """Clean up test files and directory.

    Removes the control file, log file, and the temporary directory.

    Args:
        control_file: Path to control file.
        log_file: Path to log file.
        temp_dir: Path to temporary directory.
    """
    # Remove files first
    for f in [control_file, log_file]:
        try:
            if f.exists():
                f.unlink()
        except (IOError, OSError):
            pass

    # Remove directory
    try:
        if temp_dir.exists():
            temp_dir.rmdir()
    except (IOError, OSError):
        pass