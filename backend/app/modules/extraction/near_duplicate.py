"""SimHash 近重复检测（后端设计 §6.2 第 2 条）。

用于识别模板化转载与改写近重复：
- 64 位 SimHash，字符 n-gram 特征；
- 4 段 × 16 位分桶（banding）生成候选对，避免全量两两比较；
- 汉明距离 <= SIMHASH_MAX_DISTANCE 判定为近重复；
- 并查集聚合成簇，簇内选择最早出现版本作为代表文档。

纯函数实现，便于单元测试与后续替换为 MinHash/向量方案。
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

HASH_BITS = 64
NGRAM_SIZE = 4
BAND_COUNT = 4
BAND_BITS = HASH_BITS // BAND_COUNT
SIMHASH_MAX_DISTANCE = 6
MAX_FEATURES = 256


def _token_hash(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _normalized_text(text: str) -> str:
    return "".join(ch for ch in text.casefold() if not ch.isspace())


def simhash_text(
    text: str,
    *,
    hash_bits: int = HASH_BITS,
    ngram: int = NGRAM_SIZE,
    max_features: int = MAX_FEATURES,
) -> int:
    normalized = _normalized_text(text)
    if not normalized:
        return 0
    weights = [0] * hash_bits
    if len(normalized) < ngram:
        tokens = [normalized]
    else:
        total = len(normalized) - ngram + 1
        stride = max(1, total // max_features)
        tokens = [
            normalized[idx : idx + ngram] for idx in range(0, total, stride)
        ][:max_features]
    for token in tokens:
        token_value = _token_hash(token)
        for bit in range(hash_bits):
            if token_value >> bit & 1:
                weights[bit] += 1
            else:
                weights[bit] -= 1
    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(left: int, right: int) -> int:
    return bin(left ^ right).count("1")


def hamming_similarity(left: int, right: int, *, hash_bits: int = HASH_BITS) -> float:
    return 1.0 - hamming_distance(left, right) / hash_bits


def near_duplicate_clusters(
    items: list[tuple[int, str]], *, max_distance: int = SIMHASH_MAX_DISTANCE
) -> list[list[tuple[int, float]]]:
    """输入 (key, text)，输出近重复簇；每簇为 [(key, similarity_to_representative)]。

    只返回成员 >= 2 的簇；代表为簇内最先传入的 key（调用方可自行重排）。
    """
    fingerprints = [(key, simhash_text(text)) for key, text in items]
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (_key, fingerprint) in enumerate(fingerprints):
        for band in range(BAND_COUNT):
            band_value = (fingerprint >> (band * BAND_BITS)) & ((1 << BAND_BITS) - 1)
            buckets[(band, band_value)].append(index)
    candidates: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        for i_pos, i in enumerate(members):
            for j in members[i_pos + 1 :]:
                candidates.add((min(i, j), max(i, j)))

    parent = list(range(len(fingerprints)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    for i, j in candidates:
        if hamming_distance(fingerprints[i][1], fingerprints[j][1]) <= max_distance:
            union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(fingerprints)):
        groups[find(index)].append(index)
    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda index: fingerprints[index][0])
        representative_index = members[0]
        representative_fp = fingerprints[representative_index][1]
        clusters.append(
            [
                (
                    fingerprints[index][0],
                    round(hamming_similarity(representative_fp, fingerprints[index][1]), 4),
                )
                for index in members
            ]
        )
    return clusters
