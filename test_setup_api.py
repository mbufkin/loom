#!/usr/bin/env python3
"""
test_setup_api.py — The in-app curriculum setup endpoints: create a curriculum,
put documents in it, review what organise proposed.

These run a real ThreadingHTTPServer on an OS-assigned port and speak real HTTP
to it. Calling the helper functions directly would be less code, but the thing
most likely to break here is the wiring rather than the logic: a route tuple
with the wrong arity, a filename that never leaves the query string, an
exception mapped to 403 with a "forbidden:" prefix in front of a message about
a typo. None of that is visible to a test that skips the handler.

No models, no network beyond loopback, no real corpus — PROJECTS and RUNS_DIR
are redirected into a temp directory, so a bug here cannot touch a real
curriculum.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "ui"))

import server  # noqa: E402


class _Fixture:
    """A live server with its data roots pointed at a temp directory."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="loom-setup-api-"))
        self.projects = self.tmp / "projects"
        self.projects.mkdir(parents=True)
        self._saved = (server.PROJECTS, server.RUNS_DIR)
        server.PROJECTS = self.projects
        server.RUNS_DIR = self.tmp / "logs" / "runs"
        # Port 0: let the OS pick, so a developer already running the real UI on
        # 8770 does not get a confusing bind error from the test suite.
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        server.PROJECTS, server.RUNS_DIR = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def request(
        self, method: str, path: str, body: bytes | dict | None = None
    ) -> tuple[int, dict]:
        """One HTTP call, returning (status, parsed JSON).

        An error response is a result here, not an exception: the status code
        and the message in it are exactly what these tests are checking.
        """
        url = f"http://127.0.0.1:{self.port}{path}"
        data = body
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/octet-stream")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))


def _upload(fx: _Fixture, pid: str, name: str, payload: bytes) -> tuple[int, dict]:
    q = urllib.parse.urlencode({"name": name})
    return fx.request("POST", f"/api/projects/{pid}/documents?{q}", payload)


def test_create_curriculum_makes_the_folders_a_curriculum_starts_with():
    fx = _Fixture()
    try:
        code, body = fx.request(
            "POST", "/api/projects", {"id": "my-district-2026", "title": "My District"}
        )
        assert code == 201, body
        root = fx.projects / "my-district-2026"
        assert (root / "sources").is_dir(), "sources/ is where documents go"
        assert (root / "reference").is_dir()
        assert "My District" in (root / "README.md").read_text(encoding="utf-8")

        # Creating it twice is a conflict, not a 500 and not a silent merge that
        # would quietly adopt an unrelated curriculum's documents.
        code, body = fx.request("POST", "/api/projects", {"id": "my-district-2026"})
        assert code == 409, (code, body)
    finally:
        fx.close()


def test_curriculum_names_that_are_not_safe_are_refused_as_bad_requests():
    """The name becomes a directory, a subprocess argument and a URL segment.

    Each rejection is also checked for its status code: these are mistakes a
    user makes while typing, so they must read as "fix the name" (400) rather
    than "you are not allowed" (403), which is what a bare ValueError produced
    before _BadRequest existed.
    """
    fx = _Fixture()
    try:
        for bad in (
            "../escape",
            "..",
            "Has Capitals",
            "under_scores",
            "trailing-",
            "",
            "a/b",
            "semi;colon",
        ):
            code, body = fx.request("POST", "/api/projects", {"id": bad})
            assert code == 400, f"{bad!r} returned {code}: {body}"
            assert "lowercase" in body["error"] or "invalid" in body["error"]
        # Nothing was created on the way to those refusals.
        assert list(fx.projects.iterdir()) == []
    finally:
        fx.close()


