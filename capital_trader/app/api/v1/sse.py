import asyncio, json
from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse
from app.services.event_bus import EventBus
from app.core.events import PriceUpdated
router = APIRouter()
@router.get("/stream/prices")
async def stream_prices(request: Request):
    queue = asyncio.Queue()
    async def handler(event):
        if isinstance(event, PriceUpdated):
            data = {"epic": event.epic, "bid": event.bid, "ask": event.ask}
            await queue.put(data)
    await EventBus.subscribe(handler)
    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except Exception:
            pass
    return StreamingResponse(generator(), media_type="text/event-stream")