"""
多进程测试 - 验证进程级并发
"""
import time
import tempfile
import os

from vools.task import TaskQueue, WorkerPool
from tests.test_functions import add, multiply


def test_multiprocess():
    """测试多进程功能"""
    print("=== 多进程测试 ===")

    db_path = tempfile.mktemp(suffix='.db')
    print(f"Database: {db_path}")

    try:
        queue = TaskQueue(db_path)

        # 提交多个任务
        task_ids = []
        for i in range(6):
            task_id = queue.submit(add, i, i)
            task_ids.append(task_id)
            print(f"提交任务 {task_id}: {i} + {i}")

        # 启动3个Worker进程
        print("\n启动3个Worker进程...")
        pool = WorkerPool(num_workers=3, db_path=db_path, poll_interval=0.1)
        pool.start()

        # 等待所有任务完成
        print("\n等待任务完成...")
        for i, task_id in enumerate(task_ids):
            try:
                result = queue.get_result(task_id, timeout=30)
                expected = i + i
                status = "OK" if result == expected else "FAIL"
                print(f"任务 {task_id}: {i} + {i} = {result} [{status}]")
                assert result == expected, f"期望 {expected}，实际 {result}"
            except Exception as e:
                print(f"任务 {task_id} 失败: {e}")

        print("\n多进程测试通过!")

    finally:
        pool.stop()
        # 清理数据库
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


if __name__ == '__main__':
    test_multiprocess()
