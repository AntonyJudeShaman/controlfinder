# Phase 4: Answers, citation checks and an LLM judge

## The short version

- **It never answered an unanswerable question, but it refused too many answerable ones.** It refused all 20 unanswerable dev questions (abstention recall 1.000) and also 8 of the 30 answerable ones. So 0.714 of its refusals were right (abstention precision, 95% CI [0.542, 0.864]).
- **The wrong refusals are mostly retrieval's fault, not the model's.** On the 14 answerable questions where a gold control's own chunk was among the 10 retrieved, it answered all 14 correctly. On the 13 where retrieval found the right control but represented it by a narrow enhancement, it refused 7. For example, "Should we require MFA?" brought back IA-2(5) Individual Authentication with Group Authentication, which says nothing about MFA. With that text, refusing was the honest answer.
- **What it did answer was clean.** Every citation named a control it had been given (citation precision 1.000). Of the 22 answered questions, 0.909 cited a gold control with no bad citations [0.773, 1.000].
- **The judge gave all 22 answers a 5, and it isn't a judge that says 5 to everything.** When we planted one made-up claim in each answer, it marked all 22 down: 14 to a 3 and 8 to a 4.
- **An answer takes 9,559 ms at p50**, almost all of it the model call. Retrieval takes 11 ms.

Every number below comes from `results/generation_dev.json` or `results/qa_stats.json`, and `make docs` regenerates the tables.

## What we built

| File | What it is |
|---|---|
| `data/eval/qa.jsonl` | 100 hand-written questions: 60 answerable from SP 800-53 and 40 not. Jude reviewed every label |
| `src/controlfinder/eval/qa.py` | `make qa`: checks the labels, splits the set 50/50 into dev and a sealed test half, and writes `data/eval/qa_review.md` for reviewing it |
| `src/controlfinder/generation/llm.py` | `LLM`: a model call through a Cursor SDK local agent that can only write text, with every call cached |
| `src/controlfinder/generation/prompt.py` | The answer prompt and the refusal word, `INSUFFICIENT_EVIDENCE` |
| `src/controlfinder/generation/citations.py` | Finds the `[AC-2]`-style citations in an answer and checks them against the context, in plain code |
| `src/controlfinder/generation/judge.py` | The faithfulness judge's prompt with its fixed 1–5 rubric, and the parser for its score |
| `src/controlfinder/eval/generation.py` | `make generate`: retrieves, answers, checks citations, judges, probes the judge and writes `results/generation_dev.json` |
| `src/controlfinder/eval/bootstrap.py` | Gains `resample_ci()`: a 95% interval from resampling questions |
| `data/cache/llm.jsonl` | Every model call's prompt, reply, model and timing, committed, so a fresh clone reproduces every number without an API key |
| `tests/test_qa.py`, `tests/test_generation.py` | The label checks, the split and the seal; citation parsing, the metrics and the judge probe, run against a fake model |

## How it works

### The questions

Phase 2's gold set tests retrieval: it gives a CSF sentence and asks which controls NIST maps to it. This phase needs something else: questions a person would actually type, including some the catalog can't answer, so we can see whether the system says "I don't know".

<!-- BEGIN generated: qa_counts -->
| Category | What a question needs | Dev | Test (sealed) |
|---|---|---|---|
| `answerable` | SP 800-53 supports an answer; each lists 1–2 gold base controls | 30 | 30 |
| `other_framework` | Needs another framework's text (PCI DSS, ISO 27001, SOC 2, ...) | 4 | 4 |
| `internal_policy` | Needs one organization's own facts ("Who is our CISO?") | 4 | 4 |
| `legal` | Needs a legal conclusion | 4 | 4 |
| `trivia` | General knowledge unrelated to the catalog | 4 | 4 |
| `security_specifics` | Security facts the catalog doesn't hold (a CVE's score, product steps) | 4 | 4 |
| **all** | 71 distinct gold controls from 20 families | 50 | 50 |
<!-- END generated: qa_counts -->

The agent drafted every question and its gold controls from the catalog's titles and text, without running retrieval, so the labels couldn't copy what the system finds. Jude reviewed every label in `data/eval/qa_review.md` and kept them all, before the first answer was generated. His label is final.

The split is computed fresh every time the file is loaded: 50/50 within each category, in an order fixed by a hash of the seed and the question ID. Loading the test half raises an error unless you set `CONTROLFINDER_UNSEAL_TEST=1`. Nothing in this phase unsealed it.

