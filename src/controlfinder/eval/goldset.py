"""`make goldset`: the answer key, built from NIST's CSF 2.0 to SP 800-53 mapping.

NIST's CSF 2.0 "Informative References in the Core" xlsx lists, for every subcategory, its
implementation examples (column D) and the controls of other frameworks that support it
(column E). Each subcategory becomes one `subcat` query (its own text) and one `example` query
per implementation example, and they all share one gold set: the 800-53 base controls NIST
mapped to the subcategory.

Every reference is resolved to base controls by one rule, and each rule's hits are logged:
only `SP 800-53 Rev 5.2.0:` lines count (the sheet also has Rev 5.1.1), family-level references
('CP') are dropped, a withdrawn control becomes the controls that took it over, and an
enhancement counts as its base control.

The split is by subcategory, so examples of one subcategory, which paraphrase each other, never
land on both sides. Writes data/eval/queries.jsonl and results/goldset_stats.json.
"""

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

from openpyxl import load_workbook

from controlfinder.ingest.ids import FAMILIES, normalize_control_id, parent_control_id
from controlfinder.ingest.oscal import Withdrawn, parse_catalog
from controlfinder.ingest.sources import CATALOG, CSF, fetch

SHEET = "CSF 2.0"
HEADER = ("Function", "Category", "Subcategory", "Implementation Examples", "Informative References")
REFERENCE = "SP 800-53 Rev 5.2.0:"
SEED = 20261023
DEV_SHARE = 0.7
QUERIES = Path("data/eval/queries.jsonl")
STATS = Path("results/goldset_stats.json")
UNSEAL = "CONTROLFINDER_UNSEAL_TEST"

_SUBCATEGORY = re.compile(r"([A-Z]{2}\.[A-Z]{2}-\d{2}): (.+)", re.S)
_EXAMPLE = re.compile(r"^Ex(\d+): ", re.M)


@dataclass(frozen=True)
class Subcategory:
    id: str  # 'GV.OC-01'
    text: str  # without the 'GV.OC-01: ' prefix
    examples: tuple[str, ...]  # without their 'Ex1: ' markers
    references: tuple[str, ...]  # Rev 5.2.0 references as written: 'PM-11', 'SA-08(19)', 'CP'


@dataclass(frozen=True)
class Query:
    id: str  # 'GV.OC-01' for a subcat query, 'GV.OC-01/ex2' for an example
    type: str  # 'subcat' or 'example'
    subcategory: str
    split: str  # 'dev' or 'test'
    text: str
    gold: tuple[str, ...]  # base control IDs, sorted


def read_subcategories(path: Path) -> tuple[list[Subcategory], Counter]:
    """Active subcategory rows, plus counts of the rows and references left out."""
    rows = load_workbook(path, read_only=True)[SHEET].iter_rows(values_only=True)
    next(rows)  # title banner
    if (header := next(rows)) != HEADER:
        raise ValueError(f"{path}: expected columns {HEADER}, found {header}")
    subcategories, left_out = [], Counter()
    for _, _, subcategory, examples, references in rows:
        lines = [line.strip() for line in (references or "").splitlines()]
        refs = tuple(line.removeprefix(REFERENCE).strip() for line in lines if line.startswith(REFERENCE))
        if not subcategory:
            left_out["Rev 5.2.0 references on function or category rows"] += len(refs)
        elif "[Withdrawn" in subcategory:
            left_out["withdrawn subcategory rows"] += 1
        else:
            if not (match := _SUBCATEGORY.fullmatch(subcategory.strip())):
                raise ValueError(f"unexpected subcategory cell: {subcategory[:60]!r}")
            left_out["Rev 5.1.1 references"] += sum(line.startswith("SP 800-53 Rev 5.1.1:") for line in lines)
            subcategories.append(Subcategory(match[1], " ".join(match[2].split()), split_examples(examples), refs))
    return subcategories, left_out


def split_examples(cell: str) -> tuple[str, ...]:
    """'Ex1: Share ...\\nEx2: Align ...' -> ('Share ...', 'Align ...'). Raises unless numbered 1, 2, 3, ..."""
    before, *parts = _EXAMPLE.split(cell.strip())
    numbers, texts = parts[0::2], parts[1::2]
    if before or numbers != [str(n) for n in range(1, len(numbers) + 1)]:
        raise ValueError(f"examples aren't numbered Ex1, Ex2, ...: {cell[:60]!r}")
    return tuple(" ".join(text.split()) for text in texts)


def resolve(reference: str, active: set[str], withdrawn: dict[str, Withdrawn]) -> tuple[tuple[str, ...], str]:
    """The base controls one reference counts as, and the rule that decided it.

    'PM-11' -> (('pm-11',), 'control'), 'SA-08(19)' -> (('sa-8',), 'enhancement'),
    'RA-04' -> (('ra-3',), 'withdrawn'), 'CP' -> ((), 'family').
    """
    if reference.lower() in FAMILIES:
        return (), "family"
    control_id = normalize_control_id(reference)
    if control_id in withdrawn:
        # A family target ('sr' for SA-12) is dropped, like a family-level reference.
        targets, rule = [t for t in withdrawn[control_id].targets if t not in FAMILIES], "withdrawn"
    else:
        targets = [control_id]
        rule = "control" if parent_control_id(control_id) == control_id else "enhancement"
    if unknown := [t for t in targets if t not in active]:
        raise ValueError(f"{reference}: {unknown} isn't an active control")
    return tuple(sorted({parent_control_id(t) for t in targets})), rule


