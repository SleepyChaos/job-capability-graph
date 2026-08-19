from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedJobSegment:
    segment_type: str
    start_offset: int
    end_offset: int
    text: str
    heading: str | None
    confidence: int


CHINESE_HEADINGS = {
    "岗位职责": "responsibility",
    "工作职责": "responsibility",
    "职位职责": "responsibility",
    "主要职责": "responsibility",
    "工作内容": "responsibility",
    "职位描述": "responsibility",
    "岗位描述": "responsibility",
    "任职要求": "required",
    "岗位要求": "required",
    "职位要求": "required",
    "任职资格": "required",
    "任职条件": "required",
    "能力要求": "required",
    "基本要求": "required",
    "加分项": "bonus",
    "优先条件": "bonus",
    "优先资格": "bonus",
    "应用场景": "scenario",
    "业务场景": "scenario",
    "工作场景": "scenario",
    "落地场景": "scenario",
    "公司介绍": "about",
    "关于我们": "about",
    "福利待遇": "benefit",
    "薪酬福利": "benefit",
}

ENGLISH_HEADINGS = {
    "responsibilities": "responsibility",
    "key responsibilities": "responsibility",
    "what you'll do": "responsibility",
    "what you will do": "responsibility",
    "the role": "responsibility",
    "role": "responsibility",
    "requirements": "required",
    "qualifications": "required",
    "minimum qualifications": "required",
    "required qualifications": "required",
    "what we're looking for": "required",
    "what we are looking for": "required",
    "who you are": "required",
    "preferred qualifications": "bonus",
    "nice to have": "bonus",
    "preferred skills": "bonus",
    "about us": "about",
    "about the company": "about",
    "application scenarios": "scenario",
    "use cases": "scenario",
    "benefits": "benefit",
    "equal opportunity": "about",
}

BONUS_MARKERS = (
    "优先",
    "加分",
    "者佳",
    "nice to have",
    "preferred",
    "a plus",
    "bonus",
)

SCENARIO_MARKERS = (
    "应用场景",
    "业务场景",
    "落地场景",
    "部署场景",
    "application scenario",
    "use case",
)
RESPONSIBILITY_MARKERS = (
    "负责",
    "参与",
    "主导",
    "承担",
    "开发",
    "设计",
    "搭建",
    "推进",
    "优化",
    "研究",
    "落地",
    "lead ",
    "develop ",
    "design ",
    "build ",
    "drive ",
    "own ",
    "responsible for",
    "collaborate ",
)
REQUIREMENT_MARKERS = (
    "熟悉",
    "掌握",
    "具备",
    "要求",
    "本科",
    "硕士",
    "博士",
    "经验",
    "proficient",
    "experience",
    "qualification",
    "required",
    "familiar",
    "degree",
    "years of",
    "ability to",
)
ABOUT_MARKERS = (
    "about us",
    "equal employment",
    "equal opportunity",
    "we value diversity",
    "公司简介",
    "公司介绍",
)

_CHINESE_HEADING_PATTERN = re.compile(
    "|".join(re.escape(value) for value in sorted(CHINESE_HEADINGS, key=len, reverse=True))
)
_ENGLISH_HEADING_PATTERN = re.compile(
    r"(?im)^[ \t]*("
    + "|".join(re.escape(value) for value in sorted(ENGLISH_HEADINGS, key=len, reverse=True))
    + r")[ \t]*[:：]?[ \t]*(?:\r?\n|$)"
)
_SPLIT_PATTERN = re.compile(
    r"\r?\n+|(?<=[。；;])|(?=\s*(?:[-•●▪]\s+|\d{1,2}[.、)]\s+|[（(]\d{1,2}[）)]\s*))"
)
_PREFIX_PATTERN = re.compile(r"^(?:[-•●▪]\s*|\d{1,2}[.、)]\s*|[（(]\d{1,2}[）)]\s*)")


