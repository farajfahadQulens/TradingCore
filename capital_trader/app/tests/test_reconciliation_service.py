import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.reconciliation_service import ReconciliationService, _new_summary


class ReconciliationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_orphan_position_is_imported_and_counted(self):
        service = ReconciliationService()
        broker_positions = [
            {
                "position": {
                    "dealId": "deal-1",
                    "size": 0.25,
                    "level": 2300.5,
                    "stopLevel": 2290.0,
                    "dealReference": "ref-1",
                },
                "market": {"epic": "GOLD"},
            }
        ]
        summary = _new_summary()

        with patch("app.services.reconciliation_service.PositionRepo.get_position_by_id", AsyncMock(return_value=None)):
            with patch("app.services.reconciliation_service.PositionRepo.create_position", AsyncMock()) as create_position:
                with patch("app.services.reconciliation_service.PositionRepo.get_open_positions", AsyncMock(return_value=[])):
                    await service._reconcile_positions("session", broker_positions, summary)

        create_position.assert_awaited_once()
        imported = create_position.await_args.args[1]
        self.assertEqual(imported.id, "deal-1")
        self.assertEqual(imported.epic, "GOLD")
        self.assertEqual(summary["orphan_positions_imported"], 1)

    async def test_missing_local_open_position_is_marked_closed(self):
        service = ReconciliationService()
        summary = _new_summary()
        local_position = SimpleNamespace(id="missing-deal", epic="US500")

        with patch("app.services.reconciliation_service.PositionRepo.get_open_positions", AsyncMock(return_value=[local_position])):
            with patch("app.services.reconciliation_service.PositionRepo.update_position", AsyncMock()) as update_position:
                await service._reconcile_positions("session", [], summary)

        update_position.assert_awaited_once()
        self.assertEqual(update_position.await_args.args[1], "missing-deal")
        self.assertEqual(update_position.await_args.kwargs["status"], "CLOSED")
        self.assertEqual(summary["positions_closed_locally"], 1)

    async def test_position_size_drift_is_updated_and_counted(self):
        service = ReconciliationService()
        broker_positions = [
            {
                "position": {
                    "dealId": "deal-1",
                    "size": 0.50,
                    "level": 2300.5,
                    "dealReference": "ref-1",
                },
                "market": {"epic": "GOLD"},
            }
        ]
        summary = _new_summary()
        existing = SimpleNamespace(id="deal-1", size=0.25)

        with patch("app.services.reconciliation_service.PositionRepo.get_position_by_id", AsyncMock(return_value=existing)):
            with patch("app.services.reconciliation_service.PositionRepo.update_position", AsyncMock()) as update_position:
                with patch("app.services.reconciliation_service.PositionRepo.get_open_positions", AsyncMock(return_value=[existing])):
                    await service._reconcile_positions("session", broker_positions, summary)

        update_position.assert_awaited_once()
        self.assertEqual(update_position.await_args.kwargs["size"], 0.50)
        self.assertEqual(summary["position_size_drifts_updated"], 1)

    async def test_orphan_working_order_is_imported_and_counted(self):
        service = ReconciliationService()
        working_orders = [
            {
                "workingOrder": {
                    "dealId": "order-1",
                    "status": "working",
                    "orderType": "limit",
                    "size": 0.1,
                    "level": 2301.0,
                },
                "market": {"epic": "GOLD"},
            }
        ]
        summary = _new_summary()

        with patch("app.services.reconciliation_service.OrderRepo.get_by_broker_id", AsyncMock(return_value=None)):
            with patch("app.services.reconciliation_service.OrderRepo.create", AsyncMock()) as create_order:
                await service._reconcile_orders("session", working_orders, summary)

        create_order.assert_awaited_once()
        imported = create_order.await_args.args[1]
        self.assertEqual(imported.broker_order_id, "order-1")
        self.assertEqual(imported.client_order_id, "broker:order-1")
        self.assertEqual(imported.epic, "GOLD")
        self.assertEqual(imported.state, "WORKING")
        self.assertEqual(summary["orphan_orders_imported"], 1)

    async def test_order_state_drift_is_updated_and_counted(self):
        service = ReconciliationService()
        existing = SimpleNamespace(id="local-order", state="PENDING")
        working_orders = [{"dealId": "order-1", "status": "working", "epic": "GOLD"}]
        summary = _new_summary()

        with patch("app.services.reconciliation_service.OrderRepo.get_by_broker_id", AsyncMock(return_value=existing)):
            with patch("app.services.reconciliation_service.OrderRepo.update_state", AsyncMock()) as update_state:
                await service._reconcile_orders("session", working_orders, summary)

        update_state.assert_awaited_once_with("session", "local-order", "WORKING")
        self.assertEqual(summary["order_state_drifts_updated"], 1)