def split_subcategories(ids: list[str]) -> dict[str, str]:
    """'dev' or 'test' for each subcategory: 70/30 within each CSF function (GV, ID, PR, ...).

    Members of a function are ordered by a seeded hash rather than random.shuffle, whose
    algorithm Python doesn't promise to keep, so the split can't change with the Python version.
    """
    by_function = defaultdict(list)
    for sid in ids:
        by_function[sid.split(".")[0]].append(sid)
    split = {}
    for members in by_function.values():
        members.sort(key=lambda sid: hashlib.sha256(f"{SEED}:{sid}".encode()).hexdigest())
        n_dev = round(DEV_SHARE * len(members))
        split |= {sid: "dev" if i < n_dev else "test" for i, sid in enumerate(members)}
    return split


def build_queries(subcategories: list[Subcategory], gold: dict[str, tuple[str, ...]],
                  split: dict[str, str]) -> list[Query]:
    queries = []
    for sub in subcategories:
        shared = {"subcategory": sub.id, "split": split[sub.id], "gold": gold[sub.id]}
        queries.append(Query(id=sub.id, type="subcat", text=sub.text, **shared))
        queries += [Query(id=f"{sub.id}/ex{n}", type="example", text=text, **shared)
                    for n, text in enumerate(sub.examples, 1)]
    return queries


def load_queries(split: str, path: Path = QUERIES) -> list[Query]:
    """One split of the committed queries. The test split stays sealed until the Phase 6 run."""
    if split == "test" and os.environ.get(UNSEAL) != "1":
        raise PermissionError(f"the test split is sealed; only the final Phase 6 run sets {UNSEAL}=1")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return [Query(**{**row, "gold": tuple(row["gold"])}) for row in rows if row["split"] == split]


def main() -> None:
    controls, withdrawn = parse_catalog(json.loads(fetch(CATALOG).read_text())["catalog"])
    active, withdrawn_by_id = {c.id for c in controls}, {w.id: w for w in withdrawn}
    subcategories, left_out = read_subcategories(fetch(CSF))

    gold, applied = {}, defaultdict(list)
    for sub in subcategories:
        base_ids = set()
        for reference in sub.references:
            counts_as, rule = resolve(reference, active, withdrawn_by_id)
            base_ids.update(counts_as)
            applied[rule].append({"subcategory": sub.id, "reference": reference, "counts_as": list(counts_as)})
        gold[sub.id] = tuple(sorted(base_ids))
    mapped = [sub for sub in subcategories if gold[sub.id]]
    split = split_subcategories([sub.id for sub in mapped])
    queries = build_queries(mapped, gold, split)

    QUERIES.parent.mkdir(parents=True, exist_ok=True)
    QUERIES.write_text("".join(json.dumps(asdict(q)) + "\n" for q in queries))
    sizes = [len(gold[sub.id]) for sub in mapped]
    examples = [len(sub.examples) for sub in mapped]
    resolved = sum(len(entry["counts_as"]) for entries in applied.values() for entry in entries)
    per_split = {name: [q for q in queries if q.split == name] for name in ("dev", "test")}
    stats = {
        "source": {"url": CSF.url, "sha256": CSF.sha256, "sheet": SHEET, "reference_prefix": REFERENCE},
        "subcategories": {"active": len(subcategories), "mapped": len(mapped),
                          "unmapped": [sub.id for sub in subcategories if not gold[sub.id]]},
        "left_out": dict(left_out),
        "references_by_rule": {rule: len(applied[rule]) for rule in ("control", "enhancement", "withdrawn", "family")},
        "duplicates_after_roll_up": resolved - sum(sizes),
        "family_level_dropped": applied["family"],
        "withdrawn_remapped": applied["withdrawn"],
        "enhancements_rolled_up": applied["enhancement"],
        "gold_set_size": {"min": min(sizes), "median": median(sizes), "max": max(sizes),
                          **{f"subcategories_over_{k}": sum(n > k for n in sizes) for k in (5, 10, 20)}},
        "examples_per_subcategory": {"min": min(examples), "median": median(examples), "max": max(examples)},
        "split": {
            "unit": "subcategory", "stratified_by": "CSF function", "seed": SEED, "dev_share": DEV_SHARE,
            **{name: {"subcategories": len({q.subcategory for q in qs}),
                      "subcat_queries": sum(q.type == "subcat" for q in qs),
                      "example_queries": sum(q.type == "example" for q in qs)} for name, qs in per_split.items()},
            "by_function": {fn: {name: sum(s == name for sid, s in split.items() if sid.startswith(fn + "."))
                                 for name in ("dev", "test")}
                            for fn in sorted({sid.split(".")[0] for sid in split})},
        },
    }
    STATS.write_text(json.dumps(stats, indent=2) + "\n")

    print(f"{len(mapped)} of {len(subcategories)} subcategories mapped; gold set size "
          f"{min(sizes)}-{max(sizes)} (median {median(sizes):g})")
    for name, qs in per_split.items():
        print(f"{name}: {stats['split'][name]}")
    print(f"wrote {QUERIES} ({len(queries)} queries) and {STATS}")


if __name__ == "__main__":
    main()
