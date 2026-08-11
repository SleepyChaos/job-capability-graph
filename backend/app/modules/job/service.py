from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.modules.extraction.technology import (
    TechnologyAliasMatcher,
    TechnologyHit,
    TechnologyPattern,
)
from app.modules.ingestion.models import (
    FileImportRowResult,
    FileImportRun,
    SpreadsheetRow,
)
from app.modules.job.models import (
    DataSource,
    DocumentQuality,
    DuplicateDocumentGroup,
    DuplicateDocumentMember,
    EvidenceSpan,
    JobPosting,
    JobPostingDataSource,
    JobRequirement,
    JobRequirementEvidence,
    Organization,
    OrganizationAlias,
    SourceDocument,
    SourceDocumentVersion,
)
from app.modules.taxonomy.models import (
    TechnologyAlias,
    TechnologyNode,
    TechnologyTaxonomyVersion,
)

EXPECTED_JOB_COUNT = 3718
JOB_SHEET = "岗位数据"
REQUIRED_JOB_FIELDS = {
    "occ_id",
    "group_id",
    "岗位",
    "学历(标准化)",
    "经验(标准化)",
    "能力等级",
    "清洗JD描述",
    "来源列表",
    "是否有有效JD",
}

SOURCE_DEFINITIONS = {
    "all_jobs_jd": ("全量岗位JD数据集", "file", Decimal("70")),
    "embodied_final": ("具身智能岗位精选数据集", "file", Decimal("80")),
    "search_all": ("全网检索补充数据集", "file", Decimal("60")),
    "猎聘10家中游": ("猎聘重点企业岗位数据集", "recruitment", Decimal("85")),
}

EDUCATION_CODES = {
    "未说明": "unspecified",
    "硕士": "master",
    "本科": "bachelor",
    "博士": "doctorate",
    "大专": "associate",
    "中专/高中": "high_school",
    "不限": "no_limit",
}

EXPERIENCE_RANGES = {
    "未说明": (None, None),
    "10年以上": (Decimal("10"), None),
    "5-8年": (Decimal("5"), Decimal("8")),
    "8-10年": (Decimal("8"), Decimal("10")),
    "1-3年": (Decimal("1"), Decimal("3")),
    "3-5年": (Decimal("3"), Decimal("5")),
    "经验不限": (Decimal("0"), None),
    "5年以上": (Decimal("5"), None),
}

LEVEL_CODES = {"初级": "junior", "中级": "middle", "高级": "senior"}
BONUS_MARKERS = ("加分", "优先", "优先考虑", "最好", "bonus", "preferred")


class JobImportError(ValueError):
    pass


@dataclass(frozen=True)
class JobImportResult:
    total_jobs: int
    organization_count: int
    data_source_count: int
    unique_content_count: int
    duplicate_group_count: int
    duplicate_member_count: int
    source_timed_count: int
    migration_timed_count: int
    technology_covered_job_count: int
    requirement_count: int
    evidence_span_count: int
    already_published: bool


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def stable_code(prefix: str, value: str, length: int = 24) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:length]}"


def parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError as error:
        raise JobImportError(f"无法解析时间：{text}") from error