def test_documents_upload_list_and_remove():
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "upload-demo"})
        code, body = _upload(fx, "upload-demo", "pacing-guide.md", b"# Unit 1\n")
        assert code == 201, body
        assert body["name"] == "pacing-guide.md"
        assert body["bytes"] == len(b"# Unit 1\n")
        assert (fx.projects / "upload-demo" / "sources" / "pacing-guide.md").is_file()

        code, listing = fx.request("GET", "/api/projects/upload-demo/documents")
        assert code == 200
        assert listing["count"] == 1
        assert listing["readable_count"] == 1, "the extractor reads .md"
        assert listing["has_manifest"] is False, "organise has not run yet"

        code, body = fx.request(
            "POST",
            "/api/projects/upload-demo/documents/delete",
            {"name": "pacing-guide.md"},
        )
        assert code == 200, body
        _, listing = fx.request("GET", "/api/projects/upload-demo/documents")
        assert listing["count"] == 0
    finally:
        fx.close()


def test_a_second_file_with_the_same_name_is_kept_not_overwritten():
    """Two units can legitimately both ship "quiz.docx".

    Overwriting would be data loss the user cannot see: the upload reports
    success, the file count does not go up, and the audit silently covers one
    fewer document.
    """
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "dupes"})
        _upload(fx, "dupes", "quiz.md", b"first")
        code, body = _upload(fx, "dupes", "quiz.md", b"second")
        assert code == 201, body
        assert body["renamed"] is True
        assert body["name"] == "quiz (2).md"
        sources = fx.projects / "dupes" / "sources"
        assert (sources / "quiz.md").read_text(encoding="utf-8") == "first"
        assert (sources / "quiz (2).md").read_text(encoding="utf-8") == "second"
    finally:
        fx.close()


def test_uploads_cannot_escape_the_sources_folder():
    """The filename arrives from the client, so it is untrusted input.

    A browser sends a bare basename, but this endpoint must not rely on that.
    """
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "traversal"})
        outside = fx.tmp / "config.yaml"
        for attack in (
            "../../config.yaml",
            "..\\..\\config.yaml",
            "/etc/passwd.md",
            "..",
        ):
            code, body = _upload(fx, "traversal", attack, b"owned")
            # Either refused outright, or reduced to a basename inside sources/.
            if code == 201:
                written = fx.projects / "traversal" / "sources" / body["name"]
                assert written.is_file()
                assert written.parent == fx.projects / "traversal" / "sources"
            else:
                assert code in (400, 403), (attack, code, body)
            assert not outside.exists(), f"{attack!r} wrote outside the curriculum"

        # Deletion takes a path too, and has the same boundary.
        code, body = fx.request(
            "POST",
            "/api/projects/traversal/documents/delete",
            {"name": "../../config.yaml"},
        )
        assert code == 403, (code, body)
    finally:
        fx.close()


def test_a_file_type_loom_cannot_read_is_refused_with_the_list_of_ones_it_can():
    """Better to refuse than to accept a file the pipeline will ignore.

    Accepting silently is the worse failure: the document appears in the folder,
    the user believes it was audited, and nothing ever says otherwise.
    """
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "wrong-type"})
        code, body = _upload(fx, "wrong-type", "scan.tiff", b"\x00\x01")
        assert code == 400, (code, body)
        assert "cannot read" in body["error"]
        assert "pdf" in body["error"], "say which types do work"
        assert not (fx.projects / "wrong-type" / "sources" / "scan.tiff").exists()
    finally:
        fx.close()


def test_organise_refuses_when_there_are_no_documents_yet():
    """The button exists before the folder has anything in it.

    Spawning ingest on an empty folder burns a model round-trip to produce a
    manifest with no units, which then fails validation further down.
    """
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "empty-one"})
        code, body = fx.request("POST", "/api/projects/empty-one/organise", {})
        assert code == 404, (code, body)
        assert "Add some documents first" in body["error"]
    finally:
        fx.close()


