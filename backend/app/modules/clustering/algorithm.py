import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ClusteringParameters:
    # 0.391 / 0.261 = 旧的 0.36 / 0.24 除以 0.92——相似度公式摘掉恒为 0 的 scenario 通道
    # 并归一化后满分从 0.92 回到 1.0，阈值等比例上调以保持与旧口径等价。
    assign_threshold: float = 0.391
    grey_threshold: float = 0.261
    top_k: int = 3
    max_cluster_size: int = 120
    max_block_candidates: int = 400
    # 聚类入口的低信息量过滤门槛：特征快照 technology_weights 条数低于该值的 JD
    # 不参与聚类，进待治理池。0 表示不过滤。
    #
    # 默认 1 由窗口 B 在词表 v1.2 上重新标定得出（tools/calibrate_domain_gate.py）：
    # 门槛 1 把单例簇 JD 比从 48.9% 压到 20.2%、一致性从 64.2 提到 83.6；再往上加门槛
    # 单例比反而回升、灰区激增，是幸存者偏差而非质量改善。
    # 注意：这个门槛管的是**聚类形态**，不是非技术岗过滤——后者由特征快照的
    # 职能岗位判别（extraction/occupation.py）负责，两者口径不可混用。
    min_technology_evidence_count: int = 1
    # 迭代重分配（Lloyd 式）：单遍贪心的簇成员受 JD 进入顺序影响——先进的成员把质心
    # 拉偏后，后来更相似的 JD 反而进不来。收敛后的成员集合与进入顺序无关。
    # 0 轮 = 关闭迭代，退回单遍贪心（与历史运行对照用）。
    max_reassign_rounds: int = 10
    # 本轮移动数占参与聚类 JD 的比例低于该值即认为收敛。
    reassign_convergence_ratio: float = 0.01

    def as_dict(self) -> dict:
        return {
            "assign_threshold": self.assign_threshold,
            "grey_threshold": self.grey_threshold,
            "top_k": self.top_k,
            "max_cluster_size": self.max_cluster_size,
            "max_block_candidates": self.max_block_candidates,
            "min_technology_evidence_count": self.min_technology_evidence_count,
            "max_reassign_rounds": self.max_reassign_rounds,
            "reassign_convergence_ratio": self.reassign_convergence_ratio,
            "weights": {
                **{key: round(value, 6) for key, value in CHANNEL_WEIGHTS.items()},
            },
        }


@dataclass(frozen=True)
class RawJobFeature:
    job_posting_id: int
    job_code: str
    title: str
    title_tokens: tuple[str, ...]
    responsibility_tokens: tuple[str, ...]
    technology_weights: dict[str, float]
    domain_weights: dict[str, float]
    level_code: str | None
    sample_weight: float


@dataclass(frozen=True)
class JobVector:
    raw: RawJobFeature
    title: dict[str, float]
    responsibility: dict[str, float]
    capability: dict[str, float]
    domain: dict[str, float]


@dataclass
class ClusterDraft:
    draft_id: int
    members: list[JobVector] = field(default_factory=list)
    vector_sums: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "title": defaultdict(float),
            "responsibility": defaultdict(float),
            "capability": defaultdict(float),
            "domain": defaultdict(float),
        }
    )
    level_counts: Counter = field(default_factory=Counter)
    total_weight: float = 0.0
    # 质心在一轮重分配内是常量，但要被每个候选 JD 反复读取；不缓存会让迭代重分配
    # 退化成 O(轮次 × JD数 × 候选簇数 × 质心排序) 的规模。
    _centroid_cache: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, job: JobVector) -> None:
        weight = max(0.05, job.raw.sample_weight)
        self._centroid_cache = {}
        self.members.append(job)
        self.total_weight += weight
        for channel in ("title", "responsibility", "capability", "domain"):
            for key, value in getattr(job, channel).items():
                self.vector_sums[channel][key] += value * weight
        if job.raw.level_code:
            self.level_counts[job.raw.level_code] += weight

    def centroid(self, channel: str) -> dict[str, float]:
        cached = self._centroid_cache.get(channel)
        if cached is not None:
            return cached
        if not self.total_weight:
            return {}
        limit = {"title": 40, "responsibility": 120, "capability": 60, "domain": 7}[channel]
        values = {
            key: value / self.total_weight for key, value in self.vector_sums[channel].items()
        }
        result = dict(sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit])
        self._centroid_cache[channel] = result
        return result

    def dominant_level(self) -> str | None:
        if not self.level_counts:
            return None
        return max(self.level_counts, key=lambda key: (self.level_counts[key], key))

    def rebuild(self, members: list[JobVector]) -> None:
        """用给定成员重建本簇。

        增量累加没有对应的 remove()，重分配若用累减会积累浮点误差，
        并且会让「同一成员集合」在不同移动历史下得到不同质心，破坏可重放性。
        因此每轮重分配后整簇重建。
        """
        self.members = []
        self.total_weight = 0.0
        self.level_counts = Counter()
        self.vector_sums = {
            channel: defaultdict(float)
            for channel in ("title", "responsibility", "capability", "domain")
        }
        self._centroid_cache = {}
        for member in members:
            self.add(member)

    def snapshot(self) -> dict:
        return {
            "title": self.centroid("title"),
            "responsibility": self.centroid("responsibility"),
            "capability": self.centroid("capability"),
            "domain": self.centroid("domain"),
            "level_code": self.dominant_level(),
        }


