from tools.layer_c_triple_audit import _log_support_cdf, _score_components


def test_support_cdf_is_monotonic_and_deduplicated():
    cdf = _log_support_cdf([3, 1, 3, 2])
    assert list(cdf) == [1, 2, 3]
    assert cdf[1] < cdf[2] < cdf[3]


def test_composite_score_boundaries_and_components():
    low = _score_components(support_percentile=0.1, jaccard=0.1, cooccur=1)
    high = _score_components(support_percentile=1.0, jaccard=1.0, cooccur=3)

    assert low[1] == "low"
    assert high[1] == "high"
    assert 0 <= low[0] <= high[0] <= 1
    assert high[2]["closure_bonus"] == 0.1
    assert high[3] == {"support": 1.0, "jaccard": 1.0, "path_closure": 0.1}
