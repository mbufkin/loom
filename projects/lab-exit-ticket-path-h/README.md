# lab-exit-ticket-path-h — Path H smoke (exit tickets)

Harness: `.plan/stub-path-presence-depth/tickets/01-shared-path-lab-harness.md`

## Seeds (local copies; gitignored)

| Tier | File |
|------|------|
| strong | Engineering Lesson Exit Ticket |
| mixed | Arts AV Exit Ticket Day 1 |
| weak | Professional Preparedness Exit Ticket Day 2 |

## Smoke

```bash
python3 ingest.py --project lab-exit-ticket-path-h --skip-models
python3 route.py --project lab-exit-ticket-path-h
python3 workflows/run_paths.py --project lab-exit-ticket-path-h --no-model
# review path_h/findings.json
```
