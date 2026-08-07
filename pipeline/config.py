"""统一配置：所有路径均可用环境变量覆盖，无硬编码工作区路径。"""
import os
from pathlib import Path

# 项目根目录（job-capability-graph/）
ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """轻量 .env 加载（无 python-dotenv 依赖）：不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# 项目根 .env（LLM Key 等敏感配置，不入代码库）
_load_dotenv(ROOT / ".env")

# 统一数据库（单一事实源）
DB_PATH = Path(os.environ.get("JCG_DB", ROOT / "db" / "unified.db"))
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# 管线资源目录
PIPELINE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PIPELINE_DIR / "assets"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

# 词典文件（CSV 格式：skill_term, skill_term_raw, l4_type, l1_code, l2_name, l3_name）
DICTIONARY_FILES = [
    ASSETS_DIR / "it_terms.csv",        # 新一代信息技术（AI/大数据/物联网/智能系统）
    ASSETS_DIR / "embodied_terms.csv",  # 存量具身智能词典（管线可迁移性验证集）
]

# L1 技术域编码 → 名称
L1_DOMAIN_NAMES = {
    "AI": "人工智能",
    "BD": "大数据",
    "IOT": "物联网",
    "IS": "智能系统",
    # 存量具身智能域（保留原编码作验证集）
    "T1": "具身智能-算法与智能",
    "T2": "具身智能-感知传感",
    "T3": "具身智能-硬件本体",
    "T4": "具身智能-仿真与数据",
    "T5": "具身智能-软件与系统",
    "T6": "具身智能-交互与标准",
    "T7": "具身智能-应用场景",
}

# LLM（OpenAI 兼容接口，替换原 Coze SDK）。未配置 API Key 时自动降级为规则方案。
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

# 聚类参数（沿用项目二环境变量约定）
CLUSTER_BATCH_SIZE = int(os.environ.get("CLUSTER_BATCH_SIZE", "500"))
CLUSTER_THRESHOLD = float(os.environ.get("CLUSTER_THRESHOLD", "0.35"))
CLUSTER_MIN_SHARED_KEYWORDS = int(os.environ.get("CLUSTER_MIN_SHARED_KEYWORDS", "1"))
CLUSTER_MAX_DF = float(os.environ.get("CLUSTER_MAX_DF", "1.0"))
CLUSTER_MAX_CLUSTER_SIZE = int(os.environ.get("CLUSTER_MAX_CLUSTER_SIZE", "50"))
CLUSTER_MAX_EVICTION_DEPTH = int(os.environ.get("CLUSTER_MAX_EVICTION_DEPTH", "3"))
