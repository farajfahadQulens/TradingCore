import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.logging import get_logger
from app.broker.client import CapitalComConstants
logger = get_logger(__name__)
class SessionManager:
    def __init__(self):
        self.token_expiry: datetime | None = None
        self.lock = asyncio.Lock()
        self.connected = False
        self.cst_token: str | None = None
        self.security_token: str | None = None
        self._session: aiohttp.ClientSession | None = None
    async def start(self):
        self._session = aiohttp.ClientSession()
        await self.ensure_valid()
    async def close(self):
        if self._session:
            await self._session.close()
    async def ensure_valid(self):
        async with self.lock:
            if not self.token_expiry or self.token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5):
                await self._refresh()
    async def _refresh(self):
        if not settings.capital_username or not settings.capital_password or not settings.capital_api_key:
            logger.warning("Capital credentials missing – session manager will not authenticate")
            self.connected = False
            return

        async with self._session.post(
            CapitalComConstants.SESSION_ENDPOINT,
            json={
                "identifier": settings.capital_username.get_secret_value(),
                "password": settings.capital_password.get_secret_value(),
            },
            headers={
                "Content-Type": "application/json",
                "X-CAP-API-KEY": settings.capital_api_key.get_secret_value(),
            },
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise Exception(f"Session refresh failed: {resp.status} - {body}")
            self.cst_token = resp.headers["CST"]
            self.security_token = resp.headers["X-SECURITY-TOKEN"]
            self.token_expiry = datetime.now(timezone.utc) + timedelta(minutes=9)
            self.connected = True
            logger.info("session_refreshed", expiry=self.token_expiry.isoformat())
session_manager = SessionManager()