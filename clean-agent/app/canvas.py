"""Read-only Canvas OAuth2 integration for the BI Canvas instance."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet

from app.config import settings
from app.store import store


class CanvasConfigurationError(RuntimeError):
    """Raised when Canvas OAuth is not configured."""


def _require_config() -> None:
    if not settings.canvas_client_id or not settings.canvas_client_secret:
        raise CanvasConfigurationError("Canvas OAuth client credentials are not configured")
    if not settings.canvas_token_encryption_key:
        raise CanvasConfigurationError("CANVAS_TOKEN_ENCRYPTION_KEY is not configured")


def _fernet() -> Fernet:
    _require_config()
    try:
        return Fernet(settings.canvas_token_encryption_key.encode())
    except ValueError as exc:
        raise CanvasConfigurationError("CANVAS_TOKEN_ENCRYPTION_KEY is invalid") from exc


def canvas_status() -> dict[str, Any]:
    """Return connection state without exposing credentials."""

    token = store.get_integration_token("canvas")
    return {
        "provider": "canvas",
        "connected": token is not None,
        "base_url": settings.canvas_base_url,
        "configured": bool(
            settings.canvas_client_id
            and settings.canvas_client_secret
            and settings.canvas_token_encryption_key
        ),
        "expires_at": token.get("expires_at") if token else None,
    }


def create_authorization_url() -> str:
    """Create a one-time OAuth authorization URL."""

    _require_config()
    state = secrets.token_urlsafe(32)
    store.save_oauth_state(state, expires_at=time.time() + 600)
    query = urlencode(
        {
            "client_id": settings.canvas_client_id,
            "response_type": "code",
            "redirect_uri": settings.canvas_redirect_uri,
            "state": state,
            "scope": (
                "url:GET|/api/v1/users/self/courses "
                "url:GET|/api/v1/users/self/upcoming_events "
                "url:GET|/api/v1/users/self/todo"
            ),
            "purpose": "Clean Agent read-only study assistant",
        }
    )
    return f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/auth?{query}"


async def complete_authorization(code: str, state: str) -> dict[str, Any]:
    """Validate OAuth state, exchange the code, and encrypt the token response."""

    _require_config()
    if not store.consume_oauth_state(state):
        raise CanvasConfigurationError("Canvas OAuth state is invalid or expired")

    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.canvas_client_id,
        "client_secret": settings.canvas_client_secret,
        "redirect_uri": settings.canvas_redirect_uri,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=settings.canvas_timeout_seconds) as client:
        response = await client.post(f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/token", data=payload)
        response.raise_for_status()
        token = response.json()

    store.save_integration_token(
        "canvas",
        _encrypt_token(token),
        expires_at=time.time() + float(token.get("expires_in", 3600)),
    )
    store.audit("canvas_connected", {"base_url": settings.canvas_base_url})
    return canvas_status()


class CanvasClient:
    """Small Canvas API client using the encrypted OAuth token."""

    async def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = store.get_integration_token("canvas")
        if not token:
            raise CanvasConfigurationError("Canvas is not connected")
        payload = _decrypt_token(token["token"])
        if token.get("expires_at") and token["expires_at"] <= time.time() + 30:
            payload = await self._refresh(payload.get("refresh_token"))
            access_token = payload.get("access_token")
        else:
            access_token = payload.get("access_token")
        if not access_token:
            raise CanvasConfigurationError("Canvas token has no access token")

        async with httpx.AsyncClient(
            base_url=settings.canvas_base_url.rstrip("/"),
            timeout=settings.canvas_timeout_seconds,
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    async def _refresh(self, refresh_token: str | None) -> dict[str, Any]:
        """Refresh an expiring Canvas token and retain the reusable refresh token."""

        if not refresh_token:
            raise CanvasConfigurationError("Canvas token has expired and no refresh token is available")
        payload = {
            "grant_type": "refresh_token",
            "client_id": settings.canvas_client_id,
            "client_secret": settings.canvas_client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=settings.canvas_timeout_seconds) as client:
            response = await client.post(f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/token", data=payload)
            response.raise_for_status()
            refreshed = response.json()
        refreshed.setdefault("refresh_token", refresh_token)
        store.save_integration_token(
            "canvas",
            _encrypt_token(refreshed),
            expires_at=time.time() + float(refreshed.get("expires_in", 3600)),
        )
        return refreshed

    async def courses(self) -> Any:
        return await self.request("/api/v1/users/self/courses", {"enrollment_state": "active", "per_page": 100})

    async def upcoming_events(self) -> Any:
        return await self.request("/api/v1/users/self/upcoming_events", {"per_page": 100})

    async def todo(self) -> Any:
        return await self.request("/api/v1/users/self/todo", {"per_page": 100})


def _encrypt_token(value: dict[str, Any]) -> str:
    """Encrypt a token payload before it reaches SQLite."""

    return _fernet().encrypt(json.dumps(value).encode()).decode()


def _decrypt_token(value: str) -> dict[str, Any]:
    """Decrypt a token payload retrieved from SQLite."""

    return json.loads(_fernet().decrypt(value.encode()))


canvas_client = CanvasClient()
