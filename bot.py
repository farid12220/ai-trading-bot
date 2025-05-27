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
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
TRADE_INTERVAL = 5  # seconds
RISK_TOLERANCE = 0.2
HOLD_LIMIT = 5
STOP_LOSS_PERCENT = -0.5  # -0.5%
TAKE_PROFIT_TRIGGER = 1.0  # 1%
TRAILING_STOP_PERCENT = 0.5  # sell if drops 0.5% from high after 1% gain
MAX_POSITIONS_PER_TICKER = 50

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET
}

POSITIONS = {}


def fetch_tradable_tickers():
    url = f"{ALPACA_BASE_URL}/v2/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        tickers = [a['symbol'] for a in data if a['tradable'] and a['status'] == 'active']
        print(f"Loaded {len(tickers)} tradable tickers from Alpaca.")
        return tickers
    else:
        print("Failed to load tickers from Alpaca:", response.text)
        return []


def fetch_price(symbol):
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data['quote']['ap']  # ask price
    else:
        print(f"Error fetching price for {symbol}:", response.text)
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


def scan_and_trade(tickers):
    top = random.sample(tickers, min(50, len(tickers)))
    gainers = []

    for ticker in top:
        price = fetch_price(ticker)
        if not price:
            continue

        # BUY LOGIC
        if len(POSITIONS.get(ticker, [])) < MAX_POSITIONS_PER_TICKER:
            POSITIONS.setdefault(ticker, []).append({
                "entry_price": price,
                "last_price": price,
                "highest_price": price,
                "hold_count": 0
            })
            print(f"{ticker}: BOUGHT at {price:.2f}")


def evaluate_positions():
    for ticker in list(POSITIONS.keys()):
        positions = POSITIONS[ticker]
        current_price = fetch_price(ticker)
        if not current_price:
            continue

        to_remove = []
        for pos in positions:
            entry = pos['entry_price']
            highest = max(pos['highest_price'], current_price)
            pos['highest_price'] = highest

            change_percent = ((current_price - entry) / entry) * 100
            trailing_drop = ((highest - current_price) / highest) * 100

            if change_percent <= STOP_LOSS_PERCENT:
                profit = current_price - entry
                insert_trade(ticker, entry, current_price, profit)
                print(f"{ticker}: SOLD at {current_price:.2f}, Stop-loss hit, Profit: {profit:.2f}")
                to_remove.append(pos)
            elif change_percent >= TAKE_PROFIT_TRIGGER and trailing_drop >= TRAILING_STOP_PERCENT:
                profit = current_price - entry
                insert_trade(ticker, entry, current_price, profit)
                print(f"{ticker}: SOLD at {current_price:.2f}, Trailing profit sell, Profit: {profit:.2f}")
                to_remove.append(pos)
            else:
                print(f"{ticker} holding, change: {change_percent:.2f}%")

        for pos in to_remove:
            POSITIONS[ticker].remove(pos)

        if not POSITIONS[ticker]:
            del POSITIONS[ticker]


if __name__ == "__main__":
    all_tickers = fetch_tradable_tickers()
    print("AI Trading bot started...")

    while True:
        scan_and_trade(all_tickers)
        evaluate_positions()
        time.sleep(TRADE_INTERVAL)
