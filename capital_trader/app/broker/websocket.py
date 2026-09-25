"""WebSocket client for market data streaming.
"""
import asyncio
import json
import websockets
from .session import SessionManager
from app.core.config import settings
from app.core.logging import get_logger
from app.queue_manager import price_queue
from app.services.runtime_status import runtime_status

log = get_logger(__name__)

SUBSCRIPTIONS = ["GOLD", "US500", "BTCUSD"]  # List of epics to subscribe to - can be made dynamic later


class BrokerWebSocket:
    URL = settings.broker_ws_url
    BACKOFF = [1, 2, 4, 8, 15]

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._running = False

    async def connect(self):
        self._running = True
        for delay in self.BACKOFF:
            try:
                await self._connect()
                return
            except Exception as e:
                log.warning("websocket_connect_failed", delay=delay, error=str(e))
                await asyncio.sleep(delay)
        log.error("websocket_connect_exhausted")
        raise Exception("WebSocket failed to connect after all retries")

    async def _connect(self):
        await self.session_mgr.ensure_valid()
        self.ws = await websockets.connect(self.URL)
        log.info("websocket_connected", url=self.URL)
        await self._subscribe()
        runtime_status.mark_websocket_connected(SUBSCRIPTIONS)
        asyncio.create_task(self._heartbeat())
        asyncio.create_task(self._receive_loop())

    async def _subscribe(self):
        for epic in SUBSCRIPTIONS:
            msg = json.dumps({
                "destination": "marketData.subscribe",
                "correlationId": epic,
                "cst": self.session_mgr.cst_token,
                "securityToken": self.session_mgr.security_token,
                "payload": {"epics": [epic]}
            })
            await self.ws.send(msg)
            log.info("websocket_subscribed", epic=epic)

    async def _heartbeat(self):
        while self._running and self.ws:
            try:
                await self.ws.send(json.dumps({"destination": "ping",
                "CST": self.session_mgr.cst_token,
                "X-SECURITY-TOKEN": self.session_mgr.security_token}))
                await asyncio.sleep(30)
            except Exception as e:
                log.warning("websocket_heartbeat_failed", error=str(e))
                break

    async def _receive_loop(self):
        try:
            async for msg in self.ws:
                try:
                    data = json.loads(msg)
                    await price_queue.put(data)
                except Exception as e:
                    log.error("websocket_message_error", error=str(e))
        except Exception as e:
            log.warning("websocket_disconnected", error=str(e))
            runtime_status.mark_websocket_disconnected(e)
            if self._running:
                log.info("websocket_reconnecting")
                await self.connect()

    async def close(self):
        self._running = False
        if self.ws:
            await self.ws.close()
            runtime_status.mark_websocket_disconnected()
            log.info("websocket_closed")
