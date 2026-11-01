import pytest

from controlfinder.agent import prompts
from controlfinder.agent.graph import MAX_REWRITES, Agent, Tools
from controlfinder.eval.agent import agent_row, decision_moves, pairwise, pick_tau, production_pick
from controlfinder.eval.bootstrap import paired_resample_ci
from controlfinder.eval.qa import Question
from controlfinder.generation.llm import LLM, Reply
from controlfinder.retrieval.production import Context, base_ids, with_base_text
from controlfinder.retrieval.rerank import Scored

QUESTION = Question("q1", "How do we disable accounts?", True, ("ac-2",), "answerable", "", "dev")
CONTEXT = [("ac-2", "AC-2 Account Management\n\nManage accounts ..."),
           ("sc-7", "SC-7 Boundary Protection\n\nMonitor and control communications ...")]


class Script:
    """A provider that replies by prompt kind: the scope verdict, numbered rewrites, then scripted answers."""

    __name__ = "script"

    def __init__(self, answers=(), scope="IN_SCOPE"):
        self.answers, self.scope, self.prompts = list(answers), scope, []

    def __call__(self, model, prompt):
        self.prompts.append(prompt)
        if "IN_SCOPE or OUT_OF_SCOPE" in prompt:
            text = self.scope
        elif "Queries already tried" in prompt:
            text = f"rewritten query {prompt.count(chr(10) + '- ')}"
        else:
            text = self.answers.pop(0)
        return Reply(text, 10.0, model, 100, 20)


def scores(value):
    return lambda question, texts: Scored([value] * len(texts), 2.0, 0)


def make_tools(tmp_path, provider, retrieve=lambda query: Context(CONTEXT, 1.0), grade=scores(5.0)):
    llm = LLM("m", provider, tmp_path / "llm.jsonl")
    return Tools(retrieve, grade, llm, llm)


def nodes(state):
    return [s["node"] for s in state["trace"]]


def test_the_loop_stops_after_two_rewrites_when_the_evidence_stays_weak(tmp_path):
    state = Agent(make_tools(tmp_path, Script(), grade=scores(-9.0)), tau=0.0).run(QUESTION.question)
    assert nodes(state) == ["scope_check", "retrieve", "grade_evidence", "rewrite", "retrieve", "grade_evidence",
                            "rewrite", "retrieve", "grade_evidence", "abstain"]
    assert state["decision"] == "abstain" and state["reason"] == "weak_evidence" and state["answer"] is None
    assert state["attempts"] == MAX_REWRITES
    assert state["queries_tried"] == [QUESTION.question, "rewritten query 1", "rewritten query 2"]
    assert [c.control_id for c in state["closest"]] == ["ac-2", "sc-7"]


def test_out_of_scope_abstains_without_retrieving(tmp_path):
    state = Agent(make_tools(tmp_path, Script(scope="OUT_OF_SCOPE")), tau=0.0).run("Who won the 2018 World Cup?")
    assert nodes(state) == ["scope_check", "abstain"]
    assert state["reason"] == "out_of_scope" and state["closest"] == []


def test_strong_evidence_goes_straight_to_a_checked_answer(tmp_path):
    state = Agent(make_tools(tmp_path, Script(["Disable them [AC-2]."])), tau=0.0).run(QUESTION.question)
    assert nodes(state) == ["scope_check", "retrieve", "grade_evidence", "generate", "verify_citations"]
    assert state["decision"] == "answer" and state["citations"] == ["ac-2"]


def test_a_rewrite_that_finds_better_evidence_leads_to_an_answer(tmp_path):
    def retrieve(query):
        return Context(CONTEXT[:1] if query.startswith("rewritten") else CONTEXT[1:], 1.0)

    def grade(question, texts):
        return Scored([3.0 if text.startswith("AC-2") else -3.0 for text in texts], 2.0, 0)

    state = Agent(make_tools(tmp_path, Script(["Disable them [AC-2]."]), retrieve, grade), tau=0.0).run(QUESTION.question)
    assert state["decision"] == "answer" and state["attempts"] == 1
    assert state["queries_tried"] == [QUESTION.question, "rewritten query 1"]


def test_a_bad_citation_gets_one_retry_that_names_it(tmp_path):
    provider = Script(["Use [AC-99].", "Use [AC-2]."])
    state = Agent(make_tools(tmp_path, provider), tau=0.0).run(QUESTION.question)
    assert state["decision"] == "answer" and state["generations"] == 2
    assert "it cited [AC-99], which is not among the controls above" in provider.prompts[-1]


@pytest.mark.parametrize("answers", [["Use [AC-99].", "Use [AC-98]."], ["Just do it.", "Really, just do it."]])
def test_citations_that_fail_twice_end_in_an_abstention(tmp_path, answers):
    state = Agent(make_tools(tmp_path, Script(answers)), tau=0.0).run(QUESTION.question)
    assert state["reason"] == "citations_failed" and state["generations"] == 2


def test_a_refusal_from_the_generator_is_an_abstention(tmp_path):
    state = Agent(make_tools(tmp_path, Script(["INSUFFICIENT_EVIDENCE"])), tau=0.0).run(QUESTION.question)
    assert nodes(state)[-2:] == ["generate", "abstain"] and state["reason"] == "generator_refused"


