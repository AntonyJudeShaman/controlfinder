"""The generation prompt, and how an abstention is recognized (pre-registered definition 2).

The model gets the retrieved controls, each wrapped in a tag that carries the ID it must cite,
and four rules: use only these controls, cite every claim in brackets, reply with exactly the
sentinel when they don't answer the question, and keep it short. The judge gets the same
`controls_block` text, so it grades against exactly what the generator saw.
"""

from controlfinder.ingest.ids import display_id

SENTINEL = "INSUFFICIENT_EVIDENCE"

GENERATE = """You answer questions about NIST SP 800-53 Rev 5 security and privacy controls, using only the controls below.

Rules:
1. Use only what the controls below say. Don't add facts from anywhere else.
2. Cite every claim with the ID of the control that supports it, in square brackets, exactly as written in that control's id attribute, for example [AC-2] or [AC-2(3)]. Put one ID in each pair of brackets.
3. If the controls below don't contain what's needed to answer the question, reply with exactly INSUFFICIENT_EVIDENCE and nothing else.
4. Answer in plain prose, in at most 150 words.

<controls>
{controls}
</controls>

Question: {question}"""


def controls_block(chunks: list[tuple[str, str]]) -> str:
    """(control_id, text) pairs, best first, as tagged blocks: <control id="AC-2(3)">...</control>."""
    return "\n\n".join(f'<control id="{display_id(control_id)}">\n{text}\n</control>' for control_id, text in chunks)


def generation_prompt(question: str, chunks: list[tuple[str, str]]) -> str:
    return GENERATE.format(controls=controls_block(chunks), question=question)


def abstained(answer: str) -> bool:
    return answer.lstrip().startswith(SENTINEL)
