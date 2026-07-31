# Lesson 1: Introduction to Loops — The `for` Loop

**Course:** Computer Science I
**Duration:** 50 minutes
**Quality Tier:** Very High

---

## TEKS Alignment

- **§126.33(c)(2)(B)** — identify and use looping structures to repeat a set of statements
- **§126.33(c)(2)(C)** — identify and use definite loops (e.g., `for` loops)
- **§126.33(c)(3)(A)** — create variables of different data types
- **§126.33(c)(4)(A)** — create an algorithm to solve a problem
- **§126.33(c)(4)(B)** — create flowcharts to represent algorithms

## Learning Objective

Students will be able to write `for` loops using `range()` and sequence iteration in Python to repeat a block of instructions a known number of times.

**Student-Friendly:** "I can write a `for` loop that runs exactly the number of times I need — like telling a robot 'repeat this five times' instead of writing the same instruction five times."

## Rationale

Loops are one of the three fundamental control structures in programming (sequence, selection, iteration). Without loops, every repeated task must be written line by line — impractical for any real program. Understanding `for` loops is the gateway to processing collections, automating repetitive tasks, and writing efficient code. This skill transfers directly to careers in software development, data analysis, automation engineering, and game design.

## Prerequisite Knowledge

- Basic variable assignment and data types (int, str, list)
- `print()` function
- Indentation as code blocks in Python

## Key Vocabulary

| Term | Definition |
|------|------------|
| Loop | A programming construct that repeats a block of code |
| Iteration | One execution of the loop body |
| `for` loop | A definite loop that iterates over a sequence |
| `range()` | A function that generates a sequence of numbers |
| Loop body | The indented block of code executed each iteration |
| Iterable | An object capable of returning its members one at a time |

## Research Basis

This lesson is informed by the following educational research:

1. **Linn, M. C., & Clancy, M. J. (1992).** The case for case studies of programming problems. *Communications of the ACM, 35*(3), 121–132. — Demonstrates that presenting programming patterns through worked examples before independent practice improves novice comprehension. This lesson uses the "pattern-first" approach: students see the loop pattern, trace it, then apply it.

2. **Robins, A., Rountree, J., & Rountree, N. (2003).** Learning and teaching programming: A review and discussion. *Computer Science Education, 13*(2), 137–172. — Identifies that novices struggle with the "notional machine" of loop execution. This lesson addresses this through explicit tracing activities before students write loops.

3. **Sorva, J. (2013).** Notional machines and introductory programming education. *ACM Transactions on Computing Education, 13*(2), 1–31. — Recommends program visualization for loop comprehension. The lesson incorporates a trace-table exercise where students manually track variable state across iterations.

## Materials & Supplies

- Computers with Python 3 installed (or browser-based IDE like Replit)
- Student handout: "Loop Tracing Template" (trace table with columns for iteration number, variable values, output)
- Teacher slide deck (6 slides: hook, pattern, syntax, trace, code-along, prompt)
- Exit ticket slip (half-sheet)
- Timer displayed on screen

## Lesson Structure

---

### 1. Anticipatory Set / Hook (5 min)

**Activity: "The Annoying Robot"**

Teacher projects a Python file containing:

```python
print("Thank you for your patience!")
print("Thank you for your patience!")
print("Thank you for your patience!")
print("Thank you for your patience!")
print("Thank you for your patience!")
```

Ask: *"What is wrong with this code? What if I needed 100 thank-yous? 1000?"*

Students turn and talk (30 sec), then share out. Guide them to the idea of "repetition without repeating yourself." Introduce the word **loop**.

**Teacher says:** *"A loop lets a computer do something over and over without you having to write it over and over. Today, you'll learn Python's most common loop — the `for` loop — and you'll never copy-paste a line of code again."*

---

### 2. Objective & Purpose (2 min)

