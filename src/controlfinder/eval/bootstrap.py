"""Cluster bootstrap confidence intervals: resample subcategories, not queries.

All queries of one subcategory share its gold set, so they tend to succeed or fail together.
Resampling single queries would count them as independent evidence and make the intervals too
narrow. Each resample here draws subcategories with replacement and keeps all of a drawn
subcategory's queries. To compare two systems, the paired version resamples their per-query
differences, so both are always judged on the same draw.

QA questions share nothing, so each is its own cluster, and `resample_ci` resamples them
directly. It takes any statistic of a list of questions, which also covers ratios like F1 that
aren't a mean of per-question values.
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
    defined = [d for d in draws if d is not None]
    value, ci95 = statistic(items), None
    if value is not None and len(defined) > 1:
        cuts = quantiles(defined, n=40, method="inclusive")
        ci95 = [cuts[0], cuts[-1]]
    return {"value": value, "ci95": ci95, "undefined_resamples": n_resamples - len(defined)}
