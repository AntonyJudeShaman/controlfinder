# Phase 1: Data and chunking

## What we built

`make ingest` turns NIST's SP 800-53 catalog into the rows every later phase searches: one row per active control or enhancement in `controls`, and the same text cut three different ways in `chunks`.

| File | What it is |
|---|---|
| `src/controlfinder/ingest/sources.py` | The two pinned downloads: the catalog at oscal-content commit `f0de6d8`, and the embedding model's tokenizer at Hugging Face revision `5c38ec7`. Both are checked against a sha256 on every run |
| `src/controlfinder/ingest/ids.py` | `normalize_control_id()`, `parent_control_id()`, `display_id()` |
| `src/controlfinder/ingest/oscal.py` | The parser. Active items become `Control` records with readable text; withdrawn items become `Withdrawn` records that say where their content went |
| `src/controlfinder/ingest/chunks.py` | Builds strategies A, B and C |
| `src/controlfinder/ingest/stats.py` | Counts, plus chunk lengths in the embedding model's own tokens |
| `src/controlfinder/ingest/__main__.py` | `make ingest`: fetch, parse, chunk, load Postgres, write `results/corpus_stats.json` |
| `tests/test_ids.py` | Every ID form we accept, and the near-misses we must reject |
| `tests/test_oscal.py` | The parser on a hand-written mini catalog with every OSCAL feature we rely on |
| `tests/test_chunks.py` | What each strategy contains, and that every chunk rolls up to the right parent |

## How it works

### `make ingest`, step by step

1. **Fetch.** `fetch()` downloads the catalog and the tokenizer if they're missing, then checks their sha256 either way. A mismatch stops the run.
2. **Parse.** `parse_catalog()` walks the 20 families. For every control and enhancement it first checks that NIST's own labels for it (`AC-2(1)`, `AC-02(01)`) normalize to its OSCAL id. Then it keeps the item as a `Control`, or as a `Withdrawn` record if its `status` property says `withdrawn`.
3. **Chunk.** `build_chunks()` cuts the controls three ways (below).
4. **Guard.** If any chunk still contains `{{`, the run stops: that would be a placeholder format we don't render.
5. **Load.** `load()` empties `controls` and `chunks` and inserts everything in one transaction, base controls before their enhancements so every `parent_id` points at an existing row.
6. **Measure.** `corpus_stats()` tokenizes every chunk and writes `results/corpus_stats.json`, and `make docs` refreshes the tables in this file.

<!-- BEGIN generated: corpus_counts -->
| SP 800-53 Rev 5.2.0 catalog | Count |
|---|---|
| Families | 20 |
| Active base controls | 300 |
| Active enhancements | 714 |
| Withdrawn base controls (skipped) | 24 |
| Withdrawn enhancements (skipped) | 158 |
| Withdrawn, linked as `incorporated-into` | 146 |
| Withdrawn, linked as `moved-to` | 34 |
| Withdrawn, no replacement | 2 |
| NIST ID labels checked against `normalize_control_id` | 3587 |
<!-- END generated: corpus_counts -->

### From OSCAL to text

OSCAL stores a control as nested JSON. Here is AC-2(2), trimmed to what the parser reads:

```json
{
  "id": "ac-2.2",
  "title": "Automated Temporary and Emergency Account Management",
  "props": [
    {"name": "label", "value": "AC-02(02)", "class": "zero-padded"},
    {"name": "label", "value": "AC-2(2)"}
  ],
  "params": [
    {"id": "ac-02.02_odp.01", "select": {"choice": ["remove", "disable"]}},
    {"id": "ac-02.02_odp.02", "label": "time period",
     "props": [{"name": "alt-label", "value": "time period for each type of account", "class": "sp800-53"}]}
  ],
  "parts": [
    {"name": "statement",
     "prose": "Automatically {{ insert: param, ac-02.02_odp.01 }} temporary and emergency accounts after {{ insert: param, ac-02.02_odp.02 }}."}
  ]
}
```

The `{{ insert: param, … }}` markers are blanks that each organization fills in. We render them the way NIST's published text does, so the chunk reads like the real control:

```
AC-2(2) Account Management | Automated Temporary and Emergency Account Management

Automatically [Selection: remove; disable] temporary and emergency accounts after [Assignment: organization-defined time period for each type of account].

Management of temporary and emergency accounts includes the removal or disabling of such accounts automatically after a predefined time period rather than at the convenience of the system administrator. Automatic removal or disabling of accounts provides a more consistent implementation.
```

