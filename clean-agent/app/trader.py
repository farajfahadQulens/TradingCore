"""HTTP client for the existing Capital Trader service.

This client intentionally speaks to Capital Trader over its public HTTP API.
It does not import or modify Capital Trader code.
"""

import asyncio
import threading
from typing import Any

import httpx

from app.config import settings


EPIC_ALIASES = {
    "GOLD": "GOLD",
    "XAU": "GOLD",
    "XAUUSD": "GOLD",
    "XAU/USD": "GOLD",
    "SPOTGOLD": "GOLD",
    "SPOT_GOLD": "GOLD",
}


def normalize_epic(epic: str) -> str:
    """Normalize common user-facing symbols to Capital Trader epics."""

    value = str(epic).strip().upper()
    compact = value.replace(" ", "").replace("-", "").replace(".", "")
    return EPIC_ALIASES.get(value, EPIC_ALIASES.get(compact, value))


class TraderClient:
    """Small async wrapper around Capital Trader endpoints."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.trader_base_url

    def _timeout(self) -> httpx.Timeout:
        """Use short, explicit phase limits for broker calls."""

        seconds = settings.trader_timeout_seconds
        return httpx.Timeout(
            seconds,
            connect=min(1.0, seconds),
            read=seconds,
            write=seconds,
            pool=min(1.0, seconds),
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Call Capital Trader and return decoded JSON."""

        loop = asyncio.get_running_loop()
        result: asyncio.Future[Any] = loop.create_future()

        def worker() -> None:
            try:
                value = self._request_sync(method, path, kwargs)
            except Exception as exc:
                loop.call_soon_threadsafe(self._finish, result, None, exc)
            else:
                loop.call_soon_threadsafe(self._finish, result, value, None)

        threading.Thread(target=worker, daemon=True).start()
        return await result

    async def request_text(self, method: str, path: str, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._request_text_sync, method, path, kwargs)

    @staticmethod
    def _finish(future: asyncio.Future[Any], value: Any, error: Exception | None) -> None:
        """Complete a broker future unless its caller already timed out."""

        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(value)

    def _request_sync(self, method: str, path: str, kwargs: dict[str, Any]) -> Any:
        """Perform blocking broker I/O outside the agent event loop."""

        response = self._request_response_sync(method, path, kwargs)
        if not response.content:
            return {}
        return response.json()

    def _request_text_sync(self, method: str, path: str, kwargs: dict[str, Any]) -> str:
        response = self._request_response_sync(method, path, kwargs)
        return response.text

    def _request_response_sync(
        self,
        method: str,
        path: str,
        kwargs: dict[str, Any],
    ) -> httpx.Response:
        with httpx.Client(base_url=self.base_url, timeout=self._timeout()) as client:
            response = client.request(method, path, **kwargs)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:500]
                raise httpx.HTTPStatusError(
                    f"Capital Trader {response.status_code} on {method} {path}: {detail}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
            return response

    async def health(self) -> dict[str, Any]:
        return await self.request("GET", "/api/health")

    async def deep_health(self) -> dict[str, Any]:
        return await self.request("GET", "/api/health/deep")

    async def balance(self) -> dict[str, Any]:
        return await self.request("GET", "/api/debug/equity")

    async def positions(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/positions")

    async def orders(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/orders")

    async def trade_logs(self, limit: int = 10) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/audit/trade-log", params={"limit": limit})

    async def prices(self, epic: str, resolution: str = "MINUTE", max_points: int = 20) -> dict[str, Any]:
        params = {"resolution": resolution, "max_points": max_points}
        return await self.request("GET", f"/api/v1/market/prices/{normalize_epic(epic)}", params=params)

    async def gold_candles_csv(
        self,
        limit: int = 1000,
        start: str | None = None,
        end: str | None = None,
        offset: int = 0,
    ) -> str:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self.request_text("GET", "/api/v1/market/gold/candles.csv", params=params)

    async def market(self, epic: str) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/market/{normalize_epic(epic)}")

    async def risk_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "epic" in payload:
            payload = {**payload, "epic": normalize_epic(str(payload["epic"]))}
        return await self.request("POST", "/api/v1/workflow/risk-preview", json=payload)

    async def close_preview(self, deal_id: str) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/workflow/positions/{deal_id}/close-preview")

    async def close_position(self, deal_id: str) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/workflow/positions/{deal_id}/close")

    async def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "epic" in payload:
            payload = {**payload, "epic": normalize_epic(str(payload["epic"]))}
        return await self.request("POST", "/api/v1/workflow/orders", json=payload)


trader_client = TraderClient()
