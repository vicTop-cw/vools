from vools.xl import show_table

data = [
    ['Name', 'Age', 'City'],
    ['Alice', '25', 'New York'],
    ['Bob', '30', 'Los Angeles'],
    ['Charlie', '35', 'Chicago'],
]

show_table(data, title="用户信息表")
print("---")
show_table(data)
