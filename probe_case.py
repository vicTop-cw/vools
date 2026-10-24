import sys
from vools.vconcurrent.queues import VQueue, BoundedChannel
case = sys.argv[1]
if case == 'get_timeout_0':
    q = VQueue()
    print("start", flush=True)
    print(q.get_timeout(0), flush=True)
elif case == 'get_timeout_small':
    q = VQueue()
    print("start", flush=True)
    print(q.get_timeout(0.05), flush=True)
elif case == 'put_timeout_full':
    q = VQueue(maxsize=1); q.put('a')
    print("start", flush=True)
    print(q.put_timeout('b', 0.05), flush=True)
elif case == 'channel_recv_empty':
    ch = BoundedChannel(maxsize=1)
    print("start", flush=True)
    print(ch.recv(), flush=True)
elif case == 'channel_recv_closed':
    ch = BoundedChannel(maxsize=1); ch.close()
    print("start", flush=True)
    print(ch.recv(), flush=True)
elif case == 'channel_send_closed':
    ch = BoundedChannel(maxsize=1); ch.close()
    print("start", flush=True)
    print(ch.send('x'), flush=True)
elif case == 'peek':
    q = VQueue(); print("start", flush=True); print(q.peek(), flush=True)
elif case == 'lifo_get_empty':
    from vools.vconcurrent.queues import VLifoQueue
    q = VLifoQueue(); print("start", flush=True); print(q.get(), flush=True)
