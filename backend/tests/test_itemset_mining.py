"""窗口 F-3：频繁技术组合挖掘的回归。

重点不是「能挖出项集」，而是三条会直接影响推演正确性的性质：
闭包去冗余、确定性、以及小事务不被凭空丢弃。
"""

from __future__ import annotations

from app.modules.discovery.itemsets import (
    assign_transactions,
    mine_closed_itemsets,
)


def test_mines_frequent_itemsets_within_size_bounds() -> None:
    transactions = {
        1: {10, 20, 30},
        2: {10, 20, 30},
        3: {10, 20, 30, 40},
        4: {10, 20},
        5: {50, 60},
    }
    result = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=5)

    assert (10, 20, 30) in result.itemsets
    assert result.itemsets[(10, 20, 30)] == {1, 2, 3}
    # {50,60} 只出现 1 次，低于支持度下限。
    assert (50, 60) not in result.itemsets
    assert all(2 <= len(key) <= 5 for key in result.itemsets)


def test_closure_drops_subsets_with_identical_support() -> None:
    """{A,B} 与 {A,B,C} 支持度相同时只保留后者，否则同一批 JD 会被切成多个候选。"""
    transactions = {1: {10, 20, 30}, 2: {10, 20, 30}, 3: {10, 20, 30}}
    result = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=5)

    assert (10, 20, 30) in result.itemsets
    for redundant in ((10, 20), (10, 30), (20, 30)):
        assert redundant not in result.itemsets


def test_keeps_subset_when_support_actually_differs() -> None:
    """支持度不同就不是冗余：{A,B} 比 {A,B,C} 多覆盖一份 JD，必须各自成候选。"""
    transactions = {1: {10, 20, 30}, 2: {10, 20, 30}, 3: {10, 20}}
    result = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=5)

    assert result.itemsets[(10, 20)] == {1, 2, 3}
    assert result.itemsets[(10, 20, 30)] == {1, 2}


def test_max_size_caps_combination_width() -> None:
    transactions = {index: {10, 20, 30, 40, 50, 60} for index in range(4)}
    result = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=3)

    assert result.itemsets
    assert max(len(key) for key in result.itemsets) == 3


def test_mining_is_deterministic() -> None:
    transactions = {
        1: {10, 20, 30},
        2: {20, 30, 40},
        3: {10, 20, 30, 40},
        4: {10, 30},
        5: {20, 40},
    }
    first = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=4)
    second = mine_closed_itemsets(dict(reversed(list(transactions.items()))), min_support=2,
                                  min_size=2, max_size=4)
    assert first.itemsets == second.itemsets
    assert list(first.itemsets) == list(second.itemsets)


def test_small_transactions_fall_back_to_their_own_technology_set() -> None:
    """技术数不足以成组合的 JD 不能凭空消失，否则证据侧会少掉一批岗位。"""
    transactions = {
        1: {10, 20, 30},
        2: {10, 20, 30},
        3: {90},
    }
    result = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=5)
    assigned = assign_transactions(transactions, result.itemsets, min_size=2)

    assert (90,) in assigned
    assert assigned[(90,)] == {3}
    assert 3 not in {tid for key, ids in assigned.items() if len(key) > 1 for tid in ids}


def test_stats_report_size_distribution_and_truncation() -> None:
    transactions = {index: {10, 20, 30} for index in range(3)}
    stats = mine_closed_itemsets(transactions, min_support=2, min_size=2, max_size=5).stats

    assert stats["itemset_count"] == 1
    assert stats["size_histogram"] == {"3": 1}
    assert stats["truncated_levels"] == []
