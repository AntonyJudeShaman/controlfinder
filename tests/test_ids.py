"""normalize_control_id is the function most worth testing: a wrong ID never raises, it turns a
correct retrieval into a miss. This lists every form we expect, plus near-misses that must be
rejected instead of guessed.
"""

import pytest

from controlfinder.ingest.ids import display_id, normalize_control_id, parent_control_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # OSCAL forms pass through.
        ("ac-2", "ac-2"),
        ("ac-2.1", "ac-2.1"),
        # Spreadsheet and display forms, with and without zero padding.
        ("AC-2", "ac-2"),
        ("AC-02", "ac-2"),
        ("AC-2(1)", "ac-2.1"),
        ("AC-02(01)", "ac-2.1"),
        ("AC-2 (1)", "ac-2.1"),
        ("AC-2.1", "ac-2.1"),
        ("ac-02.01", "ac-2.1"),
        ("Ac-2(1)", "ac-2.1"),
        # Padding is stripped; zeros that matter are kept.
        ("PM-09", "pm-9"),
        ("AC-10", "ac-10"),
        ("AC-010", "ac-10"),
        ("SI-04(10)", "si-4.10"),
        ("SC-7(12)", "sc-7.12"),
        ("ac-2.10", "ac-2.10"),
        # Surrounding whitespace, including the non-breaking space spreadsheets tend to carry.
        ("  AC-2 ", "ac-2"),
        ("\u00a0AC-2(1)\n", "ac-2.1"),
    ],
)
def test_normalizes_known_forms(raw, expected):
    assert normalize_control_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "CP",  # a family-level reference, not a control
        "AC",
        "AC-",
        "AC-0",
        "AC-00",
        "AC-2()",
        "AC-2(0)",
        "AC-2(1",
        "AC-2(1)(a)",  # a statement part, not an enhancement
        "AC-2a",
        "AC-2.1.1",
        "AC2",
        "AC_2",
        "AC\u20132",  # en dash
        "XY-1",  # not an SP 800-53 family
        "SP 800-53 Rev 5.2.0: AC-2",  # the reference prefix has to be stripped first
    ],
)
def test_rejects_everything_else(raw):
    with pytest.raises(ValueError):
        normalize_control_id(raw)


@pytest.mark.parametrize(
    ("raw", "parent"),
    [
        ("ac-2", "ac-2"),
        ("ac-2.1", "ac-2"),
        ("AC-02(01)", "ac-2"),
        ("SI-4(10)", "si-4"),
        # A prefix check like startswith("ac-2") would get these wrong.
        ("ac-21", "ac-21"),
        ("ac-21.1", "ac-21"),
    ],
)
def test_parent_control_id(raw, parent):
    assert parent_control_id(raw) == parent


@pytest.mark.parametrize(("raw", "shown"), [("ac-2", "AC-2"), ("ac-2.1", "AC-2(1)"), ("AC-02(01)", "AC-2(1)")])
def test_display_id(raw, shown):
    assert display_id(raw) == shown
