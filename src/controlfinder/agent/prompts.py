"""The agent's own prompts: the scope check, the query rewrite and the retry after bad citations.

Like the Phase 4 prompts, these were fixed before the agent's first run on the QA set, and
their hashes are saved with the results. None of them quotes a QA question, and the rewrite
prompt gives no example queries, so nothing from the dev questions can leak into them.
"""

from controlfinder.ingest.ids import display_id

SCOPE = """Decide whether the question below is about information security, cybersecurity or privacy: the controls, policies, processes, risks, audits or compliance an organization uses to protect its systems and data. If you're unsure, treat it as in scope.

Question: {question}

Reply with exactly one word: IN_SCOPE or OUT_OF_SCOPE."""

REWRITE = """The question below was used to search the NIST SP 800-53 Rev 5 control catalog, and the controls found didn't match it well. Write one new search query for the catalog: expand acronyms, and use the plain, formal wording that the catalog's control titles and statements use. Don't answer the question, and don't repeat a query already tried.

Question: {question}

Queries already tried:
{tried}

Reply with the new query only, on one line."""

RETRY = """{prompt}

Your previous answer broke rule 2: {problem}. Answer again, citing only IDs from the controls above."""


def scope_verdict(reply: str) -> bool | None:
    """True for IN_SCOPE, False for OUT_OF_SCOPE, None if the reply has neither."""
    text = reply.upper()
    if "OUT_OF_SCOPE" in text:
        return False
    return True if "IN_SCOPE" in text else None


def rewrite_prompt(question: str, tried: list[str]) -> str:
    return REWRITE.format(question=question, tried="\n".join(f"- {q}" for q in tried))


def rewritten_query(reply: str) -> str | None:
    """The reply's first non-empty line, without surrounding quotes."""
    lines = [line.strip().strip("\"'`") for line in reply.splitlines()]
    return next((line for line in lines if line), None)


def retry_prompt(prompt: str, invalid: list[str]) -> str:
    if invalid:
        ids = ", ".join(f"[{display_id(c)}]" for c in invalid)
        problem = f"it cited {ids}, which {'is' if len(invalid) == 1 else 'are'} not among the controls above"
    else:
        problem = "it cited no controls"
    return RETRY.format(prompt=prompt, problem=problem)
