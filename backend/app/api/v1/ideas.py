from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select

from app.core.cache import Cache, get_cache
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.models.idea import StartupIdea
from app.db.session import AsyncSession, get_session
from app.schemas.idea import IdeaCreate, IdeaRead, IdeaUpdate

router = APIRouter(prefix="/ideas", tags=["ideas"])


def _idea_cache_key(user_id: UUID, idea_id: UUID) -> str:
    # Scope the key by user as defence-in-depth (a cached value can never leak
    # to a different user even if ids were somehow reused).
    return f"idea:{user_id}:{idea_id}"


@router.post("", response_model=IdeaRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def create_idea(
    request: Request,  # required by slowapi's @limiter.limit
    payload: IdeaCreate,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StartupIdea:
    idea = StartupIdea(**payload.model_dump(), user_id=user_id)
    session.add(idea)
    await session.commit()
    await session.refresh(idea)
    return idea


@router.get("", response_model=list[IdeaRead])
async def list_ideas(
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
) -> list[StartupIdea]:
    # Note: we deliberately do NOT cache the list. Its cache key would depend on
    # limit/offset, and a single write would have to invalidate every page -
    # more trouble than it's worth. We cache the *detail* endpoint instead.
    result = await session.execute(
        select(StartupIdea)
        .where(StartupIdea.user_id == user_id)
        .order_by(StartupIdea.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/{idea_id}", response_model=IdeaRead)
async def get_idea(
    idea_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    cache: Cache = Depends(get_cache),
):
    key = _idea_cache_key(user_id, idea_id)

    # 1. Try the cache first (read-through).
    cached = await cache.get_json(key)
    if cached is not None:
        return cached

    # 2. Miss: load from the database.
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    # 3. Populate the cache for next time, then return.
    data = IdeaRead.model_validate(idea).model_dump(mode="json")
    await cache.set_json(key, data, settings.CACHE_TTL_IDEA)
    return data


@router.patch("/{idea_id}", response_model=IdeaRead)
async def update_idea(
    idea_id: UUID,
    payload: IdeaUpdate,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    cache: Cache = Depends(get_cache),
) -> StartupIdea:
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(idea, field, value)
    idea.updated_at = datetime.utcnow()

    session.add(idea)
    await session.commit()
    await session.refresh(idea)

    # Invalidate the cached copy so the next read reflects this change.
    await cache.delete(_idea_cache_key(user_id, idea_id))
    return idea


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_idea(
    idea_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    cache: Cache = Depends(get_cache),
) -> None:
    """Soft delete: mark the idea as archived rather than removing the row."""
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    idea.status = "archived"
    session.add(idea)
    await session.commit()

    await cache.delete(_idea_cache_key(user_id, idea_id))
