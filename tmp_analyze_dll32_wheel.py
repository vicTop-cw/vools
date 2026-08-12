import zipfile
from collections import defaultdict

zf = zipfile.ZipFile('dll32/dist/vools_dll32-0.7.2-py3-none-any.whl')
sizes = defaultdict(int)
counts = defaultdict(int)
for info in zf.infolist():
    parts = info.filename.split('/')
    if len(parts) >= 3 and parts[0] == 'vools' and parts[1] == 'dll32':
        key = '/'.join(parts[2:4]) if len(parts) > 4 else parts[2]
        sizes[key] += info.file_size
        counts[key] += 1
for k, size in sorted(sizes.items(), key=lambda x: -x[1])[:20]:
    print(f'{k}: {size/1024/1024:.2f} MB ({counts[k]} files)')
print(f'\nTotal: {sum(sizes.values())/1024/1024:.2f} MB')
