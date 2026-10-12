# Hosted Loom

Vercel-hosted District thin path. **Not** the local Review UI in `ui/`.

## Run locally

```bash
cd hosted
cp .env.example .env.local
# add AUTH_SECRET, AUTH_GOOGLE_ID, AUTH_GOOGLE_SECRET
npm install
npm test
npm run dev
```

Google OAuth authorized redirect: `http://localhost:3000/api/auth/callback/google`.

Without Google IDs the sign-in page still renders; the button stays disabled.

## Vercel

Project: `wrccai/loom` (`prj_9VmFm5xMofswGGqW3k2qAhPd8Mgl`).

Set **Root Directory** to `hosted` (dashboard created this project as a Python preset — do not deploy `./run-audit` as a Function).

Env on Vercel (not the NIM key): `AUTH_SECRET`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `AUTH_URL`, `OPERATOR_EMAILS`, `ADMIN_EMAILS`, plus the four `R2_*` vars.

Sign-in is **invite-only** (see `.scratch/hosted-district-thin-path/issues/11-manual-runs-and-invite-only.md`): an Admin needs a Workspace `hd` **and** an email on `ADMIN_EMAILS`. Empty or missing `ADMIN_EMAILS` = nobody reaches Workspace (the Operator view still works). Invite someone by adding their email and redeploying.

Without `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`, Workspace still loads (sign-in is fine) but Accept and paste wait. Those three plus `R2_BUCKET` come from a Cloudflare R2 API token — they are not minted here.

The Packet store **Ceiling** refuses new pastes at 9 GB of R2’s 10 GB-month free include, or 8,000 objects — whichever comes first. Tiny files cannot burn the 1 million Class A include while storage still looks empty. That is not the Run Cap (see Runs below).

`NVIDIA_API_KEY` is never on Vercel. It lives only on the Pi Worker (`hosted_worker.py`, see `.scratch/hosted-district-thin-path/issues/12-worker-on-the-pi.md`).

## Deploy

Run from the **repo root**, not `hosted/` — the Vercel project's Root Directory is `hosted`, and the root `.vercelignore` uploads only `hosted/`:

```bash
cd hosted && npm test && npm run typecheck && npm run build && cd ..
npx -y vercel@62.7.0 --prod
```

## Loom app (`/app`) and the Pi forwarder (`/api/loom/*`)

`/app` is the real Loom UI (`../ui`), built into `public/app` by `npm run build:ui`
(part of `npm run build`). Its API calls go to `/api/loom/*`
(`app/api/loom/[...path]/route.ts` → `lib/loom-proxy.ts`), which requires an
invited Admin and forwards to the Pi with `LOOM_PROXY_SECRET`. Needs
`LOOM_API_URL` + `LOOM_PROXY_SECRET` in Vercel env. Pi side, secret rotation and
deploy steps: `../deploy/hosted-app/RUNBOOK.md`.

## Runs (Start a Run → plates)

Contract: `../hosted_runs.py` (authoritative; keep `lib/packets.ts` in sync).

| Object | Writer |
|--------|--------|
| `d/<d>/packets/<p>/runs/<runId>/run.json` | Vercel creates (`status: queued`, `attempt: 0`, create-only); Worker owns after claim |
| `queue/<runId>.json` | Vercel creates after run.json (create-only); Worker deletes on claim |
| `d/<d>/packets/<p>/runs/<runId>/plates/*` | Worker only; served to the Admin via `/api/file` |

- Status shown = `run.json` status, except `running` with `heartbeatAt` older than 15 min shows **Stalled**. `meta.json` `runs` is a stale legacy field — never read it for status.
- Start (`POST /api/packets/<id>/runs`, rules in `lib/runs.ts`) needs: invited Admin of that District, Bargain accepted, Packet in that District. Cap, counted from run records by `queuedAt` (UTC): **2 started Runs per District per day**, **20 per calendar month across all Districts**, **1 queued/running Run per District**. Failed Runs count; a Worker requeue does not create a new Run.
- Double-submit: the page mints one `runId` per view and the server writes create-only, so a repeat returns the same Run (HTTP 200) instead of a second one.

## Spec

Language and locked decisions: `../.scratch/hosted-district-thin-path/`.
