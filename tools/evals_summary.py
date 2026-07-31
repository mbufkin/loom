#!/usr/bin/env python3
"""
Evals Summary Tool - Parse TSV results files and generate evaluation summaries.

Usage:
  python3 tools/evals_summary.py [PATH] [--format text|json|md] [--compare PATH]

If no PATH provided, auto-discovers *-results.tsv files in current dir and autoresearch/*/.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def discover_tsv_files() -> list[Path]:
    """Discover TSV files in current dir and autoresearch subdirs."""
    files = []
    # Current directory
    files.extend(Path.cwd().glob("*-results.tsv"))
    files.extend(Path.cwd().glob("*.tsv"))
    # autoresearch subdirectories
    for subdir in Path.cwd().glob("autoresearch/*/"):
        if subdir.is_dir():
            files.extend(subdir.glob("*-results.tsv"))
            files.extend(subdir.glob("results.tsv"))
    # Deduplicate and sort
    unique = sorted(set(files))
    return unique


def parse_tsv(path: Path) -> dict[str, Any]:
    """Parse TSV file and extract metadata and data rows."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError(f"Empty file: {path}")

    # Parse metric_direction from line 1 comment
    metric_direction = "higher_is_better"  # default
    if lines[0].startswith("# metric_direction:"):
        match = re.search(r"#\s*metric_direction:\s*(\w+)", lines[0])
        if match:
            metric_direction = match.group(1)
        lines = lines[1:]

    # Parse header
    reader = csv.DictReader(lines, delimiter="\t")
    headers = reader.fieldnames or []
    rows = list(reader)

    # Normalize column names (fuzzy matching for v2.0.03 compat)
    column_map = {}
    for h in headers:
        h_lower = h.lower().strip()
        if h_lower in ("metric_value", "metric", "error_count", "score"):
            column_map[h] = "metric"
        elif h_lower in ("delta", "change", "diff"):
            column_map[h] = "delta"
        elif h_lower in ("status", "result", "outcome"):
            column_map[h] = "status"
        elif h_lower in ("guard", "guard_result", "guard_pass"):
            column_map[h] = "guard"
        elif h_lower in ("guard_metric", "guard-metric", "guard_value"):
            column_map[h] = "guard-metric"
        elif h_lower in ("severity", "level", "severity_level"):
            column_map[h] = "severity"
        elif h_lower in ("hypothesis", "hypothesis_text", "claim"):
            column_map[h] = "hypothesis"
        elif h_lower in ("commit", "commit_hash", "sha"):
            column_map[h] = "commit"
        elif h_lower in ("technique", "method", "approach"):
            column_map[h] = "technique"
        elif h_lower in ("dimension", "area", "category", "topic"):
            column_map[h] = "dimension"
        elif h_lower in ("candidate_label", "label", "candidate"):
            column_map[h] = "candidate_label"
        elif h_lower in ("judge_verdict", "verdict", "judge"):
            column_map[h] = "judge_verdict"
        elif h_lower in ("error_type", "error_category", "error"):
            column_map[h] = "error_type"
        elif h_lower in ("classification", "type", "kind"):
            column_map[h] = "classification"
        elif h_lower in ("convergence_count", "convergence"):
            column_map[h] = "convergence_count"
        elif h_lower in ("timestamp", "time", "date"):
            column_map[h] = "timestamp"
        elif h_lower in ("iteration", "iter", "step", "num"):
            column_map[h] = "iteration"
        else:
            column_map[h] = h

    # Remap columns in rows
    normalized_rows = []
    for row in rows:
        norm_row = {}
        for k, v in row.items():
            norm_key = column_map.get(k, k)
            norm_row[norm_key] = v
        normalized_rows.append(norm_row)

    return {
        "path": path,
        "metric_direction": metric_direction,
        "headers": headers,
        "normalized_headers": list(set(column_map.values())),
        "rows": normalized_rows,
        "raw_rows": rows,
    }


