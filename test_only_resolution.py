#!/usr/bin/env python3
"""Tests for run_project.resolve_only (no models, no network).

The bug these exist for was expensive rather than subtle. `--only` is handed
to two stages that match on different things: Layer 0 filters source filenames
by substring, Layer 1 and Layer 2 look the unit up by its key in
manifest.yaml. iCEV exports are filename-prefixed, so a unit the manifest
calls "immune" holds documents named "037-immune__*". Passing `--only
037-immune` therefore selected every document correctly, spent 31 minutes
decomposing them, and then failed Layer 1 with "Unknown unit(s) in manifest".
"""

import textwrap

import pytest

from run_project import resolve_only


@pytest.fixture
def manifest(tmp_path):
    """A manifest shaped like a real export: unit keys unprefixed, files not."""
    path = tmp_path / "manifest.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            project:
              id: sample
              name: sample
            sources_dir: /nowhere/sources
            units:
              urinary:
                title: 'Body Systems: Urinary'
                calendar: units/urinary/calendar.yaml
                documents:
                - 034-urinary__assessment.html
                - 034-urinary__vocabulary-handout.html
              immune:
                title: 'Body Systems: Immune'
                calendar: units/immune/calendar.yaml
                documents:
                - 037-immune__assessment.html
                - 037-immune__view-lesson-plan.html
            """
        ),
        encoding="utf-8",
    )
    return path


class TestResolveOnly:
    def test_a_unit_key_resolves_to_itself(self, manifest):
        assert resolve_only(manifest, "immune") == ("immune", "immune")

    def test_a_filename_prefix_resolves_to_its_unit(self, manifest):
        # The case that failed: the filter stays as given for Layer 0, while
        # Layer 1 receives the manifest key it actually knows.
        assert resolve_only(manifest, "037-immune") == ("037-immune", "immune")

    def test_matching_is_case_insensitive(self, manifest):
        assert resolve_only(manifest, "037-IMMUNE")[1] == "immune"

    def test_an_unknown_value_names_the_available_units(self, manifest):
        with pytest.raises(ValueError) as excinfo:
            resolve_only(manifest, "nonsense")
        message = str(excinfo.value)
        # Failing without saying what would have worked just moves the guesswork.
        assert "immune" in message and "urinary" in message

    def test_an_ambiguous_value_is_refused(self, manifest):
        # "0" appears in both 034- and 037- filenames. Picking one arbitrarily
        # would silently audit the wrong unit, which is worse than stopping.
        with pytest.raises(ValueError) as excinfo:
            resolve_only(manifest, "0")
        assert "more than one unit" in str(excinfo.value)

    def test_a_unit_key_wins_over_a_filename_match(self, manifest):
        # An exact key is unambiguous by definition and must not be reinterpreted
        # as a substring, even though "immune" also appears in its filenames.
        assert resolve_only(manifest, "immune") == ("immune", "immune")
