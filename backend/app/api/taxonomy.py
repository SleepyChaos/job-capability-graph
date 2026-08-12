from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.session import get_db
from app.modules.ingestion.models import SpreadsheetRow
from app.modules.taxonomy.models import (
    TechnologyAlias,
    TechnologyDomain,
    TechnologyNode,
    TechnologyNodeDomain,
    TechnologyTaxonomyVersion,
)

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


class TaxonomyVersionResponse(BaseModel):
    version_code: str
    version_name: str
    effective_date: str
    status: str
    node_count: int


class TechnologyDomainResponse(BaseModel):
    code: str
    name: str
    definition: str | None
    color: str | None
    sort_order: int
    node_count: int


class TechnologyNodeResponse(BaseModel):
    node_id: int
    code: str
    name: str
    normalized_name: str
    level: str
    parent_code: str | None
    domain_code: str
    domain_name: str
    domain_color: str | None
    semantic_role: str | None
    alias_count: int
    source_sheet: str
    source_row_number: int


class TechnologyNodePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TechnologyNodeResponse]


def active_version(db: Session, version_code: str | None) -> TechnologyTaxonomyVersion:
    statement = select(TechnologyTaxonomyVersion)
    if version_code:
        statement = statement.where(TechnologyTaxonomyVersion.version_code == version_code)
    else:
        statement = statement.where(
            TechnologyTaxonomyVersion.version_status_code == "active"
        ).order_by(TechnologyTaxonomyVersion.effective_date.desc())
    version = db.scalar(statement.limit(1))
    if version is None:
        raise HTTPException(status_code=404, detail="技术体系版本不存在")
    return version


@router.get("/versions", response_model=list[TaxonomyVersionResponse])
def list_versions(db: Annotated[Session, Depends(get_db)]) -> list[TaxonomyVersionResponse]:
    rows = db.execute(
        select(
            TechnologyTaxonomyVersion,
            func.count(TechnologyNode.technology_node_id),
        )
        .outerjoin(
            TechnologyNode,
            TechnologyNode.taxonomy_version_id == TechnologyTaxonomyVersion.taxonomy_version_id,
        )
        .group_by(TechnologyTaxonomyVersion.taxonomy_version_id)
        .order_by(TechnologyTaxonomyVersion.effective_date.desc())
    ).all()
    return [
        TaxonomyVersionResponse(
            version_code=version.version_code,
            version_name=version.version_name,
            effective_date=version.effective_date.isoformat(),
            status=version.version_status_code,
            node_count=node_count,
        )
        for version, node_count in rows
    ]


@router.get("/domains", response_model=list[TechnologyDomainResponse])
def list_domains(
    db: Annotated[Session, Depends(get_db)],
    version_code: str | None = None,
) -> list[TechnologyDomainResponse]:
    version = active_version(db, version_code)
    rows = db.execute(
        select(TechnologyDomain, func.count(TechnologyNodeDomain.technology_node_id))
        .join(
            TechnologyNodeDomain,
            TechnologyNodeDomain.technology_domain_id == TechnologyDomain.technology_domain_id,
        )
        .join(
            TechnologyNode,
            TechnologyNode.technology_node_id == TechnologyNodeDomain.technology_node_id,
        )
        .where(TechnologyNode.taxonomy_version_id == version.taxonomy_version_id)
        .group_by(TechnologyDomain.technology_domain_id)
        .order_by(TechnologyDomain.sort_order)
    ).all()
    return [
        TechnologyDomainResponse(
            code=domain.domain_code,
            name=domain.domain_name,
            definition=domain.definition_text,
            color=domain.color_token,
            sort_order=domain.sort_order,
            node_count=node_count,
        )
        for domain, node_count in rows
    ]


@router.get("/nodes", response_model=TechnologyNodePage)
def list_nodes(
    db: Annotated[Session, Depends(get_db)],
    version_code: str | None = None,
    level: Literal["L1", "L2", "L3", "L4"] | None = None,
    domain_code: str | None = None,
    parent_code: str | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TechnologyNodePage:
    version = active_version(db, version_code)
    parent = aliased(TechnologyNode)
    filters = [TechnologyNode.taxonomy_version_id == version.taxonomy_version_id]
    if level:
        filters.append(TechnologyNode.level_code == level)
    if domain_code:
        filters.append(TechnologyDomain.domain_code == domain_code)
    if parent_code:
        filters.append(parent.technology_code == parent_code)
    if search:
        normalized_search = f"%{search.strip().casefold()}%"
        filters.append(
            or_(
                TechnologyNode.normalized_name.like(normalized_search),
                TechnologyNode.technology_code.like(f"%{search.strip()}%"),
            )
        )

    base = (
        select(
            TechnologyNode,
            parent.technology_code,
            TechnologyDomain,
            SpreadsheetRow.sheet_name,
            SpreadsheetRow.source_row_number,
            func.count(TechnologyAlias.technology_alias_id).label("alias_count"),
        )
        .outerjoin(parent, parent.technology_node_id == TechnologyNode.parent_technology_node_id)
        .join(
            TechnologyNodeDomain,
            TechnologyNodeDomain.technology_node_id == TechnologyNode.technology_node_id,
        )
        .join(
            TechnologyDomain,
            TechnologyDomain.technology_domain_id == TechnologyNodeDomain.technology_domain_id,
        )
        .join(
            SpreadsheetRow,
            SpreadsheetRow.spreadsheet_row_id == TechnologyNode.source_spreadsheet_row_id,
        )
        .outerjoin(
            TechnologyAlias,
            TechnologyAlias.technology_node_id == TechnologyNode.technology_node_id,
        )
        .where(and_(*filters))
        .group_by(
            TechnologyNode.technology_node_id,
            parent.technology_code,
            TechnologyDomain.technology_domain_id,
            SpreadsheetRow.spreadsheet_row_id,
        )
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(TechnologyDomain.sort_order, TechnologyNode.technology_code)
        .offset(offset)
        .limit(limit)
    ).all()
    items = [
        TechnologyNodeResponse(
            node_id=node.technology_node_id,
            code=node.technology_code,
            name=node.technology_name,
            normalized_name=node.normalized_name,
            level=node.level_code,
            parent_code=parent_code_value,
            domain_code=domain.domain_code,
            domain_name=domain.domain_name,
            domain_color=domain.color_token,
            semantic_role=node.semantic_role_code,
            alias_count=alias_count,
            source_sheet=source_sheet,
            source_row_number=source_row_number,
        )
        for node, parent_code_value, domain, source_sheet, source_row_number, alias_count in rows
    ]
    return TechnologyNodePage(total=total, limit=limit, offset=offset, items=items)
