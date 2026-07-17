# Lesson preserve spike (side only)

Not wired into `run_project.py`.

**Doctrine:** organize before paths → collect lesson plans into a unit group →
run dedicated Path A last (`single_lp` vs `lp_block`) with **A1–A7 depth** on
preserved LPs → `meeting_count` as metadata only → synthesize a gap plate only
when a signal says an LP should exist but none was found.

Depth artifacts: `units/<unit>/path_a_review.md` (+ `.json`).
A6 field remake is skipped (preserve mode).

```bash
cd ~/g10-control-center-loom
python3 experiments/lesson_preserve/run_spike.py --project dallas-career-2026
python3 experiments/lesson_preserve/test_spike.py
```

Outputs: `experiments/lesson_preserve/out/<project>/`
