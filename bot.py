import os
import requests
import time
import uuid
import datetime
import random

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
ALPACA_DATA_URL = os.environ.get("ALPACA_DATA_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
TRADE_INTERVAL = 5
MAX_OPEN_POSITIONS = 50
DELAY = 0.3
MOMENTUM_WINDOW_MINUTES = 15

ALL_TICKERS = []
POSITIONS = {}
daily_loss = 0
DAILY_LOSS_LIMIT = -100

def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    response = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if response.status_code == 200:
        data = response.json()
        return data["quote"].get("ap"), data["quote"].get("bp")
    return None, None

def fetch_momentum(symbol):
    start = end - datetime.timedelta(minutes=MOMENTUM_WINDOW_MINUTES)
    url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars?start={start.isoformat()}&end={end.isoformat()}&timeframe=1Min"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    time.sleep(DELAY)
    if r.status_code == 200:
        data = r.json().get("bars", [])
        if len(data) >= 2:
            start_price = data[0]["c"]
            end_price = data[-1]["c"]
            avg_volume = sum([bar["v"] for bar in data]) / len(data)
            return (end_price - start_price) / start_price, data[-1]["v"], avg_volume
    return None, None, None

def insert_trade(ticker, entry, exit, profit):
    global daily_loss
    daily_loss += profit
    payload = {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "entry_price": entry,
        "exit_price": exit,
        "profit": profit,
        "result": "WIN" if profit >= 0 else "LOSS",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{SUPABASE_URL}/rest/v1/trades"
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code not in [200, 201]:
        print("Error inserting trade:", r.text)

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        ALL_TICKERS = [a["symbol"] for a in data if a["tradable"] and a["exchange"] in ["NASDAQ", "NYSE"]]

def simulate_trade():
    global POSITIONS, daily_loss
    now = datetime.datetime.now()
    if now.hour == 9 and now.minute < 45:
        print("Waiting for market to stabilize...")
        return
    if daily_loss <= DAILY_LOSS_LIMIT:
        print("Daily loss limit hit. No further trading.")
        return

    for ticker in list(POSITIONS):
        pos = POSITIONS[ticker]
        current_price, _ = fetch_price(ticker)
        if not current_price:
            continue
        entry = pos["entry_price"]
        percent = (current_price - entry) / entry

        if percent < 0:
            pos["cumulative_loss"] += abs(percent)

        if percent >= 0.01:
            if not pos["trail_active"]:
                pos["trail_active"] = True
                pos["peak_price"] = current_price
            else:
                pos["peak_price"] = max(pos["peak_price"], current_price)

        sell = False
        reason = None

        if pos["cumulative_loss"] >= 0.005:
            sell = True
            reason = "Cumulative stop loss"
        elif pos["trail_active"]:
            drop = (pos["peak_price"] - current_price) / pos["peak_price"]
            if drop >= 0.005:
                sell = True
                reason = "Trailing stop hit"

        if sell:
            profit = current_price - entry
            insert_trade(ticker, entry, current_price, profit)
            print(f"{ticker} SOLD at {current_price:.2f}, P/L: {profit:.2f} ({percent*100:.2f}%) | {reason}")
            del POSITIONS[ticker]
        else:
            print(f"{ticker} holding, change: {percent*100:.2f}%")
        time.sleep(DELAY)

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue

        momentum, vol_now, vol_avg = fetch_momentum(ticker)
        if not momentum or not vol_now or not vol_avg:
            continue
        if momentum < 0.01 or vol_now < vol_avg:
            continue

        entry_price, _ = fetch_price(ticker)
        if not entry_price:
            continue
        POSITIONS[ticker] = {
            "entry_price": entry_price,
            "last_price": entry_price,
            "trail_active": False,
            "peak_price": entry_price,
            "cumulative_loss": 0
        }
        print(f"{ticker} BOUGHT at {entry_price:.2f}")
        time.sleep(DELAY)

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)

