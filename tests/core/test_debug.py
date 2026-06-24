"""
调试测试 - 不使用多进程
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import tempfile

from vools.task import TaskQueue
from vools.task.core.models import TaskStatus
from tests.test_functions import add, multiply


def test_simple_single_thread():
    """单线程测试"""
    print("=== 单线程测试 ===")

    db_path = tempfile.mktemp(suffix='.db')
    print(f"Database: {db_path}")

    try:
        queue = TaskQueue(db_path)

        # 提交任务
        task_id = queue.submit(add, 2, 3)
        print(f"Task submitted: {task_id}")

        # 手动领取任务
        worker_id = queue.storage.generate_worker_id()
        print(f"Worker ID: {worker_id}")

        task = queue.storage.claim_task(worker_id)
        if task:
            print(f"Claimed task: {task.id}")
            print(f"Task args: {task.args}")
            print(f"Task func: {task.task_func}")

            # 执行任务
            try:
                result = queue.execute_task(task)
                print(f"Execution result: {result}")

                # 标记成功
                queue.storage.update_task_status(
                    task.id,
                    TaskStatus.SUCCESS,
                    result=result,
                    worker_id=worker_id
                )
                print("Task marked as success")
            except Exception as e:
                print(f"Error executing task: {e}")
                queue.storage.update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    error_message=str(e),
                    worker_id=worker_id
                )

        # 验证结果
        task = queue.get_task(task_id)
        print(f"\nFinal task status: {task.status}")
        print(f"Final task result: {task.result}")
        assert task.status == TaskStatus.SUCCESS
        assert task.result == 5
        print("✓ 单线程测试通过!")

    finally:
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


if __name__ == '__main__':
    test_simple_single_thread()