@dataclass(frozen=True)
class CandidateScore:
    cluster_draft_id: int
    total: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class AssignmentDecision:
    job_posting_id: int
    cluster_draft_id: int
    status_code: str
    initial_score: float
    top_candidates: tuple[CandidateScore, ...]


@dataclass(frozen=True)
class ReassignRound:
    round_no: int
    moved_job_count: int
    cluster_count: int
    emptied_cluster_count: int


@dataclass(frozen=True)
class ClusteringOutput:
    clusters: tuple[ClusterDraft, ...]
    decisions: tuple[AssignmentDecision, ...]
    reassign_rounds: tuple[ReassignRound, ...] = ()
    converged: bool = True
    oscillation_detected: bool = False

    @property
    def reassign_stats(self) -> dict:
        return {
            "rounds": [
                {
                    "round_no": item.round_no,
                    "moved_job_count": item.moved_job_count,
                    "cluster_count": item.cluster_count,
                    "emptied_cluster_count": item.emptied_cluster_count,
                }
                for item in self.reassign_rounds
            ],
            "round_count": len(self.reassign_rounds),
            "total_moved_job_count": sum(item.moved_job_count for item in self.reassign_rounds),
            "converged": self.converged,
            "oscillation_detected": self.oscillation_detected,
        }


def cluster_jobs(
    raw_features: list[RawJobFeature], parameters: ClusteringParameters
) -> ClusteringOutput:
    vectors, document_frequencies = _vectorize(raw_features)
    clusters: list[ClusterDraft] = []
    block_index: dict[str, set[int]] = defaultdict(set)
    initial_status: dict[int, tuple[int, str, float]] = {}

    for job in sorted(vectors, key=lambda item: (item.raw.title, item.raw.job_code)):
        candidate_ids = _candidate_ids(job, block_index, document_frequencies, parameters)
        candidates = _rank_candidates(job, clusters, candidate_ids)
        best = candidates[0] if candidates else None
        if (
            best is not None
            and best.total >= parameters.assign_threshold
            and len(clusters[best.cluster_draft_id].members) < parameters.max_cluster_size
        ):
            cluster = clusters[best.cluster_draft_id]
            status = "assigned"
            initial_score = best.total
        else:
            cluster = ClusterDraft(draft_id=len(clusters))
            clusters.append(cluster)
            status = "grey" if best and best.total >= parameters.grey_threshold else "new_cluster"
            initial_score = best.total if best else 0.0
        cluster.add(job)
        _index_job(job, cluster.draft_id, block_index, document_frequencies)
        initial_status[job.raw.job_posting_id] = (cluster.draft_id, status, initial_score)

    assignment = {
        job_id: cluster_id for job_id, (cluster_id, _status, _score) in initial_status.items()
    }
    clusters, assignment, block_index, rounds, converged, oscillated = _reassign_until_stable(
        vectors, clusters, assignment, block_index, document_frequencies, parameters
    )

    decisions = []
    for job in vectors:
        _initial_cluster_id, status, initial_score = initial_status[job.raw.job_posting_id]
        own_cluster_id = assignment[job.raw.job_posting_id]
        candidate_ids = _candidate_ids(job, block_index, document_frequencies, parameters)
        candidate_ids.add(own_cluster_id)
        ranked = _rank_candidates(job, clusters, candidate_ids)[: parameters.top_k]
        decisions.append(
            AssignmentDecision(
                job_posting_id=job.raw.job_posting_id,
                cluster_draft_id=own_cluster_id,
                status_code=status,
                initial_score=initial_score,
                top_candidates=tuple(ranked),
            )
        )
    return ClusteringOutput(
        tuple(clusters),
        tuple(decisions),
        reassign_rounds=tuple(rounds),
        converged=converged,
        oscillation_detected=oscillated,
    )


