import os
import requests
import time
import uuid
import datetime

# === API Keys & URLs ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET
}

POSITIONS = {}
ALL_TICKERS = []
MAX_POSITIONS = 50
REQUEST_DELAY = 0.25  # delay between requests to avoid throttling

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        ALL_TICKERS = [a['symbol'] for a in data if a['tradable']]
        print(f"Loaded {len(ALL_TICKERS)} tradable tickers from Alpaca")
    else:
        print("Failed to load tickers:", response.text)

def fetch_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data['quote']['ap'], data['quote']['bp']  # ask price (ap), bid price (bp)
    else:
        return None, None

def simulate_trade():
    global POSITIONS

    # Check existing positions
    for symbol in list(POSITIONS.keys()):
        current_price, _ = fetch_price(symbol)
        if current_price is None:
            print(f"Failed to fetch price for {symbol}")
            continue

        position = POSITIONS[symbol]
        entry = position["entry_price"]
        highest = position["highest_price"]
        change = (current_price - entry) / entry

        # Update highest price
        if current_price > highest:
            POSITIONS[symbol]["highest_price"] = current_price

        # Stop-loss: -0.5%
        if change <= -0.005:
            print(f"{symbol}: SOLD at {current_price:.2f} (Stop-Loss)")
            del POSITIONS[symbol]
            continue

        # Profit rule: +1% then trail by -0.5%
        if change >= 0.01:
            drop_from_high = (current_price - highest) / highest
            if drop_from_high <= -0.005:
                print(f"{symbol}: SOLD at {current_price:.2f} (Trailing Stop)")
                del POSITIONS[symbol]
                continue

        time.sleep(REQUEST_DELAY)

    # Open new positions if below limit
    if len(POSITIONS) < MAX_POSITIONS:
        needed = MAX_POSITIONS - len(POSITIONS)
        sample = ALL_TICKERS[:needed * 2]  # buffer in case some are untradable

        for symbol in sample:
            if symbol in POSITIONS:
                continue
            ask, bid = fetch_price(symbol)
            if ask:
                POSITIONS[symbol] = {
                    "entry_price": ask,
                    "highest_price": ask,
                    "time": time.time()
                }
                print(f"{symbol}: BOUGHT at {ask:.2f}")
                time.sleep(REQUEST_DELAY)
                if len(POSITIONS) >= MAX_POSITIONS:
                    break

if __name__ == "__main__":
    print("Starting bot...")
    load_all_tickers()
    while True:
        simulate_trade()
        time.sleep(1)
