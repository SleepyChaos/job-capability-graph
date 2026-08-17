"""窗口 A-1 子任务 1.2:L3 覆盖盲区排查分析。

输入:audit_export_extraction_data.py 导出的 .audit-data/ TSV 快照。
语料口径:run_code=jdparse_e7328e6370fbee62e79d2098 覆盖的全部 3,718 份 JD 正文;
分段:有证据段 = accepted>0(1,546 份),无 accepted 证据段 = 2,172 份
(其中零评估 2,040 + 仅 needs_review 132)。

方法(docs/08 §3.2):
1. 高频词/词组抽取:英文按 ASCII 词元(casefold 合并),中文按 2–4 字 n-gram
2. 减去 md_technology_alias 已收词(英文精确匹配;n-gram 额外剔除「是别名子串」
   或「包含别名」的碎片/复合,这类已被现有词覆盖)
3. 排除通用编程/办公/HR/泛业务词(backend/tools/audit_data/generic_term_stoplist.txt)
4. 候选技术点 = 人工判读归并(编码在下方 CANDIDATES),频次由脚本计算

用法:
    python backend/tools/audit_l3_coverage_gaps.py --discover   # 探索模式:打印原始候选池
    python backend/tools/audit_l3_coverage_gaps.py              # 输出报告片段(stdout)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from audit_tsv import iter_mysql_tsv

CORPUS_COLS = [
    "job_posting_id",
    "job_title_normalized",
    "job_title_raw",
    "job_level_code",
    "region_text",
    "parse_status_code",
    "parse_quality_score",
    "accepted_cnt",
    "review_cnt",
    "distinct_node_cnt",
    "jd_clean_text",
]
INVENTORY_COLS = [
    "alias_id",
    "alias_text",
    "normalized_alias",
    "alias_len",
    "is_matchable",
    "alias_type_code",
    "source_type_code",
    "node_level",
    "node_code",
    "node_name",
    "l3_code",
    "l3_name",
]
NODES_COLS = [
    "technology_node_id",
    "technology_code",
    "level_code",
    "technology_name",
    "parent_code",
    "parent_name",
    "parent_level",
]

ASCII_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#._\-]{1,24}", re.ASCII)
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

# 候选新增技术点表(人工判读归并;频次与 JD 数由脚本计算)。
# (规范名, 匹配正则, 建议 L2, 词表现状注记, 置信说明)
# 词表现状:缺失=词表无该词;零命中=词表有等价词但 run 3 未打中;部分=词表覆盖了近义变体
CANDIDATES: list[tuple[str, str, str, str, str]] = [
    (
        "PyTorch/TensorFlow 深度学习框架",
        r"\bpytorch\b|\btensorflow\b",
        "T5.03 开发与部署工具链",
        "缺失",
        "算法岗最高频工具词;框架属工程工具链而非技术点本身,"
        "是否收录取决于词表口径(置信高、口径待窗口 B 定)",
    ),
    (
        "ROS2",
        r"\bros2\b|\bros\s?2\b",
        "T5.01 机器人操作系统",
        "缺失(词表仅有 'ros')",
        "'ros2' 因 ASCII 词边界无法被 'ros' 命中(匹配器要求非词字符边界);"
        "机器人软件岗高频,是漏报的直接成因",
    ),
    (
        "MuJoCo/Isaac/Gazebo/PyBullet 仿真栈",
        r"\bmujoco\b|\bisaac\w*\b|\bgazebo\b|\bpybullet\b|\bgym\b",
        "T4.03 仿真平台与环境",
        "部分('仿真平台/仿真引擎'泛词已收,具体引擎名全缺)",
        "具身 RL 训练仿真主流栈,具体名比泛词区分度高;置信高",
    ),
    (
        "IMU 惯性测量单元",
        r"\bimu\b|惯性测量|惯性导航",
        "T2.04 位置与惯性",
        "缺失",
        "感知硬件高频词;置信高",
    ),
    (
        "EtherCAT/CANopen/DDS 实时通信",
        r"\bethercat\b|\bcanopen\b|\bdds\b|\brs485\b|\bi2c\b|\buart\b|\bspi\b",
        "T5.02 中间件与通信",
        "缺失",
        "机器人实时总线与通信中间件,电控/嵌入式岗高频;置信高",
    ),
    (
        "嵌入式实时系统(RTOS/MCU/STM32)",
        r"\brtos\b|\bmcu\b|\bstm32\b|\bdsp\b",
        "T5.03 开发与部署工具链",
        "缺失",
        "嵌入式底座词形;归工具链或芯片方向需窗口 B 定;置信高",
    ),
    (
        "TensorRT/ONNX/OpenVINO/TVM 推理引擎",
        r"tensor\s?rt|\bonnx\b|\bopenvino\b|\btvm\b|\bncnn\b|\bmnn\b|\brknn\b|\btflite\b",
        "T5.03 开发与部署工具链",
        "缺失",
        "docs/07 证据 3(JD 245)直接指向的缺口;部署岗核心;置信高",
    ),
    (
        "vLLM/DeepSpeed/TensorRT-LLM 推理服务与训练加速",
        r"\bvllm\b|deepspeed|tensorrt-llm|lmdeploy|sglang|\bkv\s?cache\b|kv缓存",
        "T5.03 开发与部署工具链",
        "缺失",
        "LLM 工程 serving/训练加速栈;docs/08 §3.2 指定核实项;置信高",
    ),
    (
        "CUDA/cuDNN GPU 并行计算",
        r"\bcuda\b|cudnn|\bgpu\b",
        "T5.03 开发与部署工具链",
        "缺失",
        "GPU 编程与加速;置信高",
    ),
    (
        "Jetson/Orin 端侧算力平台",
        r"\bjetson\b|\borin\b|\bxavier\b",
        "T3.08 芯片与算力硬件",
        "缺失",
        "机器人端侧算力硬件;docs/08 §3.2 指定核实项;置信高",
    ),
    (
        "模型量化(INT8/FP8/PTQ/QAT)",
        r"\bfp8\b|\bint8\b|\bint4\b|\bfp16\b|量化|\bptq\b|\bqat\b",
        "T1.01 具身基础模型与VLA(或 T5.03)",
        "部分('量化'泛词未收)",
        "部署侧核心技术点,docs/08 §3.2 指定核实项;置信高",
    ),
    (
        "大模型部署与推理优化(工程侧)",
        r"推理加速|推理优化|推理框架|模型部署|端侧部署|边缘部署|端侧|\btrt\b",
        "T1.01 具身基础模型与VLA",
        "缺失(T1.01.06 的 L4 词全是论文术语,零命中)",
        "docs/07 明确指出 T1.01.06 表面词匹配不上招聘语料;置信高",
    ),
    (
        "Sim2Real 仿真到现实迁移",
        r"sim\s?2\s?real|sim[-\s]?to[-\s]?real|仿真到实|虚实迁移|虚实结合",
        "T4.04 Sim-to-Real迁移",
        "零命中(T4.04 子树无任何命中)",
        "L2 节点存在但 run 3 零命中,子树表面词与招聘语料不匹配;docs/08 §3.2 指定核实项;置信高",
    ),
    (
        "MPC/WBC 模型预测与全身控制",
        r"\bmpc\b|\bwbc\b|模型预测控制|全身控制",
        "T1.03 运动规划与控制",
        "部分('全身控制'中文别名仅命中 12)",
        "运控岗高频算法缩写;置信高",
    ),
    (
        "PPO/SAC/Diffusion Policy 等 RL 算法词形",
        r"\bppo\b|\bsac\b|diffusion\s?polic|扩散策略",
        "T1.05 学习与训练方法",
        "部分(中文词已收,英文缩写全缺)",
        "具身 RL 主流算法缩写;置信高(注意 sac/ppo 需词边界防误配)",
    ),
    (
        "VLM/Transformer/LLM 模型词形",
        r"\bvlm\b|transformer|\bllm\b|多模态模型",
        "T1.01 具身基础模型与VLA",
        "部分(中文'多模态大模型'已收但被判定过宽)",
        "VLM(视觉语言模型)与 VLA 是不同技术点,当前全被并到 T1.01.11;置信高",
    ),
    (
        "FOC/PMSM/BLDC 电机控制算法",
        r"\bfoc\b|\bpmsm\b|\bbldc\b|矢量控制|磁场定向",
        "T3.05 关节与驱动模组",
        "部分('电机/伺服驱动'已收,算法词缺)",
        "电机驱动算法岗高频(样本含 foc算法工程师);置信高",
    ),
    (
        "OpenCV/视觉算法库",
        r"\bopencv\b|\bpcl\b|点云库",
        "T1.06 感知认知与理解",
        "缺失",
        "视觉/点云开发标配库;置信中高(工具词口径同 PyTorch)",
    ),
    (
        "NeRF/3DGS 三维重建",
        r"\bnerf\b|3dgs|三维重建|神经辐射场",
        "T1.06 感知认知与理解",
        "缺失",
        "样本标题含『3dgs/世界模型/生成式重建方向』;置信中高",
    ),
    (
        "NPU/FPGA 异构算力",
        r"\bnpu\b|\bfpga\b",
        "T3.08 芯片与算力硬件",
        "部分('ai芯片'已收)",
        "端侧异构算力词形;置信中",
    ),
    (
        "AGV",
        r"\bagv\b",
        "T3.03 整机-臂与复合机器人(T3.03.08 名含 AGV)",
        "缺失(节点名含 AGV 但无该别名)",
        "节点 T3.03.08 移动机器人(AMR/AGV) 存在,'amr' 已收而 'agv' 缺;置信高",
    ),
    (
        "MoveIt 运动规划框架",
        r"\bmoveit\b",
        "T1.04 导航与定位(或 T5.03)",
        "缺失",
        "机械臂规划开源框架;置信中",
    ),
    (
        "规控/纯视觉(中文词形)",
        r"规控|纯视觉|端到端感知",
        "T1.03 运动规划与控制 / T1.01",
        "缺失",
        "机器人/自动驾驶领域缩略语与方案表述;置信中",
    ),
    (
        "整机泛称(robot/robotics/humanoid)",
        r"\brobot\b|\brobots\b|\brobotics\b|\bhumanoid\b",
        "T3.01 整机-人形机器人",
        "部分(中文'人形机器人'已收,英文全缺)",
        "英文 JD 段的整机泛称;是否作为技术点收录取决于口径;置信中",
    ),
    (
        "结构设计/热管理/电控 BMS(机械电子工程项)",
        r"结构设计|热设计|热管理|散热|\bbms\b|电控|电源管理|电池管理",
        "T3.07 结构件与材料 / T3.05 关节与驱动模组",
        "缺失",
        "机械/电子工程岗高频;属『工程实践类』范围争议项,由窗口 B 结合 1.3 标注定夺;置信中",
    ),
    (
        "学术会议/论文信号(CVPR/ICRA/NeurIPS 等)",
        r"\bcvpr\b|\bicra\b|\bneurips\b|\biccv\b|\biclr\b|\biros\b|\bcorl\b|\bicml\b|\beccv\b|\bra-l\b",
        "(不建议作为技术点收录)",
        "缺失",
        "资质信号而非技术点;建议不收,或单列为质量信号字段;置信高(不收录)",
    ),
    (
        "整机型号词(宇树 GO2/A1/B1/H1、灵巧手 Dex 系列等)",
        r"\bgo2\b|\bgo1\b|\ba1\b|\bb1\b|\bb2\b|\bh1\b|\bh2\b|\baliengo\b|\bdex\d",
        "T3.01/T3.02 整机与灵巧手",
        "部分(词表有 53 个型号词但与语料型号不重叠)",
        "语料中出现的是在售型号,词表收的是学术型号;是否收录取决于『整机型号追踪』是否是研究目标;置信中",
    ),
]


def load(data_dir: Path):
    corpus = list(iter_mysql_tsv((data_dir / "04_jd_corpus.tsv").read_text("utf-8"), CORPUS_COLS))
    inventory = list(
        iter_mysql_tsv((data_dir / "02_alias_inventory.tsv").read_text("utf-8"), INVENTORY_COLS)
    )
    return corpus, inventory


def load_stoplist(path: Path) -> set[str]:
    words = set()
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.casefold())
    return words


def segment(corpus: list) -> tuple[list, list]:
    with_ev = [c for c in corpus if int(c["accepted_cnt"]) > 0]
    without_ev = [c for c in corpus if int(c["accepted_cnt"]) == 0]
    return with_ev, without_ev


def count_pattern(rows: list, pattern: str) -> tuple[int, int]:
    """返回 (出现总次数, 出现 JD 数)。"""
    regex = re.compile(pattern, re.IGNORECASE)
    total = 0
    jds = 0
    for c in rows:
        text = c["jd_clean_text"] or ""
        n = len(regex.findall(text))
        if n:
            total += n
            jds += 1
    return total, jds


def discover_ascii_tokens(rows: list, alias_set: set[str], stop: set[str], top: int) -> list:
    counter: Counter[str] = Counter()
    jd_counter: Counter[str] = Counter()
    for c in rows:
        text = (c["jd_clean_text"] or "").lower()
        found = set(ASCII_TOKEN_RE.findall(text))
        for tok in found:
            if tok in alias_set or tok in stop or len(tok) < 2:
                continue
            counter[tok] += 1
            jd_counter[tok] += 1
    return [(tok, jd_counter[tok]) for tok, _ in counter.most_common(top)]


def discover_cjk_ngrams(rows: list, alias_set: set[str], stop: set[str], top: int) -> list:
    """2–4 字 n-gram;剔除停用词、别名子串/包含别名的碎片(已被现有词覆盖)。

    停用词与别名同样按「子串」剔除:gram 是任何 ≥2 字停用词的子串即视为模板碎片。
    """
    aliases_ge2 = [a for a in alias_set if len(a) >= 2]
    stop_ge2 = [s for s in stop if len(s) >= 2]
    counter: Counter[str] = Counter()
    jd_counter: Counter[str] = Counter()
    for c in rows:
        text = c["jd_clean_text"] or ""
        grams: set[str] = set()
        for n in (2, 3, 4):
            for i in range(len(text) - n + 1):
                g = text[i : i + n]
                if not CJK_RE.fullmatch(g):
                    continue
                if g in stop or g in alias_set:
                    continue
                if any(g in a for a in aliases_ge2):
                    continue  # 是已有别名的子串碎片
                if any(g in s for s in stop_ge2):
                    continue  # 是停用词的子串碎片
                if any(s in g for s in stop_ge2):
                    continue  # 包含停用词的模板复合(发现池足够保守,候选由人工判读兜底)
                grams.add(g)
        for g in grams:
            counter[g] += 1
            jd_counter[g] += 1
    return [(gram, jd_counter[gram]) for gram, _ in counter.most_common(top)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / ".audit-data"
    )
    parser.add_argument("--discover", action="store_true", help="探索模式:打印原始候选池,不产报告")
    parser.add_argument("--discover-top", type=int, default=150)
    args = parser.parse_args()

    corpus, inventory = load(args.data_dir)
    stop = load_stoplist(
        Path(__file__).resolve().parent / "audit_data" / "generic_term_stoplist.txt"
    )
    alias_set = {a["normalized_alias"].casefold() for a in inventory}
    with_ev, without_ev = segment(corpus)

    out = sys.stdout.write
    if args.discover:
        for label, rows in (
            ("无 accepted 证据段", without_ev),
            ("有证据段", with_ev),
        ):
            out(f"## 探索:{label}({len(rows):,} 份)英文词元 top\n\n")
            out("| 词元 | JD 数 |\n| --- | ---: |\n")
            for tok, j in discover_ascii_tokens(rows, alias_set, stop, args.discover_top):
                out(f"| {tok} | {j} |\n")
            out(f"\n## 探索:{label}中文 n-gram top\n\n")
            out("| n-gram | JD 数 |\n| --- | ---: |\n")
            for gram, j in discover_cjk_ngrams(rows, alias_set, stop, args.discover_top):
                out(f"| {gram} | {j} |\n")
            out("\n")
        return 0

    # ---------- 报告模式 ----------
    out("## 1. 语料与分段口径\n\n")
    out(f"- 语料:run 3 覆盖的全部 {len(corpus):,} 份 JD 正文(biz_job_posting.jd_clean_text)\n")
    out(f"- 有证据段(accepted>0):{len(with_ev):,} 份;无 accepted 证据段:{len(without_ev):,} 份\n")
    out("  (其中零评估 2,040 份、仅 needs_review 132 份;docs/08 §2.1 的 2,111 为旧统计口径)\n")
    matchable = sum(1 for a in inventory if a["is_matchable"] == "1")
    out(f"- 词表:可匹配别名 {matchable:,} 个(run 3 实际命中 208 个)\n\n")

    out("## 2. 候选新增技术点清单(按出现 JD 数排序)\n\n")
    out(
        "| 候选技术点 | 出现JD数(无证据段) | 出现JD数(有证据段) | 总JD数 | 出现次数(无/有) "
        "| 词表现状 | 建议挂载 L2 | 置信说明 |\n"
    )
    out("| --- | ---: | ---: | ---: | --- | --- | --- | --- |\n")
    scored = []
    for name, pattern, l2, status, note in CANDIDATES:
        tot_wo, jd_wo = count_pattern(without_ev, pattern)
        tot_w, jd_w = count_pattern(with_ev, pattern)
        scored.append((jd_wo + jd_w, jd_wo, jd_w, tot_wo, tot_w, name, status, l2, note))
    for total, jd_wo, jd_w, tot_wo, tot_w, name, status, l2, note in sorted(scored, reverse=True):
        out(
            f"| {name} | {jd_wo} | {jd_w} | {total} | {tot_wo}/{tot_w} "
            f"| {status} | {l2} | {note} |\n"
        )
    cover_wo = sum(
        1
        for c in without_ev
        if any(re.search(p, c["jd_clean_text"] or "", re.IGNORECASE) for _, p, *_ in CANDIDATES)
    )
    out(
        f"\n**覆盖影响**:无 accepted 证据的 {len(without_ev):,} 份 JD 中,"
        f"{cover_wo} 份({cover_wo / len(without_ev):.0%})至少命中一个上述候选词——"
        f"即仅收录本清单即可为这部分 JD 补上首批技术证据。\n\n"
    )

    out("## 3. 已知线索核实(docs/08 §3.2 指定)\n\n")
    out("| 线索 | 语料出现次数 / JD 数 | 词表现状 |\n| --- | --- | --- |\n")
    kv_total, kv_jd = count_pattern(corpus, r"kv\s?cache|kv缓存")
    out(f"| KV Cache | {kv_total} / {kv_jd} | 词表缺失 |\n")
    for lead in (
        "TensorRT",
        "vLLM",
        "ONNX Runtime",
        "CUDA",
        "Jetson Orin",
        "Sim2Real",
        "模型量化",
        "端侧部署",
    ):
        mapping = {
            "TensorRT": r"tensor\s?rt",
            "vLLM": r"vllm",
            "ONNX Runtime": r"onnx",
            "CUDA": r"\bcuda\b|cudnn",
            "Jetson Orin": r"jetson|orin",
            "Sim2Real": r"sim\s?2\s?real|sim[-\s]?to[-\s]?real|仿真到实",
            "模型量化": r"量化|fp8|int8",
            "端侧部署": r"端侧|边缘部署",
        }
        t, j = count_pattern(corpus, mapping[lead])
        out(f"| {lead} | {t} / {j} | 见候选清单对应行 |\n")
    out("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