def test_units_endpoint_reports_what_organise_proposed():
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "organised"})
        root = fx.projects / "organised"

        # Before organise: an honest "not yet", not an error.
        code, body = fx.request("GET", "/api/projects/organised/units")
        assert code == 200
        assert body["has_manifest"] is False
        assert body["units"] == []

        (root / "units" / "immune").mkdir(parents=True)
        (root / "units" / "immune" / "calendar.yaml").write_text(
            "days:\n  - id: d1\n    label: Day 1\n  - id: d2\n    label: Day 2\n",
            encoding="utf-8",
        )
        (root / "manifest.yaml").write_text(
            "project:\n"
            "  id: organised\n"
            "  name: Organised Curriculum\n"
            "units:\n"
            "  immune:\n"
            "    title: Immune System\n"
            "    calendar: units/immune/calendar.yaml\n"
            "    documents:\n"
            "      - immune-lesson.md\n"
            "generated_by: ingest.py\n",
            encoding="utf-8",
        )
        code, body = fx.request("GET", "/api/projects/organised/units")
        assert code == 200, body
        assert body["valid"] is True
        assert body["unit_count"] == 1
        unit = body["units"][0]
        assert unit["unit_id"] == "immune"
        assert unit["title"] == "Immune System"
        assert unit["document_count"] == 1
        assert unit["days"] == 2, "day count comes from the unit calendar"
    finally:
        fx.close()


def test_a_malformed_manifest_is_reported_as_invalid_rather_than_crashing():
    """Organise is model-driven, so a manifest that fails validation is a real
    outcome. The setup screen has to be able to say so and offer a re-organise;
    a 500 here would leave the user with no way forward."""
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "broken"})
        (fx.projects / "broken" / "manifest.yaml").write_text(
            "project:\n  id: broken\nunits: []\n", encoding="utf-8"
        )
        code, body = fx.request("GET", "/api/projects/broken/units")
        assert code == 200, body
        assert body["has_manifest"] is True
        assert body["valid"] is False
        assert body["error"], "say what is wrong with it"
    finally:
        fx.close()


def test_a_calendar_stub_with_no_dates_does_not_count_as_dated():
    """organise writes a school-calendar.yaml every time, dates or not.

    When the documents carry no district dates that file is a placeholder, and
    rollup places the units sequentially regardless. Reporting it as a calendar
    made the UI promise dated pacing for a file with no dates in it — on every
    curriculum set up through the app, since the stub is always left behind.
    """
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "cal-modes"})
        root = fx.projects / "cal-modes"
        cal = root / "school-calendar.yaml"

        assert server._has_dated_calendar(cal) is False, "no file at all"

        # Exactly what ingest.py writes for a corpus with no dates in it.
        cal.write_text(
            "school_year: null\nnotes: null\ngrading_periods: []\n", encoding="utf-8"
        )
        assert server._has_dated_calendar(cal) is False, "a stub is not a calendar"

        # A real district spine: first/last day is what rollup walks to build
        # instructional days, and what flips it into dated mode.
        cal.write_text(
            'school_year: "2026-2027"\n'
            'first_day_of_class: "2026-08-11"\n'
            'last_day_of_class: "2027-05-27"\n',
            encoding="utf-8",
        )
        assert server._has_dated_calendar(cal) is True

        # Unparseable YAML would not date anything either, and must not raise
        # from inside the project listing.
        cal.write_text("this: [is: not: valid", encoding="utf-8")
        assert server._has_dated_calendar(cal) is False
    finally:
        fx.close()


def test_bundle_version_changes_only_when_the_built_app_changes():
    """The signal behind the "Loom has been updated" notice.

    The value has to be stable under everything that is not an upgrade,
    otherwise the notice becomes noise someone learns to dismiss: rebuilding
    without editing, and restarting this server, must both leave it alone.
    """
    fx = _Fixture()
    try:
        saved_dist = server.DIST
        dist = fx.tmp / "dist"
        dist.mkdir()
        server.DIST = dist

        # No dist at all is the development case: Vite serves the app on 5173
        # with hot reload, so there is nothing to compare and nothing to say.
        server.DIST = fx.tmp / "no-dist-here"
        code, body = fx.request("GET", "/api/version")
        assert code == 200
        assert body["bundle"] is None

        server.DIST = dist
        index = dist / "index.html"
        index.write_text('<script src="/assets/index-AAA111.js">', encoding="utf-8")
        _, first = fx.request("GET", "/api/version")
        assert first["bundle"], "a built app must have an identity"

        # Asked again with nothing touched: same answer. This is what stops a
        # window being nagged to reload the app it is already running.
        _, again = fx.request("GET", "/api/version")
        assert again["bundle"] == first["bundle"]

        # Rewriting the same content -- `npm run build` with no source changes
        # -- must not read as an upgrade either. This is why the id is a hash
        # of the file and not its mtime.
        index.write_text('<script src="/assets/index-AAA111.js">', encoding="utf-8")
        _, rebuilt = fx.request("GET", "/api/version")
        assert rebuilt["bundle"] == first["bundle"], "mtime must not be the id"

        # A real rebuild: Vite content-hashes the bundle name, so index.html
        # changes and the window should be told.
        index.write_text('<script src="/assets/index-BBB222.js">', encoding="utf-8")
        _, upgraded = fx.request("GET", "/api/version")
        assert upgraded["bundle"] != first["bundle"]
    finally:
        server.DIST = saved_dist
        fx.close()


