#!entry main

# Library Example

## Scan Library

```python #!run tag=scan
import os
md_files = [f for f in os.listdir('.') if f.endswith('.md')]
print(f"Found {len(md_files)} markdown files")
```

## Build Manifest

```python #!run export=manifest tag=build
manifest = {
    'files': ['a.md', 'b.md', 'c.md'],
    'total': 3
}
print(f"Manifest: {manifest}")
```

## Cleanup

```shell #!skip
echo "Library example complete"
```
