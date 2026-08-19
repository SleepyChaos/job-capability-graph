from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.ingestion.models import (
    FileImportRowResult,
    FileImportRun,
    SpreadsheetRow,
)
from app.modules.taxonomy.models import (
    TechnologyAlias,
    TechnologyDomain,
    TechnologyNode,
    TechnologyNodeDomain,
    TechnologyTaxonomyVersion,
)

DOMAIN_COLORS = {
    "T1": "#1769e0",
    "T2": "#0b9c93",
    "T3": "#38a8dc",
    "T4": "#6fbd73",
    "T5": "#f2a43a",
    "T6": "#8e7ad5",
    "T7": "#94a3b8",
}

SHEET_NAMES = ("L1技术域", "L2技术类", "L3技术点", "L4技术词")

# 只对已冻结的历史版本卡死行数，作为回归护栏；治理新版的行数由变更集决定，
# 不在这里写死（否则每次升版都要改代码）。
EXPECTED_SHEET_COUNTS_BY_VERSION = {
    "v1.1": {
        "L1技术域": 7,
        "L2技术类": 43,
        "L3技术点": 229,
        "L4技术词": 1872,
    },
}

REQUIRED_FIELDS = {
    "L1技术域": {"L1编码", "技术域", "定义"},
    "L2技术类": {"L2编码", "技术类", "所属L1", "所属技术域", "定义"},
    "L3技术点": {"L3编码", "L3标准名", "L2编码", "L1编码"},
    "L4技术词": {"技术词", "L4类型", "挂载L3编码", "L2编码", "L1编码"},
}


class TaxonomyImportError(ValueError):
    pass


@dataclass(frozen=True)
class TaxonomyImportResult:
    taxonomy_version_id: int
    version_code: str
    domain_count: int
    l1_count: int
    l2_count: int
    l3_count: int
    l4_count: int
    alias_count: int
    domain_relation_count: int
    already_published: bool


