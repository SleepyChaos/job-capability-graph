from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.ingestion.models import FileImportRowResult, FileImportRun, SpreadsheetRow
from app.modules.job.models import Organization, OrganizationAlias
from app.modules.job.service import normalize_label, stable_code


INSTITUTION_SHEET = "机构库"
TYPE_CODES = {
    "企业": "enterprise",
    "高校": "university",
    "科研院所": "research_institute",
    "政府/事业": "government_public",
}


class InstitutionImportError(ValueError):
    """A user-correctable institution import error."""


@dataclass(frozen=True)
class InstitutionImportResult:
    source_row_count: int
    created_count: int
    merged_count: int
    alias_count: int
    failed_count: int
    total_organization_count: int
    already_published: bool


def _text(payload: dict, field: str) -> str | None:
    value = payload.get(field)
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _valid_url(value: str | None) -> str | None:
    if not value:
        return None
    for candidate in re.split(r"\s*[|;]\s*|\s+(?=https?://)", value):
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return None


def _aliases(payload: dict) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    representative = _text(payload, "代表名称")
    if representative:
        values.append((representative, "canonical_source"))
    normalized_key = _text(payload, "归一键")
    if normalized_key:
        values.append((normalized_key, "normalized_key"))
    english_aliases = _text(payload, "英文名/别名")
    if english_aliases:
        for item in re.split(r"\s*[|/；;、]\s*", english_aliases):
            if item.strip():
                values.append((item.strip(), "source_alias"))
    raw_forms = _text(payload, "全部原始形态(频次)")
    if raw_forms:
        for item in raw_forms.split("|"):
            alias = re.sub(r"\(\d+\)\s*$", "", item.strip()).strip()
            if alias:
                values.append((alias, "source_form"))
    enterprise_match = _text(payload, "企业库命中(ID|名称)")
    if enterprise_match:
        for item in enterprise_match.split(";"):
            _, separator, name = item.partition("|")
            if separator and name.strip():
                values.append((name.strip(), "enterprise_match"))
    deduplicated: dict[str, tuple[str, str]] = {}
    for alias, alias_type in values:
        deduplicated.setdefault(normalize_label(alias), (alias, alias_type))
    return list(deduplicated.values())


