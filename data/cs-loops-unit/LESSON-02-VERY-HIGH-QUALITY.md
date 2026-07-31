# Lesson 2: Condition-Controlled Loops — The `while` Loop

**Course:** Computer Science I
**Duration:** 50 minutes
**Quality Tier:** Very High

---

## TEKS Alignment

- **§126.33(c)(2)(B)** — identify and use looping structures to repeat a set of statements
- **§126.33(c)(2)(C)** — identify and use indefinite loops (e.g., `while` loops)
- **§126.33(c)(3)(A)** — create variables of different data types
- **§126.33(c)(4)(B)** — create flowcharts to represent algorithms

## Learning Objective

Students will be able to write `while` loops with boolean conditions to implement indefinite iteration, including sentinel-controlled and flag-controlled patterns.

**Student-Friendly:** "I can write a loop that keeps going until a condition changes — like 'keep asking for a password until the user gets it right' — without knowing in advance how many tries it will take."

## Rationale

While `for` loops are ideal when the number of iterations is known in advance, many real-world programming scenarios require repetition until a condition is met: validating user input, processing data until a file ends, waiting for a sensor reading, or running a game loop until the player quits. The `while` loop is the universal tool for these situations. Mastering it is essential for interactive programs, data validation, and event-driven systems.

## Prerequisite Knowledge

- `for` loop syntax and behavior (Lesson 1)
- Boolean expressions and comparison operators (`==`, `<`, `>`, `!=`, etc.)
- Variables and reassignment

## Key Vocabulary

| Term | Definition |
|------|------------|
| `while` loop | A loop that repeats as long as a boolean condition is true |
| Condition | A boolean expression checked before each iteration |
| Infinite loop | A loop whose condition never becomes false (program runs forever) |
| Sentinel value | A special value that signals the end of input |
| Flag variable | A boolean variable that controls when a loop stops |
| Loop-and-a-half | A pattern using `break` to exit from the middle of a loop |

## Research Basis

1. **Soloway, E. (1986).** Learning to program = learning to construct mechanisms and explanations. *Communications of the ACM, 29*(9), 850–858. — Identified that novices struggle with the "loop-and-a-half" pattern (read-process-loop vs. process-read-loop). This lesson explicitly teaches both patterns and when each applies.

2. **Pane, J. F., & Myers, B. A. (2001).** Studying the language and structure in non-programmers' solutions to programming problems. *International Journal of Human-Computer Studies, 54*(2), 237–264. — Found that non-programmers naturally describe indefinite repetition with "keep doing until" language, which maps directly to `while` loops. The lesson leverages this natural language mapping.

3. **Pea, R. D. (1986).** Language-independent conceptual "bugs" in novice programming. *Journal of Educational Computing Research, 2*(1), 25–36. — Documents the "infinite loop" misconception. This lesson addresses it directly through a debugging-first activity and a "loop guard" mental model.

## Materials & Supplies

- Computers with Python 3
- Student handout: "While Loop Patterns Reference Card"
- Red/green index cards (for CFU)
- Flowchart template (pre-printed)

## Lesson Structure

---

### 1. Anticipatory Set / Hook (5 min)

**Activity: "Password Check" simulation**

Teacher asks a volunteer to come to the front. Teacher says: *"I'm thinking of a secret number between 1 and 10. [Student], you can guess. I'll tell you if you're right or wrong, and you can keep guessing until you get it."*

Play one round. Then ask the class: *"How many times did [Student] guess? Did I know in advance? What if they guessed 20 times?"*

Draw the contrast: *"Yesterday, with `for` loops, we knew exactly how many times before we started. Today's loop — the `while` loop — keeps going until some condition tells it to stop. We don't need to know the count in advance."*

---

### 2. Objective & Purpose (2 min)

Display and read the learning objective. Emphasize the new concept: **indefinite iteration** — loops where the number of repetitions is determined *during* execution, not before.

*"By the end of class, you'll write a 'password checker' that keeps asking until the user gets it right — no matter how many wrong guesses they make."*

---

### 3. Direct Instruction / Input (12 min)

