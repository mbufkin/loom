# Hosted Loom app — runbook

```
browser ─▶ Vercel (hosted/, Google sign-in) ─/api/loom/*─▶ tunnel ─▶ Pi: loom-app container (ui/server.py)
           serves /app = React build of ui/       + X-Loom-Proxy-Secret        127.0.0.1:8770
```

- Access control lives on Vercel: `/app` and `/api/loom/*` need an invited Admin
  (Workspace `hd` + `ADMIN_EMAILS`). The Pi only trusts the shared secret.
- Desktop-only routes (`/api/models/*`, `/api/install-deps`) are refused on both
  hops (`hosted/lib/loom-proxy.ts`, `ui/hosted_guard.py`). Keep the lists in step.
- Model is pinned in `config.hosted.yaml` (NIM, Nemotron 3.5 Lightning, thinking off).

## Where things live (Pi `raspberrypi`)

| What | Path |
|---|---|
| Source clone (git works here) | `/media/mbufkin/pi-srv/loom-app/src` |
| Curricula, logs, run outputs | `/media/mbufkin/pi-srv/loom-app/data` (`/data` in the container) |
| Secrets (mode 600): `NVIDIA_API_KEY`, `LOOM_PROXY_SECRET` | `/media/mbufkin/pi-srv/loom-app/secrets/app.env` |
| Volume marker (container refuses to start without it) | `data/.loom-app-volume` |

The SSD is not in fstab. If it is not mounted, the bind mounts fail and the
container does not start — by design, so nothing lands on the SD card.

## Deploy / update the Pi server

```sh
ssh raspberrypi
cd /media/mbufkin/pi-srv/loom-app/src && git pull
cd deploy/hosted-app && docker compose up -d --build
docker ps --filter name=loom-app        # expect "healthy" within ~1 min
```

Check (prints status codes only, never the secret):

```sh
H=$(mktemp); chmod 600 $H
printf 'X-Loom-Proxy-Secret: %s\n' "$(grep ^LOOM_PROXY_SECRET= ../../../secrets/app.env | cut -d= -f2-)" > $H
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8770/api/version            # 401
curl -s -o /dev/null -w '%{http_code}\n' -H @$H http://127.0.0.1:8770/api/version     # 200
curl -s -o /dev/null -w '%{http_code}\n' -H @$H -X POST http://127.0.0.1:8770/api/install-deps  # 403
rm -f $H
```

## Rotate the shared secret

Both ends must change together; the app is down for the minute in between.

```sh
# On the Pi: new value in app.env, restart.
R=/media/mbufkin/pi-srv/loom-app/secrets/app.env
NEW=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
sed -i "s|^LOOM_PROXY_SECRET=.*|LOOM_PROXY_SECRET=$NEW|" $R && unset NEW
cd /media/mbufkin/pi-srv/loom-app/src/deploy/hosted-app && docker compose up -d --force-recreate

# On the Mac: pipe it into Vercel without printing it, then redeploy.
npx -y vercel@62.7.0 env rm LOOM_PROXY_SECRET production -y
ssh raspberrypi 'grep ^LOOM_PROXY_SECRET= /media/mbufkin/pi-srv/loom-app/secrets/app.env | cut -d= -f2-' \
  | tr -d '\n' | npx -y vercel@62.7.0 env add LOOM_PROXY_SECRET production
```

## Deploy Vercel (from the Mac; Mac git is unavailable)

```sh
D=$(mktemp -d) && cd $D
gh api repos/mbufkin/loom/tarball/feat/hosted-app > src.tgz && tar xzf src.tgz --strip-components=1 && rm src.tgz
mkdir -p .vercel && cp ~/Desktop/loom/.vercel/project.json .vercel/   # project wrccai/loom
npx -y vercel@62.7.0 deploy --prod     # repo root; .vercelignore uploads only hosted/ + ui/
```

Vercel's Root Directory is `hosted`; its build runs `npm run build:ui` (builds
`../ui` into `hosted/public/app` with `VITE_API_BASE=/api/loom VITE_HOSTED=1`)
then `next build`.

Production env needed beyond the existing AUTH/Google/R2 vars:
`LOOM_API_URL` (public tunnel origin, no trailing path) and `LOOM_PROXY_SECRET`.

## Known limits

- Vercel caps request bodies at ~4.5 MB, so hosted uploads are limited to about
  4 MB per file (the Pi allows 100 MB). Bigger files need a direct-to-Pi upload grant.
- No per-district separation yet: every invited Admin sees every curriculum.
