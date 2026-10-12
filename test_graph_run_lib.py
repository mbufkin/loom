"""Pointing graph/units at the current run must never end a run.

os.symlink needs elevation or Developer Mode on Windows and raises WinError
1314 otherwise. set_active_graph_run called it unguarded, so on an ordinary
Windows account a full audit died after Layer 0, Layer 0-B and the entire
graph phase had already succeeded -- every unit written to disk, the run
aborted creating a convenience link to them.

graph/ACTIVE names the current run and the review UI reads
graph/runs/<id>/units/... directly. Neither needs the link, so these tests pin
the degradation: try a symlink, fall back to a junction or a copy, and if the
platform allows none of that, carry on.
"""

import json
import os

import graph_run_lib as grl


def _run_tree(tmp_path, rid="lightning-with-graph"):
    """A project root with one graph run already written to disk."""
    run_dir = tmp_path / "graph" / "runs" / rid
    (run_dir / "units" / "immune").mkdir(parents=True)
    (run_dir / "units" / "immune" / "HAS-PART.json").write_text("{}", encoding="utf-8")
    (run_dir / "PHASE-SUMMARY.json").write_text(
        json.dumps({"units": 1}), encoding="utf-8"
    )
    return run_dir


def test_a_platform_that_refuses_links_does_not_end_the_run(tmp_path, monkeypatch):
    """The failure that aborted a finished graph phase on Windows."""

    def no_links(*a, **k):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(os, "symlink", no_links)
    monkeypatch.setattr(grl, "_point_at", lambda *a, **k: "skipped")
    _run_tree(tmp_path)

    grl.set_active_graph_run(tmp_path, "lightning-with-graph")

    # The thing that actually carries the answer still got written.
    assert grl.read_active_run(tmp_path) == "lightning-with-graph"


def test_the_active_marker_is_what_names_the_run(tmp_path):
    """graph/ACTIVE is the contract; the links are a convenience on top."""
    _run_tree(tmp_path)

    grl.set_active_graph_run(tmp_path, "lightning-with-graph")

    assert (tmp_path / "graph" / "ACTIVE").is_file()
    assert grl.read_active_run(tmp_path) == "lightning-with-graph"


def test_units_are_reachable_through_the_run_directory_either_way(tmp_path):
    """The path the review UI uses, which never goes through graph/units."""
    _run_tree(tmp_path)

    grl.set_active_graph_run(tmp_path, "lightning-with-graph")

    rid = grl.read_active_run(tmp_path)
    direct = tmp_path / "graph" / "runs" / rid / "units" / "immune" / "HAS-PART.json"
    assert direct.is_file()


def test_phase_summary_is_readable_at_the_graph_root(tmp_path, monkeypatch):
    """run_project checks graph/PHASE-SUMMARY.json to call the run complete.

    A copy satisfies that check as well as a symlink does, and the file is
    rewritten on every run, so it cannot go stale behind the run it describes.
    """

    def no_links(*a, **k):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(os, "symlink", no_links)
    _run_tree(tmp_path)

    grl.set_active_graph_run(tmp_path, "lightning-with-graph")

    summary = tmp_path / "graph" / "PHASE-SUMMARY.json"
    assert summary.is_file(), "the DONE check reads this path"
    assert json.loads(summary.read_text(encoding="utf-8")) == {"units": 1}


def test_calling_twice_in_one_run_does_not_invent_a_legacy_run(tmp_path):
    """graph_phase calls this at the start and again after writing the summary.

    The second call must recognise the link the first one made. When it did
    not -- Path.is_symlink() answers False for a Windows junction -- it read
    its own link as pre-namespace data and moved it into
    runs/legacy-pre-namespace, which then appeared in the review UI as a
    second graph run with the same two units as the real one.
    """
    _run_tree(tmp_path)

    grl.set_active_graph_run(tmp_path, "lightning-with-graph")
    grl.set_active_graph_run(tmp_path, "lightning-with-graph")

    runs = sorted(p.name for p in (tmp_path / "graph" / "runs").iterdir())
    assert runs == ["lightning-with-graph"], f"invented a run: {runs}"


def test_real_pre_namespace_data_is_still_preserved(tmp_path):
    """The migration this guards is real and must keep working.

    A graph/units directory with actual files in it predates run
    namespacing, and moving it aside is the only way not to lose it.
    """
    _run_tree(tmp_path)
    old = tmp_path / "graph" / "units"
    old.mkdir(parents=True)
    (old / "HAS-PART.json").write_text('{"old": true}', encoding="utf-8")

    grl.set_active_graph_run(tmp_path, "lightning-with-graph")

    moved = (
        tmp_path
        / "graph"
        / "runs"
        / "legacy-pre-namespace"
        / "units"
        / "HAS-PART.json"
    )
    assert moved.is_file(), "pre-namespace data was dropped"
    assert json.loads(moved.read_text(encoding="utf-8")) == {"old": True}


def test_pointing_at_a_second_run_moves_the_marker(tmp_path):
    """A/B comparison: the newer run becomes active without destroying the older."""
    _run_tree(tmp_path, "run-a")
    _run_tree(tmp_path, "run-b")

    grl.set_active_graph_run(tmp_path, "run-a")
    assert grl.read_active_run(tmp_path) == "run-a"

    grl.set_active_graph_run(tmp_path, "run-b")
    assert grl.read_active_run(tmp_path) == "run-b"
    assert (tmp_path / "graph" / "runs" / "run-a" / "units" / "immune").is_dir()
