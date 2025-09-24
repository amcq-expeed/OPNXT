from __future__ import annotations

from fastapi import APIRouter, HTTPException, status, Depends

from ...security.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    authenticate,
    create_access_token,
    JwtConfig,
    get_current_user,
    User,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    user = authenticate(req.email, req.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    cfg = JwtConfig.from_env()
    token = create_access_token(user, cfg)
    return TokenResponse(access_token=token, expires_in=cfg.expires_min * 60, user=user)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest) -> TokenResponse:
    """Open registration for development/demo.

    Assigns the 'viewer' role by default to avoid privilege escalation in open flows.
    """
    try:
        user = register_user(req.email, req.name, req.password, roles=["viewer"])  # force viewer by default
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    cfg = JwtConfig.from_env()
    token = create_access_token(user, cfg)
    return TokenResponse(access_token=token, expires_in=cfg.expires_min * 60, user=user)


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    return user