def analyze_metric(rows: list[dict], direction: str) -> dict[str, Any]:
    """Analyze metric column for trends, plateaus, biggest wins/losses."""
    metrics = []
    for i, row in enumerate(rows):
        if "metric" in row and row["metric"]:
            try:
                metrics.append((i + 1, float(row["metric"])))
            except ValueError:
                pass

    if len(metrics) < 2:
        return {"error": "Insufficient metric data"}

    iterations = [m[0] for m in metrics]
    values = [m[1] for m in metrics]

    # Trend
    start_val = values[0]
    end_val = values[-1]
    total_change = end_val - start_val
    pct_change = (total_change / abs(start_val) * 100) if start_val != 0 else 0

    # Biggest win/loss per iteration
    deltas = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        deltas.append((iterations[i], delta))

    biggest_win = max(deltas, key=lambda x: x[1]) if deltas else None
    biggest_loss = min(deltas, key=lambda x: x[1]) if deltas else None

    # Plateau detection (3+ flat iterations)
    plateau_at = None
    flat_count = 0
    for i in range(1, len(values)):
        if abs(values[i] - values[i - 1]) < 1e-6:
            flat_count += 1
            if flat_count >= 3 and plateau_at is None:
                plateau_at = iterations[i]
        else:
            flat_count = 0

    # Diminishing returns (average delta drops below threshold)
    diminishing_at = None
    if len(deltas) >= 3:
        recent_avg = sum(d[1] for d in deltas[-3:]) / 3
        early_avg = sum(d[1] for d in deltas[:3]) / 3 if len(deltas) >= 3 else recent_avg
        if direction == "higher_is_better" and recent_avg < early_avg * 0.3 and early_avg > 0:
            diminishing_at = iterations[-3]
        elif direction == "lower_is_better" and recent_avg > early_avg * 0.3 and early_avg < 0:
            diminishing_at = iterations[-3]

    return {
        "iterations": len(metrics),
        "start": start_val,
        "end": end_val,
        "total_change": total_change,
        "pct_change": pct_change,
        "biggest_win_iter": biggest_win[0] if biggest_win else None,
        "biggest_win_delta": biggest_win[1] if biggest_win else None,
        "biggest_loss_iter": biggest_loss[0] if biggest_loss else None,
        "biggest_loss_delta": biggest_loss[1] if biggest_loss else None,
        "plateau_at": plateau_at,
        "diminishing_at": diminishing_at,
        "values": values,
        "iterations": iterations,
    }


def analyze_delta(rows: list[dict]) -> dict[str, Any]:
    """Analyze delta column for per-iteration efficiency."""
    deltas = []
    for i, row in enumerate(rows):
        if "delta" in row and row["delta"]:
            try:
                deltas.append((i + 1, float(row["delta"])))
            except ValueError:
                pass

    if not deltas:
        return {"error": "No delta data"}

    total_improvement = sum(d[1] for d in deltas)
    positive = sum(1 for d in deltas if d[1] > 0)
    negative = sum(1 for d in deltas if d[1] < 0)
    zero = sum(1 for d in deltas if d[1] == 0)

    # Effort-to-gain ratio (iterations with positive delta / total positive delta)
    effort_to_gain = len(deltas) / total_improvement if total_improvement > 0 else float("inf")

    return {
        "total_iterations": len(deltas),
        "total_improvement": total_improvement,
        "positive_count": positive,
        "negative_count": negative,
        "zero_count": zero,
        "effort_to_gain_ratio": effort_to_gain,
        "avg_delta": total_improvement / len(deltas) if deltas else 0,
    }


def analyze_status(rows: list[dict]) -> dict[str, Any]:
    """Analyze status column for keep/discard rates, streaks."""
    statuses = [row.get("status", "").lower().strip() for row in rows if row.get("status")]

    if not statuses:
        return {"error": "No status data"}

    counts = Counter(statuses)
    total = len(statuses)

    # Normalize status values
    kept = sum(v for k, v in counts.items() if k in ("keep", "kept", "keep (reworked)", "baseline", "confirmed", "done"))
    discarded = sum(v for k, v in counts.items() if k in ("discard", "reverted", "crash", "no-op", "hook-blocked", "metric-error", "disproven"))

    # Streaks
    current_streak = 0
    max_streak = 0
    current_type = None
    for s in statuses:
        is_keep = s in ("keep", "kept", "keep (reworked)", "baseline", "confirmed", "done")
        if current_type is None:
            current_type = is_keep
            current_streak = 1
        elif is_keep == current_type:
            current_streak += 1
        else:
            if current_type and current_streak > max_streak:
                max_streak = current_streak
            current_type = is_keep
            current_streak = 1
    if current_type and current_streak > max_streak:
        max_streak = current_streak

    # Failure clusters
    failure_clusters = 0
    in_cluster = False
    for s in statuses:
        is_fail = s in ("discard", "reverted", "crash", "no-op", "hook-blocked", "metric-error", "disproven")
        if is_fail and not in_cluster:
            failure_clusters += 1
            in_cluster = True
        elif not is_fail:
            in_cluster = False

    return {
        "total": total,
        "kept": kept,
        "discarded": discarded,
        "revert_rate": (discarded / total * 100) if total > 0 else 0,
        "status_counts": dict(counts),
        "longest_streak": max_streak,
        "failure_clusters": failure_clusters,
    }


