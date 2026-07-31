# Lesson 3: Nested Loops and Loop Patterns

**Course:** Computer Science I
**Duration:** 50 minutes
**Quality Tier:** Very High

---

## TEKS Alignment

- **§126.33(c)(2)(B)** — identify and use looping structures to repeat a set of statements
- **§126.33(c)(2)(C)** — identify and use indefinite and definite loops
- **§126.33(c)(2)(D)** — trace the execution of algorithms and identify logic errors
- **§126.33(c)(4)(A)** — create an algorithm to solve a problem
- **§126.33(c)(4)(C)** — analyze the efficiency of an algorithm

## Learning Objective

Students will be able to write and trace nested loops combining `for` and `while`, identify common loop patterns, and analyze the computational cost of nested iteration.

**Student-Friendly:** "I can put a loop inside another loop to handle multi-dimensional data — like a seating chart with rows and columns — and I can estimate how many total times the inner code runs."

## Rationale

Nested loops unlock exponentially more powerful programs. A single loop processes one dimension — a list. Nested loops process two dimensions — grids, tables, matrices, pixels on a screen. Every data scientist, game developer, and image processing engineer relies on nested loops daily. Understanding how loops compose is also essential for analyzing algorithmic efficiency (Big O notation), a foundational CS concept assessed on AP exams and in college coursework.

## Prerequisite Knowledge

- `for` loop with `range()` and sequence iteration (Lesson 1)
- `while` loop syntax and behavior (Lesson 2)
- Basic list operations (indexing, `len()`)

## Key Vocabulary

| Term | Definition |
|------|------------|
| Nested loop | A loop placed inside the body of another loop |
| Outer loop | The enclosing loop; runs once per "row" |
| Inner loop | The enclosed loop; runs completely for each outer iteration |
| Row-major order | Traversing a grid by completing each row before moving to the next |
| Accumulator pattern | Using a variable to collect results across loop iterations |
| Big O notation | A measure of how runtime grows with input size |

## Research Basis

1. **du Boulay, B. (1986).** Some difficulties of learning to program. *Journal of Educational Computing Research, 2*(1), 57–73. — Identifies that comprehension of nested structures (loops within loops, conditionals within loops) is a critical transition point in learning programming. Novices often conflate the outer and inner loop's behavior.

2. **Lister, R., et al. (2004).** A multi-national study of reading and tracing skills in novice programmers. *ACM SIGCSE Bulletin, 36*(4), 119–150. — Demonstrates that tracing ability (predicting execution step by step) is a prerequisite to writing correct code, especially for nested constructs. This lesson prioritizes tracing before writing.

3. **Ginat, D. (2004).** Identifying and addressing algorithmic misconceptions in nested loops. *Computer Science Education, 14*(4), 301–322. — Documents common nested-loop errors (confusing inner vs. outer variable, incorrect initialization placement) and provides remediation strategies used in this lesson.

## Materials & Supplies

- Computers with Python 3
- Grid paper handout (10×10, for manual tracing)
- Colored pencils (two colors per student — one for outer, one for inner)
- Pattern matching cards (6 card decks per pair)

## Lesson Structure

---

### 1. Anticipatory Set / Hook (5 min)

**Activity: "Attendance Grid"**

Teacher draws a 3×4 grid on the board (3 rows, 4 columns). Each cell represents a student. *"I need to call on every student. I could call row 1 left to right, then row 2 left to right, then row 3. How many 'steps' does that take?"* (12)

*"Now imagine I have 1000 rows and 1000 columns. If I check every cell, how many checks?"* (1,000,000)

**Teacher says:** *"That's a nested loop — one loop for rows, one for columns. Today you'll learn how to write them, trace them, and figure out how many times they run — which is the key to writing fast programs."*

---

### 2. Objective & Purpose (2 min)

Display learning objective. Highlight three verbs: **write** (produce code), **trace** (predict execution), **analyze** (measure efficiency).

*"By the end of class, you'll not only write nested loops — you'll be able to tell me exactly how many times the inner code runs, which is the foundation of computer science's most important skill: making programs fast."*

---

### 3. Direct Instruction / Input (12 min)

#### Nested Loop Mechanics (4 min)

Present the simplest nested loop:

```python
for row in range(3):
    for col in range(4):
        print(f"({row}, {col})", end=" ")
    print()
```

**Output:**
```
(0, 0) (0, 1) (0, 2) (0, 3) 
(1, 0) (1, 1) (1, 2) (1, 3) 
(2, 0) (2, 1) (2, 2) (2, 3) 
```

