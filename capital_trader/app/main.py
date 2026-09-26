"""Entry point – starts FastAPI and the orchestrator background tasks.
"""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.broker.session import session_manager
from app.orchestrator import Orchestrator

orchestrator = Orchestrator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_manager.start()
    task = asyncio.create_task(orchestrator.run())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(lifespan=lifespan)

from app.api.routes import router as api_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.audit import router as audit_router
from app.api.v1.market import router as market_router
from app.api.v1.orders import router as orders_router
from app.api.v1.positions import router as position_router
from app.api.v1.sse import router as sse_router
from app.api.dashboard import router as dashboard_router

async def _corr_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

@app.get("/")
async def health_check():
    return {"status": "ok"}

app.middleware("http")(_corr_middleware)
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="/api/v1")
app.include_router(position_router, prefix="/api/v1")
app.include_router(accounts_router, prefix="/api/v1"))
app.include_router(orders_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/dashboard")
app.include_router(sse_router, prefix="/api/v1/sse")
app.include_router(audit_router, prefix="/api/v1")

dashboard_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
monitor_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "monitor"))
app.mount("/monitor", StaticFiles(directory=monitor_path, html=True), name="monitor")
app.mount("/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
