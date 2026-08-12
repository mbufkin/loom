/**
 * One-unit Cursor SDK graph reviewer (Grok by default).
 * Invoked by graph_phase.py --backend cursor.
 *
 * Writes narrow-step JSON under --steps-dir, then runs
 * tools/graph_assemble_from_steps.py into --out-dir.
 *
 * Usage:
 *   CURSOR_API_KEY=… node tools/run_graph_cursor.mjs \
 *     --project dallas-career-2026 --unit agriculture \
 *     --out-dir …/graph/runs/grok-4.5/units/agriculture \
 *     --steps-dir …/.raw --evidence-dir …/evidence --model grok-4.5
 */
import { Agent, Cursor } from "@cursor/sdk";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

function arg(flag, fallback = null) {
  const i = process.argv.indexOf(flag);
  if (i >= 0 && process.argv[i + 1]) return process.argv[i + 1];
  return fallback;
}

const REPO = arg("--repo", "/home/lenovo/g10-control-center-loom");
const PROJECT = arg("--project");
const UNIT = arg("--unit");
const OUT_DIR = arg("--out-dir");
const STEPS = arg("--steps-dir");
const EVIDENCE = arg("--evidence-dir");
const MODEL = arg("--model", "grok-4.5");
const force = process.argv.includes("--force");

if (!PROJECT || !UNIT || !OUT_DIR || !STEPS || !EVIDENCE) {
  console.error(
    "Required: --project --unit --out-dir --steps-dir --evidence-dir [--model] [--repo] [--force]",
  );
  process.exit(2);
}

const apiKey = process.env.CURSOR_API_KEY;
if (!apiKey) {
  console.error("CURSOR_API_KEY missing");
  process.exit(1);
}

const models = await Cursor.models.list({ apiKey });
const model =
  models.find((m) => m.id === MODEL) ||
  models.find((m) => /grok/i.test(m.id)) ||
  models[0];
if (!model) {
  console.error("No Cursor model available");
  process.exit(1);
}
console.log("[cursor-graph] model", model.id, "unit", UNIT);

fs.mkdirSync(STEPS, { recursive: true });
fs.mkdirSync(OUT_DIR, { recursive: true });

const evidenceFiles = fs
  .readdirSync(EVIDENCE)
  .filter((f) => f.endsWith(".json"));
const docList = evidenceFiles.map((f, i) => `${i + 1}. ${f}`).join("\n");

const prompt = `You are running ONE unit of the Loom graph phase (narrow-steps).

Repo cwd: ${REPO}
Project: ${PROJECT}
Unit id: ${UNIT}

## Evidence (READ THESE — ledger excerpts; do not invent from memory)
Directory: ${EVIDENCE}
Files:
${docList}

## Your job
For EACH source evidence JSON, write THREE step files under:
${STEPS}

Names (stem truncated OK to ~40–80 chars, must be unique per source):
- 01-role-<stem>.json
- 02-lessons-<stem>.json
- 03-assess-<stem>.json

Use the exact source_file basename from each evidence JSON.

Schemas:
1) {"source_file":"<exact basename>","role":"teacher_edition|learn_student|practice_student|succeed_student|other","citation_element_id":"...","excerpt_head":"..."}
   - Career CTE lesson plans → often "other" or learn_student if clearly student-facing.
   - Teacher editions / teacher guides → teacher_edition.
   - Quizzes / assessments → practice_student or other with assessment true below.
2) {"source_file":"...","covers_lesson_numbers":[1,2],"citations":[{"element_id":"...","excerpt_head":"..."}],"notes":"..."}
   - Expand ranges fully ("Lesson 1 to 15" → 1..15).
   - If no lesson numbers in evidence, [] is OK.
3) {"source_file":"...","is_assessment_bearing":false,"assessment_lesson_numbers":[],"assessment_name":null,"citations":[],"notes":"..."}

## Assemble (required — run exactly)
cd ${REPO} && python3 tools/graph_assemble_from_steps.py \\
  --project ${PROJECT} \\
  --unit ${UNIT} \\
  --steps-dir ${STEPS} \\
  --out-dir ${OUT_DIR} \\
  --model-label ${model.id} \\
  --force

## Done
Print the SUMMARY JSON. Do not edit graph_assemble.py / graph_phase.py.
If evidence is truncated, note that in notes and do your best from excerpts.`;

const started = Date.now();
const result = await Agent.prompt(prompt, {
  apiKey,
  model: { id: model.id },
  local: { cwd: REPO },
});
const elapsedMs = Date.now() - started;

console.log("[cursor-graph] status", result.status, "run", result.id, `${elapsedMs}ms`);
if (result.usage) console.log("[cursor-graph] usage", JSON.stringify(result.usage));
if (result.status === "error") {
  console.error(result.result);
}

const usageArgs = [
  path.join(REPO, "tools/record_cursor_usage.py"),
  "--project",
  PROJECT,
  "--step",
  `graph-cursor:${UNIT}`,
  "--model",
  model.id,
  "--run-id",
  result.id || "",
  "--elapsed-ms",
  String(elapsedMs),
];
if (result.usage) usageArgs.push("--usage-json", JSON.stringify(result.usage));
if (result.status === "error") {
  usageArgs.push("--no-ok", "--error", String(result.result || "error"));
}
spawnSync("python3", usageArgs, { cwd: REPO, encoding: "utf8" });

const summaryPath = path.join(OUT_DIR, "SUMMARY.json");
if (!fs.existsSync(summaryPath)) {
  // Fallback: assemble locally if the agent skipped the shell step.
  console.warn("[cursor-graph] SUMMARY missing — assembling locally");
  const assemble = spawnSync(
    "python3",
    [
      path.join(REPO, "tools/graph_assemble_from_steps.py"),
      "--project",
      PROJECT,
      "--unit",
      UNIT,
      "--steps-dir",
      STEPS,
      "--out-dir",
      OUT_DIR,
      "--model-label",
      model.id,
      "--force",
    ],
    { cwd: REPO, encoding: "utf8" },
  );
  console.log(assemble.stdout || "");
  if (assemble.status !== 0) {
    console.error(assemble.stderr || assemble.stdout);
    process.exit(assemble.status || 1);
  }
}

if (!fs.existsSync(summaryPath)) {
  console.error("[cursor-graph] still no SUMMARY.json");
  process.exit(1);
}
console.log(fs.readFileSync(summaryPath, "utf8"));
process.exit(result.status === "error" ? 1 : 0);
