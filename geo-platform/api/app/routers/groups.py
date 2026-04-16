import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.groups import MsGroup, CustomGroupMember, CustomGroupMsLink
from app.models.users import User
from app.config import settings

router = APIRouter(prefix="/groups", tags=["groups"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class GroupCreate(BaseModel):
    display_name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None


class GroupResponse(BaseModel):
    id: uuid.UUID
    ms_group_id: str
    display_name: Optional[str]
    description: Optional[str]
    is_custom: bool
    synced_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: Optional[str]
    added_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID


class MsLinkResponse(BaseModel):
    custom_group_id: uuid.UUID
    ms_group_id: str
    ms_display_name: Optional[str]
    linked_at: datetime

    model_config = {"from_attributes": True}


class AddMsLinkRequest(BaseModel):
    ms_group_id: str
    ms_display_name: Optional[str] = None


class MsGroupSearchResult(BaseModel):
    ms_group_id: str
    display_name: Optional[str]
    description: Optional[str]
    linked_to_groups: List[uuid.UUID]  # custom group IDs this MS group is already linked to


# ── Custom groups CRUD ─────────────────────────────────────────────────────────

@router.get("", response_model=List[GroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """List all custom groups."""
    result = await db.execute(
        select(MsGroup).where(MsGroup.is_custom == True).order_by(MsGroup.display_name)
    )
    return result.scalars().all()


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """Create a custom group. Permissions are assigned to custom groups."""
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    internal_id = f"custom:{uuid.uuid4()}"
    obj = MsGroup(
        ms_group_id=internal_id,
        display_name=body.display_name,
        description=body.description,
        is_custom=True,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group not found")
    return obj


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group not found")
    if not obj.is_custom:
        raise HTTPException(status_code=400, detail="Cannot edit a non-custom group")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group not found")
    if not obj.is_custom:
        raise HTTPException(status_code=400, detail="Cannot delete a non-custom group")
    await db.delete(obj)
    await db.commit()


# ── Manual members ─────────────────────────────────────────────────────────────

@router.get("/{group_id}/members", response_model=List[MemberResponse])
async def list_members(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    rows = await db.execute(
        select(CustomGroupMember, User)
        .join(User, User.id == CustomGroupMember.user_id)
        .where(CustomGroupMember.group_id == group_id)
        .order_by(User.email)
    )
    return [
        MemberResponse(
            user_id=member.user_id,
            email=user.email,
            display_name=user.display_name,
            added_at=member.added_at,
        )
        for member, user in rows.all()
    ]


@router.post("/{group_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: uuid.UUID,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if not group.is_custom:
        raise HTTPException(status_code=400, detail="Can only manage members of custom groups")

    user_result = await db.execute(select(User).where(User.id == body.user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.execute(
        select(CustomGroupMember).where(
            CustomGroupMember.group_id == group_id,
            CustomGroupMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member")

    member = CustomGroupMember(
        group_id=group_id,
        user_id=body.user_id,
        added_by=uuid.UUID(ctx.user_id),
    )
    db.add(member)
    await db.commit()
    return {"group_id": str(group_id), "user_id": str(body.user_id)}


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(
        select(CustomGroupMember).where(
            CustomGroupMember.group_id == group_id,
            CustomGroupMember.user_id == user_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(obj)
    await db.commit()


# ── Microsoft group links ──────────────────────────────────────────────────────
# Link MS Entra groups to a custom group so their members inherit the group's permissions.

@router.get("/{group_id}/ms-links", response_model=List[MsLinkResponse])
async def list_ms_links(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """List all Microsoft groups linked to this custom group."""
    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Group not found")

    rows = await db.execute(
        select(CustomGroupMsLink).where(CustomGroupMsLink.custom_group_id == group_id)
        .order_by(CustomGroupMsLink.ms_display_name)
    )
    return rows.scalars().all()


@router.post("/{group_id}/ms-links", response_model=MsLinkResponse, status_code=status.HTTP_201_CREATED)
async def add_ms_link(
    group_id: uuid.UUID,
    body: AddMsLinkRequest,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """Link a Microsoft Entra group to a custom group.
    All members of the MS group will inherit this custom group's permissions.
    """
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if not group.is_custom:
        raise HTTPException(status_code=400, detail="Can only link MS groups to custom groups")

    existing = await db.execute(
        select(CustomGroupMsLink).where(
            CustomGroupMsLink.custom_group_id == group_id,
            CustomGroupMsLink.ms_group_id == body.ms_group_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="MS group already linked")

    link = CustomGroupMsLink(
        custom_group_id=group_id,
        ms_group_id=body.ms_group_id,
        ms_display_name=body.ms_display_name,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


@router.delete("/{group_id}/ms-links/{ms_group_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_ms_link(
    group_id: uuid.UUID,
    ms_group_id: str,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """Unlink a Microsoft Entra group from a custom group."""
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(
        select(CustomGroupMsLink).where(
            CustomGroupMsLink.custom_group_id == group_id,
            CustomGroupMsLink.ms_group_id == ms_group_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(obj)
    await db.commit()


# ── MS group search ────────────────────────────────────────────────────────────

@router.get("/ms/search", response_model=List[MsGroupSearchResult])
async def search_ms_groups(
    q: str,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """
    Search Microsoft Entra for groups by name.
    Returns matching groups and which custom groups they are already linked to.
    Returns empty list in DEV_MODE (no MS credentials available).
    """
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    if settings.dev_mode:
        return []

    import httpx
    token_url = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data={
            "grant_type": "client_credentials",
            "client_id": settings.ms_client_id,
            "client_secret": settings.ms_client_secret,
            "scope": "https://graph.microsoft.com/.default",
        })
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        graph_resp = await client.get(
            "https://graph.microsoft.com/v1.0/groups",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$filter": f"startswith(displayName,'{q}')",
                "$top": "20",
                "$select": "id,displayName,description",
            },
        )
        graph_resp.raise_for_status()
        ms_groups = graph_resp.json().get("value", [])

    # Which custom groups is each MS group already linked to?
    ms_ids = [g["id"] for g in ms_groups]
    existing = await db.execute(
        select(CustomGroupMsLink.ms_group_id, CustomGroupMsLink.custom_group_id)
        .where(CustomGroupMsLink.ms_group_id.in_(ms_ids))
    )
    links: dict[str, list[uuid.UUID]] = {}
    for ms_id, cg_id in existing.all():
        links.setdefault(ms_id, []).append(cg_id)

    return [
        MsGroupSearchResult(
            ms_group_id=g["id"],
            display_name=g.get("displayName"),
            description=g.get("description"),
            linked_to_groups=links.get(g["id"], []),
        )
        for g in ms_groups
    ]