The rules, from `render_param()`:

```python
if "select" in param:                       # a list of choices
    how_many = " (one or more)" if param["select"].get("how-many") == "one-or-more" else ""
    choices = "; ".join(render(choice, params).strip() for choice in param["select"]["choice"])
    return f"[Selection{how_many}: {choices}]"   # choices can contain parameters, hence render()
# alt-label is the SP 800-53 wording; label is the shorter SP 800-53A assessment wording.
label = prop(param, "alt-label", "sp800-53") or param["label"]
if not label.startswith("organization-defined"):
    label = f"organization-defined {label}"
return f"[Assignment: {label}]"
```

Statements with sub-items (`a.`, `1.`, `(a)`) become one line per item, label first, like AC-1's "a. Develop, document, and disseminate to [Assignment: organization-defined personnel or roles]:". Links in prose, such as `[AU-02](#au-2)`, keep only their text. The assessment parts (SP 800-53A objectives and methods) are not part of the corpus.

### ID normalization

```python
FAMILIES = frozenset("ac at au ca cm cp ia ir ma mp pe pl pm ps pt ra sa sc si sr".split())

# Family, control number, then an optional enhancement number written "(1)" or ".1".
# "0*" drops zero padding and "[1-9][0-9]*" keeps the digits that matter, so "10" stays "10".
_CONTROL_ID = re.compile(r"([a-z]{2})-0*([1-9][0-9]*)(?: ?\(0*([1-9][0-9]*)\)|\.0*([1-9][0-9]*))?")

def normalize_control_id(raw: str) -> str:
    match = _CONTROL_ID.fullmatch(raw.strip().lower())       # fullmatch: no junk before or after
    if match is None or match[1] not in FAMILIES:
        raise ValueError(f"not an SP 800-53 control or enhancement ID: {raw!r}")
    family, number, enhancement = match[1], match[2], match[3] or match[4]
    return f"{family}-{number}.{enhancement}" if enhancement else f"{family}-{number}"
```

`AC-2`, `AC-02`, `AC-2(1)`, `AC-02(01)`, `AC-2 (1)` and `ac-2.1` all land on the OSCAL form the `controls` table is keyed by. Anything else raises: a family on its own (`CP`), a statement part (`AC-2(1)(a)`), an en dash, an unknown family, or a reference that still has its `SP 800-53 Rev 5.2.0:` prefix. `parent_control_id()` keeps the part before the dot, so `ac-2.1` rolls up to `ac-2` and `ac-21` stays `ac-21`.

### The three strategies

Take AC-2 and its enhancements AC-2(1), AC-2(2), and so on:

| Strategy | Chunks for AC-2 | Text |
|---|---|---|
| `A_control_only` | 1 | AC-2's heading, statement and guidance. The enhancements are not in the corpus at all |
| `B_control_plus_enh` | 1 | The A text, then every active enhancement's text, in catalog order |
| `C_separate` | 1 + one per enhancement | Each control and enhancement on its own. Base-control chunks are identical to A's |

B and C contain exactly the same words, grouped differently, so comparing them measures grouping alone. Every chunk stores `parent_control_id`: the base control for an enhancement, and itself for a base control.

<!-- BEGIN generated: chunk_lengths -->
| Strategy | Chunks | Min | Median | p90 | Max (chunk) | Over 512 tokens | Share of all tokens past 512 |
|---|---|---|---|---|---|---|---|
| A_control_only | 300 | 57 | 225.5 | 488.4 | 957 (`A:pl-2`) | 22 (7%) | 4.1% |
| B_control_plus_enh | 300 | 57 | 402 | 1174.3 | 9458 (`B:sa-8`) | 100 (33%) | 39.9% |
| C_separate | 1014 | 32 | 137 | 320.7 | 957 (`C:pl-2`) | 24 (2%) | 2.0% |
<!-- END generated: chunk_lengths -->

How to read the table:

- Lengths are in the embedding model's tokens, counted with its own tokenizer, including the `[CLS]` and `[SEP]` markers it adds to every input. The limit is 512, from the model's `sentence_bert_config.json`.
- **B:** 100 of 300 chunks are over the limit, and 39.9% of all B tokens sit past it. The embedding will never see those tokens. The longest, SA-8 with all its enhancements, is 9,458 tokens; the model reads the first 512.
- **A and C** are mostly under the limit (medians 225.5 and 137), but not entirely: 22 A chunks and 24 C chunks are over it too, mostly because their guidance is long. The longest is PL-2, at 957 tokens.