### `make generate`, step by step

1. **The rules came first.** The prompt, the citation rules, the judge's rubric and every metric's definition went into `DECISIONS.md` before the first answer was generated. The prompts' sha256 hashes are saved in the results, so a later edit would show.
2. **Retrieve.** Embed each dev question with bge-small and run exact dense search on strategy C, the Phase 3 pick. Keep the 10 best distinct controls. In C every enhancement is its own chunk, so each control comes with whichever of its chunks ranked highest: its own text, or one of its enhancements'.
3. **Answer.** Put those 10 chunks into one prompt, each wrapped in `<control id="AC-2(3)">…</control>`. Claude Sonnet 5.5 must answer only from them in at most 150 words, cite every claim like `[AC-2]`, and reply with exactly `INSUFFICIENT_EVIDENCE` if the controls don't contain the answer.
4. **Check the citations, in code.** Find every bracketed ID and normalize it. A citation is valid only if that exact control was one of the 10. A gold control counts as cited if a valid citation is the control itself or one of its enhancements. An answer is correct if every citation is valid and at least one gold control is cited.
5. **Judge.** GPT-5.6 Sol, from a different model family, reads the same 10 controls, the question and the answer, and scores faithfulness from 1 to 5 against a fixed rubric. Refusals aren't judged. Its full replies are saved.
6. **Probe the judge.** Append one made-up sentence to each answer and judge it again (see below).
7. **Score.** Compute every metric with a 95% interval from 1,000 bootstrap resamples of the questions.

### Why the model runs as a Cursor agent

Jude chose to run the models through Cursor instead of buying API keys. The Cursor Python SDK can start an agent from a script, but an agent is more than a model: it can read files, run commands and follow a folder's rules. For a fair test, the model must see only our prompt. So every call:

- creates the agent with no tools (`tools=[]`);
- runs it in a new, empty temporary folder, so there's no repo to read and no project rules to load;
- fails if the agent makes any tool call anyway.

Calls are cached by provider, model and prompt. A rerun replays the saved replies instead of calling the model, so every number reproduces and only new prompts cost anything. Moving to a direct API later means writing one provider function and pointing `PROVIDER` in `llm.py` at it.

The price of this choice: Cursor wraps our prompt in its own agent instructions, so the token counts include text we didn't write. And both models ran at Cursor's default settings rather than settings we chose.

## Results on dev

<!-- BEGIN generated: generation_metrics -->
| Metric | What it measures | Value [95% CI] | Resamples where undefined |
|---|---|---|---|
| `abstention_precision` | Of the refusals, the share that were unanswerable questions | 0.714 [0.542, 0.864] | 0 |
| `abstention_recall` | Of the unanswerable questions, the share refused | 1.000 [1.000, 1.000] | 0 |
| `abstention_f1` | The two above combined (harmonic mean) | 0.833 [0.703, 0.927] | 0 |
| `answer_rate` | Of all questions, the share answered | 0.440 [0.300, 0.580] | 0 |
| `citation_precision` | Of all citations in answers, the share whose exact control was in the context | 1.000 [1.000, 1.000] | 0 |
| `gold_citation_recall` | Per answered answerable question, the share of its gold controls validly cited, averaged | 0.864 [0.722, 0.974] | 0 |
| `answer_accuracy` | Of answered answerable questions, the share with every citation valid and at least one gold | 0.909 [0.773, 1.000] | 0 |
| `faithfulness` | The judge's mean score from 1 to 5, over answered questions | 5.000 [5.000, 5.000] | 0 |
| `gold_in_context` | Of answerable questions, the share with a gold control among the 10 retrieved | 0.900 [0.788, 1.000] | 0 |
<!-- END generated: generation_metrics -->

Refusing counts as the "positive" prediction here, because refusing is what the system should do with an unanswerable question:

<!-- BEGIN generated: abstention_matrix -->
| Dev questions | Refused | Answered |
|---|---|---|
| Unanswerable | 20 (TP) | 0 (FN) |
| Answerable | 8 (FP) | 22 (TN) |
<!-- END generated: abstention_matrix -->

TP means it refused an unanswerable question (right). FN would mean it answered one anyway, the dangerous mistake, because the answer would be made up. FP means it refused an answerable question (safe, but unhelpful). TN means it answered an answerable question.

