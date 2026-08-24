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

Env on Vercel (not the NIM key): `AUTH_SECRET`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `AUTH_URL`, `OPERATOR_EMAILS`, plus the four `R2_*` vars.

Without `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`, Workspace still loads (sign-in is fine) but Accept and paste wait. Those three plus `R2_BUCKET` come from a Cloudflare R2 API token — they are not minted here.

The Packet store **Ceiling** refuses new pastes at 9 GB of R2’s 10 GB-month free include, or 8,000 objects — whichever comes first. Tiny files cannot burn the 1 million Class A include while storage still looks empty. That is not the Run Cap.

`NVIDIA_API_KEY` belongs on Fly app `loom-smnysw` only.

## Spec

Language and locked decisions: `../.scratch/hosted-district-thin-path/`.