#### `while` Loop Syntax (4 min)

Present the pattern:

```python
while condition:
    # loop body — indented
    # must eventually make condition False
```

**Critical rules:**
1. `condition` is a boolean expression — checked before each iteration
2. If condition is `True`, the body runs; then check again
3. If condition is `False`, skip the body and continue after the loop
4. **The body must change something the condition checks** — or you get an infinite loop

**Live demonstration:**

```python
count = 0
while count < 5:
    print(f"Count is {count}")
    count = count + 1
print("Done!")
```

Trace the execution on the board:

| Check | `count < 5`? | `count` before | Action | `count` after |
|-------|-------------|----------------|--------|---------------|
| 1 | True | 0 | Print, add 1 | 1 |
| 2 | True | 1 | Print, add 1 | 2 |
| 3 | True | 2 | Print, add 1 | 3 |
| 4 | True | 3 | Print, add 1 | 4 |
| 5 | True | 4 | Print, add 1 | 5 |
| 6 | **False** | 5 | **Skip loop** | — |

#### Infinite Loops — What NOT to Do (4 min)

Project deliberately buggy code:

```python
# BUG: count never changes!
count = 0
while count < 5:
    print("Stuck forever!")
```

*"What happens? The condition is always True because count stays 0. We call this an **infinite loop**. Your computer will freeze, and you'll have to force-quit Python."*

**How to avoid it:** Every `while` loop body must include a statement that moves the condition closer to `False`.

**Live demo** (with a pre-set kill switch): Run the infinite loop for 2 seconds (Ctrl+C to break). Students see the real consequence.

#### Sentinel and Flag Patterns (4 min)

**Sentinel pattern:** Stop when a special input value is received:

```python
total = 0
value = int(input("Enter a number (-1 to quit): "))
while value != -1:
    total = total + value
    value = int(input("Enter a number (-1 to quit): "))
print(f"Total: {total}")
```

**Flag pattern:** Use a boolean variable to control the loop:

```python
found = False
numbers = [4, 8, 15, 16, 23, 42]
index = 0
search = 16

while not found and index < len(numbers):
    if numbers[index] == search:
        found = True
    else:
        index = index + 1

if found:
    print(f"Found at position {index}")
else:
    print("Not found")
```

---

### 4. Modeling / "I Do" (8 min)

**Problem: "Write a program that keeps asking for a password until the user enters 'opensesame'."**

**Teacher thinks aloud:**

*"I know the user might guess 3 times or 30 times — I don't know in advance. So I need a `while` loop. What's my condition? 'Keep going while the password is wrong.' Let me set up a variable before the loop starts."*

```python
password = input("Enter the password: ")
while password != "opensesame":
    print("Wrong! Try again.")
    password = input("Enter the password: ")
print("Access granted!")
```

**Teacher continues:** *"I could also use a flag variable. Watch how the same program looks with a flag:"*

```python
granted = False
while not granted:
    pwd = input("Enter the password: ")
    if pwd == "opensesame":
        granted = True
    else:
        print("Wrong! Try again.")
print("Access granted!")
```

*"The flag version is useful when I need to check multiple conditions before deciding to stop. The sentinel version is simpler when there's one 'special' input value."*

**Flowchart modeling:** Draw the flowchart for a sentinel-controlled `while` loop on the board:

```
       ┌──────────┐
       │  Start   │
       └────┬─────┘
            ↓
       ┌──────────┐
       │ Get input│
       └────┬─────┘
            ↓
      ┌──────────┐
      │ input == │  No ──→ ┌──────────┐
      │ sentinel?│────────→│ Process  │
      └──────────┘         └────┬─────┘
            │ Yes               ↓
            ↓              ┌──────────┐
       ┌──────────┐        │ Get input│
       │  Done    │        └──────────┘
       └──────────┘              │
                                 └────→ (back to condition)
```

---

### 5. Check for Understanding (4 min)

**Strategy: Red/Green Cards**

Teacher projects three code snippets. Students hold up green if the loop will end, red if it will run forever.

