import os
import requests
import time
import uuid
import datetime
import random

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
}

RISK_TOLERANCE = 0.2
TRADE_INTERVAL = 10
HOLD_LIMIT = 12  # about 2 minutes at 10s interval
ALL_TICKERS = []
POSITIONS = {}

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        ALL_TICKERS = [stock['symbol'] for stock in data if stock['tradable'] and stock['exchange'] in ["NYSE", "NASDAQ"]]
        print(f"Loaded {len(ALL_TICKERS)} tickers from Alpaca.")
    else:
        print("Failed to load tickers from Alpaca:", response.text)

def fetch_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data.get("quote", {}).get("ap")  # ask price
    else:
        print(f"Error fetching price for {symbol}: {response.text}")
    return None

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
    MIN_PROFIT = 0.01

    for ticker in list(POSITIONS):
        position = POSITIONS[ticker]
        current_price = fetch_price(ticker)
        if not current_price:
            continue

        if current_price > position['last_price']:
            POSITIONS[ticker]['last_price'] = current_price
            POSITIONS[ticker]['hold_count'] = 0
            print(f"{ticker} is rising, holding...")
        else:
            POSITIONS[ticker]['hold_count'] += 1

        if POSITIONS[ticker]['hold_count'] >= HOLD_LIMIT:
            entry_price = position['entry_price']
            profit = current_price - entry_price
            if profit >= MIN_PROFIT:
                insert_trade(ticker, entry_price, current_price, profit)
                print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f}")
                del POSITIONS[ticker]
            else:
                print(f"{ticker}: Not enough profit to sell ({profit:.2f}), holding...")

        time.sleep(0.2)

    if len(POSITIONS) < 3 and ALL_TICKERS:
        random.shuffle(ALL_TICKERS)
        for ticker in ALL_TICKERS:
            if ticker not in POSITIONS:
                entry_price = fetch_price(ticker)
                if entry_price:
                    POSITIONS[ticker] = {
                        'entry_price': entry_price,
                        'last_price': entry_price,
                        'hold_count': 0
                    }
                    print(f"{ticker}: BOUGHT at {entry_price:.2f}")
                    break

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    print("Alpaca-powered AI trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
