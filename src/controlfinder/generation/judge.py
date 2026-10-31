"""The faithfulness judge (pre-registered definition 6): does the answer say only what its context says?

Faithfulness isn't correctness. An answer can repeat its context perfectly and still be wrong,
because the context was the wrong controls; the citation checks and answer accuracy catch that
side. The judge sees the exact controls the generator saw and scores 1 to 5 with the rubric
below, fixed before the first judged run. Two known judge biases are handled here: it's told
not to reward length (verbosity bias), and it comes from a different model family than the
generator (self-preference). Position bias only arises when comparing two answers, in Phase 5.
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
