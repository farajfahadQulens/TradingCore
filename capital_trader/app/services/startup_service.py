"""Startup sequence.
"""
from app.core.logging import get_logger, configure_logging
from app.core.state import trading_state, TradingMode
from app.core.config import settings
from app.broker.session import session_manager
from app.broker.websocket import BrokerWebSocket
from app.core.logging import get_logger

log = get_logger(__name__)


class StartupService:
    def __init__(self):
        self.ws = BrokerWebSocket(session_manager)
        log.info("startup_service_initialized")

    async def run(self):
        configure_logging()
        await self.ws.connect()
        if settings.allow_live_trading:
            trading_state.enable_trading()
            return

        trading_state.mode = TradingMode.OBSERVE_ONLY
        log.warning("live_trading_not_enabled", mode=trading_state.mode.value)
