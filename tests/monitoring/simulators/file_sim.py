"""File simulator subprocess for testing file event monitoring.

This module simulates file operations by:
1. Reading control file for start/stop commands
2. Executing file operations (create, modify, delete)
3. Logging events to a log file

Usage:
    python file_sim.py <control_file> <log_file> <work_dir>

Compatible with Python 3.6+.
"""

from __future__ import absolute_import

import os
import sys
import time
from typing import Any, Dict, List

from utils import log_event, read_control


def execute_operation(op: Dict[str, Any], work_dir: str, log_file: str) -> bool:
    """Execute a single file operation.

    Args:
        op: Operation dict with 'type' and optional 'path', 'content'.
        work_dir: Working directory for relative paths.
        log_file: Path to log file.

    Returns:
        True if successful, False otherwise.
    """
    op_type = op.get('type')
    rel_path = op.get('path', '')
    content = op.get('content', '')

    # Resolve path relative to work_dir
    full_path = os.path.join(work_dir, rel_path)

    try:
        if op_type == 'create':
            # Create parent directory if needed
            parent_dir = os.path.dirname(full_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            # Create file with content
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            log_event(log_file, 'file_op', type=op_type, path=rel_path, success=True)

        elif op_type == 'modify':
            # Modify existing file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            log_event(log_file, 'file_op', type=op_type, path=rel_path, success=True)

        elif op_type == 'delete':
            # Delete file
            if os.path.exists(full_path):
                os.remove(full_path)
            log_event(log_file, 'file_op', type=op_type, path=rel_path, success=True)

        else:
            log_event(log_file, 'file_op', type=op_type, path=rel_path,
                      success=False, error='Unknown operation type')
            return False

        return True

    except Exception as e:
        log_event(log_file, 'file_op', type=op_type, path=rel_path,
                  success=False, error=str(e))
        return False


def main(control_file: str, log_file: str, work_dir: str) -> None:
    """Main loop for file simulator.

    Args:
        control_file: Path to control file for receiving commands.
        log_file: Path to log file for recording events.
        work_dir: Working directory for file operations.
    """
    # Ensure work_dir exists
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)

    log_event(log_file, 'simulator_start', pid=os.getpid(), work_dir=work_dir)

    # Wait for start command
    while True:
        data = read_control(control_file)

        if data is None:
            time.sleep(0.1)
            continue

        action = data.get('action')

        if action == 'start':
            # Get operations list
            params = data.get('params', {})
            operations: List[Dict[str, Any]] = params.get('operations', [])

            log_event(log_file, 'operations_start', count=len(operations))

            # Execute each operation
            for op in operations:
                execute_operation(op, work_dir, log_file)
                time.sleep(0.1)  # Small delay between operations

            log_event(log_file, 'operations_done', count=len(operations))
            break

        elif action == 'stop':
            log_event(log_file, 'simulator_stop', reason='stop_command')
            return

        time.sleep(0.1)

    log_event(log_file, 'simulator_stop', reason='completed')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <control_file> <log_file> <work_dir>",
              file=sys.stderr)
        sys.exit(1)

    control_file_path = sys.argv[1]
    log_file_path = sys.argv[2]
    work_dir_path = sys.argv[3]

    main(control_file_path, log_file_path, work_dir_path)