def test_with_no_gate_weak_evidence_still_goes_to_the_generator(tmp_path):
    tools = make_tools(tmp_path, Script(["Disable them [AC-2]."]), grade=scores(-9.0))
    state = Agent(tools, tau=None).run(QUESTION.question)
    assert state["decision"] == "answer" and state["attempts"] == 0


def test_an_unreadable_scope_reply_counts_as_in_scope(tmp_path):
    state = Agent(make_tools(tmp_path, Script(["Disable them [AC-2]."], scope="Sure!")), tau=0.0).run(QUESTION.question)
    assert state["in_scope"] and state["decision"] == "answer"


@pytest.mark.parametrize("reply, expected", [
    ("IN_SCOPE", True), ("**OUT_OF_SCOPE**", False), ("out_of_scope.", False), ("Probably yes.", None),
])
def test_scope_verdict_reads_either_word(reply, expected):
    assert prompts.scope_verdict(reply) is expected


@pytest.mark.parametrize("reply, expected", [
    ('"account management"\n', "account management"), ("\n\nboundary protection", "boundary protection"), ("", None),
])
def test_rewritten_query_is_the_first_line_without_quotes(reply, expected):
    assert prompts.rewritten_query(reply) == expected


def test_agent_row_scores_a_run_like_a_pipeline_row(tmp_path):
    state = Agent(make_tools(tmp_path, Script(["Disable them [AC-2] [SC-7]."])), tau=0.0).run(QUESTION.question)
    row = agent_row(QUESTION, state)
    assert row["correct"] is True and row["valid"] == ["ac-2", "sc-7"] and row["gold_coverage"] == "base"
    assert row["llm_calls"] == 2 and row["latency_ms"] == sum(s["ms"] for s in state["trace"])


def test_pick_tau_takes_the_best_f1_and_the_lowest_tau_on_a_tie():
    points = [{"tau": None, "abstention_f1": 0.8}, {"tau": -1.0, "abstention_f1": 0.9},
              {"tau": 0.0, "abstention_f1": 0.9}, {"tau": 1.0, "abstention_f1": None}]
    assert pick_tau(points)["tau"] == -1.0


@pytest.mark.parametrize("verdicts, result", [
    (["WINNER: 1", "WINNER: 2"], "agent"), (["WINNER: 2", "WINNER: 1"], "pipeline"),
    (["WINNER: 1", "WINNER: 1"], "tie"), (["WINNER: TIE", "WINNER: TIE"], "tie"), (["No idea.", "WINNER: 2"], "tie"),
])
def test_a_pairwise_win_needs_both_orders_to_agree(tmp_path, verdicts, result):
    grader = LLM("judge", Script(verdicts), tmp_path / "llm.jsonl")
    assert pairwise(QUESTION, "Disable them [AC-2].", "Disable accounts [AC-2].", CONTEXT, CONTEXT,
                    grader)["result"] == result


def test_identical_answers_tie_without_a_judge_call(tmp_path):
    provider = Script()
    out = pairwise(QUESTION, "Same [AC-2].", "Same [AC-2]. ", CONTEXT, CONTEXT, LLM("judge", provider, tmp_path / "x"))
    assert out == {"id": "q1", "result": "tie", "identical": True} and provider.prompts == []


def rows(refused_answerable: int) -> list[dict]:
    """20 unanswerable questions, all refused, and 20 answerable ones, `refused_answerable` of them refused."""
    return ([{"answerable": False, "decision": "abstain"}] * 20
            + [{"answerable": True, "decision": "abstain" if i < refused_answerable else "answer"} for i in range(20)])


def test_production_takes_the_simplest_system_within_noise_of_the_best():
    pick = production_pick({"pipeline": rows(5), "pipeline_base_text": rows(5), "agent": rows(4)})
    assert pick["best"] == "agent" and pick["pick"] == "pipeline"


def test_production_takes_a_system_that_is_distinguishably_best():
    pick = production_pick({"pipeline": rows(20), "pipeline_base_text": rows(20), "agent": rows(0)})
    assert pick["pick"] == "agent"


def test_paired_resample_ci_compares_the_same_questions():
    a, b = [1.0, 1.0, 0.0, 1.0], [0.0, 1.0, 0.0, 0.0]
    out = paired_resample_ci(a, b, lambda xs: sum(xs) / len(xs))
    assert out["value"] == 0.5 and out == paired_resample_ci(a, b, lambda xs: sum(xs) / len(xs))
    assert 0 <= out["ci95"][0] <= out["ci95"][1]


def test_decision_moves_count_changes_for_each_kind_of_question():
    before = [{"answerable": True, "decision": "abstain"}, {"answerable": False, "decision": "abstain"}]
    after = [{"answerable": True, "decision": "answer"}, {"answerable": False, "decision": "abstain"}]
    moves = decision_moves(after, before)
    assert moves["answerable"]["abstain_to_answer"] == 1 and moves["unanswerable"]["abstain_to_abstain"] == 1


def test_base_text_goes_in_front_of_each_enhancement():
    chunks = [("ac-2.3", "AC-2(3) ..."), ("sc-7", "SC-7 ..."), ("ia-2.5", "IA-2(5) ...")]
    assert base_ids(chunks) == ["ac-2", "ia-2"]
    out = with_base_text(chunks, {"ac-2": "AC-2 ...", "ia-2": "IA-2 ..."})
    assert [c for c, _ in out] == ["ac-2", "ac-2.3", "sc-7", "ia-2", "ia-2.5"]