**Explain the execution model:**
1. `row` = 0 → enter inner loop → `col` = 0, 1, 2, 3 → inner finishes → `print()` (newline)
2. `row` = 1 → enter inner loop → `col` = 0, 1, 2, 3 → inner finishes → `print()` (newline)
3. `row` = 2 → enter inner loop → `col` = 0, 1, 2, 3 → inner finishes → `print()` (newline)
4. Outer loop finishes

**Key insight:** The inner loop COMPLETES all its iterations for EACH iteration of the outer loop. Total iterations = outer × inner = 3 × 4 = 12.

#### Common Patterns (4 min)

**Pattern 1: Accumulator in nested loop (sum a grid)**

```python
grid = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
total = 0
for row in grid:
    for cell in row:
        total = total + cell
print(total)  # 45
```

**Pattern 2: Conditional inside nested loop (count evens)**

```python
count = 0
for i in range(5):
    for j in range(5):
        if (i + j) % 2 == 0:
            count = count + 1
print(count)  # 13
```

**Pattern 3: Triangle pattern (inner range depends on outer)**

```python
for i in range(1, 6):
    line = ""
    for j in range(i):
        line = line + "*"
    print(line)
```

**Output:**
```
*
**
***
****
*****
```

#### Efficiency Analysis (4 min)

Introduce the intuition for Big O:

| Pattern | Outer | Inner | Total iterations | Big O |
|---------|-------|-------|-----------------|-------|
| Fixed nested | `n` | `m` | `n × m` | O(n×m) |
| Square nested | `n` | `n` | `n²` | O(n²) |
| Triangle nested | `n` | `i` (grows) | `n(n+1)/2` | O(n²) |
| Single loop | `n` | — | `n` | O(n) |

**Live demonstration:** Run this with increasing sizes and time it:

```python
import time
n = 1000
start = time.time()
total = 0
for i in range(n):
    for j in range(n):
        total = total + 1
end = time.time()
print(f"n={n}: {end - start:.2f}s, total={total}")
```

Try n=100, then n=1000, then n=2000 (if time permits). Students see n=1000 takes ~10x longer than n=100 because 1000² = 1,000,000 vs 100² = 10,000.

---

### 4. Modeling / "I Do" (8 min)

**Problem: "Print a multiplication table from 1 to 5."**

**Teacher thinks aloud:**

*"I need a grid. Rows = 1 to 5, columns = 1 to 5. That's a nested loop: outer loop for the row number, inner loop for the column number. At each cell, I multiply row × column."*

```python
# Multiplication table 1-5
for row in range(1, 6):
    for col in range(1, 6):
        product = row * col
        print(f"{product:4}", end="")
    print()
```

**Trace together (first 2 rows):**

| `row` | `col` | `product` | Output (partial) |
|-------|-------|-----------|------------------|
| 1 | 1 | 1 | `   1` |
| 1 | 2 | 2 | `   2` |
| 1 | 3 | 3 | `   3` |
| 1 | 4 | 4 | `   4` |
| 1 | 5 | 5 | `   5` |
| 1 | — | — | (newline) |
| 2 | 1 | 2 | `   2` |
| 2 | 2 | 4 | `   4` |
| … | … | … | … |

*"Notice the inner variable `col` resets to 1 for EACH new row. That's critical. If I forgot to reset it — but with `for` loops, Python handles that automatically."*

**Now a harder trace (triangle pattern):**

```python
total = 0
for i in range(4):
    for j in range(i + 1):
        total = total + 1
print(total)  # ?
```

**Teacher traces with student input:**

| `i` | `j` range | inner iterations | `total` after |
|-----|-----------|-----------------|---------------|
| 0 | 0–0 | 1 | 1 |
| 1 | 0–1 | 2 | 3 |
| 2 | 0–2 | 3 | 6 |
| 3 | 0–3 | 4 | 10 |

*"So the output is 10. The pattern is 1 + 2 + 3 + 4 = 10. For n=4, total = n(n+1)/2 = 4×5/2 = 10."*

---

### 5. Check for Understanding (4 min)

**Strategy: Pattern Matching Cards**

Students work in pairs. Each pair gets 6 cards: 3 code cards and 3 output cards. They match each code to its output.

**Card A (code):**
```python
for i in range(3):
    for j in range(2):
        print(i, j)
```
**Matches: Output:**
```
0 0
0 1
1 0
1 1
2 0
2 1
```

