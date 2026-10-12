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

## Brev GPU (optional, usually off)

Each run checks the Brev NIM once at its start: `GET <base>/v1/health/ready`
must be 200 and `GET <base>/v1/models` must list
`nvidia/nemotron-3.5-lightning-30b-a3b` (3 s to connect, 5 s total). If so,
the whole run (organise and audit) uses Brev through a per-run config at
`/data/logs/runs/<runId>.config.yaml`; otherwise it uses NVIDIA's API exactly
as before. The first log line says which, and why. No key is ever sent to
Brev, and a Brev run's environment does not contain `NVIDIA_API_KEY`. If Brev
goes away mid-run, the run fails and says so; there is no mid-run switch.

Turn it on, once the Brev box has joined the tailnet (its NIM published on
port 8000):

```bash
F=/media/mbufkin/pi-srv/loom-app/secrets/app.env
grep -q '^LOOM_BREV_URL=' "$F" \
  && sed -i 's|^LOOM_BREV_URL=.*|LOOM_BREV_URL=http://100.X.Y.Z:8000|' "$F" \
  || echo 'LOOM_BREV_URL=http://100.X.Y.Z:8000' >> "$F"
grep -c '^LOOM_BREV_URL=' "$F"   # 1; prints no values
cd /media/mbufkin/pi-srv/loom-app/src/deploy/hosted-app
docker compose up -d --force-recreate
docker exec loom-app python -c "import sys; sys.path[:0]=['/app','/app/ui']; import server; print(server._probe_brev(server._brev_base(), 'nvidia/nemotron-3.5-lightning-30b-a3b'))"
```

`(True, 'Brev is up')` means the next run uses it. Turn it off by deleting the
line and recreating; leaving it set while the box is off is fine (runs fall
back after at most ~5 s). The container reaches tailnet addresses through the
host's Tailscale (verified 2026-10-12), so no network changes are needed.

## Restore a deleted curriculum

Delete in the app moves the folder to `/data/.trash/<id>-<UTC timestamp>`
(host: `/media/mbufkin/pi-srv/loom-app/data/.trash/`). Entries older than 7
days are purged on server start and on every delete (`[loom-trash]` lines in
`docker logs loom-app`). To restore, move it back under its id, which must
not be in use:

```bash
cd /media/mbufkin/pi-srv/loom-app/data
ls .trash/
mv .trash/test1-20261012T182608Z projects/test1
```

It reappears on the next page load; no restart needed.

## Known limits

- No per-district separation yet: everyone allowed in sees every curriculum.
- Cloudflare free plan caps uploads at 100 MB per request (server limit 95 MB).
- In-flight runs die if the container or Pi restarts; finished outputs stay on disk.
