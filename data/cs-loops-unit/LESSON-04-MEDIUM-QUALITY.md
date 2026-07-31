# Lesson 4: Loop Applications in Data Processing

**Course:** Computer Science I
**Duration:** 50 minutes
**Quality Tier:** Medium

---

## TEKS Alignment

- **§126.33(c)(2)(B)** — looping structures to repeat statements
- **§126.33(c)(2)(C)** — definite and indefinite loops
- **§126.33(c)(3)(A)** — create variables of different data types

## Learning Objective

Students will apply for loops and while loops to process lists of data.

**Student-Friendly:** "I can use loops to do something with every item in a list."

## Rationale

Knowing loops is important for processing data. Data is everywhere in the real world and loops let you process it.

## Prerequisite Knowledge

- Lists in Python
- For loops
- While loops

## Key Vocabulary

| Term | Definition |
|------|------------|
| Data processing | Using code to work with data |
| Iteration | Going through items one by one |

## Research Basis

Research shows that students learn programming better when they practice with real-world examples. This lesson uses data analysis examples to help students apply loops. (Source: Various computer science education research articles.)

## Materials & Supplies

- Computers
- Python

## Lesson Structure

---

### 1. Anticipatory Set / Hook (5 min)

**Activity:** Show students a list of temperatures. Ask: "How would we find the average?" Discuss briefly.

---

### 2. Objective & Purpose (2 min)

Review today's objective. Explain that loops help process data efficiently.

---

### 3. Direct Instruction / Input (10 min)

**Processing a list with a for loop:**

```python
temperatures = [72, 68, 75, 80, 78, 71, 69]
total = 0
for temp in temperatures:
    total = total + temp
average = total / len(temperatures)
print(f"Average: {average}")
```

**Finding max/min:**

```python
scores = [88, 92, 79, 93, 85]
highest = scores[0]
for score in scores:
    if score > highest:
        highest = score
print(f"Highest: {highest}")
```

**Filtering with a loop:**

```python
numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
even_numbers = []
for n in numbers:
    if n % 2 == 0:
        even_numbers.append(n)
print(even_numbers)
```

---

### 4. Modeling / "I Do" (8 min)

Walk through the temperature example step by step. Show how the loop variable changes each iteration.

---

### 5. Check for Understanding (5 min)

Ask: What does this code output?

```python
values = [10, 20, 30]
result = 0
for v in values:
    result = result + v
print(result)
```

Answer: 60

---

### 6. Guided Practice / "We Do" (10 min)

Work through these problems with the class:

1. Write a loop that counts how many numbers in a list are greater than 50
2. Write a loop that builds a new list containing the square of each number

---

### 7. Independent Practice / "You Do" (8 min)

Write a program that:
1. Creates a list of 5 numbers (hardcoded)
2. Uses a loop to calculate and print the sum
3. Uses a loop to find and print the smallest number
4. Uses a loop to create a new list with each number doubled

---

### 8. Closure / Exit Ticket (2 min)

**Exit Ticket:**

```
1. What does this code output?
   nums = [2, 4, 6]
   total = 0
   for n in nums:
       total = total + n
   print(total)

2. How would you find the largest number in a list using a loop?
```

---

## ELPS Strategies

Provide sentence stems and pair students with different language backgrounds.

## Special Education Accommodations

Allow extra time and provide partially written code.

## GT Extensions

Try processing data from a CSV file using loops.

## Resources

- w3schools Python Loops
- GeeksforGeeks
