import pytest

from controlfinder.eval.bootstrap import resample_ci
from controlfinder.eval.generation import (
    abstention_f1,
    abstention_precision,
    abstention_recall,
    answer_and_grade,
    citation_precision,
    counts,
)
from controlfinder.eval.qa import Question
from controlfinder.generation import citations, judge, prompt
from controlfinder.generation.llm import LLM, Reply

CHUNKS = [("ac-2.3", "AC-2(3) Account Management | Disable Accounts\n\nDisable accounts ..."),
          ("sc-7", "SC-7 Boundary Protection\n\nMonitor and control communications ...")]


@pytest.mark.parametrize("answer, expected", [
    ("Disable them [AC-2(3)], and [ac-2.3] again.", ["ac-2.3"]),
    ("Both apply [AC-2, SC-7].", ["ac-2", "sc-7"]),
    ("Within [AC-02(01)].", ["ac-2.1"]),
    ("Every [Assignment: organization-defined frequency].", []),
    ("AC-2 without brackets isn't a citation.", []),
])
def test_cited_normalizes_and_dedupes_bracketed_ids(answer, expected):
    assert citations.cited(answer) == expected


def test_a_base_control_isnt_covered_by_its_enhancements_chunk():
    check = citations.check("[AC-2(3)] [AC-2] [SC-7]", {"ac-2.3", "sc-7"}, ("ac-2",))
    assert check.citations == ["ac-2.3", "ac-2", "sc-7"]
    assert check.valid == ["ac-2.3", "sc-7"]
    assert check.gold_cited == ["ac-2"]


def test_prompt_tags_each_control_with_the_id_to_cite():
    text = prompt.generation_prompt("How do we disable accounts?", CHUNKS)
    assert '<control id="AC-2(3)">\nAC-2(3) Account Management' in text
    assert text.endswith("Question: How do we disable accounts?")
    assert prompt.SENTINEL in prompt.GENERATE


@pytest.mark.parametrize("answer, expected", [
    ("INSUFFICIENT_EVIDENCE", True), ("  INSUFFICIENT_EVIDENCE\n", True),
    ("The controls say INSUFFICIENT_EVIDENCE", False), ("Disable them [AC-2(3)].", False),
])
def test_abstained_needs_the_sentinel_first(answer, expected):
    assert prompt.abstained(answer) is expected


@pytest.mark.parametrize("reply, expected", [
    ("SCORE: 4\nOne claim goes beyond the controls.", 4), ("**SCORE:** 5\nAll supported.", 5),
    ("Reasoning first.\nSCORE: 2", 2), ("I'd give it a 4.", None), ("SCORE: 7", None),
])
def test_judge_score_reads_the_score_line(reply, expected):
    assert judge.score(reply) == expected


class Fake:
    """A provider that answers from a script and counts its calls."""

    def __init__(self, *texts):
        self.texts, self.calls, self.__name__ = list(texts), 0, "fake"

    def __call__(self, model, prompt):
        self.calls += 1
        return Reply(self.texts.pop(0), 12.5, model, 100, 20)


def test_llm_replays_a_cached_reply_without_calling_the_provider(tmp_path):
    fake = Fake("first", "second")
    llm = LLM("m", fake, tmp_path / "llm.jsonl")
    assert llm("p") == llm("p") == Reply("first", 12.5, "m", 100, 20)
    assert LLM("m", fake, tmp_path / "llm.jsonl")("p").text == "first"
    assert fake.calls == 1
    assert LLM("other", fake, tmp_path / "llm.jsonl")("p").text == "second"


def question(answerable=True):
    return Question("q001", "How do we disable accounts?", answerable, ("ac-2",) if answerable else (),
                    "answerable" if answerable else "trivia", "why", "dev")


def test_answer_and_grade_checks_citations_and_judges_answers(tmp_path):
    generator = LLM("g", Fake("Disable them [AC-2(3)] at the boundary [SC-7]."), tmp_path / "llm.jsonl")
    grader = LLM("j", Fake("SCORE: 5\nAll supported."), tmp_path / "llm.jsonl")
    row = answer_and_grade(question(), CHUNKS, generator, grader)
    assert row["decision"] == "answer" and row["valid"] == ["ac-2.3", "sc-7"]
    assert row["gold_in_context"] == ["ac-2"] and row["gold_recall"] == 1.0 and row["correct"] is True
    assert row["faithfulness"] == 5


def test_an_invalid_citation_makes_the_answer_incorrect(tmp_path):
    generator = LLM("g", Fake("Disable them [AC-2(3)], see [AC-6]."), tmp_path / "llm.jsonl")
    row = answer_and_grade(question(), CHUNKS, generator, LLM("j", Fake("SCORE: 3"), tmp_path / "llm.jsonl"))
    assert row["gold_recall"] == 1.0 and row["correct"] is False


def test_an_abstention_isnt_judged(tmp_path):
    grader = Fake()
    row = answer_and_grade(question(False), CHUNKS, LLM("g", Fake("INSUFFICIENT_EVIDENCE"), tmp_path / "llm.jsonl"),
                           LLM("j", grader, tmp_path / "llm.jsonl"))
    assert row["decision"] == "abstain" and "faithfulness" not in row and grader.calls == 0


def rows(*pairs):
    return [{"answerable": answerable, "decision": decision, "citations": ["ac-2", "sc-7"], "valid": ["ac-2"]}
            for answerable, decision in pairs]


def test_abstention_metrics_follow_definition_3():
    rs = rows((False, "abstain"), (False, "answer"), (True, "abstain"), (True, "answer"), (True, "answer"))
    assert counts(rs) == {"tp": 1, "fp": 1, "fn": 1, "tn": 2}
    assert abstention_precision(rs) == abstention_recall(rs) == abstention_f1(rs) == 0.5
    assert citation_precision(rs) == 0.5


def test_undefined_metrics_are_none_not_zero():
    never_abstains = rows((False, "answer"), (True, "answer"))
    assert abstention_precision(never_abstains) is None and abstention_f1(never_abstains) is None
    assert abstention_recall(never_abstains) == 0
    assert citation_precision(rows((True, "abstain"))) is None


def test_resample_ci_is_seeded_and_counts_undefined_draws():
    items = [0, 1, 1, 0, 1]
    def share(xs):
        return sum(xs) / len(xs) if 0 in xs else None
    first, again = resample_ci(items, share), resample_ci(items, share)
    assert first == again and first["value"] == 0.6 and first["undefined_resamples"] > 0
    assert first["ci95"][0] <= 0.6 <= first["ci95"][1]
    assert resample_ci([1, 1], share) == {"value": None, "ci95": None, "undefined_resamples": 1000}
