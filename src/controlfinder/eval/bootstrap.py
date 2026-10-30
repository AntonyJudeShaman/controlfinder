"""Cluster bootstrap confidence intervals: resample subcategories, not queries.

All queries of one subcategory share its gold set, so they tend to succeed or fail together.
Resampling single queries would count them as independent evidence and make the intervals too
narrow. Each resample here draws subcategories with replacement and keeps all of a drawn
subcategory's queries. To compare two systems, the paired version resamples their per-query
differences, so both are always judged on the same draw.
"""

import random
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
