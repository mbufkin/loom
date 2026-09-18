import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, describeError } from "../lib/api";
import { MarkdownViewer } from "../components/MarkdownViewer";
import {
  OutputNav,
  VIEW_GRAPH,
  VIEW_PATHS,
  VIEW_UNITS,
} from "../components/OutputNav";
import type { NavDoc } from "../components/OutputNav";
import { ReviewSlip } from "../components/ReviewSlip";
import { UnitDetail } from "../components/UnitDetail";
import { LessonDetail } from "../components/LessonDetail";
import { ArtifactDetail } from "../components/ArtifactDetail";
import { UnitOutputRow } from "../components/UnitOutputRow";
import { PacketTypeBar } from "../components/PacketTypeBar";
import { RunProgress } from "../components/RunProgress";
import { GraphBelongingPanel } from "../components/GraphBelongingPanel";
import { PathsPanel } from "../components/PathsPanel";
import { FirstRun } from "../components/FirstRun";
import { ServiceDown } from "../components/ServiceDown";
import type {
  ArtifactRung,
  Band,
  CurriculumReview,
  E2ERunInfo,
  GraphOverview,
  GraphRunInfo,
  GraphUnitDetail,
  LessonFeedback,
  OutputsTree,
  PathsSummary,
  Project,
  RunPreflight,
  RunStatus,
  Stats,
  UnitRollup,
  UnitRung,
} from "../types";

const UNITS_VIEW = VIEW_UNITS;
const GRAPH_VIEW = VIEW_GRAPH;
const PATHS_VIEW = VIEW_PATHS;
const UNIT_DETAIL = "__unit_detail__";
const LESSON_DETAIL = "__lesson_detail__";
const ARTIFACT_DETAIL = "__artifact_detail__";

/** Short label for the model picker (run_id when model is a local path). */
function graphRunLabel(r: GraphRunInfo): string {
  const m = (r.model || "").trim();
  if (!m) return r.run_id;
  if (m.includes("/") || m.endsWith(".gguf")) return r.run_id;
  return m;
}

/** Human label for a finished audit: when it completed, not its internal id.
 *
 * Reviewers pick between audits by recency ("the one from last Tuesday"), so
 * the date is the useful handle. The run id only surfaces when the server
 * could not read a completion time.
 */
function auditLabel(r?: E2ERunInfo): string {
  if (!r) return "audit";
  const units = r.n_output_units ? ` · ${r.n_output_units} units` : "";
  if (!r.finished_at) return `Audit · ${r.run_id}${units}`;
  const when = new Date(r.finished_at * 1000).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `Audit · ${when}${units}`;
}

/** Curriculum option text: prefer the manifest title, fall back to the id. */
function curriculumOptionLabel(p: Project): string {
  return (p.title || p.id).trim();
}

/** Most recently audited first, then never-audited alphabetically.
 *
 * Mirrors the order the API returns. This used to rank by a tier parsed out of
 * projects/STATUS.md, which grades our sample corpus and is simply absent on an
 * installed copy — there, every curriculum tied and the list was unordered.
 */
function projectSortKey(p: Project): [number, string, string] {
  return [-(p.last_audit ?? 0), (p.title || p.id).toLowerCase(), p.id];
}

// Prefer the real unit-rung band; otherwise derive a heat band from Layer 1 role
// fulfillment so the heatmap still renders for projects without a unit rung.
function deriveBand(r: UnitRollup): Band {
  const total = r.fulfilled + r.missing;
  if (total === 0) return "Unrated";
  const pct = r.fulfilled / total;
  if (r.mismatch > 0 || pct < 0.34) return "Weak";
  if (pct >= 0.67) return "Strong";
  return "Developing";
}

/** Optional deep-link into a completed E2E run: ?project=&e2e=&lesson= */
function reviewDeepLink(): {
  project?: string;
  e2e?: string;
  lesson?: string;
  advanced: boolean;
} {
  if (typeof window === "undefined") return { advanced: false };
  const q = new URLSearchParams(window.location.search);
  // Live root is not a review surface — e2e must be a real run id when set.
  const e2e = (q.get("e2e") || "").trim() || undefined;
  return {
    project: q.get("project") || undefined,
    e2e,
    lesson: q.get("lesson") || undefined,
    // ?advanced=1 reveals the engineering controls (lab forks, model runs).
    // They are meaningless to a curriculum reviewer and several of them are
    // permanently disabled on a normal install, so a control you cannot use is
    // simply noise. Opt-in rather than opt-out.
    advanced: q.get("advanced") === "1",
  };
}

