"""What the dashboard leads with.

The dashboard is the first thing a reviewer opens and, for most of them, the
only thing. Its old shape opened with a table of counts and closed with a
"Scope gaps across 3+ units" section that printed "No pattern reached the 3+
unit threshold" on the welding sample -- a two-unit course where exit tickets
were absent from all five slots that expected them, in both units. The single
most useful sentence the audit could say was computed, then suppressed by a
threshold a small course cannot reach, and the reviewer was told the opposite.

These tests pin the order of the page and the content of the ranked table, so
the finding cannot be demoted back below the counts.
"""

from synthesize import (
    _gap_decision,
    _ranked_gaps,
    _reach_phrase,
    render_dashboard,
)


def _agg(roles, **over):
    """An aggregate-stats payload with only the keys the dashboard reads."""
    base = {
        "documents_judged": 11,
        "elements_judged": 113,
        "mismatch_docs_high": [],
        "mismatch_docs_low": [],
        "review_queue_pending_pairs": 0,
        "finding_status_counts": {"FULFILLED": 8, "MISSING": 9},
        "systemic_missing": [],
        "missing_rollup": {"roles": roles, "silenced": []},
        "unit_rollup": [
            {
                "unit_id": "unit-1",
                "title": "Unit 1: SMAW Fundamentals",
                "match": 45,
                "mismatch": 0,
                "fulfilled": 5,
                "missing": 5,
                "duplicate": 0,
            },
            {
                "unit_id": "unit-2",
                "title": "Unit 2: Oxy-Fuel Cutting",
                "match": 30,
                "mismatch": 0,
                "fulfilled": 3,
                "missing": 4,
                "duplicate": 0,
            },
        ],
    }
    base.update(over)
    return base


def _role(role, expected, missing, units_missing=2, units_total=2, **over):
    r = {
        "role": role,
        "expected": expected,
        "missing": missing,
        "fulfilled": expected - missing,
        "absence_rate": round(missing / expected, 3) if expected else 0.0,
        "units_total": units_total,
        "units_missing": units_missing,
        "classification": "isolated",
    }
    r.update(over)
    return r


# The welding sample's real rollup, which is the case that exposed the bug.
WELDING = [
    _role("exit_ticket", 5, 5),
    _role("lesson_content", 5, 2),
    _role("worksheet", 2, 2),
]


def test_a_role_absent_everywhere_is_named_on_a_two_unit_course():
    """The finding the 3+ unit threshold used to swallow.

    Two units cannot reach SYSTEMIC_MIN_UNITS, so the old page printed "No
    pattern reached the 3+ unit threshold" while exit tickets were missing from
    every slot in both units. Naming the role is the whole point of the rewrite.
    """
    md = render_dashboard("sample", _agg(WELDING))

    assert "Exit tickets" in md
    assert "3+ unit threshold" not in md
    assert "No pattern reached" not in md


def test_widest_gap_is_listed_before_the_partial_one():
    """Reach, not count, decides the order.

    Worksheets are missing twice and lesson content twice, but worksheets are
    absent from every slot that expected them and lesson content from two of
    five. The first is one decision covering the course; the second is two
    days' work. Equal counts must not imply equal priority.
    """
    md = render_dashboard("sample", _agg(WELDING))

    assert md.index("Exit tickets") < md.index("Worksheets")
    assert md.index("Worksheets") < md.index("Lesson content")


def test_verdict_and_gaps_come_before_the_counts_and_the_heatmap():
    """Page order is the readability fix; anything else is decoration."""
    md = render_dashboard("sample", _agg(WELDING))

    assert (
        md.index("Bottom line:")
        < md.index("## What is missing")
        < md.index("## At a glance")
        < md.index("## Unit heatmap")
    )


def test_reach_distinguishes_absent_everywhere_from_absent_sometimes():
    """"All 5" and "2 of the 5" are different instructions; 1.0 and 0.4 are not."""
    assert _reach_phrase(_role("exit_ticket", 5, 5)) == "All 5 places it was expected"
    assert (
        _reach_phrase(_role("lesson_content", 5, 2))
        == "2 of the 5 places it was expected"
    )
    # Singular, because "All 1 places" is the kind of thing reviewers screenshot.
    assert _reach_phrase(_role("quiz", 1, 1)) == "All 1 place it was expected"


