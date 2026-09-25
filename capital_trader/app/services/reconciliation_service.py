"""Reconciliation service — syncs local DB with broker state every 5 minutes.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from app.broker.client import BrokerClient
from app.db.session import get_session
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.repositories.positions import PositionRepo
from app.db.repositories.orders import OrderRepo
from app.db.models.reconciliation_run import ReconciliationRun
from app.db.repositories.reconciliation_runs import ReconciliationRunRepo
from app.core.logging import get_logger
from app.core.state import trading_state
from app.services.runtime_status import runtime_status
from app.services.trade_log_service import append_trade_log

log = get_logger(__name__)

RECONCILE_INTERVAL_SECONDS = 300  # 5 minutes


def _new_summary() -> dict:
    return {
        "broker_positions_seen": 0,
        "broker_orders_seen": 0,
        "orphan_positions_imported": 0,
        "position_size_drifts_updated": 0,
        "positions_closed_locally": 0,
        "orphan_orders_imported": 0,
        "order_state_drifts_updated": 0,
    }


def _working_order_payload(item: dict) -> dict:
    return item.get("workingOrder", item)


def _working_order_market(item: dict, order: dict) -> dict:
    market = item.get("market") or item.get("marketData") or {}
    if not market and isinstance(order.get("market"), dict):
        market = order["market"]
    return market


def _working_order_id(order: dict) -> str | None:
    return order.get("dealId") or order.get("id") or order.get("workingOrderId")


def _working_order_epic(item: dict, order: dict) -> str:
    market = _working_order_market(item, order)
    return order.get("epic") or market.get("epic") or "UNKNOWN"


def _working_order_state(order: dict) -> str:
    return (order.get("status") or order.get("state") or "PENDING").upper()


def _working_order_type(order: dict) -> str:
    return (order.get("orderType") or order.get("type") or order.get("direction") or "WORKING").upper()


def _working_order_size(order: dict) -> float:
    return float(order.get("size") or order.get("quantity") or 0)


def _working_order_level(order: dict) -> float | None:
    level = order.get("level") or order.get("limitLevel") or order.get("stopLevel")
    return float(level) if level is not None else None


class ReconciliationService:
    def __init__(self):
        self.running = False

    async def run(self):
        self.running = True
        log.info("reconciliation_started")
        while self.running:
            try:
                await self.reconcile()
            except Exception as e:
                log.error("reconciliation_error", error=str(e))
                runtime_status.mark_reconciliation_error(e)
                trading_state.set_degraded(reason=f"reconciliation_failed: {e}")
            await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)

    async def reconcile(self):
        log.info("reconciliation_running")
        runtime_status.mark_reconciliation_started()
        run_id = str(uuid.uuid4())
        summary = _new_summary()

        async with get_session() as session:
            await ReconciliationRunRepo.create(
                session,
                ReconciliationRun(
                    id=run_id,
                    status="RUNNING",
                    started_at=datetime.now(timezone.utc),
                    summary=summary,
                ),
            )

        try:
            async with BrokerClient() as client:
                broker_data = await client.get_positions()
                broker_orders = await client.get_working_orders()

            broker_positions = broker_data.get("positions", [])
            working_orders = broker_orders.get("workingOrders", [])
            summary["broker_positions_seen"] = len(broker_positions)
            summary["broker_orders_seen"] = len(working_orders)

            async with get_session() as session:
                await self._reconcile_positions(session, broker_positions, summary)
                await self._reconcile_orders(session, working_orders, summary)
                await ReconciliationRunRepo.update_fields(
                    session,
                    run_id,
                    status="COMPLETED",
                    completed_at=datetime.now(timezone.utc),
                    summary=summary,
                )

            log.info("reconciliation_complete", **summary)
            runtime_status.mark_reconciliation_completed(
                positions=len(broker_positions),
                orders=len(working_orders),
                summary=summary,
            )
            await append_trade_log(
                "reconciliation_completed",
                {
                    "run_id": run_id,
                    "summary": summary,
                },
                correlation_id=run_id,
            )
            return summary
        except Exception as exc:
            async with get_session() as session:
                await ReconciliationRunRepo.update_fields(
                    session,
                    run_id,
                    status="FAILED",
                    completed_at=datetime.now(timezone.utc),
                    error=str(exc),
                    summary=summary,
                )
            await append_trade_log(
                "reconciliation_failed",
                {
                    "run_id": run_id,
                    "error": str(exc),
                    "summary": summary,
                },
                correlation_id=run_id,
            )
            raise

    async def _reconcile_positions(self, session, broker_positions: list, summary: dict | None = None):
        summary = summary if summary is not None else _new_summary()
        broker_position_ids = set()
        for item in broker_positions:
            p = item["position"]
            m = item["market"]
            deal_id = p["dealId"]
            broker_position_ids.add(deal_id)

            existing = await PositionRepo.get_position_by_id(session, deal_id)

            if existing is None:
                # Orphan detected — position exists on broker but not in DB
                log.warning("orphan_position_detected", deal_id=deal_id, epic=m["epic"])
                pos = Position(
                    id=deal_id,
                    epic=m["epic"],
                    size=p["size"],
                    entry_price=p["level"],
                    stop_loss=p.get("stopLevel"),
                    deal_reference=p["dealReference"],
                    status="OPEN",
                )
                await PositionRepo.create_position(session, pos)
                summary["orphan_positions_imported"] += 1
                log.info("orphan_position_imported", deal_id=deal_id)
            else:
                # Check for drift
                if float(existing.size) != float(p["size"]):
                    log.warning("position_size_drift",
                                deal_id=deal_id,
                                local=float(existing.size),
                                broker=float(p["size"]))
                    await PositionRepo.update_position(
                        session, deal_id, size=p["size"]
                    )
                    summary["position_size_drifts_updated"] += 1

        open_positions = await PositionRepo.get_open_positions(session)
        for local_position in open_positions:
            if local_position.id in broker_position_ids:
                continue
            await PositionRepo.update_position(
                session,
                local_position.id,
                status="CLOSED",
                closed_at=datetime.now(timezone.utc),
            )
            summary["positions_closed_locally"] += 1
            log.warning(
                "local_position_closed_missing_from_broker",
                deal_id=local_position.id,
                epic=local_position.epic,
            )

    async def _reconcile_orders(self, session, working_orders: list, summary: dict | None = None):
        summary = summary if summary is not None else _new_summary()
        for item in working_orders:
            o = _working_order_payload(item)
            broker_order_id = _working_order_id(o)
            if not broker_order_id:
                continue

            existing = await OrderRepo.get_by_broker_id(session, broker_order_id)

            if existing is None:
                log.warning("orphan_order_detected", broker_order_id=broker_order_id)
                order = Order(
                    id=str(uuid.uuid4()),
                    epic=_working_order_epic(item, o),
                    order_type=_working_order_type(o),
                    state=_working_order_state(o),
                    size=_working_order_size(o),
                    limit_price=_working_order_level(o),
                    broker_order_id=broker_order_id,
                    client_order_id=f"broker:{broker_order_id}",
                )
                await OrderRepo.create(session, order)
                summary["orphan_orders_imported"] += 1
                log.info("orphan_order_imported", broker_order_id=broker_order_id)
            else:
                broker_state = _working_order_state(o)
                if broker_state and existing.state != broker_state:
                    log.warning("order_state_drift",
                                broker_order_id=broker_order_id,
                                local=existing.state,
                                broker=broker_state)
                    await OrderRepo.update_state(session, existing.id, broker_state)
                    summary["order_state_drifts_updated"] += 1

    async def stop(self):
        self.running = False
        log.info("reconciliation_stopped")


reconciliation_service = ReconciliationService()
