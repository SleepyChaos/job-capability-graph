import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ClusteringParameters:
    assign_threshold: float = 0.36
    grey_threshold: float = 0.24
    top_k: int = 3
    max_cluster_size: int = 120
    max_block_candidates: int = 400
    # 聚类入口的低信息量过滤门槛（任务组 3 机械版）：特征快照 technology_weights
    # 条数低于该值的 JD 不参与聚类，进待治理池。默认 2 是临时值，窗口 B 词表
    # 修复后需重新标定。0 表示不过滤。
    min_technology_evidence_count: int = 2

    def as_dict(self) -> dict:
        return {
            "assign_threshold": self.assign_threshold,
            "grey_threshold": self.grey_threshold,
            "top_k": self.top_k,
            "max_cluster_size": self.max_cluster_size,
            "max_block_candidates": self.max_block_candidates,
            "min_technology_evidence_count": self.min_technology_evidence_count,
            "weights": {
                "title": 0.20,
                "responsibility": 0.30,
                "capability": 0.25,
                "domain": 0.10,
                "scenario": 0.08,
                "level": 0.07,
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

    def add(self, job: JobVector) -> None:
        weight = max(0.05, job.raw.sample_weight)
        self.members.append(job)
        self.total_weight += weight
        for channel in ("title", "responsibility", "capability", "domain"):
            for key, value in getattr(job, channel).items():
                self.vector_sums[channel][key] += value * weight
        if job.raw.level_code:
            self.level_counts[job.raw.level_code] += weight

    def centroid(self, channel: str) -> dict[str, float]:
        if not self.total_weight:
            return {}
        limit = {"title": 40, "responsibility": 120, "capability": 60, "domain": 7}[channel]
        values = {
            key: value / self.total_weight for key, value in self.vector_sums[channel].items()
        }
        return dict(sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit])

    def dominant_level(self) -> str | None:
        if not self.level_counts:
            return None
        return max(self.level_counts, key=lambda key: (self.level_counts[key], key))

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
class ClusteringOutput:
    clusters: tuple[ClusterDraft, ...]
    decisions: tuple[AssignmentDecision, ...]


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

    decisions = []
    for job in vectors:
        own_cluster_id, status, initial_score = initial_status[job.raw.job_posting_id]
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
    return ClusteringOutput(tuple(clusters), tuple(decisions))


def similarity(job: JobVector, cluster: ClusterDraft) -> CandidateScore:
    title = cosine(job.title, cluster.centroid("title"))
    responsibility = cosine(job.responsibility, cluster.centroid("responsibility"))
    capability = cosine(job.capability, cluster.centroid("capability"))
    domain = cosine(job.domain, cluster.centroid("domain"))
    level = (
        1.0
        if job.raw.level_code
        and cluster.dominant_level()
        and job.raw.level_code == cluster.dominant_level()
        else 0.0
    )
    breakdown = {
        "title": title,
        "responsibility": responsibility,
        "capability": capability,
        "domain": domain,
        "scenario": 0.0,
        "level": level,
    }
    total = (
        0.20 * title
        + 0.30 * responsibility
        + 0.25 * capability
        + 0.10 * domain
        + 0.08 * 0.0
        + 0.07 * level
    )
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
