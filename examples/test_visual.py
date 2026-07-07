import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))
from vools.xl.viewer import show_table

data = [
    ['Name', 'Age', 'City'],
    ['Alice', '25', 'New York'],
    ['Bob', '30', 'London'],
    ['Charlie', '35', 'Tokyo'],
]

show_table(data, title=\"Test Table\", has_header=True)
