# Dataset: bluebonnet-math-2026

| | |
|--|--|
| **Tier** | Active (Grade 5 + Algebra I validation) |
| **Program** | Loom at repo root — this folder is **data only** |
| **Source** | TEA Bluebonnet Learning Math (TEA Learn Canvas) |
| **Scope** | English **Grade 5** (`9543`) + **Algebra I** (`9546`); no K–4 / 6–8 / Geo / Alg II |
| **Download** | Per-module TE/SE + program docs; **skip** full Volume 1/2 binders |
| **Calendar** | DISD dated spine + TEA-derived unit day counts |
| **Run** | Stage then audit (see below) |

## Commands

```bash
# Full corpus into _corpus/ (~70 PDFs, ~0.5 GB)
python3 tools/download_bluebonnet_math.py --project bluebonnet-math-2026

# Validation ladder stages → sources/ + units/ + manifest.yaml
python3 tools/stage_bluebonnet_units.py --stage d1   # G5 Mod 1 pack + program guides
python3 tools/stage_bluebonnet_units.py --stage d2   # full Grade 5
python3 tools/stage_bluebonnet_units.py --stage d3   # Algebra I only
python3 tools/stage_bluebonnet_units.py --stage d4   # G5 + Alg I combined

./run-audit bluebonnet-math-2026 --force --skip-drive-push
```

Do **not** commit PDFs under `sources/` / `_corpus/` (gitignored).

## Pipeline accommodations (why this corpus)

- **Layer 1 ORGANIZE** batches at 40 elements (`layer1.ORGANIZE_BATCH_SIZE`) — required for TE/Learn SE element counts.
- **Layer 0** mid-chunk resume via `.raw/*-resolved-rows.json` + 900s timeouts on chunks.

See `VALIDATION.md` after the D4 ladder completes.