<!-- BEGIN generated: abstention_by_category -->
| Category | Dev questions | Refused |
|---|---|---|
| `answerable` | 30 | 8 |
| `other_framework` | 4 | 4 |
| `internal_policy` | 4 | 4 |
| `legal` | 4 | 4 |
| `trivia` | 4 | 4 |
| `security_specifics` | 4 | 4 |
<!-- END generated: abstention_by_category -->

### Why it refused answerable questions

<!-- BEGIN generated: gold_coverage -->
| What the 10 retrieved chunks held | Answerable questions | Refused | Answered | Answered correctly |
|---|---|---|---|---|
| A gold control's own chunk | 14 | 0 | 14 | 14 |
| Only chunks of a gold control's enhancements | 13 | 7 | 6 | 6 |
| No gold control at all | 3 | 1 | 2 | 0 |
<!-- END generated: gold_coverage -->

<!-- BEGIN generated: wrong_refusals -->
| ID | Answerable question the pipeline refused | Gold | Gold controls' chunks among the 10 |
|---|---|---|---|
| q005 | Can employees use their personal phones to read work email? | AC-19, AC-20 | AC-19(4), AC-20(5) |
| q011 | How long should we keep audit logs? | AU-11 | AU-11(1) |
| q017 | What does CM-8 expect our asset inventory to include? | CM-8 | CM-8(2) |
| q025 | Should we require MFA for employees? | IA-2 | IA-2(5) |
| q036 | Do our servers need backup power? | PE-11 | none |
| q042 | What background checks should we run on new hires? | PS-3 | PS-3(3) |
| q046 | How often should we scan our systems for vulnerabilities? | RA-5 | RA-5(2) |
| q057 | What anti-malware protection do we need? | SI-3 | SI-3(4) |
<!-- END generated: wrong_refusals -->

Strategy C gives each enhancement its own chunk, and the retriever represents each control by whichever of its chunks ranked highest. For "Should we require MFA for employees?", retrieval found IA-2, the right control, but represented it by IA-2(5) Individual Authentication with Group Authentication. The model saw that text, not IA-2's own, and correctly said it wasn't enough. "How long should we keep audit logs?" is the same story: AU-11 Audit Record Retention arrived as AU-11(1) Long-term Retrieval Capability.

So `gold_in_context` (0.900) overstates what the model actually saw. It counts IA-2 as in the context when only IA-2(5)'s text was. It's the same problem Phase 3 found, where the reranker judged SI-4 System Monitoring by SI-4(25).

The one real retrieval miss is "Do our servers need backup power?" PE-11 Emergency Power wasn't retrieved. The first result was CP-9(6) Redundant Secondary System, under CP-9 System Backup. "Backup" has two meanings, and the embedding followed the wrong one.

The likely fix is in retrieval, not in the prompt: whenever an enhancement is retrieved, also give the model its base control's text. This is often called parent-document or "small-to-big" retrieval. It's a candidate for Phase 5, where it would need its own decision row before it's measured.

### The two wrong answers: faithful to the wrong controls

<!-- BEGIN generated: incorrect_answers -->
| ID | Question | Gold | Gold controls' chunks among the 10 | Cited instead |
|---|---|---|---|---|
| q015 | How should we track security findings until they're fixed? | CA-5, PM-4 | none | SI-2, SA-15(2), IR-5 |
| q041 | Can we use real customer data in our test environment? | PM-25 | none | SA-3(2), SA-15(12), CM-4(1) |
<!-- END generated: incorrect_answers -->

- **q015, tracking security findings.** The gold controls, CA-5 Plan of Action and Milestones and PM-4 Plan of Action and Milestones Process, weren't retrieved. The model built its answer from SI-2 Flaw Remediation, SA-15(2) Security and Privacy Tracking Tools and IR-5 Incident Monitoring. The judge gave it a 5, correctly, because every claim is in those controls. It's faithful and still wrong, because the context was wrong.
- **q041, real customer data in testing.** The gold control, PM-25 Minimization of Personally Identifiable Information Used in Testing, Training, and Research, wasn't retrieved. The model answered from SA-3(2) Use of Live or Operational Data and SA-15(12) Minimize Personally Identifiable Information, which looks like a good answer the label didn't list. The label stays: editing labels after seeing the system's answers would tilt the test toward the system. It's reported here instead.

### Can the judge tell a bad answer from a good one?

All 22 answers got a 5. That could mean the answers are faithful, or that the judge says 5 to everything, and the two look the same. So after the first run we added a check, labelled in `DECISIONS.md` as added after seeing results. Each answer gets one extra sentence, "This must be repeated at least every 47 days [X]", where X is one of the answer's own valid citations, and the judge scores it again. The script skips any answer whose controls mention "47 days", so the planted claim is always unsupported, and a working judge must mark it down.

