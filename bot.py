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
DAILY_LOSS_LIMIT = -100

ALL_TICKERS = []
POSITIONS = {}
daily_profit = 0

def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()["quote"]
        return data["ap"], data["bp"]
    except:
        return None, None

def fetch_rsi(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/indicators/rsi?timeframe=1Hour&window=14"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        rsi = r.json()["rsi"][-1]
        return rsi
    except:
        return None

def fetch_volume(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars/latest?timeframe=1Min"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()["bar"]
        return data["v"]
    except:
        return None

def fetch_avg_volume(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/bars?timeframe=1Min&limit=50"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        bars = r.json()["bars"]
        return sum(bar["v"] for bar in bars) / len(bars)
    except:
        return None

def insert_trade(ticker, entry, exit, profit):
    global daily_profit
    daily_profit += profit
    payload = {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "entry_price": entry,
        "exit_price": exit,
        "profit": profit,
        "result": "WIN" if profit >= 0 else "LOSS",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
    }
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json"
    }
    requests.post(f"{SUPABASE_URL}/rest/v1/trades", json=payload, headers=headers)

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        ALL_TICKERS = [a["symbol"] for a in r.json() if a["tradable"] and a["exchange"] in ["NYSE", "NASDAQ"]]
        print(f"Loaded {len(ALL_TICKERS)} tradable tickers")
    else:
        print("Failed to load tickers")

def simulate_trade():
    global POSITIONS, daily_profit
    if daily_profit <= DAILY_LOSS_LIMIT:
        print("🔴 Daily loss limit reached. Trading paused.")
        return

    for ticker in list(POSITIONS):
        pos = POSITIONS[ticker]
        current_price, _ = fetch_price(ticker)
        if not current_price:
            continue

        entry = pos["entry_price"]
        change = (current_price - entry) / entry

        if change < 0:
            pos["cumulative_loss"] += abs(change)

        if change >= 0.005 and not pos.get("break_even"):
            pos["break_even"] = True

        rsi = fetch_rsi(ticker)
        reason, sell = None, False

        if pos["cumulative_loss"] >= 0.005:
            reason, sell = "Cumulative stop loss", True
        elif rsi and rsi > 80:
            reason, sell = "RSI > 80", True
        elif pos.get("break_even") and current_price < entry:
            reason, sell = "Break-even stop hit", True

        if sell:
            profit = current_price - entry
            insert_trade(ticker, entry, current_price, profit)
            print(f"{ticker}: SOLD at {current_price:.2f}, PnL: {profit:.2f} | {reason}")
            del POSITIONS[ticker]
        else:
            print(f"{ticker} holding: {change*100:.2f}%")

        time.sleep(DELAY)

    while len(POSITIONS) < MAX_OPEN_POSITIONS:
        ticker = random.choice(ALL_TICKERS)
        if ticker in POSITIONS:
            continue

        open_price, prev_price = fetch_price(ticker)
        if not open_price or not prev_price or prev_price == 0:
            continue

        change = (open_price - prev_price) / prev_price
        if change < 0.01:
            continue

        vol = fetch_volume(ticker)
        avg_vol = fetch_avg_volume(ticker)
        if not vol or not avg_vol or vol < avg_vol:
            continue

        POSITIONS[ticker] = {
            "entry_price": open_price,
            "cumulative_loss": 0,
            "break_even": False
        }
        print(f"{ticker}: BOUGHT at {open_price:.2f}")
        time.sleep(DELAY)

if __name__ == "__main__":
    print("🚀 Loading tickers...")
    load_all_tickers()
    print("🤖 Trading bot started...")
    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
