"""Folder simulator subprocess for testing folder event monitoring.

This module simulates folder operations by:
1. Reading control file for start/stop commands
2. Executing folder operations (create, create_file, delete)
3. Logging events to a log file

Usage:
    python folder_sim.py <control_file> <log_file> <work_dir>

Compatible with Python 3.6+.
"""

from __future__ import absolute_import

import os
import shutil
import sys
import time
from typing import Any, Dict, List

from utils import log_event, read_control


def execute_operation(op: Dict[str, Any], work_dir: str, log_file: str) -> bool:
    """Execute a single folder operation.

    Args:
        op: Operation dict with 'type' and optional 'path', 'folder', 'file', 'content'.
        work_dir: Working directory for relative paths.
        log_file: Path to log file.

    Returns:
        True if successful, False otherwise.
    """
    op_type = op.get('type')

    try:
        if op_type == 'create':
            # Create folder
            rel_path = op.get('path', '')
            full_path = os.path.join(work_dir, rel_path)
            os.makedirs(full_path, exist_ok=True)
            log_event(log_file, 'folder_op', type=op_type, path=rel_path, success=True)

        elif op_type == 'create_file':
            # Create file inside folder
            folder = op.get('folder', '')
            file_name = op.get('file', '')
            content = op.get('content', '')

            full_folder_path = os.path.join(work_dir, folder)
            full_file_path = os.path.join(full_folder_path, file_name)

            # Ensure folder exists
            os.makedirs(full_folder_path, exist_ok=True)

            # Create file with content
            with open(full_file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            rel_path = os.path.join(folder, file_name)
            log_event(log_file, 'folder_op', type=op_type, path=rel_path, folder=folder, file=file_name, success=True)

        elif op_type == 'delete':
            # Delete folder recursively
            rel_path = op.get('path', '')
            full_path = os.path.join(work_dir, rel_path)
            if os.path.exists(full_path):
                shutil.rmtree(full_path)
            log_event(log_file, 'folder_op', type=op_type, path=rel_path, success=True)

        else:
            log_event(log_file, 'folder_op', type=op_type,
                      success=False, error='Unknown operation type')
            return False

        return True

    except Exception as e:
        rel_path = op.get('path', '')
        log_event(log_file, 'folder_op', type=op_type, path=rel_path,
                  success=False, error=str(e))
        return False


def main(control_file: str, log_file: str, work_dir: str) -> None:
    """Main loop for folder simulator.

    Args:
        control_file: Path to control file for receiving commands.
        log_file: Path to log file for recording events.
        work_dir: Working directory for folder operations.
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