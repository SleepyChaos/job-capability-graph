"""样例 JD 生成器：从新一代信息技术词典构造 ≥100 条合成 JD + 真值标注。

用途：
1. 在没有真实数据时验证"导入→提取→聚类"全流程（赛题要求 ≥100 条 JD 测试用例）
2. ground_truth.json 记录每条 JD 埋入的技术词，用于计算提取准确率（precision/recall）

注意：合成数据仅用于流程验证与准确率测试，演示时应说明；正式数据接入后替换。
"""
from __future__ import annotations

import argparse
import csv
import json
import random

from . import config, db

# 岗位标题模板（按 L1 域）
TITLE_TEMPLATES = {
    "AI": ["算法工程师", "机器学习工程师", "大模型应用工程师", "NLP算法工程师",
           "计算机视觉工程师", "推荐算法工程师", "AI平台开发工程师"],
    "BD": ["大数据开发工程师", "数据仓库工程师", "数据治理专家", "数据分析师",
           "实时计算工程师", "BI开发工程师"],
    "IOT": ["物联网平台工程师", "嵌入式软件工程师", "IoT解决方案架构师", "边缘计算工程师",
            "智能硬件开发工程师", "工业互联网工程师"],
    "IS": ["自动驾驶感知工程师", "机器人控制算法工程师", "云原生开发工程师",
           "后端开发工程师", "测试开发工程师", "系统安全工程师"],
}

COMPANIES = ["讯智科技", "云脉智能", "数联未来", "星图数据", "灵犀智造", "光启云网",
             "深瞳算法", "联创物联", "天工智能", "慧眼科技"]
CITIES = ["北京", "上海", "深圳", "杭州", "合肥", "成都", "南京", "广州"]
EXPS = ["1-3年", "3-5年", "5-10年", "经验不限"]
EDUS = ["本科", "硕士", "本科及以上", "硕士及以上"]

JD_TEMPLATES = [
    "岗位职责：\n1. 负责{core}相关系统的设计、开发与持续优化；\n2. 参与{core}方向的新技术调研与方案落地；\n3. 与产品、测试团队协作，保障项目高质量交付。\n任职要求：\n1. 熟练掌握{skills}；\n2. 具备良好的工程素养与团队协作能力；\n3. 有{bonus}相关经验者优先。",
    "我们正在寻找一位专注{core}方向的工程师。你将负责：基于{skills_a}构建核心能力，推动{skills_b}在实际业务中的应用。\n要求：熟悉{skills}；了解{bonus}者优先；有较强的问题定位与解决能力。",
    "岗位描述：承担{core}模块的研发工作，深入使用{skills_a}等技术栈，参与{skills_b}能力建设。\n任职要求：掌握{skills}；具备扎实的数据结构与算法基础；有{bonus}经验加分。",
]


def _sample_skills(l1_terms: list[str], rng: random.Random) -> tuple[list[str], list[str], list[str]]:
    """从 L1 域词条中采样：核心 2 + 要求 4-6 + 加分 1-3。"""
    pool = l1_terms[:]
    rng.shuffle(pool)
    core = pool[:2]
    required = pool[2: 2 + rng.randint(4, 6)]
    bonus = pool[len(core) + len(required): len(core) + len(required) + rng.randint(1, 3)]
    return core, required, bonus


def generate(n: int = 120, seed: int = 42) -> tuple[str, str]:
    rng = random.Random(seed)
    conn = db.connect()
    skills = db.load_skills(conn)
    conn.close()
    if not skills:
        raise RuntimeError("统一库为空，请先运行 pipeline.import_dictionary")

    by_l1: dict[str, list[str]] = {}
    for s in skills:
        if s["l1_code"] in TITLE_TEMPLATES:
            by_l1.setdefault(s["l1_code"], []).append(s["skill_term"])

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = config.DATA_DIR / "sample_jds.csv"
    truth_path = config.DATA_DIR / "sample_ground_truth.json"

    rows, truth = [], {}
    seen_titles: set[str] = set()
    for i in range(n):
        l1 = rng.choice(list(by_l1.keys()))
        # 保证 (岗位+公司+收录时间) 唯一，避免幂等去重误伤测试样本
        while True:
            title = rng.choice(TITLE_TEMPLATES[l1])
            company = rng.choice(COMPANIES)
            key = f"{title}|{company}"
            if key not in seen_titles:
                seen_titles.add(key)
                break
        city = rng.choice(CITIES)
        core, required, bonus = _sample_skills(by_l1[l1], rng)

        template = rng.choice(JD_TEMPLATES)
        jd = template.format(
            core="、".join(core),
            skills="、".join(core + required),
            skills_a="、".join((core + required)[:3]),
            skills_b="、".join((core + required)[3:] or core),
            bonus="、".join(bonus) if bonus else "相关领域",
        )
        salary = f"{rng.randint(12, 40)}-{rng.randint(41, 60)}K"
        rows.append({
            "岗位": title, "公司": company, "城市": city, "薪资": salary,
            "经验": rng.choice(EXPS), "学历": rng.choice(EDUS),
            "JD描述": jd, "来源平台": "synthetic-sample",
            "收录时间": f"2026-08-{(i % 28) + 1:02d}",
        })
        truth[f"sample_jds.csv__{i}"] = sorted(set(core + required + bonus))

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(truth_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2)

    print(f"已生成 {n} 条样例 JD: {csv_path}")
    print(f"真值标注: {truth_path}")
    return str(csv_path), str(truth_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成合成样例 JD 与真值标注")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(args.count, args.seed)


if __name__ == "__main__":
    main()
