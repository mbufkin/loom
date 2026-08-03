/**
 * Full graph test: Cursor SDK Agent (Grok) produces narrow-step JSON;
 * Loom code merges + rebuilds + scores vs Grok gold.
 */
import { Agent, Cursor } from "@cursor/sdk";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const REPO = "/home/lenovo/g10-control-center-loom";
const PROJECT = "bluebonnet-g5-m1-graph-test";
const UNIT = "place-value-decimals";
const STEPS = path.join(REPO, "projects", PROJECT, "graph", "units", UNIT, ".raw");
const GOLD = path.join(REPO, "projects", PROJECT, "graph-gold", "HAS-PART.json");

const apiKey = process.env.CURSOR_API_KEY;
if (!apiKey) {
  console.error("CURSOR_API_KEY missing");
  process.exit(1);
}

const models = await Cursor.models.list({ apiKey });
const grok =
  models.find((m) => m.id === "grok-4.5") ||
  models.find((m) => /grok/i.test(m.id)) ||
  models.find((m) => /grok/i.test(m.displayName || ""));
if (!grok) {
  console.error(
    "No Grok model in catalog. Available:",
    models.map((m) => m.id).slice(0, 40).join(", "),
  );
  process.exit(1);
}
console.log("Using model", grok.id, grok.displayName || "");

fs.mkdirSync(STEPS, { recursive: true });

const prompt = `You are running a FULL graph-phase test for Bluebonnet G5 Module 1.

Repo cwd is already ${REPO}.

## Goal
For project \`${PROJECT}\`, unit \`${UNIT}\`, produce narrow-step JSON for each of the 4 sources by READING ledger evidence (not inventing from packaging memory), then assemble with Loom code and score vs gold.

## Sources (exact basenames)
1. K-5_Math_Grade_5_Module_1_Place_Value_and_Decimals_Teacher_Edition.pdf
2. K-5_Math_Grade_5_Module_1_Learn_Place_Value_and_Decimals_Student_Edition.pdf
3. K-5_Math_Grade_5_Module_1_Practice_Place_Value_and_Decimals_Student_Edition.pdf
4. K-5_Math_Grade_5_Module_1_Succeed_Place_Value_and_Decimals_Student_Edition.pdf

## Evidence
- Ledger: projects/${PROJECT}/layer0/ledger.json (symlink to bluebonnet-math-2026 ledger)
- Filter rows where source_file equals each basename. Use excerpts as ground truth.

## For EACH source, write THREE JSON files under:
${STEPS}

Filenames (stem may be truncated to ~40 chars like the 30B runner):
- 01-role-<stem>.json
- 02-lessons-<stem>.json
- 03-assess-<stem>.json

Schemas:
1) role: {"source_file":"...","role":"teacher_edition|learn_student|practice_student|succeed_student|other","citation_element_id":"...","excerpt_head":"..."}
2) lessons: {"source_file":"...","covers_lesson_numbers":[1,2],"citations":[{"element_id":"...","excerpt_head":"..."}],"notes":"..."}
   - Expand ranges fully (e.g. Lesson 1 to 15 → [1..15]).
   - Practice is sparse (only listed lessons).
3) assess: {"source_file":"...","is_assessment_bearing":false,"assessment_lesson_numbers":[],"assessment_name":null,"citations":[],"notes":"..."}
   - Practice book is usually assessment-bearing; Learn TE usually not as whole-file Assessment.

## Then run (exactly):
cd ${REPO} && python3 tools/graph_assemble_from_steps.py \\
  --project ${PROJECT} \\
  --unit ${UNIT} \\
  --steps-dir ${STEPS} \\
  --gold ${GOLD} \\
  --force

## Done criteria
Print the SUMMARY JSON. Prefer pass_provisional true with n_pred_lessons=15. If fail, explain which book under-read.

Do not modify graph_assemble.py / graph_inventory.py / graph_phase.py. Only write step JSON + run the assemble script.`;

const started = Date.now();
const result = await Agent.prompt(prompt, {
  apiKey,
  model: { id: grok.id },
  local: { cwd: REPO },
});
const elapsedMs = Date.now() - started;

console.log("\n=== Agent status ===", result.status);
console.log("run id:", result.id);
if (result.usage) console.log("usage:", JSON.stringify(result.usage));
if (result.result) console.log("\n=== Agent result ===\n", result.result);

const usageArgs = [
  path.join(REPO, "tools/record_cursor_usage.py"),
  "--project",
  PROJECT,
  "--step",
  `grok-graph-test:${UNIT}`,
  "--model",
  grok.id,
  "--run-id",
  result.id || "",
  "--elapsed-ms",
  String(elapsedMs),
  "--finalize",
];
if (result.usage) usageArgs.push("--usage-json", JSON.stringify(result.usage));
if (result.status === "error") {
  usageArgs.push("--no-ok", "--error", String(result.result || "error"));
}
spawnSync("python3", usageArgs, { cwd: REPO, encoding: "utf8", stdio: "inherit" });

const summaryPath = path.join(
  REPO,
  "projects",
  PROJECT,
  "graph",
  "units",
  UNIT,
  "SUMMARY.json",
);
if (fs.existsSync(summaryPath)) {
  console.log("\n=== SUMMARY.json ===");
  console.log(fs.readFileSync(summaryPath, "utf8"));
} else {
  console.error("SUMMARY.json missing after agent run");
}

process.exit(result.status === "error" ? 2 : 0);
