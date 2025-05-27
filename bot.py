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

ALL_TICKERS = []
TOP_PERFORMERS = []
POSITIONS = {}

# === HELPERS ===
def get_holding_limit(price):
    if price >= 150:
        return 5  # Large-cap: fast movers
    elif price >= 50:
        return 8  # Mid-cap: moderate hold
    else:
        return 12  # Small-cap: slower, more time

def fetch_price(symbol):
    url = f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data["quote"].get("ap"), data["quote"].get("bp")
    else:
        print(f"Error fetching price for {symbol}: {response.text}")
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

def load_all_tickers():
    global ALL_TICKERS
    url = f"{ALPACA_BASE_URL}/v2/assets"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        ALL_TICKERS = [asset['symbol'] for asset in data if asset['tradable'] and asset['exchange'] in ["NASDAQ", "NYSE"]]
        print(f"Loaded {len(ALL_TICKERS)} tradable tickers from Alpaca.")
    else:
        print("Failed to load tickers from Alpaca:", response.text)

def update_top_performers():
    global TOP_PERFORMERS
    print("Scanning top-performing stocks...")
    sample = random.sample(ALL_TICKERS, min(100, len(ALL_TICKERS)))
    gainers = []
    for symbol in sample:
        current, previous = fetch_price(symbol)
        if current and previous and previous > 0:
            change = (current - previous) / previous
            gainers.append((symbol, change))
        time.sleep(0.1)
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

        entry_price = position['entry_price']
        percent_change = (current_price - entry_price) / entry_price
        hold_limit = position['hold_limit']

        # Stop loss: -0.5%, Take profit: +1%
        if percent_change <= -0.005 or percent_change >= 0.01 or position['hold_count'] >= hold_limit:
            profit = current_price - entry_price
            insert_trade(ticker, entry_price, current_price, profit)
            print(f"{ticker}: SOLD at {current_price:.2f}, Profit: {profit:.2f} ({percent_change*100:.2f}%)")
            del POSITIONS[ticker]
        else:
            POSITIONS[ticker]['hold_count'] += 1
            print(f"{ticker} holding ({POSITIONS[ticker]['hold_count']}/{hold_limit})")
        time.sleep(0.1)

    if len(POSITIONS) < 3 and TOP_PERFORMERS:
        ticker = random.choice(TOP_PERFORMERS)
        entry_price, _ = fetch_price(ticker)
        if entry_price:
            hold_limit = get_holding_limit(entry_price)
            POSITIONS[ticker] = {
                'entry_price': entry_price,
                'last_price': entry_price,
                'hold_count': 0,
                'hold_limit': hold_limit
            }
            print(f"{ticker}: BOUGHT at {entry_price:.2f}, Hold Limit: {hold_limit}")

if __name__ == "__main__":
    print("Loading tickers...")
    load_all_tickers()
    update_top_performers()
    print("AI Trading bot started...")

    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
        if int(time.time()) % 60 == 0:
            update_top_performers()