Display the learning objective on the screen. Read it aloud. Briefly unpack: *"Write"* (you'll produce code), *"using range() and sequence iteration"* (two specific techniques), *"known number of times"* (definite iteration — you know in advance how many repetitions you need).

**Connection to the hook:** *"By the end of this class, you'll be able to write a loop that prints 'thank you' 100 times in just two lines of code."*

---

### 3. Direct Instruction / Input (12 min)

#### Pattern Introduction (4 min)

Present the general pattern of a `for` loop:

```python
for variable in sequence:
    # loop body — indented
    print(variable)
```

Define each part:
- `for` — keyword that starts the loop
- `variable` — a new variable that takes each value from the sequence, one per iteration
- `in` — keyword linking the variable to the sequence
- `sequence` — the collection of items to iterate over
- `:` — colon marks the start of the loop body
- **Indented block** — the loop body, executed once per iteration

#### `range()` Function (4 min)

Present the three forms of `range()`:

```python
range(stop)        # 0 to stop-1
range(start, stop) # start to stop-1
range(start, stop, step) # start to stop-1, incrementing by step
```

**Live demonstration:** Run each in a Python REPL, wrapping in `list()` to show the sequence:

```python
>>> list(range(5))
[0, 1, 2, 3, 4]
>>> list(range(2, 7))
[2, 3, 4, 5, 6]
>>> list(range(1, 10, 2))
[1, 3, 5, 7, 9]
```

#### Iterating Over Sequences (4 min)

Show that `for` works on any iterable:

```python
# String iteration
for letter in "hello":
    print(letter)

# List iteration
fruits = ["apple", "banana", "cherry"]
for fruit in fruits:
    print(fruit)

# Using range for counted repetition
for i in range(5):
    print("Thank you for your patience!")
```

---

### 4. Modeling / "I Do" (8 min)

**Think-aloud trace of a `for` loop:**

Project this code:

```python
total = 0
for n in range(1, 5):
    total = total + n
    print(f"n={n}, total={total}")
print("Done:", total)
```

**Teacher says (thinking aloud):**

*"Before the loop, total is 0. The loop says 'for n in range(1, 5)' — that means n will take the values 1, 2, 3, 4. Let me trace what happens each time:*

- *Iteration 1: n = 1. total = 0 + 1 = 1. Print 'n=1, total=1'*
- *Iteration 2: n = 2. total = 1 + 2 = 3. Print 'n=2, total=3'*
- *Iteration 3: n = 3. total = 3 + 3 = 6. Print 'n=3, total=6'*
- *Iteration 4: n = 4. total = 4 + 4 = 8. Print 'n=4, total=8'*

*After the loop finishes, we print 'Done: 8'. Notice the indentation: the print inside the loop runs 4 times, but the final print runs only once because it's outside the loop."*

**Trace table on the board:**

| Iter | `n` | `total` | Output |
|------|-----|---------|--------|
| 1 | 1 | 1 | n=1, total=1 |
| 2 | 2 | 3 | n=2, total=3 |
| 3 | 3 | 6 | n=3, total=6 |
| 4 | 4 | 8 | n=4, total=8 |
| — | — | — | Done: 8 |

---

### 5. Check for Understanding (4 min)

**Strategy: Fist-to-Five + Mini-Whiteboard**

1. **Fist-to-Five (2 min):** *"How confident are you that you can predict what `for i in range(3): print(i*i)` will output?"* (students show 0–5 fingers). For 3 or below, pull those students into the guided practice group.

2. **Mini-Whiteboard (2 min):** *"Write what this code outputs:"*

```python
total = 0
for x in range(4):
    total = total + 2
print(total)
```

Reveal answer: 8. Discuss why (loop runs 4 times, each adds 2, 0+2+2+2+2 = 8).

---

### 6. Guided Practice / "We Do" (8 min)

**Activity: Trace and Complete**

Students receive a handout with a trace table. Teacher leads through three problems:

**Problem A (complete trace table):**

```python
word = "code"
count = 0
for ch in word:
    if ch in "aeiou":
        count = count + 1
```

Fill trace table: | Iter | `ch` | `count` |
|------|------|---------|
| 1 | 'c' | 0 |
| 2 | 'o' | 1 |
| 3 | 'd' | 1 |
| 4 | 'e' | 2 |

**Problem B (fill in the blank):** *"Write a loop that prints the numbers 0, 2, 4, 6, 8:"*

```python
for i in range(__, __, __):
    print(i)
```

Answer: `range(0, 10, 2)` or `range(0, 9, 2)`

**Problem C (predict then run):** Students predict output, then verify by running:

```python
for i in range(3):
    for j in range(2):
        print(i, j)
```

*Note: This previews nested loops. Accept any reasonable prediction; the key is running it to see the result.*

---

### 7. Independent Practice / "You Do" (8 min)

Students complete three coding problems in their IDE:

**Level 1 (Recall):**
Write a `for` loop that prints each character of your first name on a separate line.

**Level 2 (Apply):**
Write a program that uses a `for` loop and `range()` to calculate the sum of all even numbers from 2 to 20 (inclusive). Output the total.

**Level 3 (Create):**
Write a program that asks the user for a number `n`, then uses a `for` loop with `range()` to print a multiplication table for `n` from 1 to 10.

**Differentiation:**
- **Struggling:** Start with Level 1 only, provide a partially written loop with blanks to fill
- **On-level:** Complete Levels 1 and 2
- **Advanced:** Complete all three levels. Extension: Try using `range()` with a negative step to count down from 10 to 1.

---

### 8. Closure / Exit Ticket (3 min)

**Exit Ticket (half-sheet, printed or digital form):**

```
Name: ____________________

1. How many times does this loop run?
   for i in range(7):
       print(i)
   Answer: _______

2. Write ONE line of code that uses range() to generate: 5, 8, 11, 14
   Answer: _______________________________

3. What is the output of this code?
   total = 0
   for num in [3, 5, 2]:
       total = total + num
   print(total)
   Answer: _______

4. Rate your understanding of for loops today (circle one):
   😊 Got it!  😐 Kind of  😕 Need help
```

Collect exit tickets as students leave. Sort into "Got it," "Almost," and "Need help" piles to inform next day's warm-up.

---

## ELPS Strategies

| Strategy | Implementation |
|----------|---------------|
| **1(A)** Use prior knowledge | Hook connects to real-world repetition concepts |
| **2(E)** Use visual/contextual cues | Slide deck with color-coded loop syntax; trace table graphic organizer |
| **3(E)** Share information in cooperative groups | Turn-and-talk during hook; pair programming during independent practice |
| **4(F)** Use accessible language | Sentence stems on handout: "The loop runs ___ times because ___" |

## Special Education Accommodations

- **Chunking:** Break instruction into segments with alternating activity types (5-2-12-8-4-8-8-3 minutes)
- **Scaffolded handout:** Trace table with first row pre-filled; partially written code with blanks
- **Visual timer** displayed throughout
- **Check-in:** Teacher circulates during independent practice, prioritizing students with IEPs

## GT Extensions

- Explore `enumerate()` as an alternative to `range(len(sequence))`
- Investigate: What happens if the sequence is empty? Write a loop over an empty list and observe the behavior.
- Challenge: Write a loop that computes the factorial of a number without using `math.factorial()`.

## Resources

- Codecademy Python Loops Lesson: https://www.codecademy.com/learn/learn-python-3
- Python Tutor (visual execution tracer): https://pythontutor.com/
- Swarthmore CS Loop Reference: https://www.cs.swarthmore.edu/courses/cs21book/python/loops.html
