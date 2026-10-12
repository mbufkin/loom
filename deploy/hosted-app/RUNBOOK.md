# Hosted Loom app — runbook

```
browser ─▶ Cloudflare Access (app `Loom`, one-time PIN) ─▶ tunnel `loom` ─▶ Pi 127.0.0.1:8790
           app.loomaudit.com                               cloudflared-loom.service    └▶ loom-app container
                                                                                         ui/server.py: React UI + /api
```

- Cloudflare Access signs people in and adds a signed JWT (`Cf-Access-Jwt-Assertion`)
  to every request. The server verifies it on **every** request, UI files included
  (`ui/hosted_guard.py`): RS256 against `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`,
  `aud` = `LOOM_ACCESS_AUD`, `iss` = team domain, exp/nbf with 30 s leeway.
  Missing token → 401; invalid → 403. Optional `LOOM_ALLOWED_EMAILS` allowlist.
- Hosted mode (`LOOM_HOSTED=1`, set in the image) refuses to start without
  `LOOM_ACCESS_TEAM_DOMAIN` and `LOOM_ACCESS_AUD` (fail closed).
- Desktop-only routes (`/api/models/*`, `/api/install-deps`) → 403 even when signed in.
- `/healthz` answers without a token only from inside the container (Docker healthcheck).
- Model is pinned in `config.hosted.yaml` (NIM, Nemotron 3.5 Lightning, thinking off).
- The UI is built in the image with `VITE_HOSTED=1` (no model/key/install settings).

## Live configuration (not secrets)

| Setting | Value |
|---|---|
| URL | https://app.loomaudit.com |
| Access team domain | https://weathered-sun-6ada.cloudflareaccess.com |
| Access app / policy | `Loom`, "Approved users": Allow, emails mbufkin@dallasisd.org; One-time PIN; 24 h session |
| Application AUD (`LOOM_ACCESS_AUD`) | `f17f06587630eb8e2239a0ac74a9b1cf479a68b9d442ddbbf8a2a3df085b88f3` |
| Tunnel | `loom`, id `1051ab5b-9c95-4b4f-b700-184253ff23d4`, DNS CNAME app.loomaudit.com |

Boot order: the SSD is in `/etc/fstab` (`nofail`) and `docker.service` waits for
`media-mbufkin-pi\x2dsrv.mount`, so containers come back after a reboot.

## Where things live (Pi `raspberrypi`)

| What | Path |
|---|---|
| Source clone (git works here) | `/media/mbufkin/pi-srv/loom-app/src` |
| Curricula, logs, run outputs | `/media/mbufkin/pi-srv/loom-app/data` (`/data` in the container) |
| App env (mode 600): `NVIDIA_API_KEY`, `LOOM_ACCESS_TEAM_DOMAIN`, `LOOM_ACCESS_AUD`, `LOOM_ALLOWED_EMAILS` | `/media/mbufkin/pi-srv/loom-app/secrets/app.env` |
| Volume marker (container refuses to start without it) | `data/.loom-app-volume` |
| Tunnel config / credentials | `~/.cloudflared/loom.yml`, `~/.cloudflared/1051ab5b-….json` (never in git) |
| Tunnel unit | `/etc/systemd/system/cloudflared-loom.service` (copy of `cloudflared/` here) |

`cloudflared-travel-pdf-quick.service` is a separate tunnel for travel-pdf; never edit it.

If the SSD is ever missing at boot, the bind mounts fail and the containers
stay down (by design, so nothing lands on the SD card). Once it is mounted:
`docker start loom-app loom-worker`.

## Deploy / update

```sh
ssh raspberrypi
cd /media/mbufkin/pi-srv/loom-app/src && git pull
cd deploy/hosted-app && docker compose up -d --build
docker ps --filter name=loom-app                      # expect "healthy"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8790/api/version   # 401 (no token)
curl -s -o /dev/null -w '%{http_code}\n' -H 'Cf-Access-Jwt-Assertion: x' http://127.0.0.1:8790/  # 403
```

Tests (offline, inside the image):
`docker run --rm --entrypoint python -e LOOM_HOME=/tmp/lh loom-app:latest test_hosted_guard.py`

## Tunnel

```sh
cp deploy/hosted-app/cloudflared/loom.yml ~/.cloudflared/loom.yml
sudo cp deploy/hosted-app/cloudflared/cloudflared-loom.service /etc/systemd/system/ && sudo systemctl daemon-reload
# Only after the Access app exists and loom-app is running with the Access env:
cloudflared tunnel route dns loom app.loomaudit.com
sudo systemctl enable --now cloudflared-loom.service
curl -sI https://app.loomaudit.com | head -3     # 302 to <team>.cloudflareaccess.com
```

## Change who can sign in

Cloudflare Zero Trust → Access → Applications → `Loom` → policy emails. If
`LOOM_ALLOWED_EMAILS` is set in `app.env`, add the email there too and
`docker compose up -d --force-recreate`.

## Known limits

- No per-district separation yet: everyone allowed in sees every curriculum.
- Cloudflare free plan caps uploads at 100 MB per request (server limit 95 MB).
- In-flight runs die if the container or Pi restarts; finished outputs stay on disk.