<!-- BEGIN generated: judge_scores -->
| Judge score | 1 | 2 | 3 | 4 | 5 | unparsed |
|---|---|---|---|---|---|---|
| Answers as generated | 0 | 0 | 0 | 0 | 22 | 0 |
| The same answers plus one planted claim (22 probed) | 0 | 0 | 14 | 8 | 0 | 0 |
<!-- END generated: judge_scores -->

It marked all 22 down, and its reasons name the planted sentence. For q001 it wrote: "The main claims are supported, but the requirement to repeat this every 47 days is absent from the controls." The probe is extra evidence about the judge; it changes none of the metrics above.

What it doesn't show: it tests one kind of error, an invented detail with a real citation. A judge could still miss subtler ones, like a claim that bends what a control says.

### What it costs

<!-- BEGIN generated: generation_costs -->
| Cost | p50 / p95 (ms), or mean |
|---|---|
| Retrieval: embed the question, exact dense search | 11 / 12 |
| Generation: one Cursor agent call | 9,548 / 13,665 |
| Per question: retrieval + generation | 9,559 / 13,675 |
| Judge call (evaluation only, not part of the pipeline) | 8,449 / 12,759 |
| Mean input tokens per generation call | 5,406 |
| Mean output tokens per generation call | 279 |
<!-- END generated: generation_costs -->

Each question takes one model call. The judge adds a second, but only during evaluation; a user never waits for it. The input tokens include Cursor's own agent instructions, so a direct API call with the same prompt would likely use fewer.

## Concepts

### Why citation checks belong in code, not in an LLM

"Is AC-2(3) one of the 10 controls we gave the model?" has an exact answer. Code answers it the same way every time, for free, in microseconds, and a test can prove it right. An LLM asked the same thing might miss a citation, invent one, or answer differently on a rerun, and then you'd need something to check the checker.

So the rule is: if a check can be written as code, write it as code. Save the LLM for questions code can't answer, like "does this sentence say what that control says?". That's faithfulness, so it goes to the judge.

The split matters both ways. Code found that no answer cited a control it wasn't given (citation precision 1.000). But code can't tell whether [SI-2] actually supports the sentence it's attached to. Only the judge reads for meaning.

### What goes wrong with LLM judges, and how each fix works

- **Position bias.** Asked to compare two answers, a judge tends to prefer one position, often the first. The fix is to score one answer at a time against a fixed rubric, so there's no order to favor, which is what we do. When you must compare two, run both orders and keep only the verdicts that agree. One thing we didn't test: inside our prompt the 10 controls come in retrieval order, and a judge might pay more attention to the first few.
- **Verbosity bias.** Judges tend to score longer answers higher. The fix is to say what not to reward and tie every score to a concrete rubric. Our prompt says "don't reward length: a short answer whose claims are all supported deserves a 5", and answers are capped at 150 words, which narrows how much lengths can differ. We didn't measure whether length still sways the scores.
- **Self-preference.** A model tends to rate text from its own model, or its own family, higher. The fix is a judge from a different family: our answers come from Claude Sonnet 5.5 and the judge is GPT-5.6 Sol.
- **Leniency, a judge that says yes to everything.** The fix is a probe with answers you know are bad, like our planted claim. If the judge can't mark down a known-bad answer, its 5s mean nothing.
- **Always keep the judge's raw replies.** Ours are in the results, so anyone can read why it gave each score, and the score can be re-parsed. None failed to parse.

### Faithfulness vs correctness

- **Faithful** means every claim in the answer comes from the context it was given.
- **Correct** means the answer is right for the question.

They can come apart. q015 was faithful (scored 5) but wrong, because retrieval brought the wrong controls and the model answered faithfully from them. The opposite can happen too: an answer that's right from the model's own memory but not supported by the context. We forbid that, because the user can't check it against the cited controls.

Faithfulness tells you the generator behaved; correctness also needs the retriever to have brought the right context. That's why we measure both, with `gold_in_context` beside them. Our correctness check is a stand-in: it compares citations with Jude's gold labels. Citing a gold control doesn't guarantee the answer is right, and q041 shows a right answer can cite controls the label doesn't list.

### Refusing is a yes/no prediction