## Concepts

### What chunking is, and why it matters for recall

Picture the catalog as a book, and retrieval as handing someone index cards. Search never returns "a sentence from a control"; it returns whole cards. How you cut the cards decides three things:

1. **What can be found at all.** In A, text that only an enhancement contains doesn't exist, so a question about it can't hit.
2. **How sharp a match is.** An embedding squeezes a whole chunk into one vector, which is roughly an average of everything the chunk talks about. A B chunk that merges a control with many enhancements gets a blurry average that matches no single question well. A small C chunk gets a sharp one.
3. **What the model sees.** Anything past 512 tokens is gone (next section).

Smaller isn't automatically better. A tiny chunk can lose its context: "Automated System Account Management" means more next to "Account Management". That's why every C enhancement's heading carries its parent's title, the way NIST writes it.

**Recall** asks: did the right control show up in the top k? Chunking moves recall in both directions, and that's why Phase 3 measures A, B and C instead of picking one by intuition.

### Silent truncation

Think of a teacher who only reads the first page of every essay. bge-small-en-v1.5 reads at most 512 tokens: the `[CLS]` marker, 510 tokens of text, and `[SEP]`. sentence-transformers cuts the rest off without a warning or an error. The chunk still gets a vector, so nothing looks broken.

Two consequences matter for us:

- **The damage is concentrated in B.** 39.9% of B's tokens are invisible to its embedding, compared with 2.0% for C.
- **It only affects dense retrieval.** Postgres FTS and BM25 index every word of the chunk. If B looks fine with keyword search but poor with dense search in Phase 3, truncation is the first suspect.

The usual fixes, if we need one later: split long chunks into overlapping windows that share a parent, use a long-context embedding model, or embed a shorter field. We haven't applied any yet, because B exists to measure what merging costs.

### Why strategy C needs parent-level deduplication

The answer key (Phase 2) lists base controls: an enhancement reference counts as its parent. In C, AC-2, AC-2(1) and AC-2(3) are three different chunks with one parent. If all three appear in the top 10, they are one correct answer, not three.

So metrics are computed at the parent level. Map every retrieved chunk to its `parent_control_id`, keep the first occurrence at its rank, and drop the repeats. Without this:

- Repeats take up slots, so the top 10 chunks might hold only 4 distinct controls, unfairly lowering C's recall@10.
- Precision is distorted either way, depending on whether repeats count as hits.

That's also why C retrieves deeper than k before deduplicating (a 2026-10-23 decision): the system gets to fill k distinct parents.

### Why ID normalization bugs silently wreck your metrics

Imagine the answer key says "AC-02(01)" and our system says "ac-2.1". A plain string comparison says "wrong": the system gets marked wrong for being right. No exception, no warning. Recall just comes out low, and you might conclude dense retrieval is bad when the real problem is spelling.

The classic bugs, each covered by a test:

- **Zero padding.** NIST's spreadsheets write `PM-09` and `AC-02(01)`.
- **Two enhancement syntaxes.** `(1)` in spreadsheets and the published text, `.1` in OSCAL.
- **Prefix matching.** `startswith("ac-2")` makes AC-21 a child of AC-2.
- **Naive zero stripping.** Removing every 0 turns AC-10 into AC-1.

Our defenses: one function that every ID goes through, tests for accepted and rejected forms, and a check on every ingest that all 3,587 ID labels in NIST's own catalog normalize to their item's id. Unknown forms raise instead of guessing, which is how we found the odd link formats in the gotchas below.

## Decisions

Each of these has a row in `DECISIONS.md`.