def _reassign_until_stable(
    vectors: list[JobVector],
    clusters: list[ClusterDraft],
    assignment: dict[int, int],
    block_index: dict[str, set[int]],
    document_frequencies: dict[str, tuple[int, int]],
    parameters: ClusteringParameters,
) -> tuple[
    list[ClusterDraft], dict[int, int], dict[str, set[int]], list[ReassignRound], bool, bool
]:
    """Lloyd 式迭代重分配：重算质心 → 全局重分配 → 直到稳定。

    与教科书 k-means 的两处差别，都是被这套数据的约束逼出来的：

    1. **批量应用而非边算边移。** 先用同一批质心算完所有 JD 的目标簇，再统一应用。
       边算边移会让结果依赖 JD 的处理顺序——那正是单遍贪心要解决的问题，
       在迭代里重新引入就白做了。

    2. **`max_cluster_size` 是硬约束，会破坏 Lloyd 的单调收敛。** 目标簇满员时按
       相似度降序接纳，落选的 JD 留在原簇。这使得目标函数可能不再单调下降，
       因此必须设最大轮次，并检测「成员划分回到此前出现过的状态」这类振荡。

    JD 不会被强行分配：所有候选簇都达不到 assign_threshold 的 JD 留在原处
    （它可能是自成一簇的合理离群点），不制造虚假归属。
    """
    rounds: list[ReassignRound] = []
    if parameters.max_reassign_rounds <= 0 or not vectors:
        return clusters, assignment, block_index, rounds, True, False

    ordered = sorted(vectors, key=lambda item: (item.raw.title, item.raw.job_code))
    threshold = max(1, int(len(ordered) * parameters.reassign_convergence_ratio))
    seen_partitions: set[frozenset[tuple[int, ...]]] = {_partition_key(assignment)}
    converged = False
    oscillated = False

    for round_no in range(1, parameters.max_reassign_rounds + 1):
        proposals: dict[int, tuple[int, float]] = {}
        for job in ordered:
            current_id = assignment[job.raw.job_posting_id]
            candidate_ids = _candidate_ids(job, block_index, document_frequencies, parameters)
            candidate_ids.add(current_id)
            ranked = _rank_candidates(job, clusters, candidate_ids)
            best = ranked[0] if ranked else None
            if (
                best is not None
                and best.cluster_draft_id != current_id
                and best.total >= parameters.assign_threshold
            ):
                proposals[job.raw.job_posting_id] = (best.cluster_draft_id, best.total)

        moved = _apply_proposals(ordered, assignment, proposals, parameters)
        clusters, assignment, block_index, emptied = _rebuild_clusters(
            ordered, assignment, document_frequencies, parameters
        )
        rounds.append(
            ReassignRound(
                round_no=round_no,
                moved_job_count=moved,
                cluster_count=len(clusters),
                emptied_cluster_count=emptied,
            )
        )
        if moved < threshold:
            converged = True
            break
        partition = _partition_key(assignment)
        if partition in seen_partitions:
            # 回到了此前出现过的划分：再迭代只会在几个状态之间循环。
            oscillated = True
            break
        seen_partitions.add(partition)
    return clusters, assignment, block_index, rounds, converged, oscillated


