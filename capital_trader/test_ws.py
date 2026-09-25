import pytest

@pytest.mark.skip(reason="WebSocket integration test requires real credentials")

import websockets
import json
from app.core.config import settings

CST = "N2XLGYMPiF8FsMX5j7B1OtUY"
SECURITY_TOKEN = "8bJJC04KAQtJUQtsL4Fv1WQkVdVNerd"
API_KEY = settings.capital_api_key.get_secret_value()

async def test():
    url = "wss://api-streaming-capital.backend-capital.com/connect"
    async with websockets.connect(url) as ws:
        print("Connected!")

        # Subscribe directly — tokens go in the subscription message
        msg = json.dumps({
            "destination": "marketData.subscribe",
            "correlationId": "test-gold",
            "cst": CST,
            "securityToken": SECURITY_TOKEN,
            "payload": {
                "epics": ["GOLD"]
            }
        })
        await ws.send(msg)
        print("Subscription sent")

        # Read responses
        for _ in range(3):
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"Response: {response}")

asyncio.run(test())