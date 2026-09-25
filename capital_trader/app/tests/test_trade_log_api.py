import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.audit import list_trade_logs
from app.db.models.trade_log import TradeLog
from app.services.trade_log_service import trade_log_to_dict


class TradeLogApiTests(unittest.IsolatedAsyncioTestCase):
    def test_trade_log_to_dict_serializes_model(self):
        created_at = datetime.now(timezone.utc)
        log = TradeLog(
            id="log-1",
            event_type="risk_preview",
            payload={"approved": False},
            correlation_id="corr-1",
            created_at=created_at,
        )

        result = trade_log_to_dict(log)

        self.assertEqual(result["id"], "log-1")
        self.assertEqual(result["event_type"], "risk_preview")
        self.assertEqual(result["payload"], {"approved": False})
        self.assertEqual(result["correlation_id"], "corr-1")
        self.assertEqual(result["created_at"], created_at)

    async def test_trade_log_endpoint_lists_filtered_logs(self):
        logs = [
            TradeLog(
                id="log-1",
                event_type="close_preview",
                payload={"deal_id": "deal-1"},
                correlation_id="deal-1",
                created_at=datetime.now(timezone.utc),
            )
        ]
        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"

        with patch("app.api.v1.audit.get_session", return_value=session_context):
            with patch("app.api.v1.audit.TradeRepo.list_logs", AsyncMock(return_value=logs)) as list_logs:
                result = await list_trade_logs(limit=5, event_type="close_preview", correlation_id="deal-1")

        list_logs.assert_awaited_once_with(
            "session",
            limit=5,
            event_type="close_preview",
            correlation_id="deal-1",
        )
        self.assertEqual(result["logs"][0]["event_type"], "close_preview")

    async def test_order_risk_preview_appends_trade_log(self):
        from app.core.state import TradingMode, trading_state
        from app.services.order_workflow_service import OrderWorkflowService

        original_mode = trading_state.mode
        trading_state.mode = TradingMode.OBSERVE_ONLY
        service = OrderWorkflowService()
        broker_client = AsyncMock()
        broker_client.get_market = AsyncMock(return_value={"snapshot": {"bid": 10, "offer": 10.2}})
        broker_context = AsyncMock()
        broker_context.__aenter__.return_value = broker_client
        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"

        try:
            with patch("app.services.order_workflow_service.BrokerClient", return_value=broker_context):
                with patch("app.services.order_workflow_service.get_session", return_value=session_context):
                    with patch(
                        "app.services.order_workflow_service.PositionRepo.get_open_positions",
                        AsyncMock(return_value=[]),
                    ):
                        with patch("app.services.order_workflow_service.append_trade_log", AsyncMock()) as append_log:
                            result = await service.preview_risk(
                                epic="GOLD",
                                direction="BUY",
                                size=0.1,
                                order_type="MARKET",
                            )
        finally:
            trading_state.mode = original_mode

        self.assertFalse(result["approved"])
        append_log.assert_awaited_once()
        self.assertEqual(append_log.await_args.args[0], "risk_preview")
        self.assertFalse(append_log.await_args.args[1]["approved"])

    async def test_close_preview_appends_trade_log(self):
        from app.core.state import TradingMode, trading_state
        from app.services.position_workflow_service import PositionWorkflowService

        original_mode = trading_state.mode
        trading_state.mode = TradingMode.OBSERVE_ONLY
        service = PositionWorkflowService()
        local_position = SimpleNamespace(
            id="deal-1",
            epic="GOLD",
            size=3.66,
            entry_price=4394.3,
            status="OPEN",
            deal_reference="p_deal-1",
        )
        broker_client = AsyncMock()
        broker_client.get_positions = AsyncMock(
            return_value={
                "positions": [
                    {
                        "position": {
                            "dealId": "deal-1",
                            "dealReference": "p_deal-1",
                            "size": 3.66,
                            "direction": "SELL",
                            "level": 4394.3,
                        },
                        "market": {
                            "epic": "GOLD",
                            "marketStatus": "CLOSED",
                            "bid": 4377.85,
                            "offer": 4378.35,
                        },
                    }
                ]
            }
        )
        broker_context = AsyncMock()
        broker_context.__aenter__.return_value = broker_client
        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"

        try:
            with patch("app.services.position_workflow_service.get_session", return_value=session_context):
                with patch(
                    "app.services.position_workflow_service.PositionRepo.get_position_by_id",
                    AsyncMock(return_value=local_position),
                ):
                    with patch("app.services.position_workflow_service.BrokerClient", return_value=broker_context):
                        with patch("app.services.position_workflow_service.append_trade_log", AsyncMock()) as append_log:
                            result = await service.preview_close("deal-1")
        finally:
            trading_state.mode = original_mode

        self.assertFalse(result["approved"])
        append_log.assert_awaited_once()
        self.assertEqual(append_log.await_args.args[0], "close_preview")
        self.assertEqual(append_log.await_args.args[1]["deal_id"], "deal-1")
