#!/usr/bin/env python3
"""
test_minicpm_route.py — Route docs with on-box MiniCPM5-1B vs filename/route matching.

Uses MiniCPM5-1B from MINICPM_MODEL_DIR (or ~/models/MiniCPM5-1B). Side test only.
"""

from __future__ import annotations

import argparse
import os
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from audit_lib import (  # noqa: E402
    classify_doc_type,
    doc_id_from_filename,
    load_manifest,
    project_dir,
)
from experiments.lesson_preserve.detect import (  # noqa: E402
    detect_unit_lesson_plans,
    load_route_workflow_by_doc,
)

MODEL_DIR = Path(os.environ.get("MINICPM_MODEL_DIR", Path.home() / "models" / "MiniCPM5-1B"))
LABELS = ("lesson_plan", "quiz", "rubric", "other")


def _snippet(path: Path, limit: int = 1800) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def load_model(device: str = "cuda"):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR), trust_remote_code=True)
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        str(MODEL_DIR),
        dtype=dtype,
        trust_remote_code=True,
    )
    model = model.to(device)
    model.eval()
    return tok, model


def classify_with_minicpm(tok, model, *, filename: str, snippet: str, device: str) -> str:
    import torch

    system = (
        "Classify K-12 curriculum files. "
        "Output ONLY one word from this set: lesson_plan | quiz | rubric | other. "
        "No thinking. No punctuation. No explanation."
    )
    user = (
        f"Filename: {filename}\n\n"
        f"Text excerpt:\n{snippet}\n\n"
        "Your one-word label:"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: dict = {}
    if hasattr(tok, "apply_chat_template"):
        try:
            prompt = tok.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            prompt = tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
    else:
        prompt = system + "\n\n" + user
    inputs = tok(prompt, return_tensors="pt")
    if device != "cpu":
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=64,
            do_sample=False,
            pad_token_id=tok.eos_token_id,
        )
    prompt_n = int(inputs["input_ids"].shape[1])
    gen = out[0][prompt_n:]
    # HF .generate has no OpenAI usage object — count tensor lengths and label
    # source=estimate so research rollups stay honest vs llama.cpp API usage.
    try:
        import sys
        from pathlib import Path

        _root = Path(__file__).resolve().parents[2]
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from usage_lib import record_model_call, set_usage_project

        set_usage_project(
            os.environ.get("LOOM_USAGE_PROJECT") or "lesson-preserve-hf"
        )
        completion_n = int(gen.shape[0])
        record_model_call(
            role="analyst",
            step="lesson_preserve.hf_generate",
            model=str(getattr(model, "name_or_path", "hf-local")),
            messages=messages,
            # Fake an OpenAI usage block from real token-id counts.
            resp={
                "usage": {
                    "prompt_tokens": prompt_n,
                    "completion_tokens": completion_n,
                    "total_tokens": prompt_n + completion_n,
                }
            },
            elapsed_ms=0.0,
            ok=True,
            extra={"backend": "transformers.generate"},
        )
    except Exception:
        pass
    text = tok.decode(gen, skip_special_tokens=True).strip().lower()
    # Drop thinking traces if model still emits them
    if "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()
    text = text.replace("<think>", " ").strip()
    for lab in LABELS:
        if re.search(rf"\b{re.escape(lab)}\b", text.replace(" ", "_")):
            return lab
        if lab.replace("_", " ") in text:
            return lab
    if "lesson" in text and "plan" in text:
        return "lesson_plan"
    if "quiz" in text or "exit ticket" in text:
        return "quiz"
    if "rubric" in text:
        return "rubric"
    # last non-empty token-ish line
    for line in reversed([ln.strip() for ln in text.splitlines() if ln.strip()]):
        clean = re.sub(r"[^a-z_]", "", line.replace(" ", "_"))
        if clean in LABELS:
            return clean
    return f"other({text[:60]!r})"