def test_every_listed_output_says_which_viewer_opens_it():
    """A PDF must arrive tagged as one, or the reviewer reads its bytes.

    The review screen picks its viewer from this `type` and treats a missing one
    as Markdown. The global audit PDF was listed with only a label and a path,
    so clicking it rendered "%PDF-1.4 ... /BaseFont /Helvetica" as prose -- the
    one report a principal is most likely to open, and the failure looked like a
    corrupt file rather than a missing field.
    """
    fx = _Fixture()
    try:
        out = fx.projects / "typed" / "output"
        out.mkdir(parents=True)
        (out / "DASHBOARD.md").write_text("# Dashboard\n", encoding="utf-8")
        (out / "GLOBAL-AUDIT-REPORT.pdf").write_bytes(b"%PDF-1.4\n")

        code, body = fx.request("GET", "/api/projects/typed/outputs")
        assert code == 200, body

        # Checked across every group rather than on the PDF alone: the point is
        # that nothing is listed untyped, whichever list it came from.
        listed = [*body["plates"], *body["layers"], *body["pdfs"]]
        assert listed, "fixture should produce something to open"
        untyped = [f["path"] for f in listed if not f.get("type")]
        assert not untyped, f"no viewer chosen for {untyped}"

        by_path = {f["path"]: f["type"] for f in listed}
        assert by_path["output/GLOBAL-AUDIT-REPORT.pdf"] == "pdf"
        assert by_path["output/DASHBOARD.md"] == "md"
    finally:
        fx.close()


def test_the_first_pass_packet_is_listed_once_not_under_both_its_names():
    """reports.py writes one packet and copies it to a second name.

    write_first_pass emits FIRST-PASS.md and then GLOBAL-AUDIT.md as an alias of
    it, so the two files are byte-identical after every run. The rail listed
    both, which put the same 79-line document in front of the reviewer twice
    with nothing to distinguish them -- reading one and then the other is pure
    waste, and the second read looks like a report that failed to update.

    Asserting on content rather than on the literal label keeps this honest if
    the entries are ever renamed.
    """
    fx = _Fixture()
    try:
        out = fx.projects / "aliased" / "output"
        out.mkdir(parents=True)
        packet = "# Curriculum Review Work Packet (first-pass)\n"
        (out / "FIRST-PASS.md").write_text(packet, encoding="utf-8")
        (out / "GLOBAL-AUDIT.md").write_text(packet, encoding="utf-8")
        (out / "DASHBOARD.md").write_text("# Dashboard\n", encoding="utf-8")

        code, body = fx.request("GET", "/api/projects/aliased/outputs")
        assert code == 200, body

        paths = [f["path"] for f in body["plates"]]
        aliases = [p for p in paths if p.endswith(("FIRST-PASS.md", "GLOBAL-AUDIT.md"))]
        assert len(aliases) == 1, f"packet listed under both names: {aliases}"

        # The dashboard is untouched by this: it is a different document and
        # must still be there, first.
        assert paths[0] == "output/DASHBOARD.md"
    finally:
        fx.close()


# --- organise-and-run: one run, organise then audit ---------------------------
#
# ingest and the audit are swapped for a small fake script through the
# _organise_argv / _audit_argv seams, so these tests exercise the real
# subprocess, thread and log handling with no model calls at all.

