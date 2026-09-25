# Simple Documentation – Capital.com Trading Platform

## What this thing does

It is a tiny computer program that talks to Capital.com.  It watches prices, decides when to buy or sell, and keeps everything safe.

## Big ideas (but in simple words)

* **Safety first** – if something goes wrong, the program stops trading but still listens.
* **Broker is the boss** – the real numbers (what you own) come from Capital.com, not from our notebook.
* **Events are like messages** – price comes in, we make a "price‑updated" message, then other parts listen.

## The puzzle pieces

| Piece | What it does |
|------|--------------|
| **broker** | talks to Capital.com (login, websockets, orders) |
| **market** | turns raw price ticks into candles and signals |
| **risk** | checks if an order is allowed |
| **services** | glues everything together – start‑up, reconciliation, order flow |
| **db** | saves positions, orders, candles |
| **core** | settings, logging, shared state |
| **api** | simple web‑pages you can open in a browser |

## How the program starts

1. The web server (FastAPI) starts.
2. `StartupService` runs:
   * reads the `.env` file (your secret keys)
   * makes a session with the broker
   * pulls current positions and orders from Capital.com and writes them into the local database
   * opens a WebSocket so future price updates arrive
   * finally says *"All good – you can trade now"*.
3. A background task called `MarketStreamer` keeps reading price messages from the queue and creates *events*.

## Where the code lives (file names)

* `app/core/config.py` – where we keep the secret keys and settings.
* `app/broker/client.py` – tiny helper that calls the Capital.com REST API.
* `app/broker/websocket.py` – listens to the live price stream.
* `app/market/streaming.py` – takes raw ticks, makes events.
* `app/risk/manager.py` – decides if an order is allowed.
* `app/services/order_workflow_service.py` – creates an order in the DB and emits an event.
* `app/services/reconciliation_service.py` – makes sure the local DB matches what the broker says.
* `app/api/routes.py` – a few web pages: `/health`, `/positions`.
* `app/main.py` – the entry point that starts everything.

## Running it (simple version)

1. **Make a virtual box** – `python -m venv .venv` and `source .venv/bin/activate`.
2. **Put the secret words** – copy `.env.example` to `.env` and write your Capital.com user name, password and a database URL.
3. **Install the tools** – `pip install -r requirements.txt`.
4. **Start the server** – `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
5. Open a browser and go to `http://localhost:8000/api/health` – you should see *healthy*.

## What you see on the screen

* **Logs** – nice JSON lines that tell you what is happening.
* **/api/health** – a tiny page that says the program is alive.
* **/api/positions** – a list of what you own (empty at first).

## Next steps (if you want to play more)

* Replace the fake URLs in `broker/client.py` with the real Capital.com endpoints.
* Write a function that listens for `OrderSubmitted` events and actually sends the order to the broker.
* Add more web pages to create orders from a browser.
* Put a little picture on the screen that shows the latest price.

---

*Written in simple language so even a 5‑year‑old could follow along.*
