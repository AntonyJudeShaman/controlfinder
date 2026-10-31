"""The reranker's disk cache and reordering, with a fake model in place of the cross-encoder."""

from controlfinder.retrieval import Hit
from controlfinder.retrieval.pipeline import rerank
from controlfinder.retrieval.rerank import MAX_LENGTH, Reranker


class FakeModel:
    """Scores a pair by its text's word count, tokenizes by words, and counts its runs."""

    def __init__(self):
        self.runs = 0

    def predict(self, pairs, batch_size, show_progress_bar):
        self.runs += 1
        return [float(len(text.split())) for _, text in pairs]

    def tokenizer(self, query, text, verbose):
        return {"input_ids": (query + " " + text).split()}


def test_a_rerun_reads_the_scores_and_their_latency_from_disk(tmp_path):
    model = FakeModel()
    first = Reranker(tmp_path / "rerank.jsonl", load=lambda: model).score("q", ["one two", "one"])
    again = Reranker(tmp_path / "rerank.jsonl", load=lambda: model).score("q", ["one two", "one"])
    assert first.scores == [2.0, 1.0]
    assert again == first
    assert model.runs == 1


def test_the_same_texts_in_another_order_are_scored_again(tmp_path):
    model = FakeModel()
    reranker = Reranker(tmp_path / "rerank.jsonl", load=lambda: model)
    reranker.score("q", ["one two", "one"])
    reranker.score("q", ["one", "one two"])
    assert model.runs == 2


def test_counts_pairs_over_the_length_limit(tmp_path):
    longest_that_fits = " ".join(["word"] * (MAX_LENGTH - 1))  # plus the query's word
    scored = Reranker(tmp_path / "rerank.jsonl", load=FakeModel).score("q", [longest_that_fits, longest_that_fits + " x"])
    assert scored.truncated == 1


def test_rerank_sorts_by_score_and_keeps_the_input_order_on_ties(tmp_path):
    hits = [Hit("a", "a", 0.3), Hit("b", "b", 0.2), Hit("c", "c", 0.1)]
    texts = {"a": "x", "b": "x y z", "c": "x"}
    reranked, _ = rerank(Reranker(tmp_path / "rerank.jsonl", load=FakeModel), "q", hits, texts)
    assert reranked == [Hit("b", "b", 3.0), Hit("a", "a", 1.0), Hit("c", "c", 1.0)]
