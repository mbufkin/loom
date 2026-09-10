# Test data root

A synthetic `DATA_DIR` (see `loom_paths.py`) used by the pipeline tests.

## Why this exists

The rollup and schema tests used to read a real district's corpus committed
under `projects/`. That coupled two things that should never have been
coupled:

- **Shipping.** The program and its data lived in the same directory, so
  handing someone the program handed them a district's curriculum structure —
  unit titles, pacing, calendars.
- **Test isolation.** `test_rollup.py` invoked `rollup.py --force` against
  that live tree, so simply running the suite rewrote a committed file. It
  also silently corrupted it on Windows, where the default text encoding is
  `cp1252` rather than UTF-8.

`sample-cte-demo` replaces it: invented courses, an invented district, and a
2030-2031 academic year that nobody can mistake for a real one.

## Layout

Mirrors a real data root, so tests exercise the same `project_dir()` path
resolution that production uses:

```
data-root/
  projects/
    sample-cte-demo/
      manifest.yaml               6 two-day units
      school-calendar.yaml        4 quarters, holidays, a fall break
      units/<unit-id>/calendar.yaml
```

## How tests use it

Point both this process and any subprocess at a *copy* of the fixture, never
the fixture itself — stages write `pacing-plan.yaml` and `output/` next to
their inputs, and a test that mutates its own fixture is a test that passes
once:

```python
root = Path(tempfile.mkdtemp()) / "data"
shutil.copytree(FIXTURE_DATA_ROOT, root)
os.environ["LOOM_HOME"] = str(root)   # for subprocesses
audit_lib.DATA_DIR = root             # for this process
```

## Deliberate properties

The assertions in `test_rollup.py` depend on these, so change them together:

| Property | Value |
|---|---|
| First / last day of class | 2030-08-05 / 2031-05-23 (both weekdays) |
| Units, each 2 days | 6 (so a sequential placement consumes 12 days) |
| A weekday in no grading period | 2030-10-11 (q1 ends Oct 10, q2 opens Oct 15) |
| A blocked date inside a holiday span | 2030-12-25 (Winter Break) |
| A blocked single date | 2030-09-02 (Labor Day) |

The calendar also covers every branch of `rollup.collect_blocked_dates`: bare
date strings, `{date, name}` holidays, `{begin, end, name}` spans, and the
separate `fall_break` block.
