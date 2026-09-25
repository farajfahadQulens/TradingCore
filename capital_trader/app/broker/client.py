"""Async HTTP client for Capital.com REST API.
"""
import aiohttp
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CapitalComConstants:
    API_VERSION = "v1"
    BASE_URL = 'https://api-capital.backend-capital.com/api/{}/'.format(API_VERSION)

    SESSION_ENDPOINT = BASE_URL + "session"
    ACCOUNTS_ENDPOINT = BASE_URL + "accounts"
    POSITIONS_ENDPOINT = BASE_URL + "positions"
    ORDERS_ENDPOINT = BASE_URL + "workingorders"
    PRICES_ENDPOINT = BASE_URL + "prices"
    MARKETS_ENDPOINT = BASE_URL + "markets"
    PING_ENDPOINT = BASE_URL + "ping"
    HISTORY_ENDPOINT = BASE_URL + "history/activity"
    TRANSACTIONS_ENDPOINT = BASE_URL + "history/transactions"
    CLIENTSENTIMENT_ENDPOINT = BASE_URL + "clientsentiment"


class BrokerClient:
    def __init__(self):
        self.api_key = settings.capital_api_key.get_secret_value()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        from app.broker.session import session_manager
        self._session = aiohttp.ClientSession()
        await session_manager.ensure_valid()
        self._session_manager = session_manager
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            logger.info("broker_session_closed")

    def _headers(self) -> dict:
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self._session_manager.cst_token or "",
            "X-SECURITY-TOKEN": self._session_manager.security_token or "",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        async with self._session.request(
            method, url, headers=self._headers(), **kwargs
        ) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                logger.error("broker_request_failed", status=resp.status, url=url, body=body)
                raise Exception(f"Request failed: {resp.status} - {body}")
            return await resp.json()

    async def get_balance(self) -> dict:
        data = await self._request("GET", CapitalComConstants.ACCOUNTS_ENDPOINT)
        balance = data["accounts"][0]["balance"]
        logger.info("balance_retrieved", balance=balance)
        return balance

    async def get_positions(self) -> dict:
        data = await self._request("GET", CapitalComConstants.POSITIONS_ENDPOINT)
        logger.info("positions_retrieved", count=len(data.get("positions", [])))
        return data

    async def get_working_orders(self) -> dict:
        data = await self._request("GET", CapitalComConstants.ORDERS_ENDPOINT)
        logger.info("working_orders_retrieved", count=len(data.get("workingOrders", [])))
        return data

    async def get_history(self, from_date: str, to_date: str) -> dict:
        url = f"{CapitalComConstants.HISTORY_ENDPOINT}?from={from_date}&to={to_date}&detailed=true"
        data = await self._request("GET", url)
        logger.info("history_retrieved", count=len(data.get("activities", [])))
        return data

    async def get_accounts(self) -> dict:
        data = await self._request("GET", CapitalComConstants.ACCOUNTS_ENDPOINT)
        logger.info("accounts_retrieved", count=len(data.get("accounts", [])))
        return data
    
    async def get_prices(self, epic: str , resolution: str = "MINUTE", max_points: int = 60 , from_date: str = None, to_date: str = None) -> dict:
        url = f"{CapitalComConstants.PRICES_ENDPOINT}/{epic}?resolution={resolution}&max={max_points}"
        if from_date:
            url += f"&from={from_date}"
        if to_date:
            url += f"&to={to_date}"
        data = await self._request("GET", url)
        logger.info("prices_retrieved", epic=epic)
        return data

    async def get_market(self, epic: str) -> dict:
        url = f"{CapitalComConstants.MARKETS_ENDPOINT}/{epic}"
        data = await self._request("GET", url)
        logger.info("market_retrieved", epic=epic)
        return data
    
    async def get_transactions(self, from_date: str, to_date: str) -> dict:
        url = f"{CapitalComConstants.TRANSACTIONS_ENDPOINT}?from={from_date}&to={to_date}&detailed=true"
        data = await self._request("GET", url)
        logger.info("transactions_retrieved", count=len(data.get("transactions", [])))
        return data

    async def ping(self) -> dict:
        data = await self._request("GET", CapitalComConstants.PING_ENDPOINT)
        logger.info("ping_successful")
        return data
    
    async def get_client_sentiment(self, epic: str) -> dict:
        url = f"{CapitalComConstants.CLIENTSENTIMENT_ENDPOINT}/{epic}"
        data = await self._request("GET", url)
        logger.info("client_sentiment_retrieved", epic=epic)
        return data
    
    async def place_order(self, epic: str, direction: str, size: float, order_type: str = "MARKET", level: float | None = None, limit_distance: float | None = None, stop_distance: float | None = None) -> dict:
        if order_type.upper() == "MARKET":
            payload = {"epic": epic, "direction": direction, "size": size}
            if limit_distance is not None:
                payload["limitDistance"] = limit_distance
            if stop_distance is not None:
                payload["stopDistance"] = stop_distance
            data = await self._request("POST", CapitalComConstants.POSITIONS_ENDPOINT, json=payload)
        else:
            payload = {"epic": epic, "direction": direction, "size": size, "type": order_type}
            if level is not None:
                payload["level"] = level
            if limit_distance is not None:
                payload["limitDistance"] = limit_distance
            if stop_distance is not None:
                payload["stopDistance"] = stop_distance
            data = await self._request("POST", CapitalComConstants.ORDERS_ENDPOINT, json=payload)
        logger.info("order_placed", epic=epic, direction=direction, size=size, order_type=order_type)
        return data
    
    async def cancel_order(self, order_id: str) -> dict:
        url = f"{CapitalComConstants.ORDERS_ENDPOINT}/{order_id}"
        data = await self._request("DELETE", url)
        logger.info("order_cancelled", order_id=order_id)
        return data
    
    async def close_position(self, position_id: str) -> dict:
        url = f"{CapitalComConstants.POSITIONS_ENDPOINT}/{position_id}"
        data = await self._request("DELETE", url)
        logger.info("position_closed", position_id=position_id)
        return data
    
    async def update_position(self, position_id: str, limit_distance: float = None, stop_distance: float = None) -> dict:
        payload = {}
        if limit_distance is not None:
            payload["limitDistance"] = limit_distance
        if stop_distance is not None:
            payload["stopDistance"] = stop_distance

        url = f"{CapitalComConstants.POSITIONS_ENDPOINT}/{position_id}"
        data = await self._request("PUT", url, json=payload)
        logger.info("position_updated", position_id=position_id)
        return data
    
    async def update_order(self, order_id: str, limit_distance: float = None, stop_distance: float = None) -> dict:
        payload = {}
        if limit_distance is not None:
            payload["limitDistance"] = limit_distance
        if stop_distance is not None:
            payload["stopDistance"] = stop_distance

        url = f"{CapitalComConstants.ORDERS_ENDPOINT}/{order_id}"
        data = await self._request("PUT", url, json=payload)
        logger.info("order_updated", order_id=order_id)
        return data
    
   
