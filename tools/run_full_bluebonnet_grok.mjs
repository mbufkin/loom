/**
 * Full Bluebonnet graph run: Cursor Grok 4.5 per unit → Loom assemble.
 *
 * Resumable: skips units that already have SUMMARY.json unless --force.
 *
 * Usage:
 *   CURSOR_API_KEY=… node tools/run_full_bluebonnet_grok.mjs
 *   CURSOR_API_KEY=… node tools/run_full_bluebonnet_grok.mjs --only g5-m2
 *   CURSOR_API_KEY=… node tools/run_full_bluebonnet_grok.mjs --force
 */
import { Agent, Cursor } from "@cursor/sdk";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const REPO = "/home/lenovo/g10-control-center-loom";
const PROJECT = "bluebonnet-full-grok";
const INDEX = path.join(REPO, "projects", PROJECT, "FULL-RUN-INDEX.json");
const LOG = path.join(REPO, "projects", PROJECT, "FULL-RUN-LOG.jsonl");

/** Append Cursor RunResult.usage into projects/<id>/usage.jsonl (Python meter). */
function recordCursorUsage({
  project,
  step,
  model,
  runId,
  usage,
  elapsedMs,
  ok = true,
  error = null,
  finalize = false,
  extra = null,
}) {
  const args = [
    path.join(REPO, "tools/record_cursor_usage.py"),
    "--project",
    project,
    "--step",
    step,
    "--model",
    model,
    "--elapsed-ms",
    String(elapsedMs ?? 0),
  ];
  if (runId) args.push("--run-id", runId);
  if (usage) args.push("--usage-json", JSON.stringify(usage));
  if (!ok) args.push("--no-ok");
  if (error) args.push("--error", String(error));
  if (extra) args.push("--extra-json", JSON.stringify(extra));
  if (finalize) args.push("--finalize");
  const r = spawnSync("python3", args, { cwd: REPO, encoding: "utf8" });
  if (r.status !== 0) {
    console.warn("[usage] record failed:", r.stderr || r.stdout);
  }
  return r;
}

const args = process.argv.slice(2);
const force = args.includes("--force");
const onlyIdx = args.indexOf("--only");
const only = onlyIdx >= 0 ? args[onlyIdx + 1] : null;

const apiKey = process.env.CURSOR_API_KEY;
if (!apiKey) {
  console.error("CURSOR_API_KEY missing");
  process.exit(1);
}

const models = await Cursor.models.list({ apiKey });
const grok =
  models.find((m) => m.id === "grok-4.5") ||
  models.find((m) => /grok/i.test(m.id));
if (!grok) {
  console.error("No Grok model available");
  process.exit(1);
}
console.log("model", grok.id);

const index = JSON.parse(fs.readFileSync(INDEX, "utf8"));
let unitIds = Object.keys(index.units);
if (only) {
  if (!index.units[only]) {
    console.error("unknown unit", only, "known:", unitIds.join(", "));
    process.exit(1);
  }
  unitIds = [only];
}

function appendLog(row) {
  fs.appendFileSync(LOG, JSON.stringify(row) + "\n", "utf8");
}

function unitPaths(uid) {
  const base = path.join(REPO, "projects", PROJECT, "graph", "units", uid);
  return {
    base,
    summary: path.join(base, "SUMMARY.json"),
    steps: path.join(base, ".raw"),
    evidence: path.join(REPO, "projects", PROJECT, "evidence", uid),
  };
}