class InstitutionImportService:
    def __init__(self, session: Session):
        self.session = session

    def publish(self, *, file_import_run_id: int) -> InstitutionImportResult:
        import_run = self.session.get(FileImportRun, file_import_run_id)
        if import_run is None:
            raise InstitutionImportError(f"导入运行不存在：{file_import_run_id}")
        rows = list(
            self.session.scalars(
                select(SpreadsheetRow)
                .where(
                    SpreadsheetRow.file_asset_id == import_run.file_asset_id,
                    SpreadsheetRow.sheet_name == INSTITUTION_SHEET,
                )
                .order_by(SpreadsheetRow.source_row_number)
            )
        )
        if not rows:
            raise InstitutionImportError("暂存数据中没有机构库工作表")
        published_count = (
            self.session.scalar(
                select(func.count())
                .select_from(FileImportRowResult)
                .where(
                    FileImportRowResult.file_import_run_id == file_import_run_id,
                    FileImportRowResult.target_type_code == "organization",
                )
            )
            or 0
        )
        if published_count == len(rows):
            return self._result(rows, 0, published_count, 0, 0, True)

        created = merged = alias_count = failed = 0
        already_processed = set(
            self.session.scalars(
                select(FileImportRowResult.spreadsheet_row_id).where(
                    FileImportRowResult.file_import_run_id == file_import_run_id
                )
            )
        )
        for row in rows:
            if row.spreadsheet_row_id in already_processed:
                merged += 1
                continue
            payload = row.row_payload_json
            institution_id = _text(payload, "机构ID")
            representative = _text(payload, "代表名称")
            if not institution_id or not representative:
                failed += 1
                self.session.add(
                    FileImportRowResult(
                        file_import_run_id=file_import_run_id,
                        spreadsheet_row_id=row.spreadsheet_row_id,
                        row_status_code="failed",
                        target_type_code="organization",
                        error_code="missing_required_field",
                        error_field="机构ID/代表名称",
                        error_message="机构ID和代表名称不能为空",
                    )
                )
                continue

            aliases = _aliases(payload)
            alias_norms = [normalize_label(value) for value, _ in aliases]
            organization = self.session.scalar(
                select(Organization)
                .outerjoin(
                    OrganizationAlias,
                    OrganizationAlias.organization_id == Organization.organization_id,
                )
                .where(
                    or_(
                        Organization.normalized_name.in_(alias_norms),
                        OrganizationAlias.normalized_alias.in_(alias_norms),
                    )
                )
                .order_by(Organization.organization_id)
                .limit(1)
            )
            is_new = organization is None
            metadata = {
                "institution_ids": [institution_id],
                "normalized_key": _text(payload, "归一键"),
                "source": _text(payload, "数据来源"),
                "source_types": _text(payload, "机构类型"),
                "recruitment_url": _text(payload, "招聘链接"),
                "industry_chain": _text(payload, "产业链(12类标准)"),
                "level": _text(payload, "层级"),
                "subfield": _text(payload, "细分领域"),
                "representative_product": _text(payload, "代表产品"),
                "product_type": _text(payload, "产品类型"),
                "mass_production_progress": _text(payload, "量产进展"),
                "operation_path": _text(payload, "运营路径"),
                "source_workbook": "科技人才库与机构库_20260731.xlsx",
            }
            metadata = {key: value for key, value in metadata.items() if value not in (None, "")}
            if organization is None:
                organization = Organization(
                    source_spreadsheet_row_id=row.spreadsheet_row_id,
                    organization_code=stable_code("org", normalize_label(representative)),
                    canonical_name=representative,
                    normalized_name=normalize_label(representative),
                    organization_type_code=TYPE_CODES.get(
                        _text(payload, "机构类型") or "", "other"
                    ),
                    country_code=self._country_code(_text(payload, "国家")),
                    province_name=_text(payload, "省份"),
                    city_name=_text(payload, "总部城市"),
                    website_url=_valid_url(_text(payload, "官网链接")),
                    industry_text=_text(payload, "细分领域")
                    or _text(payload, "产业链(12类标准)"),
                    source_metadata_json=metadata,
                )
                self.session.add(organization)
                self.session.flush()
                created += 1
            else:
                merged += 1
                existing_metadata = dict(organization.source_metadata_json or {})
                institution_ids = list(existing_metadata.get("institution_ids") or [])
                if institution_id not in institution_ids:
                    institution_ids.append(institution_id)
                existing_metadata.update(metadata)
                existing_metadata["institution_ids"] = institution_ids
                organization.source_metadata_json = existing_metadata
                organization.website_url = organization.website_url or _valid_url(
                    _text(payload, "官网链接")
                )
                organization.province_name = organization.province_name or _text(payload, "省份")
                organization.city_name = organization.city_name or _text(payload, "总部城市")
                organization.industry_text = organization.industry_text or _text(
                    payload, "细分领域"
                ) or _text(payload, "产业链(12类标准)")
                if organization.organization_type_code in {"", "other", "enterprise"}:
                    organization.organization_type_code = TYPE_CODES.get(
                        _text(payload, "机构类型") or "",
                        organization.organization_type_code or "other",
                    )

            for alias_text, alias_type in aliases:
                normalized_alias = normalize_label(alias_text)
                exists = self.session.scalar(
                    select(OrganizationAlias.organization_alias_id).where(
                        OrganizationAlias.organization_id == organization.organization_id,
                        OrganizationAlias.normalized_alias == normalized_alias,
                    )
                )
                if exists is None:
                    self.session.add(
                        OrganizationAlias(
                            organization_id=organization.organization_id,
                            source_spreadsheet_row_id=row.spreadsheet_row_id,
                            alias_text=alias_text,
                            normalized_alias=normalized_alias,
                            alias_type_code=alias_type,
                        )
                    )
                    alias_count += 1
            self.session.add(
                FileImportRowResult(
                    file_import_run_id=file_import_run_id,
                    spreadsheet_row_id=row.spreadsheet_row_id,
                    row_status_code="success",
                    target_type_code="organization",
                    target_record_key=organization.organization_code,
                    normalized_payload_json={
                        "organization_code": organization.organization_code,
                        "institution_id": institution_id,
                        "merged": not is_new,
                    },
                )
            )
        self.session.commit()
        return self._result(rows, created, merged, alias_count, failed, False)

    def _result(
        self,
        rows: list[SpreadsheetRow],
        created: int,
        merged: int,
        aliases: int,
        failed: int,
        already_published: bool,
    ) -> InstitutionImportResult:
        total = self.session.scalar(select(func.count()).select_from(Organization)) or 0
        return InstitutionImportResult(
            source_row_count=len(rows),
            created_count=created,
            merged_count=merged,
            alias_count=aliases,
            failed_count=failed,
            total_organization_count=total,
            already_published=already_published,
        )

    @staticmethod
    def _country_code(value: str | None) -> str | None:
        if not value:
            return None
        normalized = normalize_label(value)
        if normalized in {"中国", "中国大陆", "china", "cn"}:
            return "CN"
        return value[:16]