_FAKE_STEP = r'''
import pathlib, sys, time
root, mode = pathlib.Path(sys.argv[1]), sys.argv[2]
if mode == "audit":
    print("fake audit ran", flush=True)
    (root / "audit-ran.txt").write_text("yes", encoding="utf-8")
    sys.exit(0)
print("fake ingest reading documents", flush=True)
if mode == "ingest-fail":
    sys.exit(3)
if mode == "ingest-wait":
    for _ in range(200):
        if (root / "release").exists():
            break
        time.sleep(0.05)
if mode != "ingest-no-manifest":
    (root / "units" / "u1").mkdir(parents=True, exist_ok=True)
    (root / "units" / "u1" / "calendar.yaml").write_text(
        "days:\n  - id: d1\n    label: Day 1\n", encoding="utf-8")
    (root / "manifest.yaml").write_text(
        "project:\n  id: p\n  name: P\nunits:\n  u1:\n    title: Unit One\n"
        "    calendar: units/u1/calendar.yaml\n    documents:\n      - a.md\n"
        "generated_by: ingest.py\n", encoding="utf-8")
'''


def _use_fake_steps(fx: _Fixture, ingest_mode: str):
    """Point both phases at the fake; returns a function that undoes it."""
    script = fx.tmp / "fake_step.py"
    script.write_text(_FAKE_STEP, encoding="utf-8")
    saved = (server._organise_argv, server._audit_argv)
    server._organise_argv = lambda pid: [
        sys.executable, str(script), str(fx.projects / pid), ingest_mode
    ]
    server._audit_argv = lambda pid, flags: [
        sys.executable, str(script), str(fx.projects / pid), "audit"
    ]

    def restore() -> None:
        server._organise_argv, server._audit_argv = saved

    return restore


def _project_with_a_document(fx: _Fixture, pid: str) -> Path:
    fx.request("POST", "/api/projects", {"id": pid})
    _upload(fx, pid, "a.md", b"# Unit 1\n")
    return fx.projects / pid


def _wait_for_run(fx: _Fixture, run_id: str, timeout: float = 20.0) -> dict:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        code, status = fx.request("GET", f"/api/runs/{run_id}")
        assert code == 200, status
        if status["status"] != "running":
            return status
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} still running after {timeout}s")


def test_organise_and_run_audits_after_a_successful_organise():
    fx = _Fixture()
    restore = _use_fake_steps(fx, "ingest-ok")
    try:
        root = _project_with_a_document(fx, "chain-ok")
        code, body = fx.request("POST", "/api/projects/chain-ok/organise-and-run", {})
        assert code == 200, body
        status = _wait_for_run(fx, body["runId"])

        assert status["status"] == "done", status
        assert status["kind"] == "organise-and-run"
        assert status["phase"] == "auditing", "it got as far as the audit"
        assert status["error"] is None
        assert (root / "manifest.yaml").is_file()
        assert (root / "audit-ran.txt").is_file(), "the audit was started"
        # One run, one log, both phases in order.
        log = status["log"]
        assert log.index("fake ingest") < log.index(server.AUDIT_PHASE_MARKER)
        assert log.index(server.AUDIT_PHASE_MARKER) < log.index("fake audit ran")
    finally:
        restore()
        fx.close()


def test_organise_and_run_does_not_audit_when_organise_fails():
    fx = _Fixture()
    restore = _use_fake_steps(fx, "ingest-fail")
    try:
        root = _project_with_a_document(fx, "chain-fail")
        code, body = fx.request("POST", "/api/projects/chain-fail/organise-and-run", {})
        assert code == 200, body
        status = _wait_for_run(fx, body["runId"])

        assert status["status"] == "error", status
        assert status["exitCode"] == 3
        assert status["phase"] == "organising", "it never reached the audit"
        assert "audit was not started" in status["error"]
        assert "audit was not started" in status["log"], "the log says so too"
        assert server.AUDIT_PHASE_MARKER not in status["log"]
        assert not (root / "audit-ran.txt").exists()
    finally:
        restore()
        fx.close()