def test_the_decision_offered_depends_on_whether_anything_fulfils_the_role():
    """A role absent course-wide asks a different question than a localized gap.

    aggregate_missing's own docstring makes the distinction: absence everywhere
    is usually the day grid expecting an artifact this curriculum does not ship
    -- an expectation call -- while a role present in some slots and absent in
    others is a real, actionable miss.
    """
    assert "confirm this course is meant to ship them" in _gap_decision(
        _role("exit_ticket", 5, 5)
    )
    assert "Author it" in _gap_decision(_role("lesson_content", 5, 2))


def test_roles_a_human_already_ruled_out_are_not_counted_as_gaps():
    """Silenced means calibrated, not missing.

    Listing them among the gaps would re-raise a question the reviewer has
    already answered, which is how a gap list loses its credibility.
    """
    roles = WELDING + [_role("rubric", 4, 4, classification="silenced")]
    agg = _agg(roles)
    agg["missing_rollup"]["silenced"] = [{"role": "rubric"}]

    ranked = _ranked_gaps(agg)
    assert [r["role"] for r in ranked] == ["exit_ticket", "worksheet", "lesson_content"]

    md = render_dashboard("sample", agg)
    assert "Not counted: Rubrics" in md


def test_a_clean_course_shows_no_gap_table_at_all():
    """An empty table is worse than no table: it reads as an unfinished report."""
    agg = _agg([], finding_status_counts={"FULFILLED": 8})
    agg["mismatch_docs_high"] = []

    md = render_dashboard("clean", agg)
    assert "## What is missing" not in md
    assert "## At a glance" in md


def test_the_tier_summary_used_to_carry_alone_now_shows_on_the_heatmap():
    """SUMMARY.md existed for one column; the dashboard now renders it.

    Everything else on that page -- units in scope, elements judged, per-unit
    MATCH and MISMATCH -- already appeared here in plainer words. Tier was the
    single fact that did not, so it had to land before the page could be
    retired rather than merely hidden.
    """
    md = render_dashboard(
        "sample",
        _agg(WELDING),
        tiers={"unit-1": "Developing", "unit-2": "Strong"},
    )

    heatmap = md[md.index("## Unit heatmap") :]
    assert "| Unit | Tier |" in heatmap
    assert "**Developing**" in heatmap
    assert "**Strong**" in heatmap


def test_the_heatmap_keeps_its_old_shape_when_no_tiers_are_supplied():
    """render_dashboard stays a pure function of its arguments.

    Tiers need the project tree (Path A findings, per-unit LESSON-PLAN.json),
    so reports.unit_tiers resolves them and passes them in. Called without
    them -- in a test, or by any caller that has only aggregate stats -- the
    column is dropped rather than filled with a fabricated grade.
    """
    md = render_dashboard("sample", _agg(WELDING))

    heatmap = md[md.index("## Unit heatmap") :]
    assert "Tier" not in heatmap
    assert "| Unit | Confirmed |" in heatmap


def test_a_unit_with_no_tier_renders_a_dash_not_a_guess():
    """A missing grade must read as missing, not as the lowest grade."""
    md = render_dashboard("sample", _agg(WELDING), tiers={"unit-1": "Developing"})

    heatmap = md[md.index("## Unit heatmap") :]
    assert "**Developing**" in heatmap
    assert "| — |" in heatmap


def test_ranking_is_stable_when_two_gaps_have_identical_reach():
    """Two identical rows must not swap places between runs.

    The dashboard is regenerated on every audit and diffed by eye against the
    last one; unstable ordering turns a no-op re-run into apparent churn.
    """
    roles = [_role("worksheet", 2, 2), _role("answer_key", 2, 2)]
    order = [r["role"] for r in _ranked_gaps(_agg(roles))]
    assert order == ["answer_key", "worksheet"]
    assert order == [r["role"] for r in _ranked_gaps(_agg(list(reversed(roles))))]
