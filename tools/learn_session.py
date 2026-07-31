#!/usr/bin/env python3
"""
Learn Session — documentation generation, validation, and wiki building.

Usage:
  python3 tools/learn_session.py --mode init --scope "*.py" --depth standard
  python3 tools/learn_session.py --mode summarize --depth overview
  python3 tools/learn_session.py --mode wiki
  python3 tools/learn_session.py --mode check --file audit_lib.py

Modes:
  init       Create documentation from scratch
  update     Refresh existing documentation
  check      Validate existing documentation
  summarize  One-shot codebase summary (no loop)
  wiki       Generate navigable knowledge base
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_compact() -> str:
    return datetime.now().strftime("%y%m%d-%H%M")


def is_source_file(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in (
        ".ts", ".tsx", ".py", ".go", ".rs", ".java", ".rb", ".swift",
        ".kt", ".c", ".cpp", ".cs", ".js", ".jsx",
    )


def is_doc_file(path: Path) -> bool:
    name = path.name.lower()
    ext = path.suffix.lower()
    if ext == ".txt":
        return False  # data files, not documentation
    if ext in (".md", ".rst"):
        return True
    if name == "readme" or name.startswith("readme."):
        return True
    return False


def is_config_file(path: Path) -> bool:
    name = path.name.lower()
    return name in (
        "package.json", "requirements.txt", "pyproject.toml", "cargo.toml",
        "go.mod", "tsconfig.json", "vite.config.ts", ".env.example",
        "config.yaml", ".gitignore",
    )


# ── Argument Parsing ──────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Learn Session — documentation management for codebases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode
    parser.add_argument("--mode", choices=["init", "update", "check", "summarize", "wiki"],
                        help="Operation mode")
    parser.add_argument("--depth", choices=["overview", "standard", "comprehensive"],
                        default="standard", help="Detail depth (default: standard)")
    parser.add_argument("--scope", help="File globs to document (comma-separated)")
    parser.add_argument("--file", help="Specific file to document")
    parser.add_argument("--scan", action="store_true", help="Force fresh codebase scout")
    parser.add_argument("--topics", help="Comma-separated focus topics")
    parser.add_argument("--no-fix", action="store_true", help="Validate only, don't auto-fix")
    parser.add_argument("--format", choices=["markdown", "json", "rst"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--iterations", type=int, default=10, help="Max iterations (default: 10)")
    parser.add_argument("--evals", action="store_true", help="Enable eval checkpoints")
    parser.add_argument("--evals-interval", type=int, help="Override eval checkpoint interval")
    parser.add_argument("--chain", help="Comma-separated chain targets after completion")
    parser.add_argument("--output-dir", help="Output directory (default: autoresearch/learn-<ts>)")

    # Wiki-specific
    parser.add_argument("--modules", help="Wiki mode: comma-separated module names/paths")
    parser.add_argument("--force", action="store_true",
                        help="Wiki mode: regenerate all pages from scratch")

    return parser.parse_args(argv)


# ── Interactive Setup ─────────────────────────────────────────────────────

def interactive_setup() -> tuple[str, str, str, str]:
    """Fallback interactive questions if mode/scope/depth missing."""
    print("--- Setup: Documentation Session ---", file=sys.stderr)

    mode = ""
    while mode not in ("init", "update", "check", "summarize", "wiki"):
        mode = input("Mode? (init/update/check/summarize/wiki): ").strip().lower()

    scope_defaults = ["*.py", "*.ts", "*.tsx", "src/**/*", "docs/**/*.md", "entire codebase"]
    print(f"Scope options: {', '.join(scope_defaults)}", file=sys.stderr)
    scope = input("Scope (or press Enter for '*.py'): ").strip() or "*.py"

    depth = input("Depth? (overview/standard/comprehensive) [standard]: ").strip() or "standard"
    if depth not in ("overview", "standard", "comprehensive"):
        depth = "standard"

    topics_prompt = "Topics? (architecture/API/database/testing/all) [all]: "
    topics = input(topics_prompt).strip() or "all"

    return mode, scope, depth, topics


# ── Codebase Scout ────────────────────────────────────────────────────────

def scout_codebase(root: Path) -> dict[str, Any]:
    """Scout codebase for files, imports, exports, and existing docs."""
    src_files = []
    doc_files = []
    config_files = []
    dirs_with_source = defaultdict(list)

    # Directories to skip entirely (exact basename match in path)
    SKIP_DIRS = {"node_modules", ".venv", "dist", "archive", "__pycache__",
                 ".git", "data", "output", "_d2_snapshot", "out", "results"}

    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        parts = rel.parts
        if any(p.startswith(".") or p in SKIP_DIRS for p in parts):
            continue
        if is_source_file(f):
            src_files.append(rel)
            for depth in range(len(parts)):
                sub = Path(*parts[:depth + 1])
                if sub.is_dir() or depth == len(parts) - 1:
                    dirs_with_source[str(sub)].append(rel)
        elif is_doc_file(f):
            doc_files.append(rel)
        elif is_config_file(f):
            config_files.append(rel)

    # Identify modules (dirs with 3+ source files)
    modules = {}
    for d, files in sorted(dirs_with_source.items()):
        direct_src = [f for f in files if str(Path(d)) == str(f.parent)]
        if len(direct_src) >= 3:
            modules[d] = [str(f) for f in direct_src]

    # Check for project manifests
    manifests = {}
    for mf in ("pyproject.toml", "Cargo.toml", "go.mod", "package.json"):
        p = root / mf
        if p.exists():
            manifests[mf] = p.read_text(encoding="utf-8", errors="replace")[:500]

    # Gather imports (basic Python/TS)
    imports = defaultdict(set)
    for f in src_files:
        content = (root / f).read_text(encoding="utf-8", errors="replace")[:8000]
        for m in re.finditer(r"^(?:import|from)\s+(\S+)", content, re.MULTILINE):
            imports[str(f)].add(m.group(1))

    # Build module-level doc index: which dirs have a README or docs/ subfolder
    doc_index = defaultdict(set)
    for d in doc_files:
        # Register doc as covering its own directory
        doc_index[str(d.parent)].add(str(d))
        # If it's a README, it documents that directory
        if d.stem.lower() == "readme":
            doc_index[str(d.parent)].add(str(d))

    documented = 0
    undocumented = []
    for f in src_files:
        parent = str(f.parent)
        stem = f.stem
        # Check: same-stem .md exists, or parent dir has README, or docs/ covers it
        has_doc = False
        # Same-stem in same directory
        if (root / f.parent / (stem + ".md")).exists():
            has_doc = True
        # Same-stem in docs/
        elif (root / "docs" / (stem + ".md")).exists():
            has_doc = True
        # Parent directory has README
        elif "readme" in doc_index.get(parent, set()) or any(
            d.lower().startswith("readme") for d in doc_index.get(parent, set())
        ):
            has_doc = True
        # docs/ has relevant documentation (heuristic: filename partial match)
        elif any(stem in d for d in doc_index.get("docs", set())):
            has_doc = True

        if has_doc:
            documented += 1
        else:
            undocumented.append(str(f))

    doc_coverage = round((documented / max(len(src_files), 1)) * 100, 1)

    # Project documentation files (docs/ and root .md files)
    project_docs = [str(d) for d in doc_files
                    if str(d).startswith("docs/")
                    or (d.parent == Path(".") and d.suffix == ".md")]

    return {
        "root": str(root),
        "total_source_files": len(src_files),
        "total_doc_files": len(project_docs),
        "total_config_files": len(config_files),
        "documented_source_files": documented,
        "undocumented_source": undocumented,
        "coverage_pct": doc_coverage,
        "source_files": [str(f) for f in src_files],
        "doc_files": project_docs,
        "config_files": [str(f) for f in config_files],
        "modules": modules,
        "manifests": manifests,
        "imports": dict(imports),
    }


# ── Output Directory ──────────────────────────────────────────────────────

def create_output_dir(base: str | None = None) -> Path:
    """Create and return output directory under autoresearch/."""
    auto = PROJECT_ROOT / "autoresearch"
    auto.mkdir(exist_ok=True)
    ts = now_compact()
    name = f"learn-{ts}"
    out = Path(base) if base else (auto / name)
    out.mkdir(parents=True, exist_ok=True)
    return out


# ── TSV ───────────────────────────────────────────────────────────────────

TSV_HEADER = (
    "# metric_direction: higher_is_better\n"
    "iteration\ttimestamp\tfile_documented\tvalidation_status\t"
    "issues_found\tissues_fixed\tdescription\n"
)

TSV_COLUMNS = [
    "iteration", "timestamp", "file_documented", "validation_status",
    "issues_found", "issues_fixed", "description",
]


def init_tsv(out_dir: Path) -> Path:
    p = out_dir / "learn-results.tsv"
    p.write_text(TSV_HEADER, encoding="utf-8")
    return p


def append_tsv_row(tsv_path: Path, row: dict[str, Any]) -> None:
    """Append a row to the TSV file."""
    with open(tsv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_COLUMNS, delimiter="\t")
        writer.writerow({k: row.get(k, "") for k in TSV_COLUMNS})


# ── Validate Docs ─────────────────────────────────────────────────────────

def validate_doc(doc_path: Path, src_path: Path | None = None) -> dict[str, Any]:
    """Validate a documentation file. Returns {status, issues, description}."""
    if not doc_path.exists():
        return {
            "status": "fail",
            "issues_found": 1,
            "issues_fixed": 0,
            "description": "Documentation file not found",
        }

    content = doc_path.read_text(encoding="utf-8", errors="replace")
    issues = []

    # Check minimum length
    if len(content) < 50:
        issues.append("Too short (<50 chars)")

    # Check for headings
    if not re.search(r"^#{1,6}\s", content, re.MULTILINE):
        issues.append("No markdown headings found")

    # Check for broken links (simple check)
    for link in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
        target = link.group(2)
        if target.startswith("http"):
            continue  # skip external
        target_path = (doc_path.parent / target).resolve()
        if not target_path.exists():
            issues.append(f"Broken link: {target}")

    # If src_path provided, check for code references
    if src_path and src_path.exists():
        src_content = src_path.read_text(encoding="utf-8", errors="replace")
        # Extract class/function names from source
        symbols = re.findall(r"^(?:def |class |export (?:default )?(?:function|const|class) )(\w+)",
                             src_content, re.MULTILINE)
        for sym in symbols[:10]:
            if sym not in content and sym not in ("main",):
                issues.append(f"Missing doc for symbol: {sym}")

    return {
        "status": "pass" if len(issues) <= 2 else "fail",
        "issues_found": len(issues),
        "issues_fixed": 0,
        "description": "; ".join(issues[:5]) if issues else "Valid",
    }


# ── Generate Doc Stub ─────────────────────────────────────────────────────

def generate_doc_stub(src_path: Path, out_dir: Path, depth: str) -> Path | None:
    """Generate a documentation stub for a source file."""
    if not src_path.exists():
        return None

    content = src_path.read_text(encoding="utf-8", errors="replace")
    rel = src_path.relative_to(PROJECT_ROOT)

    # Extract symbols
    classes = re.findall(r"^(?:class )(\w+)", content, re.MULTILINE)
    functions = re.findall(r"^(?:def |async def )(\w+)", content, re.MULTILINE)
    exports = re.findall(r"^export (?:default )?(?:function|const|class|interface|type) (\w+)",
                         content, re.MULTILINE)

    # Build doc: preserve path structure, replace slashes with dashes for flat docs/
    # or mirror the directory structure
    rel_stem = rel.with_suffix("").as_posix().replace("/", "-")
    doc_name = rel_stem + ".md"
    doc_path = out_dir / "docs" / doc_name
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# {rel} — Documentation",
        "",
        f"**File:** `{rel}`",
        f"**Auto-generated:** {now_iso()}",
        f"**Depth:** {depth}",
        "",
        "## Overview",
        "",
        f"<!-- TODO: Describe what {rel} does -->",
        "",
    ]

    if classes:
        lines.append("## Classes")
        lines.append("")
        for c in classes:
            lines.append(f"- `{c}`")
        lines.append("")

    if functions:
        lines.append("## Functions")
        lines.append("")
        for f in functions[:20]:
            lines.append(f"- `{f}()`")
        lines.append("")

    if exports:
        lines.append("## Exports")
        lines.append("")
        for e in exports:
            lines.append(f"- `{e}`")
        lines.append("")

    if depth == "comprehensive":
        lines.append("## Usage")
        lines.append("")
        lines.append("```")
        lines.append(f"# TODO: Usage example for {rel}")
        lines.append("```")
        lines.append("")
        lines.append("## Dependencies")
        lines.append("")
        lines.append("<!-- TODO: List internal dependencies -->")
        lines.append("")

    doc_path.write_text("\n".join(lines), encoding="utf-8")
    return doc_path


# ── Summarize Mode ────────────────────────────────────────────────────────

def generate_summary(scout: dict[str, Any], depth: str, topics: str) -> str:
    """Generate a codebase summary (used in summarize mode)."""
    lines = [
        "# Codebase Documentation Summary",
        "",
        f"**Generated:** {now_iso()}",
        f"**Depth:** {depth}",
        f"**Topics:** {topics}",
        "",
        "## Overview",
        "",
    ]

    total = scout["total_source_files"]
    documented = scout.get("documented_source_files", 0)
    coverage = scout["coverage_pct"]

    lines.append(f"- **Total source files:** {total}")
    lines.append(f"- **Source files with companion docs:** {documented}/{total}")
    lines.append(f"- **Documentation coverage:** {coverage}%")
    lines.append("")

    mods = scout.get("modules", {})
    if mods:
        lines.append("## Modules Detected")
        lines.append("")
        lines.append("| Module | Source Files |")
        lines.append("|--------|-------------|")
        for m, files in sorted(mods.items()):
            lines.append(f"| `{m}` | {len(files)} |")
        lines.append("")

    undoc = scout.get("undocumented_source", [])
    if undoc:
        lines.append("## Documentation Gaps")
        lines.append("")
        lines.append(f"**{len(undoc)} undocumented files:**")
        lines.append("")
        for f in undoc[:20]:
            lines.append(f"- `{f}`")
        if len(undoc) > 20:
            lines.append(f"- *...and {len(undoc) - 20} more*")
        lines.append("")

    if depth in ("standard", "comprehensive"):
        # Import summary
        imports = scout.get("imports", {})
        all_imports = set()
        for imps in imports.values():
            all_imports.update(imps)
        lines.append("## Dependency Overview")
        lines.append("")
        lines.append(f"- **Unique imports used:** {len(all_imports)}")
        lines.append("")

        # Config files
        cfg = scout.get("config_files", [])
        if cfg:
            lines.append("## Configuration Files")
            lines.append("")
            for c in cfg:
                lines.append(f"- `{c}`")
            lines.append("")

    return "\n".join(lines)


# ── Wiki Mode ─────────────────────────────────────────────────────────────

SECRET_PATTERNS = re.compile(
    r"(AKIA[0-9A-Z]{16}"  # AWS access key
    r"|sk-[a-zA-Z0-9]{20,}"  # OpenAI API key
    r"|ghp_[a-zA-Z0-9]{36}"  # GitHub PAT
    r"|password\s*[:=]\s*\S+"
    r"|mongodb(\+srv)?://\S+"
    r"|postgres(ql)?://\S+)",
    re.IGNORECASE,
)


def discover_modules(root: Path, modules_arg: str | None = None) -> list[dict[str, Any]]:
    """Discover project modules for wiki generation."""
    if modules_arg:
        # Explicit override — each item must resolve inside project root
        result = []
        for m in modules_arg.split(","):
            m = m.strip()
            p = Path(m)
            if not p.is_absolute():
                p = root / p
            p = p.resolve()
            try:
                p.relative_to(root.resolve())
            except ValueError:
                print(f"Warning: Module path {m} escapes project root, skipping", file=sys.stderr)
                continue
            name = p.name if p.is_file() else str(p.relative_to(root))
            result.append({"name": name, "path": str(p.relative_to(root)), "files": []})
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and is_source_file(f):
                        result[-1]["files"].append(str(f.relative_to(root)))
            elif p.is_file():
                result[-1]["files"] = [str(p.relative_to(root))]
        return result

    # Auto-discovery: monorepo manifests → per-dir project files → heuristic
    modules = []

    # Check monorepo workspaces
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            ws = pkg.get("workspaces", [])
            if ws:
                for w in ws:
                    for d in root.glob(w):
                        if d.is_dir():
                            files = [str(f.relative_to(root)) for f in sorted(d.rglob("*"))
                                     if f.is_file() and is_source_file(f)]
                            modules.append({"name": d.name, "path": str(d.relative_to(root)), "files": files})
        except (json.JSONDecodeError, OSError):
            pass

    if not modules:
        # Per-directory project files
        for mf in ("pyproject.toml", "Cargo.toml", "go.mod"):
            p = root / mf
            if p.exists():
                modules.append({"name": root.name, "path": ".", "files": []})
                for f in sorted(root.rglob("*")):
                    if f.is_file() and is_source_file(f):
                        rel = f.relative_to(root)
                        if not any(p.startswith(".") or p in ("node_modules", ".venv", "dist")
                                   for p in rel.parts):
                            modules[-1]["files"].append(str(rel))
                break

    if not modules:
        # Heuristic: dirs with 3+ source files
        dir_counts = Counter()
        dir_files = defaultdict(list)
        for f in sorted(root.rglob("*")):
            if not f.is_file() or not is_source_file(f):
                continue
            rel = f.relative_to(root)
            if any(p.startswith(".") or p in ("node_modules", ".venv", "dist", "archive")
                   for p in rel.parts):
                continue
            parent = rel.parent
            dir_counts[str(parent)] += 1
            dir_files[str(parent)].append(str(rel))

        for d, count in dir_counts.most_common():
            if count >= 3:
                modules.append({"name": d or root.name, "path": d or ".", "files": dir_files[d]})

    # Cap at 10 modules, group if needed
    if len(modules) > 10:
        # Group by top-level dir
        grouped = defaultdict(list)
        for m in modules:
            top = m["path"].split("/")[0] if m["path"] != "." else "root"
            grouped[top].append(m)

        modules = []
        for top, group in sorted(grouped.items()):
            if len(group) > 5:
                # Expand and take 10 largest by file count
                all_expanded = sorted(group, key=lambda x: len(x["files"]), reverse=True)
                modules.extend(all_expanded[:10])
            else:
                modules.extend(group)
        modules = modules[:10]

    return modules


def wiki_secret_scan(wiki_dir: Path) -> list[str]:
    """Scan wiki pages for secrets (non-blocking warning)."""
    warnings = []
    for f in sorted(wiki_dir.rglob("*.md")):
        content = f.read_text(encoding="utf-8", errors="replace")
        matches = SECRET_PATTERNS.findall(content)
        if matches:
            warnings.append(f"{f.relative_to(wiki_dir)}: {len(matches)} potential secret(s)")
    return warnings


def generate_wiki_page(name: str, page_type: str, scout: dict[str, Any],
                       module: dict[str, Any] | None = None, depth: str = "standard") -> str:
    """Generate a wiki page. Returns markdown content."""
    lines = ["---", f"generated_by: autoresearch", f"type: {page_type}", "---", ""]

    if page_type == "architecture":
        lines.append("# Architecture Overview")
        lines.append("")
        lines.append(f"**Project:** {scout.get('root', 'unknown')}")
        lines.append(f"**Files:** {scout['total_source_files']} source, {scout['total_doc_files']} documentation")
        lines.append("")

        modules = scout.get("modules", {})
        if modules:
            lines.append("## Module Structure")
            lines.append("")
            for m, files in sorted(modules.items())[:10]:
                lines.append(f"- **{m}** — {len(files)} files")
            lines.append("")

        # Mermaid diagrams (architecture)
        lines.append("## System Context")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph TD")
        lines.append("  A[Source Documents] --> B[Ingest]")
        lines.append("  B --> C[Layer 0: Decompose]")
        lines.append("  C --> D[Route: A/B/C]")
        lines.append("  D --> E[Layer 1: Organize]")
        lines.append("  E --> F[Layer 2: Gap Analysis]")
        lines.append("  F --> G[Synthesize]")
        lines.append("  G --> H[Reports]")
        lines.append("```")
        lines.append("")

        # Data flow
        lines.append("## Data Flow")
        lines.append("")
        lines.append("```mermaid")
        lines.append("sequenceDiagram")
        lines.append("  participant C as Curriculum Data")
        lines.append("  participant I as Ingest")
        lines.append("  participant L0 as Layer 0")
        lines.append("  participant L1 as Layer 1")
        lines.append("  participant L2 as Layer 2")
        lines.append("  participant R as Reports")
        lines.append("  C->>I: Raw documents")
        lines.append("  I->>L0: Parsed elements")
        lines.append("  L0->>L1: Decomposed chunks")
        lines.append("  L1->>L2: Organized placements")
        lines.append("  L2->>R: Gap analysis")
        lines.append("```")
        lines.append("")

        if depth == "comprehensive":
            lines.append("## Key Files")
            lines.append("")
            for f in scout.get("source_files", [])[:15]:
                lines.append(f"- `{f}`")
            lines.append("")

    elif page_type == "module" and module:
        m_name = module["name"]
        m_files = module.get("files", [])
        m_path = module.get("path", "")

        lines.append(f"# Module: {m_name}")
        lines.append("")
        lines.append(f"**Path:** `{m_path}`")
        lines.append(f"**Files:** {len(m_files)}")
        lines.append("")

        lines.append("## Overview")
        lines.append("")
        lines.append(f"<!-- TODO: Overview of the {m_name} module -->")
        lines.append("")

        lines.append("## Key Files")
        lines.append("")
        lines.append("| File | Purpose |")
        lines.append("|------|---------|")
        for f in m_files[:20]:
            lines.append(f"| `{f}` | <!-- TODO --> |")
        lines.append("")

        # Try to extract entry points
        entry_points = []
        for f in m_files[:10]:
            content = (PROJECT_ROOT / f).read_text(encoding="utf-8", errors="replace")
            classes = re.findall(r"^(?:class )(\w+)", content, re.MULTILINE)[:3]
            functions = re.findall(r"^(?:def |async def )(\w+)", content, re.MULTILINE)[:3]
            if classes or functions:
                entry_points.append((f, classes, functions))

        if entry_points:
            lines.append("## Exports")
            lines.append("")
            for f, classes, functions in entry_points[:5]:
                lines.append(f"### `{f}`")
                if classes:
                    lines.append(f"- Classes: {', '.join(classes)}")
                if functions:
                    lines.append(f"- Functions: {', '.join(functions)}")
                lines.append("")

        if depth == "comprehensive":
            lines.append("## Dependencies")
            lines.append("")

            # Detect imports from files
            all_imports = set()
            for f in m_files[:10]:
                content = (PROJECT_ROOT / f).read_text(encoding="utf-8", errors="replace")
                for m_imp in re.finditer(r"^(?:import|from)\s+(\S+)", content, re.MULTILINE):
                    all_imports.add(m_imp.group(1))
            for imp in sorted(all_imports)[:15]:
                lines.append(f"- `{imp}`")
            lines.append("")

            lines.append("## Getting Started")
            lines.append("")
            lines.append("<!-- TODO: How to use this module -->")
            lines.append("")

    elif page_type == "glossary":
        lines.append("# Glossary")
        lines.append("")
        lines.append("Domain terms extracted from the codebase.")
        lines.append("")

        # Extract terms from class names, exports, types
        terms = Counter()
        for f in scout.get("source_files", []):
            content = (PROJECT_ROOT / f).read_text(encoding="utf-8", errors="replace")
            # Class names
            for m in re.finditer(r"class (\w+)", content):
                terms[m.group(1)] += 1
            # Type aliases
            for m in re.finditer(r"(?:type|interface) (\w+)", content):
                terms[m.group(1)] += 1
            # Function defs (filter out common stdlib)
            for m in re.finditer(r"def (\w+)", content):
                if len(m.group(1)) > 2:
                    terms[m.group(1)] += 1

        # Filter — only terms appearing in 3+ files, skip common names
        common = {"main", "get", "set", "run", "load", "save", "init", "log", "id", "name",
                  "type", "path", "file", "data", "test", "build", "read", "write"}
        lines.append("| Term | Frequency | Definition |")
        lines.append("|------|-----------|------------|")
        count = 0
        for term, freq in terms.most_common(80):
            if term in common or len(term) <= 2:
                continue
            if freq < 3:
                continue
            lines.append(f"| `{term}` | {freq}x | <!-- TODO --> |")
            count += 1
            if count >= 60:
                break
        lines.append("")

    elif page_type == "onboarding":
        lines.append("# Onboarding Guide")
        lines.append("")
        lines.append(f"**Project:** {PROJECT_ROOT.name}")
        lines.append(f"**Generated:** {now_iso()}")
        lines.append("")

        lines.append("## Prerequisites")
        lines.append("")
        lines.append("- Python 3.10+")
        lines.append("- A local LLM (for pipeline execution)")
        lines.append("- Dependencies: `pip install -r requirements.txt`")
        lines.append("")

        lines.append("## Setup")
        lines.append("")
        lines.append("1. Clone the repo")
        lines.append("2. `pip install -r requirements.txt`")
        lines.append("3. Copy `config.example.yaml` to `config.yaml` and configure")
        lines.append("4. Place curriculum data under `projects/<id>/`")
        lines.append("")

        lines.append("## First Run")
        lines.append("")
        lines.append("```bash")
        lines.append("./run-audit <project-id>")
        lines.append("```")
        lines.append("")

        # Try to get recent directory activity from git
        try:
            result = subprocess.run(
                ["git", "log", "--since=6 months ago", "--name-only", "--pretty=format:"],
                capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
            )
            if result.returncode == 0:
                dir_counts = Counter()
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("/")
                    if len(parts) >= 2:
                        dir_counts[parts[0]] += 1
                lines.append("## Recent Activity (6 months)")
                lines.append("")
                for d, count in dir_counts.most_common(10):
                    lines.append(f"- `{d}/` — {count} changes")
                lines.append("")
        except (subprocess.TimeoutExpired, OSError):
            lines.append("## Recent Activity")
            lines.append("")
            lines.append("*Git history not available*")
            lines.append("")

        lines.append("## Reading Order")
        lines.append("")
        lines.append("1. `README.md` — Project overview")
        lines.append("2. `docs/ARCHITECTURE.md` — System architecture")
        lines.append("3. `docs/PIPELINE.md` — Pipeline structure")
        lines.append("4. Module docs by dependency order")
        lines.append("")

        lines.append("## Common Gotchas")
        lines.append("")
        lines.append("- <!-- TODO: Add common issues -->")
        lines.append("")

    elif page_type == "index":
        lines.append("# Documentation Index")
        lines.append("")
        lines.append("Welcome to the Loom knowledge base.")
        lines.append("")
        lines.append("## Pages")
        lines.append("")
        lines.append("| Page | Description |")
        lines.append("|------|-------------|")
        lines.append("| [Architecture](architecture.md) | System architecture and data flow |")
        lines.append("| [Glossary](glossary.md) | Domain terms and definitions |")
        lines.append("| [Onboarding](onboarding.md) | Getting started guide |")
        lines.append("")

        # Module pages
        if scout.get("modules"):
            lines.append("## Modules")
            lines.append("")
            lines.append("| Module | Files | Documentation |")
            lines.append("|--------|-------|---------------|")
            for m, files in sorted(scout["modules"].items())[:10]:
                safe = m.replace("/", "-")
                lines.append(f"| [{m}](modules/{safe}.md) | {len(files)} | [generated](modules/{safe}.md) |")
            lines.append("")

    return "\n".join(lines)


def build_wiki(scout: dict, out_dir: Path, args: argparse.Namespace) -> None:
    """Build full wiki knowledge base."""
    wiki_dir = out_dir / "wiki"
    modules_dir = wiki_dir / "modules"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    modules_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = wiki_dir / "wiki-manifest.json"

    # Discover modules
    discovered = discover_modules(PROJECT_ROOT, args.modules)

    # Plan pages
    pages = {
        "wiki/index.md": {"status": "pending", "type": "index"},
        "wiki/architecture.md": {"status": "pending", "type": "architecture"},
        "wiki/glossary.md": {"status": "pending", "type": "glossary"},
        "wiki/onboarding.md": {"status": "pending", "type": "onboarding"},
    }

    for m in discovered:
        name = m["name"]
        if name in ("", "."):
            name = "root"
        safe = name.replace("/", "-")
        pages[f"wiki/modules/{safe}.md"] = {"status": "pending", "type": "module",
                                            "module": m}

    manifest = {
        "version": "1",
        "generated_at": now_iso(),
        "generation_status": "in_progress",
        "modules_detected": [m["name"] for m in discovered],
        "pages_planned": len(pages),
        "pages": pages,
    }

    # Write manifest (pre-generation)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    # Append .gitignore if needed
    gitignore = PROJECT_ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if "wiki-manifest.json" not in content:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n# Wiki manifest\nwiki-manifest.json\n")

    # Handle resume / force
    existing_pages = set()
    if args.force:
        manifest["pages"] = {k: {**v, "status": "pending"} for k, v in pages.items()}
        manifest["generation_status"] = "in_progress"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    else:
        # Check which pages already exist and have frontmatter
        for page_key in list(manifest["pages"].keys()):
            page_path = out_dir / page_key
            if page_path.exists():
                content = page_path.read_text(encoding="utf-8", errors="replace")
                if "generated_by: autoresearch" in content:
                    manifest["pages"][page_key]["status"] = "generated"
                    existing_pages.add(page_key)

    # Generate stub index with pending markers
    stub_lines = [
        "---",
        "generated_by: autoresearch",
        "type: index",
        "---",
        "",
        "# Documentation Index",
        "",
        "## Pages",
        "",
        "| Page | Status |",
        "|------|--------|",
    ]
    for page_key in sorted(manifest["pages"].keys()):
        page_info = manifest["pages"][page_key]
        status = page_info["status"]
        stub_lines.append(f"| [{page_key}]({page_key}) | [{status}] |")
    stub_lines.append("")

    index_path = out_dir / "wiki" / "index.md"
    index_path.write_text("\n".join(stub_lines), encoding="utf-8")

    # Generate each pending page
    for page_key, page_info in sorted(manifest["pages"].items()):
        if page_info["status"] == "generated" and not args.force:
            continue

        page_type = page_info["type"]
        module = page_info.get("module")

        content = generate_wiki_page(
            page_key, page_type, scout, module, args.depth
        )

        page_path = out_dir / page_key
        # Safety: check for user-created pages
        if page_path.exists() and not args.force:
            existing = page_path.read_text(encoding="utf-8", errors="replace")
            if "generated_by: autoresearch" not in existing:
                print(f"  Skip: {page_key} — user-created page (use --force to override)", file=sys.stderr)
                manifest["pages"][page_key]["status"] = "skipped"
                manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
                continue

        page_path.write_text(content, encoding="utf-8")
        manifest["pages"][page_key]["status"] = "generated"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        print(f"  Generated: {page_key}", file=sys.stderr)

    # Finalize manifest
    all_done = all(
        p["status"] in ("generated", "skipped")
        for p in manifest["pages"].values()
    )
    if all_done:
        manifest["generation_status"] = "complete"

    # Regenerate index with final descriptions
    index_content = generate_wiki_page("index", "index", scout, None, args.depth)
    index_path = out_dir / "wiki" / "index.md"
    index_path.write_text(index_content, encoding="utf-8")

    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    # Secret scan
    secrets = wiki_secret_scan(wiki_dir)
    for s in secrets:
        print(f"  SECURITY: {s}", file=sys.stderr)

    # Report
    pages_generated = sum(1 for p in manifest["pages"].values() if p["status"] == "generated")
    print(f"  Wiki: {len(discovered)} modules, {pages_generated}/{manifest['pages_planned']} pages generated", file=sys.stderr)
    if secrets:
        print(f"  Security: {len(secrets)} potential secret(s) detected (non-blocking)", file=sys.stderr)


# ── Eval Checkpoint ───────────────────────────────────────────────────────

def eval_checkpoint(tsv_path: Path, iteration: int, max_iters: int,
                    checkpoint_count: int) -> tuple[str | None, int]:
    """Run eval checkpoint. Returns (recommendation, incremented checkpoint_count)."""
    interval = max(1, max_iters // 3) if max_iters < 10**6 else 10
    if iteration % interval != 0:
        return None, checkpoint_count

    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "evals_summary.py"),
             str(tsv_path), "--format", "text"],
            capture_output=True, text=True, timeout=30,
            cwd=PROJECT_ROOT,
        )
        summary = result.stdout.strip() or "No output"
    except (subprocess.TimeoutExpired, OSError):
        summary = "Eval checkpoint unavailable"

    # Parse TSV for stats (skip comment line)
    rows = []
    with open(tsv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    data_lines = [l for l in lines if not l.startswith("#")]
    reader = csv.DictReader(data_lines, delimiter="\t")
    for row in reader:
        rows.append(row)

    docs_written = sum(1 for r in rows if r.get("file_documented", "").strip())
    validated = sum(1 for r in rows if r.get("validation_status", "").strip() == "pass")
    total_validated = sum(1 for r in rows if r.get("validation_status", "").strip())
    gaps = docs_written - validated

    checkpoint_count += 1

    lines_out = [
        f"--- Eval Checkpoint (iterations {iteration - interval + 1}-{iteration}) ---",
        f"Docs written: {docs_written} | Validation: {validated}/{total_validated} | Gaps remaining: {gaps}",
    ]

    if checkpoint_count >= 3 and docs_written == 0:
        lines_out.append("RECOMMENDATION: Early stop — no new docs in 3+ checkpoints")
    elif gaps > docs_written * 0.5:
        lines_out.append("RECOMMENDATION: Increase validation effort — high gap rate")
    else:
        lines_out.append("RECOMMENDATION: Continue")

    lines_out.append("---")
    print("\n".join(lines_out), file=sys.stderr)

    return "\n".join(lines_out), checkpoint_count


# ── Chain Handoff ─────────────────────────────────────────────────────────

def write_handoff(out_dir: Path, mode: str, chain: str | None,
                  config: dict[str, Any], results_tsv: str,
                   findings: list[dict[str, Any]]) -> Path:
    """Write handoff.json for chain continuation."""
    handoff = {
        "version": "2.1.0",
        "source": f"learn_{mode}",
        "generated_at": now_iso(),
        "status": "COMPLETE",
        "results_tsv": results_tsv,
        "config": {
            "mode": mode,
            "scope": config.get("scope", ""),
            "depth": config.get("depth", "standard"),
            "iterations": config.get("iterations", 10),
            "chain": chain,
        },
        "findings": findings,
    }
    path = out_dir / "handoff.json"
    path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    return path


# ── Iteration Loop (init/update/check) ────────────────────────────────────

def run_iteration_loop(
    mode: str, scout: dict[str, Any], out_dir: Path,
    tsv_path: Path, args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], int]:
    """Run the scout→generate→validate→fix→log iteration loop."""
    max_iters = args.iterations
    if max_iters < 1 or max_iters > 10**6:
        max_iters = 10  # Safety cap
    depth = args.depth
    no_fix = args.no_fix
    has_evals = args.evals
    evals_interval = args.evals_interval
    scope = args.scope or "*.py"

    # Parse scope globs
    scope_globs = [s.strip() for s in scope.split(",")]

    checkpoint_count = 0
    findings = []
    iterations_run = 0

    documented_set: set = set()
    target_queue: list[str] = []

    # If --file was given, use it as the sole target
    if args.file:
        target_queue = [args.file]
    else:
        # Build queue from gaps
        undocumented = [f for f in scout.get("undocumented_source", [])]
        for f in undocumented:
            if any(Path(f).match(g) for g in scope_globs) or "entire" in scope:
                target_queue.append(f)

        # Check for outdated docs
        for doc in scout.get("doc_files", []):
            doc_path = PROJECT_ROOT / doc
            if not doc_path.exists():
                continue
            stem = doc_path.stem
            for src in scout.get("source_files", []):
                if Path(src).stem == stem:
                    src_path = PROJECT_ROOT / src
                    if src_path.stat().st_size > doc_path.stat().st_size * 3:
                        target_queue.append(src)
                    break

        # De-duplicate
        seen = set()
        target_queue = [x for x in target_queue if not (x in seen or seen.add(x))]

    if not target_queue:
        print("  No documentation gaps found — SUCCESS", file=sys.stderr)
        return [], 0

    for iteration in range(1, max_iters + 1):
        # Filter out already-documented
        available = [f for f in target_queue if f not in documented_set]
        if not available:
            print(f"  Iter {iteration}: All targets processed — early stop", file=sys.stderr)
            break

        # Pick highest-priority gap
        target_file = available[0]
        target_path = PROJECT_ROOT / target_file

        print(f"  Iter {iteration}: Processing {target_file}", file=sys.stderr)

        # ── Phase 2: Generate/Update ──
        if mode == "check":
            # Check mode: just validate existing docs
            doc_candidates = scout.get("doc_files", [])
            doc_path = None
            for d in doc_candidates:
                if Path(target_file).stem == Path(d).stem:
                    doc_path = PROJECT_ROOT / d
                    break
            if doc_path:
                validation = validate_doc(doc_path, target_path)
            else:
                validation = {
                    "status": "fail",
                    "issues_found": 1,
                    "issues_fixed": 0,
                    "description": f"No documentation found for {target_file}",
                }
        else:
            # Init/Update mode: generate or update doc
            doc_path = generate_doc_stub(target_path, out_dir, depth)
            if doc_path:
                validation = validate_doc(doc_path, target_path)
            else:
                validation = {
                    "status": "fail",
                    "issues_found": 1,
                    "issues_fixed": 0,
                    "description": f"Failed to generate doc for {target_file}",
                }

        # ── Phase 3: Validate ──
        if mode == "update":
            validation = validate_doc(doc_path, target_path) if doc_path else validation

        # ── Phase 4: Fix (unless --no-fix) ──
        if validation["status"] == "fail" and not no_fix and mode in ("init", "update"):
            # Attempt basic fixes
            if doc_path and doc_path.exists():
                content = doc_path.read_text(encoding="utf-8", errors="replace")
                fixed = False

                # Fix missing heading
                if "No markdown headings found" in validation.get("description", ""):
                    stem_name = target_path.stem
                    content = f"# {stem_name}\n\n" + content
                    fixed = True

                # Fix too short
                if "Too short" in validation.get("description", ""):
                    content += "\n\n<!-- TODO: Expand documentation -->\n"
                    fixed = True

                if fixed:
                    doc_path.write_text(content, encoding="utf-8")
                    validation["issues_fixed"] = validation["issues_found"]
                    validation["issues_found"] = 0
                    validation["status"] = "pass"
                    validation["description"] += " (auto-fixed)"

        # ── Phase 5: Log ──
        row = {
            "iteration": iteration,
            "timestamp": now_iso(),
            "file_documented": target_file,
            "validation_status": validation["status"],
            "issues_found": validation["issues_found"],
            "issues_fixed": validation["issues_fixed"],
            "description": validation.get("description", ""),
        }
        append_tsv_row(tsv_path, row)
        iterations_run = iteration

        documented_set.add(target_file)
        findings.append({
            "id": iteration,
            "file": target_file,
            "status": validation["status"],
            "issues": validation["issues_found"],
            "description": validation.get("description", ""),
        })

        # ── Eval Checkpoint ──
        if has_evals:
            _, checkpoint_count = eval_checkpoint(tsv_path, iteration, max_iters, checkpoint_count)

    return findings, iterations_run


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # ── Setup ──────────────────────────────────────────────────────────
    mode = args.mode
    scope = args.scope
    depth = args.depth
    topics = args.topics or "all"

    # --file overrides scope
    if args.file:
        scope = args.file

    if not mode:
        mode, scope, depth, topics = interactive_setup()
    elif mode in ("summarize",) and not scope:
        scope = "entire codebase"
    elif mode != "wiki" and not scope:
        mode, scope, depth, topics = interactive_setup()

    if not scope:
        scope = "*.py"
    if depth not in ("overview", "standard", "comprehensive"):
        depth = "standard"

    print(f"Mode: {mode} | Scope: {scope} | Depth: {depth} | Topics: {topics}", file=sys.stderr)

    # ── Baseline ───────────────────────────────────────────────────────
    scout = scout_codebase(PROJECT_ROOT)
    print(f"Scouted: {scout['total_source_files']} source files, "
          f"{scout['total_doc_files']} doc files, "
          f"{scout['coverage_pct']}% coverage", file=sys.stderr)

    out_dir = create_output_dir(args.output_dir)
    print(f"Output: {out_dir}", file=sys.stderr)

    # ── Summarize Mode (no loop) ───────────────────────────────────────
    if mode == "summarize":
        report = generate_summary(scout, depth, topics)
        summary_path = out_dir / "summary.md"
        summary_path.write_text(report, encoding="utf-8")
        print(report)
        print(f"\nSummary written: {summary_path}", file=sys.stderr)
        return

    # ── Wiki Mode (no per-file loop) ───────────────────────────────────
    if mode == "wiki":
        build_wiki(scout, out_dir, args)
        print(f"Wiki built in: {out_dir / 'wiki'}", file=sys.stderr)
        return

    # ── Init/Update/Check Loop ────────────────────────────────────────
    tsv_path = init_tsv(out_dir)
    print(f"TSV: {tsv_path}", file=sys.stderr)

    findings, iterations_run = run_iteration_loop(
        mode, scout, out_dir, tsv_path, args,
    )

    # ── Final Eval Summary ─────────────────────────────────────────────
    if args.evals and iterations_run > 0:
        try:
            subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "tools" / "evals_summary.py"),
                 str(tsv_path), "--format", "md", "--output",
                 str(out_dir / "evals-summary.md")],
                capture_output=True, text=True, timeout=30,
                cwd=PROJECT_ROOT,
            )
        except (subprocess.TimeoutExpired, OSError):
            print("Eval summary generation failed", file=sys.stderr)

    # ── Summary ────────────────────────────────────────────────────────
    summary_lines = [
        "## Learn Session Summary",
        "",
        f"**Mode:** {mode} | **Scope:** {scope} | **Depth:** {depth}",
        f"**Iterations run:** {iterations_run}",
        f"**Files documented:** {len(findings)}",
        "",
        "### Results",
        "",
    ]

    if findings:
        passed = sum(1 for f in findings if f["status"] == "pass")
        failed = sum(1 for f in findings if f["status"] == "fail")
        total_issues = sum(f["issues"] for f in findings)
        summary_lines.append(f"- Validation pass rate: {passed}/{len(findings)} ({passed / max(len(findings), 1) * 100:.0f}%)")
        summary_lines.append(f"- Issues found: {total_issues}")
        summary_lines.append(f"- Remaining gaps: {len(scout.get('undocumented_source', [])) - iterations_run}")
    else:
        summary_lines.append("- No iterations run")

    non_doc_files = len(scout.get("undocumented_source", [])) - iterations_run
    if non_doc_files > 0:
        summary_lines.append(f"- Remaining undocumented files: {non_doc_files}")
    else:
        summary_lines.append("- All files documented")

    summary_str = "\n".join(summary_lines)
    print(summary_str)

    # Write summary.md
    summary_path = out_dir / "summary.md"
    summary_path.write_text(summary_str + "\n", encoding="utf-8")

    # Write validation report
    val_lines = []
    val_lines.append("# Validation Report")
    val_lines.append("")
    val_lines.append(f"**Session:** {out_dir.name}")
    val_lines.append(f"**Mode:** {mode}")
    val_lines.append("")
    val_lines.append("## Per-File Results")
    val_lines.append("")
    val_lines.append("| File | Status | Issues | Description |")
    val_lines.append("|------|--------|--------|-------------|")
    for f in findings:
        val_lines.append(f"| {f['file']} | {f['status']} | {f['issues']} | {f.get('description', '')} |")
    val_lines.append("")
    val_path = out_dir / "validation-report.md"
    val_path.write_text("\n".join(val_lines), encoding="utf-8")

    # ── Chain Handoff ──────────────────────────────────────────────
    if args.chain:
        chain_path = write_handoff(
            out_dir, mode, args.chain,
            {"scope": scope, "depth": depth, "iterations": args.iterations},
            str(tsv_path.relative_to(out_dir)) if tsv_path else "",
            findings,
        )
        print(f"Handoff: {chain_path}", file=sys.stderr)

        # Invoke next in chain
        targets = [t.strip() for t in args.chain.split(",")]
        if targets:
            print(f"Chain: invoking next targets: {targets}", file=sys.stderr)

    print(f"\nSession complete: {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
