from __future__ import annotations

from typing import Optional, Tuple, Dict, Any

from fastapi.testclient import TestClient


def otp_login(
    client: TestClient,
    email: str,
    *,
    name: Optional[str] = None,
    code: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Request and verify an OTP, returning auth headers and token payload."""
    req_body: Dict[str, Any] = {"email": email}
    res = client.post("/auth/request-otp", json=req_body)
    assert res.status_code == 200, res.text
    payload = res.json()
    otp = code or _fetch_otp_from_store(email)
    assert otp, "OTP code missing; ensure test OTP retrieval helper is synchronized with auth store"

    verify_body: Dict[str, Any] = {"email": email, "code": otp}
    if name:
        verify_body["name"] = name
    res = client.post("/auth/verify-otp", json=verify_body)
    assert res.status_code == 200, res.text
    data = res.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}, data


def _fetch_otp_from_store(email: str) -> Optional[str]:
    from src.orchestrator.security import auth

    entry = auth.OTP_STORE.get(email.lower())
    if not entry:
        return None
    return entry.code


def admin_headers(client: TestClient) -> Dict[str, str]:
    headers, _ = otp_login(client, "adam.thacker@expeed.com")
    return headers


def contrib_headers(client: TestClient) -> Dict[str, str]:
    headers, _ = otp_login(client, "contrib@example.com")
    return headers


def headers_for(client: TestClient, email: str, *, name: Optional[str] = None) -> Dict[str, str]:
    headers, _ = otp_login(client, email, name=name)
    return headers
