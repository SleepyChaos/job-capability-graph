"""岗位聚类：IDF 加权余弦 + 动态踢出重匹配（移植自项目二 cluster_jobs_batch.py）。

改造点：
1. 读取统一库 job_skills（JOIN skills 取技术词与 L2 类目）替代旧 job_keywords 表
2. LLM 画像改为 OpenAI 兼容接口，未配置时自动降级为启发式命名（不伪造 LLM 结果）
3. 结果写统一 clusters / job_cluster_map（JSON 数组字段），LLM 命名标记待审核
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import config, db, llm

# 过于宽泛的通用词（移植自项目二，并补充新一代信息技术领域泛词）
STOPWORDS = set(
    "架构,开发,设计,算法,测试,管理,系统,平台,硬件,软件,产品,技术,工程,研发,"
    "制造,生产,质量,项目,数据,业务,运营,市场,销售,客户,服务,支持,维护,优化,"
    "方案,解决,分析,评估,规划,实施,集成,验证,调试,文档,培训,协调,沟通,领导,团队,"
    "负责,参与,熟悉,掌握,具备,相关,优先,以上,以下,工作,经验,学历,专业,能力,素质,"
    "职责,要求,任职,岗位,职位,公司,行业,领域,方向,职能,部门,企业,单位,机构,组织,"
    "基地,区域,地点,城市,薪资,待遇,福利,工程师,专员,人员,相关经验".split(",")
)

_idf: dict[str, float] = {}
_job_keywords: dict[str, set[str]] = {}
_job_vec: dict[str, dict[str, float]] = {}
_job_norm: dict[str, float] = {}


def load_job_keyword_sets(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """岗位 → 特征词集合（技术词 + L2 类目作高阶语义特征，与项目二一致）。"""
    rows = conn.execute(
        """
        SELECT js.job_id, s.skill_term, c2.l2_name
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        LEFT JOIN l2_categories c2 ON s.l2_id = c2.l2_id
        WHERE js.review_status != 'rejected'
        """
    ).fetchall()
    groups: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        for value in (r["skill_term"], r["l2_name"]):
            if not value or value.strip().lower() in STOPWORDS:
                continue
            groups[r["job_id"]].add(value.strip())

    max_df = config.CLUSTER_MAX_DF
    if 0 < max_df < 1 and groups:
        n = len(groups)
        df_count: dict[str, int] = defaultdict(int)
        for kw_set in groups.values():
            for k in kw_set:
                df_count[k] += 1
        common = {k for k, v in df_count.items() if v / n > max_df}
        if common:
            print(f"[INFO] 过滤高频词 {len(common)} 个（df > {max_df:.0%}）")
            for jid in list(groups):
                groups[jid] -= common
    return {jid: s for jid, s in groups.items() if s}


def compute_idf(job_keywords: dict[str, set[str]]) -> dict[str, float]:
    n = len(job_keywords)
    df: dict[str, int] = defaultdict(int)
    for kw_set in job_keywords.values():
        for k in kw_set:
            df[k] += 1
    return {k: math.log(n / max(v, 1)) for k, v in df.items()}


def cosine_similarity(vec_a: dict, norm_a: float, vec_b: dict, norm_b: float):
    if norm_a == 0 or norm_b == 0:
        return 0.0, set()
    shared = set(vec_a) & set(vec_b)
    if len(shared) < config.CLUSTER_MIN_SHARED_KEYWORDS:
        return 0.0, shared
    dot = sum(vec_a[k] * vec_b[k] for k in shared)
    return dot / (norm_a * norm_b), shared


@dataclass
class Cluster:
    cluster_id: str
    name: str = ""
    description: str = ""
    shared_skills: list[str] = field(default_factory=list)
    representative_titles: list[str] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    keyword_freq: Counter = field(default_factory=Counter)
    reason: str = ""
    name_source: str = "heuristic"

    @property
    def keywords(self) -> set[str]:
        return set(self.keyword_freq)


def avg_cosine_to_cluster(job_id: str, cluster: Cluster):
    if not cluster.job_ids:
        return 0.0, set()
    vec, norm = _job_vec.get(job_id, {}), _job_norm.get(job_id, 0.0)
    total, shared_union = 0.0, set()
    for member_id in cluster.job_ids:
        sim, shared = cosine_similarity(vec, norm, _job_vec.get(member_id, {}), _job_norm.get(member_id, 0.0))
        total += sim
        shared_union |= shared
    return total / len(cluster.job_ids), shared_union


def member_fit_scores(cluster: Cluster) -> list[tuple[str, float]]:
    members = cluster.job_ids
    if len(members) <= 1:
        return [(members[0], 1.0)] if members else []
    scores = []
    for jid in members:
        vec, norm = _job_vec.get(jid, {}), _job_norm.get(jid, 0.0)
        sims = [
            cosine_similarity(vec, norm, _job_vec.get(o, {}), _job_norm.get(o, 0.0))[0]
            for o in members
            if o != jid
        ]
        scores.append((jid, sum(sims) / len(sims)))
    return scores


def find_best_cluster(job_id: str, clusters: list[Cluster]):
    best_idx, best_sim, best_shared = -1, 0.0, set()
    for idx, cluster in enumerate(clusters):
        sim, shared = avg_cosine_to_cluster(job_id, cluster)
        if sim >= config.CLUSTER_THRESHOLD and sim > best_sim:
            best_idx, best_sim, best_shared = idx, sim, shared
    return best_idx, best_sim, best_shared


def assign_job(jid: str, clusters: list[Cluster], counter: list[int], depth: int = 0) -> None:
    job_kw = _job_keywords.get(jid, set())
    if not job_kw:
        return
    best_idx, best_sim, _ = find_best_cluster(jid, clusters)
    if best_idx < 0:
        counter[0] += 1
        clusters.append(Cluster(cluster_id=f"C{counter[0]}", job_ids=[jid], keyword_freq=Counter(job_kw)))
        return

    cluster = clusters[best_idx]
    if len(cluster.job_ids) < config.CLUSTER_MAX_CLUSTER_SIZE:
        cluster.job_ids.append(jid)
        cluster.keyword_freq.update(job_kw)
        return

    scores = member_fit_scores(cluster)
    weakest_jid, weakest_score = min(scores, key=lambda x: x[1])
    if best_sim > weakest_score and depth < config.CLUSTER_MAX_EVICTION_DEPTH:
        weakest_kw = _job_keywords.get(weakest_jid, set())
        cluster.job_ids.remove(weakest_jid)
        for k in weakest_kw:
            cluster.keyword_freq[k] -= 1
            if cluster.keyword_freq[k] <= 0:
                del cluster.keyword_freq[k]
        cluster.job_ids.append(jid)
        cluster.keyword_freq.update(job_kw)
        assign_job(weakest_jid, clusters, counter, depth + 1)
    else:
        counter[0] += 1
        clusters.append(Cluster(cluster_id=f"C{counter[0]}", job_ids=[jid], keyword_freq=Counter(job_kw)))


def heuristic_profile(titles: list[str], keyword_set: set[str]) -> dict[str, Any]:
    if titles:
        counts: dict[str, int] = defaultdict(int)
        for t in titles:
            counts[t] += 1
        name = max(titles, key=lambda t: (counts[t], len(t)))[:30]
    else:
        name = "未命名聚类"
    shared = sorted(keyword_set)[:10]
    return {
        "cluster_name": name,
        "description": f"以{name}为代表的岗位集合，核心技能包括{', '.join(shared[:5]) if shared else '无明确关键词'}。",
        "shared_skills": shared,
        "representative_titles": titles[:3],
        "reason": "规则生成聚类画像。",
    }, "heuristic"


def llm_profile(titles: list[str], keyword_set: set[str]) -> dict[str, Any] | None:
    system = (
        "你是一位职业聚类专家。请根据下面一组相似岗位，提炼出一个职业聚类画像。"
        "输出严格 JSON，不要包含任何解释。字段："
        "cluster_name(不超过15字的中文聚类名), description(1-2句话描述), "
        "shared_skills(核心技术词数组，不超过10个), representative_titles(代表性岗位标题数组，不超过3个), "
        "reason(为什么把这些岗位归为一类)。"
    )
    user = f"共有技术词：{sorted(keyword_set)[:20]}\n\n岗位列表（部分）：\n" + "\n".join(
        f"- {t}" for t in titles[:8]
    )
    result = llm.chat_json(system, user)
    if result is None:
        return None
    for k in ("cluster_name", "description", "shared_skills", "representative_titles", "reason"):
        result.setdefault(k, "")
    return result


def generate_profiles(conn: sqlite3.Connection, clusters: list[Cluster]) -> None:
    title_map = {
        r["job_id"]: r["title"] for r in conn.execute("SELECT job_id, title FROM jobs").fetchall()
    }
    use_llm = llm.is_available()
    print(f"生成聚类画像（{'LLM' if use_llm else '启发式规则'}）: {len(clusters)} 个聚类")
    for idx, gc in enumerate(clusters, 1):
        titles = [title_map.get(jid, "") for jid in gc.job_ids if title_map.get(jid)]
        result = llm_profile(titles, gc.keywords) if (use_llm and len(gc.job_ids) > 1) else None
        if result is None:
            result, source = heuristic_profile(titles, gc.keywords)
        else:
            source = "llm"
        gc.name = result.get("cluster_name", "未命名聚类")
        gc.description = result.get("description", "")
        gc.shared_skills = result.get("shared_skills", [])
        gc.representative_titles = result.get("representative_titles", [])
        gc.reason = result.get("reason", "")
        gc.name_source = source
        if idx % 100 == 0:
            print(f"  ... {idx}/{len(clusters)}")


def save_results(conn: sqlite3.Connection, clusters: list[Cluster], clustered_at: str) -> dict:
    cur = conn.cursor()
    cur.execute("DELETE FROM clusters")
    cur.execute("DELETE FROM job_cluster_map")
    cur.execute("DELETE FROM cluster_classifications")
    for gc in clusters:
        # LLM 生成的命名待人工审核；规则命名直接可用
        status = "pending" if gc.name_source == "llm" else "approved"
        cur.execute(
            """
            INSERT INTO clusters (cluster_id, cluster_name, description, shared_skills,
                                  representative_titles, keywords, job_count, name_source,
                                  review_status, clustered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gc.cluster_id, gc.name, gc.description,
                json.dumps(gc.shared_skills, ensure_ascii=False),
                json.dumps(gc.representative_titles, ensure_ascii=False),
                json.dumps(sorted(gc.keywords), ensure_ascii=False),
                len(gc.job_ids), gc.name_source, status, clustered_at,
            ),
        )
        for jid in gc.job_ids:
            cur.execute(
                "INSERT OR IGNORE INTO job_cluster_map (cluster_id, job_id, clustered_at) VALUES (?, ?, ?)",
                (gc.cluster_id, jid, clustered_at),
            )
    conn.commit()
    db.set_meta(conn, "last_clustered_at", clustered_at)
    conn.commit()
    return {"cluster_count": len(clusters), "clustered_at": clustered_at}