def test_organise_and_run_does_not_audit_without_usable_units():
    """ingest exiting 0 is not enough: no manifest means nothing to audit."""
    fx = _Fixture()
    restore = _use_fake_steps(fx, "ingest-no-manifest")
    try:
        root = _project_with_a_document(fx, "chain-empty")
        _, body = fx.request("POST", "/api/projects/chain-empty/organise-and-run", {})
        status = _wait_for_run(fx, body["runId"])
        assert status["status"] == "error", status
        assert status["phase"] == "organising"
        assert "can't be used" in status["error"]
        assert not (root / "audit-ran.txt").exists()
    finally:
        restore()
        fx.close()


def test_organise_and_run_refuses_a_second_run_on_the_same_curriculum():
    """A double click must not start two runs writing the same manifest."""
    fx = _Fixture()
    restore = _use_fake_steps(fx, "ingest-wait")
    try:
        root = _project_with_a_document(fx, "chain-busy")
        _project_with_a_document(fx, "chain-other")
        code, first = fx.request("POST", "/api/projects/chain-busy/organise-and-run", {})
        assert code == 200, first

        code, second = fx.request("POST", "/api/projects/chain-busy/organise-and-run", {})
        assert code == 409, (code, second)
        assert "already being organised or audited" in second["error"]

        # Only that curriculum is locked; another one starts normally.
        code, other = fx.request("POST", "/api/projects/chain-other/organise-and-run", {})
        assert code == 200, other

        (root / "release").write_text("", encoding="utf-8")
        (fx.projects / "chain-other" / "release").write_text("", encoding="utf-8")
        assert _wait_for_run(fx, first["runId"])["status"] == "done"
        assert _wait_for_run(fx, other["runId"])["status"] == "done"

        # Once it has finished, the curriculum can be run again.
        code, again = fx.request("POST", "/api/projects/chain-busy/organise-and-run", {})
        assert code == 200, again
        _wait_for_run(fx, again["runId"])
    finally:
        restore()
        fx.close()


def test_organise_and_run_refuses_when_there_are_no_documents_yet():
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "chain-nodocs"})
        code, body = fx.request("POST", "/api/projects/chain-nodocs/organise-and-run", {})
        assert code == 404, (code, body)
        assert "Add some documents first" in body["error"]
    finally:
        fx.close()


# --- deleting a curriculum: soft, into <data root>/.trash -------------------


def _raw_post(fx: _Fixture, path: str) -> int:
    """POST a path exactly as written. urllib would normalise "/../" away
    before it left the client, which is not what an attacker's client does."""
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", fx.port, timeout=10)
    try:
        conn.request("POST", path, body=b"{}", headers={"Content-Type": "application/json"})
        return conn.getresponse().status
    finally:
        conn.close()


def test_delete_moves_the_curriculum_to_trash_and_off_the_list():
    fx = _Fixture()
    try:
        _project_with_a_document(fx, "to-delete")
        _project_with_a_document(fx, "keep-me")

        code, body = fx.request("POST", "/api/projects/to-delete/delete", {})
        assert code == 200, body
        assert body["ok"] is True and body["keep_days"] == 7
        assert body["trashed_as"].startswith(".trash/to-delete-")

        assert not (fx.projects / "to-delete").exists()
        trashed = fx.tmp / body["trashed_as"]
        assert (trashed / "sources" / "a.md").is_file(), "documents kept, recoverable"

        _, listing = fx.request("GET", "/api/projects")
        ids = [p["id"] for p in listing]
        assert "to-delete" not in ids and "keep-me" in ids

        # The id is free again, and a second delete of the new folder does not
        # collide with the first one's trash entry.
        fx.request("POST", "/api/projects", {"id": "to-delete"})
        code, again = fx.request("POST", "/api/projects/to-delete/delete", {})
        assert code == 200, again
        assert again["trashed_as"] != body["trashed_as"]
    finally:
        fx.close()


def test_delete_of_an_unknown_curriculum_is_404():
    fx = _Fixture()
    try:
        code, body = fx.request("POST", "/api/projects/never-existed/delete", {})
        assert code == 404, (code, body)
        assert "no curriculum called never-existed" in body["error"]
    finally:
        fx.close()


