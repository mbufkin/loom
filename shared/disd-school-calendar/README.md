# Dallas ISD school-year spine (shared)

**Authoritative district calendar** for any Dallas ISD curriculum dataset.

| File | Role |
|------|------|
| `DISD-Academic-Calendar-2026-2027.png` | Official one-page Traditional calendar (English/Spanish) |
| `school-calendar.yaml` | Machine-readable spine consumed by `rollup.py` (instructional days, blocked dates, nine weeks) |

## How Crystallize uses this

Without `projects/<id>/school-calendar.yaml`, rollup falls back to **sequential** mode (no real dates). With it, you get:

- `pacing-plan.yaml` in **dated** mode
- `output/03-year-calendar-map.md` (year-at-a-glance by grading period)
- Correct skipped holidays / PD / fall break when placing unit day grids

## Install into a new project

```bash
# From repo root
cp shared/disd-school-calendar/school-calendar.yaml projects/<id>/
mkdir -p projects/<id>/reference
cp shared/disd-school-calendar/DISD-Academic-Calendar-2026-2027.png projects/<id>/reference/
python3 rollup.py --project <id> --force
```

`projects/_template/` already ships with both files so `cp -a projects/_template projects/<id>` includes the DISD spine by default.

## Source / verification

- Official listing: [Dallas ISD District Calendars](https://www.dallasisd.org/about/about-dallas-isd/district-calendars) → **2026–2027 Traditional and ADSY Calendars**
- Structured YAML verified against the Traditional calendar image (first day **2026-08-11**, last day **2027-05-26**, nine-week `[` / `]` markers).
- **Traditional calendar only** (not ADSY extended start). If a campus is ADSY, fork this file and override `first_day_of_class` / blocked days.

## Re-verify when DISD publishes a new year

1. Download the new Traditional PDF/PNG into this folder.
2. Update `school-calendar.yaml` dates from the legend.
3. Copy into `projects/_template/` and any active Dallas projects.
4. `python3 rollup.py --project <id> --force` on each Dallas dataset.
