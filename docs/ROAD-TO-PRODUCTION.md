# Road to production — from "just me" to a shippable v1.0

> **Purpose of this doc.** A think-on-it roadmap for taking the curriculum
> auditor from a prototype you drive by hand to a product a *stranger* can
> install and find useful. Nothing here is built yet — it's the plan.
>
> **Decided context (2026-07-22):**
> - **Audience:** technical users who bring their own **NVIDIA GPU** box
>   (design-partner districts' IT, or the partners themselves).
> - **Distribution target:** **Docker + the NVIDIA Container Toolkit.**
> - **Product name:** deliberately deferred. This doc uses `audit` as a
>   placeholder CLI command; the real binary/product name is TBD.

---

## 0. The mindset shift

A **prototype** runs on *your* box, where *you* know the incantations. A
**product** runs on a *stranger's* box and explains itself. Almost all the
remaining work is closing that gap — and it's a well-trodden path, not novel
research. The hard, original part (the audit engine) is already built.

| Prototype (today) | Product (v1.0) |
|---|---|
| `python3 run_project.py --project dallas-career-2026` | one command: `audit run ./my-curriculum` |
| Model endpoint, GPU, paths assumed present | it **checks** them and says exactly what's missing |
| "works on my machine" | one documented, repeatable install (a container) |
| read the code to learn how | a README a stranger follows in 15 minutes |
| latest commit on `main` | a tagged `v1.0.0` with pinned dependencies |

---

## 1. Definition of done — the "15-minute stranger test"

Don't let "production" stay vague. This is the bar:

> A stranger with an NVIDIA GPU, starting from a clean machine, can:
> 1. install it (one documented path),
> 2. run `audit doctor` and see it **pass**,
> 3. run the **bundled sample curriculum** and get a real audit,
> 4. open the UI and browse the result,
>
> …**without asking us a single question** — and when a prerequisite is
> missing, the error tells them how to fix it.

If that's true, v1.0 is shipped. Everything else is polish.

---

## 2. The crux for *this* app: the local-model dependency

A normal web app just needs code. This one needs **four heavy things** on the
stranger's machine, which is exactly what makes "curl-and-go" non-trivial:

1. an **NVIDIA GPU** with enough VRAM,
2. a running **OpenAI-compatible model server** (`llama-server` / vLLM) — today
   configured in `config.yaml` under `models.analyst_url` (e.g.
   `http://localhost:8081/v1/chat/completions`),
3. a **multi-GB model file** (the Nemotron-nano-30B GGUF),
4. the **built UI** + Python dependencies.

So "shippable" = **automating and health-checking all four**, plus a graceful
"you don't have a GPU / the model isn't downloaded yet" path. This is *why*
Docker wins for us: it pins #2–#4 into one reproducible artifact, and the
NVIDIA Container Toolkit wires #1 through to the container.

---

## 3. Distribution design: Docker + NVIDIA runtime

**Two services (via `docker-compose`), because the model runtime and the app
have very different lifecycles:**

```
                      ┌─────────────────────────┐
  docker compose up   │  model  (GPU)           │
  ───────────────────►│  llama-server + GGUF    │◄── OpenAI-compatible :8081
                      └─────────────────────────┘
                                 ▲
                                 │ config.yaml models.analyst_url
                      ┌─────────────────────────┐
                      │  app                    │
                      │  pipeline + UI server   │──► browser :8770
                      │  (built static UI)      │
                      └─────────────────────────┘
```

- **`model` service** — runs `llama-server` with `--gpus all`. Requires the
  host to have the **NVIDIA driver + Container Toolkit** installed (documented
  prerequisite; `audit doctor` verifies it). The app already talks to it over
  the OpenAI-compatible endpoint, so **no engine code changes** — just point
  `config.yaml` at the service name instead of `localhost`.
- **`app` service** — Python pipeline + the UI server (`ui/server.py`), serving
  the **pre-built** UI (see Phase 3). No Node needed at runtime.

**The model file strategy (important):** do **not** bake a 20+GB GGUF into the
image (bloat + licensing). Instead:
- host the GGUF on **Hugging Face** at a **pinned revision**,
- `audit model pull` downloads it into a cache volume and **verifies a sha256**,
- the compose file **mounts that volume** so re-runs are instant and offline.

**Host prerequisites (documented + doctor-checked):** NVIDIA driver, Docker,
NVIDIA Container Toolkit, enough disk for the model, enough VRAM.

---

## 4. Product-blocking vs. quality gaps — don't confuse them

The single most useful distinction for a first v1.0. **You can ship with the
"quality" column still open**, as long as those items are labelled honestly
(which they already are in the UI's "road to production" panel).

| **Blocking v1.0** (must do) | **Quality** (ship without; keep improving) |
|---|---|
| One CLI + `audit doctor` preflight | Validation/calibration vs. a large expert set |
| Docker/compose install path | Alignment scoring promoted from advisory → gating |
| First-run model bootstrap (`model pull`) | Hardened structured output (fewer model-JSON failures) |
| Config with no hardcoded paths | OCR + non-PDF ingestion (Docs/Slides/LMS) |
| UI server serves the **built** UI | Scale/throughput, bigger/faster model, job queue |
| README that passes the 15-min test | Deeper pedagogy: standards alignment, progression, rigor |
| Pinned deps + a tagged release | Human-in-the-loop confirm/override + feedback capture |
| Clear errors on missing prerequisites | Multi-user beyond simple sign-in |
| A bundled sample curriculum | |

> Note: the engine already **degrades gracefully** on bad model output (it warns
> and keeps going instead of crashing), so robustness is *ship-acceptable* for
> v1.0 — improving it is a quality lever, not a blocker.

---

## 5. The phased plan

Each phase has a concrete **Definition of Done (DoD)** you can test.

### Phase 1 — the universal skeleton *(needed no matter the packaging)*
Turn scripts into a product-shaped CLI. Small, high-leverage, low-risk.
- Add a thin `cli.py` (argparse) with subcommands that call existing code:
  - `audit run <curriculum>` → wraps `run_project.main()`
  - `audit ui` → starts `ui/server.py`
  - `audit doctor` → preflight (below)
  - `audit model pull` → download+verify the GGUF (stub now, real in Phase 2)
  - `audit sample` → run the bundled sample end-to-end
- `pyproject.toml` with `[project.scripts]` so `pip install -e .` puts `audit`
  on PATH.
- **`audit doctor`** — checks and prints ✅/❌ **with fix hints** for: `nvidia-smi`
  present & a GPU visible; `config.yaml` exists; `models.analyst_url` reachable
  (reuse the existing health-check in `run_project.py`); Python deps importable;
  the built UI present.
- A tiny **bundled sample** at `projects/sample-mini/` (2–3 short public-domain
  PDFs + a `manifest.yaml` declaring `packet_type`) so first runs are fast.
- A **README quickstart** targeting the 15-minute test.

**DoD:** on a fresh shell, `pip install -e . && audit doctor && audit sample &&
audit ui` works, and `audit doctor` fails *loudly and helpfully* when the model
server is down.

### Phase 2 — first-run experience
- **Config resolution order:** env var → `config.yaml` → sensible default.
  Audit the code for absolute paths / hardcoded ports and route them through
  config (`config.example.yaml` already models this well — extend it).
- **`audit model pull`** for real: download the pinned GGUF from Hugging Face,
  verify sha256, store under a cache dir, write its path into config.
- **Friendly errors** at every external boundary (model server unreachable →
  "start the model service or run `audit doctor`", model file missing → "run
  `audit model pull`").

**DoD:** a new user sets only a couple of config values (or accepts defaults);
a missing model produces a one-line fix, not a stack trace.

### Phase 3 — the package (Docker)
- **Build the UI to static** (`npm run build` → `ui/dist`) and make
  `ui/server.py` **serve `dist`** (today it leans on the Vite dev server). This
  removes Node from the runtime.
- **`Dockerfile`** for the `app` image (Python + built UI + pipeline).
- **`docker-compose.yml`** with the `model` + `app` services, `--gpus all`, the
  model cache volume, and `config.yaml` pointing at the `model` service name.
- Document host prereqs (driver + Container Toolkit).

**DoD:** on a clean GPU host, `docker compose up` → UI at `localhost:8770`, and
`audit sample` (inside the app container) produces a real audit.

### Phase 4 — release hygiene
- **Pin dependencies** (a lockfile — `uv`, `pip-tools`, or `requirements.txt`
  with hashes).
- **Version** in `pyproject.toml`, surfaced by `audit --version` and in the UI
  footer; tag **`v1.0.0`**; start a `CHANGELOG.md`.
- A CI job that **builds the image** (so "it builds" is proven every push).

**DoD:** a fresh `git clone` + the documented steps passes the 15-minute test;
`git tag v1.0.0` cut.

---

## 6. Explicitly deferred (not in v1.0, and that's fine)

Multi-tenant / hosted SaaS · a no-GPU hosted fallback · OCR & non-PDF ingestion
· standards-alignment / vertical-progression / rigor scoring · large-scale
calibration · human-in-the-loop correction capture. These are real, but none
block a design-partner v1.0 for technical users with their own GPU.

> Sign-in: you've done auth before and it's genuinely **not required** for a
> design-partner v1.0. Slot a simple single-tenant sign-in in around Phase 3 if
> you want it; don't let it block shipping.

---

## 7. v1.0 checklist (copyable)

```
[ ] audit CLI: run / ui / doctor / model pull / sample
[ ] pyproject.toml with console entry point
[ ] audit doctor: GPU, config, model endpoint, deps, built-UI (with fix hints)
[ ] bundled sample curriculum (projects/sample-mini/)
[ ] config: env > config.yaml > default; no hardcoded paths/ports
[ ] audit model pull: HF pinned revision + sha256 verify + cache
[ ] friendly errors at every external boundary
[ ] UI built to dist and served by ui/server.py (no Node at runtime)
[ ] Dockerfile + docker-compose.yml (model + app, --gpus all, model volume)
[ ] documented host prereqs (driver + NVIDIA Container Toolkit)
[ ] pinned dependency lockfile
[ ] version surfaced (audit --version + UI footer)
[ ] README passes the 15-minute stranger test
[ ] CI builds the image
[ ] git tag v1.0.0 + CHANGELOG.md
```

---

## 8. Smallest next step

**Phase 1**, specifically: `cli.py` + `audit doctor` + a bundled sample + the
quickstart README. It's valuable regardless of packaging, it's low-risk, and it
makes the whole thing *feel* like a product immediately — one command, a health
check, and a sample that just works. From there the Docker packaging is
mechanical.
