"""Minimal ASGI reverse proxy used to expose an upstream service on a sub-path."""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


class UpstreamProxy:
    """Forward HTTP traffic to an upstream ASGI/HTTP service on the same host."""

    def __init__(self, upstream_url: str, strip_prefix: str = "") -> None:
        self._base_url = upstream_url.rstrip("/")
        self._strip_prefix = strip_prefix.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _upstream_path(self, path: str) -> str:
        if self._strip_prefix and path.startswith(self._strip_prefix):
            path = path[len(self._strip_prefix) :]
        if not path.startswith("/"):
            path = f"/{path}"
        return path or "/"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=None)
        return self._client

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return

        if scope["type"] != "http":
            return

        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        query = scope.get("query_string", b"").decode("latin-1")
        url = self._upstream_path(scope["path"])
        if query:
            url = f"{url}?{query}"

        headers = []
        for raw_name, raw_value in scope["headers"]:
            name = raw_name.decode("latin-1")
            if name.lower() in _HOP_BY_HOP or name.lower() == "host":
                continue
            headers.append((name, raw_value.decode("latin-1")))

        client = await self._get_client()
        request = client.build_request(
            scope["method"],
            url,
            headers=headers,
            content=body,
        )

        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            payload = f'{{"detail":"upstream unavailable: {exc}"}}'.encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 502,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return

        response_headers = [
            (raw_name, raw_value)
            for raw_name, raw_value in response.headers.raw
            if raw_name.decode("latin-1").lower() not in _HOP_BY_HOP
        ]

        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": response_headers,
            }
        )

        try:
            async for chunk in response.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        except httpx.HTTPError:
            pass
        finally:
            await response.aclose()

        await send({"type": "http.response.body", "body": b""})


__all__ = ["UpstreamProxy", "urlencode"]
