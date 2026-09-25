# How to run the tiny trading program (for kids)

## 1. Get ready

* Get a computer that has Python 3.11 or newer.
* Open a terminal (a black window where you type commands).

## 2. Make a safe playground

```bash
python -m venv .venv      # makes a little box for the program
source .venv/bin/activate  # puts you inside the box
```
You will see `(.venv)` at the start of your prompt – that means you are inside the box.

## 3. Tell the program its secrets

```bash
cp .env.example .env       # copy a template file
nano .env                  # open it and type:
# example (replace with your real stuff)
CAPITAL_USERNAME=your_name
CAPITAL_PASSWORD=your_pass
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/trading
```
Save and close the file (`Ctrl+X`, then `Y`).

## 4. Put the building blocks inside the box

```bash
pip install -r requirements.txt
```
The computer will download all the pieces the program needs.

## 5. Turn the program on

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
You will see something like:
```
INFO: Uvicorn running on http://0.0.0.0:8000
```
Leave this window open – the program is now listening for price data.

## 6. Check that it works

Open a web‑browser and type:
```
http://localhost:8000/api/health
```
You should see a tiny piece of JSON that says `"status": "healthy"`.

## 7. Look at your positions (what you own)

In the browser go to:
```
http://localhost:8000/api/positions
```
It will show an empty list at first – that is fine.

## 8. What happens behind the scenes?

* The program talks to Capital.com (login, price stream).
* It saves what it sees in a tiny database.
* If the price goes up or down a lot, it can decide to buy or sell.
* All of this is safe – if something goes wrong the program stops trading.

## 9. Have fun!

Now you have a tiny trading robot that watches the market.  You can add more pieces:
* Real order‑sending code.
* A picture that shows the latest price.
* Alerts that tell you when something important happens.

---

*Written for a kid – short, simple steps, no scary words.*
