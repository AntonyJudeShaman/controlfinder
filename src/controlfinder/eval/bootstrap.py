"""Cluster bootstrap confidence intervals: resample subcategories, not queries.

All queries of one subcategory share its gold set, so they tend to succeed or fail together.
Resampling single queries would count them as independent evidence and make the intervals too
narrow. Each resample here draws subcategories with replacement and keeps all of a drawn
subcategory's queries. To compare two systems, the paired version resamples their per-query
differences, so both are always judged on the same draw.

QA questions share nothing, so each is its own cluster, and `resample_ci` resamples them
directly. It takes any statistic of a list of questions, which also covers ratios like F1 that
aren't a mean of per-question values. `paired_resample_ci` does the same for the difference
between two systems answering the same questions.
"""

import random
from collections.abc import Callable
from statistics import quantiles

N_RESAMPLES = 1000
SEED = 20261023


def cluster_ci(values: dict[str, list[float]], n_resamples: int = N_RESAMPLES, seed: int = SEED) -> dict:
    """Mean over all queries, and its 95% percentile interval. `values` maps cluster -> query values."""
    clusters = [(sum(v), len(v)) for v in values.values()]
    rng = random.Random(seed)
    means = []
    for _ in range(n_resamples):
        draw = rng.choices(clusters, k=len(clusters))
        means.append(sum(total for total, _ in draw) / sum(n for _, n in draw))
    cuts = quantiles(means, n=40, method="inclusive")  # cut points at 2.5%, 5%, ..., 97.5%
    return {"mean": sum(total for total, _ in clusters) / sum(n for _, n in clusters), "ci95": [cuts[0], cuts[-1]]}


def paired_cluster_ci(a: dict[str, list[float]], b: dict[str, list[float]], **kwargs) -> dict:
    """Mean of a - b over the same queries, with its 95% cluster-bootstrap interval."""
    return cluster_ci({c: [x - y for x, y in zip(a[c], b[c], strict=True)] for c in a}, **kwargs)


def resample_ci(items: list, statistic: Callable[[list], float | None], n_resamples: int = N_RESAMPLES,
                seed: int = SEED) -> dict:
    """`statistic(items)` and its 95% percentile interval from resampling the items.

    A statistic can be undefined (None), like precision with nothing predicted. Resamples where
    it is are left out of the interval and counted, and an undefined value gets no interval.
    """
    rng = random.Random(seed)
    draws = [statistic(rng.choices(items, k=len(items))) for _ in range(n_resamples)]
    return _interval(statistic(items), draws)


def paired_resample_ci(a: list, b: list, statistic: Callable[[list], float | None],
                       n_resamples: int = N_RESAMPLES, seed: int = SEED) -> dict:
    """`statistic(a) - statistic(b)`, where a[i] and b[i] are two systems' rows for the same question.

    Each resample draws question positions and keeps both systems' rows for them, so the two are
    always compared on the same questions.
    """
    if len(a) != len(b):
        raise ValueError("a and b must hold the same questions, in the same order")

    def difference(positions) -> float | None:
        x, y = statistic([a[i] for i in positions]), statistic([b[i] for i in positions])
        return None if x is None or y is None else x - y

    rng = random.Random(seed)
    draws = [difference(rng.choices(range(len(a)), k=len(a))) for _ in range(n_resamples)]
    return _interval(difference(range(len(a))), draws)


def _interval(value: float | None, draws: list[float | None]) -> dict:
    defined = [d for d in draws if d is not None]
    ci95 = None
    if value is not None and len(defined) > 1:
        cuts = quantiles(defined, n=40, method="inclusive")
        ci95 = [cuts[0], cuts[-1]]
    return {"value": value, "ci95": ci95, "undefined_resamples": len(draws) - len(defined)}
