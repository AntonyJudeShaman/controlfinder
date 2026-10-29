"""The three chunking strategies, built from parsed controls.

A chunk is what we embed, index and retrieve, so the way we cut the catalog decides what one
search hit can contain:
- A_control_only: one chunk per base control (heading, statement, guidance). Enhancements are
  left out, so text that only an enhancement contains can't be found at all.
- B_control_plus_enh: one chunk per base control with all its enhancements appended. Same
  words as C, grouped into fewer and longer chunks, and the embedding model only reads the
  first 512 tokens of each.
- C_separate: one chunk per control and per enhancement, each carrying the base control it
  rolls up to. Several chunks can share a parent, so evaluation deduplicates hits to parents.
"""

from collections import defaultdict
from dataclasses import dataclass

from controlfinder.ingest.ids import display_id
from controlfinder.ingest.oscal import Control

STRATEGIES = ("A_control_only", "B_control_plus_enh", "C_separate")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # strategy letter + control id: 'A:ac-2', 'C:ac-2.1'
    strategy: str
    control_id: str
    parent_control_id: str
    text: str


def control_text(control: Control, parent_title: str | None) -> str:
    """Heading, statement, guidance. Enhancement headings use NIST's 'AC-2(1) Parent | Own title' form."""
    title = f"{parent_title} | {control.title}" if parent_title else control.title
    sections = [f"{display_id(control.id)} {title}", control.statement, control.guidance]
    return "\n\n".join(section for section in sections if section)


def build_chunks(controls: list[Control]) -> list[Chunk]:
    bases = [c for c in controls if not c.is_enhancement]
    titles = {c.id: c.title for c in bases}
    texts = {c.id: control_text(c, titles[c.parent_id] if c.parent_id else None) for c in controls}
    enhancements = defaultdict(list)
    for c in controls:
        if c.is_enhancement:
            enhancements[c.parent_id].append(c.id)

    chunks = [Chunk(f"A:{b.id}", "A_control_only", b.id, b.id, texts[b.id]) for b in bases]
    for b in bases:
        merged = "\n\n".join([texts[b.id], *(texts[e] for e in enhancements[b.id])])
        chunks.append(Chunk(f"B:{b.id}", "B_control_plus_enh", b.id, b.id, merged))
    for c in controls:
        chunks.append(Chunk(f"C:{c.id}", "C_separate", c.id, c.parent_id or c.id, texts[c.id]))
    return chunks
