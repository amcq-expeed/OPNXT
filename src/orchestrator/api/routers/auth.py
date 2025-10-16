from __future__ import annotations

from fastapi import APIRouter, HTTPException, status, Depends

from ...security.auth import (
    OTPRequest,
    OTPVerifyRequest,
    TokenResponse,
    create_access_token,
    JwtConfig,
    get_current_user,
    User,
    issue_otp,
    verify_otp,
    OTP_EXP_MINUTES,
    INCLUDE_OTP_IN_RESPONSE,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp")
def request_otp(req: OTPRequest) -> dict:
    code = issue_otp(req.email)
    payload = {
        "status": "sent",
        "expires_in": OTP_EXP_MINUTES * 60,
    }
    if INCLUDE_OTP_IN_RESPONSE:
        payload["code"] = code
    return payload


@router.post("/verify-otp", response_model=TokenResponse)
def verify(req: OTPVerifyRequest) -> TokenResponse:
    try:
        user = verify_otp(req.email, req.code, name=req.name)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    cfg = JwtConfig.from_env()
    token = create_access_token(user, cfg)
    return TokenResponse(access_token=token, expires_in=cfg.expires_min * 60, user=user)


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    return user