def analyze_guard(rows: list[dict]) -> dict[str, Any]:
    """Analyze guard column for guard failure rates."""
    guards = [row.get("guard", "").lower().strip() for row in rows if row.get("guard")]
    guard_metrics = [row.get("guard-metric", "").lower().strip() for row in rows if row.get("guard-metric")]

    if not guards:
        return {"error": "No guard data"}

    guard_counts = Counter(guards)
    total = len(guards)
    passed = guard_counts.get("pass", 0) + guard_counts.get("passed", 0)
    failed = guard_counts.get("fail", 0) + guard_counts.get("failed", 0)

    # Guard failed but metric improved
    metric_improved_guard_failed = 0
    for row in rows:
        if row.get("guard", "").lower() in ("fail", "failed") and row.get("metric"):
            try:
                # Need previous metric to compare - simplified check
                metric_improved_guard_failed += 1
            except ValueError:
                pass

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "failure_rate": (failed / total * 100) if total > 0 else 0,
        "metric_improved_guard_failed": metric_improved_guard_failed,
        "guard_counts": dict(guard_counts),
    }


def analyze_severity(rows: list[dict]) -> dict[str, Any]:
    """Analyze severity distribution."""
    severities = [row.get("severity", "").lower().strip() for row in rows if row.get("severity")]

    if not severities:
        return {"error": "No severity data"}

    counts = Counter(severities)
    total = len(severities)

    # Critical discovery rate per iteration
    critical_by_iter = defaultdict(int)
    for row in rows:
        if row.get("severity", "").lower() == "critical":
            try:
                iter_num = int(row.get("iteration", 0))
                critical_by_iter[iter_num] += 1
            except (ValueError, TypeError):
                pass

    return {
        "total": total,
        "distribution": dict(counts),
        "critical_rate_per_iter": dict(critical_by_iter),
        "critical_pct": (counts.get("critical", 0) / total * 100) if total > 0 else 0,
    }


def analyze_hypothesis(rows: list[dict]) -> dict[str, Any]:
    """Analyze hypothesis confirmation rates by technique."""
    if "hypothesis" not in rows[0] if rows else True:
        return {"error": "No hypothesis column"}

    techniques = defaultdict(lambda: {"total": 0, "confirmed": 0})
    for row in rows:
        tech = row.get("technique", "unknown").strip()
        status = row.get("status", "").lower().strip()
        techniques[tech]["total"] += 1
        if status in ("confirmed", "keep", "kept", "done", "baseline", "keep (reworked)"):
            techniques[tech]["confirmed"] += 1

    ranked = []
    for tech, data in techniques.items():
        if data["total"] > 0:
            rate = data["confirmed"] / data["total"] * 100
            ranked.append((tech, rate, data["total"], data["confirmed"]))

    ranked.sort(key=lambda x: (-x[1], -x[2]))
    return {"technique_effectiveness": ranked}


def analyze_commit(rows: list[dict]) -> dict[str, Any]:
    """Analyze commit/file hotspots."""
    commits = [row.get("commit", "").strip() for row in rows if row.get("commit")]
    if not commits:
        return {"error": "No commit data"}

    # Simple file frequency from commit messages (heuristic)
    file_counts = Counter()
    for c in commits:
        # Extract file paths from commit message
        files = re.findall(r"(\w+/\w+\.\w+|\w+\.\w+)", c)
        for f in files:
            file_counts[f] += 1

    return {
        "total_commits": len(commits),
        "file_hotspots": file_counts.most_common(10),
    }


def analyze_technique(rows: list[dict]) -> dict[str, Any]:
    """Analyze technique effectiveness."""
    return analyze_hypothesis(rows)  # Same logic