def collect_docs(project_id: str, unit_ids: list[str] | None) -> list[dict]:
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    routes = load_route_workflow_by_doc(project_id)
    units = manifest.get("units") or {}
    selected = unit_ids or sorted(units.keys())
    rows = []
    for uid in selected:
        u = units[uid]
        title_map = {
            doc_id_from_filename(r): Path(r).name for r in (u.get("documents") or [])
        }
        spike_lps = {
            r["doc_id"]
            for r in detect_unit_lesson_plans(
                project_id, uid, u.get("documents") or [], title_map=title_map
            )
        }
        for rel in u.get("documents") or []:
            did = doc_id_from_filename(rel)
            src = root / "sources" / Path(rel).name
            if not src.is_file():
                continue
            rows.append(
                {
                    "unit_id": uid,
                    "doc_id": did,
                    "filename": src.name,
                    "path": src,
                    "filename_type": classify_doc_type(src.name),
                    "route_workflow": routes.get(did) or "",
                    "spike_is_lp": did in spike_lps,
                }
            )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="dallas-career-2026")
    ap.add_argument(
        "--units",
        default="financial-literacy,engineering,professional-preparedness",
        help="Comma units (default: FL + Eng + ProPrep pilots)",
    )
    ap.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    ap.add_argument(
        "--out",
        default="",
        help="JSON report path (default under experiments/lesson_preserve/out)",
    )
    args = ap.parse_args()
    units = [u.strip() for u in args.units.split(",") if u.strip()]

    if not MODEL_DIR.is_dir():
        raise SystemExit(f"Missing model at {MODEL_DIR}")

    print(f"Loading MiniCPM5-1B from {MODEL_DIR} on {args.device} …")
    tok, model = load_model(args.device)
    rows = collect_docs(args.project, units)
    print(f"Classifying {len(rows)} documents …")

    results = []
    for i, row in enumerate(rows, 1):
        snip = _snippet(row["path"])
        pred = classify_with_minicpm(
            tok, model, filename=row["filename"], snippet=snip, device=args.device
        )
        pred_lp = pred == "lesson_plan" or pred.startswith("lesson")
        rec = {
            **{k: v for k, v in row.items() if k != "path"},
            "minicpm_label": pred,
            "minicpm_is_lp": pred_lp,
            "match_vs_spike": (
                "agree"
                if pred_lp == row["spike_is_lp"]
                else ("minicpm_only" if pred_lp else "spike_only")
            ),
            "match_vs_route": (
                "agree"
                if pred_lp == (row["route_workflow"] == "lesson_plan")
                else (
                    "minicpm_only"
                    if pred_lp
                    else "route_only"
                )
            ),
        }
        results.append(rec)
        print(
            f"[{i}/{len(rows)}] {row['unit_id'][:18]:18} "
            f"file={row['filename'][:42]:42} "
            f"route={row['route_workflow'] or '-':12} "
            f"spike_lp={str(row['spike_is_lp']):5} "
            f"minicpm={pred}"
        )

    # Summary
    agree_spike = sum(1 for r in results if r["match_vs_spike"] == "agree")
    minicpm_only = [r for r in results if r["match_vs_spike"] == "minicpm_only"]
    spike_only = [r for r in results if r["match_vs_spike"] == "spike_only"]
    print("\n=== SUMMARY (MiniCPM5-1B vs spike filename/route detect) ===")
    print(f"docs: {len(results)}  agree: {agree_spike}  "
          f"minicpm_only_LP: {len(minicpm_only)}  spike_only_LP: {len(spike_only)}")
    if minicpm_only:
        print("\nMiniCPM says LP, spike missed:")
        for r in minicpm_only:
            print(f"  - {r['unit_id']}: {r['filename']} (route={r['route_workflow']})")
    if spike_only:
        print("\nSpike says LP, MiniCPM disagreed:")
        for r in spike_only:
            print(f"  - {r['unit_id']}: {r['filename']} → {r['minicpm_label']}")

    out = Path(args.out) if args.out else (
        _ROOT
        / "experiments"
        / "lesson_preserve"
        / "out"
        / args.project
        / "minicpm1b_route_test.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "model": str(MODEL_DIR),
                "project": args.project,
                "units": units,
                "agree_with_spike": agree_spike,
                "minicpm_only_lp": minicpm_only,
                "spike_only_lp": spike_only,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
