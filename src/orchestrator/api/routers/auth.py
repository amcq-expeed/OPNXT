from __future__ import annotations

from fastapi import APIRouter, HTTPException, status, Depends, Request

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
    should_include_otp_in_response,
)
from ...security.rate_limit import rate_limit_action, RateLimitExceeded

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp")
def request_otp(req: OTPRequest, request: Request) -> dict:
    identifier = _rate_limit_identifier(request, req.email)
    try:
        rate_limit_action(
            "otp_request",
            identifier,
            limit_env="OTP_REQUEST_LIMIT",
            window_env="OTP_REQUEST_WINDOW_SEC",
            default_limit=5,
            default_window_seconds=900,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    code = issue_otp(req.email)
    payload = {
        "status": "sent",
        "expires_in": OTP_EXP_MINUTES * 60,
    }
    if should_include_otp_in_response():
        payload["code"] = code
    return payload


@router.post("/verify-otp", response_model=TokenResponse)
def verify(req: OTPVerifyRequest, request: Request) -> TokenResponse:
    identifier = _rate_limit_identifier(request, req.email)
    try:
        rate_limit_action(
            "otp_verify",
            identifier,
            limit_env="OTP_VERIFY_LIMIT",
            window_env="OTP_VERIFY_WINDOW_SEC",
            default_limit=10,
            default_window_seconds=900,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP verification attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        user = verify_otp(req.email, req.code, name=req.name)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    cfg = JwtConfig.from_env()
    token = create_access_token(user, cfg)
    return TokenResponse(access_token=token, expires_in=cfg.expires_min * 60, user=user)


def _rate_limit_identifier(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{email.lower()}"


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    return user