async function runUnit(uid) {
  const meta = index.units[uid];
  const paths = unitPaths(uid);
  if (!force && fs.existsSync(paths.summary)) {
    console.log(`[skip] ${uid} — SUMMARY exists`);
    return { unit_id: uid, skipped: true };
  }
  fs.mkdirSync(paths.steps, { recursive: true });

  const docList = meta.documents.map((d, i) => `${i + 1}. ${d}`).join("\n");
  const prompt = `You are running one UNIT of a full Bluebonnet graph job with Grok.

Repo cwd: ${REPO}
Project: ${PROJECT}
Unit id: ${uid}
Documents (${meta.n}):
${docList}

## Evidence (already extracted — READ THESE, do not load the whole ledger)
Directory: ${paths.evidence}
One JSON file per source (elements + excerpts). Use only these excerpts as ground truth.

## Your job
For EACH source, write THREE JSON files under:
${paths.steps}

Names (stem truncated OK to ~40–80 chars, must be unique per source):
- 01-role-<stem>.json
- 02-lessons-<stem>.json
- 03-assess-<stem>.json

Schemas:
1) {"source_file":"<exact basename>","role":"teacher_edition|learn_student|practice_student|succeed_student|other","citation_element_id":"...","excerpt_head":"..."}
   - Algebra TE/SE: use teacher_edition / learn_student (or other if truly a guide).
   - Guides/pacing/family: role "other".
2) {"source_file":"...","covers_lesson_numbers":[1,2],"citations":[{"element_id":"...","excerpt_head":"..."}],"notes":"..."}
   - Expand ranges fully ("Lesson 1 to 15" → 1..15).
   - Practice books: sparse lists only.
   - Guides with no lesson spine: [] is OK.
3) {"source_file":"...","is_assessment_bearing":false,"assessment_lesson_numbers":[],"assessment_name":null,"citations":[],"notes":"..."}
   - Practice student books usually true; whole Learn/TE usually false; quiz/assessment guides may be true.

## Assemble (required — run exactly)
cd ${REPO} && python3 tools/graph_assemble_from_steps.py \\
  --project ${PROJECT} \\
  --unit ${uid} \\
  --steps-dir ${paths.steps} \\
  --force

## Done
Print the SUMMARY JSON from the assemble script. Do not edit graph_assemble.py / graph_phase.py.
If a source evidence file is truncated, still do your best from included excerpts and note that in notes.`;

  console.log(`[run] ${uid} (${meta.n} files)…`);
  const started = Date.now();
  const result = await Agent.prompt(prompt, {
    apiKey,
    model: { id: grok.id },
    local: { cwd: REPO },
  });
  const elapsed_ms = Date.now() - started;
  const hasSummary = fs.existsSync(paths.summary);
  let summary = null;
  if (hasSummary) {
    summary = JSON.parse(fs.readFileSync(paths.summary, "utf8"));
  }
  const err =
    result.status === "error" ? String(result.result || "error") : null;
  recordCursorUsage({
    project: PROJECT,
    step: `grok-unit:${uid}`,
    model: grok.id,
    runId: result.id,
    usage: result.usage || null,
    elapsedMs: elapsed_ms,
    ok: result.status !== "error",
    error: err,
    extra: { unit_id: uid, n_docs: meta.n },
  });
  const row = {
    ts: new Date().toISOString(),
    unit_id: uid,
    n_docs: meta.n,
    agent_status: result.status,
    run_id: result.id,
    elapsed_ms,
    has_summary: hasSummary,
    n_lessons: summary?.n_lessons ?? null,
    step_summary: summary?.step_summary ?? null,
    usage: result.usage || null,
    error: err,
  };
  appendLog(row);
  console.log(
    `[done] ${uid} status=${result.status} summary=${hasSummary} lessons=${row.n_lessons} ${elapsed_ms}ms` +
      (result.usage?.totalTokens != null
        ? ` tokens=${result.usage.totalTokens}`
        : " tokens=?"),
  );
  if (result.status === "error") {
    console.error(result.result);
  }
  return row;
}

const results = [];
for (const uid of unitIds) {
  try {
    results.push(await runUnit(uid));
  } catch (e) {
    const row = {
      ts: new Date().toISOString(),
      unit_id: uid,
      agent_status: "throw",
      error: String(e?.message || e),
    };
    appendLog(row);
    results.push(row);
    console.error(`[throw] ${uid}`, e);
  }
}

const rollupPath = path.join(REPO, "projects", PROJECT, "FULL-RUN-ROLLUP.json");
const rollup = {
  project: PROJECT,
  model: grok.id,
  finished_at: new Date().toISOString(),
  n_units_attempted: results.length,
  n_summaries: results.filter((r) => r.has_summary || r.skipped).length,
  results,
};
fs.writeFileSync(rollupPath, JSON.stringify(rollup, null, 2) + "\n");
// Finalize USAGE-SUMMARY.json from all recorded Cursor + any Python calls.
spawnSync(
  "python3",
  [
    path.join(REPO, "tools/record_cursor_usage.py"),
    "--project",
    PROJECT,
    "--step",
    "finalize",
    "--model",
    grok.id,
    "--finalize-only",
  ],
  { cwd: REPO, encoding: "utf8" },
);
console.log("\n=== ROLLUP ===");
console.log(JSON.stringify(rollup, null, 2));
const failed = results.filter((r) => !r.skipped && !r.has_summary);
process.exit(failed.length ? 2 : 0);