def run_clustering(conn: sqlite3.Connection) -> dict:
    global _idf, _job_keywords, _job_vec, _job_norm
    clustered_at = datetime.now(timezone.utc).isoformat()

    _job_keywords = load_job_keyword_sets(conn)
    _idf = compute_idf(_job_keywords)
    _job_vec, _job_norm = {}, {}
    for jid, kws in _job_keywords.items():
        vec = {kw: _idf.get(kw, 0.0) for kw in kws}
        _job_vec[jid] = vec
        _job_norm[jid] = math.sqrt(sum(v * v for v in vec.values()))

    all_ids = list(_job_keywords)
    total = len(all_ids)
    print(f"参与聚类岗位: {total}，阈值 {config.CLUSTER_THRESHOLD}，"
          f"最大簇 {config.CLUSTER_MAX_CLUSTER_SIZE}")

    clusters: list[Cluster] = []
    counter = [0]
    start = time.time()
    batch = config.CLUSTER_BATCH_SIZE
    for b in range(0, total, batch):
        for jid in all_ids[b: b + batch]:
            assign_job(jid, clusters, counter)
        print(f"  批次 {b // batch + 1}: 已处理 {min(b + batch, total)}/{total}，"
              f"聚类数 {len(clusters)}，耗时 {time.time() - start:.1f}s")

    print(f"聚类完成：{len(clusters)} 个聚类，耗时 {time.time() - start:.1f}s")
    generate_profiles(conn, clusters)
    return save_results(conn, clusters, clustered_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="岗位动态聚类（统一库）")
    parser.parse_args()
    conn = db.connect()
    db.init_db(conn)
    stats = run_clustering(conn)
    print(f"聚类结果已写入统一库：{stats}")
    conn.close()


if __name__ == "__main__":
    main()
