"""Cluster bootstrap behavior on toy data with known answers."""

import pytest

from controlfinder.eval.bootstrap import cluster_ci, paired_cluster_ci


def width(ci: dict) -> float:
    return ci["ci95"][1] - ci["ci95"][0]


def test_constant_values_give_a_zero_width_interval():
    ci = cluster_ci({"a": [0.5, 0.5], "b": [0.5]})
    assert ci["mean"] == 0.5
    assert ci["ci95"] == [pytest.approx(0.5), pytest.approx(0.5)]


def test_mean_is_over_queries_not_clusters():
    assert cluster_ci({"a": [1.0, 1.0, 1.0], "b": [0.0]})["mean"] == 0.75


def test_same_seed_same_interval():
    values = {str(i): [i % 3 / 2, (i + 1) % 2] for i in range(30)}
    assert cluster_ci(values) == cluster_ci(values)


def test_correlated_queries_widen_the_interval():
    # 20 subcategories whose 10 queries all succeed or all fail together.
    clustered = {str(i): [float(i % 2)] * 10 for i in range(20)}
    # The same 200 values, treated as if every query were independent.
    independent = {f"{c}/{j}": [v] for c, values in clustered.items() for j, v in enumerate(values)}
    assert width(cluster_ci(clustered)) > 2 * width(cluster_ci(independent))


def test_paired_difference():
    a = {"x": [0.6, 0.8], "y": [0.4]}
    b = {"x": [0.5, 0.7], "y": [0.3]}
    ci = paired_cluster_ci(a, b)
    assert ci["mean"] == pytest.approx(0.1)
    assert ci["ci95"] == [pytest.approx(0.1), pytest.approx(0.1)]
    assert paired_cluster_ci(a, a)["ci95"] == [0, 0]


def test_paired_needs_the_same_queries():
    with pytest.raises(ValueError):
        paired_cluster_ci({"x": [0.1, 0.2]}, {"x": [0.1]})
