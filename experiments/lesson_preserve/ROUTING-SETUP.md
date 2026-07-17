# Local dual-model LP routing (9B + 30B)

Both models stay resident on the box. No cloud. Spike only — **not** wired into live `run_project`.

## How both fit

| Server | Port | Model | Context |
|--------|------|--------|---------|
| Pass2 | **8081** | Nano 9B Q4_K_M GGUF | 16k |
| Pass3 | **8080** | Nano 30B Unsloth `UD-Q8_K_XL` | **32k** (routing) |

**Key constraint:** do not leave 30B at `-c 524288` for dual routing — that KV cache crowds out 9B. Routing only needs ~16–32k (Dallas docs top out ~13k tokens).

**Disk restore (done):** `~/llama.cpp/models/nemotron3-nano-30b.gguf` → symlink to
`Nemotron-3-Nano-30B-A3B-UD-Q8_K_XL.gguf` (Unsloth Q8). Safe to kill/restart `:8080`.

## Start dual (required for true cascade)

```bash
# From repo root — restarts BOTH (30B at ctx=32768, 9B at ctx=16384)
bash experiments/lesson_preserve/scripts/start_dual_routing_servers.sh
```

`KEEP_30B=1` only if you must leave a live `:8080` alone (may OOM / force 9B-only failure). Prefer a full restart after restore.

### Preflight

```bash
curl -s http://127.0.0.1:8080/v1/models   # id ends with nemotron3-nano-30b.gguf, n_ctx=32768
curl -s http://127.0.0.1:8081/v1/models   # id contains Nano-9B, n_ctx=16384
```

The harness **exits non-zero** if `:8081` is down (no silent 30B-only fallback). Use `--single-30b` only when deliberately scoring 30B-only.

## Cascade logic

1. **Pass1** — filename/route LP match + hard non-LP skips (`Slides`, role-play, resume, attire answers, quiz/exit…).
2. **Pass2** — Nano 9B `/no_think`, full doc, conf ≥ 0.90 + LP evidence gate.
3. **Pass3** — if unsure → Nano 30B `/think` (same promote gates).

## Run tests

### Focus regression (5 units, 28 docs)

```bash
python3 experiments/lesson_preserve/test_routing_minicpm.py \
  --project dallas-career-2026 --min-confidence 0.90
```

Writes `experiments/lesson_preserve/out/dallas-career-2026/routing_hybrid_local_9b_30b_cascade.json`.

**Expected (gate vs prior baselines):**

| Check | Expect |
|-------|--------|
| Pass1 LP | 4 |
| Promotions (model) | 5 |
| Final LP | **9** |
| Escalations | 2 (attire guide → evidence block; vital-signs lab → not LP) |
| Score vs `routing_hybrid_nano9b_tight_think.json` | TP=9 FP=0 FN=0 |
| Score vs `routing_hybrid_local30b_cascade.json` | TP=9 FP=0 FN=0 |

Scorecard:

```bash
python3 experiments/lesson_preserve/scripts/score_routing_vs_baseline.py \
  --pred experiments/lesson_preserve/out/dallas-career-2026/routing_hybrid_local_9b_30b_cascade.json \
  --baseline experiments/lesson_preserve/out/dallas-career-2026/routing_hybrid_nano9b_tight_think.json
```

### Full corpus (`--units all`)

```bash
python3 experiments/lesson_preserve/test_routing_minicpm.py \
  --project dallas-career-2026 --units all --min-confidence 0.90
```

Writes `routing_hybrid_local_9b_30b_cascade_all_units.json`.

**2026-07-15 sweep (dual, ctx 32k/16k):** 111 docs → **29 final LP** (19 pass1 + 10 pass2 promotions), 22 escalations, 0 pass3 promotions. Review later if needed: `Carrasco_Brainstorm.txt` (career-cluster) promoted via pass2.

## Optional follow-up

Point systemd `llama-cuda@nemotron3-nano-30b` at `-c 32768` so a reboot does not regress to 524k KV.
