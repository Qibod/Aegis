"""app/api/routes/canvas_route.py — Living control canvas"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import CanvasEdge, CanvasNode
from app.schemas import (
    CanvasEdgeCreate, CanvasEdgeResponse,
    CanvasNodeCreate, CanvasNodeResponse, CanvasNodeUpdate,
    CanvasResponse,
)

router = APIRouter(prefix="/canvas", tags=["canvas"])


async def _recompute_orphans(org_id: str, db):
    """Mark nodes with no edges as orphans."""
    nodes = (await db.execute(
        select(CanvasNode).where(CanvasNode.org_id == org_id)
    )).scalars().all()
    for node in nodes:
        out = (await db.execute(
            select(CanvasEdge).where(CanvasEdge.from_node_id == node.id)
        )).first()
        inc = (await db.execute(
            select(CanvasEdge).where(CanvasEdge.to_node_id == node.id)
        )).first()
        node.is_orphan = (out is None and inc is None)


@router.get("", response_model=CanvasResponse)
async def get_canvas(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    nodes = (await db.execute(
        select(CanvasNode).where(CanvasNode.org_id == org_id)
        .options(selectinload(CanvasNode.risk), selectinload(CanvasNode.control))
    )).scalars().all()
    edges = (await db.execute(
        select(CanvasEdge).where(CanvasEdge.org_id == org_id)
    )).scalars().all()
    return CanvasResponse(nodes=nodes, edges=edges)


@router.post("/nodes", response_model=CanvasNodeResponse, status_code=201)
async def create_node(
    payload: CanvasNodeCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    node = CanvasNode(org_id=org_id, **payload.model_dump())
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return node


@router.patch("/nodes/{node_id}", response_model=CanvasNodeResponse)
async def update_node(
    node_id: UUID,
    payload: CanvasNodeUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CanvasNode).where(CanvasNode.id == node_id, CanvasNode.org_id == org_id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, field, value)
    return node


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CanvasNode).where(CanvasNode.id == node_id, CanvasNode.org_id == org_id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    await db.delete(node)
    await _recompute_orphans(str(org_id), db)


@router.post("/edges", response_model=CanvasEdgeResponse, status_code=201)
async def create_edge(
    payload: CanvasEdgeCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    edge = CanvasEdge(org_id=org_id, **payload.model_dump())
    db.add(edge)
    await db.flush()
    await _recompute_orphans(str(org_id), db)
    return edge


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CanvasEdge).where(CanvasEdge.id == edge_id, CanvasEdge.org_id == org_id)
    )
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(404, "Edge not found")
    await db.delete(edge)
    await _recompute_orphans(str(org_id), db)