def test_delete_refuses_traversal_and_invalid_ids():
    fx = _Fixture()
    try:
        _project_with_a_document(fx, "victim")
        (fx.tmp / "outside").mkdir()
        for path in (
            "/api/projects/../delete",
            "/api/projects/%2e%2e/delete",
            "/api/projects/..%2Fvictim/delete",
            "/api/projects/semi;colon/delete",
            "/api/projects/.hidden/delete",
        ):
            status = _raw_post(fx, path)
            assert status in (400, 403, 404), (path, status)
        assert (fx.projects / "victim" / "sources" / "a.md").is_file()
        assert (fx.tmp / "outside").is_dir()
        assert not (fx.tmp / ".trash").exists() or not any((fx.tmp / ".trash").iterdir())

        # A symlink in projects/ is not a curriculum folder; neither the link
        # nor what it points at may be moved.
        (fx.projects / "linky").symlink_to(fx.tmp / "outside", target_is_directory=True)
        code, body = fx.request("POST", "/api/projects/linky/delete", {})
        assert code == 403, (code, body)
        assert (fx.projects / "linky").is_symlink() and (fx.tmp / "outside").is_dir()
    finally:
        fx.close()


def test_delete_refuses_the_template():
    fx = _Fixture()
    try:
        (fx.projects / "_template").mkdir()
        code, body = fx.request("POST", "/api/projects/_template/delete", {})
        assert code == 403, (code, body)
        assert "can't be deleted" in body["error"]
        assert (fx.projects / "_template").is_dir()
    finally:
        fx.close()


def test_delete_refuses_a_curriculum_with_a_run_in_progress():
    fx = _Fixture()
    try:
        _project_with_a_document(fx, "busy-one")
        with server._RUNS_LOCK:
            server._RUNS["fake-running"] = {
                "pid": "busy-one", "status": "running", "kind": "audit",
                "log_path": str(fx.tmp / "none.log"), "exit_code": None,
            }
        try:
            _, listing = fx.request("GET", "/api/projects")
            assert {p["id"]: p for p in listing}["busy-one"]["run_in_progress"] is True

            code, body = fx.request("POST", "/api/projects/busy-one/delete", {})
            assert code == 409, (code, body)
            assert "once that run finishes" in body["error"]
            assert (fx.projects / "busy-one").is_dir()
        finally:
            with server._RUNS_LOCK:
                server._RUNS.pop("fake-running", None)

        code, body = fx.request("POST", "/api/projects/busy-one/delete", {})
        assert code == 200, body
    finally:
        fx.close()


def test_purge_removes_only_trash_older_than_seven_days():
    import os
    import time

    fx = _Fixture()
    try:
        trash = fx.tmp / ".trash"
        trash.mkdir()
        now = time.time()

        def stamp(days_ago: float) -> str:
            return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - days_ago * 86400))

        old = trash / f"old-one-{stamp(8)}"
        fresh = trash / f"fresh-one-{stamp(1)}"
        edge = trash / f"edge-one-{stamp(6.9)}-2"
        unrelated = trash / "notes-by-hand"
        for d in (old, fresh, edge, unrelated):
            (d / "sources").mkdir(parents=True)
        # Age is read from the name, not mtime: a renamed folder keeps the
        # mtime of its last edit, which can be months old.
        month_ago = now - 30 * 86400
        os.utime(fresh, (month_ago, month_ago))

        purged = server._purge_trash(now=now)

        assert purged == [old.name]
        assert not old.exists()
        assert fresh.is_dir() and edge.is_dir() and unrelated.is_dir()
    finally:
        fx.close()


