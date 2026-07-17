# New curriculum dataset (template)

Copy this folder to start a new corpus. The **program** stays at the repo root; this is only **data**.

```bash
cd /path/to/g10-control-center
cp -a projects/_template projects/my-district
# put files in projects/my-district/sources/
./run-audit my-district
```

## Checklist

1. Choose a slug id: lowercase letters, digits, hyphens (`my-district-2026`).
2. Copy `_template` → `projects/<id>/`.
3. Drop curriculum files into `sources/` (any supported format).
4. **School calendar (district spine):**
   - **Dallas ISD:** keep the shipped `school-calendar.yaml` + `reference/DISD-Academic-Calendar-2026-2027.png` (Traditional 2026–27). Canonical copy: [`shared/disd-school-calendar/`](../../shared/disd-school-calendar/).
   - **Other districts:** replace with your district calendar, or remove and accept sequential (no dated YAG) mode.
5. Run `./run-audit <id>` (models must be up — see `OPERATORS.md`).
6. Collect `projects/<id>/output/GLOBAL-AUDIT-REPORT.pdf` and `output/03-year-calendar-map.md`.
7. Add a one-page `README.md` in the dataset folder (tier + notes) and a row in [STATUS.md](../STATUS.md).

**MUST NOT** put pipeline scripts here — only curriculum inputs and generated artifacts.