def _apply_proposals(
    ordered: list[JobVector],
    assignment: dict[int, int],
    proposals: dict[int, tuple[int, float]],
    parameters: ClusteringParameters,
) -> int:
    """统一应用本轮的移动提议，并在目标簇满员时按相似度降序仲裁。"""
    sizes: dict[int, int] = defaultdict(int)
    for cluster_id in assignment.values():
        sizes[cluster_id] += 1
    incoming: dict[int, list[tuple[float, str, int]]] = defaultdict(list)
    by_id = {job.raw.job_posting_id: job for job in ordered}
    for job_id, (target_id, score) in proposals.items():
        incoming[target_id].append((score, by_id[job_id].raw.job_code, job_id))

    moved = 0
    for target_id in sorted(incoming):
        # 分数降序、同分按 job_code 升序：仲裁结果与提议的收集顺序无关。
        ranked_incoming = sorted(incoming[target_id], key=lambda item: (-item[0], item[1]))
        for _score, _code, job_id in ranked_incoming:
            if sizes[target_id] >= parameters.max_cluster_size:
                break
            source_id = assignment[job_id]
            assignment[job_id] = target_id
            sizes[source_id] -= 1
            sizes[target_id] += 1
            moved += 1
    return moved


def _rebuild_clusters(
    ordered: list[JobVector],
    assignment: dict[int, int],
    document_frequencies: dict[str, tuple[int, int]],
    parameters: ClusteringParameters,
) -> tuple[list[ClusterDraft], dict[int, int], dict[str, set[int]], int]:
    """按当前划分重建簇与块索引，丢弃空簇并重编 draft_id。"""
    members_by_cluster: dict[int, list[JobVector]] = defaultdict(list)
    for job in ordered:
        members_by_cluster[assignment[job.raw.job_posting_id]].append(job)

    emptied = 0
    clusters: list[ClusterDraft] = []
    remap: dict[int, int] = {}
    for old_id in sorted(members_by_cluster):
        members = members_by_cluster[old_id]
        if not members:
            emptied += 1
            continue
        cluster = ClusterDraft(draft_id=len(clusters))
        cluster.rebuild(members)
        remap[old_id] = cluster.draft_id
        clusters.append(cluster)

    new_assignment = {
        job.raw.job_posting_id: remap[assignment[job.raw.job_posting_id]] for job in ordered
    }
    block_index: dict[str, set[int]] = defaultdict(set)
    for job in ordered:
        _index_job(
            job, new_assignment[job.raw.job_posting_id], block_index, document_frequencies
        )
    return clusters, new_assignment, block_index, emptied


def _partition_key(assignment: dict[int, int]) -> frozenset[tuple[int, ...]]:
    """把划分规范化成与簇编号无关的形式，用于振荡检测。"""
    groups: dict[int, list[int]] = defaultdict(list)
    for job_id, cluster_id in assignment.items():
        groups[cluster_id].append(job_id)
    return frozenset(tuple(sorted(members)) for members in groups.values())


# 通道权重。v1 里还有一个 scenario 通道占 0.08，但场景特征从未被填充、恒为 0——
# 相似度的有效满分因此只有 0.92，assign_threshold=0.36 实际卡在 0.391 的位置上。
# 这里把空通道摘掉并把权重按原比例归一化到剩余五个通道，满分回到 1.0，
# 阈值语义变成真正的「相似度 ≥ 阈值」。默认阈值同步按 1/0.92 上调以保持行为等价，
# 使后续改动的效果不会与这次口径修正混在一起。
_RAW_CHANNEL_WEIGHTS = {
    "title": 0.20,
    "responsibility": 0.30,
    "capability": 0.25,
    "domain": 0.10,
    "level": 0.07,
}
_WEIGHT_SUM = sum(_RAW_CHANNEL_WEIGHTS.values())
CHANNEL_WEIGHTS = {key: value / _WEIGHT_SUM for key, value in _RAW_CHANNEL_WEIGHTS.items()}

# 岗位层级是有序的，相邻层级不该与跨两级同样判为 0 分。
LEVEL_RANKS = {"junior": 0, "middle": 1, "senior": 2}


def level_similarity(job_level: str | None, cluster_level: str | None) -> float:
    """按序数距离算层级相似度：同级 1.0、相邻 0.5、跨两级 0.0。

    v1 是二值的（相同得 1、否则 0），于是「初级 vs 中级」与「初级 vs 高级」同样得 0，
    丢掉了层级本身的序关系。语料里 senior/middle 各占约一半，这个区别不小。
    """
    if not job_level or not cluster_level:
        return 0.0
    if job_level == cluster_level:
        return 1.0
    left, right = LEVEL_RANKS.get(job_level), LEVEL_RANKS.get(cluster_level)
    if left is None or right is None:
        return 0.0
    span = max(LEVEL_RANKS.values()) - min(LEVEL_RANKS.values())
    return max(0.0, 1.0 - abs(left - right) / span)


