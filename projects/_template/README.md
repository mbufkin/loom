# New curriculum (template)

Copy this folder to start a new curriculum. The **program** stays at the repo
root; this is only **data**.

```bash
cp -a projects/_template projects/my-district
# put files in projects/my-district/sources/
./run-audit my-district
```

## Checklist

1. Choose a slug id: lowercase letters, digits, hyphens (`my-district-2026`).
2. Copy `_template` → `<data root>/projects/<id>/`.
3. Drop curriculum files into `sources/` (any supported format).
4. Optionally add a school calendar — see below.
5. Run `./run-audit <id>` (models must be up — see `OPERATORS.md`).
6. Collect `output/GLOBAL-AUDIT-REPORT.pdf` and `output/03-year-calendar-map.md`.

**MUST NOT** put pipeline scripts here — only curriculum inputs and generated
artifacts.

## School calendar — optional, and addable later

A new curriculum starts with **no** calendar. That is a supported state:

| | Pacing mode | What you get |
|---|---|---|
| No calendar | `sequential` | Units placed in order (Unit 1, Unit 2, …), no dates |
| Calendar present | `dated` | Units on real dates, holidays and staff days skipped, dated year-at-a-glance |

Every other part of the audit — what documents exist, what is missing, whether
materials match their unit — is identical either way. Only the pacing plan
changes.

To add one, copy [`school-calendar.example.yaml`](school-calendar.example.yaml)
to `school-calendar.yaml` and edit it; the example documents every field. Then
re-run the audit and the pacing plan upgrades from sequential to dated.

If your district publishes its calendar as a PDF or image, drop it in
[`reference/`](reference/) alongside, so a reviewer can check the structured
file against the source.