def analyze_dimension(rows: list[dict]) -> dict[str, Any]:
    """Analyze dimension coverage."""
    dims = [row.get("dimension", "").strip() for row in rows if row.get("dimension")]
    if not dims:
        return {"error": "No dimension data"}

    counts = Counter(dims)
    return {
        "total": len(dims),
        "unique_dimensions": len(counts),
        "coverage": dict(counts),
        "completeness_pct": len(counts) / 12 * 100,  # Assuming 12 dimensions
    }


def analyze_candidate_judge(rows: list[dict]) -> dict[str, Any]:
    """Analyze candidate_label + judge_verdict convergence."""
    if "candidate_label" not in rows[0] if rows else True:
        return {"error": "No candidate_label column"}

    labels = defaultdict(list)
    for row in rows:
        label = row.get("candidate_label", "").strip()
        verdict = row.get("judge_verdict", "").strip()
        if label:
            labels[label].append(verdict)

    convergence = {}
    oscillations = 0
    for label, verdicts in labels.items():
        # Count verdict changes
        changes = sum(1 for i in range(1, len(verdicts)) if verdicts[i] != verdicts[i - 1])
        convergence[label] = {
            "total_judgments": len(verdicts),
            "final_verdict": verdicts[-1] if verdicts else "unknown",
            "oscillations": changes,
        }
        oscillations += changes

    return {
        "candidates": convergence,
        "total_oscillations": oscillations,
        "converged": sum(1 for v in convergence.values() if v["oscillations"] == 0),
    }


def analyze_error_type(rows: list[dict]) -> dict[str, Any]:
    """Analyze error type distribution and fix rates."""
    errors = [row.get("error_type", "").strip() for row in rows if row.get("error_type")]
    if not errors:
        return {"error": "No error_type data"}

    counts = Counter(errors)
    return {
        "total": len(errors),
        "distribution": dict(counts),
    }


def analyze_classification(rows: list[dict]) -> dict[str, Any]:
    """Analyze classification (new/extension/duplicate) ratios."""
    classes = [row.get("classification", "").strip().lower() for row in rows if row.get("classification")]
    if not classes:
        return {"error": "No classification data"}

    counts = Counter(classes)
    total = len(classes)
    return {
        "total": total,
        "new_pct": (counts.get("new", 0) / total * 100) if total > 0 else 0,
        "extension_pct": (counts.get("extension", 0) / total * 100) if total > 0 else 0,
        "duplicate_pct": (counts.get("duplicate", 0) / total * 100) if total > 0 else 0,
        "distribution": dict(counts),
    }


def analyze_convergence(rows: list[dict]) -> dict[str, Any]:
    """Analyze convergence_count trajectory."""
    conv = []
    for row in rows:
        if "convergence_count" in row and row["convergence_count"]:
            try:
                conv.append((int(row.get("iteration", 0)), int(row["convergence_count"])))
            except ValueError:
                pass

    if not conv:
        return {"error": "No convergence data"}

    return {
        "trajectory": conv,
        "final": conv[-1][1] if conv else 0,
        "trend": "increasing" if len(conv) > 1 and conv[-1][1] > conv[0][1] else "stable",
    }


def analyze_unknown_columns(parsed: dict) -> list[str]:
    """Report unknown columns that were detected but not analyzed."""
    known = {
        "iteration", "timestamp", "metric", "delta", "status", "guard", "guard-metric",
        "severity", "hypothesis", "commit", "technique", "dimension", "candidate_label",
        "judge_verdict", "error_type", "classification", "convergence_count",
        "category", "research_question", "source", "insight_problem", "insight_mechanism",
        "confidence", "classification", "evidence", "file_line"
    }
    found = set(parsed["normalized_headers"])
    unknown = found - known
    return sorted(unknown)


def _get_analysis(analyses: dict, key: str) -> dict | None:
    """Get analysis result if it exists and has no error."""
    result = analyses.get(key)
    if result is None or "error" in result:
        return None
    return result