def valid_url(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    parsed = urlparse(text)
    return text if parsed.scheme in {"http", "https"} and parsed.netloc else None


class JobImportService:
    def __init__(self, session: Session):
        self.session = session

    def publish(
        self,
        *,
        file_import_run_id: int,
        taxonomy_version_code: str,
        received_at: datetime,
    ) -> JobImportResult:
        import_run = self.session.get(FileImportRun, file_import_run_id)
        if import_run is None:
            raise JobImportError(f"导入运行不存在：{file_import_run_id}")
        existing_count = (
            self.session.scalar(
                select(func.count())
                .select_from(JobPosting)
                .join(
                    SourceDocumentVersion,
                    SourceDocumentVersion.source_document_version_id
                    == JobPosting.source_document_version_id,
                )
                .where(SourceDocumentVersion.file_asset_id == import_run.file_asset_id)
            )
            or 0
        )
        if existing_count:
            if existing_count != EXPECTED_JOB_COUNT:
                raise JobImportError(f"源文件已有{existing_count}条JD，未达到完整数量")
            return self._result(already_published=True)

        source_rows = list(
            self.session.scalars(
                select(SpreadsheetRow)
                .where(
                    SpreadsheetRow.file_asset_id == import_run.file_asset_id,
                    SpreadsheetRow.sheet_name == JOB_SHEET,
                )
                .order_by(SpreadsheetRow.source_row_number)
            )
        )
        self._validate(source_rows)
        taxonomy_version = self.session.scalar(
            select(TechnologyTaxonomyVersion).where(
                TechnologyTaxonomyVersion.version_code == taxonomy_version_code,
                TechnologyTaxonomyVersion.version_status_code == "active",
            )
        )
        if taxonomy_version is None:
            raise JobImportError(f"技术体系版本不可用：{taxonomy_version_code}")

        sources = self._ensure_sources(import_run.file_asset_id)
        organizations = self._build_organizations(source_rows)
        matcher = self._build_matcher(taxonomy_version.taxonomy_version_id)
        document_versions_by_hash: dict[str, list[SourceDocumentVersion]] = defaultdict(list)
        job_by_document_version: dict[int, JobPosting] = {}

        for source_row in source_rows:
            payload = source_row.row_payload_json
            source_codes = self._source_codes(payload)
            primary_source = sources[source_codes[0]]
            source_time = parse_datetime(payload.get("收录时间"))
            time_quality = "source_collected" if source_time else "migration_only"
            seen_at = source_time or received_at
            occ_id = self._text(payload, "occ_id")
            group_id = self._text(payload, "group_id")
            title = self._text(payload, "岗位")
            content = self._text(payload, "清洗JD描述")
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            raw_company = self._optional_text(payload, "公司")
            canonical_company = self._optional_text(payload, "关联公司") or raw_company
            organization = (
                organizations.get(normalize_label(canonical_company)) if canonical_company else None
            )
            canonical_url = valid_url(payload.get("链接"))
            document_identity = hashlib.sha256(
                f"{primary_source.source_code}\0{occ_id}".encode()
            ).hexdigest()
            document = SourceDocument(
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                document_code=stable_code("doc", document_identity),
                data_source_id=primary_source.data_source_id,
                document_type_code="job",
                source_record_key=occ_id,
                canonical_url=canonical_url,
                document_identity_key=document_identity,
                title=title,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            self.session.add(document)
            self.session.flush()
            document_version = SourceDocumentVersion(
                source_document_id=document.source_document_id,
                version_no=1,
                file_asset_id=import_run.file_asset_id,
                collected_at=received_at,
                source_collected_at=source_time,
                valid_from=received_at,
                content_text=content,
                content_json={
                    "truth_classification": "migrated_cleaned_source",
                    "source_group_key": group_id,
                    "source_codes": source_codes,
                },
                content_hash=content_hash,
                parser_version="migrated_cleaned_v1",
            )
            self.session.add(document_version)
            self.session.flush()
            experience_text = self._text(payload, "经验(标准化)")
            experience_min, experience_max = EXPERIENCE_RANGES[experience_text]
            education_text = self._text(payload, "学历(标准化)")
            job = JobPosting(
                source_spreadsheet_row_id=source_row.spreadsheet_row_id,
                job_code=stable_code("job", f"{primary_source.source_code}\0{occ_id}"),
                source_document_version_id=document_version.source_document_version_id,
                data_source_id=primary_source.data_source_id,
                source_job_id=occ_id,
                source_group_key=group_id,
                organization_id=organization.organization_id if organization else None,
                company_name_raw=raw_company,
                job_title_raw=title,
                job_title_normalized=normalize_label(title),
                job_level_code=LEVEL_CODES[self._text(payload, "能力等级")],
                region_text=self._optional_text(payload, "城市"),
                salary_text=self._optional_text(payload, "薪资"),
                education_code=EDUCATION_CODES[education_text],
                education_text=self._optional_text(payload, "学历(原始)"),
                experience_min_years=experience_min,
                experience_max_years=experience_max,
                experience_text=self._optional_text(payload, "经验(原始)"),
                jd_clean_text=content,
                collected_at=received_at,
                source_collected_at=source_time,
                time_quality_code=time_quality,
                parse_confidence_score=Decimal("95"),
                publish_score=Decimal("90") if canonical_url and raw_company else Decimal("75"),
                source_metadata_json={
                    "career_direction": payload.get("职业方向"),
                    "career_type": payload.get("职业种类"),
                    "industry_chain_level": payload.get("产业链层级"),
                    "company_subfield": payload.get("公司细分领域"),
                    "funding_round": payload.get("融资轮次"),
                    "company_region": payload.get("公司所属地区"),
                    "company_headquarters_city": payload.get("公司总部城市"),
                    "source_skill_tags": payload.get("技能标签"),
                    "source_url_raw": payload.get("链接"),
                },
            )
            self.session.add(job)
            self.session.flush()
            for order, source_code in enumerate(source_codes, start=1):
                self.session.add(
                    JobPostingDataSource(
                        job_posting_id=job.job_posting_id,
                        data_source_id=sources[source_code].data_source_id,
                        source_role_code="primary" if order == 1 else "supporting",
                        source_order=order,
                    )
                )
            self.session.add(
                JobPostingDataSource(
                    job_posting_id=job.job_posting_id,
                    data_source_id=sources["migration_workbook"].data_source_id,
                    source_role_code="migration",
                    source_order=len(source_codes) + 1,
                )
            )
            missing_reasons = []
            if raw_company is None:
                missing_reasons.append("missing_company")
            if canonical_url is None:
                missing_reasons.append("missing_or_invalid_url")
            if source_time is None:
                missing_reasons.append("missing_source_time")
            completeness = Decimal("100")
            completeness -= Decimal("25") if raw_company is None else Decimal("0")
            completeness -= Decimal("10") if canonical_url is None else Decimal("0")
            completeness -= (
                Decimal("5") if self._optional_text(payload, "城市") is None else Decimal("0")
            )
            timeliness = Decimal("80") if source_time else Decimal("20")
            self.session.add(
                DocumentQuality(
                    source_document_version_id=document_version.source_document_version_id,
                    checker_version="migration_quality_v1",
                    timeliness_score=timeliness,
                    completeness_score=completeness,
                    noise_score=Decimal("0"),
                    duplication_score=Decimal("0"),
                    overall_quality_score=(timeliness + completeness + Decimal("100"))
                    / Decimal("3"),
                    quality_status_code="warning" if missing_reasons else "accepted",
                    reason_json={"reasons": missing_reasons},
                )
            )
            document_versions_by_hash[content_hash].append(document_version)
            job_by_document_version[document_version.source_document_version_id] = job
            self._extract_requirements(job, document_version, matcher)
            self.session.add(
                FileImportRowResult(
                    file_import_run_id=import_run.file_import_run_id,
                    spreadsheet_row_id=source_row.spreadsheet_row_id,
                    row_status_code="success",
                    target_type_code="job_posting",
                    target_record_key=job.job_code,
                    normalized_payload_json={"job_code": job.job_code},
                )
            )

        self.session.flush()
        self._create_duplicate_groups(document_versions_by_hash, job_by_document_version)
        self.session.commit()
        return self._result(already_published=False)

    def _validate(self, rows: list[SpreadsheetRow]) -> None:
        errors: list[str] = []
        if len(rows) != EXPECTED_JOB_COUNT:
            errors.append(f"岗位数据应有{EXPECTED_JOB_COUNT}行，实际{len(rows)}行")
        occ_ids: set[str] = set()
        group_ids: set[str] = set()
        for row in rows:
            payload = row.row_payload_json
            missing_fields = REQUIRED_JOB_FIELDS - payload.keys()
            if missing_fields:
                errors.append(f"第{row.source_row_number}行缺少字段{sorted(missing_fields)}")
                continue
            occ_id = self._text(payload, "occ_id")
            group_id = self._text(payload, "group_id")
            if occ_id in occ_ids:
                errors.append(f"occ_id重复：{occ_id}")
            if group_id in group_ids:
                errors.append(f"group_id重复：{group_id}")
            occ_ids.add(occ_id)
            group_ids.add(group_id)
            if self._text(payload, "是否有有效JD") != "是":
                errors.append(f"第{row.source_row_number}行不是有效JD")
            if self._text(payload, "学历(标准化)") not in EDUCATION_CODES:
                errors.append(f"第{row.source_row_number}行学历编码未知")
            if self._text(payload, "经验(标准化)") not in EXPERIENCE_RANGES:
                errors.append(f"第{row.source_row_number}行经验编码未知")
            if self._text(payload, "能力等级") not in LEVEL_CODES:
                errors.append(f"第{row.source_row_number}行能力等级未知")
            unknown_sources = set(self._source_codes(payload)) - SOURCE_DEFINITIONS.keys()
            if unknown_sources:
                errors.append(f"第{row.source_row_number}行来源未知：{sorted(unknown_sources)}")
        if errors:
            preview = "；".join(errors[:20])
            suffix = f"；另有{len(errors) - 20}项" if len(errors) > 20 else ""
            raise JobImportError(preview + suffix)

    def _ensure_sources(self, file_asset_id: int) -> dict[str, DataSource]:
        sources: dict[str, DataSource] = {}
        for code, (name, source_type, reliability) in SOURCE_DEFINITIONS.items():
            source = self.session.scalar(select(DataSource).where(DataSource.source_code == code))
            if source is None:
                source = DataSource(
                    source_code=code,
                    source_name=name,
                    source_type_code=source_type,
                    content_type_code="job",
                    authority_level_code="source_dataset",
                    independent_source_group=code,
                    default_reliability_score=reliability,
                    license_note="由20260810工作簿迁移；需在接入在线采集前补充许可核验。",
                )
                self.session.add(source)
                self.session.flush()
            sources[code] = source
        migration_source = self.session.scalar(
            select(DataSource).where(DataSource.source_code == "migration_workbook")
        )
        if migration_source is None:
            migration_source = DataSource(
                source_file_asset_id=file_asset_id,
                source_code="migration_workbook",
                source_name="20260810岗位工作簿迁移",
                source_type_code="file",
                content_type_code="job",
                authority_level_code="migration_container",
                independent_source_group="migration_20260810",
                default_reliability_score=Decimal("100"),
            )
            self.session.add(migration_source)
            self.session.flush()
        sources["migration_workbook"] = migration_source
        return sources

    def _build_organizations(self, rows: list[SpreadsheetRow]) -> dict[str, Organization]:
        organizations: dict[str, Organization] = {}
        aliases: set[tuple[int, str]] = set()
        for row in rows:
            payload = row.row_payload_json
            raw_name = self._optional_text(payload, "公司")
            canonical_name = self._optional_text(payload, "关联公司") or raw_name
            if canonical_name is None:
                continue
            normalized = normalize_label(canonical_name)
            organization = organizations.get(normalized)
            if organization is None:
                organization = self.session.scalar(
                    select(Organization).where(Organization.normalized_name == normalized)
                )
            if organization is None:
                organization = Organization(
                    source_spreadsheet_row_id=row.spreadsheet_row_id,
                    organization_code=stable_code("org", normalized),
                    canonical_name=canonical_name,
                    normalized_name=normalized,
                    organization_type_code="enterprise",
                    city_name=self._optional_text(payload, "公司总部城市"),
                    industry_text=self._optional_text(payload, "公司细分领域"),
                    source_metadata_json={
                        "funding_round": payload.get("融资轮次"),
                        "region": payload.get("公司所属地区"),
                    },
                )
                self.session.add(organization)
                self.session.flush()
            organizations[normalized] = organization
            for alias_text in {raw_name, canonical_name} - {None}:
                normalized_alias = normalize_label(alias_text)
                key = (organization.organization_id, normalized_alias)
                if key in aliases:
                    continue
                existing_alias = self.session.scalar(
                    select(OrganizationAlias.organization_alias_id).where(
                        OrganizationAlias.organization_id == organization.organization_id,
                        OrganizationAlias.normalized_alias == normalized_alias,
                    )
                )
                if existing_alias is None:
                    self.session.add(
                        OrganizationAlias(
                            organization_id=organization.organization_id,
                            source_spreadsheet_row_id=row.spreadsheet_row_id,
                            alias_text=alias_text,
                            normalized_alias=normalized_alias,
                            alias_type_code=(
                                "canonical_source" if alias_text == canonical_name else "source"
                            ),
                        )
                    )
                aliases.add(key)
        self.session.flush()
        return organizations

    def _build_matcher(self, taxonomy_version_id: int) -> TechnologyAliasMatcher:
        l4_node = aliased(TechnologyNode)
        l3_node = aliased(TechnologyNode)
        rows = self.session.execute(
            select(TechnologyAlias, l3_node.technology_node_id)
            .join(l4_node, l4_node.technology_node_id == TechnologyAlias.technology_node_id)
            .join(l3_node, l3_node.technology_node_id == l4_node.parent_technology_node_id)
            .where(
                l4_node.taxonomy_version_id == taxonomy_version_id,
                l4_node.level_code == "L4",
                l3_node.level_code == "L3",
                TechnologyAlias.is_matchable.is_(True),
            )
        ).all()
        patterns = [
            TechnologyPattern(
                alias_id=alias.technology_alias_id,
                normalized_alias=alias.normalized_alias,
                l3_technology_node_id=l3_id,
            )
            for alias, l3_id in rows
            if alias.normalized_alias
        ]
        return TechnologyAliasMatcher(patterns)

    def _extract_requirements(
        self,
        job: JobPosting,
        document_version: SourceDocumentVersion,
        matcher: TechnologyAliasMatcher,
    ) -> None:
        hits = matcher.find(job.jd_clean_text)
        grouped: dict[tuple[int, str], list[TechnologyHit]] = defaultdict(list)
        for hit in hits:
            grouped[
                (hit.l3_technology_node_id, self._requirement_type(job.jd_clean_text, hit))
            ].append(hit)
        for requirement_no, ((technology_node_id, requirement_type), group_hits) in enumerate(
            sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])), start=1
        ):
            first_hit = group_hits[0]
            requirement = JobRequirement(
                job_posting_id=job.job_posting_id,
                requirement_no=requirement_no,
                requirement_type_code=requirement_type,
                raw_term=first_hit.matched_text,
                raw_text=self._snippet(
                    job.jd_clean_text, first_hit.start_offset, first_hit.end_offset
                ),
                technology_node_id=technology_node_id,
                mention_count=len(group_hits),
                mapping_method_code="exact_alias_aho_v1",
                confidence_score=Decimal("95"),
            )
            self.session.add(requirement)
            self.session.flush()
            for hit in group_hits:
                evidence_hash = hashlib.sha256(
                    f"{hit.start_offset}\0{hit.end_offset}\0{hit.alias_id}".encode()
                ).hexdigest()
                evidence = EvidenceSpan(
                    source_document_version_id=document_version.source_document_version_id,
                    span_type_code="requirement",
                    start_offset=hit.start_offset,
                    end_offset=hit.end_offset,
                    evidence_text=job.jd_clean_text[hit.start_offset : hit.end_offset],
                    evidence_hash=evidence_hash,
                    source_reliability_score=Decimal("95"),
                )
                self.session.add(evidence)
                self.session.flush()
                self.session.add(
                    JobRequirementEvidence(
                        job_requirement_id=requirement.job_requirement_id,
                        evidence_span_id=evidence.evidence_span_id,
                        matched_alias_id=hit.alias_id,
                        support_score=Decimal("95"),
                    )
                )

    def _create_duplicate_groups(
        self,
        versions_by_hash: dict[str, list[SourceDocumentVersion]],
        job_by_document_version: dict[int, JobPosting],
    ) -> None:
        for content_hash, versions in versions_by_hash.items():
            if len(versions) <= 1:
                continue
            representative = min(versions, key=lambda item: item.source_document_version_id)
            group = DuplicateDocumentGroup(
                group_code=stable_code("dup", content_hash),
                representative_document_version_id=representative.source_document_version_id,
                detection_method_code="exact_content_hash",
                algorithm_version="sha256_v1",
                member_count=len(versions),
            )
            self.session.add(group)
            self.session.flush()
            weight = Decimal("1") / Decimal(len(versions))
            for version in versions:
                self.session.add(
                    DuplicateDocumentMember(
                        duplicate_group_id=group.duplicate_group_id,
                        source_document_version_id=version.source_document_version_id,
                        similarity_score=Decimal("1"),
                        copied_ratio=Decimal("1"),
                        is_representative=(
                            version.source_document_version_id
                            == representative.source_document_version_id
                        ),
                    )
                )
                job_by_document_version[version.source_document_version_id].evidence_weight = weight
                quality = self.session.scalar(
                    select(DocumentQuality).where(
                        DocumentQuality.source_document_version_id
                        == version.source_document_version_id
                    )
                )
                if quality is not None:
                    quality.duplication_score = Decimal("100")
                    quality.overall_quality_score = (
                        (quality.timeliness_score or Decimal("0"))
                        + (quality.completeness_score or Decimal("0"))
                    ) / Decimal("3")
                    quality.quality_status_code = "warning"
                    reasons = dict(quality.reason_json or {})
                    reasons["duplicate_group_code"] = group.group_code
                    quality.reason_json = reasons

    def _result(self, *, already_published: bool) -> JobImportResult:
        total_jobs = self.session.scalar(select(func.count()).select_from(JobPosting)) or 0
        organization_count = (
            self.session.scalar(select(func.count()).select_from(Organization)) or 0
        )
        data_source_count = self.session.scalar(select(func.count()).select_from(DataSource)) or 0
        unique_content_count = (
            self.session.scalar(
                select(func.count(func.distinct(SourceDocumentVersion.content_hash)))
            )
            or 0
        )
        duplicate_group_count = (
            self.session.scalar(select(func.count()).select_from(DuplicateDocumentGroup)) or 0
        )
        duplicate_member_count = (
            self.session.scalar(select(func.count()).select_from(DuplicateDocumentMember)) or 0
        )
        source_timed_count = (
            self.session.scalar(
                select(func.count())
                .select_from(JobPosting)
                .where(JobPosting.time_quality_code == "source_collected")
            )
            or 0
        )
        migration_timed_count = (
            self.session.scalar(
                select(func.count())
                .select_from(JobPosting)
                .where(JobPosting.time_quality_code == "migration_only")
            )
            or 0
        )
        technology_covered_job_count = (
            self.session.scalar(select(func.count(func.distinct(JobRequirement.job_posting_id))))
            or 0
        )
        requirement_count = (
            self.session.scalar(select(func.count()).select_from(JobRequirement)) or 0
        )
        evidence_span_count = (
            self.session.scalar(select(func.count()).select_from(EvidenceSpan)) or 0
        )
        return JobImportResult(
            total_jobs=total_jobs,
            organization_count=organization_count,
            data_source_count=data_source_count,
            unique_content_count=unique_content_count,
            duplicate_group_count=duplicate_group_count,
            duplicate_member_count=duplicate_member_count,
            source_timed_count=source_timed_count,
            migration_timed_count=migration_timed_count,
            technology_covered_job_count=technology_covered_job_count,
            requirement_count=requirement_count,
            evidence_span_count=evidence_span_count,
            already_published=already_published,
        )

    @staticmethod
    def _source_codes(payload: dict) -> list[str]:
        value = JobImportService._text(payload, "来源列表")
        return [item.strip() for item in value.split(";") if item.strip()]

    @staticmethod
    def _requirement_type(text: str, hit: TechnologyHit) -> str:
        context = text[
            max(0, hit.start_offset - 30) : min(len(text), hit.end_offset + 30)
        ].casefold()
        return "bonus" if any(marker in context for marker in BONUS_MARKERS) else "required"

    @staticmethod
    def _snippet(text: str, start: int, end: int, radius: int = 45) -> str:
        return text[max(0, start - radius) : min(len(text), end + radius)]

    @staticmethod
    def _text(payload: dict, field: str) -> str:
        value = payload.get(field)
        if value in (None, ""):
            raise JobImportError(f"字段{field}不能为空")
        return str(value).strip()

    @staticmethod
    def _optional_text(payload: dict, field: str) -> str | None:
        value = payload.get(field)
        return str(value).strip() if value not in (None, "") else None