Treat each refusal as the system predicting "this can't be answered". **Precision** asks: when it refused, how often was it right? **Recall** asks: of the questions it should have refused, how many did it? Here recall is 1.000 and precision 0.714.

Which mistake is worse depends on the product. For a compliance tool, a made-up answer is worse than a refusal: a refusal sends you to read the controls, while a confident wrong answer might end up in an audit. So recall matters most here. But 8 refusals out of 30 answerable questions is still a real cost, because people stop using a tool that keeps saying "I don't know".

**Undefined isn't zero.** If the system never refused, precision would be 0 divided by 0. We record that as `null`, not 0 or 1, and the bootstrap counts the resamples where a metric was undefined (none were, here).

### Why some intervals are [1.000, 1.000]

Abstention recall was 20 out of 20. Every bootstrap resample is drawn from those same 20 successes, so every resample also scores 1.000 and the interval shrinks to a point. That doesn't mean the true rate is surely 100%. It means this method can't show uncertainty when there are no failures to resample. With only 20 unanswerable dev questions, a small miss rate could easily produce zero misses. A rule of thumb, the "rule of three", says that with 0 failures in n tries the true failure rate could still be up to about 3/n. The same caution applies to citation precision and faithfulness.

## Decisions

Each of these has a row in `DECISIONS.md`.

- **The question set:** 60 answerable and 40 unanswerable questions, 8 of each unanswerable kind. The agent drafted them, and Jude reviewed the labels and kept them before the first answer. They're split 50/50 within each category, with a sealed test half.
- **The models run as Cursor SDK local agents:** text only, in an empty folder, with every call cached and the cache committed.
- **The generator is Claude Sonnet 5.5 and the judge is GPT-5.6 Sol,** from different families, both at Cursor's default settings.
- **The context is the top 10 controls** from the Phase 3 production retriever, each represented by its best-ranked chunk.
- **The prompt, the citation rules and the refusal word were fixed before the first run,** and the prompts' hashes are in the results.
- **Citations are checked in code.** The judge scores faithfulness only. Refusals aren't judged, and unparsed replies would be counted, not dropped.
- **Intervals come from 1,000 bootstrap resamples of questions.** Latency is wall-clock time, and the judge is reported separately.
- **The judge probe was added after the first run,** and is labelled as such.

## Gotchas we hit

1. **Exact search needs an autocommit connection.** The first smoke run stopped with "needs an autocommit connection, so that SET LOCAL ends with each query". That's the guard Phase 2 added for exact search. `make generate` now opens its connection the way `make baselines` does.
2. **An agent isn't a plain model call.** By default a Cursor agent can read files, use tools and load project rules, which would leak the repo into the test. That's why it gets no tools, an empty folder and the tool-call check. In the smoke test, when a prompt tempted it to list files, Sonnet wrote fake tool-call markup as plain text. Nothing ran, but it's a reminder to check what comes back.
3. **"Gold in context" overstated what the model saw.** It counted the base control while the model saw only an enhancement's text. Each answerable question's `gold_coverage` field now records which one it was.
4. **A perfect score needs a second look.** A judge giving all 5s is a result to doubt until a known-bad input shows it can give less.
5. **Labels that look wrong after the run stay as they are.** q041's answer looks reasonable, but editing labels after seeing answers would let the system grade its own homework.
6. **Words with two meanings trip up retrieval.** "Backup power" came back as data backups.

## Interview questions

**1. Walk me through how your system answers a question.**
It embeds the question with bge-small and runs exact dense search in Postgres with pgvector, keeping the top 10 controls. They go into one prompt, each tagged with its ID, and the model must answer only from them, cite every claim like [AC-2], or reply INSUFFICIENT_EVIDENCE. Code checks every citation against the 10 IDs, and during evaluation a judge from another model family scores faithfulness from 1 to 5. On 50 dev questions it answered 22. Every citation was valid, 0.909 of the answers were correct, and it never answered an unanswerable question.

**2. How do you evaluate refusals?**
As a classifier where "refused" is the positive class. I wrote 40 unanswerable questions in five kinds, such as other frameworks, legal questions and trivia; 20 are in dev. It refused all 20, so recall is 1.000. It also refused 8 answerable questions, so precision is 0.714 [0.542, 0.864] and F1 is 0.833. The recall interval is [1.000, 1.000] only because a bootstrap can't show uncertainty when there are no failures, so I wouldn't claim it never fails.

