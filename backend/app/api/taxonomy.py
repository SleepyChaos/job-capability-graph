from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.session import get_db
from app.modules.clustering.models import (
    JobClusterMember,
    JobClusterVersion,
    JobClusteringRun,
    JobRoleVersionRequirement,
)
from app.modules.ingestion.models import SpreadsheetRow
from app.modules.job.models import JobPosting, JobRequirement
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


class TechnologyNodeDetailResponse(BaseModel):
    node_id: int
    code: str
    name: str
    level_code: str
    definition_text: str | None
    alias_text: list[str]
    deprecated: bool
    replaced_by_code: str | None
    review_status_code: str
    referenced_job_count: int
    referenced_organization_count: int
    referenced_role_cluster_count: int


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


class TaxonomyTreeNode(BaseModel):
    node_id: int
    code: str
    name: str
    level_code: str
    domain_code: str
    parent_code: str | None
    referenced_job_count: int
    referenced_organization_count: int
    referenced_role_cluster_count: int
    children: list["TaxonomyTreeNode"]


TaxonomyTreeNode.model_rebuild()


@router.get("/tree", response_model=dict)
def get_taxonomy_tree(
    db: Annotated[Session, Depends(get_db)],
    version_code: str | None = None,
    max_depth: Literal["L1", "L2", "L3", "L4"] = "L3",
) -> dict:
    """T1→L2→L3→L4 技术树（支持前端展开/收起），每个节点带三类引用计数供下钻。"""
    version = active_version(db, version_code)
    depth_code = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}[max_depth]
    parent = aliased(TechnologyNode)
    rows = db.execute(
        select(
            TechnologyNode.technology_node_id,
            TechnologyNode.technology_code,
            TechnologyNode.technology_name,
            TechnologyNode.level_code,
            TechnologyDomain.domain_code,
            parent.technology_code,
        )
        .outerjoin(parent, parent.technology_node_id == TechnologyNode.parent_technology_node_id)
        .outerjoin(
            TechnologyNodeDomain,
            TechnologyNodeDomain.technology_node_id == TechnologyNode.technology_node_id,
        )
        .outerjoin(TechnologyDomain, TechnologyDomain.technology_domain_id == TechnologyNodeDomain.technology_domain_id)
        .where(
            TechnologyNode.taxonomy_version_id == version.taxonomy_version_id,
            TechnologyNode.level_code.in_(
                ["L1", "L2", "L3", "L4"][:depth_code]
            ),
        )
        .order_by(TechnologyNode.level_code, TechnologyNode.sort_order, TechnologyNode.technology_code)
    ).all()
    nodes: dict[int, TaxonomyTreeNode] = {}
    tids = [tid for tid, *_ in rows]
    counts: dict[int, tuple[int, int, int]] = {}
    if tids:
        # referenced_job_count
        j_rows = db.execute(
            select(JobRequirement.technology_node_id, func.count(distinct(JobRequirement.job_posting_id)))
            .where(JobRequirement.technology_node_id.in_(tids))
            .group_by(JobRequirement.technology_node_id)
        ).all()
        # referenced_organization_count
        o_rows = db.execute(
            select(JobRequirement.technology_node_id, func.count(distinct(JobPosting.organization_id)))
            .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
            .where(
                JobRequirement.technology_node_id.in_(tids),
                JobPosting.organization_id.is_not(None),
            )
            .group_by(JobRequirement.technology_node_id)
        ).all()
        c_rows = db.execute(
            select(
                JobRoleVersionRequirement.technology_node_id,
                func.count(distinct(JobRoleVersionRequirement.job_cluster_version_id)),
            )
            .where(JobRoleVersionRequirement.technology_node_id.in_(tids))
            .group_by(JobRoleVersionRequirement.technology_node_id)
        ).all()
        jmap: dict[int, int] = {int(t): int(c) for t, c in j_rows}
        omap: dict[int, int] = {int(t): int(c) for t, c in o_rows}
        cmap: dict[int, int] = {int(t): int(c) for t, c in c_rows}
        for tid in tids:
            counts[int(tid)] = (jmap.get(int(tid), 0), omap.get(int(tid), 0), cmap.get(int(tid), 0))
    code_to_tid: dict[str, int] = {}
    for tid, code, name, level, dcode, pcode in rows:
        jc, oc, cc = counts.get(int(tid), (0, 0, 0))
        node = TaxonomyTreeNode(
            node_id=int(tid),
            code=str(code),
            name=str(name),
            level_code=str(level),
            domain_code=str(dcode or "T7"),
            parent_code=str(pcode) if pcode is not None else None,
            referenced_job_count=int(jc),
            referenced_organization_count=int(oc),
            referenced_role_cluster_count=int(cc),
            children=[],
        )
        nodes[int(tid)] = node
        code_to_tid[str(code)] = int(tid)
    # Attach children to parent (L2→L1 parent_code is L1's code... depends on actual structure; TechnologyNode has parent_technology_node_id)
    # So rather than pcode, join by parent id again
    parent_rows = db.execute(
        select(TechnologyNode.technology_node_id, TechnologyNode.parent_technology_node_id)
        .where(TechnologyNode.technology_node_id.in_(tids))
    ).all()
    child_rel: dict[int, int] = {}
    for tid, pid in parent_rows:
        if pid:
            child_rel[int(tid)] = int(pid)
    roots: list[TaxonomyTreeNode] = []
    for tid, node in nodes.items():
        pid = child_rel.get(tid)
        if pid and pid in nodes:
            nodes[pid].children.append(node)
        else:
            roots.append(node)
    # Sort each level
    def _sort(level: str, items: list[TaxonomyTreeNode]):
        if level == "L1":
            order = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
            items.sort(key=lambda n: (order.index(n.code if n.code in order else "T7"), n.name))
        else:
            items.sort(key=lambda n: (-(n.referenced_job_count + n.referenced_role_cluster_count), n.code))
        for node in items:
            if node.children:
                next_level = "L" + str({"L1": 2, "L2": 3, "L3": 4, "L4": 4}.get(level, 2))
                _sort(next_level, node.children)
    _sort("L1", roots)
    return {
        "version_code": version.version_code,
        "max_depth": max_depth,
        "total_nodes": len(nodes),
        "root_count": len(roots),
        "roots": [r.model_dump() for r in roots],
    }


