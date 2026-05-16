"""app/api/routes/profile_route.py — Company Profile CRUD + propagation"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import (
    OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry,
    OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile,
    ProfileChangeLog, User,
)
from app.schemas import (
    FullProfileResponse,
    OrgProfileResponse, OrgProfileCreate, OrgProfileUpdate,
    LOBResponse, LOBCreate, LOBUpdate,
    GeographyResponse, GeographyCreate,
    IndustryResponse, IndustryCreate,
    ProductResponse, ProductCreate, ProductUpdate,
    SegmentResponse, SegmentCreate,
    ThirdPartyResponse, ThirdPartyCreate, ThirdPartyUpdate,
    DataTechResponse, DataTechUpdate,
    ChangeLogResponse, ChangeLogListResponse,
    PropagationPreview, PropagationApply,
)

# Country → regulatory flags static map
GEO_REGULATIONS: dict[str, list[str]] = {
    "DE": ["GDPR", "BDSG"], "FR": ["GDPR"], "IT": ["GDPR"], "ES": ["GDPR"],
    "NL": ["GDPR"], "BE": ["GDPR"], "PL": ["GDPR"], "AT": ["GDPR"],
    "GB": ["UK_GDPR", "FCA"], "US": ["CCPA", "HIPAA", "SOX", "FTC"],
    "SG": ["PDPA", "MAS_TRM"], "AU": ["Privacy_Act", "APRA_CPS234"],
    "CA": ["PIPEDA", "CASL"], "JP": ["APPI"], "IN": ["PDPB"],
    "HK": ["PDPO", "HKMA"], "BR": ["LGPD"], "ZA": ["POPIA"],
    "CH": ["nFADP"], "IE": ["GDPR"], "SE": ["GDPR"], "DK": ["GDPR"],
}

router = APIRouter(prefix="/profile", tags=["company-profile"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _log_change(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    summary: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> ProfileChangeLog:
    entry = ProfileChangeLog(
        org_id=org_id,
        changed_by=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        change_summary=summary,
        old_value=old_value,
        new_value=new_value,
        propagation_status="pending",
    )
    db.add(entry)
    await db.flush()
    return entry


def _require_admin(user: User) -> None:
    if user.role not in ("admin", "head_of_audit"):
        raise HTTPException(403, "Admin role required to edit company profile")


# ── Full profile ──────────────────────────────────────────────────────────────

@router.get("", response_model=FullProfileResponse)
async def get_full_profile(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    identity     = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org_id))).scalar_one_or_none()
    lobs         = (await db.execute(select(LineOfBusiness).where(LineOfBusiness.org_id == org_id).order_by(LineOfBusiness.is_primary.desc(), LineOfBusiness.name))).scalars().all()
    geos         = (await db.execute(select(OrgGeography).where(OrgGeography.org_id == org_id).order_by(OrgGeography.country))).scalars().all()
    industries   = (await db.execute(select(OrgIndustry).where(OrgIndustry.org_id == org_id).order_by(OrgIndustry.classification))).scalars().all()
    products     = (await db.execute(select(OrgProduct).where(OrgProduct.org_id == org_id).order_by(OrgProduct.name))).scalars().all()
    segments     = (await db.execute(select(CustomerSegment).where(CustomerSegment.org_id == org_id))).scalars().all()
    third_parties = (await db.execute(select(ThirdPartyDependency).where(ThirdPartyDependency.org_id == org_id).order_by(ThirdPartyDependency.tier, ThirdPartyDependency.name))).scalars().all()
    data_tech    = (await db.execute(select(DataTechProfile).where(DataTechProfile.org_id == org_id))).scalar_one_or_none()
    pending      = (await db.execute(select(func.count()).select_from(ProfileChangeLog).where(ProfileChangeLog.org_id == org_id, ProfileChangeLog.propagation_status == "pending"))).scalar_one()

    return FullProfileResponse(
        identity=identity,
        lines_of_business=list(lobs),
        geographies=list(geos),
        industries=list(industries),
        products=list(products),
        customer_segments=list(segments),
        third_parties=list(third_parties),
        data_tech=data_tech,
        pending_propagations=pending,
    )


# ── Identity ──────────────────────────────────────────────────────────────────

@router.post("/identity", response_model=OrgProfileResponse, status_code=201)
async def create_identity(
    payload: OrgProfileCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    existing = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Profile already exists — use PATCH to update")
    profile = OrgProfile(org_id=org_id, updated_by=user.id, **payload.model_dump())
    db.add(profile)
    await db.flush()
    await _log_change(db, org_id, user.id, "OrgProfile", profile.id, f"Created company profile: {profile.legal_name}", new_value=payload.model_dump())
    return profile


@router.patch("/identity", response_model=OrgProfileResponse)
async def update_identity(
    payload: OrgProfileUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found — create it first")
    old = {k: getattr(profile, k) for k in payload.model_fields_set}
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(profile, k, v)
    profile.updated_by = user.id
    log = await _log_change(db, org_id, user.id, "OrgProfile", profile.id, f"Updated identity: {', '.join(updates.keys())}", old_value=old, new_value=updates)
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "OrgProfile", updates)
    return profile


# ── Lines of Business ─────────────────────────────────────────────────────────

@router.get("/lines-of-business", response_model=list[LOBResponse])
async def list_lobs(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(LineOfBusiness).where(LineOfBusiness.org_id == org_id).order_by(LineOfBusiness.is_primary.desc(), LineOfBusiness.name))).scalars().all()
    return list(rows)


@router.post("/lines-of-business", response_model=LOBResponse, status_code=201)
async def create_lob(
    payload: LOBCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    lob = LineOfBusiness(org_id=org_id, **payload.model_dump())
    db.add(lob)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "LineOfBusiness", lob.id, f"Added line of business: {lob.name}", new_value=payload.model_dump())
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "LineOfBusiness", {"name": lob.name, "status": lob.status})
    return lob


@router.patch("/lines-of-business/{lob_id}", response_model=LOBResponse)
async def update_lob(
    lob_id: UUID, payload: LOBUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    lob = (await db.execute(select(LineOfBusiness).where(LineOfBusiness.id == lob_id, LineOfBusiness.org_id == org_id))).scalar_one_or_none()
    if not lob:
        raise HTTPException(404, "Line of business not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(lob, k, v)
    await _log_change(db, org_id, user.id, "LineOfBusiness", lob.id, f"Updated LOB: {lob.name}")
    return lob


@router.delete("/lines-of-business/{lob_id}", status_code=204)
async def archive_lob(
    lob_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    lob = (await db.execute(select(LineOfBusiness).where(LineOfBusiness.id == lob_id, LineOfBusiness.org_id == org_id))).scalar_one_or_none()
    if not lob:
        raise HTTPException(404, "Line of business not found")
    lob.status = "archived"
    await _log_change(db, org_id, user.id, "LineOfBusiness", lob.id, f"Archived LOB: {lob.name}")


# ── Geographies ───────────────────────────────────────────────────────────────

@router.get("/geographies", response_model=list[GeographyResponse])
async def list_geographies(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(OrgGeography).where(OrgGeography.org_id == org_id).order_by(OrgGeography.country))).scalars().all()
    return list(rows)


@router.post("/geographies", response_model=GeographyResponse, status_code=201)
async def create_geography(
    payload: GeographyCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    reg_flags = GEO_REGULATIONS.get(payload.country.upper(), [])
    data = payload.model_dump()
    geo = OrgGeography(org_id=org_id, regulatory_flags=reg_flags, **data)
    db.add(geo)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "OrgGeography", geo.id, f"Added geography: {geo.country} ({geo.presence_type})", new_value={"country": geo.country, "regulatory_flags": reg_flags})
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "OrgGeography", {"country": geo.country, "regulatory_flags": reg_flags})
    return geo


@router.delete("/geographies/{geo_id}", status_code=204)
async def delete_geography(
    geo_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    geo = (await db.execute(select(OrgGeography).where(OrgGeography.id == geo_id, OrgGeography.org_id == org_id))).scalar_one_or_none()
    if not geo:
        raise HTTPException(404, "Geography not found")
    await _log_change(db, org_id, user.id, "OrgGeography", geo.id, f"Removed geography: {geo.country}")
    await db.delete(geo)


# ── Industries ────────────────────────────────────────────────────────────────

@router.get("/industries", response_model=list[IndustryResponse])
async def list_industries(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(OrgIndustry).where(OrgIndustry.org_id == org_id).order_by(OrgIndustry.classification))).scalars().all()
    return list(rows)


@router.post("/industries", response_model=IndustryResponse, status_code=201)
async def create_industry(
    payload: IndustryCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    ind = OrgIndustry(org_id=org_id, **payload.model_dump())
    db.add(ind)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "OrgIndustry", ind.id, f"Added industry: {ind.name} ({ind.classification})", new_value=payload.model_dump())
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "OrgIndustry", payload.model_dump())
    return ind


@router.delete("/industries/{industry_id}", status_code=204)
async def delete_industry(
    industry_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    ind = (await db.execute(select(OrgIndustry).where(OrgIndustry.id == industry_id, OrgIndustry.org_id == org_id))).scalar_one_or_none()
    if not ind:
        raise HTTPException(404, "Industry not found")
    await db.delete(ind)


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products", response_model=list[ProductResponse])
async def list_products(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(OrgProduct).where(OrgProduct.org_id == org_id).order_by(OrgProduct.name))).scalars().all()
    return list(rows)


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    payload: ProductCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    product = OrgProduct(org_id=org_id, **payload.model_dump())
    db.add(product)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "OrgProduct", product.id, f"Added product: {product.name}", new_value=payload.model_dump())
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "OrgProduct", payload.model_dump())
    return product


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID, payload: ProductUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    product = (await db.execute(select(OrgProduct).where(OrgProduct.id == product_id, OrgProduct.org_id == org_id))).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(product, k, v)
    await _log_change(db, org_id, user.id, "OrgProduct", product.id, f"Updated product: {product.name}")
    return product


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    product = (await db.execute(select(OrgProduct).where(OrgProduct.id == product_id, OrgProduct.org_id == org_id))).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    await db.delete(product)


# ── Customer Segments ─────────────────────────────────────────────────────────

@router.get("/customer-segments", response_model=list[SegmentResponse])
async def list_segments(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(CustomerSegment).where(CustomerSegment.org_id == org_id))).scalars().all()
    return list(rows)


@router.post("/customer-segments", response_model=SegmentResponse, status_code=201)
async def create_segment(
    payload: SegmentCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    seg = CustomerSegment(org_id=org_id, **payload.model_dump())
    db.add(seg)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "CustomerSegment", seg.id, f"Added customer segment: {seg.name}", new_value=payload.model_dump())
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "CustomerSegment", payload.model_dump())
    return seg


@router.delete("/customer-segments/{segment_id}", status_code=204)
async def delete_segment(
    segment_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    seg = (await db.execute(select(CustomerSegment).where(CustomerSegment.id == segment_id, CustomerSegment.org_id == org_id))).scalar_one_or_none()
    if not seg:
        raise HTTPException(404, "Segment not found")
    await db.delete(seg)


# ── Third Parties ─────────────────────────────────────────────────────────────

@router.get("/third-parties", response_model=list[ThirdPartyResponse])
async def list_third_parties(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ThirdPartyDependency).where(ThirdPartyDependency.org_id == org_id).order_by(ThirdPartyDependency.tier, ThirdPartyDependency.name))).scalars().all()
    return list(rows)


@router.post("/third-parties", response_model=ThirdPartyResponse, status_code=201)
async def create_third_party(
    payload: ThirdPartyCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    tp = ThirdPartyDependency(org_id=org_id, **payload.model_dump())
    db.add(tp)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "ThirdPartyDependency", tp.id, f"Added third party: {tp.name} ({tp.tier})", new_value=payload.model_dump())
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "ThirdPartyDependency", payload.model_dump())
    return tp


@router.patch("/third-parties/{tp_id}", response_model=ThirdPartyResponse)
async def update_third_party(
    tp_id: UUID, payload: ThirdPartyUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    tp = (await db.execute(select(ThirdPartyDependency).where(ThirdPartyDependency.id == tp_id, ThirdPartyDependency.org_id == org_id))).scalar_one_or_none()
    if not tp:
        raise HTTPException(404, "Third party not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(tp, k, v)
    await _log_change(db, org_id, user.id, "ThirdPartyDependency", tp.id, f"Updated third party: {tp.name}")
    return tp


@router.delete("/third-parties/{tp_id}", status_code=204)
async def delete_third_party(
    tp_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    tp = (await db.execute(select(ThirdPartyDependency).where(ThirdPartyDependency.id == tp_id, ThirdPartyDependency.org_id == org_id))).scalar_one_or_none()
    if not tp:
        raise HTTPException(404, "Third party not found")
    await db.delete(tp)


# ── Data & Tech Profile ───────────────────────────────────────────────────────

@router.get("/data-tech", response_model=DataTechResponse | None)
async def get_data_tech(org_id: Annotated[UUID, Depends(get_org_id)], db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(DataTechProfile).where(DataTechProfile.org_id == org_id))).scalar_one_or_none()


@router.patch("/data-tech", response_model=DataTechResponse)
async def upsert_data_tech(
    payload: DataTechUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    dtp = (await db.execute(select(DataTechProfile).where(DataTechProfile.org_id == org_id))).scalar_one_or_none()
    updates = payload.model_dump(exclude_unset=True)
    if not dtp:
        dtp = DataTechProfile(org_id=org_id, **updates)
        db.add(dtp)
    else:
        for k, v in updates.items():
            setattr(dtp, k, v)
    await db.flush()
    log = await _log_change(db, org_id, user.id, "DataTechProfile", dtp.id, "Updated data & tech profile", new_value=updates)
    background_tasks.add_task(_run_propagation, str(org_id), str(log.id), "DataTechProfile", updates)
    return dtp


# ── Change Log ────────────────────────────────────────────────────────────────

@router.get("/change-log", response_model=ChangeLogListResponse)
async def get_change_log(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = select(ProfileChangeLog).where(ProfileChangeLog.org_id == org_id).order_by(ProfileChangeLog.changed_at.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ChangeLogListResponse(items=list(items), total=total, page=page, page_size=page_size)


# ── Propagation preview + apply ───────────────────────────────────────────────

@router.get("/propagate/{change_log_id}", response_model=PropagationPreview)
async def get_propagation_preview(
    change_log_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    log = (await db.execute(select(ProfileChangeLog).where(ProfileChangeLog.id == change_log_id, ProfileChangeLog.org_id == org_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(404, "Change log entry not found")
    result = log.propagation_result or {}
    return PropagationPreview(
        change_log_id=log.id,
        change_summary=log.change_summary or "",
        affected_modules=result.get("affected_modules", []),
    )


@router.post("/propagate/apply", status_code=200)
async def apply_propagation(
    payload: PropagationApply,
    org_id: Annotated[UUID, Depends(get_org_id)],
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    log = (await db.execute(select(ProfileChangeLog).where(ProfileChangeLog.id == payload.change_log_id, ProfileChangeLog.org_id == org_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(404, "Change log entry not found")
    approved = set(payload.approved_modules)
    all_modules = {m["module"] for m in (log.propagation_result or {}).get("affected_modules", [])}
    deferred = all_modules - approved
    log.propagation_status = "confirmed" if not deferred else "partial"
    return {"applied": list(approved), "deferred": list(deferred)}


# ── Background propagation ────────────────────────────────────────────────────

async def _run_propagation(org_id: str, log_id: str, entity_type: str, change_data: dict):
    from app.ai.propagation import compute_propagation
    from app.database import get_db_context
    async with get_db_context() as db:
        log = (await db.execute(select(ProfileChangeLog).where(ProfileChangeLog.id == log_id))).scalar_one_or_none()
        if not log:
            return
        result = await compute_propagation(org_id, entity_type, change_data, log.change_summary or "")
        log.propagation_result = result
        log.affected_modules = [m["module"] for m in result.get("affected_modules", [])]