**3. Why did it refuse answerable questions?**
Mostly because of retrieval. My chunking gives each enhancement its own chunk, and each control is represented by its best-ranked chunk. When a gold control's own chunk was retrieved, 14 questions, it answered all 14 correctly. When only an enhancement's chunk was, 13 questions, it refused 7. For "Should we require MFA?" it got IA-2(5), which is about group accounts, and correctly said that wasn't enough. The fix I'd test next is giving the model the base control's text whenever an enhancement is retrieved.

**4. Why check citations in code instead of asking an LLM?**
Because "was AC-2(3) in the context?" has an exact answer. Code gets it right every time, for free, and a unit test proves it. An LLM can miss or invent citations and vary between runs, and then you need to check the checker. I use the LLM only for what code can't do: deciding whether a sentence is supported by a control.

**5. How do you know your LLM judge works?**
It gave all 22 answers a 5, which could mean it says 5 to everything. So I planted a made-up claim, "this must be repeated at least every 47 days", with a real citation, in each answer and re-judged. It marked all 22 down, 14 to a 3 and 8 to a 4, and its reasons named the planted claim. It also comes from a different model family than the generator, and I store every raw reply. The limit is that the probe tests one kind of error.

**6. What biases do LLM judges have?**
Position bias: preferring the first or second of two answers. I avoid it by scoring one answer at a time against a rubric, and if I had to compare pairs I'd run both orders. Verbosity bias: preferring longer answers. The rubric says not to reward length and the answers are capped at 150 words. Self-preference: favoring its own family's writing. The generator is Claude and the judge is GPT. And leniency, which the planted-claim probe checks.

**7. What's the difference between faithfulness and correctness?**
Faithfulness asks whether the answer sticks to the context it was given; correctness asks whether it's right. q015 asked how to track security findings. Retrieval missed the gold controls, CA-5 and PM-4, so the model answered from SI-2 Flaw Remediation. The judge gave it a 5, correctly, but it's wrong for the label. A faithful answer can only be as good as the retrieved context.

**8. What does an answer cost?**
9,559 ms at p50 and 13,675 ms at p95 per question, almost all of it the model call; retrieval is 11 ms. A generation call averages 5,406 input tokens and 279 output tokens, and the input includes Cursor's agent instructions on top of my prompt. The judge adds 8,449 ms at p50, but only during evaluation.

## Follow-ups from the quiz

**For q015, the judge gave the answer a 5 but our code marked it incorrect. Can both be right?**
Yes, because they compare the answer against different things. The judge compares it with the 10 controls the model was given and asks whether every claim comes from them. It does: everything is in SI-2, SA-15(2) and IR-5, so it scores 5. The code compares the citations with Jude's gold controls, CA-5 and PM-4, and none of them is cited, because retrieval never brought them back. It's like a student who copies perfectly from the wrong page of the textbook: faithful to the page, wrong for the question. So faithfulness is necessary but not enough, and this answer could only be fixed in retrieval.

**"Should we require MFA for employees?" was refused, although `gold_in_context` says IA-2 was in the context. Why, and is it the model's fault?**
It isn't the model's fault. Strategy C makes every enhancement its own chunk, and the retriever lists each control once, using whichever of its chunks ranked highest. IA-2 came in as the text of IA-2(5) Individual Authentication with Group Authentication, which says nothing about MFA. `gold_in_context` counts the base control, so it said yes, but the model never saw IA-2's own text, and refusing was the honest answer. It's a pattern: when a gold control's own chunk was retrieved, the model answered all 14 of those questions correctly, and when only an enhancement's chunk was, it refused 7 of 13. The fix to test is giving the model the base control's text whenever an enhancement is retrieved. Telling the model to answer anyway would be the wrong fix: it would trade safe refusals for made-up answers.

**The judge gave all 22 answers a 5. Why is that suspicious, and how did we check the judge works?**
A judge that says 5 to everything would produce exactly the same result, so the 5s alone prove nothing. We tested it with answers we knew were bad: each answer got one made-up sentence, "This must be repeated at least every 47 days", with a real citation, and "47 days" appears in none of the contexts. The judge marked all 22 down, 14 to a 3 and 8 to a 4, and its reasons named the planted sentence. It also comes from a different model family than the generator (against self-preference), scores one answer at a time against a fixed rubric (against position bias), is told not to reward length (against verbosity bias), and every raw reply is stored. One gap remains: the judge asks whether each claim is supported by the controls as a group, and the code only checks that each cited control was in the context. So a claim citing [AC-2] that only AC-3 supports would pass both. Nothing here measures whether each citation points to the right control.
