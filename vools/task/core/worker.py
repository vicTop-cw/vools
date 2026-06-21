"""
Worker进程/线程 - 支持多进程和多线程处理任务
"""

__all__ = ['Worker', 'WorkerPool', 'ThreadPool']

import multiprocessing
import threading
import time
import traceback
from typing import Optional
import os

from .models import Task, TaskStatus
from .storage import TaskStorage
from .queue import TaskQueue


class Worker:
    """单个Worker进程"""

    def __init__(self, worker_id: str, db_path: str = "tasks.db",
                 lease_seconds: int = 300, poll_interval: float = 0.5):
        self.worker_id = worker_id
        self.db_path = db_path
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self._running = False
        self.storage = TaskStorage(db_path)
        self.queue = TaskQueue(db_path)

    def __getstate__(self):
        return {'worker_id': self.worker_id, 'db_path': self.db_path,
                'lease_seconds': self.lease_seconds, 'poll_interval': self.poll_interval,
                '_running': False}
    def __setstate__(self, state):
        self.worker_id = state['worker_id']
        self.db_path = state['db_path']
        self.lease_seconds = state['lease_seconds']
        self.poll_interval = state['poll_interval']
        self._running = False
        self.storage = TaskStorage(self.db_path)
        self.queue = TaskQueue(self.db_path)

    def start(self):
        """启动Worker"""
        self._running = True
        print(f"Worker {self.worker_id} started")

        while self._running:
            try:
                self._process_one_task()
            except Exception as e:
                print(f"Worker {self.worker_id} error: {e}")
                traceback.print_exc()
            time.sleep(self.poll_interval)

    def stop(self):
        """停止Worker"""
        self._running = False
        print(f"Worker {self.worker_id} stopping...")


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def _process_one_task(self):
        """处理一个任务"""
        # 原子领取任务
        task = self.storage.claim_task(self.worker_id, self.lease_seconds)
        if not task:
            return

        try:
            # 执行任务
            result = self.queue.execute_task(task)

            # 任务成功
            self.storage.update_task_status(
                task.id,
                TaskStatus.SUCCESS,
                result=result,
                worker_id=self.worker_id
            )
            print(f"Task {task.id} completed by {self.worker_id}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"

            # 检查是否可以重试
            task = self.storage.get_task(task.id)
            if task and task.retry_count < task.max_retries:
                # 进入重试状态
                self.storage.update_task_status(
                    task.id,
                    TaskStatus.RETRYING,
                    error_message=error_msg,
                    worker_id=self.worker_id
                )
                # 立即重置为PENDING以便重试
                self.storage.update_task_status(
                    task.id,
                    TaskStatus.PENDING,
                    worker_id=None
                )
                print(f"Task {task.id} retrying ({task.retry_count + 1}/{task.max_retries})")
            else:
                # 标记为失败
                self.storage.update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    error_message=error_msg,
                    worker_id=self.worker_id
                )
                print(f"Task {task.id} failed: {e}")


def _worker_process(worker_id: str, db_path: str, lease_seconds: int, poll_interval: float):
    """Worker进程函数（独立函数，可pickle）"""
    worker = Worker(worker_id, db_path, lease_seconds, poll_interval)
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()


class WorkerPool:
    """Worker进程池"""

    def __init__(self, num_workers: int = 4, db_path: str = "tasks.db",
                 lease_seconds: int = 300, poll_interval: float = 0.5):
        self.num_workers = num_workers
        self.db_path = db_path
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self._worker_ids = []
        self._processes = []
        self._started = False

    def start(self):
        """启动所有Worker进程"""
        if self._started:
            return

        storage = TaskStorage(self.db_path)

        for i in range(self.num_workers):
            worker_id = storage.generate_worker_id()
            self._worker_ids.append(worker_id)

            # 启动子进程 - 只传递可pickle的参数
            process = multiprocessing.Process(
                target=_worker_process,
                args=(worker_id, self.db_path, self.lease_seconds, self.poll_interval)
            )
            process.daemon = True
            process.start()
            self._processes.append(process)

        self._started = True
        print(f"WorkerPool started with {self.num_workers} workers")

    def stop(self):
        """停止所有Worker进程"""
        print(f"WorkerPool stopping {len(self._processes)} workers...")
        for process in self._processes:
            process.terminate()
            process.join(timeout=5)

        self._processes = []
        self._worker_ids = []
        self._started = False
        print("WorkerPool stopped")

    def __enter__(self):
        self.start()
        return self


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class ThreadPool:
    """Worker线程池（多线程版本）

    适用于IO密集型任务，共享同一进程的内存空间
    """

    def __init__(self, num_workers: int = 4, db_path: str = "tasks.db",
                 lease_seconds: int = 300, poll_interval: float = 0.5):
        self.num_workers = num_workers
        self.db_path = db_path
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self._worker_ids = []
        self._threads = []
        self._workers = []
        self._running = False

    def start(self):
        """启动所有Worker线程"""
        if self._running:
            return

        storage = TaskStorage(self.db_path)

        for i in range(self.num_workers):
            worker_id = storage.generate_worker_id()
            self._worker_ids.append(worker_id)

            worker = Worker(worker_id, self.db_path, self.lease_seconds, self.poll_interval)
            self._workers.append(worker)

            # 启动线程
            thread = threading.Thread(
                target=self._thread_loop,
                args=(worker,),
                daemon=True
            )
            thread.start()
            self._threads.append(thread)

        self._running = True
        print(f"ThreadPool started with {self.num_workers} threads")

    def stop(self):
        """停止所有Worker线程"""
        print(f"ThreadPool stopping {len(self._threads)} threads...")
        # 先通知所有Worker停止
        for worker in self._workers:
            worker.stop()
        # 等待线程结束
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads = []
        self._workers = []
        self._worker_ids = []
        print("ThreadPool stopped")

    @staticmethod
    def _thread_loop(worker: Worker):
        """Worker线程主循环"""
        worker.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self

