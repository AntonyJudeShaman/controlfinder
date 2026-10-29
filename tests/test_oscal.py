"""The parser on a tiny hand-written catalog that has each OSCAL feature we rely on: nested
statement items, assignment and selection parameters (one selection has a parameter inside it),
links in prose, an enhancement, and withdrawn items with and without links that matter.
"""

import pytest

from controlfinder.ingest.oscal import Withdrawn, parse_catalog


def labels(display: str, padded: str) -> list[dict]:
    return [{"name": "label", "value": display}, {"name": "label", "value": padded, "class": "zero-padded"}]


def catalog() -> dict:
    statement = {
        "name": "statement",
        "parts": [
            {
                "name": "item",
                "props": [{"name": "label", "value": "a."}],
                "prose": "Assign account managers to {{ insert: param, ac-2_prm_1 }}:",
                "parts": [
                    {
                        "name": "item",
                        "props": [{"name": "label", "value": "1."}],
                        "prose": "Review accounts every {{ insert: param, ac-02_odp.02 }}; and",
                    }
                ],
            },
            {
                "name": "item",
                "props": [{"name": "label", "value": "b."}],
                "prose": "{{ insert: param, ac-02_odp.03 }} stale accounts and {{ insert: param, ac-02_odp.05 }}.",
            },
        ],
    }
    params = [
        {"id": "ac-2_prm_1", "label": "organization-defined personnel or roles"},
        {
            "id": "ac-02_odp.02",
            "label": "time period",
            "props": [{"name": "alt-label", "value": "time period for each type of account", "class": "sp800-53"}],
        },
        {
            "id": "ac-02_odp.03",
            "select": {"how-many": "one-or-more", "choice": ["remove", "disable", "{{ insert: param, ac-02_odp.04 }} "]},
        },
        {"id": "ac-02_odp.04", "label": "actions"},
        {"id": "ac-02_odp.05", "select": {"choice": ["notify", "log"]}},
    ]
    enhancement = {
        "id": "ac-2.1",
        "title": "Automated System Account Management",
        "props": labels("AC-2(1)", "AC-02(01)"),
        # Uses a parameter defined on its parent, as ia-13.3 does in the real catalog.
        "parts": [{"name": "statement", "prose": "Automate {{ insert: param, ac-02_odp.04 }}."}],
    }
    withdrawn_enhancement = {
        "id": "ac-2.2",
        "title": "Removed Enhancement",
        "props": [*labels("AC-2(2)", "AC-02(02)"), {"name": "status", "value": "withdrawn"}],
        # The second target is item b of AC-2's statement, which belongs to AC-2.
        "links": [{"href": "#ac-2.1", "rel": "incorporated-into"}, {"href": "#ac-2_smt.b", "rel": "incorporated-into"}],
    }
    base = {
        "id": "ac-2",
        "title": "Account Management",
        "props": labels("AC-2", "AC-02"),
        "params": params,
        "parts": [
            statement,
            {"name": "guidance", "prose": "See [AU-02](#au-2) and [SP 800-12](#0a1b2c3d)."},
            {"name": "assessment-objective", "prose": "Assessment text is not part of the corpus."},
        ],
        "controls": [enhancement, withdrawn_enhancement],
    }
    withdrawn_base = {
        "id": "ac-3",
        "title": "Removed Control",
        "props": [*labels("AC-3", "AC-03"), {"name": "status", "value": "withdrawn"}],
        "links": [{"href": "#0a1b2c3d", "rel": "reference"}, {"href": "#ac-2", "rel": "moved-to"}],
    }
    withdrawn_into_family = {
        "id": "ac-4",
        "title": "Moved to a Whole Family",
        "props": [*labels("AC-4", "AC-04"), {"name": "status", "value": "withdrawn"}],
        "links": [{"href": "#sr", "rel": "incorporated-into"}],
    }
    controls = [base, withdrawn_base, withdrawn_into_family]
    return {"groups": [{"id": "ac", "title": "Access Control", "controls": controls}]}


def test_statement_renders_items_and_parameters_like_the_published_text():
    controls, _ = parse_catalog(catalog())
    assert controls[0].statement == (
        "a. Assign account managers to [Assignment: organization-defined personnel or roles]:\n"
        "1. Review accounts every [Assignment: organization-defined time period for each type of account]; and\n"
        "b. [Selection (one or more): remove; disable; [Assignment: organization-defined actions]] stale accounts"
        " and [Selection: notify; log]."
    )


def test_an_enhancement_can_use_a_parameter_defined_on_its_parent():
    controls, _ = parse_catalog(catalog())
    assert controls[1].statement == "Automate [Assignment: organization-defined actions]."


def test_guidance_keeps_link_text_only():
    controls, _ = parse_catalog(catalog())
    assert controls[0].guidance == "See AU-02 and SP 800-12."
    assert controls[1].guidance is None


def test_enhancements_know_their_parent():
    controls, _ = parse_catalog(catalog())
    assert [(c.id, c.family, c.parent_id) for c in controls] == [("ac-2", "AC", None), ("ac-2.1", "AC", "ac-2")]


def test_withdrawn_items_are_skipped_but_keep_where_their_content_went():
    _, withdrawn = parse_catalog(catalog())
    assert withdrawn == [
        Withdrawn("ac-2.2", is_enhancement=True, relation="incorporated-into", targets=("ac-2.1", "ac-2")),
        Withdrawn("ac-3", is_enhancement=False, relation="moved-to", targets=("ac-2",)),
        Withdrawn("ac-4", is_enhancement=False, relation="incorporated-into", targets=("sr",)),
    ]


def test_a_label_that_disagrees_with_its_id_stops_the_parse():
    bad = catalog()
    bad["groups"][0]["controls"][0]["props"] = labels("AC-2", "AC-02(01)")
    with pytest.raises(ValueError, match="ac-2"):
        parse_catalog(bad)
