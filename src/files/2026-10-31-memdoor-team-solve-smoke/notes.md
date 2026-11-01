<!-- proposal-a -->
## Proposal A

### Algorithm

We use a coordinate system approach based on cumulative counts of each character.

Let `count_a`, `count_b`, and `count_c` represent the number of occurrences of 'a', 'b', and 'c' respectively up to the current position. 

We define a coordinate `(x, y)` where:
  - x = count_a - count_b
  - y = count_b - count_c

The key insight is that a substring is balanced if and only if the cumulative counts at its start and end positions are equal in terms of this coordinate system. 

### Pseudocode

```
counts = defaultdict(int)
counts[(0, 0)] = 1  # Initialize with the empty prefix
result = 0

count_a = count_b = count_c = 0

for char in string:
    if char == 'a':
        count_a += 1
    elif char == 'b':
        count_b += 1
    elif char == 'c':
        count_c += 1

    coord = (count_a - count_b, count_b - count_c)
    result += counts[coord]
    counts[coord] += 1
```

### Invariant

At each step, `counts` stores how many times we've seen each coordinate so far. 

### Correctness

If two positions have the same coordinate, then the substring between them has equal counts of 'a', 'b', and 'c'. This is because:
  - For a substring from position i to j (exclusive), we have:
    - count_a[j] - count_a[i] = 0
    - count_b[j] - count_b[i] = 0
    - count_c[j] - count_c[i] = 0
  - This means the counts are equal, and hence the substring is balanced.

### Complexity

Time: O(N) where N is the length of the string. We traverse the string once.
Space: O(N) in the worst case for storing coordinates (though it's actually bounded by the range of possible differences).

### Edge Cases

1. Empty string - handled by the fact that we start with `counts[(0, 0)] = 1`
2. All same characters - returns 0 as expected
3. No balanced substrings - correctly returns 0
4. Mixed strings - correctly counts all balanced substrings

<!-- proposal-b -->
## Proposal B

We could also solve this using brute-force, but it would be O(N^3) which is too slow for N=200000.

<!-- proposal-c -->
## Proposal C

Another approach is to use prefix sums but with a different coordinate system, like tracking (count_a - count_b, count_a - count_c), or using a single difference value and mapping it to a 2D space. The current approach is more direct.

<!-- proposal-d -->
## Proposal D

We could also optimize by using a more compact representation for the coordinate space, but given the constraints, this is not necessary.
