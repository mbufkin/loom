import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, describeError } from "../lib/api";
import type { Project } from "../types";

/**
 * School calendars: which curricula have one, and what difference it makes.
 *
 * The important thing this screen exists to communicate is that a calendar is
 * *optional*. Verified against the pipeline: with a calendar, rollup runs in
 * "dated" mode and places units on real dates; without one it runs in
 * "sequential" mode and places them in order. Everything else about the audit
 * — which documents exist, what is missing, whether materials match their unit
 * — is byte-identical either way, and adding a calendar later upgrades the
 * pacing plan on the next run.
 *
 * That used to be invisible. Worse, the blank-curriculum template shipped one
 * specific district's calendar, so every new curriculum silently inherited
 * another district's school year until somebody noticed.
 */
export function Calendars() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<{ message: string; detail: string } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      setProjects(await api.projects());
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const curricula = projects.filter((p) => p.kind !== "lab");
  const dated = curricula.filter((p) => p.has_calendar);
  const sequential = curricula.filter((p) => !p.has_calendar);

  return (
    <div className="home">
      <div className="home-head">
        <h2>School calendars</h2>
      </div>

      <div className="panel">
        <div className="panel-head">What a calendar changes</div>
        <div className="panel-body">
          <p>
            A school calendar tells Loom your first and last day of class, your
            grading periods, and the days students are not in school. With one,
            your pacing plan is <strong>dated</strong> — every unit lands on
            real dates and holidays are skipped. Without one, pacing is{" "}
            <strong>sequential</strong>: Unit 1, Unit 2, and so on, in order.
          </p>
          <p>
            Nothing else changes. What documents exist, what is missing, and
            whether materials belong to the unit they are filed under are
            reported exactly the same either way. You can audit a curriculum
            now and add the calendar whenever you have it.
          </p>
        </div>
      </div>

      {error ? (
        <div className="panel">
          <div className="panel-head">Can’t reach Loom</div>
          <div className="panel-body">
            <p className="err-message">{error.message}</p>
            <button type="button" onClick={() => void load()}>
              Try again
            </button>
            <details className="err-details">
              <summary>Technical details</summary>
              <pre>{error.detail}</pre>
            </details>
          </div>
        </div>
      ) : !loaded ? (
        <div className="panel">
          <div className="panel-body empty">Loading…</div>
        </div>
      ) : curricula.length === 0 ? (
        <div className="panel">
          <div className="panel-head">No curricula yet</div>
          <div className="panel-body">
            <p>
              Once you add a curriculum it will appear here, with or without a
              calendar.
            </p>
            <Link className="btn-primary" to="/curricula/new">
              Add a curriculum
            </Link>
          </div>
        </div>
      ) : (
        <>
          <div className="panel">
            <div className="panel-head">
              Dated pacing · {dated.length} of {curricula.length}
            </div>
            <div className="panel-body">
              {dated.length === 0 ? (
                <p className="cal-none">
                  None of your curricula have a calendar yet, so all pacing is
                  sequential.
                </p>
              ) : (
                <ul className="cal-list">
                  {dated.map((p) => (
                    <li key={p.id} className="cal-row">
                      <span className="cal-name">{p.title || p.id}</span>
                      <span className="cal-badge cal-dated">dated</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {sequential.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                Sequential pacing · no calendar supplied
              </div>
              <div className="panel-body">
                <ul className="cal-list">
                  {sequential.map((p) => (
                    <li key={p.id} className="cal-row">
                      <span className="cal-name">{p.title || p.id}</span>
                      <span className="cal-badge cal-seq">sequential</span>
                      <Link className="btn" to={`/curricula/${p.id}`}>
                        Details
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </>
      )}

      {/* Stated plainly rather than implied by a disabled button, so nobody
          hunts for an editor that is not there yet. */}
      <p className="home-note">
        Editing calendars in the app is not built yet. For now a calendar is a{" "}
        <code>school-calendar.yaml</code> file in the curriculum’s folder, and
        each curriculum can have its own. A shared district calendar you can
        set once and reuse everywhere is the next piece of this screen.
      </p>
    </div>
  );
}