class JobStructureParser:
    def parse(self, text: str) -> list[ParsedJobSegment]:
        if not text or not text.strip():
            return []
        markers = self._headings(text)
        zones: list[tuple[int, int, str | None, str | None]] = []
        cursor = 0
        for index, (start, end, heading, segment_type) in enumerate(markers):
            if cursor < start:
                zones.append((cursor, start, None, None))
            next_start = markers[index + 1][0] if index + 1 < len(markers) else len(text)
            zones.append((end, next_start, heading, segment_type))
            cursor = next_start
        if not markers:
            zones.append((0, len(text), None, None))
        elif cursor < len(text):
            zones.append((cursor, len(text), None, None))

        segments: list[ParsedJobSegment] = []
        occupied: set[tuple[int, int]] = set()
        for start, end, heading, heading_type in zones:
            for item_start, item_end in self._split(text, start, end):
                if (item_start, item_end) in occupied:
                    continue
                value = text[item_start:item_end]
                segment_type, confidence = self._classify(value, heading_type)
                if segment_type in {"about", "benefit"}:
                    continue
                occupied.add((item_start, item_end))
                segments.append(
                    ParsedJobSegment(
                        segment_type=segment_type,
                        start_offset=item_start,
                        end_offset=item_end,
                        text=value,
                        heading=heading,
                        confidence=confidence,
                    )
                )
        return sorted(segments, key=lambda item: item.start_offset)

    @staticmethod
    def _headings(text: str) -> list[tuple[int, int, str, str]]:
        found: list[tuple[int, int, str, str]] = []
        for match in _CHINESE_HEADING_PATTERN.finditer(text):
            heading = match.group(0)
            end = match.end()
            while end < len(text) and text[end] in " :：\t\r\n":
                end += 1
            found.append((match.start(), end, heading, CHINESE_HEADINGS[heading]))
        for match in _ENGLISH_HEADING_PATTERN.finditer(text):
            heading = match.group(1)
            found.append(
                (match.start(), match.end(), heading, ENGLISH_HEADINGS[heading.casefold()])
            )
        selected: list[tuple[int, int, str, str]] = []
        for marker in sorted(found, key=lambda item: (item[0], -(item[1] - item[0]))):
            if selected and marker[0] < selected[-1][1]:
                continue
            selected.append(marker)
        return selected

    @staticmethod
    def _split(text: str, start: int, end: int) -> list[tuple[int, int]]:
        zone = text[start:end]
        boundaries = [0]
        boundaries.extend(match.end() for match in _SPLIT_PATTERN.finditer(zone))
        boundaries.append(len(zone))
        spans: list[tuple[int, int]] = []
        for left, right in zip(boundaries, boundaries[1:], strict=False):
            raw = zone[left:right]
            leading = len(raw) - len(raw.lstrip())
            item_start = start + left + leading
            value = text[item_start : start + right].rstrip()
            prefix = _PREFIX_PATTERN.match(value)
            if prefix:
                item_start += prefix.end()
                value = text[item_start : start + right].strip()
                item_start = text.find(value, item_start, start + right) if value else item_start
            item_end = item_start + len(value)
            if len(value) >= 6 and item_end > item_start:
                spans.append((item_start, item_end))
        return spans

    @staticmethod
    def _classify(text: str, heading_type: str | None) -> tuple[str, int]:
        lowered = text.casefold()
        if heading_type:
            if heading_type == "scenario":
                return "scenario", 92
            if any(marker in lowered for marker in BONUS_MARKERS):
                return "bonus", 95
            return heading_type, 92
        if any(marker in lowered for marker in ABOUT_MARKERS):
            return "about", 90
        # 保守策略：只有开头即出现场景标记的条目才归为场景，避免污染职责/要求切分。
        prefix = lowered[:14]
        if any(marker in prefix for marker in SCENARIO_MARKERS):
            return "scenario", 72
        if any(marker in lowered for marker in BONUS_MARKERS):
            return "bonus", 85
        responsibility_score = sum(marker in lowered for marker in RESPONSIBILITY_MARKERS)
        requirement_score = sum(marker in lowered for marker in REQUIREMENT_MARKERS)
        if responsibility_score > requirement_score and responsibility_score:
            return "responsibility", 78
        if requirement_score:
            return "required", 75
        return "unknown", 40


def task_parts(text: str) -> tuple[str | None, str, str | None]:
    cleaned = re.sub(r"\s+", " ", text).strip(" ：:;；。")
    lowered = cleaned.casefold()
    action: str | None = None
    action_end = 0
    for marker in RESPONSIBILITY_MARKERS:
        index = lowered.find(marker)
        if index >= 0 and (action is None or index < action_end):
            action = cleaned[index : index + len(marker)].strip()
            action_end = index + len(marker)
    task_object = cleaned[action_end:].strip(" ，,：:") if action else cleaned
    expected: str | None = None
    for separator in ("，确保", ", ensure", " to ensure", "，实现", "，提升"):
        index = task_object.casefold().find(separator.casefold())
        if index >= 0:
            expected = task_object[index + len(separator) :].strip()
            task_object = task_object[:index].strip()
            break
    return action, task_object[:500], expected[:500] if expected else None


# 英文功能词：它们在任意 JD 里都出现，作为特征只会让英文 JD 互相吸引。
# 实测中 `and` 是职责通道第 11 高频的 token，是英文 JD 被聚成一堆的直接原因。
ASCII_STOPWORDS = frozenset(
    """a an the and or of for to in on at with by from as is are be been being
    will would shall should can could may might must have has had do does did
    this that these those it its you your we our they their he she his her
    not no nor but if then than so such other others any all both each more most
    some who whom which what when where why how about into over under again
    further once here there when both few own same too very just also""".split()
)

# 中文一律切成字符二元组。中文没有空格分词，原先按「连续汉字块」取词等于取任意长度
# 的切片：两句几乎同义的职责——「负责具身智能机器人运动控制算法的设计与实现」与
# 「负责人形机器人运动控制算法开发与调优」——切点不同，token 交集为空，
# 而它们明明都含「运动控制算法」。实测 31,565 个职责 token 里 74% 只出现在一份 JD 中，
# 权重最高的职责通道（0.326）因此一直在空转。
# 二元组会产生噪声词，但 IDF 加权会把高频二元组压下去，这是无分词器场景的标准做法。
CHINESE_BIGRAM_MIN_RUN = 2
MAX_CLUSTER_TOKENS = 400


def chinese_bigrams(run: str) -> list[str]:
    return [run[index : index + 2] for index in range(len(run) - 1)]


def cluster_tokens(text: str) -> list[str]:
    lowered = text.casefold()
    ascii_tokens = [
        token
        for token in re.findall(r"[a-z][a-z0-9+#.\-]{1,30}", lowered)
        if token not in ASCII_STOPWORDS
    ]
    chinese_tokens: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        if len(run) >= CHINESE_BIGRAM_MIN_RUN:
            chinese_tokens.extend(chinese_bigrams(run))
    tokens = ascii_tokens + chinese_tokens
    return list(dict.fromkeys(tokens))[:MAX_CLUSTER_TOKENS]
