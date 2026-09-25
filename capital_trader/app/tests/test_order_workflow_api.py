import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.orders import OrderRequest, create_order, create_workflow_order, preview_workflow_risk
from app.core.events import OrderRejected
from app.core.state import TradingMode, trading_state
from app.services.order_workflow_service import OrderWorkflowService, _market_quote


class OrderWorkflowApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_order_endpoint_is_disabled(self):
        with self.assertRaises(HTTPException) as exc:
            await create_order(
                OrderRequest(
                    epic="GOLD",
                    direction="BUY",
                    size=0.1,
                    stop_distance=1.0,
                )
            )

        self.assertEqual(exc.exception.status_code, 403)
        self.assertIn("Direct broker order placement is disabled", exc.exception.detail)

    async def test_workflow_endpoint_maps_risk_rejection_to_403(self):
        with patch(
            "app.api.v1.orders.order_workflow_service.submit_and_place",
            AsyncMock(side_effect=PermissionError("Risk rejected: trading_not_allowed")),
        ):
            with self.assertRaises(HTTPException) as exc:
                await create_workflow_order(
                    OrderRequest(
                        epic="GOLD",
                        direction="BUY",
                        size=0.1,
                        stop_distance=1.0,
                    )
                )

        self.assertEqual(exc.exception.status_code, 403)
        self.assertIn("trading_not_allowed", exc.exception.detail)

    async def test_risk_preview_endpoint_returns_preview_without_order(self):
        preview = {
            "workflow": "risk_preview",
            "approved": False,
            "reason": "trading_not_allowed",
            "request": {"epic": "GOLD", "direction": "BUY", "size": 0.1, "order_type": "MARKET"},
            "market": {"bid": 1.2, "ask": 1.3, "spread": 0.1, "max_spread": 0.5},
            "risk": {"trading_mode": "observe", "is_trading_allowed": False},
        }
        with patch(
            "app.api.v1.orders.order_workflow_service.preview_risk",
            AsyncMock(return_value=preview),
        ) as preview_risk:
            result = await preview_workflow_risk(
                OrderRequest(
                    epic="GOLD",
                    direction="BUY",
                    size=0.1,
                    stop_distance=1.0,
                )
            )

        preview_risk.assert_awaited_once()
        self.assertEqual(result["workflow"], "risk_preview")
        self.assertFalse(result["approved"])
        self.assertEqual(result["reason"], "trading_not_allowed")

    async def test_risk_preview_endpoint_maps_validation_to_422(self):
        with patch(
            "app.api.v1.orders.order_workflow_service.preview_risk",
            AsyncMock(side_effect=ValueError("market quote missing bid/offer")),
        ):
            with self.assertRaises(HTTPException) as exc:
                await preview_workflow_risk(
                    OrderRequest(
                        epic="GOLD",
                        direction="BUY",
                        size=0.1,
                        stop_distance=1.0,
                    )
                )

        self.assertEqual(exc.exception.status_code, 422)
        self.assertIn("market quote missing", exc.exception.detail)

    def test_market_quote_extracts_bid_offer_from_known_shapes(self):
        self.assertEqual(_market_quote({"bid": 1.2, "offer": 1.3}), (1.2, 1.3))
        self.assertEqual(_market_quote({"snapshot": {"bid": 2.2, "offer": 2.4}}), (2.2, 2.4))
        self.assertEqual(_market_quote({"market": {"bid": 3.2, "ask": 3.5}}), (3.2, 3.5))

    def test_market_quote_requires_bid_and_offer(self):
        with self.assertRaises(ValueError):
            _market_quote({"bid": 1.2})

    def test_base_event_factory_accepts_order_payload(self):
        event = OrderRejected.new(
            sequence_id=1,
            correlation_id="test-correlation",
            epic="GOLD",
            client_order_id="client-1",
            reason="trading_not_allowed",
        )

        self.assertEqual(event.epic, "GOLD")
        self.assertEqual(event.client_order_id, "client-1")
        self.assertEqual(event.reason, "trading_not_allowed")

    async def test_risk_preview_service_does_not_create_or_approve_order(self):
        original_mode = trading_state.mode
        trading_state.mode = TradingMode.OBSERVE_ONLY
        service = OrderWorkflowService()

        broker_client = AsyncMock()
        broker_client.get_market = AsyncMock(return_value={"snapshot": {"bid": 10.0, "offer": 10.2}})
        broker_context = AsyncMock()
        broker_context.__aenter__.return_value = broker_client

        session_context = AsyncMock()
        session_context.__aenter__.return_value = "session"

        try:
            with patch("app.services.order_workflow_service.BrokerClient", return_value=broker_context):
                with patch("app.services.order_workflow_service.get_session", return_value=session_context):
                    with patch(
                        "app.services.order_workflow_service.PositionRepo.get_open_positions",
                        AsyncMock(return_value=[object()]),
                    ):
                        with patch("app.services.order_workflow_service.OrderRepo.create", AsyncMock()) as create_order:
                            with patch("app.services.order_workflow_service.risk_manager.approve") as approve:
                                with patch(
                                    "app.services.order_workflow_service.append_trade_log",
                                    AsyncMock(),
                                ) as append_log:
                                    result = await service.preview_risk(
                                        epic="GOLD",
                                        direction="BUY",
                                        size=0.1,
                                        order_type="MARKET",
                                    )
        finally:
            trading_state.mode = original_mode

        self.assertFalse(result["approved"])
        self.assertIn("trading_not_allowed", result["reason"])
        self.assertEqual(result["market"]["bid"], 10.0)
        self.assertEqual(result["risk"]["open_positions_count"], 1)
        create_order.assert_not_awaited()
        approve.assert_not_called()
        append_log.assert_awaited_once()
        self.assertEqual(append_log.await_args.args[0], "risk_preview")