export function RunReview() {
  const deepLink = useMemo(() => reviewDeepLink(), []);
  const [projects, setProjects] = useState<Project[]>([]);
  // Empty until the project list arrives and picks one with results. Seeding a
  // hardcoded district here would flash somebody else's curriculum name in the
  // picker before the real default settles.
  const [projectId, setProjectId] = useState<string>(deepLink.project || "");
  // Lab forks (lab-*) stay out of Curriculum until the reviewer opts in.
  const [showLabForks, setShowLabForks] = useState(false);
  const [outputs, setOutputs] = useState<OutputsTree | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [unitRung, setUnitRung] = useState<UnitRung | null>(null);
  const [lessonFeedback, setLessonFeedback] = useState<LessonFeedback | null>(
    null
  );
  const [artifactRung, setArtifactRung] = useState<ArtifactRung | null>(null);
  const [lessonReview, setLessonReview] = useState<CurriculumReview | null>(
    null
  );
  // Only REVIEW-READY e2e runs are listed; empty = waiting for a completed run.
  const [e2eRuns, setE2eRuns] = useState<E2ERunInfo[]>([]);
  const [e2eRunId, setE2eRunId] = useState<string>(deepLink.e2e ?? "");
  const [e2eListLoaded, setE2eListLoaded] = useState(false);
  // One-shot: open a lesson once quality/review plates have loaded.
  const [pendingLessonId, setPendingLessonId] = useState<string | null>(
    deepLink.lesson ?? null
  );
  // Model graph A/B: curriculum picker + model picker drive the belonging panel.
  // When an E2E workspace is selected, graph runs are nested under that tree.
  const [graphRuns, setGraphRuns] = useState<GraphRunInfo[]>([]);
  const [graphRunId, setGraphRunId] = useState<string>("");
  const [graphOverview, setGraphOverview] = useState<GraphOverview | null>(null);
  const [graphUnitDetail, setGraphUnitDetail] =
    useState<GraphUnitDetail | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  // Paths A–H: the router's eight review lenses for the current workspace.
  const [pathsSummary, setPathsSummary] = useState<PathsSummary | null>(null);
  const [pathsLoading, setPathsLoading] = useState(false);

  const [activePath, setActivePath] = useState<string | null>(null);
  const [activeType, setActiveType] = useState<string>("md");
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(
    null
  );
  // Which unit's review of that document to show. A course-level document is
  // filed under every unit it serves, so a doc_id on its own no longer names
  // one review: the artifact rung judges a document in the context of the unit
  // it sits in, and verdicts like "quiz -> key pairing" depend on that unit's
  // other documents. Without this, opening the pacing guide under Unit 2 shows
  // the review written for Unit 1.
  const [selectedArtifactUnitId, setSelectedArtifactUnitId] = useState<
    string | null
  >(null);
  const [viewerText, setViewerText] = useState<string>("");
  // A sentence the reviewer can act on, plus the raw text behind a disclosure.
  // Never render the detail on its own: it is a status code and a URL.
  const [error, setError] = useState<{
    message: string;
    detail?: string;
  } | null>(null);
  // Distinct from `error`: this means the local API is unreachable, so nothing
  // on the page can be trusted. Kept separate because loadWorkspace clears
  // `error` on every navigation and would wipe it out.
  const [serviceError, setServiceError] = useState<{
    message: string;
    detail?: string;
  } | null>(null);
  // Bumped by the retry action so every data effect re-runs. Reloading only the
  // project list is not enough: the e2e-run lookup keys off projectId, which is
  // unchanged after a recovery, so the console would keep showing the stale
  // "not audited yet" state even though the service was back.
  const [reloadKey, setReloadKey] = useState(0);

  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const pollRef = useRef<number | null>(null);
  // Asked once: can this machine start an audit at all? Drives whether the
  // first-run screen offers a button or explains why it cannot.
  const [preflight, setPreflight] = useState<RunPreflight | null>(null);

  // Placeholder for the window between "a project is selected" and "the list
  // has arrived", so the panels below can render without null checks.
  const project: Project = projects.find((p) => p.id === projectId) ?? {
    id: projectId,
    has_output: false,
    has_stats: false,
    has_unit_rung: false,
  };

  // A curriculum is a folder ingest has organised into units. The fallback
  // catches one that has documents but has not been organised yet, so a
  // half-finished setup is still reachable instead of silently missing.
  const curriculumProjects = useMemo(() => {
    const ingested = projects.filter((p) => p.kind === "curriculum");
    const list =
      ingested.length > 0
        ? ingested
        : projects.filter((p) => p.kind !== "lab" && !p.id.startsWith("lab-"));
    return [...list].sort((a, b) => {
      const ka = projectSortKey(a);
      const kb = projectSortKey(b);
      return ka[0] - kb[0] || ka[1].localeCompare(kb[1]) || ka[2].localeCompare(kb[2]);
    });
  }, [projects]);

  // Curricula that actually have something to review, offered as one-click
  // escapes on the first-run screen. Labs stay out: they are not a place to
  // send someone who just wants to see a finished audit.
  const reviewableProjects = useMemo(
    () =>
      projects.filter(
        (p) =>
          p.has_review_run && p.kind !== "lab" && !p.id.startsWith("lab-")
      ),
    [projects]
  );

  const labProjects = useMemo(() => {
    return projects
      .filter((p) => p.kind === "lab" || p.id.startsWith("lab-"))
      .sort((a, b) =>
        (a.title || a.id).localeCompare(b.title || b.id, undefined, {
          sensitivity: "base",
        })
      );
  }, [projects]);

  // Model runs A–Z by display label (stable secondary key = run_id).
  const sortedGraphRuns = useMemo(() => {
    return [...graphRuns].sort((a, b) => {
      const la = graphRunLabel(a).toLowerCase();
      const lb = graphRunLabel(b).toLowerCase();
      return la.localeCompare(lb) || a.run_id.localeCompare(b.run_id);
    });
  }, [graphRuns]);

  // Load the project list. Prefer ?project= deep-link, else the first
  // curriculum with results.
  // Best practice: never clobber an explicit URL curriculum with the default.
  // Extracted from the effect so the offline screen can offer a real retry.
  const loadProjects = useCallback(() => {
    api
      .projects()
      .then((ps) => {
        setServiceError(null);
        setProjects(ps);
        const curricula = ps.filter((p) => p.kind === "curriculum");
        const fallback =
          curricula.length > 0
            ? curricula
            : ps.filter((p) => p.kind !== "lab" && !p.id.startsWith("lab-"));
        // Honour an explicit ?project= against the *full* API list, not just the
        // curated curriculum rows. An ad-hoc tree (kind "other", e.g. a local
        // smoke run) is a real reviewable project, and matching only `fallback`
        // silently dropped the deep link and loaded the default instead.
        const linked =
          deepLink.project && ps.some((p) => p.id === deepLink.project)
            ? deepLink.project
            : undefined;
        // Land on something that will actually render. The console only shows
        // finished audits, so opening on a curriculum without one meant a blank
        // page with no explanation. No district is hardcoded here: Loom serves
        // any district, and privileging one by name is both wrong for everyone
        // else and a guaranteed dead end wherever that folder is absent.
        // Preference order: the URL, a curriculum with a finished audit, any
        // project with one, then simply the first curriculum listed.
        const firstReviewable = (list: Project[]) =>
          list.find((p) => p.has_review_run)?.id;
        const next =
          linked ??
          firstReviewable(fallback) ??
          firstReviewable(ps) ??
          fallback[0]?.id;
        if (next) setProjectId(next);
      })
      // If the project list itself cannot be fetched the service is down, and
      // every "nothing here yet" panel below would be telling the reviewer a
      // comfortable lie. Record it separately so the UI can say so outright.
      .catch((e) => setServiceError(describeError(e)));
  }, [deepLink.project]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects, reloadKey]);

  // Capability check for the audit button. A failure here is not worth an error
  // banner: treat it as "cannot run" and let the first-run screen say so.
  useEffect(() => {
    api
      .canRun()
      .then(setPreflight)
      .catch(() =>
        setPreflight({
          can_run: false,
          missing: ["a working connection to the local Loom service"],
          platform: "unknown",
        })
      );
  }, []);

  // Keep the address bar shareable as the reviewer changes curriculum / E2E run.
  useEffect(() => {
    if (typeof window === "undefined" || !projectId) return;
    const q = new URLSearchParams(window.location.search);
    q.set("project", projectId);
    if (e2eRunId) q.set("e2e", e2eRunId);
    else q.delete("e2e");
    // Strip ?view= if an old bookmark still carries it. It named the Overview
    // and Next Steps decks, and an address bar advertising a page that no
    // longer exists is worse than no parameter at all.
    q.delete("view");
    const next = `${window.location.pathname}?${q.toString()}`;
    const cur = `${window.location.pathname}${window.location.search}`;
    if (next !== cur) window.history.replaceState(null, "", next);
  }, [projectId, e2eRunId]);

  const loadDoc = useCallback(
    async (id: string, path: string, type = "md", e2eRun?: string) => {
      setActivePath(path);
      setActiveType(type);
      // PDF and HTML are shown via embed/iframe (own contrast styles); skip MD parse.
      if (type === "pdf" || type === "html") {
        setViewerText("");
        return;
      }
      try {
        const txt = await api.fileText(id, path, e2eRun);
        setViewerText(txt);
      } catch (e) {
        setViewerText(`Could not load \`${path}\`\n\n${String(e)}`);
      }
    },
    []
  );

  // Load plates / stats / graph for a completed E2E workspace only.
  const loadWorkspace = useCallback(
    async (id: string, e2eRun: string) => {
      setError(null);
      setOutputs(null);
      setStats(null);
      setUnitRung(null);
      setGraphRuns([]);
      setGraphRunId("");
      setGraphOverview(null);
      setGraphUnitDetail(null);
      setLessonFeedback(null);
      setArtifactRung(null);
      setLessonReview(null);
      setPathsSummary(null);
      if (!e2eRun) {
        return;
      }
      const e2e = e2eRun;
      try {
        const tree = await api.outputs(id, e2e);
        setOutputs(tree);
        // Default to the first available plate (Dashboard).
        const first = tree.plates[0] ?? tree.layers[0];
        if (first) await loadDoc(id, first.path, first.type, e2e);
        else {
          setActivePath(UNITS_VIEW);
          setActiveType("md");
        }
      } catch (e) {
        // Still offer View → Curriculum graph when plates are not ready yet.
        setOutputs({ plates: [], layers: [], pdfs: [], units: [], e2e_run: e2e });
        setActivePath(GRAPH_VIEW);
        setActiveType("md");
        setError({
          message:
            "The reports for this audit aren’t readable yet — it may still be finishing.",
          detail: `no output plates for ${id}/${e2e}: ${describeError(e).detail}`,
        });
      }
      api.stats(id, e2e).then(setStats).catch(() => setStats(null));
      api.unitRung(id, e2e).then(setUnitRung);
      api.artifactRung(id, e2e).then(setArtifactRung);
      // Paths A–H. Reads route-map + path_*/findings.json, which exist well
      // before the output plates do, so this is safe on a partial workspace.
      setPathsLoading(true);
      api
        .paths(id, e2e)
        .then(setPathsSummary)
        .catch(() => setPathsSummary(null))
        .finally(() => setPathsLoading(false));
      // Graph A/B (or nested graph under the E2E mirror).
      setGraphLoading(true);
      api
        .graphRuns(id, e2e)
        .then((res) => {
          setGraphRuns(res.runs);
          // Prefer active pointer on live root; under E2E prefer matching run id.
          const preferred =
            e2e && res.runs.some((r) => r.run_id === e2e)
              ? e2e
              : res.active && res.runs.some((r) => r.run_id === res.active)
                ? res.active
                : res.runs[0]?.run_id ?? "";
          setGraphRunId(preferred);
        })
        .catch(() => {
          setGraphRuns([]);
          setGraphRunId("");
        })
        .finally(() => setGraphLoading(false));
    },
    [loadDoc]
  );

  // Curriculum change: list REVIEW-READY e2e runs only; auto-select when one.
  useEffect(() => {
    let cancelled = false;
    setE2eListLoaded(false);
    setE2eRuns([]);
    setE2eRunId("");
    // No curriculum chosen yet (the list is still loading). Requesting
    // /api/projects//e2e/runs would just 404 and flash a false empty state.
    if (!projectId) return;
    api
      .e2eRuns(projectId)
      .then((res) => {
        if (cancelled) return;
        setE2eRuns(res.runs);
        const deep =
          deepLink.e2e && res.runs.some((r) => r.run_id === deepLink.e2e)
            ? deepLink.e2e
            : undefined;
        // One ready run → select it. Several → prefer deep-link, else first.
        const preferred =
          deep ??
          (res.runs.length === 1 ? res.runs[0].run_id : res.runs[0]?.run_id) ??
          "";
        setE2eRunId(preferred);
        setE2eListLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setE2eRuns([]);
        setE2eRunId("");
        setE2eListLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, deepLink.e2e, reloadKey]);

  // Workspace reload whenever a completed E2E selection settles.
  useEffect(() => {
    if (!projectId) return;
    loadWorkspace(projectId, e2eRunId);
  }, [projectId, e2eRunId, loadWorkspace]);

  // Selected model run → belonging overview (drives the panel under the heatmap).
  useEffect(() => {
    if (!projectId || !graphRunId) {
      setGraphOverview(null);
      return;
    }
    let cancelled = false;
    const e2e = e2eRunId || undefined;
    setGraphLoading(true);
    api
      .graphOverview(projectId, graphRunId, e2e)
      .then((ov) => {
        if (!cancelled) setGraphOverview(ov);
      })
      .catch(() => {
        if (!cancelled) setGraphOverview(null);
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, graphRunId, e2eRunId]);

  // Quality + curriculum-review plates from the selected ready E2E tree only.
  useEffect(() => {
    if (!projectId || !e2eRunId) {
      setLessonFeedback(null);
      setLessonReview(null);
      return;
    }
    let cancelled = false;
    const rid = graphRunId || undefined;
    Promise.all([
      api.lessonFeedback(projectId, rid, e2eRunId),
      api.lessonReview(projectId, rid, e2eRunId),
    ])
      .then(([fb, rev]) => {
        if (cancelled) return;
        setLessonFeedback(fb);
        setLessonReview(rev);
      })
      .catch(() => {
        if (cancelled) return;
        setLessonFeedback(null);
        setLessonReview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, graphRunId, e2eRunId]);

  // Deep-link ?lesson=… → lesson detail once the quality plate is present.
  useEffect(() => {
    if (!pendingLessonId || !lessonFeedback || !e2eRunId) return;
    for (const ls of Object.values(lessonFeedback.units)) {
      const hit = ls.find((l) => l.lesson_id === pendingLessonId);
      if (hit) {
        setSelectedUnitId(hit.unit_id);
        setSelectedLessonId(pendingLessonId);
        setSelectedArtifactId(null);
        setActivePath(LESSON_DETAIL);
        setActiveType("md");
        setPendingLessonId(null);
        return;
      }
    }
  }, [pendingLessonId, lessonFeedback]);

  // Open unit + selected model → materials / lessons / assessments (HAS-PART).
  // Load on unit drill-down *and* Curriculum graph view so the SVG can draw
  // below-unit nodes (previously GRAPH_VIEW cleared detail and stayed unit-only).
  useEffect(() => {
    if (!projectId || !graphRunId || !selectedUnitId) {
      setGraphUnitDetail(null);
      return;
    }
    if (activePath !== UNIT_DETAIL && activePath !== GRAPH_VIEW) {
      setGraphUnitDetail(null);
      return;
    }
    let cancelled = false;
    const e2e = e2eRunId || undefined;
    api
      .graphUnit(projectId, graphRunId, selectedUnitId, e2e)
      .then((d) => {
        if (!cancelled) setGraphUnitDetail(d);
      })
      .catch(() => {
        if (!cancelled) setGraphUnitDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, graphRunId, e2eRunId, selectedUnitId, activePath]);

  // --- run + poll ---------------------------------------------------------
  const stopPoll = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startRun = useCallback(async () => {
    try {
      stopPoll();
      const id = await api.startRun(projectId, []);
      setRunStatus({ runId: id, status: "running", exitCode: null, log: "" });
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await api.runStatus(id);
          setRunStatus(s);
          if (s.status !== "running") {
            stopPoll();
            // Live audit writes to project root — refresh that workspace.
            loadWorkspace(projectId, e2eRunId);
          }
        } catch {
          /* keep polling */
        }
      }, 1500);
    } catch (e) {
      setError(describeError(e));
    }
  }, [projectId, e2eRunId, loadWorkspace]);

  useEffect(() => stopPoll, []);

  const running = runStatus?.status === "running";

  const bandFor = useCallback(
    (u: UnitRollup): Band => {
      const real = unitRung?.units?.[u.unit_id]?.band;
      return real ?? deriveBand(u);
    },
    [unitRung]
  );

  // Completeness (Chip 1) comes straight from the unit rung; undefined when the
  // rung predates the packet-type work, so the chip degrades to "unknown".
  const completenessFor = useCallback(
    (u: UnitRollup) => unitRung?.units?.[u.unit_id]?.completeness ?? null,
    [unitRung]
  );

  // Drill-down now opens the rich unit-rung detail panel (rendered from the
  // already-loaded UNIT-RUNG.json) instead of the thin per-unit stub. The stub
  // and other artifacts remain reachable as links inside the panel.
  const openUnitDetail = useCallback((unitId: string) => {
    setSelectedUnitId(unitId);
    setSelectedLessonId(null);
    setSelectedArtifactId(null);
    setActivePath(UNIT_DETAIL);
    setActiveType("md");
  }, []);

  const openLessonDetail = useCallback((lessonId: string) => {
    setSelectedLessonId(lessonId);
    setActivePath(LESSON_DETAIL);
    setActiveType("md");
  }, []);

  const openArtifactDetail = useCallback((docId: string, unitId?: string) => {
    setSelectedArtifactId(docId);
    setSelectedArtifactUnitId(unitId ?? null);
    setActivePath(ARTIFACT_DETAIL);
    setActiveType("md");
  }, []);

  // Lessons for the currently-selected unit (from LESSON-QUALITY-FEEDBACK.json).
  const selectedUnitLessons = useMemo(() => {
    if (!selectedUnitId || !lessonFeedback) return [];
    return lessonFeedback.units[selectedUnitId] ?? [];
  }, [selectedUnitId, lessonFeedback]);

  const selectedLesson = useMemo(() => {
    if (!selectedLessonId || !lessonFeedback) return undefined;
    for (const ls of Object.values(lessonFeedback.units)) {
      const hit = ls.find((l) => l.lesson_id === selectedLessonId);
      if (hit) return hit;
    }
    return undefined;
  }, [selectedLessonId, lessonFeedback]);

  // The grounded curriculum review for the selected lesson (if one has been
  // generated). Matched by lesson_id across units, same as the quality feedback.
  const selectedLessonReview = useMemo(() => {
    if (!selectedLessonId || !lessonReview) return undefined;
    for (const ls of Object.values(lessonReview.units)) {
      const hit = ls.find((l) => l.lesson_id === selectedLessonId);
      if (hit) return hit;
    }
    return undefined;
  }, [selectedLessonId, lessonReview]);

  // The artifact rung's per-unit block for the selected unit, and the single doc
  // record for the artifact drill-down.
  const selectedUnitArtifacts = useMemo(() => {
    if (!selectedUnitId || !artifactRung) return undefined;
    return artifactRung.units[selectedUnitId];
  }, [selectedUnitId, artifactRung]);

  // The reviewed documents per unit, in the shape the rail needs. Sorted by
  // title so a unit's documents read in a stable order rather than whatever
  // order the rung happened to write them in.
  const docsByUnit = useMemo(() => {
    const out: Record<string, NavDoc[]> = {};
    for (const [unitId, u] of Object.entries(artifactRung?.units ?? {})) {
      out[unitId] = u.documents
        .map((d) => ({
          doc_id: d.doc_id,
          title: d.title || d.doc_id,
          gate_pass: d.presence.gate_pass,
        }))
        .sort((a, b) => a.title.localeCompare(b.title));
    }
    return out;
  }, [artifactRung]);

  const selectedArtifact = useMemo(() => {
    if (!selectedArtifactId || !artifactRung) return undefined;
    const inUnit = selectedArtifactUnitId
      ? artifactRung.units[selectedArtifactUnitId]?.documents.find(
          (d) => d.doc_id === selectedArtifactId
        )
      : undefined;
    if (inUnit) return inUnit;
    // Opened without a unit in hand. Any review of this document beats an
    // empty panel, so take the first — but only as a fallback, because for a
    // shared document "the first" is an arbitrary one of several.
    for (const u of Object.values(artifactRung.units)) {
      const hit = u.documents.find((d) => d.doc_id === selectedArtifactId);
      if (hit) return hit;
    }
    return undefined;
  }, [selectedArtifactId, selectedArtifactUnitId, artifactRung]);

  // Per-unit artifact files, minus the thin stub "Report" when richer files
  // exist, so the detail panel links to the useful reports first.
  const selectedUnitFiles = useMemo(() => {
    if (!selectedUnitId) return [];
    const unit = outputs?.units.find((x) => x.unit_id === selectedUnitId);
    const files = unit?.files ?? [];
    const rich = files.filter((f) => f.label !== "Report");
    return rich.length > 0 ? rich : files;
  }, [outputs, selectedUnitId]);

  const quickLinks = useMemo(
    () => (outputs ? outputs.plates.slice(0, 4) : []),
    [outputs]
  );

  const showUnits = activePath === UNITS_VIEW;
  const showUnitDetail = activePath === UNIT_DETAIL && !!selectedUnitId;
  const showLessonDetail = activePath === LESSON_DETAIL && !!selectedLesson;
  const showArtifactDetail =
    activePath === ARTIFACT_DETAIL && !!selectedArtifact;
  const selectedRollup = selectedUnitId
    ? stats?.unit_rollup?.find((u) => u.unit_id === selectedUnitId)
    : undefined;
  const selectedRecord = selectedUnitId
    ? unitRung?.units?.[selectedUnitId]
    : undefined;

  const showGraph = activePath === GRAPH_VIEW;
  const hasGraph = !!graphOverview || sortedGraphRuns.length > 0;
  const showPaths = activePath === PATHS_VIEW;
  const nPathsRan =
    pathsSummary?.paths.filter((p) => p.status === "ok").length ?? 0;

  // The nav already knows a human label for every file it lists. Without this
  // lookup the panel header renders the raw relative path, so the most
  // prominent heading on the page reads "output/03-year-calendar-map.md".
  const fileLabels = useMemo(() => {
    const m = new Map<string, string>();
    if (!outputs) return m;
    for (const f of [...outputs.plates, ...outputs.layers, ...outputs.pdfs]) {
      m.set(f.path, f.label);
    }
    for (const u of outputs.units) {
      for (const f of [...u.files, ...(u.teacher_files ?? [])]) {
        m.set(f.path, f.label);
      }
    }
    return m;
  }, [outputs]);

  let panelTitle: string;
  if (showUnits) panelTitle = "Unit quality";
  else if (showGraph) panelTitle = "Curriculum graph";
  else if (showPaths) panelTitle = "What we checked for";
  else if (showUnitDetail)
    panelTitle = `Unit · ${selectedRecord?.title ?? selectedRollup?.title ?? selectedUnitId}`;
  else if (showLessonDetail) panelTitle = `Lesson · ${selectedLesson!.title}`;
  else if (showArtifactDetail)
    panelTitle = `Artifact · ${selectedArtifact!.title}`;
  else
    panelTitle =
      (activePath ? fileLabels.get(activePath) : undefined) ??
      activePath ??
      "Viewer";

  return (
    // No `.app` wrapper: AppShell provides it, along with the global nav. This
    // bar is page context only — which curriculum, which audit, which deck.
    <>
      <div className="topbar">
        <select
          value={projectId}
          onChange={(e) => {
            // Clear E2E with the curriculum change so we never request
            // projects/<new>/e2e/runs/<old-id> for one paint cycle.
            setE2eRunId("");
            setProjectId(e.target.value);
          }}
          aria-label="Curriculum"
          title="Curriculum"
        >
          <optgroup label="Curriculum">
            {curriculumProjects.map((p) => (
              <option key={p.id} value={p.id}>
                {curriculumOptionLabel(p)}
              </option>
            ))}
          </optgroup>
          {showLabForks && labProjects.length > 0 && (
            <optgroup label="Lab forks">
              {labProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {curriculumOptionLabel(p)}
                </option>
              ))}
            </optgroup>
          )}
          {/* Keep a selected lab visible if the toggle was just turned off. */}
          {!showLabForks &&
            labProjects.some((p) => p.id === projectId) && (
              <optgroup label="Lab forks">
                {labProjects
                  .filter((p) => p.id === projectId)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {curriculumOptionLabel(p)}
                    </option>
                  ))}
              </optgroup>
            )}
          {/* A deep-linked tree in neither list still needs a visible row,
              otherwise <select> falls back to showing the first option and
              the picker would disagree with what is actually loaded. */}
          {!curriculumProjects.some((p) => p.id === projectId) &&
            !labProjects.some((p) => p.id === projectId) &&
            projects.some((p) => p.id === projectId) && (
              <optgroup label="Other">
                {projects
                  .filter((p) => p.id === projectId)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {curriculumOptionLabel(p)}
                    </option>
                  ))}
              </optgroup>
            )}
        </select>
        {/* Engineering-only: experiment forks are not curricula anyone is
            reviewing, so they stay behind ?advanced=1. */}
        {deepLink.advanced && (
        <label className="topbar-lab-toggle" title="Show lab-* experiment forks">
          <input
            type="checkbox"
            checked={showLabForks}
            onChange={(e) => {
              const on = e.target.checked;
              setShowLabForks(on);
              // Leaving labs: snap back to a real curriculum so the list stays clean.
              if (!on && labProjects.some((p) => p.id === projectId)) {
                const next =
                  curriculumProjects.find((p) => p.has_review_run) ??
                  curriculumProjects[0];
                if (next) setProjectId(next.id);
              }
            }}
          />
          <span>Lab forks</span>
        </label>
        )}
        <select
          value={e2eRunId}
          onChange={(e) => setE2eRunId(e.target.value)}
          disabled={!e2eRuns.length}
          aria-label="Audit"
          title="Finished audits of this curriculum"
        >
          {!e2eRuns.length ? (
            <option value="">
              {e2eListLoaded ? "No finished audit yet" : "Loading…"}
            </option>
          ) : (
            e2eRuns.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {auditLabel(r)}
              </option>
            ))
          )}
        </select>
        {/* Model runs are an A/B research control, not a reviewer
            control, and are empty on a normal install. */}
        {deepLink.advanced && (
        <select
          value={graphRunId}
          onChange={(e) => setGraphRunId(e.target.value)}
          disabled={!sortedGraphRuns.length || !e2eRunId}
          aria-label="Model run"
          title={
            e2eRunId
              ? `Graph nested under e2e/runs/${e2eRunId}/graph/runs/`
              : "Open a finished audit first"
          }
        >
          {!sortedGraphRuns.length ? (
            <option value="">No model runs</option>
          ) : (
            sortedGraphRuns.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {graphRunLabel(r)}
                {r.active ? " · active" : ""}
                {r.n_haspart ? ` · ${r.n_haspart}u` : ""}
              </option>
            ))
          )}
        </select>
        )}
        <div className="spacer" />
        <span className="mono" style={{ color: "var(--muted)" }}>
          {e2eRunId
            ? auditLabel(e2eRuns.find((r) => r.run_id === e2eRunId))
            : "no finished audit"}
        </span>
      </div>

      {serviceError ? (
        // Checked before every data-backed view below: without this each
        // "nothing here yet" panel would be stating a comfortable lie when the
        // truth is that the local service cannot be reached at all.
        <ServiceDown
          error={serviceError}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : !e2eListLoaded ? (
        <div className="layout">
          <div className="main">
            <div className="panel">
              <div className="panel-body empty">Loading review runs…</div>
            </div>
          </div>
        </div>
      ) : !e2eRunId ? (
        <FirstRun
          projectTitle={project.title || project.id}
          reviewable={reviewableProjects}
          onPick={(id) => {
            setE2eRunId("");
            setProjectId(id);
          }}
          preflight={preflight}
          onRunAudit={startRun}
          running={running}
          runStatus={runStatus}
        />
      ) : (
      <div className="layout">
        <div className="main">
          {error && (
            <div className="panel">
              <div className="panel-body">
                <p className="err-message">{error.message}</p>
                {error.detail && (
                  <details className="err-details">
                    <summary>Technical details</summary>
                    <code>{error.detail}</code>
                  </details>
                )}
              </div>
            </div>
          )}

          {runStatus && (
            <div className="panel">
              <div className="panel-head">
                Audit progress{" "}
                <span className={`pill ${runStatus.status}`}>
                  {runStatus.status}
                </span>
              </div>
              <div className="panel-body">
                {/* Stages first, log second. The log is the diagnostic; the
                    stages are the answer to "what is it doing and is it
                    still alive", which is what someone watching wants. */}
                <RunProgress
                  progress={runStatus.progress}
                  status={runStatus.status}
                />
                <details className="err-details">
                  <summary>Run log</summary>
                  <div className="runlog">{runStatus.log || "starting…"}</div>
                </details>
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              {showUnitDetail && (
                <button
                  className="back-link"
                  onClick={() => {
                    setActivePath(UNITS_VIEW);
                    setActiveType("md");
                  }}
                >
                  ← heatmap
                </button>
              )}
              {(showLessonDetail || showArtifactDetail) && (
                <button
                  className="back-link"
                  onClick={() => {
                    setActivePath(UNIT_DETAIL);
                    setActiveType("md");
                  }}
                >
                  ← {selectedRecord?.title ?? selectedRollup?.title ?? "unit"}
                </button>
              )}
              {panelTitle}
            </div>
            <div className="panel-body">
              {showUnits ? (
                <>
                  {(stats?.unit_rollup ?? []).length === 0 ? (
                    <div className="empty">
                      This audit didn’t produce per-unit results. Choose a
                      different audit, or run this one again.
                    </div>
                  ) : (
                    <>
                      <PacketTypeBar
                        projectId={projectId}
                        packet={unitRung?.packet_type}
                        onChanged={() => loadWorkspace(projectId, e2eRunId)}
                      />
                      <div className="heat-colhead">
                        <span />
                        <span>Unit</span>
                        <span className="hc-pkt">
                          Packet &amp; completeness
                        </span>
                        <span className="hc-qual">Quality</span>
                      </div>
                      {stats!.unit_rollup!.map((u) => (
                        <UnitOutputRow
                          key={u.unit_id}
                          rollup={u}
                          band={bandFor(u)}
                          completeness={completenessFor(u)}
                          onOpen={() => openUnitDetail(u.unit_id)}
                        />
                      ))}
                    </>
                  )}
                </>
              ) : showPaths ? (
                <PathsPanel
                  summary={pathsSummary}
                  loading={pathsLoading}
                  onOpenFindings={(p) =>
                    loadDoc(projectId, p, "md", e2eRunId || undefined)
                  }
                />
              ) : showGraph ? (
                <GraphBelongingPanel
                  overview={graphOverview}
                  unitDetail={graphUnitDetail}
                  selectedUnitId={selectedUnitId}
                  loading={graphLoading}
                  onOpenUnit={(unitId) => {
                    // Stay on Curriculum graph view; empty id = back to map.
                    if (!unitId) {
                      setSelectedUnitId(null);
                      setGraphUnitDetail(null);
                      return;
                    }
                    setSelectedUnitId(unitId);
                    setSelectedLessonId(null);
                    setSelectedArtifactId(null);
                    setActivePath(GRAPH_VIEW);
                    setActiveType("md");
                  }}
                />
              ) : showUnitDetail ? (
                <>
                  <UnitDetail
                    unitId={selectedUnitId!}
                    record={selectedRecord}
                    rollup={selectedRollup}
                    files={selectedUnitFiles}
                    band={
                      selectedRecord?.band ??
                      (selectedRollup ? bandFor(selectedRollup) : "Unrated")
                    }
                    onOpenFile={(path, type) =>
                      loadDoc(projectId, path, type, e2eRunId || undefined)
                    }
                    lessons={selectedUnitLessons}
                    onSelectLesson={openLessonDetail}
                    artifacts={selectedUnitArtifacts}
                    onSelectArtifact={(docId) =>
                      openArtifactDetail(docId, selectedUnitId!)
                    }
                  />
                  <GraphBelongingPanel
                    overview={graphOverview}
                    unitDetail={graphUnitDetail}
                    selectedUnitId={selectedUnitId}
                    loading={graphLoading}
                    onOpenUnit={openUnitDetail}
                  />
                </>
              ) : showLessonDetail ? (
                <LessonDetail
                  lesson={selectedLesson!}
                  review={selectedLessonReview}
                  projectId={projectId}
                />
              ) : showArtifactDetail ? (
                <ArtifactDetail doc={selectedArtifact!} projectId={projectId} />
              ) : activeType === "pdf" && activePath ? (
                <div>
                  <p>
                    <a
                      href={api.fileUrl(
                        projectId,
                        activePath,
                        e2eRunId || undefined
                      )}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open / download PDF ↗
                    </a>
                  </p>
                  <embed
                    src={api.fileUrl(
                      projectId,
                      activePath,
                      e2eRunId || undefined
                    )}
                    type="application/pdf"
                    width="100%"
                    height="720px"
                    style={{ border: "2px solid var(--line)" }}
                  />
                </div>
              ) : activeType === "html" && activePath ? (
                <div>
                  <p>
                    <a
                      href={api.fileUrl(
                        projectId,
                        activePath,
                        e2eRunId || undefined
                      )}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open HTML in new tab ↗
                    </a>
                  </p>
                  <iframe
                    title={activePath}
                    src={api.fileUrl(
                      projectId,
                      activePath,
                      e2eRunId || undefined
                    )}
                    width="100%"
                    height="860px"
                    style={{
                      border: "2px solid var(--line)",
                      background: "#f3efe6",
                    }}
                  />
                </div>
              ) : viewerText ? (
                <MarkdownViewer
                  text={viewerText}
                  onNavigate={(rel) => {
                    const type = /\.pdf$/i.test(rel) ? "pdf" : "md";
                    loadDoc(projectId, rel, type, e2eRunId || undefined);
                  }}
                />
              ) : (
                <div className="empty">Select an output to review.</div>
              )}
            </div>
          </div>
        </div>

        <div>
          {outputs && (
            <OutputNav
              outputs={outputs}
              activePath={activePath}
              hasGraph={hasGraph}
              graphLabel={
                graphRunId
                  ? `Curriculum graph · ${graphRunLabel(
                      sortedGraphRuns.find((r) => r.run_id === graphRunId) ?? {
                        run_id: graphRunId,
                        model: graphRunId,
                        n_units: 0,
                        n_haspart: 0,
                      }
                    )}`
                  : "Curriculum graph"
              }
              nPathsRan={nPathsRan}
              advanced={deepLink.advanced}
              docsByUnit={docsByUnit}
              onSelectDoc={openArtifactDetail}
              activeDoc={
                showArtifactDetail
                  ? { docId: selectedArtifactId!, unitId: selectedArtifactUnitId }
                  : null
              }
              onSelect={(path, type) => {
                if (
                  path === UNITS_VIEW ||
                  path === GRAPH_VIEW ||
                  path === PATHS_VIEW
                ) {
                  setSelectedUnitId(null);
                  setSelectedLessonId(null);
                  setSelectedArtifactId(null);
                  setActivePath(path);
                  setActiveType("md");
                  setViewerText("");
                } else {
                  loadDoc(projectId, path, type, e2eRunId || undefined);
                }
              }}
            />
          )}
          <ReviewSlip
            project={project}
            stats={stats}
            quickLinks={quickLinks}
            running={running}
            runStatus={runStatus}
            onRun={startRun}
            onRefresh={() => loadWorkspace(projectId, e2eRunId)}
            onQuickLink={(path) =>
              loadDoc(projectId, path, "md", e2eRunId || undefined)
            }
          />
        </div>
      </div>
      )}
    </>
  );
}
