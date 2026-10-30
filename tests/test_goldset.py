"""Answer-key rules on hand-made inputs, plus structural checks on the committed queries file."""

import json
from collections import defaultdict

import pytest
from openpyxl import Workbook

from controlfinder.eval.goldset import (
    HEADER,
    QUERIES,
    SHEET,
    UNSEAL,
    Subcategory,
    build_queries,
    load_queries,
    read_subcategories,
    resolve,
    split_examples,
    split_subcategories,
)
from controlfinder.ingest.ids import parent_control_id
from controlfinder.ingest.oscal import Withdrawn

ACTIVE = {"ac-2", "ac-2.1", "pm-11", "ra-3"}
WITHDRAWN = {
    "ra-4": Withdrawn("ra-4", False, "incorporated-into", ("ra-3",)),
    "sa-12": Withdrawn("sa-12", False, "incorporated-into", ("sr",)),
}


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("PM-11", (("pm-11",), "control")),
        ("AC-02", (("ac-2",), "control")),
        ("AC-02(01)", (("ac-2",), "enhancement")),
        ("RA-04", (("ra-3",), "withdrawn")),
        ("SA-12", ((), "withdrawn")),
        ("CP", ((), "family")),
    ],
)
def test_resolve(reference, expected):
    assert resolve(reference, ACTIVE, WITHDRAWN) == expected


@pytest.mark.parametrize("reference", ["AC-03", "AC-02(02)", "AC-2a"])
def test_resolve_rejects_references_outside_the_active_catalog(reference):
    with pytest.raises(ValueError):
        resolve(reference, ACTIVE, WITHDRAWN)


def test_split_examples_strips_markers_and_whitespace():
    assert split_examples("Ex1: Share the\n mission\nEx2: Align  goals") == ("Share the mission", "Align goals")


@pytest.mark.parametrize("cell", ["Ex1: a\nEx3: b", "Preamble\nEx1: a", "Ex2: a"])
def test_split_examples_rejects_unexpected_numbering(cell):
    with pytest.raises(ValueError):
        split_examples(cell)


def write_sheet(path, header, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    sheet.append([None, "The NIST Cybersecurity Framework 2.0", None, None, None])
    sheet.append(list(header))
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_read_subcategories_keeps_active_rows_and_rev_520_references(tmp_path):
    path = tmp_path / "csf.xlsx"
    write_sheet(path, HEADER, [
        ["GOVERN (GV): The strategy", None, None, None, "SP 800-53 Rev 5.2.0: PM-01"],
        [None, "Organizational Context (GV.OC): The circumstances", None, None, "CSF v1.1: ID.BE"],
        [None, None, "GV.OC-01: The organizational mission is understood", "Ex1: Share the mission\nEx2: Align goals",
         "CCMv4.0: BCR-01\nSP 800-53 Rev 5.1.1: PM-11\nSP 800-53 Rev 5.2.0: PM-11\nSP 800-53 Rev 5.2.0: SA-08(19)"],
        [None, None, "ID.AM-06: [Withdrawn: Incorporated into GV.RR-02]", None, None],
    ])
    subcategories, left_out = read_subcategories(path)
    assert subcategories == [Subcategory("GV.OC-01", "The organizational mission is understood",
                                         ("Share the mission", "Align goals"), ("PM-11", "SA-08(19)"))]
    assert left_out == {"Rev 5.2.0 references on function or category rows": 1, "Rev 5.1.1 references": 1,
                        "withdrawn subcategory rows": 1}


def test_read_subcategories_rejects_a_changed_layout(tmp_path):
    path = tmp_path / "csf.xlsx"
    write_sheet(path, ["Function", "Category", "Subcategory", "Informative References", "Implementation Examples"], [])
    with pytest.raises(ValueError):
        read_subcategories(path)


def test_split_is_70_30_within_each_function_and_order_independent():
    ids = [f"GV.OC-{n:02d}" for n in range(1, 11)] + [f"RC.RP-{n:02d}" for n in range(1, 4)]
    split = split_subcategories(ids)
    assert split == split_subcategories(list(reversed(ids)))
    assert sum(split[sid] == "dev" for sid in ids[:10]) == 7
    assert sum(split[sid] == "dev" for sid in ids[10:]) == 2


def test_examples_inherit_their_subcategorys_gold_set_and_split():
    sub = Subcategory("GV.OC-01", "Mission is understood", ("Share it", "Align it"), ("PM-11",))
    queries = build_queries([sub], {"GV.OC-01": ("pm-11",)}, {"GV.OC-01": "dev"})
    assert [(q.id, q.type, q.text) for q in queries] == [
        ("GV.OC-01", "subcat", "Mission is understood"),
        ("GV.OC-01/ex1", "example", "Share it"),
        ("GV.OC-01/ex2", "example", "Align it"),
    ]
    assert {(q.split, q.gold) for q in queries} == {("dev", ("pm-11",))}


def test_test_split_is_sealed(monkeypatch):
    monkeypatch.delenv(UNSEAL, raising=False)
    with pytest.raises(PermissionError):
        load_queries("test")


def test_unsealing_takes_the_explicit_flag(tmp_path, monkeypatch):
    path = tmp_path / "queries.jsonl"
    row = {"id": "GV.OC-01", "type": "subcat", "subcategory": "GV.OC-01", "split": "test", "text": "t", "gold": ["pm-11"]}
    path.write_text(json.dumps(row) + "\n")
    monkeypatch.setenv(UNSEAL, "1")
    assert [(q.id, q.gold) for q in load_queries("test", path)] == [("GV.OC-01", ("pm-11",))]


def committed_queries() -> list[dict]:
    return [json.loads(line) for line in QUERIES.read_text().splitlines()]


def test_committed_split_keeps_each_subcategory_on_one_side():
    sides = defaultdict(set)
    for q in committed_queries():
        sides[q["subcategory"]].add(q["split"])
    assert all(len(s) == 1 for s in sides.values())


def test_committed_gold_sets_are_nonempty_and_base_controls_only():
    for q in committed_queries():
        assert q["gold"] and all(parent_control_id(c) == c for c in q["gold"])
