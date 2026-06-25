from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import require_admin
from ..models import CurrentUser, LoginRequest, UserCreate, UserUpdate


router = APIRouter(prefix="/api/auth", tags=["auth"])


def auth_service():
    from ..main import app_state

    return app_state.auth


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service=Depends(auth_service),
) -> CurrentUser:
    return await service.login(payload.username, payload.password, response=response, request=request)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    service=Depends(auth_service),
) -> dict[str, bool]:
    return await service.logout(request, response)


@router.get("/me")
async def me(request: Request, service=Depends(auth_service)) -> CurrentUser:
    user = getattr(request.state, "current_user", None)
    if user:
        return user
    user = await service.user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    request.state.current_user = user
    return user


@router.get("/users")
async def users(
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(auth_service),
) -> list[CurrentUser]:
    return await service.list_users()


@router.post("/users")
async def create_user(
    payload: UserCreate,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(auth_service),
) -> CurrentUser:
    return await service.create_user(
        username=payload.username,
        password=payload.password,
        display_name=payload.displayName,
        role=payload.role,
        active=payload.active,
    )


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    _admin: CurrentUser = Depends(require_admin),
    service=Depends(auth_service),
) -> CurrentUser:
    return await service.update_user(user_id, payload.model_dump(exclude_unset=True))
