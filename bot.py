import requests
import time
import uuid
import datetime
import os

# === CONFIG ===
ALPACA_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_API_SECRET")
BASE_URL = os.environ.get("ALPACA_BASE_URL")
HEADERS = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
}
MAX_POSITIONS = 50
DELAY_BETWEEN_REQUESTS = 1.0  # seconds

POSITIONS = {}


def fetch_tickers():
    url = f"{BASE_URL}/v2/assets"
    try:
        response = requests.get(url, headers=HEADERS)
        assets = response.json()
        return [asset['symbol'] for asset in assets if asset['tradable'] and asset['status'] == 'active']
    except Exception as e:
        print("Error fetching tickers:", e)
        return []


def fetch_price(symbol):
    url = f"{BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    try:
        response = requests.get(url, headers=HEADERS)
        data = response.json()
        return data['quote']['ap']  # ask price
    except Exception:
        return None


def simulate_trade(symbols):
    global POSITIONS
    for symbol in symbols:
        if len(POSITIONS) >= MAX_POSITIONS:
            break

        price = fetch_price(symbol)
        time.sleep(DELAY_BETWEEN_REQUESTS)

        if price is None:
            continue

        POSITIONS[symbol] = {
            'entry': price,
            'highest': price,
            'hold_time': 0
        }
        print(f"{symbol}: BOUGHT at {price:.2f}")


def monitor_positions():
    global POSITIONS
    to_remove = []

    for symbol, data in POSITIONS.items():
        current = fetch_price(symbol)
        time.sleep(DELAY_BETWEEN_REQUESTS)

        if current is None:
            continue

        entry = data['entry']
        high = data['highest']
        change = (current - entry) / entry

        if current > high:
            POSITIONS[symbol]['highest'] = current

        # Stop Loss
        if change <= -0.005:
            print(f"{symbol}: SOLD at {current:.2f}, Loss: {change*100:.2f}%")
            to_remove.append(symbol)
        # Profit Lock
        elif change >= 0.01 and (current - high) / high <= -0.005:
            print(f"{symbol}: SOLD at {current:.2f}, Profit from peak dip")
            to_remove.append(symbol)

    for symbol in to_remove:
        POSITIONS.pop(symbol, None)


if __name__ == "__main__":
    print("Starting bot...")
    tickers = fetch_tickers()
    print(f"Loaded {len(tickers)} tradable tickers from Alpaca")

    while True:
        try:
            monitor_positions()
            simulate_trade(tickers)
            time.sleep(5)
        except Exception as e:
            print("Runtime error:", e)
            time.sleep(5)
