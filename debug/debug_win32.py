import os, time, tempfile, threading
from vools.reactive.file_watcher import _Win32WatchBackend

with tempfile.TemporaryDirectory() as tmpdir:
    received = []
    def handler(path, old_path, ct, is_dir):
        received.append((path, ct.name, is_dir))
        print(f'   [EVENT] {path} {ct.name} is_dir={is_dir}')

    be = _Win32WatchBackend(handler, paths=[tmpdir], interval=0.1)
    be.start()
    time.sleep(0.3)

    child_file = os.path.join(tmpdir, 'file.txt')
    print(f'[BEFORE] creating file {child_file}')
    with open(child_file, 'w') as f:
        f.write('hello')
    time.sleep(1.0)
    print(f'[AFTER] received={len(received)} events')
    for r in received:
        print(f'  {r}')
    be.stop()