@router.get("/nodes/{code}/detail", response_model=TechnologyNodeDetailResponse)
def node_detail(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    version_code: str | None = None,
) -> TechnologyNodeDetailResponse:
    version = active_version(db, version_code)
    parent = aliased(TechnologyNode)
    node_row = db.execute(
        select(
            TechnologyNode,
            parent.technology_code,
            TechnologyNodeDomain.review_status_code,
        )
        .outerjoin(parent, parent.technology_node_id == TechnologyNode.parent_technology_node_id)
        .outerjoin(
            TechnologyNodeDomain,
            and_(
                TechnologyNodeDomain.technology_node_id == TechnologyNode.technology_node_id,
                TechnologyNodeDomain.is_primary.is_(True),
            ),
        )
        .where(
            TechnologyNode.taxonomy_version_id == version.taxonomy_version_id,
            TechnologyNode.technology_code == code,
        )
    ).one_or_none()
    if node_row is None:
        raise HTTPException(status_code=404, detail="技术词不存在")
    node, _parent_code, review_status = node_row
    aliases = list(
        db.scalars(
            select(TechnologyAlias.alias_text).where(
                TechnologyAlias.technology_node_id == node.technology_node_id
            )
        )
    )
    l2_l3_node_ids = {node.technology_node_id}
    if node.level_code == "L2":
        descendant_rows = db.scalars(
            select(TechnologyNode.technology_node_id).where(
                TechnologyNode.taxonomy_version_id == version.taxonomy_version_id,
                TechnologyNode.parent_technology_node_id == node.technology_node_id,
                TechnologyNode.level_code.in_(["L3", "L4"]),
            )
        )
        l2_l3_node_ids.update(descendant_rows)
    elif node.level_code == "L3":
        descendant_rows = db.scalars(
            select(TechnologyNode.technology_node_id).where(
                TechnologyNode.taxonomy_version_id == version.taxonomy_version_id,
                TechnologyNode.parent_technology_node_id == node.technology_node_id,
                TechnologyNode.level_code == "L4",
            )
        )
        l2_l3_node_ids.update(descendant_rows)
    referenced_job_count = (
        db.scalar(
            select(func.count(distinct(JobRequirement.job_posting_id))).where(
                JobRequirement.technology_node_id.in_(list(l2_l3_node_ids))
            )
        )
        or 0
    )
    referenced_organization_count = (
        db.scalar(
            select(func.count(distinct(JobPosting.organization_id)))
            .join(JobPosting, JobPosting.job_posting_id == JobRequirement.job_posting_id)
            .where(JobRequirement.technology_node_id.in_(list(l2_l3_node_ids)))
        )
        or 0
    )
    latest_clustering_run = db.scalar(
        select(JobClusteringRun)
        .where(JobClusteringRun.run_status_code == "success")
        .order_by(JobClusteringRun.target_date.desc(), JobClusteringRun.clustering_run_id.desc())
        .limit(1)
    )
    referenced_role_cluster_count = 0
    if latest_clustering_run:
        referenced_role_cluster_count = (
            db.scalar(
                select(func.count(distinct(JobClusterVersion.job_cluster_version_id)))
                .join(
                    JobClusterMember,
                    JobClusterMember.job_cluster_version_id
                    == JobClusterVersion.job_cluster_version_id,
                )
                .join(
                    JobRequirement,
                    JobRequirement.job_posting_id == JobClusterMember.job_posting_id,
                )
                .where(
                    JobClusterVersion.clustering_run_id
                    == latest_clustering_run.clustering_run_id,
                    JobRequirement.technology_node_id.in_(list(l2_l3_node_ids)),
                )
            )
            or 0
        )
    deprecated = node.governance_status_code in {"deprecated", "superseded"}
    return TechnologyNodeDetailResponse(
        node_id=node.technology_node_id,
        code=node.technology_code,
        name=node.technology_name,
        level_code=node.level_code,
        definition_text=node.definition_text,
        alias_text=aliases,
        deprecated=deprecated,
        replaced_by_code=None,
        review_status_code=review_status or "unreviewed",
        referenced_job_count=referenced_job_count,
        referenced_organization_count=referenced_organization_count,
        referenced_role_cluster_count=referenced_role_cluster_count,
    )
