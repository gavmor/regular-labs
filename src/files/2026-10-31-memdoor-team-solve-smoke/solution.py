import sys
from collections import defaultdict

# Read input
line = sys.stdin.read().strip()

# Use a coordinate system where we track (count_a - count_b, count_b - count_c)
# This allows us to identify balanced substrings efficiently
counts = defaultdict(int)
counts[(0, 0)] = 1  # Initial state: 0 a's, 0 b's, 0 c's

result = 0
count_a = count_b = count_c = 0

for char in line:
    if char == 'a':
        count_a += 1
    elif char == 'b':
        count_b += 1
    elif char == 'c':
        count_c += 1
    
    # Calculate the current coordinate
    coord = (count_a - count_b, count_b - count_c)
    
    # If this coordinate has been seen before, we found balanced substrings
    result += counts[coord]
    
    # Record this coordinate
    counts[coord] += 1

print(result)
