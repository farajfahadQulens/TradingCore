import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.state import TradingMode, trading_state
from app.services.position_workflow_service import PositionWorkflowService


def broker_position(
    *,
    deal_id: str = "deal-1",
    epic: str = "GOLD",
    direction: str = "SELL",
    size: float = 3.66,
    market_status: str = "TRADEABLE",
) -> dict:
    return {
        "position": {
            "dealId": deal_id,
            "dealReference": f"p_{deal_id}",
            "size": size,
            "direction": direction,
            "level": 4394.3,
            "upl": 10.5,
        },
        "market": {
            "epic": epic,
            "marketStatus": market_status,
            "bid": 4377.85,
            "offer": 4378.35,
        },
    }


def local_position(
    *,
    deal_id: str = "deal-1",
    epic: str = "GOLD",
    size: float = 3.66,
    status: str = "OPEN",
):
    return SimpleNamespace(
        id=deal_id,
        epic=epic,
        size=size,
        entry_price=4394.3,
        status=status,
        deal_reference=f"p_{deal_id}",
    )


class PositionWorkflowServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_mode = trading_state.mode

    def tearDown(self):
        trading_state.mode = self.original_mode

    async def test_close_preview_requires_local_open_position(self):
        service = PositionWorkflowService()
        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"

        with patch("app.services.position_workflow_service.get_session", return_value=session_context):
            with patch(
                "app.services.position_workflow_service.PositionRepo.get_position_by_id",
                AsyncMock(return_value=None),
            ):
                with self.assertRaises(ValueError) as exc:
                    await service.preview_close("missing")

        self.assertIn("Local position not found", str(exc.exception))

    async def test_close_preview_reports_observe_mode_rejection(self):
        trading_state.mode = TradingMode.OBSERVE_ONLY
        service = PositionWorkflowService()
        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"
        broker_client = AsyncMock()
        broker_client.get_positions = AsyncMock(return_value={"positions": [broker_position()]})
        broker_context = AsyncMock()
        broker_context.__aenter__.return_value = broker_client

        with patch("app.services.position_workflow_service.get_session", return_value=session_context):
            with patch(
                "app.services.position_workflow_service.PositionRepo.get_position_by_id",
                AsyncMock(return_value=local_position()),
            ):
                with patch("app.services.position_workflow_service.BrokerClient", return_value=broker_context):
                    with patch("app.services.position_workflow_service.append_trade_log", AsyncMock()) as append_log:
                        result = await service.preview_close("deal-1")

        self.assertFalse(result["approved"])
        self.assertIn("trading_not_allowed", result["reason"])
        self.assertEqual(result["broker_position"]["estimated_close_price"], 4378.35)
        append_log.assert_awaited_once()
        self.assertEqual(append_log.await_args.args[0], "close_preview")

    async def test_close_position_updates_local_db_after_broker_close(self):
        trading_state.mode = TradingMode.LIVE_TRADING
        service = PositionWorkflowService()
        updated_position = local_position(status="CLOSED")
        updated_position.close_price = 4378.35
        updated_position.closed_at = "closed-at"

        broker_client = AsyncMock()
        broker_client.get_positions = AsyncMock(return_value={"positions": [broker_position()]})
        broker_client.close_position = AsyncMock(return_value={"dealReference": "close-ref"})
        broker_context = AsyncMock()
        broker_context.__aenter__.return_value = broker_client

        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"

        with patch("app.services.position_workflow_service.BrokerClient", return_value=broker_context):
            with patch("app.services.position_workflow_service.get_session", return_value=session_context):
                with patch(
                    "app.services.position_workflow_service.PositionRepo.get_position_by_id",
                    AsyncMock(return_value=local_position()),
                ):
                    with patch(
                        "app.services.position_workflow_service.PositionRepo.update_position",
                        AsyncMock(return_value=updated_position),
                    ) as update_position:
                        with patch("app.services.position_workflow_service.EventBus.publish", AsyncMock()) as publish:
                            with patch(
                                "app.services.position_workflow_service.append_trade_log",
                                AsyncMock(),
                            ) as append_log:
                                result = await service.close_position("deal-1")

        broker_client.close_position.assert_awaited_once_with("deal-1")
        update_position.assert_awaited_once()
        self.assertEqual(update_position.await_args.kwargs["status"], "CLOSED")
        self.assertEqual(update_position.await_args.kwargs["close_price"], 4378.35)
        publish.assert_awaited_once()
        self.assertTrue(result["closed"])
        self.assertEqual(result["position"]["status"], "CLOSED")
        self.assertEqual(
            [call.args[0] for call in append_log.await_args_list],
            ["close_preview", "position_close_requested", "position_closed"],
        )

    async def test_close_position_blocks_when_market_is_closed(self):
        trading_state.mode = TradingMode.LIVE_TRADING
        service = PositionWorkflowService()
        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"
        broker_client = AsyncMock()
        broker_client.get_positions = AsyncMock(return_value={"positions": [broker_position(market_status="CLOSED")]})
        broker_client.close_position = AsyncMock()
        broker_context = AsyncMock()
        broker_context.__aenter__.return_value = broker_client

        with patch("app.services.position_workflow_service.get_session", return_value=session_context):
            with patch(
                "app.services.position_workflow_service.PositionRepo.get_position_by_id",
                AsyncMock(return_value=local_position()),
            ):
                with patch("app.services.position_workflow_service.BrokerClient", return_value=broker_context):
                    with patch("app.services.position_workflow_service.append_trade_log", AsyncMock()) as append_log:
                        with self.assertRaises(PermissionError) as exc:
                            await service.close_position("deal-1")

        self.assertIn("market_not_tradeable", str(exc.exception))
        broker_client.close_position.assert_not_awaited()
        self.assertEqual(
            [call.args[0] for call in append_log.await_args_list],
            ["close_preview", "close_rejected"],
        )
