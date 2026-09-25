from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from app.broker.client import BrokerClient, CapitalComConstants


class BrokerClientTests(IsolatedAsyncioTestCase):
    async def test_market_order_preserves_risk_distances(self):
        captured = {}

        async def fake_request(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return {"dealReference": "demo-ref"}

        with patch.object(BrokerClient, "_request", fake_request):
            client = BrokerClient()
            result = await client.place_order(
                epic="CS.D.EURUSD.TODAY",
                direction="BUY",
                size=0.1,
                order_type="MARKET",
                limit_distance=0.001,
                stop_distance=0.0005,
            )

        self.assertEqual(result, {"dealReference": "demo-ref"})
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], CapitalComConstants.POSITIONS_ENDPOINT)
        self.assertEqual(
            captured["kwargs"]["json"],
            {
                "epic": "CS.D.EURUSD.TODAY",
                "direction": "BUY",
                "size": 0.1,
                "limitDistance": 0.001,
                "stopDistance": 0.0005,
            },
        )
