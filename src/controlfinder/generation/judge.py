"""The LLM judges: faithfulness (pre-registered definition 6) and pairwise (definition 7).

Faithfulness isn't correctness. An answer can repeat its context perfectly and still be wrong,
because the context was the wrong controls; the citation checks and answer accuracy catch that
side. The faithfulness judge sees the exact controls the generator saw and scores 1 to 5 with
the rubric below, fixed before the first judged run. Two known judge biases are handled here:
it's told not to reward length (verbosity bias), and it comes from a different model family
than the generator (self-preference).

The pairwise judge picks the better of two answers, which brings in position bias: judges tend
to favor whichever answer comes first, or second. So the caller asks in both orders and counts
a win only when both orders pick the same answer.
"""

import re

from controlfinder.generation.prompt import controls_block

JUDGE = """You are checking whether an answer is faithful to the controls it was written from: does every claim in it come from those controls? Judge only that. Don't judge whether the answer is true in the real world, whether it's complete, or how well it's written, and don't reward length: a short answer whose claims are all supported deserves a 5.

Score from 1 to 5:
5: every claim in the answer is supported by the controls.
4: every main claim is supported; one minor detail goes beyond the controls.
3: the main point is supported, but at least one claim isn't.
2: most claims aren't supported by the controls.
1: the answer contradicts the controls or has nothing to do with them.

<controls>
{controls}
</controls>

Question: {question}

<answer>
{answer}
</answer>

Reply with one line in the form SCORE: <1-5>, then one sentence saying why."""

_SCORE = re.compile(r"^\W*SCORE\W*([1-5])\b", re.IGNORECASE | re.MULTILINE)  # also '**SCORE:** 4'


def judge_prompt(question: str, chunks: list[tuple[str, str]], answer: str) -> str:
    return JUDGE.format(controls=controls_block(chunks), question=question, answer=answer)


def score(reply: str) -> int | None:
    """The first 'SCORE: n' line's n, or None if the judge didn't follow the format."""
    match = _SCORE.search(reply)
    return int(match[1]) if match else None


PAIRWISE = """You are comparing two answers to a question about NIST SP 800-53 Rev 5 security and privacy controls. Each answer was written from controls retrieved for it, and all of those controls are below. Decide which answer is better: the one that answers the question more directly and correctly, using only claims the controls support. Don't prefer an answer for being longer, or for coming first or second. If they're about equally good, say TIE.

<controls>
{controls}
</controls>

Question: {question}

<answer_1>
{first}
</answer_1>

<answer_2>
{second}
</answer_2>

Reply with one line in the form WINNER: 1, WINNER: 2 or WINNER: TIE, then one sentence saying why."""

_WINNER = re.compile(r"^\W*WINNER\W*(1|2|TIE)\b", re.IGNORECASE | re.MULTILINE)


def pairwise_prompt(question: str, chunks: list[tuple[str, str]], first: str, second: str) -> str:
    return PAIRWISE.format(controls=controls_block(chunks), question=question, first=first, second=second)


def winner(reply: str) -> str | None:
    """'1', '2' or 'TIE' from the first 'WINNER: ...' line, or None if the judge didn't follow the format."""
    match = _WINNER.search(reply)
    return match[1].upper() if match else None
