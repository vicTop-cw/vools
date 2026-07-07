"""
测试任务队列功能
"""
import os
import time
import tempfile
import threading

from vools.task import TaskQueue, WorkerPool, ThreadPool, task
from tests.test_functions import add, multiply, sometimes_fails, decorated_add


def test_basic_functionality():
    """测试基本功能"""
    print("=== 测试基本功能 ===")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        queue = TaskQueue(db_path)

        task_id1 = queue.submit(add, 2, 3)
        task_id2 = queue.submit(multiply, 4, 5)

        print(f"Task 1 submitted: {task_id1}")
        print(f"Task 2 submitted: {task_id2}")

        with WorkerPool(num_workers=2, db_path=db_path, poll_interval=0.1) as pool:
            result1 = queue.get_result(task_id1, timeout=10)
            result2 = queue.get_result(task_id2, timeout=10)

            print(f"Task 1 result: {result1}")
            print(f"Task 2 result: {result2}")

            assert result1 == 5
            assert result2 == 20

        print("基本功能测试通过")
    finally:
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


def test_decorator():
    """测试@task装饰器"""
    print("\n=== 测试@task装饰器 ===")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        queue = TaskQueue(db_path)

        task_id = decorated_add(10, 20, queue=queue)
        print(f"Decorated task submitted: {task_id}")

        direct_result = decorated_add.direct(10, 20)
        print(f"Direct execution result: {direct_result}")
        assert direct_result == 30

        with WorkerPool(num_workers=1, db_path=db_path, poll_interval=0.1) as pool:
            result = queue.get_result(task_id, timeout=10)
            print(f"Task result: {result}")
            assert result == 30

        print("装饰器测试通过")
    finally:
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


def test_status_change():
    """测试状态变更"""
    print("\n=== 测试状态变更 ===")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        queue = TaskQueue(db_path)

        task_id = queue.submit(add, 1, 1)

        status = queue.get_task_status(task_id)
        print(f"Initial status: {status}")
        assert status.value == "PENDING"

        queue.cancel_task(task_id)
        status = queue.get_task_status(task_id)
        print(f"After cancel: {status}")
        assert status.value == "CANCEL"

        print("状态变更测试通过")
    finally:
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


def test_retry():
    """测试重试功能"""
    print("\n=== 测试重试功能 ===")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        queue = TaskQueue(db_path)

        task_id = queue.submit(sometimes_fails, True, max_retries=2)

        with WorkerPool(num_workers=1, db_path=db_path, poll_interval=0.1) as pool:
            try:
                result = queue.get_result(task_id, timeout=15)
                print(f"Unexpected success: {result}")
            except Exception as e:
                print(f"Task failed as expected: {e}")

        task = queue.get_task(task_id)
        print(f"Retry count: {task.retry_count}")
        assert task.retry_count == 2
        assert task.status.value == "FAILED"

        print("重试测试通过")
    finally:
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


def main():
    print("任务队列系统测试")
    print("=" * 40)

    test_basic_functionality()
    test_decorator()
    test_status_change()
    test_retry()

    print("\n" + "=" * 40)
    print("所有测试完成")


if __name__ == '__main__':
    main()
