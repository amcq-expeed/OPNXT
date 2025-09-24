import jwt
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.security.auth import decode_token, JwtConfig


client = TestClient(app)


def test_public_mode_allows_anonymous(monkeypatch):
    monkeypatch.setenv("OPNXT_PUBLIC_MODE", "true")
    r = client.get("/projects")
    assert r.status_code == 200


def test_non_public_mode_requires_token(monkeypatch):
    monkeypatch.setenv("OPNXT_PUBLIC_MODE", "false")
    r = client.get("/projects")
    assert r.status_code == 401


def test_invalid_token_in_public_mode(monkeypatch):
    monkeypatch.setenv("OPNXT_PUBLIC_MODE", "true")
    r = client.get("/projects", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 200


def test_decode_token_expired():
    cfg = JwtConfig(secret="unit-test-secret", expires_min=1)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user@example.com",
        "name": "User",
        "roles": ["viewer"],
        "iat": int((now - timedelta(minutes=10)).timestamp()),
        "exp": int((now - timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(payload, cfg.secret, algorithm=cfg.algorithm)
    try:
        decode_token(token, cfg=cfg)
        assert False, "Expected expired token to raise"
    except Exception as e:
        # FastAPI HTTPException with 401
        assert "expired" in str(e).lower()