- **The canonical ID is the OSCAL form (`ac-2`, `ac-2.1`), and unknown forms raise.** The schema already keyed `controls` this way, and raising turned format surprises into loud failures instead of silent misses.
- **Parameters are rendered as in NIST's published text, preferring the SP 800-53 `alt-label`.** AC-2(2) reads "time period for each type of account", not the 800-53A label's bare "time period".
- **Parameters are looked up across the whole catalog, not per item.** Parameter ids are unique catalog-wide, and some enhancements use a parameter defined on their parent or a sibling.
- **Withdrawn-item links resolve to a control or a family code.** A statement-part target maps to its control. A family target stays a family code, which Phase 2 drops and logs like other family-level references.
- **Chunk text is heading, statement and guidance, with no assessment text.** Enhancement headings use NIST's "AC-2(1) Parent | Own title" form, so each enhancement carries its parent's topic.
- **B is A plus each enhancement's C text.** B and C hold the same words, so the ablation isolates grouping.
- **Lengths are counted with the model's own tokenizer, at a pinned revision.** The same revision embeds in Phase 2. We use the `tokenizers` library alone, which avoids installing PyTorch before we need it.
- **Downloads are gitignored and checked against a sha256 on every run.** Both are pinned to immutable versions. The CSF xlsx will still be committed in Phase 2, because its endpoint isn't versioned.
- **No `data/processed/` JSONL.** Postgres is the only copy of parsed controls and chunks, so copies can't drift apart, and BM25 in Phase 2 reads the same rows as FTS.
- **Re-ingesting replaces both tables in one transaction.** The database always matches the pinned sources. Embeddings go with their chunks, so `make embed` runs after every ingest.

## Gotchas we hit

1. **Withdrawn links don't always point at a control.** The strict normalizer crashed on `ac-2_smt.k`: AC-2(10) was folded into item k of AC-2's statement. SA-12's link points at `#sr`, the whole Supply Chain Risk Management family. The fix: map a statement part to its control, and keep a family as a family code.
2. **A parameter can live on another item.** IA-13(3) uses a parameter defined on IA-13, and SC-42(2) uses one defined on SC-42(1). The per-item lookup raised `KeyError`. Parameter ids turned out to be unique catalog-wide, so one catalog-wide lookup fixed it.
3. **Withdrawn items can still carry a statement.** CP-10(3) and SC-19 are withdrawn but have statement text. Only the `status` property decides what's active.
4. **There are two label vocabularies.** A parameter's `label` is the SP 800-53A wording, and the SP 800-53 wording sometimes lives in `alt-label`. Using `label` alone would have produced "[Assignment: organization-defined time period]" for AC-2(2).
5. **Truncation isn't only B's problem.** 22 A chunks exceed 512 tokens on their own, mostly because of long guidance. Even AC-2, without its enhancements, is over the limit.
6. **Cross-references in prose are zero-padded.** Guidance says `AU-02`, not `AU-2`. We keep NIST's text as it is; normalization takes care of any ID an LLM copies from it in Phase 4.

## Interview questions

**1. How did you chunk the corpus, and why three strategies instead of one?**
The catalog has 300 active base controls and 714 active enhancements. A keeps one chunk per base control and leaves enhancements out; B merges each base control with all its enhancements into one chunk; C makes every control and enhancement its own chunk, 1,014 in total. B and C contain exactly the same words, so the comparison isolates grouping. I didn't want to pick by intuition: small chunks give sharp embeddings but lose context, big chunks keep context but blur and get truncated. Phase 3 measures all three on the same queries.

**2. What happens when a chunk is longer than the embedding model's limit?**
bge-small reads 512 tokens, including its `[CLS]` and `[SEP]` markers, and sentence-transformers silently drops the rest. The chunk still gets a vector, so nothing errors. In our corpus, 100 of 300 B chunks are over the limit, and 39.9% of all B tokens are never seen by the embedding; SA-8 with its enhancements is 9,458 tokens. Keyword search still sees every word, so truncation hurts B in dense retrieval only, which is exactly what I'd check first if B looks fine with BM25 but bad with dense search.

**3. Why does strategy C need parent-level deduplication?**
The gold set lists base controls, and in C several chunks share one parent: AC-2, AC-2(1) and AC-2(3) are one correct answer, not three. So before computing metrics I map each retrieved chunk to its `parent_control_id`, keep the first occurrence at its rank, and drop repeats. Otherwise repeats eat top-k slots and lower C's recall, and precision gets distorted. C also retrieves deeper than k before deduplicating, so it can still fill k distinct parents.

**4. Why is ID normalization "the most important gotcha"?**
Because a mismatch never errors; it shows up as a miss. NIST's spreadsheet writes `AC-02(01)`, OSCAL writes `ac-2.1`, and LLMs write whatever they like. Compare them as strings and the system is marked wrong for being right, and you'd draw the wrong conclusion about the retriever. I route every ID through one function with tests for accepted and rejected forms, including traps like `ac-21` vs `ac-2` and `AC-10` vs `AC-1`, and on every ingest I check that all 3,587 ID labels in NIST's catalog normalize to their item's own id.