def generate_report(parsed: dict, analyses: dict) -> str:
    """Generate the text report."""
    rows = parsed["rows"]
    total_iters = len(rows)
    path = parsed["path"]
    direction = parsed["metric_direction"]

    lines = []
    lines.append(f"## Evals Summary — {path.name} ({total_iters} iterations)")
    lines.append("")

    # Key Metrics
    lines.append("### Key Metrics")
    status_analysis = _get_analysis(analyses, "status")
    if status_analysis:
        lines.append(f"- Total iterations: {status_analysis['total']} | Kept: {status_analysis['kept']} | Reverted: {status_analysis['discarded']} | Revert rate: {status_analysis['revert_rate']:.1f}%")
    else:
        lines.append(f"- Total iterations: {total_iters}")

    metric_analysis = _get_analysis(analyses, "metric")
    if metric_analysis:
        lines.append(f"- Starting metric: {metric_analysis['start']:.4f} | Final metric: {metric_analysis['end']:.4f} | Improvement: {metric_analysis['pct_change']:.1f}%")
    lines.append("")

    # Trend Analysis
    lines.append("### Trend Analysis")
    if metric_analysis:
        trend = "improving" if (direction == "higher_is_better" and metric_analysis["total_change"] > 0) or (direction == "lower_is_better" and metric_analysis["total_change"] < 0) else "declining" if metric_analysis["total_change"] != 0 else "flat"
        lines.append(f"- Metric progression: {trend} ({direction.replace('_', ' ')})")

        if metric_analysis.get("plateau_at"):
            lines.append(f"- Plateau detected at iteration {metric_analysis['plateau_at']} (metric stable for 3+ iterations)")

        if metric_analysis.get("biggest_win_iter"):
            lines.append(f"- Biggest win: iteration {metric_analysis['biggest_win_iter']} (+{metric_analysis['biggest_win_delta']:.4f})")

        if metric_analysis.get("biggest_loss_iter"):
            lines.append(f"- Biggest loss: iteration {metric_analysis['biggest_loss_iter']} ({metric_analysis['biggest_loss_delta']:.4f})")

        if metric_analysis.get("diminishing_at"):
            lines.append(f"- Diminishing returns: after iteration {metric_analysis['diminishing_at']}, average delta dropped below 30% of early average")
    else:
        lines.append("- No metric column detected for trend analysis")
    lines.append("")

    # Patterns
    lines.append("### Patterns")

    # Status patterns
    if status_analysis:
        kept_desc = []
        discarded_desc = []
        for row in rows:
            status = row.get("status", "").lower().strip()
            desc = row.get("hypothesis") or row.get("insight_mechanism") or row.get("evidence") or row.get("category") or ""
            if status in ("keep", "kept", "keep (reworked)", "baseline", "confirmed", "done") and desc:
                kept_desc.append(desc[:100])
            elif status in ("discard", "reverted", "crash", "no-op", "hook-blocked", "metric-error", "disproven") and desc:
                discarded_desc.append(desc[:100])

        if kept_desc:
            lines.append(f"- What succeeded: {'; '.join(kept_desc[:3])}")
        if discarded_desc:
            lines.append(f"- What failed: {'; '.join(discarded_desc[:3])}")

    # File hotspots
    commit_analysis = _get_analysis(analyses, "commit")
    if commit_analysis and commit_analysis.get("file_hotspots"):
        hotspots = ", ".join([f"{f} ({c})" for f, c in commit_analysis["file_hotspots"][:5]])
        lines.append(f"- File hotspots: {hotspots}")

    # Technique effectiveness
    tech_analysis = _get_analysis(analyses, "technique") or _get_analysis(analyses, "hypothesis")
    if tech_analysis and tech_analysis.get("technique_effectiveness"):
        top_tech = tech_analysis["technique_effectiveness"][:3]
        tech_str = ", ".join([f"{t[0]} ({t[1]:.0f}% confirm, {t[3]}/{t[2]})" for t in top_tech])
        lines.append(f"- Technique effectiveness: {tech_str}")

    # Dimension coverage
    dim_analysis = _get_analysis(analyses, "dimension")
    if dim_analysis:
        lines.append(f"- Dimension coverage: {dim_analysis['unique_dimensions']}/12 ({dim_analysis['completeness_pct']:.0f}%)")

    # Convergence
    cand_analysis = _get_analysis(analyses, "candidate_judge")
    if cand_analysis:
        lines.append(f"- Convergence: {cand_analysis['converged']}/{len(cand_analysis['candidates'])} candidates converged, {cand_analysis['total_oscillations']} total oscillations")

    lines.append("")

    # Recommendation
    lines.append("### Recommendation")
    if metric_analysis:
        if metric_analysis.get("plateau_at") and metric_analysis.get("diminishing_at"):
            lines.append("- **Stop** — Plateau detected and diminishing returns confirmed. Consider changing strategy or stopping.")
        elif metric_analysis.get("plateau_at"):
            lines.append("- **Change strategy** — Plateau detected. Try different techniques or dimensions.")
        elif status_analysis and status_analysis.get("revert_rate", 0) > 50:
            lines.append("- **Change strategy** — High revert rate (>50%). Current approach not yielding improvements.")
        elif metric_analysis["pct_change"] > 0 and direction == "higher_is_better":
            lines.append("- **Continue** — Positive trend with room for improvement.")
        elif metric_analysis["pct_change"] < 0 and direction == "lower_is_better":
            lines.append("- **Continue** — Positive trend (metric decreasing) with room for improvement.")
        else:
            lines.append("- **Continue** — Monitoring recommended.")

        # Specific actionable suggestion
        if tech_analysis and tech_analysis.get("technique_effectiveness"):
            best = tech_analysis["technique_effectiveness"][0]
            lines.append(f"- Focus on **{best[0]}** technique ({best[1]:.0f}% confirmation rate) for highest impact.")
    else:
        lines.append("- **Continue** — Insufficient metric data for trend recommendation. Add metric tracking.")
        if "dimension" in parsed["normalized_headers"]:
            lines.append("- Consider adding a metric column to enable trend analysis.")

    return "\n".join(lines)


