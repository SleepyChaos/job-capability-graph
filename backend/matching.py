"""人岗匹配引擎（阶段 3）：移植项目三 vectorization.py 的混合匹配机制。

改造点（相对原实现）：
1. 能力本体从 capability_nodes（三级能力树）改为统一库 skills 本体（L1-L4）
2. 稀疏向量直接构建在 skill_id 上：简历向量来自 resume_skills（权重=置信度），
   岗位向量来自 job_skills（权重=置信度）；L1 域向量由 skill → l1_code 汇总
3. 语义向量（bge-small-zh）暂不启用：sentence-transformers 未安装时透明降级，
   不伪造语义分（项目三原设计原则），各分量按激活权重归一化
4. 差距分析：shared（共同技能）/ missing（岗位有简历缺）/ extra（简历有岗位无）
"""
from __future__ import annotations

import math
import sqlite3
from difflib import SequenceMatcher

# 混合匹配权重（参照 vectorization.py MATCH_WEIGHTS，去掉未启用的 semantic/compatibility）
MATCH_WEIGHTS = {
    "capability": 0.50,   # skill 级稀疏向量余弦
    "l1": 0.20,           # L1 域分布余弦（方向是否对口）
    "core_jaccard": 0.20, # 核心技能集合 Jaccard
    "title": 0.10,        # 目标头衔相似度（简历未提供头衔时该分量不参与）
}


def normalize_sparse(values: dict[int, float]) -> dict[int, float]:
    norm = math.sqrt(sum(v * v for v in values.values()))
    if norm <= 0:
        return {}
    return {k: v / norm for k, v in values.items() if v > 0}


