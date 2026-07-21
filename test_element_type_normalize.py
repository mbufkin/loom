#!/usr/bin/env python3
"""
test_element_type_normalize.py — regression test for the Layer 0 element_type
normalizer. The bug it guards: the model emits 5E-model phase names and compound
values that used to collapse to 'unclear', starving every downstream rubric of
the components that were genuinely present.
"""

from schema_validate import ELEMENT_TYPES, normalize_element_type


def test_canonical_types_pass_through():
    for t in ELEMENT_TYPES:
        assert normalize_element_type(t) == t


def test_5e_phases_map_onto_components():
    assert normalize_element_type("explore_activity") == "guided_practice"
    assert normalize_element_type("explain_activity") == "direct_instruction"
    assert normalize_element_type("evaluate_activity") == "assessment_checkpoint"
    assert normalize_element_type("elaborate") == "independent_practice"
    assert normalize_element_type("extend_activity") == "independent_practice"
    assert normalize_element_type("engage") == "hook_engagement"


def test_compound_takes_first_resolvable_component():
    # The model echoing the pipe-delimited enum list, or tagging one element with
    # several phases — take the first that resolves to a real component type.
    assert normalize_element_type("hook_engagement|direct_instruction") == "hook_engagement"
    assert normalize_element_type("explore_activity|guided_practice") == "guided_practice"
    assert normalize_element_type("evaluate_activity|assessment_checkpoint") == "assessment_checkpoint"
    assert normalize_element_type("unclear|guided_practice") == "guided_practice"


def test_surface_variants_and_casing():
    assert normalize_element_type("Objective") == "standards_objectives"
    assert normalize_element_type("  CLOSURE ") == "reflection_closure"
    assert normalize_element_type("exit_ticket") == "assessment_checkpoint"


def test_unknown_and_empty_return_none():
    assert normalize_element_type("banana") is None
    assert normalize_element_type("") is None
    assert normalize_element_type(None) is None
    assert normalize_element_type(42) is None


def test_explicit_unclear_is_preserved_not_none():
    # 'unclear' is a first-class honest answer, distinct from an unrecognizable
    # type (which returns None so callers can flag/coerce).
    assert normalize_element_type("unclear") == "unclear"


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:  # noqa: PERF203
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
