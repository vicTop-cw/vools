"""修复 ACTUS_SCHEMA_SPEC.md 嵌套 fence 渲染破损（一次性修到位）。

规则：外层 → 5 反引号 ````````，内层 → 4 反引号 ````，最内层示例 → 3 反引号 ```。

判定：只升级"在 3 反引号 fence 内容中的 ````markdown` / ````json` / ````yaml` / ````python`"
等外层代码块，把它们变成 5 反引号。

简单稳妥的做法：扫一遍全文，记录 fence 嵌套层级：
  - level 0: 普通正文
  - level 1: 三反引号内层 fence 里的内容
  - level 2: 外层 fence（四反引号现在是外层，要升级成五）
"""

import re

path = "actus/vools/actus/ACTUS_SCHEMA_SPEC.md"
text = open(path, encoding="utf-8").read()

# 策略：逐行扫，维护一个 fence 栈。栈顶是当前最内层 fence 的反引号数。
# 任何一个 fence 里，如果其内部还有比它更长或等长的 fence → 内外层冲突，
# 把外层升级 1 段（三→四 / 四→五）。

lines = text.split("\n")
stack = []  # 存整数（反引号数），代表当前嵌套层最内层 fence

# 先找所有 fence 行位置
fence_positions = []
for i, line in enumerate(lines):
    stripped = line.rstrip()
    m = re.match(r"^(`{3,})", stripped)
    if m:
        fence_positions.append((i, len(m.group(1))))

print(f"total fence lines: {len(fence_positions)}")

# 建嵌套树：找外层 fence（包含内层 fence 的那些）
# 简单做法：按位置遍历，维护 stack；每次遇到 fence 栈顶数字相等或更大则出栈
# 然后看栈顶 + 当前 fence 是否冲突。如果冲突（当前 fence 反引号数 <= 栈顶），
# 把当前 fence 升级。

new_lines = list(lines)
upgrade_map = {}  # pos -> new_backtick_count

# 遍历两遍：先收集所有 fence 段的内部冲突，再统一升级
# 简化做法：逐段分析
i = 0
while i < len(fence_positions):
    start_pos, start_count = fence_positions[i]
    # 找配对的 end
    depth = 1
    j = i + 1
    while j < len(fence_positions) and depth > 0:
        depth += 1 if fence_positions[j][1] == start_count else 0
        depth -= 1 if fence_positions[j][1] == start_count else 0
        j += 1
    end_pos = fence_positions[j - 1][0] if j < len(fence_positions) else len(lines) - 1

    # 检查 start_count 段内部是否有 start_count 或更短的 fence
    inner_conflict = False
    k = i + 1
    while k < j - 1:
        _, inner_count = fence_positions[k]
        if inner_count <= start_count:
            inner_conflict = True
            break
        k += 1

    if inner_conflict:
        upgrade_map[start_pos] = start_count + 1
        upgrade_map[end_pos] = start_count + 1

    i = j

# 应用升级
for pos, new_count in upgrade_map.items():
    old_line = new_lines[pos]
    new_line = "`" * new_count + old_line[len("`" * (len(old_line) - len(old_line.lstrip("`")))):]
    # 只替换开头的反引号数，保留语言标记
    stripped = old_line.rstrip()
    m = re.match(r"^(`{3,})(.*)", stripped)
    if m:
        suffix = m.group(2)
        new_lines[pos] = "`" * new_count + suffix

open(path, "w", encoding="utf-8", newline="").write("\n".join(new_lines))

# 验证
out = open(path, encoding="utf-8").read()
print("done.")
