import requests
import time
import uuid
import datetime
import os

# === CONFIG ===
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_API_SECRET = os.environ.get("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
RISK_TOLERANCE = 0.2
TRADE_INTERVAL = 5
HOLD_LIMIT = 5

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET
}

POSITIONS = {}
ALL_TICKERS = []
TOP_PERFORMERS = []

def load_all_tickers():
    global ALL_TICKERS
    print("Loading tickers from Alpaca...")
    url = f"{ALPACA_BASE_URL}/v2/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        ALL_TICKERS = [asset['symbol'] for asset in data if asset['tradable'] and asset['exchange'] in ['NASDAQ', 'NYSE']]
        print(f"Loaded {len(ALL_TICKERS)} tickers from Alpaca.")
    else:
        print(f"\u274C Failed to load tickers from Alpaca: {response.text}")

def fetch_price(symbol):
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/quotes/latest"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        return data.get("ask_price", 0), data.get("bid_price", 0)
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

def update_top_performers():
    global TOP_PERFORMERS
    print("Scanning top-performing stocks...")
    sample = ALL_TICKERS[:100]
    gainers = []
    for symbol in sample:
        ask, bid = fetch_price(symbol)
        if ask and bid and bid > 0:
            change = (ask - bid) / bid
            gainers.append((symbol, change))
        time.sleep(0.1)
    gainers.sort(key=lambda x: x[1], reverse=True)
    TOP_PERFORMERS = [g[0] for g in gainers[:10]]
    print(f"Top performers: {TOP_PERFORMERS}")

def simulate_trade():
    global POSITIONS
    for ticker in list(POSITIONS):
        position = POSITIONS[ticker]
        ask, _ = fetch_price(ticker)
        if not ask:
            continue
        if ask > position['last_price']:
            POSITIONS[ticker]['last_price'] = ask
            POSITIONS[ticker]['hold_count'] += 1
            print(f"{ticker} is rising, holding ({POSITIONS[ticker]['hold_count']}/{HOLD_LIMIT})")
        else:
            POSITIONS[ticker]['hold_count'] += 1
        if POSITIONS[ticker]['hold_count'] >= HOLD_LIMIT:
            entry_price = position['entry_price']
            profit = ask - entry_price
            insert_trade(ticker, entry_price, ask, profit)
            print(f"{ticker}: SOLD at {ask:.2f}, Profit: {profit:.2f}")
            del POSITIONS[ticker]
        time.sleep(0.1)

    if len(POSITIONS) < 3 and TOP_PERFORMERS:
        ticker = TOP_PERFORMERS[len(POSITIONS) % len(TOP_PERFORMERS)]
        ask, _ = fetch_price(ticker)
        if ask:
            POSITIONS[ticker] = {
                'entry_price': ask,
                'last_price': ask,
                'hold_count': 0
            }
            print(f"{ticker}: BOUGHT at {ask:.2f}")

if __name__ == "__main__":
    print("Starting Container")
    print("Alpaca Key:", ALPACA_API_KEY)
    print("Alpaca Secret:", ALPACA_API_SECRET)
    print("Alpaca Base URL:", ALPACA_BASE_URL)
    load_all_tickers()
    update_top_performers()
    print("AI Trading bot started...")
    while True:
        simulate_trade()
        time.sleep(TRADE_INTERVAL)
        if int(time.time()) % 50 == 0:
            update_top_performers()
