"""Chunk building on a few hand-made controls: what each strategy contains, and that every chunk
rolls up to the right parent control, which the parent-level metrics depend on.
"""

from controlfinder.ingest.chunks import build_chunks
from controlfinder.ingest.oscal import Control

CONTROLS = [
    Control("ac-1", "AC", "Policy and Procedures", "a. Write a policy.", "Policies set direction.", None),
    Control("ac-2", "AC", "Account Management", "a. Define account types.", None, None),
    Control("ac-2.1", "AC", "Automated System Account Management", "Use automation.", "Automation helps.", "ac-2"),
    Control("ac-2.2", "AC", "Removal of Temporary Accounts", "Remove them.", None, "ac-2"),
]


def by_strategy(strategy: str) -> dict:
    return {chunk.control_id: chunk for chunk in build_chunks(CONTROLS) if chunk.strategy == strategy}


def test_a_has_one_chunk_per_base_control_and_no_enhancement_text():
    a = by_strategy("A_control_only")
    assert list(a) == ["ac-1", "ac-2"]
    assert a["ac-1"].text == "AC-1 Policy and Procedures\n\na. Write a policy.\n\nPolicies set direction."
    assert a["ac-2"].text == "AC-2 Account Management\n\na. Define account types."


def test_b_appends_each_enhancement_to_its_base_control_in_order():
    b = by_strategy("B_control_plus_enh")
    assert list(b) == ["ac-1", "ac-2"]
    assert b["ac-2"].text == (
        "AC-2 Account Management\n\na. Define account types.\n\n"
        "AC-2(1) Account Management | Automated System Account Management\n\nUse automation.\n\nAutomation helps.\n\n"
        "AC-2(2) Account Management | Removal of Temporary Accounts\n\nRemove them."
    )


def test_c_has_one_chunk_per_control_and_enhancement():
    c = by_strategy("C_separate")
    assert list(c) == ["ac-1", "ac-2", "ac-2.1", "ac-2.2"]
    assert c["ac-2"].text == by_strategy("A_control_only")["ac-2"].text
    assert c["ac-2.1"].text == (
        "AC-2(1) Account Management | Automated System Account Management\n\nUse automation.\n\nAutomation helps."
    )


def test_every_chunk_rolls_up_to_its_controls_parent():
    controls = {c.id: c for c in CONTROLS}
    for chunk in build_chunks(CONTROLS):
        assert chunk.parent_control_id == (controls[chunk.control_id].parent_id or chunk.control_id)


def test_chunk_ids_are_unique():
    ids = [chunk.chunk_id for chunk in build_chunks(CONTROLS)]
    assert len(ids) == len(set(ids))