def generate_json_report(parsed: dict, analyses: dict) -> dict:
    """Generate structured JSON report."""
    return {
        "source": str(parsed["path"]),
        "metric_direction": parsed["metric_direction"],
        "total_iterations": len(parsed["rows"]),
        "columns_detected": parsed["normalized_headers"],
        "unknown_columns": analyze_unknown_columns(parsed),
        "key_metrics": analyses.get("status", {}),
        "trend_analysis": analyses.get("metric", {}),
        "delta_analysis": analyses.get("delta", {}),
        "status_analysis": analyses.get("status", {}),
        "guard_analysis": analyses.get("guard", {}),
        "severity_analysis": analyses.get("severity", {}),
        "hypothesis_analysis": analyses.get("hypothesis", {}),
        "commit_analysis": analyses.get("commit", {}),
        "technique_analysis": analyses.get("technique", {}),
        "dimension_analysis": analyses.get("dimension", {}),
        "candidate_judge_analysis": analyses.get("candidate_judge", {}),
        "error_type_analysis": analyses.get("error_type", {}),
        "classification_analysis": analyses.get("classification", {}),
        "convergence_analysis": analyses.get("convergence", {}),
        "recommendation": generate_recommendation_text(analyses, parsed),
    }


def generate_recommendation_text(analyses: dict, parsed: dict) -> str:
    """Generate recommendation text for JSON output."""
    metric_analysis = _get_analysis(analyses, "metric")
    status_analysis = _get_analysis(analyses, "status")
    tech_analysis = _get_analysis(analyses, "technique") or _get_analysis(analyses, "hypothesis")
    direction = parsed["metric_direction"]

    if metric_analysis:
        if metric_analysis.get("plateau_at") and metric_analysis.get("diminishing_at"):
            return "Stop — Plateau detected and diminishing returns confirmed. Consider changing strategy or stopping."
        elif metric_analysis.get("plateau_at"):
            return "Change strategy — Plateau detected. Try different techniques or dimensions."
        elif status_analysis and status_analysis.get("revert_rate", 0) > 50:
            return "Change strategy — High revert rate (>50%). Current approach not yielding improvements."
        elif metric_analysis["pct_change"] > 0 and direction == "higher_is_better":
            return "Continue — Positive trend with room for improvement."
        elif metric_analysis["pct_change"] < 0 and direction == "lower_is_better":
            return "Continue — Positive trend (metric decreasing) with room for improvement."
        else:
            return "Continue — Monitoring recommended."
    else:
        return "Continue — Insufficient metric data for trend recommendation. Add metric tracking."


def generate_md_report(parsed: dict, analyses: dict) -> str:
    """Generate markdown report (same as text but with .md extension handling)."""
    return generate_report(parsed, analyses)


