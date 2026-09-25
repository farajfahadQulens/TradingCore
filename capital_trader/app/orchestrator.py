"""Main orchestrator that boots the whole system.
"""
import asyncio
from app.services.startup_service import StartupService
from app.market.streaming import MarketStreamer
from app.core.logging import get_logger
from app.services.reconciliation_service import reconciliation_service
from app.services.candle_service import candle_service
from app.services.trading_service import trading_service
from app.market.signals import signal_detector
from app.services.redis_event_bridge import bridge_worker

log = get_logger(__name__)


class Orchestrator:
    def __init__(self):
        self.startup = StartupService()
        self.market = MarketStreamer()

    async def run(self):
        log.info("orchestrator_starting")
        await self.startup.run()
        await signal_detector.start()
        await candle_service.start()
        await trading_service.start()
        asyncio.create_task(self.market.run())
        asyncio.create_task(reconciliation_service.run())
        asyncio.create_task(bridge_worker())
        log.info("orchestrator_started")