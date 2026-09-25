from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.core.state import TradingMode, trading_state
from app.services.startup_service import StartupService


class StartupServiceTests(IsolatedAsyncioTestCase):
    async def test_startup_stays_observe_only_unless_live_trading_is_allowed(self):
        trading_state.mode = TradingMode.LIVE_TRADING
        service = StartupService()
        service.ws.connect = AsyncMock()

        with patch("app.services.startup_service.settings.allow_live_trading", False):
            await service.run()

        service.ws.connect.assert_awaited_once()
        self.assertEqual(trading_state.mode, TradingMode.OBSERVE_ONLY)

    async def test_startup_can_enable_live_trading_explicitly(self):
        trading_state.mode = TradingMode.OBSERVE_ONLY
        service = StartupService()
        service.ws.connect = AsyncMock()

        with patch("app.services.startup_service.settings.allow_live_trading", True):
            await service.run()

        service.ws.connect.assert_awaited_once()
        self.assertEqual(trading_state.mode, TradingMode.LIVE_TRADING)
