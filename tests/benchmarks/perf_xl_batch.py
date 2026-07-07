"""批量读写性能测试"""
import sys
import os
import time
import tempfile
ROWS = 10000
COLS = 10

print(f'测试参数：{ROWS} 行 x {COLS} 列')
print('=' * 60)

# ========== 测试 write_matrix ==========
print('\n[Sheet.write_matrix] 批量写入测试')
from vools.xl import Book

# 生成测试数据
data = []
for row in range(ROWS):
    row_data = []
    for col in range(COLS):
        if col == 0:
            row_data.append(f'Name_{row}')
        elif col == 1:
            row_data.append(row * 100 + col)
        else:
            row_data.append(row + col)
    data.append(row_data)

tmp_file = os.path.join(tempfile.gettempdir(), 'perf_batch.xlsx')

start = time.time()
with Book() as book:
    sheet = book.add_sheet('Data')
    sheet.write_matrix(data)
    book.save(tmp_file)

matrix_write_time = time.time() - start
print(f'write_matrix 耗时: {matrix_write_time:.3f}s')
print(f'文件大小: {os.path.getsize(tmp_file)} bytes')

# ========== 测试 read_matrix ==========
print('\n[Sheet.read_matrix] 批量读取测试')
start = time.time()
with Book() as book:
    book.load(tmp_file)
    sheet = book.get_sheet(0)
    result = sheet.read_matrix(ROWS, COLS)

matrix_read_time = time.time() - start
print(f'read_matrix 耗时: {matrix_read_time:.3f}s')
print(f'读取行数: {len(result)}')

# ========== 对比：逐单元格写入 ==========
print('\n[逐单元格写入] 对比测试')
start = time.time()
with Book() as book:
    sheet = book.add_sheet('Data2')
    for row_idx in range(min(ROWS, 1000)):  # 只测1000行避免太久
        for col_idx in range(COLS):
            value = data[row_idx][col_idx]
            if isinstance(value, str):
                sheet.write_str(row_idx + 1, col_idx, value)
            else:
                sheet.write_num(row_idx + 1, col_idx, value)
    book.save(tmp_file.replace('.xlsx', '_cell.xlsx'))

cell_write_time = time.time() - start
print(f'逐单元格写入 1000行: {cell_write_time:.3f}s')
print(f'折算 {ROWS}行: {cell_write_time * ROWS / 1000:.3f}s')

# ========== 对比：逐单元格读取 ==========
print('\n[逐单元格读取] 对比测试')
start = time.time()
with Book() as book:
    book.load(tmp_file)
    sheet = book.get_sheet(0)
    result = []
    for row in range(1, min(ROWS, 1000) + 1):
        row_data = []
        for col in range(COLS):
            ct = sheet.cell_type(row, col)
            if ct == 1:
                row_data.append(sheet.read_num(row, col))
            elif ct == 2:
                row_data.append(sheet.read_str(row, col))
            else:
                row_data.append(None)
        result.append(row_data)

cell_read_time = time.time() - start
print(f'逐单元格读取 1000行: {cell_read_time:.3f}s')
print(f'折算 {ROWS}行: {cell_read_time * ROWS / 1000:.3f}s')

# ========== 结果汇总 ==========
print('\n' + '=' * 60)
print('性能对比结果')
print('=' * 60)
print(f'写入速度: write_matrix {matrix_write_time:.3f}s vs 逐单元格 {cell_write_time * ROWS / 1000:.3f}s')
if cell_write_time * ROWS / 1000 > 0:
    ratio = (cell_write_time * ROWS / 1000) / matrix_write_time
    print(f'           write_matrix 快 {ratio:.1f}x')

print(f'\n读取速度: read_matrix {matrix_read_time:.3f}s vs 逐单元格 {cell_read_time * ROWS / 1000:.3f}s')
if cell_read_time * ROWS / 1000 > 0:
    ratio = (cell_read_time * ROWS / 1000) / matrix_read_time
    print(f'           read_matrix 快 {ratio:.1f}x')

# ========== 与 openpyxl 对比 ==========
print('\n' + '=' * 60)
print('与 openpyxl 对比')
print('=' * 60)
try:
    from openpyxl import Workbook
    tmp_openpyxl = os.path.join(tempfile.gettempdir(), 'perf_openpyxl.xlsx')
    start = time.time()
    wb = Workbook()
    ws = wb.active
    for row in range(1, ROWS + 1):
        for col in range(1, COLS + 1):
            idx = row - 1
            ws.cell(row=row, column=col, value=data[idx][col-1])
    wb.save(tmp_openpyxl)
    openpyxl_write = time.time() - start
    print(f'openpyxl 写入: {openpyxl_write:.3f}s')
    print(f'vools.xl write_matrix: {matrix_write_time:.3f}s')
    if openpyxl_write > 0:
        ratio = openpyxl_write / matrix_write_time
        print(f'vools.xl 写入快 {ratio:.1f}x')
except ImportError:
    print('openpyxl 未安装')

# 清理
os.remove(tmp_file)
print('\n测试完成')
