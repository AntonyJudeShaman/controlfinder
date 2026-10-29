"""Control ID normalization. Every control ID in the project goes through `normalize_control_id`.

OSCAL writes `ac-2` and `ac-2.1`. NIST's spreadsheets write `AC-2`, `AC-02`, `AC-2(1)` or
`AC-02(01)`, and LLM answers will cite whichever form they like. Gold labels, chunks and
citations only match once they share one form, and a mismatch never raises an error: it just
looks like a retrieval miss. So this module maps every form to the OSCAL form that the
`controls` table is keyed by, and raises on anything it doesn't recognize instead of guessing.
"""

import re

FAMILIES = frozenset("ac at au ca cm cp ia ir ma mp pe pl pm ps pt ra sa sc si sr".split())

# Family, control number, then an optional enhancement number written "(1)" or ".1".
# "0*" drops zero padding and "[1-9][0-9]*" keeps the digits that matter, so "10" stays "10".
_CONTROL_ID = re.compile(r"([a-z]{2})-0*([1-9][0-9]*)(?: ?\(0*([1-9][0-9]*)\)|\.0*([1-9][0-9]*))?")


def normalize_control_id(raw: str) -> str:
    """'AC-02(01)', 'AC-2(1)' and 'ac-2.1' all become 'ac-2.1'. Raises ValueError otherwise."""
    match = _CONTROL_ID.fullmatch(raw.strip().lower())
    if match is None or match[1] not in FAMILIES:
        raise ValueError(f"not an SP 800-53 control or enhancement ID: {raw!r}")
    family, number, enhancement = match[1], match[2], match[3] or match[4]
    return f"{family}-{number}.{enhancement}" if enhancement else f"{family}-{number}"


def parent_control_id(control_id: str) -> str:
    """The base control an ID rolls up to: 'AC-2(1)' -> 'ac-2', and 'ac-2' -> 'ac-2'."""
    return normalize_control_id(control_id).split(".")[0]


def display_id(control_id: str) -> str:
    """NIST's display form, used in chunk headings: 'ac-2.1' -> 'AC-2(1)'."""
    base, _, enhancement = normalize_control_id(control_id).partition(".")
    return base.upper() + (f"({enhancement})" if enhancement else "")
