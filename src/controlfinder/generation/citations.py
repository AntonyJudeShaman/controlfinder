"""Citation checks, done in code rather than by an LLM (pre-registered definition 4).

Whether a cited ID was in the context is a lookup, not a judgment: code gets it right every
time, and an LLM asked to check its own citations can be wrong in the same way it was wrong
when it wrote them. A citation is a bracketed control ID, normalized so '[AC-2(3)]' and
'[ac-2.3]' match. It's valid if the context held that exact control or enhancement, and it
counts toward gold recall through its base control.
"""

import re
from typing import NamedTuple

from controlfinder.ingest.ids import normalize_control_id, parent_control_id

_BRACKETS = re.compile(r"\[([^\[\]]*)\]")


def cited(answer: str) -> list[str]:
    """Bracketed control IDs, normalized, each once, in order of first appearance.

    '[AC-2, SC-7]' is two citations. Brackets holding anything else, like the catalog's
    '[Assignment: organization-defined frequency]', aren't citations.
    """
    ids = []
    for inside in _BRACKETS.findall(answer):
        for part in re.split(r"[,;]", inside):
            try:
                control_id = normalize_control_id(part)
            except ValueError:
                continue
            if control_id not in ids:
                ids.append(control_id)
    return ids


class Check(NamedTuple):
    citations: list[str]
    valid: list[str]  # citations whose exact ID was in the context
    gold_cited: list[str]  # gold base controls reached through valid citations


def check(answer: str, context_ids: set[str], gold: tuple[str, ...]) -> Check:
    citations = cited(answer)
    valid = [c for c in citations if c in context_ids]
    return Check(citations, valid, sorted({parent_control_id(c) for c in valid} & set(gold)))
