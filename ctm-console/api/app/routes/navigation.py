from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..auth import require_admin
from ..models import (
    CurrentUser,
    DiscoveryRun,
    DiscoveryScanRequest,
    NavCandidate,
    NavCandidateUpdate,
    NavLink,
    NavLinkCreate,
    NavLinkPreview,
    NavLinkPreviewRequest,
    NavLinkUpdate,
    NavReorderRequest,
)


router = APIRouter(prefix="/api/nav", tags=["navigation"])


def nav_service():
    from ..main import app_state

    return app_state.nav


@router.get("/links")
async def links(
    request: Request,
    include_disabled: bool = Query(default=False, alias="includeDisabled"),
    service=Depends(nav_service),
) -> list[NavLink]:
    if include_disabled:
        await require_admin(request)
    return await service.list_links(include_disabled=include_disabled)


@router.post("/links")
async def create_link(
    payload: NavLinkCreate,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> NavLink:
    return await service.create_link(payload)


@router.post("/links/preview")
async def preview_link(
    payload: NavLinkPreviewRequest,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> NavLinkPreview:
    return await service.preview_link(payload.url)


@router.patch("/links/reorder")
async def reorder_links(
    payload: NavReorderRequest,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> dict[str, bool]:
    return await service.reorder_links([(item.id, item.sortOrder) for item in payload.items])


@router.get("/links/{link_id}")
async def link(link_id: int, service=Depends(nav_service)) -> NavLink:
    return await service.get_link(link_id)


@router.patch("/links/{link_id}")
async def update_link(
    link_id: int,
    payload: NavLinkUpdate,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> NavLink:
    return await service.update_link(link_id, payload)


@router.delete("/links/{link_id}")
async def delete_link(
    link_id: int,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> dict[str, bool]:
    return await service.delete_link(link_id)


@router.post("/discovery/scan")
async def start_scan(
    payload: DiscoveryScanRequest | None = None,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> DiscoveryRun:
    return await service.start_scan(
        cidrs=payload.cidrs if payload else None,
        ports=payload.ports if payload else None,
    )


@router.get("/discovery/runs/{run_id}")
async def discovery_run(
    run_id: int,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> DiscoveryRun:
    return await service.get_run(run_id)


@router.get("/discovery/candidates")
async def candidates(
    include_ignored: bool = Query(default=False, alias="includeIgnored"),
    include_imported: bool = Query(default=False, alias="includeImported"),
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> list[NavCandidate]:
    return await service.list_candidates(
        include_ignored=include_ignored,
        include_imported=include_imported,
    )


@router.post("/discovery/candidates/{candidate_id}/import")
async def import_candidate(
    candidate_id: int,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> NavLink:
    return await service.import_candidate(candidate_id)


@router.patch("/discovery/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: int,
    payload: NavCandidateUpdate,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(nav_service),
) -> NavCandidate:
    return await service.update_candidate(candidate_id, payload.model_dump(exclude_unset=True))
