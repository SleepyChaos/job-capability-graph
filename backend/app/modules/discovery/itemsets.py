"""频繁技术组合挖掘：把推演候选的粒度从「技术对」提到「技术组合」（窗口 F-3）。

**为什么必须换粒度。** 候选与既有岗位的距离用非对称覆盖率
`|候选∩岗位| / |候选|` 衡量。候选是技术对时分母恒为 2，这个测量只能取
0、0.5、1.0 三个值，`existing_role`(≥0.75) / `role_evolution`(≥0.45) /
`potential_new_role` 三档退化成「全覆盖 / 覆盖一半 / 不覆盖」，阈值形同虚设——
实测 100 个候选里 91 个覆盖率恰好等于 1.0。分辨率不足以判别新岗位。

把候选扩到 3–5 个技术后，分母变成 3–5，覆盖率取值随之细化，两个阈值才真正分档。
组合本身也更接近「一个岗位要求的能力集」，而不是任意两个技术的共现。

**为什么用闭项集。** 频繁项集天然冗余：若 {A,B,C} 在 20 份 JD 中出现，
它的全部子集也至少出现 20 次，直接枚举会产出大量「同一批 JD 的不同切片」。
闭项集（没有任何超集与之支持度相同）只保留每个支持度等价类里最大的那个，
既去冗余，又保证不丢失任何支持度信息。

**确定性。** 逐层 Apriori，每层内按 (技术 id 元组) 排序后处理，同输入必然同输出；
每层候选数设上限防止组合爆炸，截断时按支持度降序保留，截断事实写进结果供审计。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

ITEMSET_ALGORITHM_VERSION = "closed_frequent_itemset_apriori_v1"


@dataclass(frozen=True)
class ItemsetMiningResult:
    """挖掘结果。`itemsets` 的键为排序后的技术 id 元组，值为支持该组合的事务 id 集合。"""

    itemsets: dict[tuple[int, ...], set[int]]
    truncated_levels: tuple[int, ...]
    max_level_reached: int

    @property
    def stats(self) -> dict:
        sizes: dict[int, int] = defaultdict(int)
        for key in self.itemsets:
            sizes[len(key)] += 1
        return {
            "algorithm_version": ITEMSET_ALGORITHM_VERSION,
            "itemset_count": len(self.itemsets),
            "size_histogram": {str(size): count for size, count in sorted(sizes.items())},
            "truncated_levels": list(self.truncated_levels),
            "max_level_reached": self.max_level_reached,
        }


def mine_closed_itemsets(
    transactions: dict[int, set[int]],
    *,
    min_support: int,
    min_size: int = 2,
    max_size: int = 5,
    max_candidates_per_level: int = 20000,
) -> ItemsetMiningResult:
    """从「事务 → 项集合」中挖掘频繁闭项集。

    参数
    ----
    transactions:
        事务 id → 该事务包含的项（这里是一份 JD 及其 L3 技术节点集合）。
    min_support:
        支持度下限，按**事务条数**计（绝对值，不是比例），低于该值的组合丢弃。
    min_size / max_size:
        产出组合的大小区间。小于 `min_size` 的事务由调用方决定如何兜底，
        本函数不为它们编造组合。
    max_candidates_per_level:
        每层候选上限，防止稠密数据上的组合爆炸；触发截断时按支持度降序保留。
    """
    if min_support < 1:
        raise ValueError("min_support 必须 ≥ 1")
    if min_size < 1 or max_size < min_size:
        raise ValueError("min_size/max_size 区间非法")

    # 第 1 层：频繁单项。先剪掉低频项能大幅压缩后续所有层。
    support_1: dict[int, set[int]] = defaultdict(set)
    for transaction_id, items in transactions.items():
        for item in items:
            support_1[item].add(transaction_id)
    current: dict[tuple[int, ...], set[int]] = {
        (item,): ids for item, ids in support_1.items() if len(ids) >= min_support
    }

    levels: list[dict[tuple[int, ...], set[int]]] = [current]
    truncated: list[int] = []
    level = 1
    while current and level < max_size:
        nxt: dict[tuple[int, ...], set[int]] = {}
        keys = sorted(current)
        for index, left in enumerate(keys):
            # Apriori 连接：只连接前 k-1 项相同的两个 k 项集，保证每个候选只生成一次。
            prefix = left[:-1]
            for right in keys[index + 1 :]:
                if right[:-1] != prefix:
                    break
                merged = left + (right[-1],)
                shared = current[left] & current[right]
                if len(shared) >= min_support:
                    nxt[merged] = shared
        if len(nxt) > max_candidates_per_level:
            truncated.append(level + 1)
            kept = sorted(nxt.items(), key=lambda item: (-len(item[1]), item[0]))
            nxt = dict(kept[:max_candidates_per_level])
        if not nxt:
            break
        levels.append(nxt)
        current = nxt
        level += 1

    # 闭包过滤：丢掉与某个直接超集支持度相同的项集。
    # 支持度沿超集单调不增，因此只需与下一层的超集比较即可。
    closed: dict[tuple[int, ...], set[int]] = {}
    for depth, level_sets in enumerate(levels):
        if depth + 1 < len(levels):
            larger = levels[depth + 1]
            supersets_by_subset: dict[tuple[int, ...], list[int]] = defaultdict(list)
            for key, ids in larger.items():
                for dropped in range(len(key)):
                    subset = key[:dropped] + key[dropped + 1 :]
                    supersets_by_subset[subset].append(len(ids))
        else:
            supersets_by_subset = {}
        for key, ids in level_sets.items():
            if len(key) < min_size:
                continue
            if any(count == len(ids) for count in supersets_by_subset.get(key, ())):
                continue
            closed[key] = ids
    return ItemsetMiningResult(
        itemsets=dict(sorted(closed.items())),
        truncated_levels=tuple(truncated),
        max_level_reached=len(levels),
    )


def assign_transactions(
    transactions: dict[int, set[int]],
    itemsets: dict[tuple[int, ...], set[int]],
    *,
    min_size: int,
) -> dict[tuple[int, ...], set[int]]:
    """把每个事务归到它支持的组合上，并为不被任何组合覆盖的事务保留兜底键。

    技术数少于 `min_size` 的 JD 挖不出合法组合，若直接丢弃就会在证据侧凭空少掉
    一批岗位。这类 JD 用其自身完整技术集合作为键——粒度上不如挖掘出的组合，
    但至少不伪造、也不丢失。
    """
    result: dict[tuple[int, ...], set[int]] = {
        key: set(ids) for key, ids in itemsets.items() if ids
    }
    covered = {tid for ids in itemsets.values() for tid in ids}
    for transaction_id, items in transactions.items():
        if transaction_id in covered or not items:
            continue
        result.setdefault(tuple(sorted(items)), set()).add(transaction_id)
    return dict(sorted(result.items()))
