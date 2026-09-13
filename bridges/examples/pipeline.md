#!entry main

# Data Pipeline

```python #!run export=data tag=main
data = [1, 2, 3, 4, 5]
result = sum(data)
print(f"Sum: {result}")
```

## Process

```python #!run import=data tag=process
data = [1, 2, 3, 4, 5]
result = sum(data)
print(f"Sum: {result}")
```

## Cleanup

```shell #!skip
echo "Cleanup"
```
