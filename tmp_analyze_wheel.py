import zipfile
from collections import defaultdict

zf = zipfile.ZipFile('dist/vools-0.7.2-py3-none-any.whl')
sizes = defaultdict(int)
counts = defaultdict(int)
for info in zf.infolist():
    parts = info.filename.split('/')
    if len(parts) >= 2 and parts[0] == 'vools':
        mod = parts[1]
        sizes[mod] += info.file_size
        counts[mod] += 1
for mod, size in sorted(sizes.items(), key=lambda x: -x[1]):
    if size > 1024*1024:
        print(f'{mod}: {size/1024/1024:.2f} MB ({counts[mod]} files)')
    else:
        print(f'{mod}: {size/1024:.2f} KB ({counts[mod]} files)')
