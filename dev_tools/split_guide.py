"""Split USER_GUIDE.md into guide/ sub-files"""
import os

src = os.path.join(os.path.dirname(__file__), '..', 'USER_GUIDE.md')
dst_dir = os.path.join(os.path.dirname(__file__), '..', 'guide')
os.makedirs(dst_dir, exist_ok=True)

with open(src, encoding='utf-8') as f:
    lines = f.readlines()

sections = {
    'core.md': (65, 735),
    'vic-classes.md': (736, 956),
    'functional.md': (957, 1066),
    'reactive.md': (1067, 1659),
    'extras.md': (1415, 1659),  # 编码+加密+Result
}

for fname, (start, end) in sections.items():
    content = ''.join(lines[start:end])
    path = os.path.join(dst_dir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    sz = len(content)
    print(f'{fname}: {sz} bytes ({end-start} lines)')