def test_every_site_audit_runs_the_graph_phase():
    # Both ways the site starts an audit must sort documents by content first.
    # The flag is forced, not offered, so whatever the caller sends it is there
    # exactly once, and a stray graph option from the caller is not.
    fx = _Fixture()
    restore = _use_fake_steps(fx, "ingest-ok")
    fake_argv = server._audit_argv
    seen: list[list[str]] = []

    def recording(pid, flags):
        seen.append(list(flags))
        return fake_argv(pid, flags)

    server._audit_argv = recording
    try:
        _project_with_a_document(fx, "graph-on")
        code, body = fx.request("POST", "/api/projects/graph-on/organise-and-run", {})
        assert code == 200, body
        assert _wait_for_run(fx, body["runId"])["status"] == "done"
        assert seen[-1] == ["--with-graph"], seen

        for sent, expected in [
            ([], ["--with-graph"]),
            (["--force", "--only"], ["--force", "--with-graph"]),
            (
                ["--only", "u1", "--with-graph", "--graph-backend", "cursor"],
                ["--only", "u1", "--with-graph"],
            ),
        ]:
            code, body = fx.request("POST", "/api/projects/graph-on/run", {"flags": sent})
            assert code == 200, body
            _wait_for_run(fx, body["runId"])
            assert seen[-1] == expected, (sent, seen[-1])
    finally:
        restore()
        fx.close()


def _progress_log(*lines: str) -> str:
    return "\n".join(["[audit] e2e: LOOM_E2E_RUN=r1", "[audit] models: ok", *lines])


def test_progress_shows_the_sorting_stage_with_per_document_counts():
    fx = _Fixture()
    try:
        fx.request("POST", "/api/projects", {"id": "prog"})
        (fx.projects / "prog" / "manifest.yaml").write_text(
            "units:\n  u1:\n    documents: [a.md, b.md]\n  u2:\n    documents: [c.md]\n",
            encoding="utf-8",
        )
        read = [f"[audit] Layer 0: decomposing {n} (10 chars)" for n in ("a.md", "b.md", "c.md")]
        sorting = [
            "[audit] graph: run_id=r1 backend=local model=m",
            "[audit] graph STEP role ← a.md",
            "[audit] graph STEP lessons ← a.md",
            "[audit] graph STEP assessment ← a.md",
            "[audit] graph STEP stub (no evidence) ← b.md",
        ]
        p = server._run_progress("prog", _progress_log(*read, *sorting), 0.0, "running", [])
        by_id = {s["id"]: s for s in p["stages"]}
        assert p["current"] == "graph", p
        assert by_id["graph"]["label"] == "Sorting documents by content"
        assert by_id["graph"]["state"] == "running" and by_id["layer0"]["state"] == "done"
        # One line per document, not per step: b.md is in hand, a.md is done.
        assert (p["detail"], p["docsDone"], p["docsTotal"]) == ("b.md", 1, 3), p

        # The pipeline order: read, sort, review paths, then Layers 1 and 2.
        ids = [s["id"] for s in p["stages"]]
        for earlier, later in [("layer0", "graph"), ("graph", "paths"),
                               ("paths", "layer1"), ("layer1", "layer2")]:
            assert ids.index(earlier) < ids.index(later), ids
        assert by_id["paths"]["label"] == "Running each document's review path"

        after = [
            "[audit] Sorted 3 documents: 2 by content, 1 by filename; paths A×1 D×2",
            "[audit] path A → 1 lesson_plan doc(s); A1–A6",
            "[audit] Layer 1: 40 elements in scope",
        ]
        p = server._run_progress(
            "prog", _progress_log(*read, *sorting, *after), 0.0, "running", []
        )
        by_id = {s["id"]: s for s in p["stages"]}
        assert p["current"] == "layer1", p
        assert by_id["graph"]["state"] == by_id["paths"]["state"] == "done"
        assert by_id["layer2"]["state"] == "pending", "Layer 2 has not started"
    finally:
        fx.close()


def test_the_readiness_check_answers_instead_of_crashing():
    # The setup screen only shows "Organise and run the audit" once this says
    # can_run. If the check raises, the page gets a 500 and the button is
    # silently missing, so a crash here must fail the suite, not the user.
    fx = _Fixture()
    try:
        code, body = fx.request("GET", "/api/can-run")
        assert code == 200, body
        assert isinstance(body.get("can_run"), bool), body
        assert isinstance(body.get("checks"), list), body
    finally:
        fx.close()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
