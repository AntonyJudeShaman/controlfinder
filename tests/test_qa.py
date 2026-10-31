import json
from collections import Counter

import pytest

from controlfinder.eval.goldset import UNSEAL
from controlfinder.eval.qa import QA, UNANSWERABLE, check, load_questions, read_questions, split_questions
from controlfinder.ingest.oscal import parse_catalog
from controlfinder.ingest.sources import CATALOG, fetch


def row(qid="q001", question="How should we back up our data?", gold=("cp-9",), category="answerable"):
    return {"id": qid, "question": question, "answerable": bool(gold), "gold": list(gold),
            "category": category, "why": "a reason"}


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_check_accepts_answerable_and_unanswerable_rows():
    check(row())
    check(row(gold=(), category="trivia"))


@pytest.mark.parametrize("change", [
    {"gold": []},
    {"answerable": False, "category": "legal"},
    {"category": "legal"},
    {"category": "mystery"},
    {"gold": ["ac-2.1"]},
    {"gold": ["AC-2"]},
    {"gold": ["cp-9", "cp-9"]},
    {"note": "an extra key"},
])
def test_check_rejects_labels_that_disagree(change):
    with pytest.raises(ValueError):
        check(row() | change)


def test_split_is_50_50_within_each_category_and_order_independent():
    rows = [row(f"a{n}") for n in range(6)] + [row(f"t{n}", gold=(), category="trivia") for n in range(4)]
    split = split_questions(rows)
    assert split == split_questions(list(reversed(rows)))
    assert sum(split[f"a{n}"] == "dev" for n in range(6)) == 3
    assert sum(split[f"t{n}"] == "dev" for n in range(4)) == 2


@pytest.mark.parametrize("second", [row(question="Another question?"), row("q002", question=" how should we BACK UP our data? ")])
def test_read_questions_rejects_a_repeated_id_or_question(tmp_path, second):
    with pytest.raises(ValueError, match="repeated"):
        read_questions(write(tmp_path / "qa.jsonl", [row(), second]))


def test_test_split_is_sealed(monkeypatch):
    monkeypatch.delenv(UNSEAL, raising=False)
    with pytest.raises(PermissionError):
        load_questions("test")


def test_unsealing_takes_the_explicit_flag(tmp_path, monkeypatch):
    path = write(tmp_path / "qa.jsonl", [row(f"q{n}", question=f"Question {n}?") for n in range(2)])
    monkeypatch.setenv(UNSEAL, "1")
    assert len(load_questions("test", path)) == 1


def test_committed_set_has_60_answerable_and_8_of_each_unanswerable_kind_split_evenly():
    counts = Counter((q.category, q.split) for q in read_questions(QA))
    assert counts == {("answerable", "dev"): 30, ("answerable", "test"): 30,
                      **{(category, side): 4 for category in UNANSWERABLE for side in ("dev", "test")}}


def test_committed_gold_labels_are_active_base_controls():
    controls, _ = parse_catalog(json.loads(fetch(CATALOG).read_text())["catalog"])
    active = {c.id for c in controls if not c.is_enhancement}
    assert {c for q in read_questions(QA) for c in q.gold} <= active
