# CTAT Flow Diagram Exports

Presentation canvases for **data flow** and **file flow** — SVG (vector) + PNG (slides/Canva).

## Files

| SVG | PNG | Topic |
|-----|-----|--------|
| `data-flow-01-high-level.svg` | `png/data-flow-01-high-level.png` | Compact pipeline overview |
| `data-flow-02-layer01.svg` | `png/data-flow-02-layer01.png` | **Five-column Layer 0/1 data flow (showcase)** |
| `file-flow-01-high-level.svg` | `png/file-flow-01-high-level.png` | Folders in → reports out |
| `file-flow-02-unit-output.svg` | `png/file-flow-02-unit-output.png` | Per-unit output anatomy |
| `file-flow-03-pipeline-writes.svg` | `png/file-flow-03-pipeline-writes.png` | Script → files on disk |

Regenerate SVGs:

```bash
# From repo root — generator lives in tools/ (Zone D), writes into this folder
python3 tools/generate-flow-svgs.py
```

Regenerate PNGs (after SVG change):

```bash
python3 -c "
import cairosvg; from pathlib import Path
src = Path('.')
out = src / 'png'; out.mkdir(exist_ok=True)
for svg in src.glob('*.svg'):
    cairosvg.svg2png(url=str(svg), write_to=str(out / (svg.stem + '.png')), scale=2.0)
"
```

Mermaid source canvases (more diagrams): `../DATA-FLOW.md`, `../FILE-FLOW.md` → export via [mermaid.live](https://mermaid.live).

---

## Upload to Google Drive

### One-time setup (rclone)

**On your Mac** (local Terminal):

```bash
brew install rclone    # if needed
rclone authorize "drive"
```

Copy the JSON token it prints.

**On G10** (SSH):

```bash
cd /path/to/g10-control-center-loom/docs/images
bash setup-gdrive-rclone.sh '<paste-json-here>'
```

### Upload diagrams

```bash
bash upload-to-gdrive.sh
```

Uploads to `Google Drive/CTAT-2026/flow-diagrams/` (SVG + `png/` subfolder).

### Manual upload (no rclone)

From Mac:

```bash
scp -r user@your-host:/path/to/g10-control-center-loom/docs/images ~/Desktop/ctat-flow-diagrams
```

Drag `~/Desktop/ctat-flow-diagrams/png/*.png` into [drive.google.com](https://drive.google.com).

Tarball on G10 Desktop: `ctat-flow-diagrams.tar.gz` (regenerate with `tar` after adding PNGs).
