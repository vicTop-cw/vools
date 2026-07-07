"""测试 Table SQL 风格方法"""
from vools.data import Table

# 测试数据
data = [
    ['Alice', 25, 'NYC', 50000],
    ['Bob', 30, 'LA', 60000],
    ['Charlie', 35, 'NYC', 70000],
    ['David', 28, 'LA', 55000],
    ['Eve', 40, 'Chicago', 80000],
    ['Frank', 22, 'NYC', 45000],
]
table = Table(data, columns=['name', 'age', 'city', 'salary'])

print('=== 测试 where 字符串表达式 ===')
result = table.where('age > 28')
print(f'age > 28: {result.rows()} 行')
assert result.rows() == 3, f'Expected 3, got {result.rows()}'

result = table.where('age >= 30 and city == "LA"')
print(f'age >= 30 and city == "LA": {result.rows()} 行')
assert result.rows() == 1

result = table.where('salary > 60000 or age < 25')
print(f'salary > 60000 or age < 25: {result.rows()} 行')
assert result.rows() == 3

print()
print('=== 测试 where 函数式 ===')
result = table.where(lambda r: r['age'] > 28)
print(f'lambda: {result.rows()} 行')
assert result.rows() == 3

print()
print('=== 测试 order_by ===')
result = table.order_by('age', desc=True)
ages = result.column('age')
print(f'ages desc: {ages}')
assert ages == [40, 35, 30, 28, 25, 22]

result = table.order_by('salary')
salaries = result.column('salary')
print(f'salaries asc: {salaries}')
assert salaries == sorted(salaries)

print()
print('=== 测试 agg ===')
result = table.agg({'age': 'mean', 'salary': 'sum'})
print(f'mean age, sum salary: {result.column("age")[0]:.2f}, {result.column("salary")[0]}')
assert abs(result.column('age')[0] - 30.0) < 0.1
assert result.column('salary')[0] == 360000

# 测试 count/min/max
result = table.agg({'age': 'count', 'salary': 'min'})
print(f'count: {result.column("age")[0]}, min salary: {result.column("salary")[0]}')
assert result.column('age')[0] == 6
assert result.column('salary')[0] == 45000

# 测试 std/var
result = table.agg({'age': 'std', 'salary': 'var'})
print(f'std age: {result.column("age")[0]:.2f}, var salary: {result.column("salary")[0]:.2f}')
assert result.column('age')[0] > 0
assert result.column('salary')[0] > 0

# 自定义函数
result = table.agg({'age': lambda vals: sum(vals) / len(vals)})
print(f'custom lambda: {result.column("age")[0]:.2f}')

print()
print('=== 测试链式 SQL 风格 ===')
result = (table
    .select('name', 'age', 'salary')
    .where('age >= 28')
    .order_by('salary', desc=True))
print(f'链式查询: {result.rows()} 行')
print(result)
assert result.rows() == 4

print()
print('=== 测试 query 一体化 ===')
result = table.query(where='age >= 30', order_by='age', desc=True, limit=2)
print(f'query top 2: {result.rows()} 行')
assert result.rows() == 2

result = table.query(select='name,city', where='city == "NYC"', limit=10)
print(f'query NYC: {result.rows()} 行')
assert result.rows() == 3

print()
print('=== 测试 group_by + 手动聚合 ===')
groups = table.group_by('city')
for city, g in groups.items():
    print(f'{city}: {g.rows()} 人, 平均工资: {g.avg("salary"):.0f}')

# 用 having 过滤大组
big_groups = [t for k, t in groups.items() if t.rows() >= 2]
print(f'行数 >=2 的组: {len(big_groups)} 个')
assert len(big_groups) == 2  # NYC 和 LA

print()
print('=== 测试 limit + offset ===')
result = table.order_by('age').limit(2, offset=1)
print(f'skip 1 take 2: {result.column("name")}')
# 按 age 升序: Frank(22), Alice(25), David(28), Bob(30)...
# 跳过 Frank(22), 取 Alice(25) 和 David(28)
assert result.column('name') == ['Alice', 'David']

print()
print('所有 Table SQL 风格测试通过!')
