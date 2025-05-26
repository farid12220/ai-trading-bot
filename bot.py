import requests
import os
import time
import uuid
import datetime
import random

# Debugging: Print keys to confirm they're loaded
print("Alpaca Key:", os.environ.get("APCA_API_KEY_ID"))
print("Alpaca Secret:", os.environ.get("APCA_API_SECRET_KEY"))
print("Alpaca Base URL:", os.environ.get("ALPACA_BASE_URL"))

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("APCA_API_KEY_ID")
ALPACA_SECRET_KEY = os.environ.get("APCA_API_SECRET_KEY")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
RISK_TOLERANCE = 0.2
TRADE_INTERVAL = 5
HOLD_LIMIT = 5

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}

ALL_TICKERS = []
TOP_PERFORMERS = []
POSITIONS = {}

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            ALL_TICKERS = [stock['symbol'] for stock in data if stock['tradable']]
            print(f"Loaded {len(ALL_TICKERS)} tickers from Alpaca.")
        else:
            print("Failed to load tickers from Alpaca:", response.text)
    except Exception as e:
        print("Exception loading tickers:", str(e))

def fetch_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            return data['quote']['ap'], data['quote']['ap']
        return None, None
    except Exception as e:
        print(f"Error fetching price for {symbol}:", str(e))
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

def update_top_performers():
    global TOP_PERFORMERS
    print("Scanning top-performing stocks...")
    sample = random.sample(ALL_TICKERS, min(100, len(ALL_TICKERS)))
    gainers = []

    for symbol in sample:
        current, prev_close = fetch_price(symbol)
        if current and prev_close and prev_close > 0:
            change = (current - prev_close) / prev_close
            gainers.append((symbol, change))
        time.sleep(0.2)

    gainers.sort(key=lambda x: x[1], reverse=True)
    TOP_PERFORMERS = [g[0] for g in gainers[:10]]
    print(f"Top performers: {TOP_PERFORMERS}")

def simulate_trade():
    global POSITIONS

    for ticker in list(POSITIONS):
        position = POSITIONS[ticker]
        current_price, _ = fetch_price(ticker)
        if not current_price:
            continue

        if current_price > position['last_price']:
            POSITIONS[ticker]['last_price'] = current_price
            POSITIONS[ticker]['hold_count'] += 1
            print(f"{ticker} is rising, holding ({POSITIONS[ticker]['hold_count']}/{HOLD_LIMIT})")
        else:
            POSITIONS[ticker]['hold_count'] += 1

        if POSITIONS[ticker]['hold_count'] >= HOLD_LIMIT:
            entry_price = position['entry_price']
            profit = current_price - entry_price
            insert_trade(ticker, entry_price, current_price, profit)
            print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f}")
            del POSITIONS[ticker]
        time.sleep(0.1)

    if len(POSITIONS) < 3 and TOP_PERFORMERS:
        ticker = random.choice(TOP_PERFORMERS)
        entry_price, _ = fetch_price(ticker)
        if entry_price:
            POSITIONS[ticker] = {
                'entry_price': entry_price,
                'last_price': entry_price,
                'hold_count': 0
            }
            print(f"{ticker}: BOUGHT at {entry_price:.2f}")

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    update_top_performers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
        if int(time.time()) % 50 == 0:
            update_top_performers()
