import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.broker.session import session_manager
from app.core.state import TradingMode, trading_state
from app.services.health_service import HealthService
from app.services.runtime_status import runtime_status


class HealthServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_session = {
            "connected": session_manager.connected,
            "cst_token": session_manager.cst_token,
            "security_token": session_manager.security_token,
            "token_expiry": session_manager.token_expiry,
        }
        self.original_mode = trading_state.mode

    def tearDown(self):
        session_manager.connected = self.original_session["connected"]
        session_manager.cst_token = self.original_session["cst_token"]
        session_manager.security_token = self.original_session["security_token"]
        session_manager.token_expiry = self.original_session["token_expiry"]
        trading_state.mode = self.original_mode

        runtime_status.websocket_connected = False
        runtime_status.websocket_last_connected_at = None
        runtime_status.websocket_last_disconnected_at = None
        runtime_status.websocket_last_error = None
        runtime_status.websocket_subscriptions = []
        runtime_status.last_price_tick_at = None
        runtime_status.last_price_tick_epic = None
        runtime_status.redis_bridge_subscribed = False
        runtime_status.redis_last_publish_at = None
        runtime_status.redis_last_error = None
        runtime_status.reconciliation_running = False
        runtime_status.reconciliation_last_started_at = None
        runtime_status.reconciliation_last_completed_at = None
        runtime_status.reconciliation_last_error = None
        runtime_status.reconciliation_last_counts = {"positions": 0, "orders": 0}

    async def test_deep_health_reports_healthy_components(self):
        session_manager.connected = True
        session_manager.cst_token = "cst"
        session_manager.security_token = "security"
        session_manager.token_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        trading_state.mode = TradingMode.LIVE_TRADING
        runtime_status.mark_websocket_connected(["GOLD"])
        runtime_status.mark_price_tick("GOLD")
        runtime_status.mark_redis_subscribed()
        runtime_status.mark_redis_publish()
        runtime_status.mark_reconciliation_completed(positions=1, orders=0)

        service = HealthService()
        with patch.object(service, "_database_status", AsyncMock(return_value={"status": "healthy"})):
            with patch.object(service, "_redis_status", AsyncMock(return_value={"status": "healthy"})):
                result = await service.deep_health()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["components"]["broker_session"]["status"], "healthy")
        self.assertEqual(result["components"]["websocket"]["subscriptions"], ["GOLD"])
        self.assertEqual(result["components"]["reconciliation"]["last_counts"]["positions"], 1)

    async def test_deep_health_degrades_when_runtime_signals_are_missing(self):
        session_manager.connected = True
        session_manager.cst_token = "cst"
        session_manager.security_token = "security"
        session_manager.token_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        trading_state.mode = TradingMode.OBSERVE_ONLY

        service = HealthService()
        with patch.object(service, "_database_status", AsyncMock(return_value={"status": "healthy"})):
            with patch.object(service, "_redis_status", AsyncMock(return_value={"status": "healthy"})):
                result = await service.deep_health()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["components"]["websocket"]["status"], "degraded")
        self.assertEqual(result["components"]["prices"]["status"], "degraded")
        self.assertEqual(result["components"]["trading"]["mode"], "observe")

    async def test_deep_health_is_unhealthy_when_database_is_unhealthy(self):
        session_manager.connected = True
        session_manager.cst_token = "cst"
        session_manager.security_token = "security"
        session_manager.token_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

        service = HealthService()
        with patch.object(service, "_database_status", AsyncMock(return_value={"status": "unhealthy", "error": "db down"})):
            with patch.object(service, "_redis_status", AsyncMock(return_value={"status": "healthy"})):
                result = await service.deep_health()

        self.assertEqual(result["status"], "unhealthy")
        self.assertEqual(result["components"]["database"]["error"], "db down")
