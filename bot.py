import os
import requests
import time
import uuid
import datetime
import random

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")

TRADE_INTERVAL = 5
MAX_OPEN_POSITIONS = 50
REQUEST_DELAY = 0.6  # safe API spacing

POSITIONS = {}

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET
}

# === Fetch Tradable Tickers ===
def fetch_tradable_assets():
    url = f"{ALPACA_BASE_URL}/v2/assets"
    params = {"status": "active", "tradable": "true"}
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        return [asset['symbol'] for asset in response.json() if asset['tradable'] and asset['status'] == 'active']
    else:
        print("Failed to load tickers:", response.text)
        return []

# === Fetch Live Price ===
def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data.get("quote", {}).get("ap")  # Ask price
    return None

# === Supabase Logger ===
def insert_trade(ticker, entry, exit, profit):
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
    requests.post(url, json=payload, headers=headers)

# === Sell Decision Logic ===
def check_position(symbol, entry_price, current_price):
    if not current_price:
        return False

    change = (current_price - entry_price) / entry_price
    highest = POSITIONS[symbol]['highest_price']

    if current_price > highest:
        POSITIONS[symbol]['highest_price'] = current_price

    if change <= -0.005:
        return True  # Stop loss hit

    if change >= 0.01:
        drop_from_peak = (current_price - highest) / highest
        if drop_from_peak <= -0.005:
            return True  # Gave back 0.5% from peak

    return False

# === Trading Simulation ===
def simulate_trading():
    global POSITIONS

    for symbol in list(POSITIONS):
        entry_price = POSITIONS[symbol]['entry_price']
        current_price = fetch_price(symbol)
        time.sleep(REQUEST_DELAY)

        if check_position(symbol, entry_price, current_price):
            profit = current_price - entry_price
            insert_trade(symbol, entry_price, current_price, profit)
            print(f"{symbol}: SOLD at {current_price:.2f}, Profit: {profit:.2f}")
            del POSITIONS[symbol]
        else:
            print(f"{symbol} holding, change: {((current_price - entry_price) / entry_price) * 100:.2f}%")

    # New buys
    if len(POSITIONS) < MAX_OPEN_POSITIONS:
        available = [s for s in ALL_TICKERS if s not in POSITIONS]
        if available:
            candidates = random.sample(available, min(5, len(available)))
            for symbol in candidates:
                if len(POSITIONS) >= MAX_OPEN_POSITIONS:
                    break
                price = fetch_price(symbol)
                time.sleep(REQUEST_DELAY)
                if price:
                    POSITIONS[symbol] = {
                        'entry_price': price,
                        'highest_price': price
                    }
                    print(f"{symbol}: BOUGHT at {price:.2f}")

# === MAIN ===
if __name__ == "__main__":
    print("Loading tickers...")
    ALL_TICKERS = fetch_tradable_assets()
    print(f"Loaded {len(ALL_TICKERS)} tradable tickers.")
    print("AI trading bot running...\n")

    while True:
        simulate_trading()
        time.sleep(TRADE_INTERVAL)