1. 
```python
x = 10
while x > 0:
    print(x)
    x = x - 1
```
**Green** (x decreases, will reach 0)

2. 
```python
x = 10
while x > 0:
    print(x)
```
**Red** (x never changes — infinite loop)

3. 
```python
x = 1
while x > 0:
    print(x)
    x = x + 1
```
**Red** (x increases, will always be > 0 — infinite loop)

---

### 6. Guided Practice / "We Do" (8 min)

**Activity: Complete the Pattern**

Students work in pairs with one computer. Teacher projects three partially written programs:

**Problem 1 (sentinel):** Complete the loop that sums numbers until the user enters 0:

```python
total = 0
num = int(input("Enter a number (0 to stop): "))
while ________:
    total = total + num
    ________
print("Sum:", total)
```

Answer: `num != 0` and `num = int(input("Enter a number (0 to stop): "))`

**Problem 2 (flag):** Complete the loop that searches for "apple" in a list:

```python
fruits = ["banana", "orange", "apple", "grape"]
found = False
i = 0
while not found and i < len(fruits):
    if fruits[i] == "apple":
        ________
    ________
if found:
    print("Found it!")
else:
    print("Not found")
```

Answer: `found = True` and `i = i + 1`

**Problem 3 (conversion):** Convert this `for` loop to a `while` loop:

```python
for i in range(1, 6):
    print(i * i)
```

Answer:

```python
i = 1
while i <= 5:
    print(i * i)
    i = i + 1
```

---

### 7. Independent Practice / "You Do" (8 min)

Students write three programs:

**Level 1 (Recall):**
Write a `while` loop that prints the numbers from 10 down to 1.

**Level 2 (Apply):**
Write a program that asks the user to guess a secret number (e.g., 7). Keep asking until they get it right. After each wrong guess, tell them "Too high" or "Too low."

**Level 3 (Create):**
Write a program that reads integers from the user until they enter -1. Then print the sum, average, and count of the numbers entered (excluding the -1).

**Differentiation:**
- **Struggling:** Provide the loop structure skeleton; students fill in conditions only
- **On-level:** Complete Levels 1 and 2
- **Advanced:** Complete all three levels. Extension: Add input validation — reject non-integer inputs with a try/except

---

### 8. Closure / Exit Ticket (3 min)

**Exit Ticket:**

```
Name: ____________________

1. How many times will this loop run?
   x = 0
   while x < 3:
       x = x + 1
   Answer: _______

2. What is WRONG with this code?
   x = 5
   while x > 0:
       print(x)
   Answer: _______________________________

3. Write a while loop that prints "Hello" 4 times.
   (Hint: use a counter variable)

4. What is one real-world situation where you'd use a while loop
   instead of a for loop?
   ________________________________________
```

---

## ELPS Strategies

| Strategy | Implementation |
|----------|---------------|
| **2(D)** Monitor understanding | Red/green card checks provide nonverbal self-assessment |
| **2(I)** Demonstrate listening comprehension | Students explain why a loop is infinite in their own words |
| **3(B)** Use new vocabulary in context | Sentence frames for explaining loop behavior: "The loop continues while ___" |
| **4(C)** Use writing to communicate | Exit ticket requires written explanation of loop behavior |

## Special Education Accommodations

- **Modified handout:** Flowchart template with partial labels; pre-printed reference card for while syntax
- **Extended time:** Independent practice shortened — complete Level 1 and start Level 2
- **Pairing:** Strategic pairing with a stronger partner during guided practice
- **Visual supports:** Color-coded flowchart components (condition = diamond in yellow, action = rectangle in blue)

## GT Extensions

- Explore `break` and `continue` to refine loop control
- Challenge: Rewrite the search program to find ALL occurrences of a value, not just the first
- Research: What is a "post-test loop" (do-while)? Why doesn't Python have one, and how can you simulate it?

## Resources

- Real Python Guide to While Loops: https://realpython.com/python-while-loop/
- Pythontutor.com (visual execution): https://pythontutor.com/
- GeeksforGeeks Python While Loop: https://www.geeksforgeeks.org/python-while-loop/