**5. Why does your normalizer raise instead of doing its best?**
A best-effort parser turns a format surprise into a wrong ID that nobody notices. On the first run, the normalizer rejected `ac-2_smt.k`, a withdrawn enhancement's link to a statement part. Listing every link from withdrawn items then turned up one more odd shape, a link to a whole family (`sr`). Both became explicit, tested rules and logged decisions instead of silent guesses. The same idea caught the next problem: a strict parameter lookup raised `KeyError` instead of leaving a placeholder in the text.

**6. What did you do with withdrawn controls?**
The catalog has 182 withdrawn items (24 base controls and 158 enhancements), and we skip them, because they have no current text to retrieve. We keep where their content went: 146 are `incorporated-into` other controls (SA-12 into the whole SR family), 34 are `moved-to`, and 2 have no replacement. Phase 2 uses those links to remap answer-key references, such as RA-4 to RA-3, so a reference to a withdrawn control doesn't count as a miss that can never be fixed.

**7. How do you know the parsed text is right?**
Three layers. Unit tests run the parser on a hand-written mini catalog with each feature we rely on: nested items, both parameter kinds, a selection with a parameter inside it, links, and withdrawn items. At ingest, guards stop the run if any NIST label disagrees with its id or any placeholder is left unrendered. And I compared output with the published text: AC-2(2) renders as "Automatically [Selection: remove; disable] temporary and emergency accounts after [Assignment: organization-defined time period for each type of account]."

## Follow-ups from the quiz

**Why can B tie C on keyword search but lose on dense search?**
B and C hold the same words; B only groups each control with its enhancements. FTS and BM25 index every word, so both strategies give them the same material. BM25 does weigh matches in long chunks less (length normalization), but that's a discount, not a deletion. The embedding model reads 512 tokens and drops the rest: 100 of 300 B chunks are over the limit, and 39.9% of B's tokens are never embedded, against 2.0% for C. It's worst for base controls that are over the limit on their own, because their B window fills up before the first enhancement starts. Of the 165 base controls with enhancements, 16 have a B vector identical to their A vector (`results/embed_stats.json`), so not one word of their enhancements reaches the embedding. Fixes: overlapping windows under 512 tokens that share the parent ID, or searching small pieces and returning the merged chunk, which is strategy C with a parent roll-up. A long-context model would read everything, but it squeezes even more topics into one vector.

**Why does C retrieve deeper than k before deduplicating?**
Take a made-up result list. C returns AC-2(1), AC-2, AC-6, AC-2(3), IA-2, and the answer key is AC-2, IA-2 and AC-3. Recall starts from the answer key: how many of its controls are in the top k? Deduplicated to parents, the top 3 is AC-2, AC-6, IA-2, so recall@3 is 2/3. AC-3 was never retrieved, and AC-6 costs precision, not recall. Deduplicating only the top 3 chunks leaves AC-2 and AC-6, two different controls in three slots, and recall@3 drops to 1/3. A and B never have repeats, so without the deeper fetch C would be penalized for repeats, not for retrieving worse. With HNSW, `hnsw.ef_search` must be at least as deep as the fetch: at the default of 40, the partial index returned exactly 40 rows for a LIMIT of 50.

**What's wrong with "lowercase and delete every 0", plus `startswith` for roll-ups?**
`"AC-10".lower().replace("0", "")` gives `ac-1`: the 0 in 10 is a digit, not padding, so Concurrent Session Control turns into Policy and Procedures. `AC-2(1)` comes out as `ac-2(1)`, which matches nothing, because the key is `ac-2.1`. `SI-04(10)` gets both bugs at once: `si-4(1)`, the wrong enhancement in the wrong syntax. `PM-09` gives `pm-9`, which is why a single happy-path test passes. `"ac-21".startswith("ac-2")` is true, so AC-21 (Information Sharing) counts as a hit for AC-2 (Account Management), and so does every control from AC-20 to AC-25. Nothing crashes. Some of these bugs hide right answers and others reward wrong ones, so recall can come out believable and still be wrong. `normalize_control_id` strips only leading zeros, accepts both enhancement syntaxes and raises on anything else. `parent_control_id` cuts at the dot and compares the whole parent.