def normalize_term(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def l4_code(parent_code: str, term: str) -> str:
    fingerprint = hashlib.sha256(f"{parent_code}\0{normalize_term(term)}".encode()).hexdigest()
    return f"L4-{fingerprint[:20].upper()}"


def semantic_role(source_type: str) -> str:
    return {
        "指标词": "metric",
        "型号词": "product",
        "组合词": "tool",
        "细分词": "other",
        "碎片词": "other",
    }.get(source_type, "other")


class TaxonomyImportService:
    def __init__(self, session: Session):
        self.session = session

    def publish(
        self,
        *,
        file_import_run_id: int,
        version_code: str,
        version_name: str,
        effective_date: date,
        domain_version: str,
        change_summary: str | None = None,
    ) -> TaxonomyImportResult:
        import_run = self.session.get(FileImportRun, file_import_run_id)
        if import_run is None:
            raise TaxonomyImportError(f"导入运行不存在：{file_import_run_id}")
        existing_version = self.session.scalar(
            select(TechnologyTaxonomyVersion).where(
                TechnologyTaxonomyVersion.version_code == version_code
            )
        )
        if existing_version is not None:
            if existing_version.source_file_asset_id != import_run.file_asset_id:
                raise TaxonomyImportError(f"版本{version_code}已绑定其他源文件")
            return self._result(existing_version, already_published=True)

        rows = self._load_rows(import_run.file_asset_id)
        self._validate(rows, version_code)
        version = TechnologyTaxonomyVersion(
            version_code=version_code,
            version_name=version_name,
            source_file_asset_id=import_run.file_asset_id,
            effective_date=effective_date,
            version_status_code="draft",
            change_summary=change_summary or f"由技术词主数据工作簿{version_code}可追溯导入。",
        )
        self.session.add(version)
        self.session.flush()

        domains: dict[str, TechnologyDomain] = {}
        nodes: dict[str, TechnologyNode] = {}

        for index, source_row in enumerate(rows["L1技术域"], start=1):
            payload = source_row.row_payload_json
            code = self._text(payload, "L1编码")
            name = self._text(payload, "技术域")
            domain = TechnologyDomain(
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                domain_version=domain_version,
                domain_code=code,
                domain_name=name,
                definition_text=self._optional_text(payload, "定义"),
                color_token=DOMAIN_COLORS[code],
                sort_order=index,
            )
            node = TechnologyNode(
                taxonomy_version_id=version.taxonomy_version_id,
                technology_code=code,
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                level_code="L1",
                technology_name=name,
                normalized_name=normalize_term(name),
                definition_text=self._optional_text(payload, "定义"),
            )
            self.session.add_all([domain, node])
            self.session.flush()
            domains[code] = domain
            nodes[code] = node
            self._link_domain(node, domain, source_row)
            self._record_result(import_run, source_row, "technology_node", code)

        for source_row in rows["L2技术类"]:
            payload = source_row.row_payload_json
            code = self._text(payload, "L2编码")
            parent_code = self._text(payload, "所属L1")
            name = self._text(payload, "技术类")
            node = TechnologyNode(
                taxonomy_version_id=version.taxonomy_version_id,
                technology_code=code,
                parent_technology_node_id=nodes[parent_code].technology_node_id,
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                level_code="L2",
                technology_name=name,
                normalized_name=normalize_term(name),
                definition_text=self._optional_text(payload, "定义"),
            )
            self.session.add(node)
            self.session.flush()
            nodes[code] = node
            self._link_domain(node, domains[parent_code], source_row)
            self._record_result(import_run, source_row, "technology_node", code)

        for source_row in rows["L3技术点"]:
            payload = source_row.row_payload_json
            code = self._text(payload, "L3编码")
            parent_code = self._text(payload, "L2编码")
            domain_code = self._text(payload, "L1编码")
            name = self._text(payload, "L3标准名")
            node = TechnologyNode(
                taxonomy_version_id=version.taxonomy_version_id,
                technology_code=code,
                parent_technology_node_id=nodes[parent_code].technology_node_id,
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                level_code="L3",
                technology_name=name,
                normalized_name=normalize_term(name),
                node_type_code="standard_point",
            )
            self.session.add(node)
            self.session.flush()
            nodes[code] = node
            self._link_domain(node, domains[domain_code], source_row)
            self._record_result(import_run, source_row, "technology_node", code)

        for source_row in rows["L4技术词"]:
            payload = source_row.row_payload_json
            term = self._text(payload, "技术词")
            parent_code = self._text(payload, "挂载L3编码")
            domain_code = self._text(payload, "L1编码")
            source_type = self._text(payload, "L4类型")
            code = l4_code(parent_code, term)
            node = TechnologyNode(
                taxonomy_version_id=version.taxonomy_version_id,
                technology_code=code,
                parent_technology_node_id=nodes[parent_code].technology_node_id,
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                level_code="L4",
                technology_name=term,
                normalized_name=normalize_term(term),
                node_type_code="surface_term",
                semantic_role_code=semantic_role(source_type),
            )
            self.session.add(node)
            self.session.flush()
            self.session.add(
                TechnologyAlias(
                    technology_node_id=node.technology_node_id,
                    source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                    alias_text=term,
                    normalized_alias=normalize_term(term),
                    alias_type_code="source",
                    source_type_code=source_type,
                    source_metadata_json={
                        "original_level": payload.get("原层级(留痕)"),
                        "cross_domain_adjustment": payload.get("跨域调整"),
                        "source_hit": payload.get("命中来源"),
                        "source_detail": payload.get("来源明细(留痕)"),
                    },
                    is_matchable=self._is_matchable(payload, source_type),
                )
            )
            self._link_domain(node, domains[domain_code], source_row)
            self._record_result(import_run, source_row, "technology_node", code)

        version.version_status_code = "active"
        self.session.commit()
        return self._result(version, already_published=False)

    def _load_rows(self, file_asset_id: int) -> dict[str, list[SpreadsheetRow]]:
        return {
            sheet: list(
                self.session.scalars(
                    select(SpreadsheetRow)
                    .where(
                        SpreadsheetRow.file_asset_id == file_asset_id,
                        SpreadsheetRow.sheet_name == sheet,
                    )
                    .order_by(SpreadsheetRow.source_row_number)
                )
            )
            for sheet in SHEET_NAMES
        }

    def _validate(self, rows: dict[str, list[SpreadsheetRow]], version_code: str) -> None:
        errors: list[str] = []
        expected_counts = EXPECTED_SHEET_COUNTS_BY_VERSION.get(version_code, {})
        for sheet in SHEET_NAMES:
            expected_count = expected_counts.get(sheet)
            if expected_count is not None and len(rows[sheet]) != expected_count:
                errors.append(f"{sheet}应有{expected_count}行，实际{len(rows[sheet])}行")
            if not rows[sheet]:
                errors.append(f"{sheet}没有任何数据行")
            for source_row in rows[sheet]:
                missing = REQUIRED_FIELDS[sheet] - source_row.row_payload_json.keys()
                if missing:
                    errors.append(
                        f"{sheet}第{source_row.source_row_number}行缺少字段：{sorted(missing)}"
                    )

        l1_codes = self._unique_codes(rows["L1技术域"], "L1编码", errors)
        if l1_codes != set(DOMAIN_COLORS):
            errors.append(f"L1/T领域编码必须为T1-T7，实际为{sorted(l1_codes)}")
        l2_codes = self._unique_codes(rows["L2技术类"], "L2编码", errors)
        l3_codes = self._unique_codes(rows["L3技术点"], "L3编码", errors)

        l2_parent: dict[str, str] = {}
        for row in rows["L2技术类"]:
            payload = row.row_payload_json
            code = self._text(payload, "L2编码")
            parent = self._text(payload, "所属L1")
            l2_parent[code] = parent
            if parent not in l1_codes:
                errors.append(f"L2 {code}引用不存在的L1 {parent}")

        l3_parent: dict[str, str] = {}
        for row in rows["L3技术点"]:
            payload = row.row_payload_json
            code = self._text(payload, "L3编码")
            parent = self._text(payload, "L2编码")
            domain = self._text(payload, "L1编码")
            l3_parent[code] = parent
            if parent not in l2_codes:
                errors.append(f"L3 {code}引用不存在的L2 {parent}")
            elif l2_parent[parent] != domain:
                errors.append(f"L3 {code}的L1 {domain}与L2父链不一致")

        seen_l4: set[tuple[str, str]] = set()
        for row in rows["L4技术词"]:
            payload = row.row_payload_json
            term = self._text(payload, "技术词")
            parent = self._text(payload, "挂载L3编码")
            l2 = self._text(payload, "L2编码")
            domain = self._text(payload, "L1编码")
            key = (parent, normalize_term(term))
            if key in seen_l4:
                errors.append(f"L4重复挂载：{parent}/{term}")
            seen_l4.add(key)
            if parent not in l3_codes:
                errors.append(f"L4 {term}引用不存在的L3 {parent}")
            elif l3_parent[parent] != l2 or l2_parent.get(l2) != domain:
                errors.append(f"L4 {term}的L3/L2/L1父链不一致")

        if errors:
            preview = "；".join(errors[:20])
            suffix = f"；另有{len(errors) - 20}项" if len(errors) > 20 else ""
            raise TaxonomyImportError(preview + suffix)

    def _unique_codes(self, rows: list[SpreadsheetRow], field: str, errors: list[str]) -> set[str]:
        values = [self._text(row.row_payload_json, field) for row in rows]
        if len(values) != len(set(values)):
            errors.append(f"字段{field}存在重复编码")
        return set(values)

    def _link_domain(
        self, node: TechnologyNode, domain: TechnologyDomain, source_row: SpreadsheetRow
    ) -> None:
        self.session.add(
            TechnologyNodeDomain(
                technology_node_id=node.technology_node_id,
                technology_domain_id=domain.technology_domain_id,
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                domain_score=Decimal("100.0000"),
                is_primary=True,
                evidence_count=1,
                calculation_version="source_v1.1",
            )
        )

    def _record_result(
        self,
        import_run: FileImportRun,
        source_row: SpreadsheetRow,
        target_type: str,
        target_key: str,
    ) -> None:
        self.session.add(
            FileImportRowResult(
                file_import_run_id=import_run.file_import_run_id,
                spreadsheet_row_id=source_row.spreadsheet_row_id,
                row_status_code="success",
                target_type_code=target_type,
                target_record_key=target_key,
                normalized_payload_json={"target_key": target_key},
            )
        )

    def _result(
        self, version: TechnologyTaxonomyVersion, *, already_published: bool
    ) -> TaxonomyImportResult:
        counts = dict(
            self.session.execute(
                select(TechnologyNode.level_code, func.count())
                .where(TechnologyNode.taxonomy_version_id == version.taxonomy_version_id)
                .group_by(TechnologyNode.level_code)
            ).all()
        )
        domain_count = self.session.scalar(select(func.count()).select_from(TechnologyDomain)) or 0
        alias_count = self.session.scalar(select(func.count()).select_from(TechnologyAlias)) or 0
        relation_count = (
            self.session.scalar(select(func.count()).select_from(TechnologyNodeDomain)) or 0
        )
        return TaxonomyImportResult(
            taxonomy_version_id=version.taxonomy_version_id,
            version_code=version.version_code,
            domain_count=domain_count,
            l1_count=counts.get("L1", 0),
            l2_count=counts.get("L2", 0),
            l3_count=counts.get("L3", 0),
            l4_count=counts.get("L4", 0),
            alias_count=alias_count,
            domain_relation_count=relation_count,
            already_published=already_published,
        )

    @staticmethod
    def _is_matchable(payload: dict, source_type: str) -> bool:
        """L4 是否参与 JD 匹配：工作簿写了「可匹配」列就以它为准，否则沿用碎片词规则。

        词表治理需要在保留节点与谱系的前提下把过宽词下线（而不是删行），
        这一列就是下线开关。
        """
        declared = payload.get("可匹配")
        if declared in (None, ""):
            return source_type != "碎片词"
        return str(declared).strip().casefold() not in {"否", "no", "false", "0", "n"}

    @staticmethod
    def _text(payload: dict, field: str) -> str:
        value = payload.get(field)
        if value in (None, ""):
            raise TaxonomyImportError(f"字段{field}不能为空")
        return str(value).strip()

    @staticmethod
    def _optional_text(payload: dict, field: str) -> str | None:
        value = payload.get(field)
        return str(value).strip() if value not in (None, "") else None