def similarity(job: JobVector, cluster: ClusterDraft) -> CandidateScore:
    breakdown = {
        "title": cosine(job.title, cluster.centroid("title")),
        "responsibility": cosine(job.responsibility, cluster.centroid("responsibility")),
        "capability": cosine(job.capability, cluster.centroid("capability")),
        "domain": cosine(job.domain, cluster.centroid("domain")),
        "level": level_similarity(job.raw.level_code, cluster.dominant_level()),
    }
    total = sum(CHANNEL_WEIGHTS[channel] * value for channel, value in breakdown.items())
    return CandidateScore(cluster.draft_id, round(total, 6), breakdown)


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left).intersection(right)
    if not shared:
        return 0.0
    dot = sum(left[key] * right[key] for key in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _vectorize(
    features: list[RawJobFeature],
) -> tuple[list[JobVector], dict[str, tuple[int, int]]]:
    title_idf, title_df = _idf([item.title_tokens for item in features])
    responsibility_idf, responsibility_df = _idf([item.responsibility_tokens for item in features])
    technology_idf, technology_df = _idf([tuple(item.technology_weights) for item in features])
    domain_idf, domain_df = _idf([tuple(item.domain_weights) for item in features])
    vectors = []
    for item in features:
        vectors.append(
            JobVector(
                raw=item,
                title={key: title_idf[key] for key in set(item.title_tokens)},
                responsibility={
                    key: responsibility_idf[key] for key in set(item.responsibility_tokens)
                },
                capability={
                    key: float(value) * technology_idf[key]
                    for key, value in item.technology_weights.items()
                },
                domain={
                    key: float(value) * domain_idf[key]
                    for key, value in item.domain_weights.items()
                },
            )
        )
    document_frequencies = {}
    for prefix, values in (
        ("t", title_df),
        ("r", responsibility_df),
        ("c", technology_df),
        ("d", domain_df),
    ):
        document_frequencies.update(
            {f"{prefix}:{key}": (count, len(features)) for key, count in values.items()}
        )
    return vectors, document_frequencies


def _idf(documents: list[tuple[str, ...]]) -> tuple[dict[str, float], dict[str, int]]:
    frequency: Counter = Counter()
    for document in documents:
        frequency.update(set(document))
    size = len(documents)
    return (
        {key: math.log((1 + size) / (1 + count)) + 1 for key, count in frequency.items()},
        dict(frequency),
    )


def _blocking_keys(job: JobVector, frequencies: dict[str, tuple[int, int]]) -> set[str]:
    keys = set()
    for token in job.title:
        count, total = frequencies[f"t:{token}"]
        if count / total <= 0.25:
            keys.add(f"t:{token}")
    for token in job.capability:
        keys.add(f"c:{token}")
    for token in job.domain:
        keys.add(f"d:{token}")
    responsibility = sorted(job.responsibility, key=job.responsibility.get, reverse=True)
    for token in responsibility[:8]:
        count, total = frequencies[f"r:{token}"]
        if count / total <= 0.15:
            keys.add(f"r:{token}")
    return keys


def _candidate_ids(
    job: JobVector,
    block_index: dict[str, set[int]],
    frequencies: dict[str, tuple[int, int]],
    parameters: ClusteringParameters,
) -> set[int]:
    counts: Counter = Counter()
    for key in _blocking_keys(job, frequencies):
        counts.update(block_index.get(key, ()))
    return {
        cluster_id for cluster_id, _count in counts.most_common(parameters.max_block_candidates)
    }


def _index_job(
    job: JobVector,
    cluster_id: int,
    block_index: dict[str, set[int]],
    frequencies: dict[str, tuple[int, int]],
) -> None:
    for key in _blocking_keys(job, frequencies):
        block_index[key].add(cluster_id)


def _rank_candidates(
    job: JobVector, clusters: list[ClusterDraft], candidate_ids: set[int]
) -> list[CandidateScore]:
    return sorted(
        (similarity(job, clusters[cluster_id]) for cluster_id in candidate_ids),
        key=lambda item: (-item.total, item.cluster_draft_id),
    )


def decimal_score(value: float, scale: str = "0.000001") -> Decimal:
    return Decimal(str(value)).quantize(Decimal(scale))