def cosine_sparse(left: dict[int, float], right: dict[int, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    value = sum(w * right.get(k, 0.0) for k, w in left.items())
    return max(0.0, min(1.0, value))


def jaccard(left: set[int], right: set[int]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class MatchingEngine:
    """从统一库加载技能本体/岗位画像，支持批量匹配。实例按请求构建即可（~万级边毫秒级）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # 技能本体：skill_id → {term, l1_code}
        self.skills: dict[int, dict] = {}
        self.term_index: dict[str, int] = {}
        for r in conn.execute("SELECT skill_id, skill_term, l1_code FROM skills"):
            self.skills[int(r["skill_id"])] = {
                "term": r["skill_term"],
                "l1_code": r["l1_code"] or "",
            }

    # ---- 画像构建 ----

    def resume_profile(self, resume_id: str) -> tuple[dict[int, float], dict[str, float], set[int]]:
        """简历画像：skill 稀疏向量 / L1 域向量 / 技能 id 集合。"""
        raw: dict[int, float] = {}
        for r in self.conn.execute(
            "SELECT skill_id, confidence FROM resume_skills WHERE resume_id = ?", (resume_id,)
        ):
            raw[int(r["skill_id"])] = max(raw.get(int(r["skill_id"]), 0.0), float(r["confidence"]))
        return self._profile_from_raw(raw)

    def job_profiles(self) -> dict[str, tuple[dict[int, float], dict[str, float], set[int]]]:
        """全量岗位画像（job_id → 三元组）。job_id 为文本主键。"""
        grouped: dict[str, dict[int, float]] = {}
        for r in self.conn.execute("SELECT job_id, skill_id, confidence FROM job_skills"):
            gid = str(r["job_id"])
            sid = int(r["skill_id"])
            grouped.setdefault(gid, {})[sid] = max(
                grouped.get(gid, {}).get(sid, 0.0), float(r["confidence"])
            )
        return {gid: self._profile_from_raw(raw) for gid, raw in grouped.items()}

    def _profile_from_raw(self, raw: dict[int, float]):
        l1_raw: dict[str, float] = {}
        for sid, w in raw.items():
            info = self.skills.get(sid)
            if info and info["l1_code"]:
                l1_raw[info["l1_code"]] = l1_raw.get(info["l1_code"], 0.0) + w
        return normalize_sparse(raw), normalize_sparse(l1_raw), set(raw.keys())

    # ---- 匹配 ----

    def match(
        self,
        resume_id: str,
        top_n: int = 10,
        l1_filter: str | None = None,
        resume_title: str | None = None,
    ) -> dict:
        """对一份简历做全库匹配，返回 Top N + 差距分析。

        resume_title：候选人目标头衔（可选），参与标题相似度分量。
        l1_filter：限定候选岗位的 L1 域（如 'T1'）。
        """
        r_vec, r_l1, r_set = self.resume_profile(resume_id)
        if not r_set:
            return {"matches": [], "warning": "简历未提取到任何技能，无法匹配", "resume_skill_count": 0}

        # 候选预筛：只保留与简历有共同技能的岗位（无交集的余弦/Jaccard 均为 0）
        inverted: dict[str, set[int]] = {}
        for r in self.conn.execute("SELECT job_id, skill_id FROM job_skills"):
            sid = int(r["skill_id"])
            if sid in r_set:
                inverted.setdefault(str(r["job_id"]), set()).add(sid)

        job_meta: dict[str, sqlite3.Row] = {}
        if inverted:
            placeholders = ",".join("?" * len(inverted))
            for r in self.conn.execute(
                f"SELECT job_id, title, company, city, salary_text, experience FROM jobs WHERE job_id IN ({placeholders})",
                tuple(inverted.keys()),
            ):
                job_meta[str(r["job_id"])] = r

        profiles = self.job_profiles()
        results: list[dict] = []
        for job_id in inverted:
            meta = job_meta.get(job_id)
            profile = profiles.get(job_id)
            if meta is None or profile is None:
                continue
            if l1_filter:
                j_l1 = profile[1]
                # 主导 L1 域过滤：岗位画像中权重最大的技术域必须与筛选域一致
                if not j_l1 or max(j_l1, key=j_l1.get) != l1_filter:
                    continue
            j_vec, j_l1, j_set = profile

            cap_score = cosine_sparse(r_vec, j_vec)
            l1_score = cosine_sparse(r_l1, j_l1)
            core_score = jaccard(r_set, j_set)

            components = {
                "capability": cap_score,
                "l1": l1_score,
                "core_jaccard": core_score,
            }
            title_score = None
            if resume_title:
                title_score = SequenceMatcher(
                    None, resume_title.lower(), str(meta["title"] or "").lower()
                ).ratio()
                components["title"] = title_score

            active_weight = sum(MATCH_WEIGHTS[k] for k in components)
            total = sum(MATCH_WEIGHTS[k] * v for k, v in components.items()) / active_weight

            # 差距分析清单
            shared = sorted(r_set & j_set, key=lambda s: j_vec.get(s, 0.0), reverse=True)
            missing = sorted(j_set - r_set, key=lambda s: j_vec.get(s, 0.0), reverse=True)
            extra = sorted(r_set - j_set, key=lambda s: r_vec.get(s, 0.0), reverse=True)
            names = lambda ids: [self.skills[s]["term"] for s in ids if s in self.skills]

            results.append({
                "job_id": str(job_id),
                "title": meta["title"],
                "company": meta["company"],
                "city": meta["city"],
                "salary": meta["salary_text"] or "",
                "score": round(max(0.0, min(1.0, total)), 4),
                "capability_score": round(cap_score, 4),
                "l1_score": round(l1_score, 4),
                "core_jaccard": round(core_score, 4),
                "title_score": round(title_score, 4) if title_score is not None else None,
                "coverage": round(min(1.0, len(r_set) / 8.0), 2),  # 简历技能丰富度（参照原实现）
                "shared": names(shared[:10]),
                "missing": names(missing[:10]),
                "extra": names(extra[:10]),
                "missing_severity": _severity(len(missing), len(j_set)),
            })

        results.sort(key=lambda x: (-x["score"], x["title"] or ""))
        return {
            "matches": results[:top_n],
            "candidate_count": len(results),
            "resume_skill_count": len(r_set),
            "semantic_available": False,  # 语义模型未启用，透明声明（不伪造语义分）
        }


def _severity(missing_count: int, job_skill_count: int) -> str:
    """差距严重度：缺失占岗位技能比例（演示口径，对应前端三档缺失样式）。"""
    if job_skill_count <= 0:
        return "minor"
    ratio = missing_count / job_skill_count
    if ratio >= 0.6:
        return "severe"
    if ratio >= 0.3:
        return "moderate"
    return "minor"
