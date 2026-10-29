"""Parse the OSCAL SP 800-53 catalog into flat records, one per control or enhancement.

OSCAL nests the text we need. A statement is a tree of labeled items ("a.", "1.", "(a)"),
parameters are placeholders like `{{ insert: param, ac-01_odp.04 }}` defined elsewhere on the
control, prose links to other controls as `[AU-02](#au-2)`, and withdrawn items are flagged by
a property. This module turns each active item into plain text, rendering parameters the way
NIST's published text does. Withdrawn items are kept aside with the links that say where their
content went, because the gold set remaps references to them.
"""

import re
from dataclasses import dataclass

from controlfinder.ingest.ids import FAMILIES, normalize_control_id, parent_control_id

_INSERT = re.compile(r"\{\{\s*insert:\s*param,\s*([\w.-]+)\s*\}\}")
_LINK = re.compile(r"\[([^\]]*)\]\(#[^)]*\)")


@dataclass(frozen=True)
class Control:
    id: str  # OSCAL form: 'ac-2', 'ac-2.1'
    family: str  # 'AC'
    title: str
    statement: str
    guidance: str | None
    parent_id: str | None  # the base control, for enhancements

    @property
    def is_enhancement(self) -> bool:
        return self.parent_id is not None


@dataclass(frozen=True)
class Withdrawn:
    id: str
    is_enhancement: bool
    relation: str | None  # 'incorporated-into', 'moved-to', or None when nothing replaced it
    targets: tuple[str, ...]  # control IDs, or a family code ('sr') when a whole family took it over


def catalog_items(catalog: dict) -> list[tuple[dict, dict, dict]]:
    """(group, base control, item) for every control and enhancement, in catalog order."""
    return [(g, base, item) for g in catalog["groups"] for base in g["controls"] for item in [base, *base.get("controls", [])]]


def parse_catalog(catalog: dict) -> tuple[list[Control], list[Withdrawn]]:
    """Active items in catalog order (each base control before its enhancements), plus withdrawn ones."""
    items = catalog_items(catalog)
    # Parameter IDs are unique across the catalog, and a few enhancements use one defined on
    # their parent or a sibling (ia-13.3 uses ia-13_odp.01), so they're looked up catalog-wide.
    params = {p["id"]: p for _, _, item in items for p in item.get("params", [])}
    controls, withdrawn = [], []
    for group, base, item in items:
        parent_id = None if item is base else base["id"]
        check_ids(item, parent_id)
        if prop(item, "status") == "withdrawn":
            withdrawn.append(withdrawn_record(item, parent_id))
        else:
            controls.append(control_record(item, group["id"].upper(), parent_id, params))
    return controls, withdrawn


def check_ids(item: dict, parent_id: str | None) -> None:
    """Stop if NIST's own labels for an item ('AC-2(1)', 'AC-02(01)') don't normalize to its id."""
    labels = [item["id"], *(p["value"] for p in item.get("props", []) if p["name"] == "label")]
    if {normalize_control_id(label) for label in labels} != {item["id"]}:
        raise ValueError(f"{item['id']}: labels {labels} don't all normalize to the id")
    if parent_id is not None and parent_control_id(item["id"]) != parent_id:
        raise ValueError(f"{item['id']} is nested under {parent_id}")


def control_record(item: dict, family: str, parent_id: str | None, params: dict) -> Control:
    parts = {p["name"]: p for p in item["parts"]}
    guidance = parts.get("guidance")
    return Control(
        id=item["id"],
        family=family,
        title=item["title"],
        statement="\n".join(statement_lines(parts["statement"], params)),
        guidance=render(guidance["prose"], params) if guidance else None,
        parent_id=parent_id,
    )


def withdrawn_record(item: dict, parent_id: str | None) -> Withdrawn:
    links = [link for link in item.get("links", []) if link["rel"] in ("incorporated-into", "moved-to")]
    return Withdrawn(
        id=item["id"],
        is_enhancement=parent_id is not None,
        relation=links[0]["rel"] if links else None,
        targets=tuple(link_target(link["href"]) for link in links),
    )


def link_target(href: str) -> str:
    """'#ra-3' -> 'ra-3', '#ac-2_smt.k' (item k of AC-2's statement) -> 'ac-2', '#sr' -> 'sr'."""
    target = href.removeprefix("#").split("_smt")[0]
    return target if target in FAMILIES else normalize_control_id(target)


def statement_lines(part: dict, params: dict) -> list[str]:
    """Depth-first, one line per item, label first: 'a. Develop, document, and disseminate ...'."""
    line = " ".join(x for x in (prop(part, "label"), render(part.get("prose", ""), params)) if x)
    lines = [line] if line else []
    for child in part.get("parts", []):
        lines += statement_lines(child, params)
    return lines


def render(prose: str, params: dict) -> str:
    """Replace parameter placeholders with readable text, and links with their link text."""
    text = _INSERT.sub(lambda m: render_param(params[m[1]], params), prose)
    return _LINK.sub(r"\1", text)


def render_param(param: dict, params: dict) -> str:
    """'[Assignment: organization-defined frequency]' or '[Selection (one or more): a; b]'."""
    if "select" in param:
        how_many = " (one or more)" if param["select"].get("how-many") == "one-or-more" else ""
        choices = "; ".join(render(choice, params).strip() for choice in param["select"]["choice"])
        return f"[Selection{how_many}: {choices}]"
    # alt-label is the SP 800-53 wording; label is the shorter SP 800-53A assessment wording.
    label = prop(param, "alt-label", "sp800-53") or param["label"]
    if not label.startswith("organization-defined"):
        label = f"organization-defined {label}"
    return f"[Assignment: {label}]"


def prop(obj: dict, name: str, cls: str | None = None) -> str | None:
    return next((p["value"] for p in obj.get("props", []) if p["name"] == name and p.get("class") == cls), None)
