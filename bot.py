import os
import requests
import time
import uuid
import datetime
import random

# === CONFIG ===
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

TRADE_INTERVAL = 5  # seconds
HOLD_LIMIT = 5  # number of checks before selling

ALL_TICKERS = []
POSITIONS = {}

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        ALL_TICKERS = [asset["symbol"] for asset in data if asset["tradable"] and asset["exchange"] in ("NASDAQ", "NYSE", "ARCA")]
        print(f"Loaded {len(ALL_TICKERS)} tradable tickers from Alpaca.")
    else:
        print("Failed to load tickers from Alpaca:", response.text)

def fetch_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data.get("ask_price", None), data.get("bid_price", None)
    return None, None

def insert_trade(ticker, entry, exit, profit):
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
    url = f"{SUPABASE_URL}/rest/v1/trades"
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code not in [200, 201]:
        print("Error inserting trade:", r.text)

def simulate_trade():
    global POSITIONS

    # Close positions
    for ticker in list(POSITIONS):
        position = POSITIONS[ticker]
        current_price, _ = fetch_price(ticker)
        if not current_price:
            continue

        if current_price > position["last_price"]:
            POSITIONS[ticker]["last_price"] = current_price
            POSITIONS[ticker]["hold_count"] += 1
            print(f"{ticker} is rising, holding ({POSITIONS[ticker]['hold_count']}/{HOLD_LIMIT})")
        else:
            POSITIONS[ticker]["hold_count"] += 1

        if POSITIONS[ticker]["hold_count"] >= HOLD_LIMIT:
            entry_price = position["entry_price"]
            profit = current_price - entry_price
            insert_trade(ticker, entry_price, current_price, profit)
            print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f}")
            del POSITIONS[ticker]
        time.sleep(0.1)

    # Open new positions
    if len(POSITIONS) < 3 and ALL_TICKERS:
        sample = random.sample(ALL_TICKERS, 10)
        for ticker in sample:
            if ticker in POSITIONS:
                continue
            entry_price, _ = fetch_price(ticker)
            if entry_price:
                POSITIONS[ticker] = {
                    "entry_price": entry_price,
                    "last_price": entry_price,
                    "hold_count": 0
                }
                print(f"{ticker}: BOUGHT at {entry_price:.2f}")
                break

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