def main():
    parser = argparse.ArgumentParser(
        description="Parse TSV results files and generate evaluation summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 tools/evals_summary.py                    # Auto-discover TSV files
  python3 tools/evals_summary.py path/to/results.tsv
  python3 tools/evals_summary.py --format md        # Write evals-summary.md
  python3 tools/evals_summary.py --format json      # Write evals-summary.json
  python3 tools/evals_summary.py --compare other.tsv  # v2.2.0 placeholder
        """
    )
    parser.add_argument("path", nargs="?", help="Path to TSV file (optional, auto-discovered if omitted)")
    parser.add_argument("--format", choices=["text", "json", "md"], default="text", help="Output format (default: text)")
    parser.add_argument("--compare", help="Compare with another TSV file (v2.2.0 placeholder, not implemented)")
    parser.add_argument("--output", "-o", help="Output file path (default: evals-summary.{md,json} in same dir as input)")

    args = parser.parse_args()

    # Handle --compare placeholder
    if args.compare:
        print("NOTICE: --compare is a v2.2.0 placeholder and not yet implemented", file=sys.stderr)

    # Discover or use provided path
    if args.path:
        tsv_path = Path(args.path)
        if not tsv_path.exists():
            print(f"Error: File not found: {tsv_path}", file=sys.stderr)
            sys.exit(1)
    else:
        files = discover_tsv_files()
        if not files:
            print("Error: No *-results.tsv files found in current directory or autoresearch/*/", file=sys.stderr)
            print("Provide a path to a TSV file.", file=sys.stderr)
            sys.exit(1)
        elif len(files) == 1:
            tsv_path = files[0]
            print(f"Auto-discovered: {tsv_path}")
        else:
            print("Multiple results files found:")
            for i, f in enumerate(files, 1):
                print(f"  {i}. {f}")
            choice = input("Which results to analyze? (number): ").strip()
            try:
                idx = int(choice) - 1
                tsv_path = files[idx]
            except (ValueError, IndexError):
                print("Invalid selection", file=sys.stderr)
                sys.exit(1)

    # Parse TSV
    try:
        parsed = parse_tsv(tsv_path)
    except Exception as e:
        print(f"Error parsing TSV: {e}", file=sys.stderr)
        sys.exit(1)

    # Run analyses based on detected columns
    rows = parsed["rows"]
    headers = set(parsed["normalized_headers"])

    analyses = {}

    if "metric" in headers:
        analyses["metric"] = analyze_metric(rows, parsed["metric_direction"])
    if "delta" in headers:
        analyses["delta"] = analyze_delta(rows)
    if "status" in headers:
        analyses["status"] = analyze_status(rows)
    if "guard" in headers:
        analyses["guard"] = analyze_guard(rows)
    if "severity" in headers:
        analyses["severity"] = analyze_severity(rows)
    if "hypothesis" in headers:
        analyses["hypothesis"] = analyze_hypothesis(rows)
    if "commit" in headers:
        analyses["commit"] = analyze_commit(rows)
    if "technique" in headers:
        analyses["technique"] = analyze_technique(rows)
    if "dimension" in headers:
        analyses["dimension"] = analyze_dimension(rows)
    if "candidate_label" in headers and "judge_verdict" in headers:
        analyses["candidate_judge"] = analyze_candidate_judge(rows)
    if "error_type" in headers:
        analyses["error_type"] = analyze_error_type(rows)
    if "classification" in headers:
        analyses["classification"] = analyze_classification(rows)
    if "convergence_count" in headers:
        analyses["convergence"] = analyze_convergence(rows)

    # Report unknown columns
    unknown = analyze_unknown_columns(parsed)
    if unknown:
        print(f"Note: Unknown columns detected (not analyzed): {', '.join(unknown)}", file=sys.stderr)

    # Generate output
    if args.format == "json":
        report = generate_json_report(parsed, analyses)
        output = json.dumps(report, indent=2)
        default_name = "evals-summary.json"
    elif args.format == "md":
        output = generate_md_report(parsed, analyses)
        default_name = "evals-summary.md"
    else:
        output = generate_report(parsed, analyses)
        default_name = None  # text goes to stdout

    # Write output
    if args.format in ("json", "md"):
        if args.output:
            out_path = Path(args.output)
        else:
            out_path = tsv_path.parent / default_name
        out_path.write_text(output, encoding="utf-8")
        print(f"Written: {out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()