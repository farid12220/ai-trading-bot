import requests
import time
import uuid
import datetime
import os
import random

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}
POSITIONS = {}
MAX_POSITIONS = 50
HOLD_LIMIT = 5

# === HELPERS ===
def fetch_tickers():
    print("Loading tickers from Alpaca...")
    url = f"{ALPACA_BASE_URL}/v2/assets"
    try:
        res = requests.get(url, headers=HEADERS)
        res.raise_for_status()
        data = res.json()
        tradable = [a['symbol'] for a in data if a['tradable'] and a['status'] == 'active']
        print(f"Loaded {len(tradable)} tradable tickers from Alpaca")
        return tradable
    except Exception as e:
        print("Error loading tickers:", e)
        return []

def get_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    try:
        res = requests.get(url, headers=HEADERS)
        res.raise_for_status()
        quote = res.json()
        return quote.get("ask_price") or quote.get("bid_price")
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None

# === LOGIC ===
def scan_and_buy(tickers):
    if len(POSITIONS) >= MAX_POSITIONS:
        return
    random.shuffle(tickers)
    for symbol in tickers:
        if symbol in POSITIONS:
            continue
        price = get_price(symbol)
        if price:
            POSITIONS[symbol] = {
                "entry": price,
                "peak": price,
                "holds": 0
            }
            print(f"{symbol}: BOUGHT at {price:.2f}")
        time.sleep(0.25)
        if len(POSITIONS) >= MAX_POSITIONS:
            break

def monitor_positions():
    to_remove = []
    for symbol, pos in POSITIONS.items():
        price = get_price(symbol)
        if not price:
            continue

        entry = pos['entry']
        peak = pos['peak']

        if price > peak:
            POSITIONS[symbol]['peak'] = price

        change = ((price - entry) / entry) * 100
        print(f"{symbol} holding, change: {change:.2f}%")

        if change <= -0.5:
            print(f"{symbol}: SOLD at {price:.2f}, LOSS {change:.2f}%")
            to_remove.append(symbol)
        elif peak >= entry * 1.01 and price <= peak * 0.995:
            gain = ((price - entry) / entry) * 100
            print(f"{symbol}: SOLD at {price:.2f}, PROFIT {gain:.2f}%")
            to_remove.append(symbol)

        time.sleep(0.25)

    for sym in to_remove:
        del POSITIONS[sym]

# === MAIN ===
print("Starting bot...")
tickers = fetch_tickers()
if not tickers:
    print("No tickers loaded. Exiting.")
    exit()

while True:
    monitor_positions()
    scan_and_buy(tickers)
    time.sleep(5)