**Card B (code):**
```python
for i in range(3):
    print(i)
    for j in range(2):
        print(j)
```
**Matches: Output:**
```
0
0
1
1
0
1
2
0
1
```

**Card C (code):**
```python
for i in range(3):
    for j in range(i):
        print(i, j)
```
**Matches: Output:**
```
1 0
2 0
2 1
```

Circulate and check matches. Common misconception: Card B — students think output matches Card A. Discuss WHY they differ (the `print(i)` is OUTSIDE the inner loop in Card B).

---

### 6. Guided Practice / "We Do" (8 min)

**Activity: Three Guided Problems**

**Problem 1 (complete the trace table):**

```python
result = ""
for ch in "abc":
    for num in "12":
        result = result + ch + num
```

| `ch` | `num` | `result` |
|------|-------|----------|
| 'a' | '1' | "a1" |
| 'a' | '2' | "a12" |
| 'b' | '1' | "a12b1" |
| 'b' | '2' | "a12b12" |
| 'c' | '1' | "a12b12c1" |
| 'c' | '2' | "a12b12c12" |

**Problem 2 (identify the bug):**

```python
# Intended: print a 3x3 grid of coordinates
for x in range(3):
    for y in range(3):
        print(f"({x},{y})")
print("---")
# Student wrote this instead:
for x in range(3):
    for y in range(3):
        print(f"({x},{y})")
print("---")
```

*Wait — those are identical. What if the student indented wrong?*

Teacher presents the buggy version:

```python
for x in range(3):
    for y in range(3):
        print(f"({x},{y})")
    print("---")  # BUG: this runs after EACH row, not once
```

**Problem 3 (flip the nesting):**

How does the output change if we swap outer/inner?

```python
# Version A
for row in range(3):
    for col in range(4):
        print(f"({row},{col})", end=" ")
    print()

# Version B (swapped)
for col in range(4):
    for row in range(3):
        print(f"({row},{col})", end=" ")
    print()
```

A prints row-by-row. B prints column-by-column. Students predict, then run to verify.

---

### 7. Independent Practice / "You Do" (8 min)

**Level 1 (Recall):**
Write a nested loop that prints a 4×6 rectangle of `#` characters.

**Level 2 (Apply):**
Write a program that creates a 5×5 grid where each cell contains the product of its row index and column index (0-based). Print the grid.

**Level 3 (Create):**
Write a program that draws a diagonal line of `\` characters across a 10×10 grid. That is, print 10 rows where row `i` has `i` spaces followed by `\`.

**Differentiation:**
- **Struggling:** Level 1 only with a pre-written outer loop skeleton
- **On-level:** Levels 1 and 2
- **Advanced:** All three levels. Extension: draw an X shape across the entire grid (both diagonals)

---

### 8. Closure / Exit Ticket (3 min)

**Exit Ticket:**

```
Name: ____________________

1. How many total times does "Hello" print?
   for a in range(4):
       for b in range(3):
           print("Hello")
   Answer: _______

2. What is the output of:
   for i in range(1, 4):
       for j in range(1, i+1):
           print(i, end="")
       print()
   Answer:
   ___
   ___
   ___

3. If a nested loop has an outer loop of n iterations and an inner
   loop of n iterations, total work is _____ (Big O).

4. One thing I'm still confused about:
   ________________________________________
```

---

## ELPS Strategies

| Strategy | Implementation |
|----------|---------------|
| **2(C)** Learn new language through content | Sentence stems for describing nested behavior |
| **2(E)** Use visual supports | Two-color tracing system (outer=blue, inner=green) |
| **3(F)** Ask and answer questions | Think-pair-share before each CFU card match |
| **4(G)** Understand complex instructions | Demonstration + written steps for each practice level |

## Special Education Accommodations

- **Grid paper handout** pre-labeled with loop variable placeholders
- **Card sorting activity** reduces cognitive load by separating identification from writing
- **Color coding:** Outer loop traced in blue, inner in green on handouts
- **Oral option:** Students may explain output verbally instead of writing for CFU

## GT Extensions

- Explore `break` and `continue` inside nested loops — which loop does `break` exit?
- Challenge: Write a program to print a checkerboard pattern (alternating `#` and space) in an 8×8 grid
- Research: What is the difference between O(n²) and O(n log n)? Find an algorithm for each

## Resources

- Real Python — Nested Loops: https://realpython.com/python-nested-loops/
- Visualize nested loops: https://pythontutor.com/
- Big O Cheatsheet: https://www.bigocheatsheet.com/
